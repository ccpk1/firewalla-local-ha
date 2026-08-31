"""Tests for the Firewalla Local integration manager."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import CONF_LICENSE, DOMAIN
from custom_components.firewalla_local.managers.host_manager import (
    FirewallaHostManager,
)
from custom_components.firewalla_local.managers.integration_manager import (
    FirewallaIntegrationManager,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaDiskUsageInput,
    FirewallaHostRuntime,
    FirewallaNetworkKind,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
)


def _build_manager(
    snapshot: FirewallaRuntimeSnapshot,
    *,
    unique_id: str | None = None,
) -> FirewallaIntegrationManager:
    """Return an integration manager with minimal coordinator state."""
    coordinator = SimpleNamespace(data=snapshot, hass=None)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data={CONF_LICENSE: "license-123"},
    )
    manager = FirewallaIntegrationManager(coordinator, entry, MagicMock())
    coordinator.last_init_payload = {
        "networkMonitorData": {
            "overall_wan_state:overall_wan_state": {
                "labels": {
                    "wanStatus": {
                        "eth0": {
                            "wan_intf_name": "WAN-ONE",
                            "wan_intf_uuid": "wan-1",
                        },
                        "eth1": {
                            "wan_intf_name": "WAN-TWO",
                            "wan_intf_uuid": "wan-2",
                        },
                    }
                }
            }
        }
    }
    return manager


def test_handle_refresh_shapes_appliance_views() -> None:
    """Test the manager shapes appliance identity, status, and speed-test views."""
    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name=None,
            device_name="Hallway Box",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(
            booting_complete=True,
            dist_codename="bionic",
            cloud_connected=False,
            ddns="box.example.firewalla.org",
            firmware_release_type="alpha",
            public_ip=None,
            public_ips={"wan": "23.245.207.179"},
            cpu_usage_1m=37.5,
            memory_usage_ratio=0.25,
            total_memory_mb=1000,
            disk_usages=(
                FirewallaDiskUsageInput(
                    mount="/",
                    capacity_ratio=0.29,
                    used_bytes=None,
                    size_bytes=None,
                ),
                FirewallaDiskUsageInput(
                    mount="/data",
                    capacity_ratio=None,
                    used_bytes=30,
                    size_bytes=500,
                ),
                FirewallaDiskUsageInput(
                    mount="/home",
                    capacity_ratio=0.9,
                    used_bytes=None,
                    size_bytes=None,
                ),
            ),
        ),
        policy_rules=(),
        exception_rule_count=0,
        speed_test_results=(
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1000,
                download_mbps=100,
                upload_mbps=20,
                latency_ms=10,
                jitter_ms=1,
                packet_loss_percent=0,
                download_megabytes=50,
                upload_megabytes=10,
                isp="ISP",
                public_ip="23.245.207.179",
                server_country="United States",
                server_host="server-a",
                server_id="1",
                server_location="Columbus, OH",
                server_sponsor="Boost Mobile",
                manual=False,
                success=True,
                vendor="ookla",
                wan_uuid="wan-1",
            ),
            FirewallaSpeedTestRecord(
                tested_at_timestamp=2000,
                download_mbps=200,
                upload_mbps=30,
                latency_ms=11,
                jitter_ms=2,
                packet_loss_percent=0,
                download_megabytes=60,
                upload_megabytes=11,
                isp="ISP",
                public_ip="23.245.207.180",
                server_country="United States",
                server_host="server-b",
                server_id="2",
                server_location="Chicago, IL",
                server_sponsor="Carrier",
                manual=True,
                success=False,
                vendor="ookla",
                wan_uuid="wan-2",
            ),
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1500,
                download_mbps=150,
                upload_mbps=25,
                latency_ms=9,
                jitter_ms=1.5,
                packet_loss_percent=0,
                download_megabytes=55,
                upload_megabytes=10.5,
                isp="ISP",
                public_ip="23.245.207.181",
                server_country="United States",
                server_host="server-c",
                server_id="3",
                server_location="Cleveland, OH",
                server_sponsor="Carrier",
                manual=True,
                success=True,
                vendor="ookla",
                wan_uuid="wan-1",
            ),
        ),
    )

    manager = _build_manager(snapshot)

    manager.handle_refresh(snapshot)

    assert manager.system_info.name == "Hallway Box"
    assert manager.system_info.host == "192.168.200.1"
    assert manager.system_status is not None
    assert manager.system_status.wan_ip == "23.245.207.179"
    assert manager.system_status.box_image_codename == "bionic"
    assert manager.system_status.box_image_version == "Ubuntu 18.04 LTS (Bionic Beaver)"
    assert manager.system_status.cpu_usage_1m == 37.5
    assert manager.system_status.memory_usage_percent == 25.0
    assert manager.system_status.memory_free_mb == 750.0
    assert manager.system_status.disk_usage_percent_by_mount == {
        "/": 29,
        "/data": 6,
    }
    assert manager.latest_speed_test is not None
    assert manager.latest_speed_test.tested_at_timestamp == 1500
    assert manager.latest_speed_test.download_mbps == 150
    assert manager.latest_speed_test.success is True
    assert manager.latest_speed_test.wan_uuid == "wan-1"
    assert manager.latest_speed_test.wan_name == "WAN-ONE"
    assert manager.system_info.model == "Gold"


def test_handle_refresh_uses_raw_codename_when_release_map_is_missing() -> None:
    """Test the box image version falls back to the raw codename."""
    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name=None,
            device_name="Hallway Box",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(
            dist_codename="plucky",
        ),
        policy_rules=(),
        exception_rule_count=0,
    )

    manager = _build_manager(snapshot)

    manager.handle_refresh(snapshot)

    assert manager.system_status is not None
    assert manager.system_status.box_image_codename == "plucky"
    assert manager.system_status.box_image_version == "plucky"


def test_build_device_info_uses_default_name_and_entry_unique_id() -> None:
    """Test device info uses the shaped appliance name and config entry identity."""
    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name=None,
            device_name=None,
            model="purple",
            serial_number="serial-999",
            software_version="2.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
    )

    manager = _build_manager(snapshot, unique_id="entry-123")

    device_info = manager.build_device_info()

    assert device_info["name"] == "Firewalla"
    assert device_info["model"] == "Purple"
    assert device_info["serial_number"] == "serial-999"
    assert device_info["sw_version"] == "2.0.0"
    assert device_info["identifiers"] == {(DOMAIN, "entry-123")}


def test_latest_speed_test_is_none_without_successful_records() -> None:
    """Test unsuccessful speed tests do not produce a latest-speed-test view."""
    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model=None,
            serial_number=None,
            software_version=None,
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
        speed_test_results=(
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1000,
                download_mbps=None,
                upload_mbps=None,
                latency_ms=None,
                jitter_ms=None,
                packet_loss_percent=None,
                download_megabytes=None,
                upload_megabytes=None,
                isp=None,
                public_ip=None,
                server_country=None,
                server_host=None,
                server_id=None,
                server_location=None,
                server_sponsor=None,
                manual=False,
                success=False,
                vendor=None,
            ),
        ),
    )

    manager = _build_manager(snapshot)

    manager.handle_refresh(snapshot)

    assert manager.latest_speed_test is None


def test_get_speed_test_results_reuses_shaped_speed_test_path() -> None:
    """Test speed-test result lists reuse the same shaping logic as the sensor view."""
    snapshot = FirewallaRuntimeSnapshot(
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
        speed_test_results=(
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1000,
                download_mbps=100,
                upload_mbps=20,
                latency_ms=10,
                jitter_ms=1,
                packet_loss_percent=0,
                download_megabytes=50,
                upload_megabytes=10,
                isp="ISP",
                public_ip="23.245.207.179",
                server_country="United States",
                server_host="server-a",
                server_id="1",
                server_location="Columbus, OH",
                server_sponsor="Boost Mobile",
                manual=False,
                success=True,
                vendor="ookla",
                wan_uuid="wan-1",
            ),
            FirewallaSpeedTestRecord(
                tested_at_timestamp=2000,
                download_mbps=200,
                upload_mbps=30,
                latency_ms=11,
                jitter_ms=2,
                packet_loss_percent=1,
                download_megabytes=60,
                upload_megabytes=11,
                isp="ISP",
                public_ip="23.245.207.180",
                server_country="United States",
                server_host="server-b",
                server_id="2",
                server_location="Chicago, IL",
                server_sponsor="Carrier",
                manual=True,
                success=False,
                vendor="ookla",
                wan_uuid="wan-2",
            ),
        ),
    )
    manager = _build_manager(snapshot)

    results = manager.get_speed_test_results(limit=2)
    wan_filtered_results = manager.get_speed_test_results(wan_uuid="wan-1", limit=2)

    assert [result.tested_at_timestamp for result in results] == [2000, 1000]
    assert results[0].wan_name == "WAN-TWO"
    assert len(wan_filtered_results) == 1
    assert wan_filtered_results[0].wan_uuid == "wan-1"


def test_get_available_wans_ignores_speed_test_uuid_fallback() -> None:
    """Test WAN discovery does not fall back to speed-test-only UUIDs."""
    snapshot = FirewallaRuntimeSnapshot(
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
        speed_test_results=(
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1000,
                download_mbps=100,
                upload_mbps=20,
                latency_ms=10,
                jitter_ms=1,
                packet_loss_percent=0,
                download_megabytes=50,
                upload_megabytes=10,
                isp="ISP",
                public_ip="23.245.207.179",
                server_country="United States",
                server_host="server-a",
                server_id="1",
                server_location="Columbus, OH",
                server_sponsor="Boost Mobile",
                manual=False,
                success=True,
                vendor="ookla",
                wan_uuid="wan-extra",
            ),
        ),
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {}

    available_wans = manager.get_available_wans()

    assert available_wans == ()


def test_get_networks_discovers_all_kinds_from_interface_registry() -> None:
    """Test the unified collector classifies LAN, VLAN, VPN, and WAN networks."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkProfiles": {
            "95169e6a-a7c9-4d6a-8e83-6061b4812bf2": {"intf": "bond0.10"},
            "aff1d681-981f-4ae4-ba0c-d1620947097b": {"intf": "bond0"},
            "876e3889-0199-45f3-aeb1-a49c3f38e96e": {"intf": "awg0"},
        },
        "networkConfig": {
            "interface": {
                "phy": {
                    "eth0": {
                        "meta": {
                            "name": "WAN-ONE",
                            "type": "wan",
                            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
                        }
                    }
                },
                "bond": {
                    "bond0": {
                        "meta": {
                            "name": "LAN-MGMT",
                            "type": "lan",
                            "uuid": "aff1d681-981f-4ae4-ba0c-d1620947097b",
                        }
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
                    }
                },
                "amneziawg": {
                    "awg0": {
                        "meta": {
                            "name": "AmneziaWG",
                            "type": "lan",
                            "uuid": "876e3889-0199-45f3-aeb1-a49c3f38e96e",
                        }
                    }
                },
            }
        },
    }

    networks = manager.get_networks()
    by_uuid = {network.uuid: network for network in networks}

    assert (
        by_uuid["8d5a7f20-2923-49a3-8e2b-338f9428a632"].kind is FirewallaNetworkKind.WAN
    )
    assert by_uuid["8d5a7f20-2923-49a3-8e2b-338f9428a632"].name == "WAN-ONE"
    assert by_uuid["aff1d681-981f-4ae4-ba0c-d1620947097b"].kind is (
        FirewallaNetworkKind.LAN
    )
    assert by_uuid["aff1d681-981f-4ae4-ba0c-d1620947097b"].name == "LAN-MGMT"
    assert by_uuid["95169e6a-a7c9-4d6a-8e83-6061b4812bf2"].kind is (
        FirewallaNetworkKind.VLAN
    )
    assert by_uuid["95169e6a-a7c9-4d6a-8e83-6061b4812bf2"].name == "VLAN10 CORE"
    assert by_uuid["876e3889-0199-45f3-aeb1-a49c3f38e96e"].kind is (
        FirewallaNetworkKind.VPN
    )
    assert by_uuid["876e3889-0199-45f3-aeb1-a49c3f38e96e"].name == "AmneziaWG"


