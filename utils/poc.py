"""Standalone proof-of-concept for the Firewalla pairing handshake.

This script intentionally stays outside the Home Assistant integration code.
It is meant to prove the pairing flow before any config-flow work starts.

The current evidence supports a split architecture:

1. Cloud provisioning
    - generate the RSA keypair
    - establish ETP identity with `login/eptoken`
    - decrypt the QR payload into the rendezvous pairing object
    - execute the authenticated cloud link request
    - poll for the newly linked group until the box appears
2. Local runtime handoff
    - decrypt the durable symmetric key from the linked group
    - send the first local `init` Firewalla message to
      `http://{localIp}:8833/v1/encipher/message/{gid}`

The RSA key serialization formats in this file are verified against the public
Node tooling and the external builder brief:

- private key: PEM PKCS#8, unencrypted
- public key: PEM SPKI

Public Node tooling also shows the message transport uses AES-256-CBC with a
zero IV and base64 ciphertext. This proof keeps that cipher contract explicit
so experiments stay comparable with upstream behavior.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEFAULT_MESSAGE_PATH_TEMPLATE = "/v1/encipher/message/{gid}"
DEFAULT_TIMEOUT = 15.0
REQUIRED_QR_FIELDS = ("gid", "seed", "license", "ek", "ipaddress")
APP_SECRET = "fbb05afa-9145-41f1-8076-9de8be56f104"
APP_API_BASE = "https://firewalla.encipher.io/app/api/v2"
APP_GROUP_ENDPOINT_CANDIDATES = (
    "/ept/group/me",
    "/ept/groups/me",
)
DEFAULT_APP_ID = "com.rottiesoft.circle"
DEFAULT_APP_VERSION = "1.51.84"
DEFAULT_GROUP_POLL_ATTEMPTS = 10
DEFAULT_GROUP_POLL_INTERVAL = 3.0
DEFAULT_INIT_TARGET = "0.0.0.0"
DEFAULT_ARTIFACT_ROOT = Path(".artifacts/poc")


@dataclass(slots=True, frozen=True)
class PairingQrData:
    """Validated QR fields needed for the pairing proof."""

    gid: str
    seed: str
    license: str
    ek: str
    ipaddress: str
    raw_payload: dict[str, Any]

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> PairingQrData:
        """Build validated QR data from a mapping."""
        missing_fields = [field for field in REQUIRED_QR_FIELDS if field not in payload]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"QR JSON is missing required fields: {missing}")

        normalized: dict[str, str] = {}
        for field in REQUIRED_QR_FIELDS:
            value = payload[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"QR field {field!r} must be a non-empty string")
            normalized[field] = value.strip()

        return cls(
            gid=normalized["gid"],
            seed=normalized["seed"],
            license=normalized["license"],
            ek=normalized["ek"],
            ipaddress=normalized["ipaddress"],
            raw_payload=dict(payload),
        )


@dataclass(slots=True, frozen=True)
class GeneratedKeys:
    """PEM-encoded key material for Firewalla ETP."""

    private_pem: str
    public_pem: str


@dataclass(slots=True, frozen=True)
class GroupBootstrap:
    """Durable group data required for local Encipher messaging."""

    access_token: str | None
    gid: str
    eid: str
    aid: str
    symmetric_key_cipher: str
    symmetric_key_plain: str


@dataclass(slots=True, frozen=True)
class PairingCode:
    """Decrypted QR pairing object used for the cloud rendezvous step."""

    r: str
    evalue: dict[str, Any]
    raw_plaintext: str


@dataclass(slots=True, frozen=True)
class ETPIdentity:
    """Authenticated ETP identity returned by login/eptoken."""

    access_token: str
    eid: str
    aid: str
    groups: list[dict[str, Any]]


@dataclass(slots=True, frozen=True)
class GroupFetchResult:
    """Outcome of one cloud group fetch attempt."""

    source: str
    status: int
    response_text: str
    groups: list[dict[str, Any]]


@dataclass(slots=True, frozen=True)
class ArtifactPaths:
    """Filesystem locations for one PoC run's captured artifacts."""

    root: Path
    summary_json: Path
    qr_json: Path
    pairing_code_json: Path
    identity_json: Path
    cloud_link_response_txt: Path
    group_fetch_json: Path
    bootstrap_json: Path
    init_message_json: Path
    local_payload_json: Path
    local_response_txt: Path
    local_response_decrypted_json: Path


