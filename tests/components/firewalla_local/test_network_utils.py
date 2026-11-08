"""Tests for the unified network inventory normalization."""

from __future__ import annotations

from custom_components.firewalla_local.models import FirewallaNetworkKind
from custom_components.firewalla_local.utils.network import (
    build_network_inventory,
    primary_wan_interface_name,
)

_WAN_STATUS_KEY = "networkMonitorData"


def _wan_status(*interfaces: tuple[str, str, str]) -> dict[str, object]:
    """Return a raw ``wanStatus`` block keyed by interface name."""
    return {
        "overall_wan_state:overall_wan_state": {
            "labels": {
                "wanStatus": {
                    interface_key: {
                        "wan_intf_name": wan_name,
                        "wan_intf_uuid": wan_uuid,
                    }
                    for interface_key, wan_uuid, wan_name in interfaces
                }
            }
        }
    }


def test_a_wan_status_only_uplink_is_published_as_a_wan() -> None:
    """Test a PPPoE uplink the interface registry omits is still a WAN.

    The reporting box listed the PPPoE interface only in ``networkProfiles`` and
    ``wanStatus``. The profile pass classified it as a LAN and the WAN status pass
    refused to correct it, so it was published as a LAN and no WAN selector could
    name it (issue #61).
    """
    networks = build_network_inventory(
        {
            "networkProfiles": {
                "d564a8c7-a323-473a-9f9f-d7f0a5b1af7d": {
                    "intf": "pppoe0",
                    "ipv4": "86.10.20.30",
                },
                "f165924c-5854-4cd7-9041-ef7b8f1170f0": {
                    "intf": "wlan0",
                    "ipv4": "192.168.50.20",
                },
            },
            "networkConfig": {
                "interface": {
                    "wlan": {
                        "wlan0": {
                            "meta": {
                                "name": "Wireless",
                                "type": "wan",
                                "uuid": "f165924c-5854-4cd7-9041-ef7b8f1170f0",
                            }
                        }
                    }
                }
            },
            _WAN_STATUS_KEY: _wan_status(
                ("pppoe0", "d564a8c7-a323-473a-9f9f-d7f0a5b1af7d", "EE"),
                ("wlan0", "f165924c-5854-4cd7-9041-ef7b8f1170f0", "Wireless"),
            ),
        }
    )

    by_uuid = {network.uuid: network for network in networks}
    pppoe = by_uuid["d564a8c7-a323-473a-9f9f-d7f0a5b1af7d"]

    assert pppoe.kind is FirewallaNetworkKind.WAN
    assert pppoe.name == "EE"
    assert pppoe.interface_name == "pppoe0"
    assert pppoe.ports == ("pppoe0",)
    assert pppoe.ipv4_addresses == ("86.10.20.30",)
    assert by_uuid["f165924c-5854-4cd7-9041-ef7b8f1170f0"].kind is (
        FirewallaNetworkKind.WAN
    )


def test_an_unknown_interface_category_is_classified_by_meta_type() -> None:
    """Test categories outside the reverse-engineered map are not invisible.

    The category keys are open-ended and the box's coarse ``meta.type`` is enough
    to classify an uplink the map has never seen, while keeping the raw key so it
    is diagnosable.
    """
    networks = build_network_inventory(
        {
            "networkConfig": {
                "interface": {
                    "pppoe": {
                        "pppoe0": {
                            "meta": {
                                "name": "WAN-EE",
                                "type": "wan",
                                "uuid": "wan-pppoe",
                            }
                        }
                    },
                    "unknown-lan": {
                        "eth9": {
                            "meta": {
                                "name": "Guest",
                                "type": "lan",
                                "uuid": "lan-unknown",
                            }
                        }
                    },
                    "untyped": {"x0": {"meta": {"name": "No Type", "uuid": "untyped"}}},
                }
            }
        }
    )

    by_uuid = {network.uuid: network for network in networks}

    assert by_uuid["wan-pppoe"].kind is FirewallaNetworkKind.WAN
    assert by_uuid["wan-pppoe"].interface_category == "pppoe"
    assert by_uuid["lan-unknown"].kind is FirewallaNetworkKind.LAN
    assert by_uuid["lan-unknown"].interface_category == "unknown-lan"
    # Without a coarse type there is nothing to classify it with, so an entry
    # that might not be a network at all is not invented as one.
    assert "untyped" not in by_uuid


def test_a_registry_display_name_wins_over_the_wan_status_name() -> None:
    """Test the WAN status name only replaces a fallback, never a real label."""
    networks = build_network_inventory(
        {
            "networkConfig": {
                "interface": {
                    "phy": {
                        "eth0": {
                            "meta": {
                                "name": "WAN-ONE",
                                "type": "wan",
                                "uuid": "wan-1",
                            }
                        }
                    }
                }
            },
            _WAN_STATUS_KEY: _wan_status(("eth0", "wan-1", "EE")),
        }
    )

    assert [(network.name, network.kind) for network in networks] == [
        ("WAN-ONE", FirewallaNetworkKind.WAN)
    ]