def test_get_networks_excludes_unnamed_physical_ports() -> None:
    """Test unnamed phy ports (eth1/2/3) are not surfaced as WAN networks."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkConfig": {
            "interface": {
                "phy": {
                    "eth0": {
                        "meta": {
                            "name": "WAN-ONE",
                            "type": "wan",
                            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
                        }
                    },
                    "eth1": {"meta": {"uuid": "d2a5b1c5-31ca-4d42-8906-09b24e68c5d2"}},
                    "eth2": {"meta": {"uuid": "27aa9b20-e679-4f78-8c76-791e02a7c2ca"}},
                    "eth3": {"meta": {"uuid": "47f86e7a-c673-4374-a8a4-0c7b445f5c8d"}},
                }
            }
        }
    }

    networks = manager.get_networks()

    assert {network.uuid for network in networks} == {
        "8d5a7f20-2923-49a3-8e2b-338f9428a632"
    }


def test_get_networks_addresses_are_bare_and_subnets_are_cidr() -> None:
    """Test ipv4_addresses stay bare, ipv4_subnets hold CIDRs, and dhcp gateway."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkProfiles": {
            "95169e6a-a7c9-4d6a-8e83-6061b4812bf2": {
                "intf": "bond0.10",
                "ipv4": "192.168.10.1",
                "ipv4Subnet": "192.168.10.0/24",
                "ipv4Subnets": ["192.168.10.0/24"],
            }
        },
        "networkConfig": {
            "interface": {
                "vlan": {
                    "bond0.10": {
                        "meta": {
                            "name": "VLAN10 CORE",
                            "type": "lan",
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        },
                        "ipv4": "192.168.10.1/24",
                    }
                }
            },
            "dhcp": {
                "bond0.10": {
                    "gateway": "192.168.10.1",
                    "subnetMask": "255.255.255.0",
                }
            },
        },
    }

    network = next(network for network in manager.get_networks())

    assert network.ipv4_addresses == ("192.168.10.1",)
    assert network.ipv4_subnets == ("192.168.10.0/24",)
    assert network.gateway == "192.168.10.1"


