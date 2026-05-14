"""Tests for the Firewalla Local device tracker platform."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import (
    ATTR_PURPOSE,
    ATTR_WATCHED_DEVICE_CONNECTION_TYPE,
    ATTR_WATCHED_DEVICE_DEVICE_GROUP,
    ATTR_WATCHED_DEVICE_IP_ADDRESS,
    ATTR_WATCHED_DEVICE_LAST_ACTIVE,
    ATTR_WATCHED_DEVICE_NETWORK_NAME,
    CONF_AID,
    CONF_DEVICE_TRACKER_AWAY_WINDOW,
    CONF_DEVICE_TRACKERS,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
    DOMAIN,
    TRANS_KEY_PURPOSE_DEVICE_TRACKER_PRESENCE,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaHostRuntime,
    FirewallaRuntimeSnapshot,
)

_PATCHED_NOW = datetime(2026, 3, 22, 17, 10, tzinfo=UTC)


def _device_tracker_registry_entry(hass: HomeAssistant, entry_id: str):
    """Return the single device-tracker registry entry for one config entry."""
    return next(
        entity_entry
        for entity_entry in er.async_entries_for_config_entry(
            er.async_get(hass), entry_id
        )
        if entity_entry.domain == "device_tracker"
    )


def _tracked_client_device(
    hass: HomeAssistant, entry, mac: str
) -> dr.DeviceEntry | None:
    """Return the tracked-client device for one selected MAC."""
    return dr.async_get(hass).async_get_device(
        identifiers={
            entry.runtime_data.integration_manager.build_tracked_client_device_identifier(
                mac
            )
        }
    )


def _device_tracker_state_for_unique_suffix(hass: HomeAssistant, unique_suffix: str):
    """Return the device-tracker state matching one unique-ID suffix."""
    entity_entry = next(
        entry
        for entry in er.async_get(hass).entities.values()
        if entry.domain == "device_tracker" and entry.unique_id.endswith(unique_suffix)
    )
    state = hass.states.get(entity_entry.entity_id)
    assert state is not None
    return state


def _runtime_payload() -> dict[str, object]:
    """Return a minimal init payload for setup tests."""
    return {"policyRules": []}


def _snapshot_with_hosts(*hosts: FirewallaHostRuntime) -> FirewallaRuntimeSnapshot:
    """Return a runtime snapshot with the requested hosts."""
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


async def test_device_tracker_exposes_state_and_attributes(
    hass: HomeAssistant,
) -> None:
    """Test a selected host becomes a router-backed device tracker."""
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
            CONF_DEVICE_TRACKERS: ["AA:BB:CC:DD:EE:FF"],
            CONF_DEVICE_TRACKER_AWAY_WINDOW: 15,
        },
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
            last_active=1774285600.0,
            download_bytes=1234,
            upload_bytes=5678,
            stale=False,
        )
    )

    with (
        patch(
            "custom_components.firewalla_local.managers.host_manager.dt_util.utcnow",
            return_value=_PATCHED_NOW,
        ),
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

    tracker_state = _device_tracker_state_for_unique_suffix(
        hass, "_AA:BB:CC:DD:EE:FF_device_tracker"
    )
    tracker_entry = _device_tracker_registry_entry(hass, entry.entry_id)
    client_device = _tracked_client_device(hass, entry, "AA:BB:CC:DD:EE:FF")
    router_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "license-123")}
    )

    assert client_device is not None
    assert router_device is not None
    assert tracker_entry.device_id == client_device.id
    assert client_device.name == "Kaden Phone"
    assert client_device.via_device_id == router_device.id
    assert tracker_state.name is not None
    assert tracker_state.name == "Kaden Phone Presence"
    assert tracker_entry.entity_id == "device_tracker.kaden_phone_presence"
    assert tracker_state.state == STATE_HOME
    assert (
        tracker_state.attributes[ATTR_PURPOSE]
        == TRANS_KEY_PURPOSE_DEVICE_TRACKER_PRESENCE
    )
    assert tracker_state.attributes[ATTR_WATCHED_DEVICE_IP_ADDRESS] == "192.168.200.25"
    assert tracker_state.attributes[ATTR_WATCHED_DEVICE_DEVICE_GROUP] == "KADEN"
    assert tracker_state.attributes[ATTR_WATCHED_DEVICE_NETWORK_NAME] == "VLAN10 CORE"
    assert tracker_state.attributes[ATTR_WATCHED_DEVICE_CONNECTION_TYPE] == "phone"
    assert (
        tracker_state.attributes[ATTR_WATCHED_DEVICE_LAST_ACTIVE]
        == datetime.fromtimestamp(1774285600.0, UTC).isoformat()
    )
    assert tracker_state.attributes["source_type"] == "router"


async def test_device_tracker_is_unavailable_when_host_missing(
    hass: HomeAssistant,
) -> None:
    """Test a configured device tracker remains unavailable when its host is absent."""
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
            CONF_DEVICE_TRACKERS: ["AA:BB:CC:DD:EE:FF"],
            CONF_DEVICE_TRACKER_AWAY_WINDOW: 15,
        },
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

    tracker_state = _device_tracker_state_for_unique_suffix(
        hass, "_AA:BB:CC:DD:EE:FF_device_tracker"
    )
    client_device = _tracked_client_device(hass, entry, "AA:BB:CC:DD:EE:FF")

    assert client_device is not None
    assert client_device.name == "Client aa:bb:cc:dd:ee:ff"
    assert tracker_state.name is not None
    assert tracker_state.name == "Client aa:bb:cc:dd:ee:ff Presence"
    assert tracker_state.state == STATE_UNAVAILABLE


async def test_device_tracker_uses_recent_activity_window(
    hass: HomeAssistant,
) -> None:
    """Test device-tracker state uses its own away window from current time."""
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
            CONF_DEVICE_TRACKERS: ["AA:BB:CC:DD:EE:FF"],
            CONF_DEVICE_TRACKER_AWAY_WINDOW: 15,
        },
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
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    tracker_state = _device_tracker_state_for_unique_suffix(
        hass, "_AA:BB:CC:DD:EE:FF_device_tracker"
    )

    assert tracker_state.state == STATE_NOT_HOME


async def test_device_tracker_name_updates_after_host_rename(
    hass: HomeAssistant,
) -> None:
    """Test device-tracker friendly names track app-side renames after refresh."""
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
            CONF_DEVICE_TRACKERS: ["AA:BB:CC:DD:EE:FF"],
            CONF_DEVICE_TRACKER_AWAY_WINDOW: 15,
        },
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
            "custom_components.firewalla_local.managers.host_manager.dt_util.utcnow",
            return_value=_PATCHED_NOW,
        ),
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

        tracker_entry = _device_tracker_registry_entry(hass, entry.entry_id)
        client_device = _tracked_client_device(hass, entry, "AA:BB:CC:DD:EE:FF")

        initial_state = hass.states.get(tracker_entry.entity_id)
        assert initial_state is not None
        assert initial_state.name is not None
        assert initial_state.name == "Kaden Phone Presence"
        assert client_device is not None
        assert client_device.name == "Kaden Phone"

        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()

    renamed_state = hass.states.get(tracker_entry.entity_id)
    renamed_device = _tracked_client_device(hass, entry, "AA:BB:CC:DD:EE:FF")
    assert renamed_state is not None
    assert renamed_state.name is not None
    assert renamed_state.name == "Kaden Pixel Presence"
    assert renamed_device is not None
    assert renamed_device.name == "Kaden Pixel"


async def test_device_tracker_unique_ids_are_entry_scoped(
    hass: HomeAssistant,
) -> None:
    """Test two entries can track the same MAC without unique-ID collisions."""
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
        options={
            CONF_DEVICE_TRACKERS: ["AA:BB:CC:DD:EE:FF"],
            CONF_DEVICE_TRACKER_AWAY_WINDOW: 15,
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
        options={CONF_DEVICE_TRACKERS: ["AA:BB:CC:DD:EE:FF"]},
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
    tracker_entries = [
        entity_entry
        for entity_entry in (
            er.async_entries_for_config_entry(registry, first_entry.entry_id)
            + er.async_entries_for_config_entry(registry, second_entry.entry_id)
        )
        if entity_entry.entity_id.startswith("device_tracker.")
    ]
    device_registry = dr.async_get(hass)
    first_client_device = _tracked_client_device(hass, first_entry, "AA:BB:CC:DD:EE:FF")
    second_client_device = _tracked_client_device(
        hass, second_entry, "AA:BB:CC:DD:EE:FF"
    )
    first_router_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "license-123")}
    )
    second_router_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "license-456")}
    )

    assert len(tracker_entries) == 2
    assert len({entity_entry.unique_id for entity_entry in tracker_entries}) == 2
    assert first_client_device is not None
    assert second_client_device is not None
    assert first_router_device is not None
    assert second_router_device is not None
    assert first_client_device.id != second_client_device.id
    assert first_client_device.via_device_id == first_router_device.id
    assert second_client_device.via_device_id == second_router_device.id
    assert {
        hass.states.get(entity_entry.entity_id).state
        for entity_entry in tracker_entries
    } == {STATE_NOT_HOME}
