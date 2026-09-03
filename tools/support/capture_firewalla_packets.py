"""Windows helper to capture Firewalla packets and build a safe report.

This support tool is intentionally narrow:

- prompt for router IP address or hostname and SSH password
- optionally, accept QR JSON and email for cloud provisioning
- SSH to the Firewalla box as user ``pi`` on port ``22``
- start a remote tcpdump capture in the background
- wait for the user to reproduce the behavior they want to capture
- stop the capture, download the pcap, and clean up remote files
- build a local safe report from cleartext HTTP metadata only
- when provisioning was used, write a sidecar key file alongside the pcap
  so the capture can be decrypted later

It does not include the raw pcap or key in the safe report archive.
"""

# pylint: disable=too-many-lines

from __future__ import annotations

import sys

if sys.version_info < (3, 11):  # noqa: UP036
    print(
        "Error: Python 3.11 or newer is required for this script. "
        f"Current version: {sys.version_info.major}.{sys.version_info.minor}",
        file=sys.stderr,
    )
    sys.exit(1)

import argparse
import asyncio
import base64
import getpass
import ipaddress
import json
import re
import time
import zipfile
from collections import Counter, defaultdict
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

try:
    import paramiko
except ImportError:  # pragma: no cover - environment-specific dependency
    paramiko = None

try:
    from scp import SCPClient, SCPException
except ImportError:  # pragma: no cover - environment-specific dependency
    SCPClient = None
    SCPException = None

try:
    from scapy.layers.inet import IP, TCP
    from scapy.utils import rdpcap
except ImportError:  # pragma: no cover - environment-specific dependency
    IP = None
    TCP = None
    rdpcap = None

try:
    import aiohttp
except ImportError:  # pragma: no cover - environment-specific dependency
    aiohttp = None

try:
    from cryptography.hazmat.primitives import hashes, padding, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:  # pragma: no cover - environment-specific dependency
    CRYPTOGRAPHY_AVAILABLE = False

if TYPE_CHECKING:
    from paramiko import SSHClient


PROVISIONING_APP_API_BASE: Final = "https://firewalla.encipher.io/app/api/v2"
PROVISIONING_APP_ID: Final = "com.rottiesoft.circle"
PROVISIONING_APP_SECRET: Final = "fbb05afa-9145-41f1-8076-9de8be56f104"
PROVISIONING_GROUP_POLL_ATTEMPTS: Final = 20
PROVISIONING_GROUP_POLL_INTERVAL: Final = 3.0
PROVISIONING_REQUEST_TIMEOUT: Final = 15.0
PROVISIONING_REQUIRED_QR_FIELDS: Final = ("gid", "seed", "license", "ek", "ipaddress")
PROVISIONING_ENDPOINT_LOGIN: Final = "/login/eptoken"
PROVISIONING_ENDPOINT_RENDEZVOUS: Final = "/ept/rendezvous/me"
PROVISIONING_ENDPOINT_GROUP_CANDIDATES: Final = ("/ept/group/me", "/ept/groups/me")

SSH_PORT: Final = 22
SSH_USER: Final = "pi"
REMOTE_PCAP_PATH: Final = "/tmp/firewalla_capture.pcap"
REMOTE_PID_PATH: Final = "/tmp/firewalla_capture.pid"
DEFAULT_CONNECT_TIMEOUT: Final = 10.0
DEFAULT_CAPTURE_FILTER: Final = "tcp port 8833"
SERVER_PORT: Final = 8833
MESSAGE_PATH_RE = re.compile(r"(/v1/encipher/message/)[^\s?]+")


@dataclass(slots=True)
class Segment:
    """One TCP payload segment captured from the local Firewalla transport."""

    seq: int
    data: bytes
    ts: float


@dataclass(slots=True)
class HttpMessage:
    """One parsed HTTP message from a reassembled port 8833 TCP stream."""

    ts: float | None
    first_line: str
    headers: dict[str, str]
    content_length: int
    body: bytes = b""


@dataclass(slots=True)
class SafeReportEvent:
    """One safe report event derived from cleartext packet metadata."""

    timestamp_utc: str
    direction: str
    kind: str
    message_class: str
    first_line: str
    content_length: int | None = None
    user_agent: str | None = None
    content_type: str | None = None
    latency_seconds: float | None = None
    status_code: str | None = None


@dataclass(slots=True, frozen=True)
class _ProvisioningQrData:
    """Validated QR fields needed for cloud provisioning."""

    gid: str
    seed: str
    license: str
    ek: str
    ipaddress: str

    @classmethod
    def from_raw_json(cls, raw_json: str) -> _ProvisioningQrData:
        """Parse and validate raw QR JSON."""
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as err:
            raise ValueError("QR JSON is not valid JSON") from err
        if not isinstance(payload, dict):
            raise ValueError("QR JSON root must be an object")
        missing = [f for f in PROVISIONING_REQUIRED_QR_FIELDS if f not in payload]
        if missing:
            raise ValueError(f"QR JSON missing required fields: {', '.join(missing)}")
        normalized: dict[str, str] = {}
        for field in PROVISIONING_REQUIRED_QR_FIELDS:
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
        )


@dataclass(slots=True, frozen=True)
class _ProvisioningResult:
    """Result of one cloud provisioning run."""

    symmetric_key: str
    gid: str
    eid: str
    aid: str


def _derive_qr_key(license_value: str, seed: str) -> str:
    """Derive the pre-pairing AES key material from QR fields."""
    return f"{license_value[:8]}{seed}"


def _derive_aes256_key(key_material: str) -> bytes:
    """Derive AES-256 key matching NodeJS SecureUtil behavior."""
    key = key_material[:32].encode("utf-8")
    if len(key) != 32:
        raise ValueError(
            "Derived AES key material must be at least 32 UTF-8 bytes long"
        )
    return key


