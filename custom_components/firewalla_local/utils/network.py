"""Unified Firewalla network inventory normalization helpers."""

from __future__ import annotations

from typing import Final

from ..models import (
    FirewallaNetwork,
    FirewallaNetworkDhcpConfig,
    FirewallaNetworkKind,
)

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
_RAW_ENABLED_KEY: Final = "enabled"
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
_RAW_NETWORK_MONITOR_DATA_KEY: Final = "networkMonitorData"
_RAW_WAN_STATUS_KEY: Final = "wanStatus"
_RAW_WAN_INTERFACE_NAME_KEY: Final = "wan_intf_name"
_RAW_WAN_INTERFACE_UUID_KEY: Final = "wan_intf_uuid"
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


def _normalized_network_name(value: object) -> str | None:
    """Return a stripped network name when one is present."""
    if not isinstance(value, str):
        return None
    stripped_value = value.strip()
    return stripped_value or None


def _normalized_int(value: object) -> int | None:
    """Return an integer when one is present."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _normalized_bool(value: object) -> bool | None:
    """Return a boolean when one is present."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        stripped_value = value.strip().casefold()
        if stripped_value == "true":
            return True
        if stripped_value == "false":
            return False
    return None


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
    kind: FirewallaNetworkKind,
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
            meta_name = _normalized_network_name(raw_meta.get(_RAW_NAME_KEY))
            if meta_name is not None:
                network_name = meta_name
            meta_type = _normalized_network_name(raw_meta.get(_RAW_TYPE_KEY))

        # Unnamed physical ports (eth1/2/3 on the Gold) carry no friendly
        # identity and are not user-facing networks; skip them. A phy port is
        # only a WAN network when the box marks it as such via meta.type.
        if network_id is None:
            continue
        if kind is FirewallaNetworkKind.WAN and meta_type != _RAW_TYPE_WAN:
            continue

        networks[network_id] = FirewallaNetwork(
            uuid=network_id,
            name=network_name,
            kind=kind,
            interface_name=interface_name,
            vlan_id=_normalized_int(raw_entry.get(_RAW_VID_KEY)),
            ports=_normalized_string_tuple(raw_entry.get(_RAW_INTF_KEY)),
            enabled=_normalized_bool(raw_entry.get(_RAW_ENABLED_KEY)),
            ipv4_addresses=_normalized_string_tuple(raw_entry.get(_RAW_IPV4_KEY)),
        )


