"""Tests for Firewalla Local binary sensors."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import (
    ATTR_AP_CHANNEL_2G,
    ATTR_AP_CHANNEL_5G,
    ATTR_AP_CLIENT_COUNT,
    ATTR_AP_COUNTRY,
    ATTR_AP_DISABLE_ACL,
    ATTR_AP_LED,
    ATTR_AP_MESH_MODE,
    ATTR_AP_MODEL,
    ATTR_AP_NAME,
    ATTR_AP_PAUSE_WIFI,
    ATTR_AP_TIMEZONE,
    ATTR_AP_TX_POWER,
    ATTR_INTEGRATION,
    ATTR_NETWORK_BLOCK_ICMP,
    ATTR_NETWORK_DHCP,
    ATTR_NETWORK_DNS_SERVERS,
    ATTR_NETWORK_ENABLED,
    ATTR_NETWORK_GATEWAY,
    ATTR_NETWORK_HOST_COUNT,
    ATTR_NETWORK_IPV4_ADDRESSES,
    ATTR_NETWORK_IPV4_SUBNETS,
    ATTR_NETWORK_KIND,
    ATTR_NETWORK_MDNS_RELAY,
    ATTR_NETWORK_PORTS,
    ATTR_NETWORK_SSDP_RELAY,
    ATTR_NETWORK_TOP_TALKERS,
    ATTR_NETWORK_USAGE,
    ATTR_NETWORK_VLAN_ID,
    ATTR_PURPOSE,
    ATTR_SSID_BAND,
    ATTR_SSID_ENCRYPTION,
    ATTR_SSID_INTERFACE,
    ATTR_SSID_NAME,
    ATTR_SSID_PAUSED,
    ATTR_SSID_VLAN_ID,
    ATTR_SSID_WPA3,
    ATTR_SYSTEM_BLUETOOTH_MAC,
    ATTR_SYSTEM_PORTS,
    ATTR_SYSTEM_TIMEZONE,
    ATTR_SYSTEM_WAN_ROUTING,
    ATTR_WAN_FAILOVER_ACTIVE_WAN,
    ATTR_WAN_FAILOVER_MODE,
    ATTR_WAN_FAILOVER_PRIMARY,
    ATTR_WAN_HEALTH,
    ATTR_WAN_IN_USE,
    ATTR_WAN_READY,
    ATTR_WAN_ROLE,
    ATTR_WATCHED_DEVICE_CONNECTION_TYPE,
    ATTR_WATCHED_DEVICE_DOWNLOAD_USAGE,
    ATTR_WATCHED_DEVICE_HOST_GROUP,
    ATTR_WATCHED_DEVICE_IP_ADDRESS,
    ATTR_WATCHED_DEVICE_LAST_ACTIVE,
    ATTR_WATCHED_DEVICE_LAST_ACTIVE_TIMESTAMP,
    ATTR_WATCHED_DEVICE_NETWORK_NAME,
    ATTR_WATCHED_DEVICE_TOPOLOGY_CONNECTION_TYPE,
    ATTR_WATCHED_DEVICE_UPLOAD_USAGE,
    ATTR_WATCHED_DEVICE_WIFI_AP,
    ATTR_WATCHED_DEVICE_WIFI_BAND,
    ATTR_WATCHED_DEVICE_WIFI_RSSI,
    ATTR_WATCHED_DEVICE_WIFI_SSID,
    CONF_AID,
    CONF_EID,
    CONF_ENABLE_NETWORK_ENTITIES,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
    CONF_WATCHED_DEVICES,
    DOMAIN,
    TRANS_KEY_PURPOSE_WATCHED_DEVICE_CONNECTIVITY,
)
from custom_components.firewalla_local.helpers.device_registry import (
    async_get_entry_device,
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


def _box_host() -> FirewallaHostRuntime:
    """Return the Firewalla box's own host record, always present in snapshots."""
    return FirewallaHostRuntime(
        mac="AA:BB:CC:DD:EE:00",
        host_name="Firewalla",
        ip_address="192.168.200.1",
        group_name=None,
        network_name=None,
        connection_type=None,
        last_active=None,
        download_bytes=None,
        upload_bytes=None,
        stale=False,
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
    assert watched_state.attributes[ATTR_INTEGRATION] == DOMAIN
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_IP_ADDRESS] == "192.168.200.25"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_HOST_GROUP] == "KADEN"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_NETWORK_NAME] == "VLAN10 CORE"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_CONNECTION_TYPE] == "phone"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_DOWNLOAD_USAGE] == 1234
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_UPLOAD_USAGE] == 5678
    assert (
        watched_state.attributes[ATTR_WATCHED_DEVICE_LAST_ACTIVE]
        == datetime.fromtimestamp(1774287984.272, UTC).isoformat()
    )
    # The epoch twin carries the same instant, so a template can compare times
    # without parsing the date above.
    assert (
        watched_state.attributes[ATTR_WATCHED_DEVICE_LAST_ACTIVE_TIMESTAMP]
        == 1774287984.272
    )
    # Without AP7s there is no AP config, so topology/WiFi attributes are absent.
    assert ATTR_WATCHED_DEVICE_TOPOLOGY_CONNECTION_TYPE not in watched_state.attributes
    assert ATTR_WATCHED_DEVICE_WIFI_SSID not in watched_state.attributes
    assert ATTR_WATCHED_DEVICE_WIFI_BAND not in watched_state.attributes
    assert ATTR_WATCHED_DEVICE_WIFI_RSSI not in watched_state.attributes
    assert ATTR_WATCHED_DEVICE_WIFI_AP not in watched_state.attributes