def _aes256_cbc_decrypt_from_base64(ciphertext: str, key_material: str) -> str:
    """Decrypt a base64 AES-256-CBC payload."""
    key = _derive_aes256_key(key_material)
    iv = bytes(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(base64.b64decode(ciphertext)) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


def _generate_firewalla_keys() -> tuple[str, str]:
    """Generate RSA keypair and return (private_pem, public_pem)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
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
    return private_pem, public_pem


def _rsa_decrypt_base64(ciphertext: str, private_pem: str) -> str:
    """Decrypt base64 RSA ciphertext using OAEP/SHA-1."""
    private_key = serialization.load_pem_private_key(
        private_pem.encode("utf-8"), password=None
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


def _decrypt_pairing_code(qr_data: _ProvisioningQrData) -> dict[str, object]:
    """Decrypt the QR ek field and return the pairing rendezvous data."""
    plaintext = _aes256_cbc_decrypt_from_base64(
        qr_data.ek,
        _derive_qr_key(qr_data.license, qr_data.seed),
    )
    try:
        parsed = json.loads(plaintext)
    except json.JSONDecodeError:
        return {"r": plaintext, "evalue": {"license": qr_data.license}}
    if not isinstance(parsed, dict):
        raise ValueError("QR pairing payload did not decode to an object")
    return parsed


async def _provision_symmetric_key(
    qr_data: _ProvisioningQrData,
    private_pem: str,
    public_pem: str,
    email: str,
) -> _ProvisioningResult:
    """Run the cloud provisioning flow and return the symmetric key."""
    pairing_code = _decrypt_pairing_code(qr_data)
    rendezvous_id = pairing_code.get("r") or pairing_code.get("rid")
    evalue = pairing_code.get("evalue")
    if not isinstance(rendezvous_id, str) or not isinstance(evalue, dict):
        raise ValueError("QR pairing code missing rendezvous data")

    timeout = aiohttp.ClientTimeout(total=PROVISIONING_REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Step 1: login/eptoken
        login_payload = {
            "assertion": {
                "name": email,
                "info": {"name": "circle"},
                "publicKey": public_pem,
                "appId": PROVISIONING_APP_ID,
                "appSecret": PROVISIONING_APP_SECRET,
                "signature": "",
            }
        }
        async with session.post(
            f"{PROVISIONING_APP_API_BASE}{PROVISIONING_ENDPOINT_LOGIN}",
            json=login_payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"login/eptoken returned HTTP {resp.status}")
            login_data: dict[str, object] = await resp.json()
        access_token = login_data.get("access_token")
        eid = login_data.get("eid")
        aid = login_data.get("aid")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("login/eptoken response missing access_token")
        if not isinstance(eid, str) or not eid:
            raise RuntimeError("login/eptoken response missing eid")
        if not isinstance(aid, str) or not aid:
            raise RuntimeError("login/eptoken response missing aid")

        # Step 2: cloud rendezvous link
        rendezvous_payload = {
            "rid": rendezvous_id,
            "evalue": json.dumps(evalue, separators=(",", ":")),
        }
        async with session.post(
            f"{PROVISIONING_APP_API_BASE}{PROVISIONING_ENDPOINT_RENDEZVOUS}",
            json=rendezvous_payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Cloud rendezvous returned HTTP {resp.status}")

        # Step 3: poll for group with symmetric key
        gid = qr_data.gid
        current_access_token: str = access_token
        for attempt in range(PROVISIONING_GROUP_POLL_ATTEMPTS):
            if attempt:
                await asyncio.sleep(PROVISIONING_GROUP_POLL_INTERVAL)

            for endpoint in PROVISIONING_ENDPOINT_GROUP_CANDIDATES:
                async with session.get(
                    f"{PROVISIONING_APP_API_BASE}{endpoint}",
                    headers={"Authorization": f"Bearer {current_access_token}"},
                ) as resp:
                    if resp.status == 401:
                        break
                    if resp.status != 200:
                        continue
                    groups_data: object = await resp.json()

                groups: list[dict[str, Any]] = []
                if isinstance(groups_data, list):
                    groups = [g for g in groups_data if isinstance(g, dict)]
                elif isinstance(groups_data, dict):
                    raw = groups_data.get("groups")
                    if isinstance(raw, list):
                        groups = [g for g in raw if isinstance(g, dict)]

                for group in groups:
                    if group.get("_id") != gid:
                        continue
                    group_eid = group.get("eid")
                    group_aid = group.get("aid")
                    sym_keys = group.get("symmetricKeys")
                    has_rkey = bool(
                        sym_keys
                        and isinstance(sym_keys, list)
                        and len(sym_keys) > 0
                        and isinstance(sym_keys[0], dict)
                        and sym_keys[0].get("rkey")
                    )
                    print(
                        f"  Found matching group: gid={gid}, "
                        f"eid={'present' if group_eid else 'absent'}, "
                        f"aid={'present' if group_aid else 'absent'}, "
                        f"symmetricKeys="
                        f"{len(sym_keys) if isinstance(sym_keys, list) else 0}, "
                        f"rkey={'present' if has_rkey else 'absent'}"
                    )
                    if not isinstance(group_eid, str) or not group_eid:
                        continue
                    if not isinstance(group_aid, str) or not group_aid:
                        continue
                    if not isinstance(sym_keys, list) or not sym_keys:
                        continue
                    first_key = sym_keys[0]
                    if not isinstance(first_key, dict):
                        continue
                    key_cipher = first_key.get("key")
                    if not isinstance(key_cipher, str) or not key_cipher:
                        continue
                    symmetric_key = _rsa_decrypt_base64(key_cipher, private_pem)
                    # rkey rotation key: APK's n73.m15464y() tries
                    # symmetricKeys[0].rkey.key first, then falls back
                    rkey_raw = first_key.get("rkey")
                    if isinstance(rkey_raw, str) and rkey_raw:
                        try:
                            rkey_payload = json.loads(rkey_raw)
                            rkey_cipher = rkey_payload.get("key")
                            if isinstance(rkey_cipher, str) and rkey_cipher:
                                print(
                                    "  Group has rkey rotation key; "
                                    "deriving key from rkey"
                                )
                                symmetric_key = _rsa_decrypt_base64(
                                    rkey_cipher, private_pem
                                )
                        except ValueError, TypeError, json.JSONDecodeError:
                            print("  rkey parsing failed; using direct key")
                    print(
                        f"  Derived symmetric key: "
                        f"{len(symmetric_key)} chars, "
                        f"prefix={symmetric_key[:8]}..."
                    )
                    return _ProvisioningResult(
                        symmetric_key=symmetric_key,
                        gid=gid,
                        eid=group_eid,
                        aid=group_aid,
                    )

            # Refresh identity on miss — login response includes groups
            async with session.post(
                f"{PROVISIONING_APP_API_BASE}{PROVISIONING_ENDPOINT_LOGIN}",
                json={
                    "assertion": {
                        "name": email,
                        "info": {"name": "circle"},
                        "publicKey": public_pem,
                        "appId": PROVISIONING_APP_ID,
                        "appSecret": PROVISIONING_APP_SECRET,
                        "signature": "",
                    }
                },
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status != 200:
                    continue
                refresh: dict[str, object] = await resp.json()
                token = refresh.get("access_token")
                if isinstance(token, str) and token:
                    current_access_token = token
                # Also check groups from the login response itself
                login_groups_raw = refresh.get("groups")
                if isinstance(login_groups_raw, list):
                    for group in login_groups_raw:
                        if not isinstance(group, dict):
                            continue
                        if group.get("_id") != gid:
                            continue
                        group_eid = group.get("eid")
                        group_aid = group.get("aid")
                        sym_keys = group.get("symmetricKeys")
                        has_rkey = bool(
                            sym_keys
                            and isinstance(sym_keys, list)
                            and len(sym_keys) > 0
                            and isinstance(sym_keys[0], dict)
                            and sym_keys[0].get("rkey")
                        )
                        print(
                            f"  Found matching group (login fallback): "
                            f"gid={gid}, "
                            f"symmetricKeys="
                            f"{len(sym_keys) if isinstance(sym_keys, list) else 0}, "
                            f"rkey={'present' if has_rkey else 'absent'}"
                        )
                        if not isinstance(group_eid, str) or not group_eid:
                            continue
                        if not isinstance(group_aid, str) or not group_aid:
                            continue
                        if not isinstance(sym_keys, list) or not sym_keys:
                            continue
                        first_key = sym_keys[0]
                        if not isinstance(first_key, dict):
                            continue
                        key_cipher = first_key.get("key")
                        if not isinstance(key_cipher, str) or not key_cipher:
                            continue
                        symmetric_key = _rsa_decrypt_base64(key_cipher, private_pem)
                        rkey_raw = first_key.get("rkey")
                        if isinstance(rkey_raw, str) and rkey_raw:
                            try:
                                rkey_payload = json.loads(rkey_raw)
                                rkey_cipher = rkey_payload.get("key")
                                if isinstance(rkey_cipher, str) and rkey_cipher:
                                    print(
                                        "  Group has rkey rotation key; "
                                        "deriving key from rkey"
                                    )
                                    symmetric_key = _rsa_decrypt_base64(
                                        rkey_cipher, private_pem
                                    )
                            except ValueError, TypeError, json.JSONDecodeError:
                                print("  rkey parsing failed; using direct key")
                        print(
                            f"  Derived symmetric key: "
                            f"{len(symmetric_key)} chars, "
                            f"prefix={symmetric_key[:8]}..."
                        )
                        return _ProvisioningResult(
                            symmetric_key=symmetric_key,
                            gid=gid,
                            eid=group_eid,
                            aid=group_aid,
                        )

        raise RuntimeError(
            "Cloud provisioning did not produce a visible group before "
            f"timing out after {PROVISIONING_GROUP_POLL_ATTEMPTS} attempts"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Start a remote Firewalla packet capture, wait for the target "
            "behavior to occur, download the pcap, and clean up"
        )
    )
    parser.add_argument(
        "--host",
        help="Router IP address or hostname. If omitted, you will be prompted.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Local directory where the downloaded pcap should be saved",
    )
    parser.add_argument(
        "--label",
        help=(
            "Optional short label to distinguish one capture, such as "
            "phone-success or home-assistant-attempt"
        ),
    )
    parser.add_argument(
        "--client-ip",
        help=(
            "Optional client IP address to restrict the remote capture to one "
            "client, such as the pairing phone or Home Assistant host"
        ),
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=DEFAULT_CONNECT_TIMEOUT,
        help="SSH connection timeout in seconds",
    )
    parser.add_argument(
        "--qr-json",
        help=(
            "Raw QR JSON string from the Firewalla app. "
            "On Windows, use --qr-file instead to avoid shell quoting issues."
        ),
    )
    parser.add_argument(
        "--qr-file",
        type=Path,
        help=(
            "Path to a file containing the raw QR JSON. "
            "Recommended over --qr-json on Windows to avoid quoting issues."
        ),
    )
    parser.add_argument(
        "--email",
        help=(
            "Email or label for the cloud provisioning identity (required when "
            "--qr-json or --qr-file is provided)"
        ),
    )
    parser.add_argument(
        "--decode",
        type=Path,
        help="Path to a pcap file to decode using a provisioning key file",
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        help="Path to a .key file (produced by --qr-json during capture)",
    )
    parser.add_argument(
        "--redacted-report",
        type=Path,
        help=(
            "Path to write a JSON report with credential values redacted. "
            "Use with --decode to share message structures without exposing keys."
        ),
    )
    return parser


def require_dependencies() -> None:
    """Raise a friendly error if required libraries are not installed."""
    missing: list[str] = []
    if paramiko is None:
        missing.append("paramiko")
    if SCPClient is None:
        missing.append("scp")
    if missing:
        package_list = ", ".join(missing)
        raise RuntimeError(
            "Missing required Python packages: "
            f"{package_list}. Install them with: pip install {package_list}"
        )


def prompt_host(provided_host: str | None) -> str:
    """Return the provided or prompted router IP address."""
    if provided_host and provided_host.strip():
        return provided_host.strip()

    while True:
        host = input("Router IP address or hostname: ").strip()
        if host:
            return host
        print("A router IP address or hostname is required.")


def normalize_label(label: str | None) -> str | None:
    """Return a filesystem-safe label fragment or None."""
    if label is None:
        return None

    normalized = "".join(
        char.lower() if char.isalnum() else "-" for char in label.strip()
    ).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized or None


def build_local_capture_path(output_dir: Path, label: str | None) -> Path:
    """Return one timestamped local output path for the downloaded pcap."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"_{label}" if label else ""
    return output_dir / f"firewalla_capture_{timestamp}{suffix}.pcap"


def build_capture_filter(client_ip: str | None) -> str:
    """Return the tcpdump filter for the requested capture scope."""
    if not client_ip:
        return DEFAULT_CAPTURE_FILTER

    validated_ip = ipaddress.ip_address(client_ip)
    return f"{DEFAULT_CAPTURE_FILTER} and host {validated_ip}"


def format_ts(ts: float) -> str:
    """Render one timestamp in a stable UTC format."""
    return datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z")


def reassemble(segments: list[Segment]) -> tuple[bytes, list[tuple[int, float]]]:
    """Reassemble ordered TCP payload segments into one byte stream."""
    ordered = sorted(segments, key=lambda item: (item.seq, item.ts, len(item.data)))
    output = bytearray()
    offsets: list[tuple[int, float]] = []
    next_seq: int | None = None
    for segment in ordered:
        if next_seq is None:
            offsets.append((0, segment.ts))
            output.extend(segment.data)
            next_seq = segment.seq + len(segment.data)
            continue

        if segment.seq >= next_seq:
            gap = segment.seq - next_seq
            if gap:
                output.extend(b" " * gap)
            offsets.append((len(output), segment.ts))
            output.extend(segment.data)
            next_seq = segment.seq + len(segment.data)
            continue

        overlap = next_seq - segment.seq
        if overlap < len(segment.data):
            offsets.append((len(output), segment.ts))
            output.extend(segment.data[overlap:])
            next_seq += len(segment.data) - overlap

    return bytes(output), offsets


def ts_for_offset(offsets: list[tuple[int, float]], position: int) -> float | None:
    """Return the last packet timestamp known at one stream offset."""
    current: float | None = None
    for offset, ts in offsets:
        if offset > position:
            break
        current = ts
    return current


def parse_http_messages(
    blob: bytes,
    offsets: list[tuple[int, float]],
    *,
    request: bool,
) -> list[HttpMessage]:
    """Split a byte stream into HTTP messages with timestamps and headers."""
    request_markers = (b"POST ", b"GET ")
    response_marker = b"HTTP/1.1 "
    index = 0
    parsed: list[HttpMessage] = []
    while True:
        if request:
            starts = [blob.find(marker, index) for marker in request_markers]
            starts = [start for start in starts if start >= 0]
            start = min(starts) if starts else -1
        else:
            start = blob.find(response_marker, index)
        if start < 0:
            break

        header_end = blob.find(b"\r\n\r\n", start)
        if header_end < 0:
            break

        header = blob[start:header_end].decode("latin1", errors="ignore")
        first_line, *rest = header.split("\r\n")
        headers: dict[str, str] = {}
        content_length: int | None = None
        for line in rest:
            name, _, value = line.partition(":")
            header_name = name.lower()
            header_value = value.strip()
            headers[header_name] = header_value
            if header_name == "content-length":
                try:
                    content_length = int(header_value)
                except ValueError:
                    content_length = 0

        if content_length is None:
            if request:
                content_length = 0
            else:
                transfer_encoding = headers.get("transfer-encoding", "")
                content_type = headers.get("content-type", "")
                if transfer_encoding.lower() == "chunked" or content_type.startswith(
                    "text/event-stream"
                ):
                    next_start = blob.find(response_marker, header_end + 4)
                    if next_start < 0:
                        content_length = len(blob) - (header_end + 4)
                    else:
                        content_length = next_start - (header_end + 4)
                else:
                    content_length = 0

        body_start = header_end + 4
        body_end = body_start + content_length
        body = blob[body_start:body_end]
        if len(body) < content_length:
            break

        parsed.append(
            HttpMessage(
                ts=ts_for_offset(offsets, start),
                first_line=first_line,
                headers=headers,
                content_length=len(body),
                body=body,
            )
        )
        index = body_end

    return parsed


def classify_message(message: HttpMessage, *, request: bool) -> str:
    """Return one stable safe-report class label."""
    if request:
        if message.first_line.startswith("POST "):
            return "post_request"
        if message.first_line.startswith("GET "):
            return "get_request"
        return "request_unknown"

    content_type = message.headers.get("content-type", "")
    if content_type.startswith("text/event-stream"):
        return "event_stream_response"
    if content_type.startswith("application/json"):
        return "json_response"
    return "response_unknown"


def redact_request_line(first_line: str) -> str:
    """Redact the Firewalla message path identifier from one request line."""
    return MESSAGE_PATH_RE.sub(r"\1{gid}", first_line)


def extract_status_code(first_line: str) -> str | None:
    """Return the HTTP status code from one response line when present."""
    parts = first_line.split()
    if len(parts) >= 2 and parts[0].startswith("HTTP/"):
        return parts[1]
    return None


def determine_connection_pattern(
    *,
    distinct_request_connections: int,
    request_count: int,
) -> str:
    """Return a compact description of client connection reuse."""
    if request_count == 0:
        return "no_http_requests"
    if distinct_request_connections == 1:
        return "persistent_request_connection"
    if distinct_request_connections >= request_count:
        return "separate_request_connections"
    return "mixed_request_connections"


def flow_peer_key(flow: tuple[str, int, str, int], *, request: bool) -> tuple[str, int]:
    """Return a stable client endpoint key for one parsed flow."""
    if request:
        return (flow[0], flow[1])
    return (flow[2], flow[3])


def flow_direction_label(is_request: bool, peer_index: int) -> str:
    """Return a stable redacted direction label."""
    peer = f"CLIENT_{peer_index}"
    if is_request:
        return f"{peer} -> BOX"
    return f"BOX -> {peer}"


def build_safe_report(
    capture_path: Path,
    *,
    capture_label: str | None,
    client_ip: str | None,
    capture_filter: str,
) -> tuple[dict[str, object], list[SafeReportEvent]] | None:
    """Build one shareable safe report from a local pcap."""
    if IP is None or TCP is None or rdpcap is None:
        return None

    flows: dict[tuple[str, int, str, int], list[Segment]] = defaultdict(list)
    events: list[SafeReportEvent] = []
    peer_indices: dict[str, int] = {}
    request_times: dict[tuple[str, int], list[float]] = defaultdict(list)
    response_index_by_peer: dict[tuple[str, int], int] = defaultdict(int)
    distinct_request_connections: set[tuple[str, int]] = set()

    for packet in rdpcap(str(capture_path)):
        if IP not in packet or TCP not in packet:
            continue
        ip = packet[IP]
        tcp = packet[TCP]
        if tcp.sport != SERVER_PORT and tcp.dport != SERVER_PORT:
            continue

        peer_ip = ip.src if tcp.sport != SERVER_PORT else ip.dst
        if client_ip and peer_ip != client_ip:
            continue
        peer_index = peer_indices.setdefault(peer_ip, len(peer_indices) + 1)
        direction = flow_direction_label(tcp.dport == SERVER_PORT, peer_index)

        flags = int(tcp.flags)
        if flags & 0x04:
            events.append(
                SafeReportEvent(
                    timestamp_utc=format_ts(float(packet.time)),
                    direction=direction,
                    kind="tcp_event",
                    message_class="tcp_reset",
                    first_line="TCP RST observed",
                )
            )
        elif flags & 0x01:
            events.append(
                SafeReportEvent(
                    timestamp_utc=format_ts(float(packet.time)),
                    direction=direction,
                    kind="tcp_event",
                    message_class="tcp_finish",
                    first_line="TCP FIN observed",
                )
            )

        payload = bytes(tcp.payload)
        if not payload:
            continue
        flows[(ip.src, tcp.sport, ip.dst, tcp.dport)].append(
            Segment(seq=int(tcp.seq), data=payload, ts=float(packet.time))
        )

    parsed_flows: list[tuple[tuple[str, int, str, int], bool, list[HttpMessage]]] = []
    for flow, segments in sorted(flows.items()):
        is_request = flow[3] == SERVER_PORT
        blob, offsets = reassemble(segments)
        messages = parse_http_messages(blob, offsets, request=is_request)
        if not messages:
            continue
        parsed_flows.append((flow, is_request, messages))
        if is_request:
            distinct_request_connections.add((flow[0], flow[1]))
            peer_key = flow_peer_key(flow, request=True)
            for message in messages:
                if message.ts is not None:
                    request_times[peer_key].append(message.ts)

    for flow, is_request, messages in parsed_flows:
        peer_ip = flow[0] if is_request else flow[2]
        direction = flow_direction_label(is_request, peer_indices[peer_ip])
        peer_key = flow_peer_key(flow, request=is_request)
        for message in messages:
            if message.ts is None:
                continue

            latency_seconds: float | None = None
            if not is_request:
                request_index = response_index_by_peer[peer_key]
                if request_index < len(request_times[peer_key]):
                    latency_seconds = round(
                        message.ts - request_times[peer_key][request_index],
                        3,
                    )
                    response_index_by_peer[peer_key] += 1

            events.append(
                SafeReportEvent(
                    timestamp_utc=format_ts(message.ts),
                    direction=direction,
                    kind="http_request" if is_request else "http_response",
                    message_class=classify_message(message, request=is_request),
                    first_line=(
                        redact_request_line(message.first_line)
                        if is_request
                        else message.first_line
                    ),
                    content_length=message.content_length,
                    user_agent=message.headers.get("user-agent"),
                    content_type=message.headers.get("content-type"),
                    latency_seconds=latency_seconds,
                    status_code=(
                        None if is_request else extract_status_code(message.first_line)
                    ),
                )
            )

    sorted_events = sorted(events, key=lambda item: item.timestamp_utc)
    http_events = [event for event in sorted_events if event.kind.startswith("http_")]
    http_responses = [
        event.status_code
        for event in http_events
        if event.kind == "http_response" and event.status_code is not None
    ]
    http_request_events = [
        event for event in http_events if event.kind == "http_request"
    ]
    http_response_events = [
        event for event in http_events if event.kind == "http_response"
    ]

    summary: dict[str, object] = {
        "report_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "capture_file_name": capture_path.name,
        "capture_label": capture_label,
        "capture_filter": capture_filter,
        "client_ip_filter_applied": client_ip is not None,
        "distinct_client_connection_count": len(distinct_request_connections),
        "connection_pattern": determine_connection_pattern(
            distinct_request_connections=len(distinct_request_connections),
            request_count=len(http_request_events),
        ),
        "http_request_count": len(http_request_events),
        "http_response_count": len(http_response_events),
        "http_request_method_sequence": [
            event.first_line.split()[0]
            for event in http_request_events
            if event.first_line.split()
        ],
        "http_response_status_sequence": http_responses,
        "http_request_class_counts": dict(
            Counter(event.message_class for event in http_request_events)
        ),
        "http_response_class_counts": dict(
            Counter(event.message_class for event in http_response_events)
        ),
        "http_response_status_counts": dict(Counter(http_responses)),
        "http_412_count": sum(status == "412" for status in http_responses),
        "live_stream_observed": any(
            event.message_class in {"get_request", "event_stream_response"}
            for event in http_events
        ),
        "tcp_event_counts": dict(
            Counter(
                event.first_line for event in sorted_events if event.kind == "tcp_event"
            )
        ),
        "observed_user_agents": sorted(
            {
                event.user_agent
                for event in http_request_events
                if event.user_agent is not None
            }
        ),
        "notes": [
            (
                "This safe report contains only cleartext HTTP metadata and "
                "TCP lifecycle events."
            ),
            "It does not decrypt payloads and does not include the raw pcap.",
            (
                "Repeated HTTP 412 responses and TCP disconnect patterns are "
                "preserved so pairing acceptance failures can be compared with "
                "Home Assistant logs."
            ),
            (
                "Cleartext headers such as User-Agent may still identify the "
                "app family or version used during pairing."
            ),
        ],
    }
    return summary, sorted_events


def write_safe_report(
    capture_path: Path,
    *,
    summary: dict[str, object],
    events: list[SafeReportEvent],
) -> Path:
    """Write one local safe report zip and return its path."""
    report_dir = capture_path.parent / f"{capture_path.stem}_safe_report"
    report_dir.mkdir(parents=True, exist_ok=False)

    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (report_dir / "events.json").write_text(
        json.dumps([asdict(event) for event in events], indent=2, sort_keys=True),
        encoding="utf-8",
    )

    transcript_lines = [
        "Windows Firewalla packet capture safe report",
        "",
        f"Capture file: {capture_path.name}",
    ]
    if summary.get("capture_label"):
        transcript_lines.append(f"Capture label: {summary['capture_label']}")
    connection_count = summary["distinct_client_connection_count"]
    connection_pattern = summary["connection_pattern"]
    request_count = summary["http_request_count"]
    response_count = summary["http_response_count"]
    status_counts = summary["http_response_status_counts"]
    status_sequence = summary["http_response_status_sequence"]
    request_sequence = summary["http_request_method_sequence"]
    http_412_count = summary["http_412_count"]
    live_stream_observed = summary["live_stream_observed"]
    transcript_lines.extend(
        [
            f"Distinct client connections: {connection_count}",
            f"Connection pattern: {connection_pattern}",
            f"HTTP requests: {request_count}",
            f"HTTP responses: {response_count}",
            f"HTTP response status counts: {status_counts}",
            f"HTTP response status sequence: {status_sequence}",
            f"HTTP request method sequence: {request_sequence}",
            f"HTTP 412 responses: {http_412_count}",
            f"Live stream observed: {live_stream_observed}",
            "",
            "Observed user agents:",
        ]
    )
    user_agents = summary.get("observed_user_agents", [])
    if isinstance(user_agents, list) and user_agents:
        transcript_lines.extend(f"- {user_agent}" for user_agent in user_agents)
    else:
        transcript_lines.append("- none")
    transcript_lines.extend(["", "HTTP and TCP events:"])
    for event in events:
        parts = [
            event.timestamp_utc,
            event.direction,
            event.kind,
            event.message_class,
            event.first_line,
        ]
        if event.content_length is not None:
            parts.append(f"content_length={event.content_length}")
        if event.user_agent:
            parts.append(f"user_agent={event.user_agent}")
        if event.content_type:
            parts.append(f"content_type={event.content_type}")
        if event.latency_seconds is not None:
            parts.append(f"latency_seconds={event.latency_seconds}")
        transcript_lines.append(" | ".join(parts))

    (report_dir / "transcript.txt").write_text(
        "\n".join(transcript_lines) + "\n",
        encoding="utf-8",
    )
    (report_dir / "README.txt").write_text(
        "This safe report archive contains only cleartext packet metadata, such as "
        "HTTP request lines, response status lines, selected headers, content "
        "lengths, and TCP disconnect events. The raw pcap stays local and is not "
        "included in this zip.\n",
        encoding="utf-8",
    )

    bundle_path = capture_path.parent / f"{capture_path.stem}_safe_report.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(report_dir.iterdir()):
            bundle.write(path, arcname=path.name)
    return bundle_path


def connect_ssh(host: str, password: str, timeout: float) -> SSHClient:
    """Open and return one SSH connection to the remote router."""
    assert paramiko is not None
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=SSH_PORT,
        username=SSH_USER,
        password=password,
        timeout=timeout,
        auth_timeout=timeout,
        banner_timeout=timeout,
    )
    return client