def _collect_wan_status_fallback(
    raw_value: object,
    networks: dict[str, FirewallaNetwork],
) -> None:
    """Recursively collect WAN identities from any nested wanStatus block."""
    if isinstance(raw_value, dict):
        raw_status = raw_value.get(_RAW_WAN_STATUS_KEY)
        if isinstance(raw_status, dict):
            for _port_key, raw_port in raw_status.items():
                if not isinstance(raw_port, dict):
                    continue
                wan_uuid = raw_port.get(_RAW_WAN_INTERFACE_UUID_KEY)
                if not isinstance(wan_uuid, str) or not wan_uuid:
                    continue
                wan_name = _normalized_network_name(
                    raw_port.get(_RAW_WAN_INTERFACE_NAME_KEY)
                )
                resolved_name = wan_name if wan_name is not None else wan_uuid
                existing = networks.get(wan_uuid)
                if existing is None or existing.name == wan_uuid:
                    networks[wan_uuid] = FirewallaNetwork(
                        uuid=wan_uuid,
                        name=resolved_name,
                        kind=FirewallaNetworkKind.WAN,
                    )

        for nested_value in raw_value.values():
            _collect_wan_status_fallback(nested_value, networks)
        return

    if isinstance(raw_value, list):
        for nested_value in raw_value:
            _collect_wan_status_fallback(nested_value, networks)


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
    ``wireguard``/``amneziawg``/``openvpn``). The category key drives the
    network kind. Names prefer the registry ``meta.name``, then
    ``networkProfiles`` display-name fields, then the interface name. WAN
    identities missing from the registry fall back to
    ``networkMonitorData.wanStatus``.
    """
    networks: dict[str, FirewallaNetwork] = {}

    raw_network_config = data.get(_RAW_NETWORK_CONFIG_KEY)
    if isinstance(raw_network_config, dict):
        raw_interfaces = raw_network_config.get(_RAW_INTERFACE_KEY)
        if isinstance(raw_interfaces, dict):
            for category, kind in _NETWORK_KIND_BY_INTERFACE_CATEGORY.items():
                raw_category = raw_interfaces.get(category)
                if not isinstance(raw_category, dict):
                    continue
                _collect_network_interface_entries(raw_category, kind, networks)

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
            if existing is None or existing.name == network_id:
                display_name = _resolve_network_display_name(raw_profile)
                if display_name and display_name != network_id:
                    networks[network_id] = FirewallaNetwork(
                        uuid=network_id,
                        name=display_name,
                        kind=(
                            existing.kind
                            if existing is not None
                            else FirewallaNetworkKind.LAN
                        ),
                    )

    # Fall back to wanStatus for WAN identities the registry omitted.
    raw_monitor = data.get(_RAW_NETWORK_MONITOR_DATA_KEY)
    if isinstance(raw_monitor, dict):
        _collect_wan_status_fallback(raw_monitor, networks)

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

        networks[network_id] = FirewallaNetwork(
            uuid=existing.uuid,
            name=existing.name,
            kind=existing.kind,
            interface_name=existing.interface_name,
            vlan_id=existing.vlan_id,
            ports=existing.ports,
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
            gateway=_normalized_network_name(raw_profile.get(_RAW_GATEWAY_KEY)),
            dns_servers=_normalized_string_tuple(raw_profile.get(_RAW_DNS_KEY)),
            dhcp=existing.dhcp,
            device_host_count=existing.device_host_count,
            enabled=existing.enabled,
            mdns_relay=existing.mdns_relay,
            ssdp_relay=existing.ssdp_relay,
            block_icmp=existing.block_icmp,
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
    # ``intf`` parent (a bond or a phy port) to the concrete member set.
    parent_members: dict[str, tuple[str, ...]] = {}
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

    for network in networks.values():
        interface_name = network.interface_name
        if interface_name is None:
            continue

        if network.kind is FirewallaNetworkKind.WAN:
            # A phy/wlan WAN is itself the port.
            ports: tuple[str, ...] = (interface_name,)
        else:
            ports = resolve_members(interface_name)

        networks[network.uuid] = FirewallaNetwork(
            uuid=network.uuid,
            name=network.name,
            kind=network.kind,
            interface_name=network.interface_name,
            vlan_id=network.vlan_id,
            ports=ports,
            ipv4_addresses=network.ipv4_addresses,
            ipv4_subnets=network.ipv4_subnets,
            ipv6_addresses=network.ipv6_addresses,
            ipv6_subnets=network.ipv6_subnets,
            gateway=network.gateway,
            dns_servers=network.dns_servers,
            dhcp=network.dhcp,
            device_host_count=network.device_host_count,
            enabled=network.enabled,
            mdns_relay=network.mdns_relay,
            ssdp_relay=network.ssdp_relay,
            block_icmp=network.block_icmp,
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
            range_start = _normalized_network_name(raw_range.get(_RAW_FROM_KEY))
            range_end = _normalized_network_name(raw_range.get(_RAW_TO_KEY))

        dhcp_gateway = _normalized_network_name(raw_dhcp.get(_RAW_GATEWAY_KEY))
        gateway = network.gateway or dhcp_gateway

        networks[network.uuid] = FirewallaNetwork(
            uuid=network.uuid,
            name=network.name,
            kind=network.kind,
            interface_name=network.interface_name,
            vlan_id=network.vlan_id,
            ports=network.ports,
            ipv4_addresses=network.ipv4_addresses,
            ipv4_subnets=network.ipv4_subnets,
            ipv6_addresses=network.ipv6_addresses,
            ipv6_subnets=network.ipv6_subnets,
            gateway=gateway,
            dns_servers=network.dns_servers,
            dhcp=FirewallaNetworkDhcpConfig(
                gateway=dhcp_gateway,
                subnet_mask=_normalized_network_name(
                    raw_dhcp.get(_RAW_SUBNET_MASK_KEY)
                ),
                lease_seconds=_normalized_int(raw_dhcp.get(_RAW_LEASE_KEY)),
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
            device_host_count=network.device_host_count,
            enabled=network.enabled,
            mdns_relay=network.mdns_relay,
            ssdp_relay=network.ssdp_relay,
            block_icmp=network.block_icmp,
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

        networks[network.uuid] = FirewallaNetwork(
            uuid=network.uuid,
            name=network.name,
            kind=network.kind,
            interface_name=network.interface_name,
            vlan_id=network.vlan_id,
            ports=network.ports,
            ipv4_addresses=network.ipv4_addresses,
            ipv4_subnets=network.ipv4_subnets,
            ipv6_addresses=network.ipv6_addresses,
            ipv6_subnets=network.ipv6_subnets,
            gateway=network.gateway,
            dns_servers=network.dns_servers,
            dhcp=network.dhcp,
            device_host_count=network.device_host_count,
            enabled=network.enabled,
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
        networks[network.uuid] = FirewallaNetwork(
            uuid=network.uuid,
            name=network.name,
            kind=network.kind,
            interface_name=network.interface_name,
            vlan_id=network.vlan_id,
            ports=network.ports,
            ipv4_addresses=network.ipv4_addresses,
            ipv4_subnets=network.ipv4_subnets,
            ipv6_addresses=network.ipv6_addresses,
            ipv6_subnets=network.ipv6_subnets,
            gateway=network.gateway,
            dns_servers=network.dns_servers,
            dhcp=network.dhcp,
            device_host_count=device_count,
            enabled=network.enabled,
            mdns_relay=network.mdns_relay,
            ssdp_relay=network.ssdp_relay,
            block_icmp=network.block_icmp,
        )
