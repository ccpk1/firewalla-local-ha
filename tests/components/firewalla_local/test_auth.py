"""Tests for Firewalla Local auth helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientSession

from custom_components.firewalla_local.api.auth import (
    async_provision_firewalla_credentials,
    extract_group_credentials,
    extract_groups,
    load_qr_json,
    parse_login_identity,
)
from custom_components.firewalla_local.api.exceptions import (
    FirewallaProtocolError,
    FirewallaValidationError,
)
from custom_components.firewalla_local.api.models import (
    ETPIdentity,
    FirewallaProvisionedCredentials,
    GeneratedKeys,
    GroupFetchResult,
    PairingCode,
)
from custom_components.firewalla_local.const import DEFAULT_GROUP_POLL_ATTEMPTS


def test_load_qr_json_rejects_non_object_root() -> None:
    """Test QR JSON root must be an object."""
    with pytest.raises(
        FirewallaValidationError,
        match="QR JSON root must be an object",
    ):
        load_qr_json('["not", "an", "object"]')


def test_parse_login_identity_rejects_invalid_json() -> None:
    """Test invalid login/eptoken JSON raises a protocol error."""
    with pytest.raises(
        FirewallaProtocolError,
        match="login/eptoken response was not valid JSON",
    ):
        parse_login_identity("not-json")


def test_parse_login_identity_requires_access_token() -> None:
    """Test login/eptoken responses must include an access token."""
    with pytest.raises(
        FirewallaProtocolError,
        match="login/eptoken response did not include access_token",
    ):
        parse_login_identity('{"eid":"eid-123","aid":"aid-123","groups":[]}')


def test_extract_groups_supports_wrapped_and_raw_lists() -> None:
    """Test group extraction handles both wrapped and raw list payloads."""
    raw_groups = [{"_id": "gid-123", "eid": "eid-123", "aid": "aid-123"}]

    assert extract_groups(raw_groups) == raw_groups
    assert extract_groups({"groups": raw_groups}) == raw_groups
    assert extract_groups({"groups": "invalid"}) is None


def test_extract_group_credentials_returns_credentials() -> None:
    """Test matching group records yield durable local credentials."""
    qr_data = load_qr_json(
        '{"gid":"gid-123","seed":"seed-123","license":"license-123","ek":"ciphertext","ipaddress":"192.168.200.1"}'
    )

    with patch(
        "custom_components.firewalla_local.api.auth.rsa_decrypt_base64",
        return_value="plain-symmetric-key",
    ):
        credentials = extract_group_credentials(
            groups=[
                {
                    "_id": "gid-123",
                    "eid": "eid-123",
                    "aid": "aid-123",
                    "symmetricKeys": [{"key": "encrypted-key"}],
                }
            ],
            qr_data=qr_data,
            host="192.168.200.1",
            private_pem="private-pem",
        )

    assert credentials == FirewallaProvisionedCredentials(
        license="license-123",
        host="192.168.200.1",
        gid="gid-123",
        eid="eid-123",
        aid="aid-123",
        symmetric_key="plain-symmetric-key",
        box_name=None,
    )


def test_extract_group_credentials_uses_rkey_when_present() -> None:
    """Test rkey.key takes priority over symmetricKeys[0].key."""
    qr_data = load_qr_json(
        '{"gid":"gid-123","seed":"seed-123","license":"license-123",'
        '"ek":"ciphertext","ipaddress":"192.168.200.1"}'
    )

    with patch(
        "custom_components.firewalla_local.api.auth.rsa_decrypt_base64",
        side_effect=["intermediate-key", "rkey-derived-key"],
    ):
        credentials = extract_group_credentials(
            groups=[
                {
                    "_id": "gid-123",
                    "eid": "eid-123",
                    "aid": "aid-123",
                    "symmetricKeys": [
                        {
                            "key": "encrypted-key",
                            "rkey": '{"key":"encrypted-rkey","ts":1765640872}',
                        }
                    ],
                }
            ],
            qr_data=qr_data,
            host="192.168.200.1",
            private_pem="private-pem",
        )

    assert credentials == FirewallaProvisionedCredentials(
        license="license-123",
        host="192.168.200.1",
        gid="gid-123",
        eid="eid-123",
        aid="aid-123",
        symmetric_key="rkey-derived-key",
        box_name=None,
    )


def test_extract_group_credentials_falls_back_when_rkey_absent() -> None:
    """Test direct symmetricKeys[0].key is used when rkey is absent."""
    qr_data = load_qr_json(
        '{"gid":"gid-123","seed":"seed-123","license":"license-123",'
        '"ek":"ciphertext","ipaddress":"192.168.200.1"}'
    )

    with patch(
        "custom_components.firewalla_local.api.auth.rsa_decrypt_base64",
        return_value="direct-key",
    ):
        credentials = extract_group_credentials(
            groups=[
                {
                    "_id": "gid-123",
                    "eid": "eid-123",
                    "aid": "aid-123",
                    "symmetricKeys": [{"key": "encrypted-key"}],
                }
            ],
            qr_data=qr_data,
            host="192.168.200.1",
            private_pem="private-pem",
        )

    assert credentials == FirewallaProvisionedCredentials(
        license="license-123",
        host="192.168.200.1",
        gid="gid-123",
        eid="eid-123",
        aid="aid-123",
        symmetric_key="direct-key",
        box_name=None,
    )


def test_extract_group_credentials_falls_back_on_rkey_parse_failure() -> None:
    """Test extract falls back to direct key when rkey JSON is malformed."""
    qr_data = load_qr_json(
        '{"gid":"gid-123","seed":"seed-123","license":"license-123",'
        '"ek":"ciphertext","ipaddress":"192.168.200.1"}'
    )

    with patch(
        "custom_components.firewalla_local.api.auth.rsa_decrypt_base64",
        return_value="direct-key",
    ):
        credentials = extract_group_credentials(
            groups=[
                {
                    "_id": "gid-123",
                    "eid": "eid-123",
                    "aid": "aid-123",
                    "symmetricKeys": [
                        {
                            "key": "encrypted-key",
                            "rkey": "not-valid-json{",
                        }
                    ],
                }
            ],
            qr_data=qr_data,
            host="192.168.200.1",
            private_pem="private-pem",
        )

    assert credentials == FirewallaProvisionedCredentials(
        license="license-123",
        host="192.168.200.1",
        gid="gid-123",
        eid="eid-123",
        aid="aid-123",
        symmetric_key="direct-key",
        box_name=None,
    )


def test_default_group_poll_attempts_extended_for_slower_cloud_link() -> None:
    """Test the default polling window allows slower cloud group visibility."""
    assert DEFAULT_GROUP_POLL_ATTEMPTS == 20


@pytest.mark.asyncio
async def test_async_provision_firewalla_credentials_polls_until_group_visible() -> (
    None
):
    """Test provisioning stays internal and polls until group credentials appear."""
    qr_data = load_qr_json(
        '{"gid":"gid-123","seed":"seed-123","license":"license-123",'
        '"ek":"ciphertext","ipaddress":"192.168.200.1",'
        '"deviceName":"Office Box"}'
    )
    keys = GeneratedKeys(private_pem="private-pem", public_pem="public-pem")
    identity = ETPIdentity(
        access_token="token-123",
        eid="eid-123",
        aid="aid-123",
        groups=[],
    )
    expected_credentials = FirewallaProvisionedCredentials(
        license="license-123",
        host="192.168.200.1",
        gid="gid-123",
        eid="eid-123",
        aid="aid-123",
        symmetric_key="plain-symmetric-key",
        box_name="Office Box",
    )

    async with ClientSession() as session:
        with (
            patch(
                "custom_components.firewalla_local.api.auth.login_eptoken",
                AsyncMock(return_value=identity),
            ),
            patch(
                "custom_components.firewalla_local.api.auth.decrypt_pairing_code",
                return_value=PairingCode(
                    rendezvous_id="rid-123",
                    evalue={"license": "license-123"},
                ),
            ),
            patch(
                "custom_components.firewalla_local.api.auth.link_group_cloud",
                AsyncMock(),
            ) as mock_link_group_cloud,
            patch(
                "custom_components.firewalla_local.api.auth.fetch_groups",
                AsyncMock(
                    side_effect=[
                        (
                            GroupFetchResult(
                                source="/ept/group/me",
                                status=200,
                                groups=[],
                            ),
                            identity,
                        ),
                        (
                            GroupFetchResult(
                                source="/ept/group/me",
                                status=200,
                                groups=[{"_id": "gid-123"}],
                            ),
                            identity,
                        ),
                    ]
                ),
            ) as mock_fetch_groups,
            patch(
                "custom_components.firewalla_local.api.auth.extract_group_credentials",
                side_effect=[None, expected_credentials],
            ) as mock_extract_group_credentials,
            patch(
                "custom_components.firewalla_local.api.auth.asyncio.sleep",
                AsyncMock(),
            ) as mock_sleep,
        ):
            credentials = await async_provision_firewalla_credentials(
                session,
                qr_data=qr_data,
                host="192.168.200.1",
                keys=keys,
                attempts=2,
                interval=0.01,
            )

    assert credentials == expected_credentials
    assert mock_link_group_cloud.await_count == 1
    assert mock_fetch_groups.await_count == 2
    assert mock_extract_group_credentials.call_count == 2
    assert mock_sleep.await_count == 1