def run_remote_command(client: SSHClient, command: str) -> tuple[int, str, str]:
    """Run one remote shell command and return status, stdout, and stderr."""
    stdin, stdout, stderr = client.exec_command(command)
    stdin.close()
    exit_status = stdout.channel.recv_exit_status()
    return (
        exit_status,
        stdout.read().decode("utf-8", errors="ignore"),
        stderr.read().decode("utf-8", errors="ignore"),
    )


def start_remote_capture(client: SSHClient, capture_filter: str) -> None:
    """Start tcpdump on the remote router and persist its PID."""
    command = (
        "sudo sh -lc "
        f"'rm -f {REMOTE_PCAP_PATH} {REMOTE_PID_PATH}; "
        f"tcpdump -U -n -s 0 -i any -w {REMOTE_PCAP_PATH} {capture_filter} "
        ">/dev/null 2>&1 & "
        f"echo $! > {REMOTE_PID_PATH}'"
    )
    exit_status, _stdout, stderr = run_remote_command(client, command)
    if exit_status != 0:
        raise RuntimeError(
            "Failed to start remote packet capture"
            + (f": {stderr.strip()}" if stderr.strip() else "")
        )

    time.sleep(1.0)
    verify_status, stdout, stderr = run_remote_command(
        client,
        f"sh -lc 'test -s {REMOTE_PID_PATH} && cat {REMOTE_PID_PATH}'",
    )
    if verify_status != 0 or not stdout.strip():
        detail = stderr.strip() or stdout.strip()
        raise RuntimeError(
            "Remote packet capture did not report a running PID"
            + (f": {detail}" if detail else "")
        )