def generate_firewalla_keys() -> GeneratedKeys:
    """Generate the RSA keypair formatted exactly for Firewalla ETP."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    return GeneratedKeys(private_pem=private_pem, public_pem=public_pem)


def load_qr_json(raw_json: str) -> PairingQrData:
    """Parse and validate the Firewalla QR JSON."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as err:
        raise ValueError("QR JSON is not valid JSON") from err

    if not isinstance(payload, dict):
        raise ValueError("QR JSON root must be an object")

    return PairingQrData.from_mapping(payload)


def _json_dumps_compact(value: Any) -> str:
    """Serialize JSON using the compact separators seen in upstream tooling."""
    return json.dumps(value, separators=(",", ":"))


def build_fwmessage(
    *,
    eid: str,
    device_name: str,
    message_type: str,
    data: dict[str, Any],
    target: str = "0.0.0.0",
) -> dict[str, Any]:
    """Build the Firewalla-style message envelope used on the Encipher queue."""
    timezone_name = datetime.now().astimezone().tzname() or "UTC"
    return {
        "mtype": "msg",
        "message": {
            "mtype": "msg",
            "type": "jsondata",
            "msg": "",
            "from": device_name,
            "obj": {
                "type": "jsonmsg",
                "id": str(uuid.uuid4()),
                "mtype": message_type,
                "target": target,
                "data": data,
            },
            "appInfo": {
                "deviceName": device_name,
                "appID": DEFAULT_APP_ID,
                "platform": sys.platform,
                "timezone": timezone_name,
                "language": "en",
                "version": DEFAULT_APP_VERSION,
                "eid": eid,
            },
            "compressMode": 1,
        },
    }


def resolve_message_path(endpoint_path: str, qr_data: PairingQrData) -> str:
    """Resolve QR-derived placeholders in the target endpoint path."""
    try:
        return endpoint_path.format(
            gid=qr_data.gid,
            license=qr_data.license,
            seed=qr_data.seed,
        )
    except KeyError as err:
        raise ValueError(
            f"Unsupported placeholder in endpoint path: {err.args[0]}"
        ) from err


def derive_aes256_key(key_material: str) -> bytes:
    """Mirror the NodeJS SecureUtil AES key derivation behavior."""
    key = key_material[:32].encode("utf-8")
    if len(key) != 32:
        raise ValueError(
            "Derived AES key material must be at least 32 UTF-8 bytes long"
        )
    return key


def aes256_cbc_encrypt_to_base64(plaintext: str, key_material: str) -> str:
    """Encrypt a UTF-8 string with AES-256-CBC and return base64 ciphertext."""
    key = derive_aes256_key(key_material)
    iv = bytes(16)

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("utf-8")


def aes256_cbc_decrypt_from_base64(ciphertext: str, key_material: str) -> str:
    """Decrypt a base64 AES-256-CBC payload using the NodeJS key contract."""
    key = derive_aes256_key(key_material)
    iv = bytes(16)

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(base64.b64decode(ciphertext))
    padded_plaintext += decryptor.finalize()

    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    return plaintext.decode("utf-8")


def rsa_decrypt_base64(ciphertext: str, private_pem: str) -> str:
    """Decrypt base64 RSA ciphertext using Node's default OAEP/SHA-1 behavior."""
    private_key = serialization.load_pem_private_key(
        private_pem.encode("utf-8"),
        password=None,
    )
    plaintext = private_key.decrypt(
        base64.b64decode(ciphertext),
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        ),
    )
    return plaintext.decode("utf-8")


def derive_qr_bootstrap_key(qr_data: PairingQrData) -> str:
    """Return the pre-pairing AES material derived directly from the QR code."""
    return f"{qr_data.license[:8]}{qr_data.seed}"


def decrypt_pairing_code(qr_data: PairingQrData) -> PairingCode:
    """Decrypt the QR `ek` field into the pairing object used by the cloud link."""
    plaintext = aes256_cbc_decrypt_from_base64(
        qr_data.ek,
        derive_qr_bootstrap_key(qr_data),
    )

    try:
        parsed = json.loads(plaintext)
        if isinstance(parsed, dict):
            rendezvous_id = parsed.get("r") or parsed.get("rid")
            evalue = parsed.get("evalue")
            if isinstance(rendezvous_id, str) and isinstance(evalue, dict):
                return PairingCode(
                    r=rendezvous_id,
                    evalue=evalue,
                    raw_plaintext=plaintext,
                )
    except json.JSONDecodeError:
        pass

    return PairingCode(
        r=plaintext,
        evalue={"license": qr_data.license},
        raw_plaintext=plaintext,
    )


