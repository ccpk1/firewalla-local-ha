"""Cloud provisioning helpers for the Firewalla Local API boundary."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import ClientError, ClientSession

from ..const import (
    APP_API_BASE,
    APP_GROUP_ENDPOINT_CANDIDATES,
    DEFAULT_GROUP_POLL_ATTEMPTS,
    DEFAULT_GROUP_POLL_INTERVAL,
    DEFAULT_PAIRING_DEVICE_NAME,
    FIREWALLA_APP_ID,
    FIREWALLA_APP_SECRET,
)
from .crypto import (
    aes256_cbc_decrypt_from_base64,
    derive_qr_bootstrap_key,
    rsa_decrypt_base64,
)
from .exceptions import (
    FirewallaAuthError,
    FirewallaConnectionError,
    FirewallaProtocolError,
    FirewallaValidationError,
)
from .models import (
    ETPIdentity,
    FirewallaProvisionedCredentials,
    GeneratedKeys,
    GroupFetchResult,
    PairingCode,
    PairingQrData,
)


def load_qr_json(raw_json: str) -> PairingQrData:
    """Parse and validate the Firewalla QR JSON."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as err:
        raise FirewallaValidationError("QR JSON is not valid JSON") from err

    if not isinstance(payload, dict):
        raise FirewallaValidationError("QR JSON root must be an object")

    return PairingQrData.from_mapping(payload)


def _json_dumps_compact(value: Any) -> str:
    """Serialize JSON using the compact separators seen in upstream tooling."""
    return json.dumps(value, separators=(",", ":"))


def decrypt_pairing_code(qr_data: PairingQrData) -> PairingCode:
    """Decrypt the QR `ek` field into the pairing object used by the cloud link."""
    plaintext = aes256_cbc_decrypt_from_base64(
        qr_data.ek,
        derive_qr_bootstrap_key(qr_data.license, qr_data.seed),
    )

    try:
        parsed = json.loads(plaintext)
    except json.JSONDecodeError:
        return PairingCode(
            rendezvous_id=plaintext,
            evalue={"license": qr_data.license},
        )

    if not isinstance(parsed, dict):
        raise FirewallaProtocolError("QR pairing payload did not decode to an object")

    rendezvous_id = parsed.get("r") or parsed.get("rid")
    evalue = parsed.get("evalue")
    if isinstance(rendezvous_id, str) and isinstance(evalue, dict):
        return PairingCode(rendezvous_id=rendezvous_id, evalue=evalue)

    raise FirewallaProtocolError("QR pairing payload did not include rendezvous data")


def build_login_payload(assertion_name: str, public_pem: str) -> dict[str, Any]:
    """Build the `login/eptoken` request payload."""
    return {
        "assertion": {
            "name": assertion_name,
            "info": {"name": "circle"},
            "publicKey": public_pem,
            "appId": FIREWALLA_APP_ID,
            "appSecret": FIREWALLA_APP_SECRET,
            "signature": "",
        }
    }


def build_cloud_link_payload(pairing_code: PairingCode) -> dict[str, Any]:
    """Build the authenticated rendezvous payload for the cloud link step."""
    return {
        "rid": pairing_code.rendezvous_id,
        "evalue": _json_dumps_compact(pairing_code.evalue),
    }


async def post_json(
    session: ClientSession,
    url: str,
    payload: dict[str, Any],
    *,
    access_token: str | None = None,
) -> tuple[int, str]:
    """Post JSON and return the raw HTTP status and text body."""
    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    try:
        async with session.post(url, json=payload, headers=headers) as response:
            return response.status, await response.text()
    except ClientError as err:
        raise FirewallaConnectionError(
            f"Could not reach Firewalla cloud API: {err}"
        ) from err


async def get_json(
    session: ClientSession,
    url: str,
    *,
    access_token: str,
) -> tuple[int, str]:
    """Issue an authenticated GET and return the raw HTTP status and text body."""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with session.get(url, headers=headers) as response:
            return response.status, await response.text()
    except ClientError as err:
        raise FirewallaConnectionError(
            f"Could not reach Firewalla cloud API: {err}"
        ) from err


def parse_login_identity(response_text: str) -> ETPIdentity:
    """Parse the cloud login response into a strongly typed identity."""
    payload = json.loads(response_text)
    if not isinstance(payload, dict):
        raise FirewallaProtocolError("login/eptoken response was not a JSON object")

    access_token = payload.get("access_token")
    eid = payload.get("eid")
    aid = payload.get("aid")
    groups = payload.get("groups", [])

    if not isinstance(access_token, str) or not access_token:
        raise FirewallaProtocolError(
            "login/eptoken response did not include access_token"
        )
    if not isinstance(eid, str) or not eid:
        raise FirewallaProtocolError("login/eptoken response did not include eid")
    if not isinstance(aid, str) or not aid:
        raise FirewallaProtocolError("login/eptoken response did not include aid")
    if not isinstance(groups, list):
        raise FirewallaProtocolError(
            "login/eptoken response did not include a groups list"
        )

    return ETPIdentity(access_token=access_token, eid=eid, aid=aid, groups=groups)