def stop_remote_capture(client: SSHClient) -> None:
    """Stop tcpdump on the remote router if it is still running."""
    command = (
        "sudo sh -lc "
        f"'if [ -f {REMOTE_PID_PATH} ]; then "
        f"kill $(cat {REMOTE_PID_PATH}) >/dev/null 2>&1 || true; "
        f"wait $(cat {REMOTE_PID_PATH}) >/dev/null 2>&1 || true; "
        f"rm -f {REMOTE_PID_PATH}; "
        f'else pkill -f "tcpdump -i any -w {REMOTE_PCAP_PATH}" '
        ">/dev/null 2>&1 || true; "
        "fi'"
    )
    run_remote_command(client, command)


def cleanup_remote_capture(client: SSHClient) -> None:
    """Delete temporary remote capture files."""
    run_remote_command(
        client,
        f"sudo rm -f {REMOTE_PCAP_PATH} {REMOTE_PID_PATH}",
    )


def download_capture(client: SSHClient, local_path: Path) -> None:
    """Download the remote pcap to the requested local path."""
    assert SCPClient is not None
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport is no longer available for SCP download")

    with SCPClient(transport) as scp:
        scp.get(REMOTE_PCAP_PATH, str(local_path))


_REDACT_LABEL: Final = "<redacted>"