def test_get_networks_resolves_physical_ports() -> None:
    """Test ports resolve: WAN=own phy port, bond/VLAN=bond members, VPN=none."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkConfig": {
            "interface": {
                "phy": {
                    "eth0": {
                        "meta": {
                            "name": "WAN-ONE",
                            "type": "wan",
                            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
                        }
                    }
                },
                "bond": {
                    "bond0": {
                        "meta": {
                            "name": "LAN-MGMT",
                            "type": "lan",
                            "uuid": "aff1d681-981f-4ae4-ba0c-d1620947097b",
                        },
                        "intf": ["eth2", "eth3"],
                    }
                },
                "vlan": {
                    "bond0.10": {
                        "meta": {
                            "name": "VLAN10 CORE",
                            "type": "lan",
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        },
                        "intf": "bond0",
                    }
                },
                "amneziawg": {
                    "awg0": {
                        "meta": {
                            "name": "AmneziaWG",
                            "type": "lan",
                            "uuid": "876e3889-0199-45f3-aeb1-a49c3f38e96e",
                        }
                    }
                },
            }
        }
    }

    by_uuid = {network.uuid: network for network in manager.get_networks()}

    assert by_uuid["8d5a7f20-2923-49a3-8e2b-338f9428a632"].ports == ("eth0",)
    assert by_uuid["aff1d681-981f-4ae4-ba0c-d1620947097b"].ports == (
        "eth2",
        "eth3",
    )
    assert by_uuid["95169e6a-a7c9-4d6a-8e83-6061b4812bf2"].ports == (
        "eth2",
        "eth3",
    )
    assert by_uuid["876e3889-0199-45f3-aeb1-a49c3f38e96e"].ports == ()


def test_get_networks_discovers_bridge_and_wlan_categories() -> None:
    """Test bridge LANs and wireless WAN uplinks are classified correctly.

    Router-Mode boxes segment LANs as ``bridge`` interfaces (carrying direct
    ports and/or tagged VLAN members), and a ``wlan`` entry is a wireless WAN
    uplink only when ``meta.type == "wan"``.
    """
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkConfig": {
            "interface": {
                "phy": {
                    "eth0": {
                        "meta": {
                            "name": "2degrees",
                            "type": "wan",
                            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
                        }
                    },
                    "eth1": {"meta": {"uuid": "d2a5b1c5-31ca-4d42-8906-09b24e68c5d2"}},
                    "eth2": {"meta": {"uuid": "27aa9b20-e679-4f78-8c76-791e02a7c2ca"}},
                    "eth3": {"meta": {"uuid": "47f86e7a-c673-4374-a8a4-0c7b445f5c8d"}},
                },
                "wlan": {
                    "wlan0": {
                        "meta": {
                            "name": "Wireless",
                            "type": "wan",
                            "uuid": "deadbeef-1111-4222-8333-444455556666",
                        }
                    }
                },
                "bridge": {
                    "br1": {
                        "meta": {
                            "name": "Guest",
                            "type": "lan",
                            "uuid": "aff1d681-981f-4ae4-ba0c-d1620947097b",
                        },
                        "intf": ["eth3.101"],
                    }
                },
                "vlan": {
                    "eth3.101": {
                        "meta": {
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        },
                        "vid": 101,
                        "intf": "eth3",
                    }
                },
            }
        }
    }

    by_uuid = {network.uuid: network for network in manager.get_networks()}

    # The wlan uplink is a WAN, distinct from the phy WAN.
    assert by_uuid["deadbeef-1111-4222-8333-444455556666"].kind is (
        FirewallaNetworkKind.WAN
    )
    assert by_uuid["deadbeef-1111-4222-8333-444455556666"].name == "Wireless"
    assert by_uuid["deadbeef-1111-4222-8333-444455556666"].ports == ("wlan0",)
    # The bridge is a LAN and its tagged VLAN member is transport, so the VLAN
    # is not surfaced as a separate network.
    assert by_uuid["aff1d681-981f-4ae4-ba0c-d1620947097b"].kind is (
        FirewallaNetworkKind.LAN
    )
    assert by_uuid["aff1d681-981f-4ae4-ba0c-d1620947097b"].name == "Guest"
    assert by_uuid["aff1d681-981f-4ae4-ba0c-d1620947097b"].ports == ("eth3",)
    assert "95169e6a-a7c9-4d6a-8e83-6061b4812bf2" not in by_uuid


def test_get_networks_keeps_standalone_vlan_not_referenced_by_bridge() -> None:
    """Test a standalone VLAN not referenced by any bridge stays a VLAN."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkConfig": {
            "interface": {
                "phy": {
                    "eth0": {
                        "meta": {
                            "name": "WAN-ONE",
                            "type": "wan",
                            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
                        }
                    }
                },
                "bridge": {
                    "br1": {
                        "meta": {
                            "name": "Guest",
                            "type": "lan",
                            "uuid": "aff1d681-981f-4ae4-ba0c-d1620947097b",
                        },
                        "intf": ["eth3.101"],
                    }
                },
                "vlan": {
                    "eth3.101": {
                        "meta": {
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        },
                        "vid": 101,
                        "intf": "eth3",
                    },
                    "eth1.9": {
                        "meta": {
                            "name": "DMZ",
                            "type": "lan",
                            "uuid": "deadbeef-2222-4222-8333-444455556666",
                        },
                        "vid": 9,
                        "intf": "eth1",
                    },
                },
            }
        }
    }

    by_uuid = {network.uuid: network for network in manager.get_networks()}

    # The bridge-referenced VLAN is transport and filtered.
    assert "95169e6a-a7c9-4d6a-8e83-6061b4812bf2" not in by_uuid
    # The standalone VLAN is surfaced.
    assert by_uuid["deadbeef-2222-4222-8333-444455556666"].kind is (
        FirewallaNetworkKind.VLAN
    )
    assert by_uuid["deadbeef-2222-4222-8333-444455556666"].name == "DMZ"
    assert by_uuid["deadbeef-2222-4222-8333-444455556666"].ports == ("eth1",)