async def login_eptoken(
    session: ClientSession,
    *,
    assertion_name: str,
    public_pem: str,
) -> ETPIdentity:
    """Create or refresh the ETP identity used for the cloud link step."""
    status, response_text = await post_json(
        session,
        f"{APP_API_BASE}/login/eptoken",
        build_login_payload(assertion_name, public_pem),
    )
    if status == 401:
        raise FirewallaAuthError("login/eptoken returned unauthorized")
    if status != 200:
        raise FirewallaProtocolError(
            f"login/eptoken failed with HTTP {status}: {response_text}"
        )
    return parse_login_identity(response_text)


async def link_group_cloud(
    session: ClientSession,
    *,
    access_token: str,
    pairing_code: PairingCode,
) -> None:
    """Execute the authenticated cloud rendezvous step for additional pairing."""
    status, response_text = await post_json(
        session,
        f"{APP_API_BASE}/ept/rendezvous/me",
        build_cloud_link_payload(pairing_code),
        access_token=access_token,
    )
    if status == 401:
        raise FirewallaAuthError("Cloud rendezvous returned unauthorized")
    if status != 200:
        raise FirewallaProtocolError(
            f"Cloud rendezvous failed with HTTP {status}: {response_text}"
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
    session: ClientSession,
    *,
    identity: ETPIdentity,
    assertion_name: str,
    public_pem: str,
) -> tuple[GroupFetchResult, ETPIdentity]:
    """Fetch the linked groups from the strongest known cloud sources."""
    for endpoint in APP_GROUP_ENDPOINT_CANDIDATES:
        status, response_text = await get_json(
            session,
            f"{APP_API_BASE}{endpoint}",
            access_token=identity.access_token,
        )
        if status == 401:
            break
        if status != 200:
            continue

        payload = json.loads(response_text)
        if groups := extract_groups(payload):
            return (
                GroupFetchResult(source=endpoint, status=status, groups=groups),
                identity,
            )

    refreshed_identity = await login_eptoken(
        session,
        assertion_name=assertion_name,
        public_pem=public_pem,
    )
    return (
        GroupFetchResult(
            source="/login/eptoken",
            status=200,
            groups=refreshed_identity.groups,
        ),
        refreshed_identity,
    )


def extract_group_credentials(
    *,
    groups: list[dict[str, Any]],
    qr_data: PairingQrData,
    host: str,
    private_pem: str,
) -> FirewallaProvisionedCredentials | None:
    """Extract the durable local runtime credentials from a linked group list."""
    matching_group = next(
        (group for group in groups if group.get("_id") == qr_data.gid),
        None,
    )
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
    return FirewallaProvisionedCredentials(
        license=qr_data.license,
        host=host,
        gid=qr_data.gid,
        eid=eid,
        aid=aid,
        symmetric_key=symmetric_key_plain,
        box_name=qr_data.device_name,
    )


async def async_provision_firewalla_credentials(
    session: ClientSession,
    *,
    qr_data: PairingQrData,
    host: str,
    keys: GeneratedKeys,
    assertion_name: str = DEFAULT_PAIRING_DEVICE_NAME,
    attempts: int = DEFAULT_GROUP_POLL_ATTEMPTS,
    interval: float = DEFAULT_GROUP_POLL_INTERVAL,
) -> FirewallaProvisionedCredentials:
    """Run the approved cloud provisioning flow and return durable local credentials."""
    identity = await login_eptoken(
        session,
        assertion_name=assertion_name,
        public_pem=keys.public_pem,
    )
    pairing_code = decrypt_pairing_code(qr_data)
    await link_group_cloud(
        session,
        access_token=identity.access_token,
        pairing_code=pairing_code,
    )

    current_identity = identity
    for attempt in range(attempts):
        if attempt:
            await asyncio.sleep(interval)

        fetch_result, current_identity = await fetch_groups(
            session,
            identity=current_identity,
            assertion_name=assertion_name,
            public_pem=keys.public_pem,
        )
        credentials = extract_group_credentials(
            groups=fetch_result.groups,
            qr_data=qr_data,
            host=host,
            private_pem=keys.private_pem,
        )
        if credentials is not None:
            return credentials

    raise FirewallaProtocolError(
        "Cloud link did not produce a visible group before polling timed out"
    )