def _redact_credentials(value: object) -> object:
    """Replace credential values with a redacted label, keeping structure intact."""
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for k, v in value.items():
            key_lower = k.lower()
            if key_lower in (
                "eid",
                "aid",
                "gid",
                "symmetric_key",
                "accesstoken",
                "access_token",
                "token",
                "password",
                "secret",
                "key",
                "publickey",
                "privatekey",
                "license",
                "seed",
                "ek",
                "jwt",
                "jwtoken",
                "ddnstoken",
                "btmac",
                "cpuid",
                "rkey",
            ) or (isinstance(v, str) and len(v) == 36 and v.count("-") == 4):
                redacted[k] = _REDACT_LABEL
            else:
                redacted[k] = _redact_credentials(v)
        return redacted
    if isinstance(value, list):
        return [_redact_credentials(item) for item in value]
    return value


def _decode_capture(
    pcap_path: Path, key_path: Path, redacted_report: Path | None = None
) -> int:
    """Decode a captured pcap using the sidecar key file and print message contents."""
    if not pcap_path.is_file():
        print(f"Error: pcap file not found: {pcap_path}", file=sys.stderr)
        return 1
    if not key_path.is_file():
        print(f"Error: key file not found: {key_path}", file=sys.stderr)
        return 1
    if IP is None or TCP is None or rdpcap is None:
        print("Error: scapy is required for decoding", file=sys.stderr)
        return 1

    key_data = json.loads(key_path.read_text(encoding="utf-8"))
    symmetric_key = key_data.get("symmetric_key")
    if not isinstance(symmetric_key, str) or not symmetric_key:
        print("Error: key file does not contain a valid symmetric_key", file=sys.stderr)
        return 1

    decoded_messages: list[dict[str, object]] = []
    flows_data: dict[tuple, list[Segment]] = defaultdict(list)
    for packet in rdpcap(str(pcap_path)):
        if IP not in packet or TCP not in packet:
            continue
        ip = packet[IP]
        tcp = packet[TCP]
        if tcp.sport != SERVER_PORT and tcp.dport != SERVER_PORT:
            continue
        payload = bytes(tcp.payload)
        if not payload:
            continue
        flows_data[(ip.src, tcp.sport, ip.dst, tcp.dport)].append(
            Segment(seq=int(tcp.seq), data=payload, ts=float(packet.time))
        )

    for flow, segments in sorted(flows_data.items()):
        is_request = flow[3] == SERVER_PORT
        direction = "REQUEST" if is_request else "RESPONSE"
        blob, offsets = reassemble(segments)
        messages = parse_http_messages(blob, offsets, request=is_request)
        for msg in messages:
            entry: dict[str, object] = {
                "direction": direction,
                "first_line": msg.first_line,
                "content_length": msg.content_length,
            }
            if msg.body:
                try:
                    body = json.loads(msg.body.decode("utf-8", errors="ignore"))
                except json.JSONDecodeError:
                    entry["raw_body"] = msg.body[:200].decode(
                        "latin1", errors="replace"
                    )
                    decoded_messages.append(entry)
                    continue
                encrypted = body.get("message") if isinstance(body, dict) else None
                if isinstance(encrypted, str):
                    try:
                        decrypted = _aes256_cbc_decrypt_from_base64(
                            encrypted, symmetric_key
                        )
                        parsed = json.loads(decrypted)
                        entry["decrypted"] = parsed
                    except (
                        ValueError,
                        UnicodeDecodeError,
                        json.JSONDecodeError,
                    ) as exc:
                        entry["decrypt_error"] = str(exc)
                    # Preserve outer envelope keys (everything except the
                    # encrypted message blob) so users can inspect fields like
                    # mtype, timestamp, rkeyts, etc.
                    outer = {k: v for k, v in body.items() if k != "message"}
                    if outer:
                        entry["outer_envelope"] = outer
                else:
                    entry["body"] = body
            decoded_messages.append(entry)

    # Print full output
    for entry in decoded_messages:
        print(f"\n{'=' * 60}")
        print(f"[{entry['direction']}] {entry['first_line']}")
        print(f"  content_length: {entry.get('content_length', '')}")
        if outer := entry.get("outer_envelope"):
            print(f"  outer_envelope: {json.dumps(outer)}")
        if "decrypted" in entry:
            print(f"  decrypted: {json.dumps(entry['decrypted'], indent=2)}")
        elif "body" in entry:
            print(f"  body: {json.dumps(entry['body'], indent=2)}")
        elif "raw_body" in entry:
            print(f"  body (raw): {entry['raw_body']}")

    # Write redacted report if requested
    if redacted_report:
        redacted_entries = _redact_credentials(decoded_messages)
        assert isinstance(redacted_entries, list)
        redacted_report.write_text(
            json.dumps(redacted_entries, indent=2),
            encoding="utf-8",
        )
        print(f"\nRedacted report saved to: {redacted_report}")
        print(
            "This report can be shared — credential values have been replaced "
            "with <redacted>."
        )
    return 0