def test_get_networks_wan_requires_meta_type_wan() -> None:
    """Test a wlan entry with a non-wan meta.type is not surfaced as WAN."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkConfig": {
            "interface": {
                "wlan": {
                    "wlan0": {
                        "meta": {
                            "name": "Wireless LAN AP",
                            "type": "lan",
                            "uuid": "deadbeef-3333-4222-8333-444455556666",
                        }
                    }
                }
            }
        }
    }

    networks = manager.get_networks()

    assert {network.uuid for network in networks} == set()


@pytest.mark.asyncio
async def test_async_refresh_network_usage_attaches_totals() -> None:
    """Test usage refresh fetches item=intf and merges totals into networks."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkConfig": {
            "interface": {
                "vlan": {
                    "bond0.10": {
                        "meta": {
                            "name": "VLAN10 CORE",
                            "type": "lan",
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        }
                    }
                },
                "amneziawg": {
                    "awg0": {
                        "meta": {
                            "name": "AmneziaWG",
                            "type": "lan",
                            "uuid": "876e3889-0199-45f3-aeb1-a49c3f38e96e",
                        }
                    }
                },
            }
        }
    }

    usage_payloads = {
        "95169e6a-a7c9-4d6a-8e83-6061b4812bf2": {
            "newLast24": {
                "totalDownload": 100,
                "totalUpload": 50,
            },
            "last30": {
                "totalDownload": 900,
                "totalUpload": 450,
            },
        },
        "876e3889-0199-45f3-aeb1-a49c3f38e96e": {
            "newLast24": {
                "totalDownload": 10,
                "totalUpload": 5,
            },
        },
    }

    async def _fake_fetch(**kwargs):
        payload = usage_payloads[kwargs["network_uuid"]]
        return dict(payload)

    manager.client.async_get_network_interface_payload = AsyncMock(
        side_effect=_fake_fetch
    )

    await manager.async_refresh_network_usage()

    by_uuid = {network.uuid: network for network in manager.get_networks()}
    vlan_usage = by_uuid["95169e6a-a7c9-4d6a-8e83-6061b4812bf2"].usage
    vpn_usage = by_uuid["876e3889-0199-45f3-aeb1-a49c3f38e96e"].usage

    assert vlan_usage is not None
    assert vlan_usage.last_24h is not None
    assert vlan_usage.last_24h.download_bytes == 100
    assert vlan_usage.last_24h.upload_bytes == 50
    assert vlan_usage.last_30d is not None
    assert vlan_usage.last_30d.download_bytes == 900
    assert vpn_usage is not None
    assert vpn_usage.last_24h is not None
    assert vpn_usage.last_24h.download_bytes == 10


