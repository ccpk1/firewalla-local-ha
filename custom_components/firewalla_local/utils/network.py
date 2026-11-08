"""Unified Firewalla network inventory normalization helpers."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Final

from ..const import WAN_MODE_LOAD_BALANCE, WAN_MODE_PRIMARY_STANDBY
from ..models import (
    FirewallaNetwork,
    FirewallaNetworkDhcpConfig,
    FirewallaNetworkKind,
    FirewallaWanRouting,
)
from .values import normalized_bool, normalized_int, normalized_string

# Raw keys/literals for the unified Firewalla network registry.
_RAW_NETWORK_CONFIG_KEY: Final = "networkConfig"
_RAW_INTERFACE_KEY: Final = "interface"
_RAW_META_KEY: Final = "meta"
_RAW_NAME_KEY: Final = "name"
_RAW_DESC_KEY: Final = "desc"
_RAW_INTF_KEY: Final = "intf"
_RAW_UUID_KEY: Final = "uuid"
_RAW_TYPE_KEY: Final = "type"
_RAW_TYPE_WAN: Final = "wan"
_RAW_TYPE_LAN: Final = "lan"
_RAW_ENABLED_KEY: Final = "enabled"
_RAW_ACTIVE_KEY: Final = "active"
_RAW_READY_KEY: Final = "ready"
_RAW_VID_KEY: Final = "vid"
_RAW_IPV4_KEY: Final = "ipv4"
_RAW_IPV4_SUBNET_KEY: Final = "ipv4Subnet"
_RAW_IPV4_SUBNETS_KEY: Final = "ipv4Subnets"
_RAW_IPV6_KEY: Final = "ipv6"
_RAW_IPV6_SUBNETS_KEY: Final = "ipv6Subnets"
_RAW_GATEWAY_KEY: Final = "gateway"
_RAW_DNS_KEY: Final = "dns"
_RAW_DHCP_KEY: Final = "dhcp"
_RAW_MDNS_REFLECTOR_KEY: Final = "mdns_reflector"
_RAW_ICMP_KEY: Final = "icmp"
_RAW_MROUTE_KEY: Final = "mroute"
_RAW_ROUTES_KEY: Final = "routes"
_RAW_CIDR_KEY: Final = "cidr"
_RAW_ECHO_REQUEST_KEY: Final = "echoRequest"
_RAW_RANGE_KEY: Final = "range"
_RAW_FROM_KEY: Final = "from"
_RAW_TO_KEY: Final = "to"
_RAW_SUBNET_MASK_KEY: Final = "subnetMask"
_RAW_LEASE_KEY: Final = "lease"
_RAW_NAMESERVERS_KEY: Final = "nameservers"
_RAW_SEARCH_DOMAIN_KEY: Final = "searchDomain"
_RAW_EXTRA_OPTIONS_KEY: Final = "extraOptions"
_SSDP_MULTICAST_CIDR: Final = "239.255.255.250"
_RAW_NETWORK_PROFILES_KEY: Final = "networkProfiles"
_RAW_HOSTS_KEY: Final = "hosts"
_RAW_HOST_MAC_VENDOR_KEY: Final = "macVendor"
_RAW_HOST_INTF_KEY: Final = "intf"
_FIREWALLA_VENDOR_MARKER: Final = "firewalla"
_RAW_NETWORK_BLOCK_KEY: Final = "network"
_RAW_IP_ADDRESS_KEY: Final = "ip_address"
_RAW_IP4_ADDRESSES_KEY: Final = "ip4_addresses"
_RAW_WAN_TEST_RESULT_KEY: Final = "wanTestResult"
_RAW_WANS_KEY: Final = "wans"
_RAW_TS_KEY: Final = "ts"
_RAW_CARRIER_KEY: Final = "carrier"
_RAW_PING_KEY: Final = "ping"
_RAW_HTTP_KEY: Final = "http"
_RAW_STATUS_CODE_KEY: Final = "statusCode"
_RAW_FAILURES_KEY: Final = "failures"
_RAW_RECENT_DOWN_TIME_KEY: Final = "recentDownTime"
_RAW_LABELS_KEY: Final = "labels"
_RAW_WAN_INTERFACE_NAME_KEY: Final = "wan_intf_name"
_RAW_WAN_INTERFACE_UUID_KEY: Final = "wan_intf_uuid"
# The only payload blocks whose entries carry event ``labels``. Enumerating them
# keeps the WAN-name lookup proportional to the event count rather than to the
# whole payload.
_WAN_NAME_EVENT_KEYS: Final = (
    "latestAllStateEvents",
    "latestStateEventsError",
    "networkMonitorEvents",
)
_RAW_ROUTING_KEY: Final = "routing"
_RAW_GLOBAL_KEY: Final = "global"
_RAW_DEFAULT_ROUTE_KEY: Final = "default"
_RAW_VIA_INTF_KEY: Final = "viaIntf"
_RAW_VIA_INTF2_KEY: Final = "viaIntf2"
_RAW_FAILBACK_KEY: Final = "failback"
_RAW_NEXT_HOPS_KEY: Final = "nextHops"
_RAW_WEIGHT_KEY: Final = "weight"
_WAN_MODE_PRIMARY_STANDBY: Final = WAN_MODE_PRIMARY_STANDBY
_WAN_MODE_LOAD_BALANCE: Final = WAN_MODE_LOAD_BALANCE
# The role vocabulary a WAN can carry under one mode. `shared` is load balance's
# equal membership of the routing set; see `wan_role`.
WAN_ROLE_PRIMARY: Final = "primary"
WAN_ROLE_STANDBY: Final = "standby"
WAN_ROLE_SHARED: Final = "shared"
_RAW_PHY_CATEGORY: Final = "phy"
_RAW_BOND_CATEGORY: Final = "bond"
_RAW_VLAN_CATEGORY: Final = "vlan"
_RAW_WIREGUARD_CATEGORY: Final = "wireguard"
_RAW_AMNEZIAWG_CATEGORY: Final = "amneziawg"
_RAW_OPENVPN_CATEGORY: Final = "openvpn"
_RAW_BRIDGE_CATEGORY: Final = "bridge"
_RAW_WLAN_CATEGORY: Final = "wlan"
_NETWORK_KIND_BY_INTERFACE_CATEGORY: Final = {
    _RAW_PHY_CATEGORY: FirewallaNetworkKind.WAN,
    _RAW_BOND_CATEGORY: FirewallaNetworkKind.LAN,
    _RAW_VLAN_CATEGORY: FirewallaNetworkKind.VLAN,
    _RAW_WIREGUARD_CATEGORY: FirewallaNetworkKind.VPN,
    _RAW_AMNEZIAWG_CATEGORY: FirewallaNetworkKind.VPN,
    _RAW_OPENVPN_CATEGORY: FirewallaNetworkKind.VPN,
    # Router-Mode boxes segment their LANs either as a LAG ``bond`` or as
    # per-network ``bridge`` interfaces (each carrying direct ports and/or
    # tagged VLAN members). Both are LAN networks.
    _RAW_BRIDGE_CATEGORY: FirewallaNetworkKind.LAN,
    # A ``wlan`` entry is a wireless WAN uplink (the box joins a Wi-Fi
    # network as a client), so it is a WAN only when ``meta.type == "wan"``.
    _RAW_WLAN_CATEGORY: FirewallaNetworkKind.WAN,
}


def _normalized_bool(value: object) -> bool | None:
    """Return a boolean when one is present."""
    return normalized_bool(value)


def _normalized_string_tuple(value: object) -> tuple[str, ...]:
    """Return a tuple of stripped strings from a string or list of strings."""
    if isinstance(value, str):
        stripped_value = value.strip()
        return (stripped_value,) if stripped_value else ()
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                items.append(item.strip())
        return tuple(items)
    return ()


def _normalized_dict(value: object) -> dict[str, object] | None:
    """Return a JSON-like dict when one is present."""
    if not isinstance(value, dict):
        return None
    return value or None


def _resolve_network_display_name(raw_profile: dict[str, object]) -> str | None:
    """Resolve the best available display name from one network profile."""
    for key in (_RAW_DESC_KEY, _RAW_NAME_KEY, _RAW_INTF_KEY):
        value = raw_profile.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _collect_network_interface_entries(
    raw_category: dict[str, object],
    *,
    category: str,
    known_kind: FirewallaNetworkKind | None,
    networks: dict[str, FirewallaNetwork],
) -> None:
    """Collect one ``networkConfig.interface`` category into the network map."""
    for interface_name, raw_entry in raw_category.items():
        if not isinstance(interface_name, str) or not interface_name:
            continue
        if not isinstance(raw_entry, dict):
            continue

        raw_meta = raw_entry.get(_RAW_META_KEY)
        network_id = None
        network_name = interface_name
        meta_type = None
        if isinstance(raw_meta, dict):
            meta_uuid = raw_meta.get(_RAW_UUID_KEY)
            if isinstance(meta_uuid, str) and meta_uuid:
                network_id = meta_uuid
            meta_name = normalized_string(raw_meta.get(_RAW_NAME_KEY))
            if meta_name is not None:
                network_name = meta_name
            meta_type = normalized_string(raw_meta.get(_RAW_TYPE_KEY))

        # Unnamed physical ports (eth1/2/3 on the Gold) carry no friendly
        # identity and are not user-facing networks; skip them. A phy port is
        # only a WAN network when the box marks it as such via meta.type.
        if network_id is None:
            continue
        if known_kind is None:
            # The registry keys are open-ended: a box can expose a transport
            # category that has not been reverse-engineered yet (a PPPoE
            # uplink, for example). Fall back to the box's own coarse
            # ``meta.type``, and publish nothing when even that is missing so
            # an unclassifiable entry is never invented as a network.
            if meta_type not in (_RAW_TYPE_WAN, _RAW_TYPE_LAN):
                continue
            kind = (
                FirewallaNetworkKind.WAN
                if meta_type == _RAW_TYPE_WAN
                else FirewallaNetworkKind.LAN
            )
        else:
            if known_kind is FirewallaNetworkKind.WAN and meta_type != _RAW_TYPE_WAN:
                continue
            kind = known_kind

        networks[network_id] = FirewallaNetwork(
            uuid=network_id,
            name=network_name,
            kind=kind,
            interface_name=interface_name,
            interface_category=category,
            vlan_id=normalized_int(raw_entry.get(_RAW_VID_KEY)),
            ports=_normalized_string_tuple(raw_entry.get(_RAW_INTF_KEY)),
            enabled=_normalized_bool(raw_entry.get(_RAW_ENABLED_KEY)),
            ipv4_addresses=_normalized_string_tuple(raw_entry.get(_RAW_IPV4_KEY)),
        )


def _resolved_wan_name(
    network: FirewallaNetwork,
    *,
    wan_name: str | None,
    interface_name: str | None,
) -> str:
    """Return the display name to keep for one WAN identity.

    A name that only repeats the uuid or the interface name is a fallback
    rather than a label, so the WAN profile name replaces it; a real display
    name is kept.
    """
    if wan_name is None:
        return network.name
    if network.name in (network.uuid, network.interface_name, interface_name):
        return wan_name
    return network.name


def _resolved_profile_kind(
    raw_profile: dict[str, object],
    *,
    existing: FirewallaNetwork | None,
) -> FirewallaNetworkKind:
    """Return the kind one ``networkProfiles`` entry states for its network.

    The profile's ``type`` is the box's own declaration, and it is the only WAN
    signal available for an uplink that ``networkConfig.interface`` omits: on a
    real box every WAN profile carries ``type: "wan"`` together with the
    link-state keys (``active``, ``ready``, ``pendingTest``) that a LAN or VPN
    profile never has. A network the registry already classified keeps that
    classification, because the registry is more specific than ``lan``/``wan``.
    """
    if existing is not None:
        return existing.kind
    if normalized_string(raw_profile.get(_RAW_TYPE_KEY)) == _RAW_TYPE_WAN:
        return FirewallaNetworkKind.WAN
    return FirewallaNetworkKind.LAN


def _iter_declared_wans(
    data: dict[str, object],
) -> Iterator[tuple[str, str | None, str | None]]:
    """Yield ``(wan_uuid, wan_name, interface_name)`` for every WAN declaration.

    Only the top-level ``network`` block qualifies: it describes the WAN the box
    is routing through right now (``uuid``, ``name``, ``desc``, ``type: "wan"``).

    ``wanStatus`` carries the same information, but it appears **only inside
    monitor-event labels** (``dualwan_state``), never in an init payload, so it
    belongs to the event path and not here. Reading it from this payload was
    verified dead on a live box (2026-11-08).
    """
    raw_network = data.get(_RAW_NETWORK_BLOCK_KEY)
    if not isinstance(raw_network, dict):
        return
    wan_uuid = normalized_string(raw_network.get(_RAW_UUID_KEY))
    if wan_uuid is None:
        return
    if normalized_string(raw_network.get(_RAW_TYPE_KEY)) != _RAW_TYPE_WAN:
        return
    yield (
        wan_uuid,
        normalized_string(raw_network.get(_RAW_DESC_KEY)),
        normalized_string(raw_network.get(_RAW_NAME_KEY)),
    )


def _enrich_wan_identity(
    data: dict[str, object],
    networks: dict[str, FirewallaNetwork],
) -> None:
    """Make the box's WAN declarations authoritative for WAN identity.

    The interface-category registry is the primary inventory, but it only
    describes what the box publishes there: a PPPoE uplink can be missing from
    it while the box still declares it a WAN elsewhere. Those identities were
    dropped whenever an earlier pass had already named the network, which
    published the uplink as a LAN. A declaration states directly that the
    interface carries WAN, so it upgrades the kind, supplies the missing
    interface name, and adopts the declared name where the current one is only
    a fallback. Everything else the earlier passes resolved is preserved.
    """
    for wan_uuid, wan_name, interface_name in _iter_declared_wans(data):
        existing = networks.get(wan_uuid)
        if existing is None:
            networks[wan_uuid] = FirewallaNetwork(
                uuid=wan_uuid,
                name=wan_name or interface_name or wan_uuid,
                kind=FirewallaNetworkKind.WAN,
                interface_name=interface_name,
            )
            continue
        networks[wan_uuid] = replace(
            existing,
            kind=FirewallaNetworkKind.WAN,
            interface_name=existing.interface_name or interface_name,
            name=_resolved_wan_name(
                existing,
                wan_name=wan_name,
                interface_name=interface_name,
            ),
        )


def _apply_wan_event_names(
    data: dict[str, object],
    networks: dict[str, FirewallaNetwork],
) -> None:
    """Adopt the WAN display names carried by the box's monitor-event labels.

    The init payload's profile entries have no display name, so a WAN can only
    be known by its uuid or interface until the box names it. The WAN monitor
    events carry ``wan_intf_uuid`` beside ``wan_intf_name``, which is the label
    the app shows and the string a user types. It is applied only as a name —
    never to classify or create a network, since an event can outlive the WAN
    it describes.
    """
    for wan_uuid, wan_name in _iter_wan_event_names(data):
        existing = networks.get(wan_uuid)
        if existing is None or existing.kind is not FirewallaNetworkKind.WAN:
            continue
        networks[wan_uuid] = replace(
            existing,
            name=_resolved_wan_name(
                existing,
                wan_name=wan_name,
                interface_name=None,
            ),
        )


def _iter_wan_event_names(
    data: dict[str, object],
) -> Iterator[tuple[str, str | None]]:
    """Yield ``(wan_uuid, wan_name)`` from the payload's event blocks.

    Only the blocks that carry events are read, and only their top level: each
    event is ``{event_key: {labels: {...}}}``. Walking the whole payload instead
    cost ~9 ms per call against ~0.2 ms here, and this runs on every
    ``get_networks()`` read.
    """
    for block_key in _WAN_NAME_EVENT_KEYS:
        raw_blocks = data.get(block_key)
        if isinstance(raw_blocks, list):
            events: Iterator[object] = iter(raw_blocks)
        elif isinstance(raw_blocks, dict):
            events = iter(raw_blocks.values())
        else:
            continue

        for raw_event in events:
            if not isinstance(raw_event, dict):
                continue
            raw_labels = raw_event.get(_RAW_LABELS_KEY)
            if not isinstance(raw_labels, dict):
                continue
            wan_uuid = normalized_string(raw_labels.get(_RAW_WAN_INTERFACE_UUID_KEY))
            wan_name = normalized_string(raw_labels.get(_RAW_WAN_INTERFACE_NAME_KEY))
            if wan_uuid is not None and wan_name is not None:
                yield wan_uuid, wan_name


def wan_routing(data: dict[str, object]) -> FirewallaWanRouting | None:
    """Return how the box distributes traffic across its WAN uplinks.

    ``networkConfig.routing.global.default`` is the app's multi-WAN setting, and
    ``type`` is what the box calls the mode: ``primary_standby`` names a
    ``viaIntf`` primary and a ``viaIntf2`` standby with a ``failback`` toggle,
    while ``load_balance`` carries ``nextHops`` with a ``weight`` per interface
    and names no primary at all. The two shapes are disjoint, so only the fields
    the stated mode actually uses are populated.

    Absent when the payload has no routing block, which is the honest answer for
    a box that states no preference rather than a guess at one.
    """
    raw_default = _raw_default_route(data)
    if raw_default is None:
        return None
    mode = normalized_string(raw_default.get(_RAW_TYPE_KEY))
    if mode is None:
        return None

    if mode == _WAN_MODE_PRIMARY_STANDBY:
        return FirewallaWanRouting(
            mode=mode,
            primary=normalized_string(raw_default.get(_RAW_VIA_INTF_KEY)),
            standby=normalized_string(raw_default.get(_RAW_VIA_INTF2_KEY)),
            failback=normalized_bool(raw_default.get(_RAW_FAILBACK_KEY)),
        )

    if mode == _WAN_MODE_LOAD_BALANCE:
        return FirewallaWanRouting(
            mode=mode,
            traffic_share_percent=_traffic_share_percent(
                raw_default.get(_RAW_NEXT_HOPS_KEY)
            ),
        )

    return FirewallaWanRouting(mode=mode)


def _raw_default_route(data: dict[str, object]) -> dict[str, object] | None:
    """Return ``networkConfig.routing.global.default`` when the box states one."""
    raw_network_config = data.get(_RAW_NETWORK_CONFIG_KEY)
    if not isinstance(raw_network_config, dict):
        return None
    raw_routing = raw_network_config.get(_RAW_ROUTING_KEY)
    if not isinstance(raw_routing, dict):
        return None
    raw_global = raw_routing.get(_RAW_GLOBAL_KEY)
    if not isinstance(raw_global, dict):
        return None
    raw_default = raw_global.get(_RAW_DEFAULT_ROUTE_KEY)
    return raw_default if isinstance(raw_default, dict) else None


def _traffic_share_percent(raw_next_hops: object) -> dict[str, int] | None:
    """Return the declared load-balance share per interface, if stated."""
    if not isinstance(raw_next_hops, list):
        return None
    share: dict[str, int] = {}
    for raw_hop in raw_next_hops:
        if not isinstance(raw_hop, dict):
            continue
        interface_name = normalized_string(raw_hop.get(_RAW_VIA_INTF_KEY))
        weight = normalized_int(raw_hop.get(_RAW_WEIGHT_KEY))
        if interface_name is None or weight is None:
            continue
        share[interface_name] = weight
    return share or None


def primary_wan_interface_name(data: dict[str, object]) -> str | None:
    """Return the interface the box is configured to route through first.

    Read from :func:`wan_routing` so there is one parser for the block. Only the
    failover mode names a primary; load balance distributes across every
    interface and has none, so it reports ``None`` rather than electing the first
    next hop.

    It outranks any ordering derived from interface names, which cannot
    distinguish a primary from a standby.
    """
    routing = wan_routing(data)
    return routing.primary if routing is not None else None


def wan_role(
    routing: FirewallaWanRouting | None,
    interface_name: str | None,
) -> str | None:
    """Return a WAN's role under the active mode, or ``None`` when it has none.

    Failover names a ``primary`` and a ``standby``; load balance treats every
    participating interface as an equal member of the routing set, so each one is
    ``shared``. That is deliberately a stated role rather than an omission: a
    reader should never have to consult the mode to learn that a load-balanced
    WAN is load balanced.

    A single-WAN box has nothing to be primary, standby or shared relative to, so
    it reports ``None``, as does any mode this integration has not verified.
    """
    if routing is None or interface_name is None:
        return None
    if routing.mode == _WAN_MODE_PRIMARY_STANDBY:
        if interface_name == routing.primary:
            return WAN_ROLE_PRIMARY
        if interface_name == routing.standby:
            return WAN_ROLE_STANDBY
        return None
    if routing.mode == _WAN_MODE_LOAD_BALANCE:
        return WAN_ROLE_SHARED
    return None


def active_wan_interface_name(data: dict[str, object]) -> str | None:
    """Return the interface of the WAN the box is routing through right now.

    The top-level ``network`` block is the box's own answer to "which WAN is
    carrying traffic": it names the interface, the label, the address, and its
    link state. Under failover it follows the primary, and when the primary has
    failed it follows the standby, which is what makes it the failover signal.

    Under load balance it still names one interface — the first next hop — so it
    is the box's current choice rather than a claim that only one WAN is used.
    """
    raw_network = data.get(_RAW_NETWORK_BLOCK_KEY)
    if not isinstance(raw_network, dict):
        return None
    if normalized_string(raw_network.get(_RAW_TYPE_KEY)) != _RAW_TYPE_WAN:
        return None
    return normalized_string(raw_network.get(_RAW_NAME_KEY))


def active_wan_ipv4_address(data: dict[str, object]) -> str | None:
    """Return the box-level IPv4 the app reports for the appliance.

    Read from the top-level ``network`` block rather than derived, because that
    block is the address the box itself reports for the WAN it is using. It is
    preferred over ``publicIp``, which some models fill with a DNS resolver
    address instead of the WAN address.
    """
    raw_network = data.get(_RAW_NETWORK_BLOCK_KEY)
    if not isinstance(raw_network, dict):
        return None
    if normalized_string(raw_network.get(_RAW_TYPE_KEY)) != _RAW_TYPE_WAN:
        return None
    address = normalized_string(raw_network.get(_RAW_IP_ADDRESS_KEY))
    if address is not None:
        return address
    addresses = _normalized_string_tuple(raw_network.get(_RAW_IP4_ADDRESSES_KEY))
    return addresses[0] if addresses else None


def _wan_health_failures(raw_failures: object) -> tuple[str, ...]:
    """Return the failure names from one WAN health entry.

    The box lists them as ``[{"type": "carrier"}]``, and ``type`` is the part
    that says what broke, so it is what gets published. A bare string is accepted
    too, because the same field is a plain list elsewhere in the payload.
    """
    if not isinstance(raw_failures, list):
        return ()
    failures: list[str] = []
    for raw_failure in raw_failures:
        if isinstance(raw_failure, str):
            name = raw_failure.strip()
            if name:
                failures.append(name)
            continue
        if not isinstance(raw_failure, dict):
            continue
        failure_type = normalized_string(raw_failure.get(_RAW_TYPE_KEY))
        if failure_type is not None:
            failures.append(failure_type)
    return tuple(failures)


def wan_health_by_interface(
    data: dict[str, object],
) -> dict[str, dict[str, object]]:
    """Return the box's own per-WAN health test, keyed by interface name.

    ``wanTestResult`` is a separate block from the per-WAN profile: the profile
    states whether the WAN is in the routing set, while this states whether the
    link actually works — carrier, DNS, ping, HTTP, and the failures recorded
    when one of them does not. Both are needed to tell "standby, idle, healthy"
    from "standby, idle, broken".

    Every interface shares one ``ts`` because the box tests them together, so the
    reading is a single snapshot rather than per-WAN samples.
    """
    raw_result = data.get(_RAW_WAN_TEST_RESULT_KEY)
    if not isinstance(raw_result, dict):
        return {}
    raw_wans = raw_result.get(_RAW_WANS_KEY)
    if not isinstance(raw_wans, dict):
        return {}

    shared_timestamp = normalized_int(raw_result.get(_RAW_TS_KEY))
    health: dict[str, dict[str, object]] = {}
    for interface_name, raw_entry in raw_wans.items():
        if not isinstance(interface_name, str) or not isinstance(raw_entry, dict):
            continue
        raw_http = raw_entry.get(_RAW_HTTP_KEY)
        health[interface_name] = {
            "tested_at_timestamp": normalized_int(raw_entry.get(_RAW_TS_KEY))
            or shared_timestamp,
            "carrier": normalized_bool(raw_entry.get(_RAW_CARRIER_KEY)),
            "dns": normalized_bool(raw_entry.get(_RAW_DNS_KEY)),
            "ping": normalized_bool(raw_entry.get(_RAW_PING_KEY)),
            "http_status": (
                normalized_int(raw_http.get(_RAW_STATUS_CODE_KEY))
                if isinstance(raw_http, dict)
                else None
            ),
            "failures": _wan_health_failures(raw_entry.get(_RAW_FAILURES_KEY)),
            "recent_down_at_timestamp": normalized_int(
                raw_entry.get(_RAW_RECENT_DOWN_TIME_KEY)
            ),
        }
    return health


def _bridge_member_interface_names(data: dict[str, object]) -> set[str]:
    """Return interface names referenced as members by any bridge."""
    raw_network_config = data.get(_RAW_NETWORK_CONFIG_KEY)
    if not isinstance(raw_network_config, dict):
        return set()
    raw_interfaces = raw_network_config.get(_RAW_INTERFACE_KEY)
    if not isinstance(raw_interfaces, dict):
        return set()

    member_names: set[str] = set()
    raw_bridges = raw_interfaces.get(_RAW_BRIDGE_CATEGORY)
    if not isinstance(raw_bridges, dict):
        return member_names
    for raw_entry in raw_bridges.values():
        if not isinstance(raw_entry, dict):
            continue
        for member in _normalized_string_tuple(raw_entry.get(_RAW_INTF_KEY)):
            member_names.add(member)
    return member_names


def build_network_inventory(data: dict[str, object]) -> tuple[FirewallaNetwork, ...]:
    """Return the unified network identities from a raw init payload.

    Networks are discovered from the ``networkConfig.interface`` registry,
    which is category-keyed (``phy``/``bond``/``bridge``/``vlan``/
    ``wireguard``/``amneziawg``/``openvpn``). Known category keys drive the
    network kind; an unknown key is classified by the box's coarse
    ``meta.type``. Names prefer the registry ``meta.name``, then
    ``networkProfiles`` display-name fields, then the interface name. Finally
    the box's own WAN declarations are authoritative for WAN identity, so an
    uplink the registry does not describe (a PPPoE interface, for example) is
    still published as a WAN.
    """
    networks: dict[str, FirewallaNetwork] = {}

    raw_network_config = data.get(_RAW_NETWORK_CONFIG_KEY)
    if isinstance(raw_network_config, dict):
        raw_interfaces = raw_network_config.get(_RAW_INTERFACE_KEY)
        if isinstance(raw_interfaces, dict):
            for category, raw_category in raw_interfaces.items():
                if not isinstance(category, str) or not isinstance(raw_category, dict):
                    continue
                _collect_network_interface_entries(
                    raw_category,
                    category=category,
                    known_kind=_NETWORK_KIND_BY_INTERFACE_CATEGORY.get(category),
                    networks=networks,
                )

    # A VLAN referenced by a bridge's ``intf`` is transport for that bridge
    # (e.g. ``eth3.101`` tagging the Guest bridge), not a standalone network;
    # only VLANs no bridge references are user-facing VLAN networks.
    bridge_member_interfaces = _bridge_member_interface_names(data)
    for network_id in [
        network_id
        for network_id, network in networks.items()
        if network.kind is FirewallaNetworkKind.VLAN
        and network.interface_name in bridge_member_interfaces
    ]:
        networks.pop(network_id)

    # Normalize names from networkProfiles for the same uuids where the registry
    # did not expose a friendlier display name.
    raw_network_profiles = data.get(_RAW_NETWORK_PROFILES_KEY)
    if isinstance(raw_network_profiles, dict):
        for network_id, raw_profile in raw_network_profiles.items():
            if not isinstance(network_id, str) or not network_id:
                continue
            if not isinstance(raw_profile, dict):
                continue

            existing = networks.get(network_id)
            if existing is not None and existing.name != network_id:
                continue
            display_name = _resolve_network_display_name(raw_profile)
            if not display_name or display_name == network_id:
                continue
            networks[network_id] = FirewallaNetwork(
                uuid=network_id,
                name=display_name,
                kind=_resolved_profile_kind(raw_profile, existing=existing),
                # The profile states the interface too, and it is the only
                # interface name available for a network the registry omits.
                # Without it the port, DHCP and relay lookups all skip the
                # network, which is what a PPPoE uplink suffered from.
                interface_name=(
                    existing.interface_name if existing is not None else None
                )
                or normalized_string(raw_profile.get(_RAW_INTF_KEY)),
            )

    # The box's own WAN declarations are authoritative for WAN identity, and
    # cover an uplink the registry above does not describe.
    _enrich_wan_identity(data, networks)
    _apply_wan_event_names(data, networks)

    _enrich_network_addressing(data, networks)
    _enrich_network_dhcp(data, networks)
    _enrich_network_advanced_options(data, networks)
    _enrich_network_device_counts(data, networks)
    _enrich_network_ports(data, networks)

    return tuple(
        sorted(
            networks.values(),
            key=lambda network: (network.name.casefold(), network.uuid),
        )
    )


def _enrich_network_addressing(
    data: dict[str, object],
    networks: dict[str, FirewallaNetwork],
) -> None:
    """Populate addressing fields from ``networkProfiles`` for each network."""
    raw_network_profiles = data.get(_RAW_NETWORK_PROFILES_KEY)
    if not isinstance(raw_network_profiles, dict):
        return

    for network_id, raw_profile in raw_network_profiles.items():
        if not isinstance(network_id, str) or not network_id:
            continue
        if not isinstance(raw_profile, dict):
            continue
        existing = networks.get(network_id)
        if existing is None:
            continue

        networks[network_id] = replace(
            existing,
            ipv4_addresses=(
                _normalized_string_tuple(raw_profile.get(_RAW_IPV4_KEY))
                or existing.ipv4_addresses
            ),
            ipv4_subnets=_normalized_string_tuple(
                raw_profile.get(_RAW_IPV4_SUBNETS_KEY)
            )
            or _normalized_string_tuple(raw_profile.get(_RAW_IPV4_SUBNET_KEY)),
            ipv6_addresses=_normalized_string_tuple(raw_profile.get(_RAW_IPV6_KEY)),
            ipv6_subnets=_normalized_string_tuple(
                raw_profile.get(_RAW_IPV6_SUBNETS_KEY)
            ),
            gateway=normalized_string(raw_profile.get(_RAW_GATEWAY_KEY)),
            dns_servers=_normalized_string_tuple(raw_profile.get(_RAW_DNS_KEY)),
            # Only WAN profiles carry these, so a LAN/VLAN/VPN network keeps them
            # absent rather than reporting a link state it was never given.
            active=(
                _normalized_bool(raw_profile.get(_RAW_ACTIVE_KEY))
                if existing.kind is FirewallaNetworkKind.WAN
                else existing.active
            ),
            ready=(
                _normalized_bool(raw_profile.get(_RAW_READY_KEY))
                if existing.kind is FirewallaNetworkKind.WAN
                else existing.ready
            ),
        )


def _enrich_network_ports(
    data: dict[str, object],
    networks: dict[str, FirewallaNetwork],
) -> None:
    """Resolve per-network physical ports from the interface registry.

    A physical WAN port (``phy``/``wlan``) is the interface itself (its
    device name). A bond/bridge lists its member interfaces in ``intf``
    (direct ports and/or tagged VLAN members). A VLAN references its parent
    interface in ``intf`` (``bond0``/``eth3``); its real ports are the
    parent's members. VPNs carry no ports. Each member is dereferenced
    through parent chains (bridge → VLAN → physical port) to concrete ports.
    """
    raw_network_config = data.get(_RAW_NETWORK_CONFIG_KEY)
    if not isinstance(raw_network_config, dict):
        return
    raw_interfaces = raw_network_config.get(_RAW_INTERFACE_KEY)
    if not isinstance(raw_interfaces, dict):
        return

    # Resolve member ports per interface once, so a VLAN can dereference its
    # ``intf`` parent (a bond or a phy port) to the concrete member set. Also
    # record each tagged interface's vid so a bridge can surface the VLAN of
    # its tagged members.
    parent_members: dict[str, tuple[str, ...]] = {}
    member_vlan_ids: dict[str, int] = {}
    for raw_category in raw_interfaces.values():
        if not isinstance(raw_category, dict):
            continue
        for interface_name, raw_entry in raw_category.items():
            if not isinstance(interface_name, str) or not interface_name:
                continue
            if not isinstance(raw_entry, dict):
                continue
            direct = _normalized_string_tuple(raw_entry.get(_RAW_INTF_KEY))
            parent_members[interface_name] = direct
            vlan_id = normalized_int(raw_entry.get(_RAW_VID_KEY))
            if vlan_id is not None:
                member_vlan_ids[interface_name] = vlan_id

    def resolve_members(interface_name: str) -> tuple[str, ...]:
        """Return the concrete member ports for one interface reference.

        A member may itself be a parent reference (a bond/bridge, or a tagged
        VLAN interface like ``eth3.101`` whose parent is ``eth3``), so each
        member is dereferenced recursively to the physical port set.
        """
        direct = parent_members.get(interface_name)
        if not direct:
            return ()
        resolved: list[str] = []
        for member in direct:
            nested = parent_members.get(member)
            if nested:
                resolved.extend(nested)
            else:
                resolved.append(member)
        # Deduplicate while preserving order.
        return tuple(dict.fromkeys(resolved))

    def resolve_vlan_id(interface_name: str) -> int | None:
        """Return the VLAN id of a network from its tagged members.

        A bridge/bond network surfaces the vid of its tagged member(s) when
        present (e.g. ``br3`` Home carries ``eth3.100`` → 100); an untagged
        network has no VLAN. An explicit vid on the network itself wins.
        """
        for member in parent_members.get(interface_name, ()):
            vlan_id = member_vlan_ids.get(member)
            if vlan_id is not None:
                return vlan_id
        return None

    for network in networks.values():
        interface_name = network.interface_name
        if interface_name is None:
            continue

        if network.kind is FirewallaNetworkKind.WAN:
            # A phy/wlan WAN is itself the port.
            ports: tuple[str, ...] = (interface_name,)
            vlan_id = network.vlan_id
        else:
            ports = resolve_members(interface_name)
            # Only fill an unset vlan_id from tagged members; an explicit vid
            # (standalone VLAN/bond) is preserved.
            vlan_id = network.vlan_id or resolve_vlan_id(interface_name)

        networks[network.uuid] = replace(
            network,
            vlan_id=vlan_id,
            ports=ports,
        )


def _enrich_network_dhcp(
    data: dict[str, object],
    networks: dict[str, FirewallaNetwork],
) -> None:
    """Populate DHCP config from ``networkConfig.dhcp`` for each network."""
    raw_network_config = data.get(_RAW_NETWORK_CONFIG_KEY)
    if not isinstance(raw_network_config, dict):
        return
    raw_dhcp_by_interface = raw_network_config.get(_RAW_DHCP_KEY)
    if not isinstance(raw_dhcp_by_interface, dict):
        return

    for network in networks.values():
        interface_name = network.interface_name
        if interface_name is None:
            continue
        raw_dhcp = raw_dhcp_by_interface.get(interface_name)
        if not isinstance(raw_dhcp, dict):
            continue

        raw_range = raw_dhcp.get(_RAW_RANGE_KEY)
        range_start = None
        range_end = None
        if isinstance(raw_range, dict):
            range_start = normalized_string(raw_range.get(_RAW_FROM_KEY))
            range_end = normalized_string(raw_range.get(_RAW_TO_KEY))

        dhcp_gateway = normalized_string(raw_dhcp.get(_RAW_GATEWAY_KEY))
        gateway = network.gateway or dhcp_gateway

        networks[network.uuid] = replace(
            network,
            gateway=gateway,
            dhcp=FirewallaNetworkDhcpConfig(
                gateway=dhcp_gateway,
                subnet_mask=normalized_string(raw_dhcp.get(_RAW_SUBNET_MASK_KEY)),
                lease_seconds=normalized_int(raw_dhcp.get(_RAW_LEASE_KEY)),
                range_start=range_start,
                range_end=range_end,
                name_servers=_normalized_string_tuple(
                    raw_dhcp.get(_RAW_NAMESERVERS_KEY)
                ),
                search_domains=_normalized_string_tuple(
                    raw_dhcp.get(_RAW_SEARCH_DOMAIN_KEY)
                ),
                extra_options=_normalized_dict(raw_dhcp.get(_RAW_EXTRA_OPTIONS_KEY)),
            ),
        )


def _enrich_network_advanced_options(
    data: dict[str, object],
    networks: dict[str, FirewallaNetwork],
) -> None:
    """Populate mDNS/SSDP relay and Block ICMP from ``networkConfig``."""
    raw_network_config = data.get(_RAW_NETWORK_CONFIG_KEY)
    if not isinstance(raw_network_config, dict):
        return

    raw_mdns = raw_network_config.get(_RAW_MDNS_REFLECTOR_KEY)
    raw_icmp = raw_network_config.get(_RAW_ICMP_KEY)
    raw_mroute = raw_network_config.get(_RAW_MROUTE_KEY)

    for network in networks.values():
        interface_name = network.interface_name
        if interface_name is None:
            continue

        mdns_relay = network.mdns_relay
        if isinstance(raw_mdns, dict):
            raw_entry = raw_mdns.get(interface_name)
            if isinstance(raw_entry, dict):
                mdns_relay = _normalized_bool(raw_entry.get(_RAW_ENABLED_KEY))

        block_icmp = network.block_icmp
        if isinstance(raw_icmp, dict):
            raw_entry = raw_icmp.get(interface_name)
            if isinstance(raw_entry, dict):
                echo_request = _normalized_bool(raw_entry.get(_RAW_ECHO_REQUEST_KEY))
                # ``echoRequest`` means "respond to ICMP echo (ping)"; the box
                # clears it when the app's Block ICMP toggle is on, so it is
                # the inverse of block_icmp.
                if echo_request is not None:
                    block_icmp = not echo_request

        # SSDP relay is an explicit app toggle; the box only emits an mroute
        # entry for interfaces where the SSDP multicast route is active, so
        # the absence of an entry means the relay is off.
        ssdp_relay = False
        if isinstance(raw_mroute, dict):
            raw_entry = raw_mroute.get(interface_name)
            if isinstance(raw_entry, dict):
                ssdp_relay = _has_ssdp_route(raw_entry)

        networks[network.uuid] = replace(
            network,
            mdns_relay=mdns_relay,
            ssdp_relay=ssdp_relay,
            block_icmp=block_icmp,
        )


def _has_ssdp_route(raw_mroute_entry: dict[str, object]) -> bool:
    """Return whether an mroute entry carries the SSDP multicast route."""
    raw_routes = raw_mroute_entry.get(_RAW_ROUTES_KEY)
    if not isinstance(raw_routes, list):
        return False
    for raw_route in raw_routes:
        if not isinstance(raw_route, dict):
            continue
        if raw_route.get(_RAW_CIDR_KEY) == _SSDP_MULTICAST_CIDR:
            return True
    return False


def _is_firewalla_box(raw_host: dict[str, object]) -> bool:
    """Return whether one raw host identifies the Firewalla appliance itself.

    The box exposes itself as a host record whose vendor marker is the
    Firewalla vendor. Its raw ``intf`` (the network it last served as a
    gateway) is volatile and meaningless for a per-network device count, so it
    is excluded from client counts.
    """
    vendor = raw_host.get(_RAW_HOST_MAC_VENDOR_KEY)
    if not isinstance(vendor, str):
        return False
    return _FIREWALLA_VENDOR_MARKER in vendor.strip().casefold()


def _enrich_network_device_counts(
    data: dict[str, object],
    networks: dict[str, FirewallaNetwork],
) -> None:
    """Populate per-network client device counts from the raw host inventory.

    The count is the number of non-Firewalla-vendor hosts whose network
    assignment (``host.intf``) matches the network uuid. The Firewalla box is
    excluded because it is the gateway device, not a client on any one network.
    """
    raw_hosts = data.get(_RAW_HOSTS_KEY)
    if not isinstance(raw_hosts, list):
        return

    counts: dict[str, int] = {}
    for raw_host in raw_hosts:
        if not isinstance(raw_host, dict):
            continue
        if _is_firewalla_box(raw_host):
            continue
        interface_id = raw_host.get(_RAW_HOST_INTF_KEY)
        if not isinstance(interface_id, str) or not interface_id:
            continue
        counts[interface_id] = counts.get(interface_id, 0) + 1

    for network in networks.values():
        device_count = counts.get(network.uuid)
        if device_count is None:
            continue
        networks[network.uuid] = replace(network, device_host_count=device_count)