def main() -> int:
    """Run the Windows Firewalla packet capture workflow."""
    parser = build_parser()
    args = parser.parse_args()

    # Decode mode: skip capture and just decode an existing pcap
    if args.decode:
        if not args.key_file:
            print(
                "Error: --key-file is required when --decode is provided",
                file=sys.stderr,
            )
            return 1
        return _decode_capture(
            args.decode, args.key_file, redacted_report=args.redacted_report
        )

    try:
        require_dependencies()
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    assert paramiko is not None
    assert SCPException is not None

    # Optional: run cloud provisioning to capture the symmetric key
    key_path: Path | None = None
    qr_raw: str | None = args.qr_json
    if qr_raw is None and args.qr_file is not None:
        try:
            qr_raw = args.qr_file.read_text(encoding="utf-8").strip()
        except OSError as err:
            print(f"Error: could not read QR file: {err}", file=sys.stderr)
            return 1
    if qr_raw is not None:
        if not args.email:
            print(
                "Error: --email is required when --qr-json or --qr-file is provided",
                file=sys.stderr,
            )
            return 1
        if aiohttp is None or not CRYPTOGRAPHY_AVAILABLE:
            print(
                "Error: aiohttp and cryptography are required for provisioning. "
                "Install them with: pip install aiohttp cryptography",
                file=sys.stderr,
            )
            return 1
        try:
            qr_data = _ProvisioningQrData.from_raw_json(qr_raw)
            private_pem, public_pem = _generate_firewalla_keys()
            print("Starting cloud provisioning to capture the symmetric key...")
            result = asyncio.run(
                _provision_symmetric_key(qr_data, private_pem, public_pem, args.email)
            )
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            key_path = Path(args.output_dir) / f"provisioning_key_{ts}.key"
            key_path.write_text(
                json.dumps(
                    {
                        "symmetric_key": result.symmetric_key,
                        "gid": result.gid,
                        "eid": result.eid,
                        "aid": result.aid,
                        "provisioned_at_utc": (
                            datetime.now(UTC).isoformat().replace("+00:00", "Z")
                        ),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"Symmetric key captured and saved to: {key_path}")
            print(
                "This key can decrypt the pcap from this session. "
                "Keep it private — do not share publicly or include in safe reports."
            )
        except (ValueError, RuntimeError, OSError, aiohttp.ClientError) as err:
            print(f"Cloud provisioning failed: {err}", file=sys.stderr)
            return 1

    host = prompt_host(args.host)
    password = getpass.getpass(f"SSH password for {SSH_USER}@{host}: ")
    label = normalize_label(args.label)
    local_capture_path = build_local_capture_path(args.output_dir, label)

    try:
        capture_filter = build_capture_filter(args.client_ip)
    except ValueError as err:
        print(f"Invalid --client-ip value: {err}", file=sys.stderr)
        return 1

    client: SSHClient | None = None
    capture_started = False

    try:
        client = connect_ssh(host, password, args.connect_timeout)
        start_remote_capture(client, capture_filter)
        capture_started = True

        print()
        print(f"Remote capture filter: {capture_filter}")
        print(
            "Capture started. Reproduce the behavior you want to capture now. "
            "Press [ENTER] when you are finished or if the issue occurs."
        )
        input()

        stop_remote_capture(client)
        download_capture(client, local_capture_path)
        cleanup_remote_capture(client)

        report_path: Path | None = None
        safe_report = build_safe_report(
            local_capture_path,
            capture_label=label,
            client_ip=args.client_ip,
            capture_filter=capture_filter,
        )
        if safe_report is not None:
            summary, events = safe_report
            report_path = write_safe_report(
                local_capture_path,
                summary=summary,
                events=events,
            )

        print()
        print(f"Success. Capture saved to: {local_capture_path}")
        if key_path is not None:
            print(f"Provisioning key saved to: {key_path}")
            print(
                "Keep the key file private — it can decrypt this pcap. "
                "Only share alongside the raw pcap privately."
            )
        if report_path is not None:
            print(f"Safe report saved to: {report_path}")
            print("Share the safe report first and keep the raw pcap private.")
        else:
            print(
                "Safe report generation was skipped because Scapy is not available. "
                "Keep the raw pcap private unless asked to share it privately."
            )
        return 0
    except KeyboardInterrupt:
        print()
        print("Interrupted. Attempting remote cleanup before exiting.", file=sys.stderr)
        return 130
    except paramiko.AuthenticationException as err:
        print(f"Authentication failed: {err}", file=sys.stderr)
        return 1
    except (paramiko.SSHException, OSError, TimeoutError) as err:
        print(f"Connection or SSH error: {err}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, SCPException) as err:
        print(f"Capture failed: {err}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            if capture_started:
                with suppress(Exception):
                    stop_remote_capture(client)
                with suppress(Exception):
                    cleanup_remote_capture(client)
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