def build_login_payload(email: str, public_pem: str) -> dict[str, Any]:
    """Build the `login/eptoken` request payload."""
    return {
        "assertion": {
            "name": email,
            "info": {"name": "circle"},
            "publicKey": public_pem,
            "appId": DEFAULT_APP_ID,
            "appSecret": APP_SECRET,
            "signature": "",
        }
    }


def build_cloud_link_payload(pairing_code: PairingCode) -> dict[str, Any]:
    """Build the authenticated rendezvous payload for the cloud link step."""
    return {
        "rid": pairing_code.r,
        "evalue": _json_dumps_compact(pairing_code.evalue),
    }


def build_init_payload(target: str = DEFAULT_INIT_TARGET) -> dict[str, Any]:
    """Build the inner `init` request payload used after the cloud link succeeds."""
    return {"get": target}


def iter_nested_mappings(value: Any) -> Any:
    """Yield all nested mappings in a JSON-like structure."""
    if isinstance(value, dict):
        yield value
        for nested_value in value.values():
            yield from iter_nested_mappings(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from iter_nested_mappings(nested_value)


def build_outer_message_payload(
    encrypted_message: str,
    timestamp: float | None = None,
) -> dict[str, Any]:
    """Build the outer HTTP JSON body for the message queue."""
    return {
        "message": encrypted_message,
        "timestamp": timestamp if timestamp is not None else time.time(),
    }


async def post_json(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict[str, Any],
    *,
    access_token: str | None = None,
) -> tuple[int, str]:
    """Post JSON and return the raw HTTP status and text body."""
    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    async with session.post(url, json=payload, headers=headers) as response:
        return response.status, await response.text()


async def get_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    access_token: str,
) -> tuple[int, str]:
    """Issue an authenticated GET and return the raw HTTP status and text body."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with session.get(url, headers=headers) as response:
        return response.status, await response.text()


def write_key_file(path: Path, content: str, *, force: bool) -> None:
    """Persist a PEM file to disk."""
    if path.exists() and not force:
        raise FileExistsError(
            f"Refusing to overwrite existing file {path}; rerun with --force"
        )
    path.write_text(content, encoding="utf-8")


def create_artifact_paths(root: Path | None = None) -> ArtifactPaths:
    """Create a timestamped directory for all artifacts from one PoC run."""
    base_root = root or DEFAULT_ARTIFACT_ROOT
    run_dir = base_root / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)

    return ArtifactPaths(
        root=run_dir,
        summary_json=run_dir / "summary.json",
        qr_json=run_dir / "qr.json",
        pairing_code_json=run_dir / "pairing_code.json",
        identity_json=run_dir / "identity.json",
        cloud_link_response_txt=run_dir / "cloud_link_response.txt",
        group_fetch_json=run_dir / "group_fetch.json",
        bootstrap_json=run_dir / "bootstrap.json",
        init_message_json=run_dir / "local_init_message.json",
        local_payload_json=run_dir / "local_payload.json",
        local_response_txt=run_dir / "local_response.txt",
        local_response_decrypted_json=run_dir / "local_response_decrypted.json",
    )


def write_json_file(path: Path, value: Any) -> None:
    """Persist structured JSON output with stable formatting."""
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def write_text_file(path: Path, value: str) -> None:
    """Persist raw text output."""
    path.write_text(value, encoding="utf-8")


def write_run_artifacts(
    *,
    artifacts: ArtifactPaths,
    qr_data: PairingQrData,
    pairing_code: PairingCode,
    identity: ETPIdentity,
    cloud_status: int,
    cloud_response_text: str,
    group_fetch_result: GroupFetchResult,
    bootstrap: GroupBootstrap,
    init_message: dict[str, Any],
    local_payload: dict[str, Any],
    local_status: int,
    local_response_text: str,
    local_decrypted: str,
    local_ip: str,
) -> None:
    """Write the full PoC run outputs to disk for later analysis."""
    write_json_file(artifacts.qr_json, qr_data.raw_payload)
    write_json_file(
        artifacts.pairing_code_json,
        {
            "evalue": pairing_code.evalue,
            "r": pairing_code.r,
            "raw_plaintext": pairing_code.raw_plaintext,
        },
    )
    write_json_file(
        artifacts.identity_json,
        {
            "aid": identity.aid,
            "eid": identity.eid,
            "group_count": len(identity.groups),
            "used_existing_token": identity.eid == "<provided-token>",
        },
    )
    write_text_file(artifacts.cloud_link_response_txt, cloud_response_text)
    write_json_file(
        artifacts.group_fetch_json,
        {
            "group_count": len(group_fetch_result.groups),
            "response_text": group_fetch_result.response_text,
            "source": group_fetch_result.source,
            "status": group_fetch_result.status,
        },
    )
    write_json_file(
        artifacts.bootstrap_json,
        {
            "aid": bootstrap.aid,
            "eid": bootstrap.eid,
            "gid": bootstrap.gid,
            "has_access_token": bool(bootstrap.access_token),
            "symmetric_key_cipher": bootstrap.symmetric_key_cipher,
        },
    )
    write_json_file(artifacts.init_message_json, init_message)
    write_json_file(artifacts.local_payload_json, local_payload)
    write_text_file(artifacts.local_response_txt, local_response_text)

    try:
        local_decrypted_value: Any = json.loads(local_decrypted)
    except json.JSONDecodeError:
        local_decrypted_value = {"raw_text": local_decrypted}
    write_json_file(artifacts.local_response_decrypted_json, local_decrypted_value)
    write_json_file(
        artifacts.summary_json,
        {
            "artifact_dir": os.fspath(artifacts.root),
            "cloud_link_status": cloud_status,
            "group_fetch_source": group_fetch_result.source,
            "group_fetch_status": group_fetch_result.status,
            "linked_gid": bootstrap.gid,
            "local_ip": local_ip,
            "local_status": local_status,
        },
    )


async def post_verify(
    firewalla_ip: str,
    endpoint_path: str,
    payload: dict[str, Any],
    *,
    request_timeout: float,
) -> tuple[int, str]:
    """Send an authenticated local runtime message to the Firewalla box."""
    client_timeout = aiohttp.ClientTimeout(total=request_timeout)
    url = f"http://{firewalla_ip}:8833{endpoint_path}"

    async with (
        aiohttp.ClientSession(timeout=client_timeout) as session,
        session.post(url, json=payload) as response,
    ):
        return response.status, await response.text()


def parse_login_identity(response_text: str) -> ETPIdentity:
    """Parse the cloud login response into a strongly typed identity."""
    payload = json.loads(response_text)
    if not isinstance(payload, dict):
        raise ValueError("login/eptoken response was not a JSON object")

    access_token = payload.get("access_token")
    eid = payload.get("eid")
    aid = payload.get("aid")
    groups = payload.get("groups", [])

    if not isinstance(access_token, str) or not access_token:
        raise ValueError("login/eptoken response did not include access_token")
    if not isinstance(eid, str) or not eid:
        raise ValueError("login/eptoken response did not include eid")
    if not isinstance(aid, str) or not aid:
        raise ValueError("login/eptoken response did not include aid")
    if not isinstance(groups, list):
        raise ValueError("login/eptoken response did not include a groups list")

    return ETPIdentity(
        access_token=access_token,
        eid=eid,
        aid=aid,
        groups=groups,
    )


async def login_eptoken(
    session: aiohttp.ClientSession,
    *,
    email: str,
    public_pem: str,
) -> ETPIdentity:
    """Create or refresh the ETP identity used for the cloud link step."""
    status, response_text = await post_json(
        session,
        f"{APP_API_BASE}/login/eptoken",
        build_login_payload(email, public_pem),
    )
    if status != 200:
        raise ValueError(f"login/eptoken failed with HTTP {status}: {response_text}")
    return parse_login_identity(response_text)


async def link_group_cloud(
    session: aiohttp.ClientSession,
    *,
    access_token: str,
    pairing_code: PairingCode,
) -> tuple[int, str]:
    """Execute the authenticated cloud rendezvous step for additional pairing."""
    return await post_json(
        session,
        f"{APP_API_BASE}/ept/rendezvous/me",
        build_cloud_link_payload(pairing_code),
        access_token=access_token,
    )


def extract_groups(payload: Any) -> list[dict[str, Any]] | None:
    """Normalize cloud group-list responses that may wrap the groups array."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        groups = payload.get("groups")
        if isinstance(groups, list):
            return [item for item in groups if isinstance(item, dict)]
    return None


