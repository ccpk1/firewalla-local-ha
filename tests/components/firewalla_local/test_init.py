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
    CONF_CONFIG_ENTRY_ID,
    CONF_CONFIG_ENTRY_NAME,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
    DOMAIN,
    LEGACY_CONF_LOCAL_IP,
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

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
        new=AsyncMock(return_value=_mock_snapshot()),
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


async def test_setup_entry_migrates_legacy_local_ip(hass: HomeAssistant) -> None:
    """Test setup migrates legacy local_ip connection data to host."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            LEGACY_CONF_LOCAL_IP: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
        new=AsyncMock(return_value=_mock_snapshot()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.data[CONF_HOST] == "192.168.200.1"
    assert LEGACY_CONF_LOCAL_IP not in entry.data


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
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
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

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
        new=AsyncMock(return_value=_mock_snapshot()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_data = entry.runtime_data
    caplog.set_level(logging.INFO, logger="custom_components.firewalla_local.const")

    with patch.object(
        runtime_data.client,
        "async_get_runtime_snapshot",
        AsyncMock(
            side_effect=[
                FirewallaConnectionError("offline"),
                FirewallaConnectionError("offline"),
                _mock_snapshot(),
            ]
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

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
        new=AsyncMock(return_value=_mock_snapshot()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_payload = {
        "hosts": [],
        "networkProfiles": {},
        "tags": {"10": {"name": "KADEN's Devices", "policy": {}}},
        "userTags": {"21": {"name": "KADEN", "affiliatedTag": "10"}},
        "policyRules": [
            {"pid": "739", "target": "00:08:9B:FB:01:D9", "type": "mac"}
        ],
    }

    with patch.object(
        entry.runtime_data.client,
        "async_get_runtime_init_payload",
        AsyncMock(return_value=runtime_payload),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RUNTIME_INVENTORY,
            {CONF_CONFIG_ENTRY_ID: entry.entry_id},
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

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
        new=AsyncMock(return_value=_mock_snapshot()),
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

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
        new=AsyncMock(return_value=_mock_snapshot()),
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
            {CONF_CONFIG_ENTRY_NAME: "Office Firewalla"},
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["config_entry_id"] == entry.entry_id


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

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
        new=AsyncMock(return_value=_mock_snapshot()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError, match="Config entry not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RUNTIME_INVENTORY,
            {CONF_CONFIG_ENTRY_ID: "missing-entry"},
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

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
        new=AsyncMock(return_value=_mock_snapshot()),
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