@pytest.mark.asyncio
async def test_async_refresh_network_usage_survives_per_network_failure() -> None:
    """Test one failing network fetch does not drop the others' usage."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkConfig": {
            "interface": {
                "vlan": {
                    "bond0.10": {
                        "meta": {
                            "name": "VLAN10 CORE",
                            "type": "lan",
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        }
                    }
                }
            }
        }
    }

    async def _fake_fetch(**kwargs):
        raise RuntimeError("intf unavailable")

    manager.client.async_get_network_interface_payload = AsyncMock(
        side_effect=_fake_fetch
    )

    await manager.async_refresh_network_usage()

    network = next(iter(manager.get_networks()))
    assert network.usage is None


@pytest.mark.asyncio
async def test_async_refresh_network_usage_excludes_wan() -> None:
    """Test WAN networks get no windowed usage (no per-WAN windowed source)."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkConfig": {
            "interface": {
                "phy": {
                    "eth0": {
                        "meta": {
                            "name": "WAN-ONE",
                            "type": "wan",
                            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
                        }
                    }
                },
                "vlan": {
                    "bond0.10": {
                        "meta": {
                            "name": "VLAN10 CORE",
                            "type": "lan",
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        }
                    }
                },
            }
        },
        "newLast24": {"totalDownload": 1000, "totalUpload": 500},
    }

    async def _fake_fetch(**kwargs):  # only non-WAN networks are fetched
        return {"newLast24": {"totalDownload": 1000, "totalUpload": 500}}

    manager.client.async_get_network_interface_payload = AsyncMock(
        side_effect=_fake_fetch
    )

    await manager.async_refresh_network_usage()

    by_uuid = {network.uuid: network for network in manager.get_networks()}
    assert by_uuid["8d5a7f20-2923-49a3-8e2b-338f9428a632"].usage is None
    vlan_usage = by_uuid["95169e6a-a7c9-4d6a-8e83-6061b4812bf2"].usage
    assert vlan_usage is not None
    assert vlan_usage.last_24h is not None
    assert vlan_usage.last_24h.download_bytes == 1000


