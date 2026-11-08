"""Tests for the unified network inventory normalization."""

from __future__ import annotations

from custom_components.firewalla_local.models import (
    FirewallaNetworkKind,
    FirewallaWanRouting,
)
from custom_components.firewalla_local.utils.network import (
    build_network_inventory,
    primary_wan_interface_name,
    wan_health_by_interface,
    wan_routing,
)

_WAN_STATUS_KEY = "networkMonitorData"


def _wan_status(*interfaces: tuple[str, str, str]) -> dict[str, object]:
    """Return a ``wanStatus`` block in the shape the monitor events carry."""
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


def test_a_profile_only_wan_is_fully_populated_from_its_profile() -> None:
    """Test the issue #61 shape: an uplink present only in ``networkProfiles``.

    The reporting box listed the PPPoE uplink only there, so the profile's own
    ``type`` has to supply the kind. Its interface name has to come from the
    profile's ``intf`` too, because nothing else states it — without that the
    network is skipped by the port, DHCP and relay lookups.
    """
    networks = build_network_inventory(
        {
            "networkProfiles": {
                "d564a8c7-a323-473a-9f9f-d7f0a5b1af7d": {
                    "intf": "pppoe0",
                    "type": "wan",
                    "active": True,
                    "ready": True,
                    "ipv4": "86.10.20.30",
                },
            },
            # The registry exists but does not describe the uplink; an empty map
            # keeps the port and relay passes running against it.
            "networkConfig": {"interface": {}},
        }
    )

    (pppoe,) = networks

    assert pppoe.kind is FirewallaNetworkKind.WAN
    assert pppoe.interface_name == "pppoe0"
    assert pppoe.ports == ("pppoe0",)
    assert pppoe.ipv4_addresses == ("86.10.20.30",)


def test_an_init_payload_wan_status_block_is_not_a_wan_source() -> None:
    """Test ``networkMonitorData`` in an init payload cannot create a WAN.

    A live box publishes no ``networkMonitorData`` there at all — ``wanStatus``
    lives only in monitor-event labels — so an earlier version of this parser
    read a block that never exists. Pinning the absence keeps that dead path
    from being reintroduced: the invented source must not classify anything.
    """
    networks = build_network_inventory(
        {
            "networkProfiles": {"pppoe-uuid": {"intf": "pppoe0", "type": "lan"}},
            _WAN_STATUS_KEY: _wan_status(("pppoe0", "pppoe-uuid", "EE")),
        }
    )

    (network,) = networks

    assert network.kind is FirewallaNetworkKind.LAN
    assert network.name == "pppoe0"


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


def test_routing_reads_the_failover_settings() -> None:
    """Test failover reports a primary, a standby and the auto-fallback toggle."""
    routing = wan_routing(
        {
            "networkConfig": {
                "routing": {
                    "global": {
                        "default": {
                            "type": "primary_standby",
                            "viaIntf": "eth1",
                            "viaIntf2": "eth0",
                            "failback": False,
                        }
                    }
                }
            }
        }
    )

    assert routing == FirewallaWanRouting(
        mode="primary_standby",
        primary="eth1",
        standby="eth0",
        failback=False,
    )


def test_routing_reads_the_load_balance_share_without_inventing_a_primary() -> None:
    """Test load balance reports the configured share and no primary.

    Captured from a live box: load balance carries ``nextHops`` and names no
    primary, so electing one would state a hierarchy the mode does not have.
    """
    routing = wan_routing(
        {
            "networkConfig": {
                "routing": {
                    "global": {
                        "default": {
                            "type": "load_balance",
                            "nextHops": [
                                {"viaIntf": "eth0", "weight": 60},
                                {"viaIntf": "eth1", "weight": 40},
                            ],
                        }
                    }
                }
            }
        }
    )

    assert routing == FirewallaWanRouting(
        mode="load_balance",
        traffic_share_percent={"eth0": 60, "eth1": 40},
    )
    assert (
        primary_wan_interface_name(
            {
                "networkConfig": {
                    "routing": {
                        "global": {
                            "default": {
                                "type": "load_balance",
                                "nextHops": [{"viaIntf": "eth0", "weight": 100}],
                            }
                        }
                    }
                }
            }
        )
        is None
    )


def test_routing_states_the_mode_alone_when_it_has_no_settings() -> None:
    """Test a mode with nothing to configure reports only its name."""
    payload = {
        "networkConfig": {
            "routing": {"global": {"default": {"type": "single"}}},
        }
    }

    assert wan_routing(payload) == FirewallaWanRouting(mode="single")
    assert primary_wan_interface_name(payload) is None


def test_routing_ignores_a_next_hop_without_a_weight() -> None:
    """Test a malformed next hop is dropped rather than published as zero."""
    routing = wan_routing(
        {
            "networkConfig": {
                "routing": {
                    "global": {
                        "default": {
                            "type": "load_balance",
                            "nextHops": [
                                {"viaIntf": "eth0", "weight": 60},
                                {"viaIntf": "eth1"},
                                {"weight": 40},
                            ],
                        }
                    }
                }
            }
        }
    )

    assert routing is not None
    assert routing.traffic_share_percent == {"eth0": 60}


def test_routing_is_absent_without_a_routing_block() -> None:
    """Test a box that states no preference reports nothing, not a default mode."""
    assert wan_routing({}) is None
    assert wan_routing({"networkConfig": {"routing": None}}) is None
    assert wan_routing({"networkConfig": {"routing": {"global": {}}}}) is None


def test_health_failures_are_read_from_the_boxes_object_shape() -> None:
    """Test a failed probe names what broke.

    The box lists failures as ``[{"type": "carrier"}]``. Reading that as a string
    list yielded nothing, which silently dropped the only part of the health
    block that says *why* a WAN is unhealthy.
    """
    health = wan_health_by_interface(
        {
            "wanTestResult": {
                "wans": {
                    "eth0": {
                        "carrier": False,
                        "ready": False,
                        "failures": [{"type": "carrier"}],
                    },
                    "eth1": {
                        "carrier": True,
                        "failures": [{"type": "dns", "target": "1.1.1.1"}],
                    },
                }
            }
        }
    )

    assert health["eth0"]["failures"] == ("carrier",)
    assert health["eth0"]["carrier"] is False
    assert health["eth1"]["failures"] == ("dns",)


def test_health_is_absent_when_the_box_reports_no_test_result() -> None:
    """Test a payload without the health block yields nothing to publish."""
    assert wan_health_by_interface({}) == {}
    assert wan_health_by_interface({"wanTestResult": {"wans": None}}) == {}


def test_primary_wan_interface_is_absent_when_the_box_does_not_state_one() -> None:
    """Test a payload without a routing block reports no primary instead of a guess."""
    assert primary_wan_interface_name({}) is None
    assert primary_wan_interface_name({"networkConfig": {"routing": None}}) is None