async def test_watched_device_group_attribute_shows_the_user_for_a_legacy_tag(
    hass: HomeAssistant,
) -> None:
    """A device in a legacy human-named backing tag reports the user's name.

    Before Firewalla's current user model a user *was* a group, so users created
    then still have a backing tag named with a human-readable label. That label
    must never render: the device's group attribute shows the user's name,
    resolved by the tag's `affiliatedTag` linkage rather than by the tag's name.

    This leaves the real normalization in place, so it covers the client through
    to the entity attribute rather than asserting on an injected snapshot.
    """
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
        options={CONF_WATCHED_DEVICES: ["0C:85:E1:B0:1D:1C"]},
    )
    entry.add_to_hass(hass)

    raw_payload: dict[str, object] = {
        "hosts": [
            {
                "mac": "0C:85:E1:B0:1D:1C",
                "name": "Kaden Phone",
                "ip": "192.168.200.25",
                "tags": ["31"],
            }
        ],
        "tags": {
            "31": {"name": "KADEN's Devices", "policy": {"userTags": ["32"]}},
        },
        "userTags": {"32": {"name": "KADENS_DEVICES", "affiliatedTag": "31"}},
        "policyRules": [],
    }

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient."
        "async_get_runtime_init_payload",
        new=AsyncMock(return_value=raw_payload),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    watched_state = _binary_sensor_state_for_unique_suffix(
        hass, "_0C:85:E1:B0:1D:1C_binary_sensor"
    )

    assert watched_state is not None
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_HOST_GROUP] == "KADENS_DEVICES"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_HOST_GROUP] != (
        "KADEN's Devices"
    )


