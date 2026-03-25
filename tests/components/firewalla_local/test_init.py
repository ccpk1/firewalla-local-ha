"""Tests for Firewalla Local setup."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.api.exceptions import (
    FirewallaAuthError,
    FirewallaConnectionError,
)
from custom_components.firewalla_local.const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_LOCAL_IP,
    CONF_SYMMETRIC_KEY,
    DOMAIN,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIG_ENTRY_NAME,
    SERVICE_GET_RUNTIME_INVENTORY,
)
from custom_components.firewalla_local.models import (
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
    FirewallaSystemInfo,
)


def _mock_snapshot() -> FirewallaRuntimeSnapshot:
    """Return a representative runtime snapshot for setup and refresh tests."""
    return FirewallaRuntimeSnapshot(
        system_info=FirewallaSystemInfo(
            host="192.168.200.1",
            name="Firewalla",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="739",
                action="block",
                target="00:08:9B:FB:01:D9",
                target_type="mac",
                direction="bidirection",
                enabled=False,
                purpose="dap",
                scope=(),
                target_name="Living room speaker",
            ),
        ),
        exception_rule_count=12,
    )


def _mock_runtime_payload() -> dict[str, object]:
    """Return a representative raw init payload for setup and refresh tests."""
    return {"policyRules": []}


async def test_setup_entry(hass: HomeAssistant) -> None:
    """Test setting up a provisioned Firewalla entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_mock_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_data = entry.runtime_data
    assert runtime_data.client.host == "192.168.200.1"
    assert runtime_data.client.gid == "gid-123"
    assert runtime_data.coordinator.data is not None
    assert runtime_data.coordinator.data.system_info.host == "192.168.200.1"
    assert len(runtime_data.coordinator.data.policy_rules) == 1
    assert runtime_data.coordinator.data.exception_rule_count == 12


