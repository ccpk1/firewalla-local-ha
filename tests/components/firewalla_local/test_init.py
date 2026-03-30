"""Tests for Firewalla Local setup."""

from __future__ import annotations

import logging
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DOMAIN, ATTR_SERVICE, EVENT_SERVICE_REGISTERED
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
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
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    CONF_SYMMETRIC_KEY,
    CONF_UPDATE_INTERVAL,
    CONF_WATCHED_DEVICES,
    DOMAIN,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIG_ENTRY_NAME,
    SERVICE_GET_NETWORK_INTERFACES,
    SERVICE_GET_RUNTIME_INVENTORY,
    SERVICE_GET_SPEED_TEST_RESULTS,
    SERVICE_GET_USAGE_HISTORY,
    SERVICE_GET_WAN_DATA_USAGE,
    SERVICE_GET_WAN_EVENTS,
    SERVICE_PAUSE_RULE,
    SERVICE_RESUME_RULE,
    SERVICE_RUN_INTERNET_SPEED_TEST,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
    FirewallaUserAppUsage,
    FirewallaUserRuntime,
)


def _mock_snapshot() -> FirewallaRuntimeSnapshot:
    """Return a representative runtime snapshot for setup and refresh tests."""
    return FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
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
        hosts=(
            FirewallaHostRuntime(
                mac="wg_peer:test-peer",
                display_name="WireGuard Kaden",
                fallback_name=None,
                ip_address="10.42.0.2",
                group_name=None,
                network_name="VLAN10 CORE",
                connection_type="phone",
                last_active=1774287000.5,
                download_bytes=99,
                upload_bytes=100,
                stale=False,
                user_ids=("21",),
            ),
        ),
        users=(
            FirewallaUserRuntime(
                user_id="21",
                name="KADEN",
                affiliated_group_id="10",
                affiliated_group_name="KADEN's Devices",
                total_minutes_today=410,
                unique_minutes_today=381,
                app_usage_today=(
                    FirewallaUserAppUsage(
                        app_id="youtube",
                        category="av",
                        total_minutes=47,
                        unique_minutes=44,
                    ),
                ),
            ),
        ),
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
    assert runtime_data.integration_manager.system_info.host == "192.168.200.1"
    assert len(runtime_data.coordinator.data.policy_rules) == 1
    assert runtime_data.coordinator.data.exception_rule_count == 12
    assert runtime_data.host_manager.get_host("wg_peer:test-peer") is not None
    watched_user = runtime_data.user_manager.get_user("21")
    assert watched_user is not None
    assert watched_user.total_minutes_today == 410
    assert watched_user.associated_host_names == ("WireGuard Kaden",)


async def test_setup_uses_entry_scoped_update_interval_options(
    hass: HomeAssistant,
) -> None:
    """Test each loaded entry uses its own configured polling interval."""
    first_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="First Firewalla",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_UPDATE_INTERVAL: 3},
    )
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-456",
        title="Second Firewalla",
        data={
            CONF_LICENSE: "license-456",
            CONF_HOST: "192.168.200.2",
            CONF_GID: "gid-456",
            CONF_EID: "eid-456",
            CONF_AID: "aid-456",
            CONF_SYMMETRIC_KEY: "symmetric-key-2",
        },
        options={CONF_UPDATE_INTERVAL: 7},
    )
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)

    second_snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.2",
            group_name="Firewalla Upstairs",
            device_name=None,
            model="gold",
            serial_number="serial-456",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=(_mock_snapshot(), second_snapshot),
        ),
    ):
        assert await hass.config_entries.async_setup(first_entry.entry_id)
        if second_entry.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(second_entry.entry_id)
        await hass.async_block_till_done()

    assert first_entry.runtime_data.coordinator.update_interval == timedelta(minutes=3)
    assert second_entry.runtime_data.coordinator.update_interval == timedelta(minutes=7)


