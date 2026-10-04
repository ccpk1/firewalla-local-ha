"""Pure aggregation of a flow rollup and its records into report models.

The rollup is already a summary -- the box computes it -- so nothing here re-reads
the wire. This turns one response into the sections a report presents: totals, top
destinations, the blocked breakdown, LAN peers and the per-member ranking, plus
the rule join for a record family.

**Why a separate module from ``flow_manager``.** Everything here is a pure
function over decoded rows, so it is unit-testable without a manager, a
coordinator or a box. The manager owns the orchestration -- calling the client and
handing rows in -- which is the split ``ARCHITECTURE.md`` draws between ``utils/``
(pure, no Home Assistant) and ``managers/`` (orchestration).

**One response, several views.** The rollup carries all of these at once, so the
sections are presentations of one row set rather than separate fetches. In
particular ``download`` and ``upload`` name the same destinations, so a
destination is merged across both and ranked per direction by the caller.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from ..const import (
    FLOW_UNIT_BYTES,
)
from ..models import (
    FirewallaBlockedDestination,
    FirewallaFlowDestination,
    FirewallaFlowMember,
    FirewallaFlowRecord,
    FirewallaFlowRecordSet,
    FirewallaFlowRecordView,
    FirewallaFlowRollup,
    FirewallaFlowSummary,
    FirewallaFlowTotals,
    FirewallaLocalPeer,
)
from .flow import (
    build_flow_record,
    flow_family_direction,
    flow_family_unit,
    flow_row_host_id,
    flow_row_remote_host,
    flow_row_remote_ip,
)
from .values import normalized_int, normalized_string


@dataclass(slots=True)
class _DestinationAccumulator:
    """Mutable per-destination tally while the byte families are merged."""

    download_bytes: int = 0
    upload_bytes: int = 0
    rollup_rows: int = 0
    destination_ips: set[str] = field(default_factory=set)
    device_ids: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _BlockedAccumulator:
    """Mutable per-destination tally while the blocked families are merged."""

    block_count: int = 0
    rollup_rows: int = 0
    destination_ips: set[str] = field(default_factory=set)
    device_ids: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _PeerAccumulator:
    """Mutable per-peer tally while the LAN connection families are merged."""

    connection_count: int = 0
    rollup_rows: int = 0


_RAW_ROW_COUNT_KEY: Final = "count"
_RAW_ROW_DST_MAC_KEY: Final = "dstMac"
_RAW_ROW_DEVICE_KEY: Final = "device"

_FAMILY_DOWNLOAD: Final = "download"
_FAMILY_UPLOAD: Final = "upload"
_FAMILY_LOCAL_DOWNLOAD: Final = "local:download"
_FAMILY_LOCAL_UPLOAD: Final = "local:upload"
_FAMILY_DNS_BLOCKED: Final = "dnsB"
_FAMILY_LOCAL_IN: Final = "local:in"
_FAMILY_LOCAL_OUT: Final = "local:out"

# Per-member counters, as the rollup's ``hosts`` block names them. ``:lo`` marks a
# LAN-local figure, which is a different measurement from the WAN-facing one.
_MEMBER_FIELDS: Final = {
    "download": "download_bytes",
    "upload": "upload_bytes",
    "download:lo": "local_download_bytes",
    "upload:lo": "local_upload_bytes",
    "conn": "connection_count",
    "dns": "dns_count",
    "dnsB": "blocked_dns_count",
    "ipB": "blocked_ip_count",
    "ipD": "denied_ip_count",
    "ntp": "ntp_count",
}

# Blocked families and the kind of match each represents, which the box reports as
# ``blockType`` in the public model: a DNS match or an IP one.
_BLOCKED_FAMILY_KINDS: Final = {
    "dnsB": "dns",
    "ipB:in": "ip",
    "ipB:out": "ip",
    "local:ipB:in": "ip",
    "local:ipB:out": "ip",
}

# How many destinations and members a summary keeps. The rollup already returns
# the largest first, so this bounds the report without changing the order.
_TOP_DESTINATION_LIMIT: Final = 25
_TOP_MEMBER_LIMIT: Final = 25


def summarise_rollup(
    rollup: FirewallaFlowRollup,
    *,
    device_names: Mapping[str, str] | None = None,
    device_addresses: Mapping[str, str] | None = None,
) -> FirewallaFlowSummary:
    """Build the summarized view of one rollup.

    ``device_names`` / ``device_addresses`` are optional host-inventory lookups;
    a member whose id has no inventory entry keeps ``None``, which is the honest
    answer for a device id that is not a host.
    """
    names = device_names or {}
    addresses = device_addresses or {}

    return FirewallaFlowSummary(
        window=rollup.window,
        totals=_summarise_totals(rollup.families),
        top_download=_rank_destinations(
            _aggregate_destinations(rollup.families, "download"),
            by="download_bytes",
        ),
        top_upload=_rank_destinations(
            _aggregate_destinations(rollup.families, "upload"),
            by="upload_bytes",
        ),
        blocked=_rank_blocked(_aggregate_blocked(rollup.families)),
        local_peers=_aggregate_local_peers(rollup.families),
        top_members=_summarise_members(rollup.hosts, names=names, addresses=addresses),
        family_row_counts={
            family: len(rows) for family, rows in rollup.families.items()
        },
    )


def build_record_view(
    record_set: FirewallaFlowRecordSet,
    *,
    rule_names: Mapping[int, str] | None = None,
    network_names: Mapping[str, str] | None = None,
    membership_names: Mapping[str, str] | None = None,
) -> FirewallaFlowRecordView:
    """Normalize one record family and resolve the names its records reference.

    A record whose ``blocked_by_rule_id`` matches no current rule is **kept**, with
    no name and counted in ``unattributed_blocks``. Rule ids are not durable across
    a delete and re-create, so an id that resolves to nothing is expected rather
    than exceptional, and dropping the record would hide the block itself.

    The interface and tag maps are filtered to the ids these records actually
    reference: a record carries those as lists, and resolving the whole inventory
    would be wasted work.
    """
    rules = rule_names or {}
    networks = network_names or {}
    memberships = membership_names or {}

    records: list[FirewallaFlowRecord] = []
    resolved_rules: dict[int, str] = {}
    referenced_networks: set[str] = set()
    referenced_memberships: set[str] = set()
    unattributed = 0

    for raw_record in record_set.records:
        record = build_flow_record(raw_record)
        records.append(record)

        if record.network_id is not None:
            referenced_networks.add(record.network_id)
        if record.remote_network_id is not None:
            referenced_networks.add(record.remote_network_id)
        referenced_memberships.update(record.tags)
        referenced_memberships.update(record.user_tags)
        referenced_memberships.update(record.membership_tags)
        referenced_memberships.update(record.destination_tags)

        rule_id = record.blocked_by_rule_id
        if rule_id is None:
            continue
        name = rules.get(rule_id)
        if name is None:
            unattributed += 1
            continue
        resolved_rules[rule_id] = name

    return FirewallaFlowRecordView(
        records=tuple(records),
        rows_available=record_set.rows_available,
        next_cursor=record_set.next_cursor,
        truncated=record_set.truncated,
        pages_fetched=record_set.pages_fetched,
        records_dropped_as_duplicates=record_set.records_dropped_as_duplicates,
        unattributed_blocks=unattributed,
        rule_names=resolved_rules,
        network_names={
            network_id: networks[network_id]
            for network_id in referenced_networks
            if network_id in networks
        },
        membership_names={
            tag_id: memberships[tag_id]
            for tag_id in referenced_memberships
            if tag_id in memberships
        },
    )


def _summarise_totals(
    families: Mapping[str, tuple[Mapping[str, object], ...]],
) -> FirewallaFlowTotals:
    """Total each unit separately, so bytes and counts are never added together."""
    bytes_by_family: dict[str, int] = {}
    for family, rows in families.items():
        if flow_family_unit(family) != FLOW_UNIT_BYTES:
            continue
        bytes_by_family[family] = sum(_row_count(row) for row in rows)

    blocked_ip = sum(
        _family_total(families, family)
        for family in ("ipB:in", "ipB:out", "local:ipB:in", "local:ipB:out")
    )
    return FirewallaFlowTotals(
        download_bytes=bytes_by_family.get(_FAMILY_DOWNLOAD, 0),
        upload_bytes=bytes_by_family.get(_FAMILY_UPLOAD, 0),
        local_download_bytes=bytes_by_family.get(_FAMILY_LOCAL_DOWNLOAD, 0),
        local_upload_bytes=bytes_by_family.get(_FAMILY_LOCAL_UPLOAD, 0),
        blocked_dns_count=_family_total(families, _FAMILY_DNS_BLOCKED),
        blocked_ip_count=blocked_ip,
        connection_count=(
            _family_total(families, _FAMILY_LOCAL_IN)
            + _family_total(families, _FAMILY_LOCAL_OUT)
        ),
    )


def _aggregate_destinations(
    families: Mapping[str, tuple[Mapping[str, object], ...]],
    family: str,
) -> tuple[FirewallaFlowDestination, ...]:
    """Merge one byte family's rows into a destination per remote endpoint.

    The same destination appears once per device **and once per address**, so the
    rows are summed rather than deduplicated. Keying on the address would list one
    hostname several times over -- measured, 43 of 116 hosts in a single window
    resolved to more than one address -- so the hostname is the key and its
    addresses are collected alongside.
    """
    rows = families.get(family)
    if not rows:
        return ()

    add_download = family == _FAMILY_DOWNLOAD
    merged: dict[tuple[str | None, str | None], _DestinationAccumulator] = {}

    for row in rows:
        remote_host = flow_row_remote_host(row)
        remote_ip = flow_row_remote_ip(row)
        key = (remote_host, _destination_kind(remote_host, remote_ip))
        entry = merged.setdefault(key, _DestinationAccumulator())

        if add_download:
            entry.download_bytes += _row_count(row)
        else:
            entry.upload_bytes += _row_count(row)
        entry.rollup_rows += 1
        if remote_ip is not None:
            entry.destination_ips.add(remote_ip)
        if (device_id := flow_row_host_id(row)) is not None:
            entry.device_ids.add(device_id)

    return tuple(
        FirewallaFlowDestination(
            destination=destination,
            destination_kind=kind,
            destination_ips=tuple(sorted(entry.destination_ips)),
            download_bytes=entry.download_bytes,
            upload_bytes=entry.upload_bytes,
            rollup_rows=entry.rollup_rows,
            device_ids=tuple(sorted(entry.device_ids)),
        )
        for (destination, kind), entry in merged.items()
    )


def _aggregate_blocked(
    families: Mapping[str, tuple[Mapping[str, object], ...]],
) -> tuple[FirewallaBlockedDestination, ...]:
    """Merge the blocked families into one row per destination, kind and direction.

    Kind, direction **and address-kind** are part of the key rather than folded
    away: "what did this device try to reach" and "what tried to reach it" are
    different questions, a DNS block is a different thing from an IP block, and a
    named destination is a different answer from a bare address.
    """
    merged: dict[
        tuple[str | None, str | None, str | None, str | None], _BlockedAccumulator
    ] = {}

    for family, block_type in _BLOCKED_FAMILY_KINDS.items():
        rows = families.get(family)
        if not rows:
            continue
        direction = flow_family_direction(family)

        for row in rows:
            destination = flow_row_remote_host(row)
            remote_ip = flow_row_remote_ip(row)
            kind = _destination_kind(destination, remote_ip)
            if destination is None and remote_ip is None:
                # A LAN peer is identified by a device id, which is not always a
                # MAC -- see `_flow_record_destination` in `utils/flow.py`.
                peer_id = normalized_string(row.get(_RAW_ROW_DST_MAC_KEY))
                if peer_id is None:
                    continue
                destination, kind = peer_id, "device"

            key = (destination, kind, block_type, direction)
            entry = merged.setdefault(key, _BlockedAccumulator())
            entry.block_count += _row_count(row)
            entry.rollup_rows += 1
            if remote_ip is not None:
                entry.destination_ips.add(remote_ip)
            if (device_id := flow_row_host_id(row)) is not None:
                entry.device_ids.add(device_id)

    return tuple(
        FirewallaBlockedDestination(
            destination=destination,
            destination_kind=kind,
            destination_ips=tuple(sorted(entry.destination_ips)),
            block_type=block_type,
            direction=direction,
            block_count=entry.block_count,
            rollup_rows=entry.rollup_rows,
            device_ids=tuple(sorted(entry.device_ids)),
        )
        for (destination, kind, block_type, direction), entry in merged.items()
    )


def _aggregate_local_peers(
    families: Mapping[str, tuple[Mapping[str, object], ...]],
) -> tuple[FirewallaLocalPeer, ...]:
    """Merge the LAN connection families into one row per peer.

    A peer is identified by ``dstMac``: traffic that never left the network has no
    hostname to resolve to, which is why this list is separate from the
    destination lists rather than merged into them.
    """
    merged: dict[str, _PeerAccumulator] = {}
    for family in (_FAMILY_LOCAL_IN, _FAMILY_LOCAL_OUT):
        for row in families.get(family, ()):
            peer_id = normalized_string(row.get(_RAW_ROW_DST_MAC_KEY))
            if peer_id is None:
                continue
            entry = merged.setdefault(peer_id, _PeerAccumulator())
            entry.connection_count += _row_count(row)
            entry.rollup_rows += 1

    return tuple(
        FirewallaLocalPeer(
            peer_id=peer_id,
            connection_count=entry.connection_count,
            rollup_rows=entry.rollup_rows,
        )
        for peer_id, entry in sorted(merged.items())
    )


def _summarise_members(
    hosts: Mapping[str, Mapping[str, object]],
    *,
    names: Mapping[str, str],
    addresses: Mapping[str, str],
) -> tuple[FirewallaFlowMember, ...]:
    """Build the per-device ranking from the rollup's ``hosts`` block."""
    members: list[FirewallaFlowMember] = []
    for device_id, counters in hosts.items():
        fields = {
            attribute: _counter(counters, key)
            for key, attribute in _MEMBER_FIELDS.items()
        }
        members.append(
            FirewallaFlowMember(
                device_id=device_id,
                device_name=names.get(device_id),
                device_ip=addresses.get(device_id),
                **fields,
            )
        )

    return tuple(
        sorted(
            members,
            key=lambda member: (
                -member.total_bytes,
                -(member.connection_count or 0),
                (member.device_name or "").casefold(),
                member.device_id,
            ),
        )[:_TOP_MEMBER_LIMIT]
    )