async def test_setup_entry_normalizes_local_ip_to_host(hass: HomeAssistant) -> None:
    """Test setup normalizes local_ip connection data to host."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_LOCAL_IP: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_mock_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.data[CONF_HOST] == "192.168.200.1"
    assert CONF_LOCAL_IP not in entry.data


async def test_setup_entry_raises_auth_failed(hass: HomeAssistant) -> None:
    """Test auth failures during first refresh fail setup cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
        new=AsyncMock(side_effect=FirewallaAuthError("unauthorized")),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_coordinator_logs_unavailability_once_and_recovery(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test the coordinator logs one outage and one recovery event."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_mock_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_data = entry.runtime_data
    caplog.set_level(logging.INFO, logger="custom_components.firewalla_local.const")

    with (
        patch.object(
            runtime_data.client,
            "async_get_runtime_init_payload",
            AsyncMock(
                side_effect=[
                    FirewallaConnectionError("offline"),
                    FirewallaConnectionError("offline"),
                    _mock_runtime_payload(),
                ]
            ),
        ),
        patch.object(
            runtime_data.client,
            "build_runtime_snapshot",
            return_value=_mock_snapshot(),
        ),
    ):
        await runtime_data.coordinator.async_refresh()
        await runtime_data.coordinator.async_refresh()
        await runtime_data.coordinator.async_refresh()

    unavailable_messages = [
        record.message
        for record in caplog.records
        if "The Firewalla box is unavailable" in record.message
    ]
    recovery_messages = [
        record.message
        for record in caplog.records
        if record.message == "The Firewalla box is back online"
    ]

    assert len(unavailable_messages) == 1
    assert len(recovery_messages) == 1


async def test_get_runtime_inventory_service_returns_markdown(
    hass: HomeAssistant,
) -> None:
    """Test the runtime inventory service returns markdown from a loaded entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_mock_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_payload = {
        "hosts": [],
        "networkProfiles": {},
        "tags": {"10": {"name": "KADEN's Devices", "policy": {}}},
        "userTags": {"21": {"name": "KADEN", "affiliatedTag": "10"}},
        "policyRules": [{"pid": "739", "target": "00:08:9B:FB:01:D9", "type": "mac"}],
    }

    with patch.object(
        entry.runtime_data.client,
        "async_get_runtime_init_payload",
        AsyncMock(return_value=runtime_payload),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RUNTIME_INVENTORY,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert "# Firewalla runtime inventory" in response["markdown"]
    assert response["inventory"]["summary"]["group_count"] == 1


async def test_get_runtime_inventory_service_uses_single_loaded_entry(
    hass: HomeAssistant,
) -> None:
    """Test the runtime inventory service defaults to the only loaded entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_mock_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_payload = {
        "hosts": [],
        "networkProfiles": {},
        "tags": {},
        "userTags": {},
        "policyRules": [],
    }

    with patch.object(
        entry.runtime_data.client,
        "async_get_runtime_init_payload",
        AsyncMock(return_value=runtime_payload),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RUNTIME_INVENTORY,
            {},
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["config_entry_id"] == entry.entry_id


async def test_get_runtime_inventory_service_accepts_entry_name(
    hass: HomeAssistant,
) -> None:
    """Test the runtime inventory service can target a loaded entry by title."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Office Firewalla",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_mock_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_payload = {
        "hosts": [],
        "networkProfiles": {},
        "tags": {},
        "userTags": {},
        "policyRules": [],
    }

    with patch.object(
        entry.runtime_data.client,
        "async_get_runtime_init_payload",
        AsyncMock(return_value=runtime_payload),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RUNTIME_INVENTORY,
            {SERVICE_FIELD_CONFIG_ENTRY_NAME: "Office Firewalla"},
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["config_entry_id"] == entry.entry_id


async def test_setup_populates_raw_payload_for_live_rule_filtering(
    hass: HomeAssistant,
) -> None:
    """Test setup stores the raw payload used by live rule selection."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    runtime_payload = {
        "policyRules": [
            {
                "pid": "639",
                "action": "allow",
                "target": "chrome.cloudflare-dns.com",
                "target_name": "chrome.cloudflare-dns.com",
                "type": "dns",
                "direction": "outbound",
                "disabled": 0,
            },
            {
                "pid": "650",
                "action": "block",
                "target": "vin15.pbs.ovhnextmillmedia.com",
                "target_name": "vin15.pbs.ovhnextmillmedia.com",
                "type": "dns",
                "direction": "bidirection",
                "disabled": 0,
                "method": "auto",
                "alarm_type": "ALARM_INTEL",
                "blockby": "fastdns",
                "category": "intel",
                "reason": "ALARM_INTEL",
            },
        ]
    }
    runtime_snapshot = FirewallaRuntimeSnapshot(
        system_info=FirewallaSystemInfo(
            host="192.168.200.1",
            name="Firewalla",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="639",
                action="allow",
                target="chrome.cloudflare-dns.com",
                target_type="dns",
                direction="outbound",
                enabled=True,
                purpose=None,
                scope=(),
                target_name="chrome.cloudflare-dns.com",
                raw_update_payload=dict(runtime_payload["policyRules"][0]),
            ),
            FirewallaPolicyRule(
                rule_id="650",
                action="block",
                target="vin15.pbs.ovhnextmillmedia.com",
                target_type="dns",
                direction="bidirection",
                enabled=True,
                purpose=None,
                scope=(),
                target_name="vin15.pbs.ovhnextmillmedia.com",
                raw_update_payload=dict(runtime_payload["policyRules"][1]),
            ),
        ),
        exception_rule_count=0,
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=runtime_payload),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=runtime_snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.runtime_data.coordinator.last_init_payload == runtime_payload
    assert entry.runtime_data.rule_manager.get_switch_candidate_choices() == {
        "639": "[639] allow dns chrome.cloudflare-dns.com (enabled)"
    }


async def test_get_runtime_inventory_service_rejects_unknown_entry(
    hass: HomeAssistant,
) -> None:
    """Test the runtime inventory service validates the requested config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_mock_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError, match="Config entry not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RUNTIME_INVENTORY,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: "missing-entry"},
            blocking=True,
            return_response=True,
        )


async def test_get_runtime_inventory_service_requires_selector_with_multiple_entries(
    hass: HomeAssistant,
) -> None:
    """Test the runtime inventory service requires a selector with multiple entries."""
    first_entry = MockConfigEntry(
        domain=DOMAIN,
        title="First Firewalla",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Second Firewalla",
        data={
            CONF_LICENSE: "license-456",
            CONF_HOST: "192.168.200.2",
            CONF_GID: "gid-456",
            CONF_EID: "eid-456",
            CONF_AID: "aid-456",
            CONF_SYMMETRIC_KEY: "symmetric-key-2",
        },
    )
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_mock_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(first_entry.entry_id)
        if second_entry.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(second_entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match=(
            "Multiple Firewalla entries are loaded; "
            "use config_entry_id or config_entry_name"
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RUNTIME_INVENTORY,
            {},
            blocking=True,
            return_response=True,
        )
