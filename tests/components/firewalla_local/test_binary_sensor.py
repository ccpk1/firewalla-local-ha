"""Tests for Firewalla Local binary sensors."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import (
    ATTR_PURPOSE,
    ATTR_WATCHED_DEVICE_CONNECTION_TYPE,
    ATTR_WATCHED_DEVICE_DEVICE_GROUP,
    ATTR_WATCHED_DEVICE_DOWNLOAD_USAGE,
    ATTR_WATCHED_DEVICE_IP_ADDRESS,
    ATTR_WATCHED_DEVICE_LAST_ACTIVE,
    ATTR_WATCHED_DEVICE_NETWORK_NAME,
    ATTR_WATCHED_DEVICE_UPLOAD_USAGE,
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
    CONF_WATCHED_DEVICES,
    DOMAIN,
    TRANS_KEY_PURPOSE_WATCHED_DEVICE_CONNECTIVITY,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaHostRuntime,
    FirewallaRuntimeSnapshot,
)


def _binary_sensor_state_for_unique_suffix(hass: HomeAssistant, unique_suffix: str):
    """Return the binary-sensor state matching one unique-ID suffix."""
    entity_entry = next(
        entry
        for entry in er.async_get(hass).entities.values()
        if entry.domain == "binary_sensor" and entry.unique_id.endswith(unique_suffix)
    )
    state = hass.states.get(entity_entry.entity_id)
    assert state is not None
    return state


def _runtime_payload() -> dict[str, object]:
    """Return a minimal init payload for setup tests."""
    return {"policyRules": []}


def _snapshot_with_hosts(*hosts: FirewallaHostRuntime) -> FirewallaRuntimeSnapshot:
    """Return a runtime snapshot with the requested watched hosts."""
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
        policy_rules=(),
        exception_rule_count=0,
        hosts=hosts,
    )


async def test_watched_device_binary_sensor_exposes_state_and_attributes(
    hass: HomeAssistant,
) -> None:
    """Test a selected watched host becomes a connectivity binary sensor."""
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
        options={CONF_WATCHED_DEVICES: ["AA:BB:CC:DD:EE:FF"]},
    )
    entry.add_to_hass(hass)

    snapshot = _snapshot_with_hosts(
        FirewallaHostRuntime(
            mac="AA:BB:CC:DD:EE:FF",
            host_name="Kaden Phone",
            dns_hostname="kaden-phone",
            ip_address="192.168.200.25",
            group_name="KADEN",
            network_name="VLAN10 CORE",
            connection_type="phone",
            last_active=1774287984.272,
            download_bytes=1234,
            upload_bytes=5678,
            stale=False,
        )
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    watched_state = _binary_sensor_state_for_unique_suffix(
        hass, "_AA:BB:CC:DD:EE:FF_binary_sensor"
    )

    assert watched_state is not None
    assert watched_state.name is not None
    assert "Kaden Phone" in watched_state.name
    assert watched_state.state == STATE_ON
    assert (
        watched_state.attributes[ATTR_PURPOSE]
        == TRANS_KEY_PURPOSE_WATCHED_DEVICE_CONNECTIVITY
    )
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_IP_ADDRESS] == "192.168.200.25"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_DEVICE_GROUP] == "KADEN"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_NETWORK_NAME] == "VLAN10 CORE"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_CONNECTION_TYPE] == "phone"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_DOWNLOAD_USAGE] == 1234
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_UPLOAD_USAGE] == 5678
    assert (
        watched_state.attributes[ATTR_WATCHED_DEVICE_LAST_ACTIVE]
        == datetime.fromtimestamp(1774287984.272, UTC).isoformat()
    )


async def test_watched_device_binary_sensor_is_unavailable_when_host_missing(
    hass: HomeAssistant,
) -> None:
    """Test a configured watched MAC remains as an unavailable entity when absent."""
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
        options={CONF_WATCHED_DEVICES: ["AA:BB:CC:DD:EE:FF"]},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    watched_state = _binary_sensor_state_for_unique_suffix(
        hass, "_AA:BB:CC:DD:EE:FF_binary_sensor"
    )

    assert watched_state is not None
    assert watched_state.name is not None
    assert "AA:BB:CC:DD:EE:FF" in watched_state.name
    assert watched_state.state == STATE_UNAVAILABLE


async def test_watched_device_binary_sensor_uses_recent_activity_window(
    hass: HomeAssistant,
) -> None:
    """Test watched-device connectivity matches recent-activity online logic."""
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
        options={CONF_WATCHED_DEVICES: ["AA:BB:CC:DD:EE:FF"]},
    )
    entry.add_to_hass(hass)

    snapshot = _snapshot_with_hosts(
        FirewallaHostRuntime(
            mac="AA:BB:CC:DD:EE:FF",
            host_name="Older device",
            ip_address="192.168.200.25",
            group_name=None,
            network_name=None,
            connection_type=None,
            last_active=9_000.0,
            download_bytes=None,
            upload_bytes=None,
            stale=False,
        ),
        FirewallaHostRuntime(
            mac="AA:BB:CC:DD:EE:01",
            host_name="Recent device",
            ip_address="192.168.200.26",
            group_name=None,
            network_name=None,
            connection_type=None,
            last_active=10_000.0,
            download_bytes=None,
            upload_bytes=None,
            stale=False,
        ),
    )

    with (
        patch(
            "custom_components.firewalla_local.managers.host_manager.dt_util.utcnow",
            return_value=datetime.fromtimestamp(10_000.0, UTC),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value={"policyRules": []}),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    watched_state = _binary_sensor_state_for_unique_suffix(
        hass, "_AA:BB:CC:DD:EE:FF_binary_sensor"
    )

    assert watched_state is not None
    assert watched_state.state == STATE_OFF


async def test_watched_device_binary_sensor_name_updates_after_host_rename(
    hass: HomeAssistant,
) -> None:
    """Test watched-device friendly names track app-side renames after refresh."""
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
        options={CONF_WATCHED_DEVICES: ["AA:BB:CC:DD:EE:FF"]},
    )
    entry.add_to_hass(hass)

    initial_snapshot = _snapshot_with_hosts(
        FirewallaHostRuntime(
            mac="AA:BB:CC:DD:EE:FF",
            host_name="Kaden Phone",
            ip_address="192.168.200.25",
            group_name=None,
            network_name=None,
            connection_type=None,
            last_active=None,
            download_bytes=None,
            upload_bytes=None,
            stale=False,
        )
    )
    renamed_snapshot = _snapshot_with_hosts(
        FirewallaHostRuntime(
            mac="AA:BB:CC:DD:EE:FF",
            host_name="Kaden Pixel",
            ip_address="192.168.200.25",
            group_name=None,
            network_name=None,
            connection_type=None,
            last_active=None,
            download_bytes=None,
            upload_bytes=None,
            stale=False,
        )
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=[initial_snapshot, renamed_snapshot],
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        watched_entry = next(
            entity_entry
            for entity_entry in er.async_entries_for_config_entry(
                er.async_get(hass), entry.entry_id
            )
            if entity_entry.unique_id.endswith("_AA:BB:CC:DD:EE:FF_binary_sensor")
        )

        initial_state = hass.states.get(watched_entry.entity_id)
        assert initial_state is not None
        assert initial_state.name is not None
        assert "Kaden Phone" in initial_state.name

        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()

    renamed_state = hass.states.get(watched_entry.entity_id)
    assert renamed_state is not None
    assert renamed_state.name is not None
    assert "Kaden Pixel" in renamed_state.name


async def test_watched_device_binary_sensor_unique_ids_are_entry_scoped(
    hass: HomeAssistant,
) -> None:
    """Test two entries can watch the same MAC without unique-ID collisions."""
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
        options={CONF_WATCHED_DEVICES: ["AA:BB:CC:DD:EE:FF"]},
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
        options={CONF_WATCHED_DEVICES: ["AA:BB:CC:DD:EE:FF"]},
    )
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)

    host = FirewallaHostRuntime(
        mac="AA:BB:CC:DD:EE:FF",
        host_name="Kaden Phone",
        ip_address="192.168.200.25",
        group_name=None,
        network_name=None,
        connection_type=None,
        last_active=None,
        download_bytes=None,
        upload_bytes=None,
        stale=True,
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=(_snapshot_with_hosts(host), _snapshot_with_hosts(host)),
        ),
    ):
        assert await hass.config_entries.async_setup(first_entry.entry_id)
        if second_entry.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(second_entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    watched_entries = [
        entity_entry
        for entity_entry in (
            er.async_entries_for_config_entry(registry, first_entry.entry_id)
            + er.async_entries_for_config_entry(registry, second_entry.entry_id)
        )
        if entity_entry.entity_id.startswith("binary_sensor.")
        and not entity_entry.unique_id.endswith("_system_status_binary_sensor")
    ]

    assert len(watched_entries) == 2
    assert len({entity_entry.unique_id for entity_entry in watched_entries}) == 2
    assert {
        hass.states.get(entity_entry.entity_id).state
        for entity_entry in watched_entries
    } == {STATE_OFF}