def test_physical_ports_the_box_does_not_mark_as_wan_stay_out() -> None:
    networks = build_network_inventory(
        {
            "networkConfig": {
                "interface": {
                    "phy": {
                        "eth2": {
                            "meta": {
                                "name": "eth2",
                                "type": "lan",
                                "uuid": "lan-port",
                            }
                        }
                    },
                    "wlan": {
                        "wlan1": {
                            "meta": {
                                "name": "Wireless LAN",
                                "type": "lan",
                                "uuid": "lan-wifi",
                            }
                        }
                    },
                }
            }
        }
    )

    assert networks == ()


def test_a_profile_only_uplink_is_classified_from_the_profile_type() -> None:
    """Test the profile's own type classifies an uplink the registry omits.

    This is the shape a PPPoE box actually publishes (issue #61): ``pppoe0`` has
    no ``networkConfig.interface`` entry at all, and the runtime payload carries
    no ``networkMonitorData`` either, so ``networkProfiles[uuid].type`` is the
    box's only statement that the interface is a WAN.
    """
    networks = build_network_inventory(
        {
            "networkProfiles": {
                "br0-uuid": {"intf": "br0", "type": "lan"},
                "pppoe-uuid": {
                    "intf": "pppoe0",
                    "type": "wan",
                    "active": True,
                    "ready": True,
                    "pendingTest": False,
                },
            },
            "networkConfig": {
                "interface": {
                    "bridge": {
                        "br0": {
                            "meta": {
                                "name": "LAN Network",
                                "type": "lan",
                                "uuid": "br0-uuid",
                            }
                        }
                    }
                }
            },
        }
    )

    by_uuid = {network.uuid: network for network in networks}
    pppoe = by_uuid["pppoe-uuid"]

    assert pppoe.kind is FirewallaNetworkKind.WAN
    assert pppoe.interface_name == "pppoe0"
    assert pppoe.ports == ("pppoe0",)
    # The registry describes this one, so its kind is not overridden by the
    # profile's coarse ``lan``/``wan`` vocabulary.
    assert by_uuid["br0-uuid"].kind is FirewallaNetworkKind.LAN
    assert by_uuid["br0-uuid"].interface_category == "bridge"


def test_the_primary_wan_block_declares_a_wan_without_a_profile_type() -> None:
    """Test the top-level ``network`` block is read as a WAN declaration."""
    networks = build_network_inventory(
        {
            "networkProfiles": {"wan-uuid": {"intf": "eth0"}},
            "network": {
                "uuid": "wan-uuid",
                "name": "eth0",
                "desc": "WAN-ONE",
                "type": "wan",
                "active": True,
            },
        }
    )

    by_uuid = {network.uuid: network for network in networks}

    assert by_uuid["wan-uuid"].kind is FirewallaNetworkKind.WAN
    assert by_uuid["wan-uuid"].name == "WAN-ONE"


def test_the_event_labels_name_a_wan_but_cannot_create_one() -> None:
    """Test monitor-event labels supply the display name the profiles omit."""
    payload: dict[str, object] = {
        "networkProfiles": {"pppoe-uuid": {"intf": "pppoe0", "type": "wan"}},
        "latestAllStateEvents": {
            "ping:pppoe0-1.1.1.1": {
                "labels": {
                    "wan_intf_uuid": "pppoe-uuid",
                    "wan_intf_name": "EE",
                }
            },
            # A stale event for a WAN the box no longer configures.
            "ping:eth9-1.1.1.1": {
                "labels": {
                    "wan_intf_uuid": "gone-uuid",
                    "wan_intf_name": "OLD",
                }
            },
        },
    }

    by_uuid = {network.uuid: network for network in build_network_inventory(payload)}

    assert by_uuid["pppoe-uuid"].name == "EE"
    assert "gone-uuid" not in by_uuid


def test_primary_wan_is_the_interface_the_box_routes_through_first() -> None:
    """Test the configured WAN preference is read rather than inferred."""
    payload = {
        "networkConfig": {
            "routing": {
                "global": {
                    "default": {
                        "type": "primary_standby",
                        "viaIntf": "pppoe0",
                        "viaIntf2": "eth0",
                        "failback": True,
                    }
                }
            }
        }
    }

    assert primary_wan_interface_name(payload) == "pppoe0"


def test_primary_wan_interface_is_absent_when_the_box_does_not_state_one() -> None:
    """Test a payload without a routing block reports no primary instead of a guess."""
    assert primary_wan_interface_name({}) is None
    assert primary_wan_interface_name({"networkConfig": {"routing": None}}) is None
