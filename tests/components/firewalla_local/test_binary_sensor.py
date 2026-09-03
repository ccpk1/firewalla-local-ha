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
    ATTR_INTEGRATION,
    ATTR_NETWORK_BLOCK_ICMP,
    ATTR_NETWORK_DEVICE_COUNT,
    ATTR_NETWORK_DHCP,
    ATTR_NETWORK_DNS_SERVERS,
    ATTR_NETWORK_ENABLED,
    ATTR_NETWORK_GATEWAY,
    ATTR_NETWORK_IPV4_ADDRESSES,
    ATTR_NETWORK_IPV4_SUBNETS,
    ATTR_NETWORK_KIND,
    ATTR_NETWORK_MDNS_RELAY,
    ATTR_NETWORK_PORTS,
    ATTR_NETWORK_SSDP_RELAY,
    ATTR_NETWORK_USAGE,
    ATTR_NETWORK_VLAN_ID,
    ATTR_PURPOSE,
    ATTR_SYSTEM_PORTS,
    ATTR_WATCHED_DEVICE_CONNECTION_TYPE,
    ATTR_WATCHED_DEVICE_DEVICE_GROUP,
    ATTR_WATCHED_DEVICE_DOWNLOAD_USAGE,
    ATTR_WATCHED_DEVICE_IP_ADDRESS,
    ATTR_WATCHED_DEVICE_LAST_ACTIVE,
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
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_DEVICE_GROUP] == "KADEN"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_NETWORK_NAME] == "VLAN10 CORE"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_CONNECTION_TYPE] == "phone"
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_DOWNLOAD_USAGE] == 1234
    assert watched_state.attributes[ATTR_WATCHED_DEVICE_UPLOAD_USAGE] == 5678
    assert (
        watched_state.attributes[ATTR_WATCHED_DEVICE_LAST_ACTIVE]
        == datetime.fromtimestamp(1774287984.272, UTC).isoformat()
    )
    # Without AP7s there is no AP config, so topology/WiFi attributes are absent.
    assert ATTR_WATCHED_DEVICE_TOPOLOGY_CONNECTION_TYPE not in watched_state.attributes
    assert ATTR_WATCHED_DEVICE_WIFI_SSID not in watched_state.attributes
    assert ATTR_WATCHED_DEVICE_WIFI_BAND not in watched_state.attributes
    assert ATTR_WATCHED_DEVICE_WIFI_RSSI not in watched_state.attributes
    assert ATTR_WATCHED_DEVICE_WIFI_AP not in watched_state.attributes


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
        and not entity_entry.unique_id.endswith("_system_status_binary_sensor")
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
            "eth0": {"carrier": "1"},
            "eth1": {"carrier": "0"},
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
    assert vlan_state.attributes[ATTR_NETWORK_DNS_SERVERS] == ["192.168.10.1"]
    assert vlan_state.attributes[ATTR_NETWORK_MDNS_RELAY] is True
    assert vlan_state.attributes[ATTR_NETWORK_SSDP_RELAY] is False
    assert vlan_state.attributes[ATTR_NETWORK_BLOCK_ICMP] is True
    assert vlan_state.attributes[ATTR_NETWORK_DHCP]["gateway"] == "192.168.10.1"
    assert vlan_state.attributes[ATTR_NETWORK_DEVICE_COUNT] == 2
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

    assert wan_state is not None
    assert wan_state.state == STATE_ON
    assert wan_state.attributes[ATTR_NETWORK_KIND] == "wan"
    assert wan_state.attributes[ATTR_NETWORK_PORTS] == ["eth0"]
    assert wan_state.attributes[ATTR_NETWORK_USAGE] == {
        "last_24h": {"download_bytes": None, "upload_bytes": None},
        "last_60m": {"download_bytes": None, "upload_bytes": None},
        "last_30d": {"download_bytes": None, "upload_bytes": None},
        "last_12m": {"download_bytes": None, "upload_bytes": None},
        "monthly": {"download_bytes": 2048, "upload_bytes": 512},
    }


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
        "eth0": "up",
        "eth1": "down",
    }


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