async def fetch_groups(
    session: aiohttp.ClientSession,
    *,
    identity: ETPIdentity,
    email: str,
    public_pem: str,
) -> tuple[GroupFetchResult, ETPIdentity]:
    """Fetch the linked groups from the strongest known cloud sources."""
    for endpoint in APP_GROUP_ENDPOINT_CANDIDATES:
        status, response_text = await get_json(
            session,
            f"{APP_API_BASE}{endpoint}",
            access_token=identity.access_token,
        )
        if status != 200:
            continue

        payload = json.loads(response_text)
        if groups := extract_groups(payload):
            return (
                GroupFetchResult(
                    source=endpoint,
                    status=status,
                    response_text=response_text,
                    groups=groups,
                ),
                identity,
            )

    refreshed_identity = await login_eptoken(
        session,
        email=email,
        public_pem=public_pem,
    )
    return (
        GroupFetchResult(
            source="/login/eptoken",
            status=200,
            response_text="<groups from login/eptoken response>",
            groups=refreshed_identity.groups,
        ),
        refreshed_identity,
    )


def extract_group_bootstrap(
    *,
    groups: list[dict[str, Any]],
    gid: str,
    private_pem: str,
    access_token: str,
) -> GroupBootstrap | None:
    """Extract the durable group symmetric key from a linked cloud group list."""
    matching_group = next((group for group in groups if group.get("_id") == gid), None)
    if matching_group is None:
        return None

    eid = matching_group.get("eid")
    aid = matching_group.get("aid")
    symmetric_keys = matching_group.get("symmetricKeys")
    if not isinstance(eid, str) or not eid:
        return None
    if not isinstance(aid, str) or not aid:
        return None
    if not isinstance(symmetric_keys, list) or not symmetric_keys:
        return None

    first_symmetric_key = symmetric_keys[0]
    if not isinstance(first_symmetric_key, dict):
        return None

    symmetric_key_cipher = first_symmetric_key.get("key")
    if not isinstance(symmetric_key_cipher, str) or not symmetric_key_cipher:
        return None

    symmetric_key_plain = rsa_decrypt_base64(symmetric_key_cipher, private_pem)

    return GroupBootstrap(
        access_token=access_token,
        gid=gid,
        eid=eid,
        aid=aid,
        symmetric_key_cipher=symmetric_key_cipher,
        symmetric_key_plain=symmetric_key_plain,
    )


