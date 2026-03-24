"""Tests for Firewalla Local client normalization."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientSession

from custom_components.firewalla_local.api.client import FirewallaApiClient
from custom_components.firewalla_local.api.crypto import aes256_cbc_encrypt_to_base64
from custom_components.firewalla_local.api.exceptions import FirewallaAuthError
from custom_components.firewalla_local.models import (
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
)

TEST_SYMMETRIC_KEY = "0123456789abcdef0123456789abcdef"


@pytest.mark.asyncio
async def test_get_runtime_snapshot_normalizes_policy_rules() -> None:
    """Test runtime snapshots normalize policy rules into a stable typed shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(
                return_value={
                    "groupName": "Firewalla",
                    "model": "gold",
                    "cpuid": "serial-123",
                    "longVersion": "1.0.0",
                    "customizedCategories": {
                        "dap_00089bfb01d9": {"name": "DAP - 00:08:9B:FB:01:D9"}
                    },
                    "hosts": [{"mac": "00:08:9B:FB:01:D9", "name": "Kitchen speaker"}],
                    "networkConfig": {
                        "interface": {
                            "bond": {
                                "bond0.10": {
                                    "meta": {
                                        "name": "VLAN10 CORE",
                                        "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
                                    }
                                }
                            }
                        }
                    },
                    "networkProfiles": {
                        "5799d896-5e0f-40a5-a776-38a5d7746204": {"intf": "bond0.10"}
                    },
                    "tags": {
                        "10": {"name": "KADEN's Devices"},
                        "12": {"name": "Quarantine"},
                    },
                    "userTags": {"21": {"name": "KADEN", "affiliatedTag": "10"}},
                    "exceptionRules": [{"aid": "1"}, {"aid": "2"}],
                    "policyRules": [
                        {
                            "pid": "739",
                            "action": "block",
                            "target": "00:08:9B:FB:01:D9",
                            "type": "mac",
                            "direction": "bidirection",
                            "disabled": "1",
                            "purpose": "dap",
                        },
                        {
                            "pid": "738",
                            "action": "allow",
                            "target": "dap_00089bfb01d9",
                            "type": "category",
                            "direction": "outbound",
                            "disabled": "0",
                            "purpose": "dap",
                            "scope": ["00:08:9B:FB:01:D9"],
                        },
                        {
                            "pid": "737",
                            "action": "block",
                            "target": "5799d896-5e0f-40a5-a776-38a5d7746204",
                            "type": "network",
                            "direction": "bidirection",
                            "disabled": "0",
                        },
                        {
                            "pid": "736",
                            "action": "block",
                            "target": "TAG",
                            "type": "mac",
                            "direction": "bidirection",
                            "disabled": "0",
                            "tag": ["tag:12"],
                        },
                        {
                            "pid": "735",
                            "action": "allow",
                            "target": "spotify.com",
                            "type": "dns",
                            "direction": "outbound",
                            "disabled": "0",
                            "tag": ["tag:10"],
                        },
                        {
                            "pid": "734",
                            "action": "block",
                            "target": "social",
                            "type": "category",
                            "direction": "bidirection",
                            "disabled": "0",
                            "tag": ["tag:12"],
                            "activatedTime": "1774299013",
                            "expire": 3600,
                            "autoDeleteWhenExpires": "1",
                            "dnsmasq_only": True,
                        },
                    ],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    rules = snapshot.policy_rules
    assert len(rules) == 6
    assert snapshot.system_info.name == "Firewalla"
    assert snapshot.exception_rule_count == 2
    assert rules[0].rule_id == "739"
    assert rules[0].enabled is False
    assert rules[0].target_name == "Kitchen speaker"
    assert rules[1].rule_id == "738"
    assert rules[1].enabled is True
    assert rules[1].scope == ("00:08:9B:FB:01:D9",)
    assert rules[1].target_name == "DAP - 00:08:9B:FB:01:D9"
    assert rules[2].target_name == "VLAN10 CORE"
    assert rules[3].target_name == "Quarantine"
    assert rules[4].applies_to == ("KADEN's Devices (KADEN)",)
    assert rules[5].target_name == "social"
    assert rules[5].tag_refs == ("tag:12",)
    assert rules[5].activated_time == 1774299013.0
    assert rules[5].expire_seconds == 3600
    assert rules[5].expires_at == 1774302613.0
    assert rules[5].auto_delete_when_expires is True
    assert rules[5].dnsmasq_only is True
    assert rules[5].is_temporary is True


@pytest.mark.asyncio
async def test_create_rule_sends_confirmed_persistent_payload() -> None:
    """Test rule creation uses the confirmed persistent mutation shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        template = FirewallaRuleTemplate(
            source_rule_id="744",
            name="block category social for AV_SMART_TV",
            action="block",
            target="social",
            target_type="category",
            tag_refs=("tag:17",),
            dnsmasq_only=True,
        )

        with (
            patch(
                "custom_components.firewalla_local.api.client.time.time",
                return_value=1774303259.8190122,
            ),
            patch.object(
                client, "_async_send_local_message", AsyncMock(return_value={})
            ) as mock_send,
        ):
            await client.async_create_rule(template)

    assert mock_send.await_args.kwargs == {
        "message_type": "cmd",
        "data": {
            "item": "policy:create",
            "value": {
                "action": "block",
                "appTimeUsage": {},
                "disturbLevel": "",
                "disturbMethod": {},
                "dnsmasq_only": True,
                "duration": "",
                "scope": [],
                "tag": ["tag:17"],
                "target": "social",
                "trust": "",
                "type": "category",
                "updatedTime": 1774303259.8190122,
                "useBf": True,
            },
        },
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_delete_rule_sends_confirmed_delete_payload() -> None:
    """Test rule deletion uses the confirmed delete mutation shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )

        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(return_value={}),
        ) as mock_send:
            await client.async_delete_rule("744")

    assert mock_send.await_args.kwargs == {
        "message_type": "cmd",
        "data": {"item": "policy:delete", "value": {"policyID": "744"}},
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_update_rule_sends_live_rule_payload_with_changed_state() -> None:
    """Test rule updates preserve the live payload and only toggle state fields."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        rule = FirewallaPolicyRule(
            rule_id="211",
            action="allow",
            target="spotify.com",
            target_type="dns",
            direction="outbound",
            enabled=False,
            purpose=None,
            scope=(),
            tag_refs=("tag:10",),
            applies_to=("KADEN's Devices (KADEN)",),
            dnsmasq_only=False,
            raw_update_payload={
                "pid": "211",
                "action": "allow",
                "direction": "outbound",
                "disabled": 1,
                "dnsmasq_only": False,
                "idleTs": "1774324800",
                "tag": ["tag:10"],
                "target": "spotify.com",
                "timestamp": "1693953160.462",
                "trust": True,
                "type": "dns",
                "upnp": False,
                "useBf": "",
            },
        )

        with (
            patch(
                "custom_components.firewalla_local.api.client.time.time",
                return_value=1774310993.8565822,
            ),
            patch.object(
                client, "_async_send_local_message", AsyncMock(return_value={})
            ) as mock_send,
        ):
            await client.async_update_rule(rule, enabled=True)

    assert mock_send.await_args.kwargs == {
        "message_type": "cmd",
        "data": {
            "item": "policy:update",
            "value": {
                "pid": "211",
                "action": "allow",
                "direction": "outbound",
                "disabled": 0,
                "dnsmasq_only": False,
                "idleTs": "",
                "tag": ["tag:10"],
                "target": "spotify.com",
                "timestamp": "1693953160.462",
                "trust": True,
                "type": "dns",
                "updatedTime": 1774310993.8565822,
                "upnp": False,
                "useBf": "",
            },
        },
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_get_system_info_retries_once_on_unauthorized() -> None:
    """Test a single 401 is retried before decoding the local response."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        encrypted_message = aes256_cbc_encrypt_to_base64(
            json.dumps(
                {
                    "code": 200,
                    "data": {
                        "groupName": "Firewalla",
                        "model": "gold",
                        "cpuid": "serial-123",
                        "longVersion": "1.0.0",
                    },
                },
                separators=(",", ":"),
            ),
            TEST_SYMMETRIC_KEY,
        )

        with patch.object(
            client,
            "_async_post_local_payload",
            AsyncMock(
                side_effect=[
                    (401, "unauthorized"),
                    (200, json.dumps({"message": encrypted_message})),
                ]
            ),
        ) as mock_post:
            system_info = await client.async_get_system_info()

    assert system_info.name == "Firewalla"
    assert mock_post.await_count == 2


@pytest.mark.asyncio
async def test_get_system_info_raises_auth_error_after_second_unauthorized() -> None:
    """Test repeated 401 responses raise a typed auth error."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )

        with (
            patch.object(
                client,
                "_async_post_local_payload",
                AsyncMock(side_effect=[(401, "unauthorized"), (401, "unauthorized")]),
            ) as mock_post,
            pytest.raises(FirewallaAuthError),
        ):
            await client.async_get_system_info()

    assert mock_post.await_count == 2