def test_get_available_networks_filters_lan_and_vlan_kinds() -> None:
    """Test LAN/VLAN subset wraps the unified collector without regressions."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkProfiles": {
            "95169e6a-a7c9-4d6a-8e83-6061b4812bf2": {"intf": "bond0.10"},
            "876e3889-0199-45f3-aeb1-a49c3f38e96e": {"intf": "awg0"},
        },
        "networkConfig": {
            "interface": {
                "phy": {
                    "eth0": {
                        "meta": {
                            "name": "WAN-ONE",
                            "type": "wan",
                            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
                        }
                    }
                },
                "vlan": {
                    "bond0.10": {
                        "meta": {
                            "name": "VLAN10 CORE",
                            "type": "lan",
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        }
                    }
                },
                "amneziawg": {
                    "awg0": {
                        "meta": {
                            "name": "AmneziaWG",
                            "type": "lan",
                            "uuid": "876e3889-0199-45f3-aeb1-a49c3f38e96e",
                        }
                    }
                },
            }
        },
    }

    networks = manager.get_available_networks()
    by_uuid = {network.uuid: network for network in networks}

    assert set(by_uuid) == {"95169e6a-a7c9-4d6a-8e83-6061b4812bf2"}
    assert by_uuid["95169e6a-a7c9-4d6a-8e83-6061b4812bf2"].name == "VLAN10 CORE"


def test_get_available_wans_filters_wan_kind_without_speed_test_fallback() -> None:
    """Test WAN subset wraps the unified collector without speed-test fallback."""
    snapshot = FirewallaRuntimeSnapshot(
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
        speed_test_results=(
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1000,
                download_mbps=100,
                upload_mbps=20,
                latency_ms=10,
                jitter_ms=1,
                packet_loss_percent=0,
                download_megabytes=50,
                upload_megabytes=10,
                isp="ISP",
                public_ip="23.245.207.179",
                server_country="United States",
                server_host="server-a",
                server_id="1",
                server_location="Columbus, OH",
                server_sponsor="Boost Mobile",
                manual=False,
                success=True,
                vendor="ookla",
                wan_uuid="wan-extra",
            ),
        ),
    )
    manager = _build_manager(snapshot)
    manager.coordinator.last_init_payload = {
        "networkConfig": {
            "interface": {
                "phy": {
                    "eth0": {
                        "meta": {
                            "name": "WAN-ONE",
                            "type": "wan",
                            "uuid": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
                        }
                    }
                },
                "vlan": {
                    "bond0.10": {
                        "meta": {
                            "name": "VLAN10 CORE",
                            "type": "lan",
                            "uuid": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
                        }
                    }
                },
            }
        }
    }

    available_wans = manager.get_available_wans()

    assert [wan.uuid for wan in available_wans] == [
        "8d5a7f20-2923-49a3-8e2b-338f9428a632"
    ]


@pytest.mark.asyncio
async def test_async_delete_host_forwards_to_client_and_evicts_index() -> None:
    """Test host delete forwards the MAC and drops it from the host index."""
    snapshot = FirewallaRuntimeSnapshot(
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
        hosts=(
            FirewallaHostRuntime(
                mac="12:A9:78:EB:EA:02",
                host_name="Test Device",
                ip_address="192.168.200.25",
                group_name=None,
                network_name=None,
                connection_type=None,
                last_active=None,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
            ),
        ),
    )
    manager = _build_manager(snapshot)
    host_manager = FirewallaHostManager(
        manager.coordinator, manager.entry, manager.client
    )
    host_manager.handle_refresh(snapshot)
    manager.coordinator.host_manager = host_manager
    manager.client.async_delete_host = AsyncMock(return_value={"ok": True})

    response = await manager.async_delete_host("12:A9:78:EB:EA:02")

    assert response == {"deleted": "12:A9:78:EB:EA:02"}
    manager.client.async_delete_host.assert_awaited_once_with("12:A9:78:EB:EA:02")
    assert host_manager.get_host("12:A9:78:EB:EA:02") is None


@pytest.mark.asyncio
async def test_async_delete_host_skips_eviction_without_host_manager() -> None:
    """Test delete still forwards the client when no host manager is attached."""
    snapshot = FirewallaRuntimeSnapshot(
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
    )
    manager = _build_manager(snapshot)
    manager.client.async_delete_host = AsyncMock(return_value={"ok": True})

    response = await manager.async_delete_host("12:A9:78:EB:EA:02")

    assert response == {"deleted": "12:A9:78:EB:EA:02"}
    manager.client.async_delete_host.assert_awaited_once_with("12:A9:78:EB:EA:02")