async def test_watched_device_binary_sensor_exposes_wifi_attributes(
    hass: HomeAssistant,
) -> None:
    """Test the watched-device sensor surfaces wireless connection attributes."""
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

    payload = _runtime_payload()
    payload["networkConfig"] = {
        "apc": {
            "assets": {
                "20:6D:31:71:1D:D0": {
                    "sysConfig": {"name": "Main Floor"},
                    "model": "fwap-D",
                }
            }
        }
    }
    payload["switchTopology"] = {
        "info": {
            "tree": [
                {
                    "mac": "AA:BB:CC:DD:EE:00",
                    "type": "box",
                    "children": [
                        {
                            "mac": "20:6D:31:71:1D:D0",
                            "name": "Main Floor",
                            "type": "ap",
                            "connectionType": "wired",
                            "children": [
                                {
                                    "mac": "AA:BB:CC:DD:EE:FF",
                                    "name": "Kaden Phone",
                                    "type": "device",
                                    "connectionType": "wireless",
                                    "ssid": "Universe",
                                    "band": "5g",
                                    "rssi": -51,
                                    "parent_port": "ath1",
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "errors": [],
    }

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=payload),
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
    assert (
        watched_state.attributes[ATTR_WATCHED_DEVICE_TOPOLOGY_CONNECTION_TYPE]
        == "wireless"
    )
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_WIFI_SSID] == "Universe"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_WIFI_BAND] == "5g"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_WIFI_RSSI] == -51
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_WIFI_AP] == "Main Floor"


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
            return_value=_snapshot_with_hosts(_box_host()),
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
        and not entity_entry.unique_id.endswith(
            (
                "_system_status_binary_sensor",
                "_alarm_active_binary_sensor",
                "_wan_failover_binary_sensor",
            )
        )
    ]

    assert len(watched_entries) == 2
    assert len({entity_entry.unique_id for entity_entry in watched_entries}) == 2
    assert {
        hass.states.get(entity_entry.entity_id).state
        for entity_entry in watched_entries
    } == {STATE_OFF}


def _network_payload() -> dict[str, object]:
    """Return a raw init payload with one VLAN and one VPN network."""
    return {
        "policyRules": [],
        "btMac": "20:6D:31:FC:1C:56",
        "hosts": [
            {
                "mac": "AA:BB:CC:DD:EE:01",
                "intf": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                "macVendor": "Apple",
            },
            {
                "mac": "AA:BB:CC:DD:EE:02",
                "intf": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                "macVendor": "Samsung",
            },
            # The Firewalla box must be excluded from client counts.
            {
                "mac": "20:6D:31:01:5E:DD",
                "intf": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                "macVendor": "FIREWALLA INC",
            },
        ],
        "nicStates": {
            "eth0": {
                "carrier": "1",
                "speed": "1000",
                "address": "20:6D:31:01:5E:DD",
            },
            "eth1": {"carrier": "0", "speed": "-1"},
        },
        "networkConfig": {
            "interface": {
                "phy": {
                    "eth0": {
                        "meta": {
                            "name": "WAN-ONE",
                            "type": "wan",
                            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
                        },
                        "enabled": True,
                    }
                },
                "vlan": {
                    "bond0.10": {
                        "meta": {
                            "name": "VLAN10 CORE",
                            "type": "lan",
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        },
                        "vid": 10,
                        "enabled": True,
                    }
                },
                "amneziawg": {
                    "awg0": {
                        "meta": {
                            "name": "AmneziaWG",
                            "type": "lan",
                            "uuid": "876e3889-0199-45f3-aeb1-a49c3f38e96e",
                        },
                        "enabled": True,
                    }
                },
            },
            "dhcp": {
                "bond0.10": {
                    "gateway": "192.168.10.1",
                    "subnetMask": "255.255.255.0",
                    "lease": 86400,
                    "range": {"from": "192.168.10.110", "to": "192.168.10.126"},
                    "nameservers": ["192.168.10.1"],
                    "searchDomain": ["int.ccpk.us"],
                }
            },
            "mdns_reflector": {"bond0.10": {"enabled": True}},
            "icmp": {"bond0.10": {"echoRequest": False}},
        },
        "networkProfiles": {
            "95169e6a-a7c9-4d6a-8e83-6061b4812bf2": {
                "intf": "bond0.10",
                "ipv4": "192.168.10.1",
                "ipv4Subnet": "192.168.10.0/24",
                "ipv4Subnets": ["192.168.10.0/24"],
                "gateway": "192.168.10.1",
                "dns": ["192.168.10.1"],
            },
            "876e3889-0199-45f3-aeb1-a49c3f38e96e": {
                "intf": "awg0",
                "ipv4": "10.190.68.1",
            },
        },
        "monthlyDataUsageOnWans": {
            "8d5a7f20-2923-49a3-8e2b-338f9428a632": {
                "totalDownload": 2048,
                "totalUpload": 512,
            },
        },
    }


async def test_network_binary_sensor_exposes_state_and_attributes(
    hass: HomeAssistant,
) -> None:
    """Test each unified network becomes a connectivity binary sensor."""
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
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_network_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(_box_host()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(
                side_effect=lambda **kwargs: {
                    "newLast24": {"totalDownload": 100, "totalUpload": 50},
                    "last30": {"totalDownload": 900, "totalUpload": 450},
                }
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    vlan_state = _binary_sensor_state_for_unique_suffix(
        hass, "_network_95169e6a-a7c9-4d6a-8e83-6061b4812bf2_binary_sensor"
    )
    vpn_state = _binary_sensor_state_for_unique_suffix(
        hass, "_network_876e3889-0199-45f3-aeb1-a49c3f38e96e_binary_sensor"
    )
    wan_state = _binary_sensor_state_for_unique_suffix(
        hass, "_network_8d5a7f20-2923-49a3-8e2b-338f9428a632_binary_sensor"
    )

    assert vlan_state is not None
    assert vlan_state.state == STATE_ON
    assert vlan_state.attributes[ATTR_NETWORK_KIND] == "vlan"
    assert vlan_state.attributes[ATTR_NETWORK_VLAN_ID] == 10
    assert vlan_state.attributes[ATTR_NETWORK_ENABLED] is True
    assert vlan_state.attributes[ATTR_NETWORK_IPV4_ADDRESSES] == ["192.168.10.1"]
    assert vlan_state.attributes[ATTR_NETWORK_IPV4_SUBNETS] == ["192.168.10.0/24"]
    assert vlan_state.attributes[ATTR_NETWORK_GATEWAY] == "192.168.10.1"
    # DNS servers are exposed for WAN networks only; a VLAN omits the attribute.
    assert ATTR_NETWORK_DNS_SERVERS not in vlan_state.attributes
    assert vlan_state.attributes[ATTR_NETWORK_MDNS_RELAY] is True
    assert vlan_state.attributes[ATTR_NETWORK_SSDP_RELAY] is False
    assert vlan_state.attributes[ATTR_NETWORK_BLOCK_ICMP] is True
    assert vlan_state.attributes[ATTR_NETWORK_DHCP]["gateway"] == "192.168.10.1"
    assert vlan_state.attributes[ATTR_NETWORK_HOST_COUNT] == 2
    assert vlan_state.attributes[ATTR_NETWORK_USAGE] == {
        "last_24h": {"download_bytes": 100, "upload_bytes": 50},
        "last_60m": {"download_bytes": None, "upload_bytes": None},
        "last_30d": {"download_bytes": 900, "upload_bytes": 450},
        "last_12m": {"download_bytes": None, "upload_bytes": None},
        "monthly": {"download_bytes": None, "upload_bytes": None},
    }

    assert vpn_state is not None
    assert vpn_state.state == STATE_ON
    assert vpn_state.attributes[ATTR_NETWORK_KIND] == "vpn"
    assert vpn_state.attributes[ATTR_NETWORK_PORTS] == []
    # A network without a VLAN omits the vlan_id attribute (no "unknown").
    assert ATTR_NETWORK_VLAN_ID not in vpn_state.attributes

    assert wan_state is not None
    assert wan_state.state == STATE_ON
    assert wan_state.attributes[ATTR_NETWORK_KIND] == "wan"
    assert wan_state.attributes[ATTR_NETWORK_PORTS] == ["eth0"]
    # WAN keeps the dns_servers attribute (empty here as the fixture has none).
    assert wan_state.attributes[ATTR_NETWORK_DNS_SERVERS] == []
    # WAN has no host assignment, so no talkers can be ranked.
    assert wan_state.attributes[ATTR_NETWORK_TOP_TALKERS] == []
    assert vlan_state.attributes[ATTR_NETWORK_TOP_TALKERS] == []
    assert wan_state.attributes[ATTR_NETWORK_USAGE] == {
        "last_24h": {"download_bytes": None, "upload_bytes": None},
        "last_60m": {"download_bytes": None, "upload_bytes": None},
        "last_30d": {"download_bytes": None, "upload_bytes": None},
        "last_12m": {"download_bytes": None, "upload_bytes": None},
        "monthly": {"download_bytes": 2048, "upload_bytes": 512},
    }


async def test_network_binary_sensor_exposes_ranked_top_talkers(
    hass: HomeAssistant,
) -> None:
    """Test the network attribute ranks up/down talkers and skips idle hosts."""
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
    )
    entry.add_to_hass(hass)
    vlan_uuid = "95169e6a-a7c9-4d6a-8e83-6061b4812bf2"

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_network_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(
                _box_host(),
                FirewallaHostRuntime(
                    mac="AA:00:00:00:00:01",
                    host_name="nas1",
                    ip_address="192.168.10.5",
                    group_name=None,
                    network_name="VLAN10 CORE",
                    connection_type=None,
                    last_active=None,
                    download_bytes=7_600_000_000,
                    upload_bytes=563_000_000,
                    stale=False,
                    network_uuid=vlan_uuid,
                ),
                FirewallaHostRuntime(
                    mac="AA:00:00:00:00:02",
                    host_name="clsrazer",
                    ip_address="192.168.10.6",
                    group_name=None,
                    network_name="VLAN10 CORE",
                    connection_type=None,
                    last_active=None,
                    download_bytes=1_017_664_978,
                    upload_bytes=216_289_236,
                    stale=False,
                    network_uuid=vlan_uuid,
                ),
                # An idle host must never appear in the ranked list.
                FirewallaHostRuntime(
                    mac="AA:00:00:00:00:03",
                    host_name="idle-host",
                    ip_address="192.168.10.7",
                    group_name=None,
                    network_name="VLAN10 CORE",
                    connection_type=None,
                    last_active=None,
                    download_bytes=0,
                    upload_bytes=0,
                    stale=False,
                    network_uuid=vlan_uuid,
                ),
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    vlan_state = _binary_sensor_state_for_unique_suffix(
        hass, f"_network_{vlan_uuid}_binary_sensor"
    )

    assert vlan_state is not None
    assert vlan_state.attributes[ATTR_NETWORK_TOP_TALKERS] == [
        {
            "host_name": "nas1",
            "download_bytes": 7_600_000_000,
            "upload_bytes": 563_000_000,
        },
        {
            "host_name": "clsrazer",
            "download_bytes": 1_017_664_978,
            "upload_bytes": 216_289_236,
        },
    ]


async def test_network_binary_sensor_name_uses_kind_and_name(
    hass: HomeAssistant,
) -> None:
    """Test the network binary sensor translation placeholders."""
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
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_network_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(_box_host()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value={}),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    vlan_state = _binary_sensor_state_for_unique_suffix(
        hass, "_network_95169e6a-a7c9-4d6a-8e83-6061b4812bf2_binary_sensor"
    )

    assert vlan_state.name is not None
    assert vlan_state.name == "Firewalla VLAN VLAN10 CORE Status"


async def test_system_status_exposes_ports_attribute(
    hass: HomeAssistant,
) -> None:
    """Test the System Status binary sensor reports per-port link state."""
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
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_network_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(_box_host()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    system_state = _binary_sensor_state_for_unique_suffix(
        hass, "_system_status_binary_sensor"
    )

    assert system_state is not None
    assert system_state.attributes[ATTR_SYSTEM_PORTS] == {
        "eth0": {
            "link": "up",
            "speed_mbps": 1000,
            "mac": "20:6D:31:01:5E:DD",
        },
        "eth1": {"link": "down", "speed_mbps": None, "mac": None},
    }
    assert system_state.attributes[ATTR_SYSTEM_BLUETOOTH_MAC] == "20:6D:31:FC:1C:56"
    assert system_state.attributes[ATTR_SYSTEM_TIMEZONE] is None


async def test_system_status_exposes_the_failover_routing(
    hass: HomeAssistant,
) -> None:
    """Test the System Status sensor reports the failover mode and its settings."""
    await _setup_routing_entry(
        hass,
        routing={
            "type": "primary_standby",
            "viaIntf": "eth0",
            "viaIntf2": "eth1",
            "failback": True,
        },
    )

    system_state = _binary_sensor_state_for_unique_suffix(
        hass, "_system_status_binary_sensor"
    )

    assert system_state.attributes[ATTR_SYSTEM_WAN_ROUTING] == {
        "mode": "primary_standby",
        "primary": "WAN-ONE",
        "standby": "WAN-TWO",
        "failback": True,
    }


async def test_system_status_exposes_the_load_balance_share(
    hass: HomeAssistant,
) -> None:
    """Test load balance reports the declared share and no primary.

    Captured shape from a live box: ``nextHops`` replaces ``viaIntf``/``viaIntf2``
    entirely, so publishing a primary here would invent one.
    """
    await _setup_routing_entry(
        hass,
        routing={
            "type": "load_balance",
            "nextHops": [
                {"viaIntf": "eth0", "weight": 60},
                {"viaIntf": "eth1", "weight": 40},
            ],
        },
    )

    system_state = _binary_sensor_state_for_unique_suffix(
        hass, "_system_status_binary_sensor"
    )

    assert system_state.attributes[ATTR_SYSTEM_WAN_ROUTING] == {
        "mode": "load_balance",
        "traffic_share_percent": {"WAN-ONE": 60, "WAN-TWO": 40},
    }


async def test_system_status_reports_no_routing_when_the_box_states_no_preference(
    hass: HomeAssistant,
) -> None:
    """Test a box with no routing block reports ``None`` rather than a mode.

    ``None`` and not an invented ``single``: the box states no preference, and a
    guessed mode would be indistinguishable from a stated one.
    """
    await _setup_routing_entry(hass, routing=None)

    system_state = _binary_sensor_state_for_unique_suffix(
        hass, "_system_status_binary_sensor"
    )

    assert system_state.attributes[ATTR_SYSTEM_WAN_ROUTING] is None


async def test_wan_network_sensors_report_failover_roles(
    hass: HomeAssistant,
) -> None:
    """Test each WAN carries its role and link state in failover."""
    await _setup_routing_entry(
        hass,
        routing={
            "type": "primary_standby",
            "viaIntf": "eth0",
            "viaIntf2": "eth1",
            "failback": True,
        },
        wan_profiles={
            "8d5a7f20-2923-49a3-8e2b-338f9428a632": {"active": True, "ready": True},
            "wan-two": {"active": False, "ready": True},
        },
    )

    primary = _network_state_for_uuid(hass, "8d5a7f20-2923-49a3-8e2b-338f9428a632")
    standby = _network_state_for_uuid(hass, "wan-two")

    assert primary.attributes[ATTR_WAN_ROLE] == "primary"
    assert primary.attributes[ATTR_WAN_IN_USE] is True
    assert primary.attributes[ATTR_WAN_READY] is True
    # A standby is ready while idle, which is healthy rather than a fault.
    assert standby.attributes[ATTR_WAN_ROLE] == "standby"
    assert standby.attributes[ATTR_WAN_IN_USE] is False
    assert standby.attributes[ATTR_WAN_READY] is True


async def test_wan_network_sensors_report_no_role_in_load_balance(
    hass: HomeAssistant,
) -> None:
    """Test load balance leaves the role off rather than electing a primary.

    Both WANs are equal members of the routing set, so both report themselves in
    use and neither carries a role.
    """
    await _setup_routing_entry(
        hass,
        routing={
            "type": "load_balance",
            "nextHops": [
                {"viaIntf": "eth0", "weight": 60},
                {"viaIntf": "eth1", "weight": 40},
            ],
        },
        wan_profiles={
            "8d5a7f20-2923-49a3-8e2b-338f9428a632": {"active": True, "ready": True},
            "wan-two": {"active": True, "ready": True},
        },
    )

    first = _network_state_for_uuid(hass, "8d5a7f20-2923-49a3-8e2b-338f9428a632")
    second = _network_state_for_uuid(hass, "wan-two")

    # Load balance gives every member the same role rather than no role, so a
    # reader never has to consult the mode to learn how a WAN is being used.
    assert first.attributes[ATTR_WAN_ROLE] == "shared"
    assert second.attributes[ATTR_WAN_ROLE] == "shared"
    assert first.attributes[ATTR_WAN_IN_USE] is True
    assert second.attributes[ATTR_WAN_IN_USE] is True


async def test_lan_network_sensor_carries_no_wan_attributes(
    hass: HomeAssistant,
) -> None:
    """Test routing attributes stay off non-WAN networks."""
    await _setup_routing_entry(
        hass,
        routing={
            "type": "primary_standby",
            "viaIntf": "eth0",
            "viaIntf2": "eth1",
            "failback": True,
        },
    )

    vlan_state = _network_state_for_uuid(hass, "95169e6a-a7c9-4d6a-8e83-6061b4812bf2")

    assert ATTR_WAN_ROLE not in vlan_state.attributes
    assert ATTR_WAN_IN_USE not in vlan_state.attributes
    assert ATTR_WAN_READY not in vlan_state.attributes


async def test_wan_network_sensor_exposes_the_box_health_test(
    hass: HomeAssistant,
) -> None:
    """Test the WAN sensor carries the box's own link health test."""
    await _setup_routing_entry(
        hass,
        routing={
            "type": "primary_standby",
            "viaIntf": "eth0",
            "viaIntf2": "eth1",
            "failback": True,
        },
        wan_profiles={
            "8d5a7f20-2923-49a3-8e2b-338f9428a632": {"active": True, "ready": True},
            "wan-two": {"active": False, "ready": True},
        },
        wan_test_result={
            "ts": 1794159471,
            "wans": {
                "eth0": {
                    "active": True,
                    "carrier": True,
                    "dns": True,
                    "ping": True,
                    "http": {"statusCode": 200},
                    "failures": [],
                },
                "eth1": {
                    "active": True,
                    "carrier": True,
                    "dns": False,
                    "ping": True,
                    "http": {"statusCode": None},
                    "failures": ["dns"],
                    "recentDownTime": 1793248443,
                },
            },
        },
    )

    primary = _network_state_for_uuid(hass, "8d5a7f20-2923-49a3-8e2b-338f9428a632")
    standby = _network_state_for_uuid(hass, "wan-two")

    assert primary.attributes[ATTR_WAN_HEALTH]["carrier"] is True
    assert primary.attributes[ATTR_WAN_HEALTH]["http_status"] == 200
    assert primary.attributes[ATTR_WAN_HEALTH]["failures"] == []
    # A standby whose DNS probe fails still reports ready from the profile, which
    # is why the health block exists: readiness alone would hide the failure.
    assert standby.attributes[ATTR_WAN_READY] is True
    assert standby.attributes[ATTR_WAN_HEALTH]["dns"] is False
    assert standby.attributes[ATTR_WAN_HEALTH]["failures"] == ["dns"]
    assert standby.attributes[ATTR_WAN_HEALTH]["recent_down_at_timestamp"] == (
        1793248443
    )


async def test_failover_sensor_is_off_while_the_primary_carries_traffic(
    hass: HomeAssistant,
) -> None:
    """Test the failover sensor is off while the configured primary is in use."""
    await _setup_routing_entry(
        hass,
        routing={
            "type": "primary_standby",
            "viaIntf": "eth0",
            "viaIntf2": "eth1",
            "failback": True,
        },
        active_interface="eth0",
    )

    state = _binary_sensor_state_for_unique_suffix(hass, "_wan_failover_binary_sensor")

    assert state.state == STATE_OFF
    assert state.attributes[ATTR_WAN_FAILOVER_PRIMARY] == "WAN-ONE"
    assert state.attributes[ATTR_WAN_FAILOVER_ACTIVE_WAN] == "WAN-ONE"
    assert state.attributes[ATTR_WAN_FAILOVER_MODE] == "primary_standby"


async def test_failover_sensor_is_on_while_the_standby_carries_traffic(
    hass: HomeAssistant,
) -> None:
    """Test the failover sensor reports a failover when the standby is in use."""
    await _setup_routing_entry(
        hass,
        routing={
            "type": "primary_standby",
            "viaIntf": "eth0",
            "viaIntf2": "eth1",
            "failback": True,
        },
        active_interface="eth1",
    )

    state = _binary_sensor_state_for_unique_suffix(hass, "_wan_failover_binary_sensor")

    assert state.state == STATE_ON
    assert state.attributes[ATTR_WAN_FAILOVER_PRIMARY] == "WAN-ONE"
    assert state.attributes[ATTR_WAN_FAILOVER_ACTIVE_WAN] == "WAN-TWO"


async def test_failover_sensor_is_unavailable_outside_failover_mode(
    hass: HomeAssistant,
) -> None:
    """Test load balance has no failover to report, so the entity is unavailable."""
    await _setup_routing_entry(
        hass,
        routing={
            "type": "load_balance",
            "nextHops": [
                {"viaIntf": "eth0", "weight": 50},
                {"viaIntf": "eth1", "weight": 50},
            ],
        },
    )

    state = _binary_sensor_state_for_unique_suffix(hass, "_wan_failover_binary_sensor")

    assert state.state == STATE_UNAVAILABLE


def _network_state_for_uuid(hass: HomeAssistant, network_uuid: str):
    """Return the per-network binary sensor for one network uuid."""
    return _binary_sensor_state_for_unique_suffix(
        hass, f"_network_{network_uuid}_binary_sensor"
    )


async def _setup_routing_entry(
    hass: HomeAssistant,
    *,
    routing: dict[str, object] | None,
    wan_profiles: dict[str, dict[str, object]] | None = None,
    wan_test_result: dict[str, object] | None = None,
    active_interface: str | None = None,
) -> MockConfigEntry:
    """Set up one entry whose payload declares two WANs and the given routing."""
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
    )
    entry.add_to_hass(hass)

    payload = _network_payload()
    network_config = payload["networkConfig"]
    assert isinstance(network_config, dict)
    network_config["interface"]["phy"]["eth1"] = {
        "meta": {"name": "WAN-TWO", "type": "wan", "uuid": "wan-two"},
        "enabled": True,
    }
    profiles = payload["networkProfiles"]
    assert isinstance(profiles, dict)
    profiles["wan-two"] = {"intf": "eth1", "ipv4": "192.168.12.237", "type": "wan"}
    for profile_uuid, wan_state in (wan_profiles or {}).items():
        profiles[profile_uuid] = {
            **profiles.get(profile_uuid, {}),
            "type": "wan",
            **wan_state,
        }
    if routing is not None:
        network_config["routing"] = {"global": {"default": routing}}
    if wan_test_result is not None:
        payload["wanTestResult"] = wan_test_result
    if active_interface is not None:
        payload["network"] = {
            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632"
            if active_interface == "eth0"
            else "wan-two",
            "name": active_interface,
            "desc": "WAN-ONE" if active_interface == "eth0" else "WAN-TWO",
            "type": "wan",
            "active": True,
            "ready": True,
            "ip_address": "23.245.207.179",
        }

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=payload),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(_box_host()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _count_network_binary_sensors(hass: HomeAssistant) -> int:
    """Return the number of per-network binary-sensor registry entries."""
    return sum(
        1
        for entity_entry in er.async_get(hass).entities.values()
        if entity_entry.platform == DOMAIN
        and entity_entry.domain == "binary_sensor"
        and "_network_" in entity_entry.unique_id
    )


async def _setup_network_entities_entry(
    hass: HomeAssistant,
    *,
    enable_network_entities: bool,
) -> MockConfigEntry:
    """Set up one entry with the network-entities toggle set accordingly."""
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
        options={CONF_ENABLE_NETWORK_ENTITIES: enable_network_entities},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_network_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(_box_host()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value={}),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_network_entities_created_when_toggle_enabled(
    hass: HomeAssistant,
) -> None:
    """Test network binary sensors are created when the toggle is on."""
    await _setup_network_entities_entry(hass, enable_network_entities=True)

    assert _count_network_binary_sensors(hass) == 3


async def test_network_entities_not_created_when_toggle_disabled(
    hass: HomeAssistant,
) -> None:
    """Test network binary sensors are not created when the toggle is off."""
    await _setup_network_entities_entry(hass, enable_network_entities=False)

    assert _count_network_binary_sensors(hass) == 0


async def test_reconcile_network_entities_removes_stale_entries(
    hass: HomeAssistant,
) -> None:
    """Test reconcile removes network entities no longer expected (toggle off)."""
    entry = await _setup_network_entities_entry(hass, enable_network_entities=True)

    assert _count_network_binary_sensors(hass) == 3

    # Simulate the toggle being switched off: reconcile with no expected networks.
    await entry.runtime_data.integration_manager.async_reconcile_network_entities(())

    assert _count_network_binary_sensors(hass) == 0


def _ssid_runtime_payload() -> dict[str, object]:
    """Return a raw init payload with an AP7 wireless config."""
    return {
        "policyRules": [],
        "networkConfig": {
            "apc": {
                "assets": {
                    "20:6D:31:71:1D:D0": {
                        "sysConfig": {"name": "Main Floor"},
                        "model": "fwap-D",
                    }
                },
                "assets_template": {
                    "ap_default": {
                        "wifiNetworks": [
                            {
                                "intf": "br1",
                                "vlan": 100,
                                "ssidProfiles": [
                                    "f185dc47-2730-48a8-844c-b57aa31af4ba"
                                ],
                            }
                        ]
                    }
                },
                "profile": {
                    "f185dc47-2730-48a8-844c-b57aa31af4ba": {
                        "ssid": "Castle Guest",
                        "band": "2.4g+5g+6g",
                        "encryption": "psk2+ccmp",
                        "wpa3": False,
                    },
                },
            }
        },
    }


async def test_ssid_binary_sensor_exposes_state_and_attributes(
    hass: HomeAssistant,
) -> None:
    """Test the SSID binary sensor surfaces wireless network state."""
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
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_ssid_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(_box_host()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.firewalla_ssid_castle_guest_status")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes[ATTR_SSID_NAME] == "Castle Guest"
    assert state.attributes[ATTR_SSID_BAND] == "2.4g+5g+6g"
    assert state.attributes[ATTR_SSID_ENCRYPTION] == "psk2+ccmp"
    assert state.attributes[ATTR_SSID_WPA3] is False
    assert state.attributes[ATTR_SSID_VLAN_ID] == 100
    assert state.attributes[ATTR_SSID_INTERFACE] == "br1"
    assert state.attributes[ATTR_SSID_PAUSED] is False


async def test_ssid_binary_sensor_reflects_paused_state(
    hass: HomeAssistant,
) -> None:
    """Test the SSID binary sensor is off when the SSID is paused."""
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
        options={},
    )
    entry.add_to_hass(hass)

    payload = _ssid_runtime_payload()
    payload["networkConfig"]["apc"]["profile"]["f185dc47-2730-48a8-844c-b57aa31af4ba"][
        "paused"
    ] = True

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=payload),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(_box_host()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.firewalla_ssid_castle_guest_status")
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_SSID_PAUSED] is True


def _ap_runtime_payload() -> dict[str, object]:
    """Return a raw init payload with an AP7 access point."""
    return {
        "policyRules": [],
        "networkConfig": {
            "apc": {
                "assets": {
                    "20:6D:31:71:1D:D0": {
                        "sysConfig": {
                            "name": "Main Floor",
                            "channel": {"5g": "149", "2g": "1"},
                            "led": "off",
                            "txPower": "auto",
                            "country": "US",
                            "meshMode": "mesh",
                            "timezone": "America/New_York",
                            "pauseWifi": False,
                            "disableAcl": False,
                        },
                        "model": "fwap-D",
                    }
                },
            }
        },
        "switchTopology": {
            "info": {
                "tree": [
                    {
                        "mac": "AA:BB:CC:DD:EE:00",
                        "type": "box",
                        "children": [
                            {
                                "mac": "20:6D:31:71:1D:D0",
                                "name": "Main Floor",
                                "type": "ap",
                                "children": [
                                    {
                                        "mac": "AA:BB:CC:DD:EE:FF",
                                        "type": "device",
                                        "connectionType": "wireless",
                                    },
                                    {
                                        "mac": "AA:BB:CC:DD:EE:01",
                                        "type": "device",
                                        "connectionType": "wireless",
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        },
    }


async def test_ap_status_binary_sensor_exposes_state_and_attributes(
    hass: HomeAssistant,
) -> None:
    """Test the AP status binary sensor surfaces access-point state."""
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
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_ap_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(_box_host()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.main_floor_ap_status")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes[ATTR_AP_NAME] == "Main Floor"
    assert state.attributes[ATTR_AP_MODEL] == "fwap-D"
    assert state.attributes[ATTR_AP_CHANNEL_5G] == "149"
    assert state.attributes[ATTR_AP_CHANNEL_2G] == "1"
    assert state.attributes[ATTR_AP_LED] == "off"
    assert state.attributes[ATTR_AP_TX_POWER] == "auto"
    assert state.attributes[ATTR_AP_COUNTRY] == "US"
    assert state.attributes[ATTR_AP_MESH_MODE] == "mesh"
    assert state.attributes[ATTR_AP_TIMEZONE] == "America/New_York"
    assert state.attributes[ATTR_AP_PAUSE_WIFI] is False
    assert state.attributes[ATTR_AP_DISABLE_ACL] is False
    assert state.attributes[ATTR_AP_CLIENT_COUNT] == 2

    ap_device = async_get_entry_device(
        dr.async_get(hass), (DOMAIN, "license-123_ap_20:6d:31:71:1d:d0"), entry.entry_id
    )
    router_device = async_get_entry_device(
        dr.async_get(hass), (DOMAIN, "license-123"), entry.entry_id
    )
    assert ap_device is not None
    assert router_device is not None
    assert ap_device.name == "Main Floor"
    assert ap_device.model == "fwap-D"
    assert ap_device.via_device_id == router_device.id


async def test_ap_status_binary_sensor_removed_when_ap_disappears(
    hass: HomeAssistant,
) -> None:
    """Test the AP entity is removed when the AP disappears from the payload."""
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
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_ap_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_hosts(_box_host()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = "binary_sensor.main_floor_ap_status"
    state = hass.states.get(entity_id)
    assert state is not None

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get(entity_id) is not None

    await entry.runtime_data.integration_manager.async_reconcile_ap_entities(())

    assert entity_registry.async_get(entity_id) is None