async def poll_for_group(
    *,
    gid: str,
    identity: ETPIdentity,
    keys: GeneratedKeys,
    email: str,
    session: aiohttp.ClientSession,
    attempts: int,
    interval: float,
) -> tuple[GroupBootstrap, GroupFetchResult]:
    """Poll cloud groups until the linked Firewalla group becomes visible."""
    current_identity = identity
    last_fetch_result: GroupFetchResult | None = None

    for attempt in range(attempts):
        if attempt:
            await asyncio.sleep(interval)

        fetch_result, current_identity = await fetch_groups(
            session,
            identity=current_identity,
            email=email,
            public_pem=keys.public_pem,
        )
        last_fetch_result = fetch_result
        bootstrap = extract_group_bootstrap(
            groups=fetch_result.groups,
            gid=gid,
            private_pem=keys.private_pem,
            access_token=current_identity.access_token,
        )
        if bootstrap is not None:
            return bootstrap, fetch_result

    raise ValueError(
        "Cloud link did not produce a visible group before polling timed out"
        if last_fetch_result is None
        else (
            "Cloud link did not produce a visible group before polling timed out; "
            f"last group source={last_fetch_result.source} "
            f"status={last_fetch_result.status}"
        )
    )


def decrypt_local_message_response(response_text: str, symmetric_key: str) -> str:
    """Decrypt the local Encipher message response body."""
    payload = json.loads(response_text)
    if not isinstance(payload, dict):
        raise ValueError("Encipher response was not a JSON object")
    if response_error := payload.get("error"):
        raise ValueError(f"Encipher response contained error: {response_error}")

    response_message = payload.get("message")
    if not isinstance(response_message, str) or not response_message:
        raise ValueError("Encipher response did not include an encrypted message")

    return aes256_cbc_decrypt_from_base64(response_message, symmetric_key)