async def test_options_update_changes_coordinator_interval_without_reload(
    hass: HomeAssistant,
) -> None:
    """Test update_interval-only option changes update the live coordinator in place."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={
            CONF_SELECTED_RULE_IDS: [],
            CONF_UPDATE_INTERVAL: 3,
            CONF_WATCHED_DEVICES: [],
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

    original_runtime_data = entry.runtime_data
    original_coordinator = entry.runtime_data.coordinator

    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_SELECTED_RULE_IDS: [],
            CONF_SELECTED_RULE_TEMPLATES: [],
            CONF_UPDATE_INTERVAL: 6,
            CONF_WATCHED_DEVICES: [],
        },
    )
    await hass.async_block_till_done()

    assert entry.runtime_data is original_runtime_data
    assert entry.runtime_data.coordinator is original_coordinator
    assert entry.runtime_data.coordinator.update_interval == timedelta(minutes=6)


async def test_options_update_reloads_entry_when_watched_devices_change(
    hass: HomeAssistant,
) -> None:
    """Test watched-device selection changes trigger a config-entry reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={
            CONF_SELECTED_RULE_IDS: [],
            CONF_UPDATE_INTERVAL: 3,
            CONF_WATCHED_DEVICES: [],
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

    with patch.object(
        hass.config_entries,
        "async_reload",
        new=AsyncMock(),
    ) as mock_reload:
        hass.config_entries.async_update_entry(
            entry,
            options={
                CONF_SELECTED_RULE_IDS: [],
                CONF_SELECTED_RULE_TEMPLATES: [],
                CONF_UPDATE_INTERVAL: 3,
                CONF_WATCHED_DEVICES: ["wg_peer:test-peer"],
            },
        )
        await hass.async_block_till_done()

    mock_reload.assert_awaited_once_with(entry.entry_id)


async def test_setup_multiple_entries_create_distinct_license_devices(
    hass: HomeAssistant,
) -> None:
    """Test two loaded entries create distinct license-anchored devices."""
    first_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
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
        unique_id="license-456",
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

    second_snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.2",
            group_name="Firewalla Upstairs",
            device_name=None,
            model="gold",
            serial_number="serial-456",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=(_mock_snapshot(), second_snapshot),
        ),
    ):
        assert await hass.config_entries.async_setup(first_entry.entry_id)
        if second_entry.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(second_entry.entry_id)
        await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    first_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "license-123")}
    )
    second_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "license-456")}
    )

    assert first_device is not None
    assert second_device is not None
    assert first_device.id != second_device.id
    assert (
        len(dr.async_entries_for_config_entry(device_registry, first_entry.entry_id))
        == 1
    )
    assert (
        len(dr.async_entries_for_config_entry(device_registry, second_entry.entry_id))
        == 1
    )


async def test_setup_multiple_entries_registers_domain_services_once(
    hass: HomeAssistant,
) -> None:
    """Test domain services register once even when two entries load."""
    first_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
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
        unique_id="license-456",
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

    second_snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.2",
            group_name="Firewalla Upstairs",
            device_name=None,
            model="gold",
            serial_number="serial-456",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
    )
    registered_events: list[dict[str, str]] = []

    def _capture_service_registered(event) -> None:
        if event.data[ATTR_DOMAIN] == DOMAIN:
            registered_events.append(event.data)

    hass.bus.async_listen(EVENT_SERVICE_REGISTERED, _capture_service_registered)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_mock_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=(_mock_snapshot(), second_snapshot),
        ),
    ):
        assert await hass.config_entries.async_setup(first_entry.entry_id)
        if second_entry.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(second_entry.entry_id)
        await hass.async_block_till_done()

    assert sorted(
        (event[ATTR_DOMAIN], event[ATTR_SERVICE]) for event in registered_events
    ) == sorted(
        [
            (DOMAIN, SERVICE_GET_NETWORK_INTERFACES),
            (DOMAIN, SERVICE_GET_RUNTIME_INVENTORY),
            (DOMAIN, SERVICE_GET_SPEED_TEST_RESULTS),
            (DOMAIN, SERVICE_GET_USAGE_HISTORY),
            (DOMAIN, SERVICE_GET_WAN_EVENTS),
            (DOMAIN, SERVICE_GET_WAN_DATA_USAGE),
            (DOMAIN, SERVICE_PAUSE_RULE),
            (DOMAIN, SERVICE_RESUME_RULE),
            (DOMAIN, SERVICE_RUN_INTERNET_SPEED_TEST),
        ]
    )
    assert set(hass.services.async_services()[DOMAIN]) == {
        SERVICE_GET_NETWORK_INTERFACES,
        SERVICE_GET_RUNTIME_INVENTORY,
        SERVICE_GET_SPEED_TEST_RESULTS,
        SERVICE_GET_USAGE_HISTORY,
        SERVICE_GET_WAN_EVENTS,
        SERVICE_GET_WAN_DATA_USAGE,
        SERVICE_PAUSE_RULE,
        SERVICE_RESUME_RULE,
        SERVICE_RUN_INTERNET_SPEED_TEST,
    }


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
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
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