def _rank_destinations(
    destinations: Sequence[FirewallaFlowDestination],
    *,
    by: str,
) -> tuple[FirewallaFlowDestination, ...]:
    """Rank destinations by one direction, with a stable tie-break.

    Ordering by a single direction rather than the combined total is deliberate:
    the "top download" and "top upload" lists answer different questions, and
    ranking them by the sum would make them the same list twice.
    """
    return tuple(
        sorted(
            destinations,
            key=lambda destination: (
                -int(getattr(destination, by)),
                (destination.destination or "").casefold(),
                destination.destination_kind or "",
            ),
        )[:_TOP_DESTINATION_LIMIT]
    )


def _rank_blocked(
    destinations: Sequence[FirewallaBlockedDestination],
) -> tuple[FirewallaBlockedDestination, ...]:
    """Rank blocked destinations by block count, with a stable tie-break."""
    return tuple(
        sorted(
            destinations,
            key=lambda destination: (
                -destination.block_count,
                (destination.destination or "").casefold(),
                destination.block_type or "",
                destination.direction or "",
            ),
        )[:_TOP_DESTINATION_LIMIT]
    )


def _destination_kind(
    destination: str | None,
    remote_ip: str | None,
) -> str | None:
    """Return the kind of name a destination resolved to.

    The rollup does not say which of ``host`` or ``domain`` a row used, so a
    resolved name is reported as ``host`` and an address-only row as ``ip``. A
    local peer is classified separately, by its MAC.
    """
    if destination is not None:
        return "host"
    if remote_ip is not None:
        return "ip"
    return None


def _row_count(row: Mapping[str, object]) -> int:
    """Return one rollup row's ``count``, whose unit depends on the family."""
    return normalized_int(row.get(_RAW_ROW_COUNT_KEY)) or 0


def _family_total(
    families: Mapping[str, tuple[Mapping[str, object], ...]],
    family: str,
) -> int:
    """Return one family's summed ``count``, or zero when it is absent."""
    return sum(_row_count(row) for row in families.get(family, ()))


def _counter(counters: Mapping[str, object], key: str) -> int:
    """Return one per-member counter, tolerating an absent or odd value."""
    return normalized_int(counters.get(key)) or 0


def resolve_member_devices(
    members: Iterable[FirewallaFlowMember],
) -> tuple[tuple[str, ...], int]:
    """Return the device ids in a member list and how many had no name.

    A device id is not always a host: a VPN peer carries a ``wg_peer:`` prefix and
    an interface an ``if:`` one, and neither resolves in the host inventory. The
    unresolvable count is returned so a caller can say so rather than presenting a
    nameless device as a normal one.
    """
    device_ids: list[str] = []
    unresolved = 0
    for member in members:
        device_ids.append(member.device_id)
        if member.device_name is None:
            unresolved += 1
    return tuple(device_ids), unresolved