async def run_pairing_flow(
    *,
    qr_data: PairingQrData,
    keys: GeneratedKeys,
    device_name: str,
    email: str,
    request_timeout: float,
    group_poll_attempts: int,
    group_poll_interval: float,
    access_token: str | None,
    firewalla_ip_override: str | None,
) -> tuple[
    ETPIdentity,
    PairingCode,
    tuple[int, str],
    GroupBootstrap,
    GroupFetchResult,
    dict[str, Any],
    dict[str, Any],
    int,
    str,
    str,
]:
    """Run the approved cloud-provisioning flow followed by local init."""
    client_timeout = aiohttp.ClientTimeout(total=request_timeout)
    endpoint_path = resolve_message_path(DEFAULT_MESSAGE_PATH_TEMPLATE, qr_data)
    if not endpoint_path.startswith("/"):
        raise ValueError("Resolved local message path must start with '/'")

    async with aiohttp.ClientSession(timeout=client_timeout) as session:
        if access_token is None:
            identity = await login_eptoken(
                session,
                email=email,
                public_pem=keys.public_pem,
            )
        else:
            identity = ETPIdentity(
                access_token=access_token,
                eid="<provided-token>",
                aid="<provided-token>",
                groups=[],
            )
        pairing_code = decrypt_pairing_code(qr_data)
        cloud_link_result = await link_group_cloud(
            session,
            access_token=identity.access_token,
            pairing_code=pairing_code,
        )
        bootstrap, group_fetch_result = await poll_for_group(
            gid=qr_data.gid,
            identity=identity,
            keys=keys,
            email=email,
            session=session,
            attempts=group_poll_attempts,
            interval=group_poll_interval,
        )

    init_payload = build_init_payload()
    init_message = build_fwmessage(
        eid=bootstrap.eid,
        device_name=device_name,
        message_type="init",
        data=init_payload,
        target=DEFAULT_INIT_TARGET,
    )
    encrypted_message = aes256_cbc_encrypt_to_base64(
        _json_dumps_compact(init_message),
        bootstrap.symmetric_key_plain,
    )
    local_payload = build_outer_message_payload(
        encrypted_message,
        timestamp=int(time.time()),
    )
    local_status, local_response_text = await post_verify(
        firewalla_ip_override or qr_data.ipaddress,
        endpoint_path,
        local_payload,
        request_timeout=request_timeout,
    )
    local_decrypted = ""
    if local_status == 200:
        local_decrypted = decrypt_local_message_response(
            local_response_text,
            bootstrap.symmetric_key_plain,
        )

    return (
        identity,
        pairing_code,
        cloud_link_result,
        bootstrap,
        group_fetch_result,
        init_message,
        local_payload,
        local_status,
        local_response_text,
        local_decrypted,
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Proof-of-concept Firewalla local message pairing handshake",
    )
    qr_group = parser.add_mutually_exclusive_group(required=False)
    qr_group.add_argument(
        "--qr-json",
        help="Raw QR JSON string from the Firewalla app",
    )
    qr_group.add_argument(
        "--qr-file",
        type=Path,
        help="Path to a file containing the raw QR JSON",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email or label to bind to the ETP token during login",
    )
    parser.add_argument(
        "--access-token",
        help="Use an existing bearer token instead of calling login/eptoken",
    )
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help=(
            "Only validate cloud authentication with login/eptoken and one "
            "authenticated group fetch; do not pair or contact the local box"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--device-name",
        default="Home Assistant",
        help="Device name to place inside the Firewalla appInfo envelope",
    )
    parser.add_argument(
        "--firewalla-ip",
        help="Override the LAN IP used for the local post-link handoff",
    )
    parser.add_argument(
        "--group-poll-attempts",
        type=int,
        default=DEFAULT_GROUP_POLL_ATTEMPTS,
        help=(
            "How many times to poll for the newly linked group "
            f"(default: {DEFAULT_GROUP_POLL_ATTEMPTS})"
        ),
    )
    parser.add_argument(
        "--group-poll-interval",
        type=float,
        default=DEFAULT_GROUP_POLL_INTERVAL,
        help=(
            "Seconds between cloud group polls "
            f"(default: {DEFAULT_GROUP_POLL_INTERVAL})"
        ),
    )
    parser.add_argument(
        "--print-payload",
        action="store_true",
        help="Print the cloud and local payload details",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help=(
            "Directory where the full cloud and local responses should be written; "
            "defaults to a timestamped directory under .artifacts/poc"
        ),
    )
    parser.add_argument(
        "--print-full-response",
        action="store_true",
        help="Print the raw cloud and local response bodies to stdout",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate keys and payload without making the HTTPS request",
    )
    parser.add_argument(
        "--public-key-out",
        type=Path,
        default=Path("etp.public.pem"),
        help="Path to write the authorized public key on success",
    )
    parser.add_argument(
        "--private-key-out",
        type=Path,
        default=Path("etp.private.pem"),
        help="Path to write the authorized private key on success",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting existing output files",
    )
    return parser


def prompt_for_raw_qr_json() -> str:
    """Prompt for the raw QR JSON without shell-escaping issues."""
    print("--- Firewalla Local ETP Pairing ---")
    print("Scan your Firewalla 'Additional Pairing' QR code with a generic reader")
    return input("Paste the raw JSON string here and press Enter: ")


async def async_main() -> int:
    """Run the standalone pairing proof."""
    parser = build_parser()
    args = parser.parse_args()

    if args.auth_only and args.access_token:
        print(
            "Error: --auth-only cannot be combined with --access-token because "
            "that would skip the login/eptoken check",
            file=sys.stderr,
        )
        return 1

    if args.auth_only:
        artifacts = create_artifact_paths(args.artifact_dir)
        print("Phase A1: generating an ephemeral local RSA keypair")
        print("Phase A2: calling login/eptoken once")
        print("Phase A3: fetching groups once with the returned bearer token")
        print(f"Artifact directory: {artifacts.root}")

        keys = generate_firewalla_keys()
        client_timeout = aiohttp.ClientTimeout(total=args.timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            identity = await login_eptoken(
                session,
                email=args.email,
                public_pem=keys.public_pem,
            )
            group_fetch_result, _ = await fetch_groups(
                session,
                identity=identity,
                email=args.email,
                public_pem=keys.public_pem,
            )

        print("Cloud auth request: POST https://firewalla.encipher.io/app/api/v2/login/eptoken")
        print("Cloud auth HTTP 200")
        print(
            json.dumps(
                {
                    "aid": identity.aid,
                    "eid": identity.eid,
                    "group_count": len(identity.groups),
                },
                indent=2,
                sort_keys=True,
            )
        )
        print(
            "Cloud group fetch: GET "
            f"https://firewalla.encipher.io/app/api/v2{group_fetch_result.source}"
        )
        print(f"Cloud group fetch HTTP {group_fetch_result.status}")

        write_json_file(
            artifacts.identity_json,
            {
                "aid": identity.aid,
                "eid": identity.eid,
                "group_count": len(identity.groups),
                "used_existing_token": False,
            },
        )
        write_json_file(
            artifacts.group_fetch_json,
            {
                "group_count": len(group_fetch_result.groups),
                "response_text": group_fetch_result.response_text,
                "source": group_fetch_result.source,
                "status": group_fetch_result.status,
            },
        )
        write_json_file(
            artifacts.summary_json,
            {
                "artifact_dir": os.fspath(artifacts.root),
                "auth_only": True,
                "login_status": 200,
                "group_fetch_source": group_fetch_result.source,
                "group_fetch_status": group_fetch_result.status,
                "group_count": len(group_fetch_result.groups),
            },
        )
        print("Auth-only smoke check complete")
        return 0

    raw_qr_json = args.qr_json
    if raw_qr_json is None and args.qr_file is None:
        raw_qr_json = prompt_for_raw_qr_json()
    elif args.qr_file is not None:
        raw_qr_json = args.qr_file.read_text(encoding="utf-8")

    assert raw_qr_json is not None
    qr_data = load_qr_json(raw_qr_json)
    print(f"Successfully loaded QR data for IP: {qr_data.ipaddress}")
    keys = generate_firewalla_keys()
    pairing_code = decrypt_pairing_code(qr_data)
    artifacts = create_artifact_paths(args.artifact_dir)

    print(f"Artifact directory: {artifacts.root}")

    if args.dry_run:
        write_json_file(artifacts.qr_json, qr_data.raw_payload)
        write_json_file(
            artifacts.pairing_code_json,
            {
                "evalue": pairing_code.evalue,
                "r": pairing_code.r,
                "raw_plaintext": pairing_code.raw_plaintext,
            },
        )
        print("Phase 1: generated local RSA keypair")
        print("Phase 2: decrypted the QR pairing object")
        print(f"Pairing object plaintext: {pairing_code.raw_plaintext}")
        print("Cloud link endpoint: POST /app/api/v2/ept/rendezvous/me")
        print("Dry run complete; no network request was sent")
        return 0

    print("Phase 1: generated local RSA keypair")
    print("Phase 2: establishing the cloud ETP identity")
    print("Phase 3: decrypting the QR pairing object")
    print("Phase 4: executing the authenticated cloud link")
    print("Phase 5: polling for the newly linked group")
    print("Phase 6: sending the first local init message")
    (
        identity,
        pairing_code,
        cloud_link_result,
        bootstrap,
        group_fetch_result,
        init_message,
        local_payload,
        local_status,
        local_response_text,
        local_decrypted,
    ) = await run_pairing_flow(
        qr_data=qr_data,
        keys=keys,
        device_name=args.device_name,
        email=args.email,
        request_timeout=args.timeout,
        group_poll_attempts=args.group_poll_attempts,
        group_poll_interval=args.group_poll_interval,
        access_token=args.access_token,
        firewalla_ip_override=args.firewalla_ip,
    )

    cloud_status, cloud_response_text = cloud_link_result

    print(
        "Cloud link request: POST "
        "https://firewalla.encipher.io/app/api/v2/ept/rendezvous/me"
    )
    print(f"Cloud link HTTP {cloud_status}")
    if args.print_full_response:
        print(cloud_response_text)
    if cloud_status != 200:
        return 1

    if args.print_payload:
        print("Identity:")
        print(
            json.dumps(
                {
                    "aid": identity.aid,
                    "eid": identity.eid,
                    "group_count": len(identity.groups),
                },
                indent=2,
                sort_keys=True,
            )
        )
        print("Pairing code:")
        print(
            json.dumps(
                {
                    "evalue": pairing_code.evalue,
                    "r": pairing_code.r,
                },
                indent=2,
                sort_keys=True,
            )
        )
        print("Local init message:")
        print(json.dumps(init_message, indent=2, sort_keys=True))
        print("Local outer payload:")
        print(json.dumps(local_payload, indent=2, sort_keys=True))
        print("Last group fetch result:")
        print(
            json.dumps(
                {
                    "group_count": len(group_fetch_result.groups),
                    "source": group_fetch_result.source,
                    "status": group_fetch_result.status,
                },
                indent=2,
                sort_keys=True,
            )
        )

    print("Recovered group bootstrap:")
    print(
        json.dumps(
            {
                "gid": bootstrap.gid,
                "eid": bootstrap.eid,
                "aid": bootstrap.aid,
                "has_access_token": bool(bootstrap.access_token),
            },
            indent=2,
            sort_keys=True,
        )
    )

    print(
        "Local handoff request: POST http://"
        f"{args.firewalla_ip or qr_data.ipaddress}:8833"
        f"{resolve_message_path(DEFAULT_MESSAGE_PATH_TEMPLATE, qr_data)}"
    )
    print(f"Local HTTP {local_status}")
    if args.print_full_response:
        print(local_response_text)
    if local_status != 200:
        return 1

    write_run_artifacts(
        artifacts=artifacts,
        qr_data=qr_data,
        pairing_code=pairing_code,
        identity=identity,
        cloud_status=cloud_status,
        cloud_response_text=cloud_response_text,
        group_fetch_result=group_fetch_result,
        bootstrap=bootstrap,
        init_message=init_message,
        local_payload=local_payload,
        local_status=local_status,
        local_response_text=local_response_text,
        local_decrypted=local_decrypted,
        local_ip=args.firewalla_ip or qr_data.ipaddress,
    )

    print("Decrypted local init response written to artifact directory")

    write_key_file(args.public_key_out, keys.public_pem, force=args.force)
    write_key_file(args.private_key_out, keys.private_pem, force=args.force)
    print(f"Saved public key to {args.public_key_out}")
    print(f"Saved private key to {args.private_key_out}")
    return 0


def main() -> int:
    """Run the async CLI entry point."""
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except (
        aiohttp.ClientError,
        TimeoutError,
        FileExistsError,
        OSError,
        ValueError,
    ) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
