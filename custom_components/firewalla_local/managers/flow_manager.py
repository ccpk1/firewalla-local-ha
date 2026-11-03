"""Flow-reporting reads for one Firewalla config entry.

Owns the three local flow queries and the two behaviours the box does not provide
itself: reporting the window it *actually* served, and walking the page cursor.

**Live per call, never cached.** Nothing here is polled or held between refreshes,
so a flow report adds no request to a normal refresh cycle and cannot go stale.

**Fail-soft, deliberately.** The client raises on an unexpected shape -- that is
the established pattern and the right one for a protocol boundary -- so this layer
catches and returns ``None``, letting the service report a section as unavailable
rather than failing the whole call. Connectivity and auth failures are *not*
caught: those are not "data unavailable", and the coordinator already owns how they
surface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Final

from ..api.exceptions import FirewallaProtocolError
from ..const import (
    DEFAULT_FLOW_REPORT_WINDOW_HOURS,
    FLOW_LOG_PAGE_DEADLINE_SECONDS,
    LIVE_SAMPLE_READING_SECONDS,
    MAX_FLOW_LOG_PAGE_SIZE,
    served_live_sample_seconds,
)
from ..models import (
    FirewallaFlowRecordSet,
    FirewallaFlowReportView,
    FirewallaFlowRollup,
    FirewallaFlowWindow,
    FirewallaLiveHostThroughput,
    FirewallaLiveInterfaceThroughput,
    FirewallaLiveThroughput,
    FirewallaNetworkKind,
    format_policy_rule_name,
)
from ..utils.flow_report import build_record_view, summarise_rollup
from .base_manager import FirewallaBaseManager

_LOGGER: Final = logging.getLogger(__package__)

_FLOW_TARGET_TYPE_TAG: Final = "tag"
_FLOW_TARGET_TYPE_HOST: Final = "host"

_RAW_FLOW_FAMILIES_KEY: Final = "flows"
_RAW_FLOW_HOSTS_KEY: Final = "hosts"
_RAW_FLOW_BEGIN_KEY: Final = "begin"
_RAW_FLOW_END_KEY: Final = "end"

# One stream id for the whole integration, so repeated calls reuse the box's running
# `iftop` sampler instead of starting another set.
_LIVE_STREAM_ID: Final = "home-assistant-firewalla-local"
# The sampler averages over 2 s, so readings 2 s apart cover a window without
# gaps. A cold start answered zeros at once and real rates 3 s later on a Gold, so
# one retry after this pause turns a cold call into a reading.
_LIVE_WARMUP_SECONDS: Final = 3.0

_RAW_LIVE_THROUGHPUT_KEY: Final = "throughput"
_RAW_LIVE_DEVICES_KEY: Final = "devices"

# Bound at import so the wait can be stubbed by patching this attribute. Patching
# `asyncio.sleep` through the module patches the real one process-wide, which a
# live-throughput test would then impose on every other coroutine in the run.
_live_sleep = asyncio.sleep

# `hourblock` must be at least 2 or the box answers with an empty response and no
# error. It has no other observable effect, so one value is used throughout.
_FLOW_HOURBLOCK: Final = 24


class FirewallaFlowManager(FirewallaBaseManager):
    """Flow reporting reads for one config entry."""

    async def async_get_rollup(
        self,
        *,
        target_type: str,
        target: str,
        window_hours: int = DEFAULT_FLOW_REPORT_WINDOW_HOURS,
    ) -> FirewallaFlowRollup | None:
        """Return one windowed flow rollup, or ``None`` when it could not be read.

        The returned ``window`` describes what the box **served**, read from the
        row bounds, not what was requested. The box clamps silently: a 168-hour
        request was served 24 hours with code 200 and no indication, so a report
        built on the requested window would claim history it does not have.
        """
        now = int(time.time())
        try:
            payload = await self.client.async_get_flow_rollup_payload(
                target_type=target_type,
                target=target,
                start_timestamp=now - window_hours * 3600,
                end_timestamp=now,
                hourblock=_FLOW_HOURBLOCK,
            )
        except FirewallaProtocolError as err:
            _LOGGER.debug(
                "Flow rollup unavailable for %s %s: %s",
                target_type,
                target,
                err,
            )
            return None

        families = _normalise_flow_families(payload.get(_RAW_FLOW_FAMILIES_KEY))
        return FirewallaFlowRollup(
            target_type=target_type,
            target=target,
            window=_build_served_window(families, requested_hours=window_hours),
            families=families,
            hosts=_normalise_flow_hosts(payload.get(_RAW_FLOW_HOSTS_KEY)),
        )

    async def async_get_live_throughput(
        self,
        *,
        sample_seconds: int,
        network_kinds: Mapping[str, FirewallaNetworkKind] | None = None,
    ) -> FirewallaLiveThroughput | None:
        """Return live per-network rates averaged over ``sample_seconds``.

        ``sample_seconds`` is a request, not a promise: one reading is a 2 s
        average, so an odd window is served at the next even second and the result
        reports that window rather than the request.

        ``network_kinds`` lets an interface row carry the kind that decides which
        of its counters is the download. Without it a row keeps ``None`` there and
        its direction stays unknown rather than guessed.
        """
        return await self._async_sample_live_throughput(
            sample_seconds=sample_seconds,
            read=lambda: self._async_read_live_throughput(network_kinds=network_kinds),
        )

    async def async_get_host_live_throughput(
        self, *, mac: str, sample_seconds: int
    ) -> FirewallaLiveThroughput | None:
        """Return one host's live rates averaged over ``sample_seconds``.

        This is the box's own single-host query rather than a slice of the system
        answer: one row, no interface counters to reconcile against, and an idle
        host answering zeros instead of being omitted.
        """
        return await self._async_sample_live_throughput(
            sample_seconds=sample_seconds,
            read=lambda: self._async_read_host_live_throughput(mac),
        )

    async def _async_sample_live_throughput(
        self,
        *,
        sample_seconds: int,
        read: Callable[[], Awaitable[FirewallaLiveThroughput]],
    ) -> FirewallaLiveThroughput | None:
        """Average repeated readings across the served window, or ``None``.

        The box reports a 2 s average, and streaming traffic arrives in bursts
        (measured: 25-38 Mbps for 2-4 s every 10 s from a player averaging about
        6 Mbps), so a single reading usually lands in a gap.

        A cold sampler answers real interface traffic with no host rows, so that
        first answer is retried once after a short pause and never counted.
        """
        served_seconds = served_live_sample_seconds(sample_seconds)
        try:
            reading = await read()
            if reading.warming_up:
                await _live_sleep(_LIVE_WARMUP_SECONDS)
                reading = await read()
                if reading.warming_up:
                    # Still starting: report the window that was served rather
                    # than the normaliser's 0, which would look like no window.
                    return replace(reading, sample_seconds=served_seconds)
            readings = [reading]
            wanted = max(1, served_seconds // LIVE_SAMPLE_READING_SECONDS)
            while len(readings) < wanted:
                await _live_sleep(LIVE_SAMPLE_READING_SECONDS)
                readings.append(await read())
        except FirewallaProtocolError as err:
            _LOGGER.debug("Live throughput unavailable: %s", err)
            return None
        return _average_live_readings(readings, sample_seconds=served_seconds)

    async def _async_read_live_throughput(
        self, *, network_kinds: Mapping[str, FirewallaNetworkKind] | None = None
    ) -> FirewallaLiveThroughput:
        """Take one 2 s reading of the whole box."""
        return _normalise_live_throughput(
            await self.client.async_get_live_throughput_payload(
                stream_id=_LIVE_STREAM_ID
            ),
            network_kinds=network_kinds,
        )

    async def _async_read_host_live_throughput(
        self, mac: str
    ) -> FirewallaLiveThroughput:
        """Take one 2 s reading of a single host."""
        return _normalise_live_throughput(
            await self.client.async_get_host_live_throughput_payload(
                mac=mac, stream_id=_LIVE_STREAM_ID
            ),
            host_scope=mac,
        )

    async def async_get_flow_log(
        self,
        *,
        target_type: str,
        target: str,
        page_size: int = MAX_FLOW_LOG_PAGE_SIZE,
        fetch_all: bool = False,
        include_blocked: bool = False,
        deadline_seconds: float = FLOW_LOG_PAGE_DEADLINE_SECONDS,
    ) -> FirewallaFlowRecordSet | None:
        """Return flow-log records, or ``None`` when they could not be read.

        Without ``fetch_all`` this is a single page and promises nothing about
        completeness. With it, the cursor is walked to exhaustion, stopping only on
        the deadline or on a cursor that fails to advance -- never on a row count,
        because the page ceiling is the box's and could change.

        ``include_blocked`` *adds* blocked records rather than filtering to them;
        use :meth:`async_get_block_log` for blocked records alone.
        """
        return await self._async_collect_records(
            target_type=target_type,
            target=target,
            blocked_only=False,
            page_size=page_size,
            fetch_all=fetch_all,
            include_blocked=include_blocked,
            deadline_seconds=deadline_seconds,
        )

    async def async_get_block_log(
        self,
        *,
        target_type: str,
        target: str,
        page_size: int = MAX_FLOW_LOG_PAGE_SIZE,
        fetch_all: bool = False,
        category: str | None = None,
        deadline_seconds: float = FLOW_LOG_PAGE_DEADLINE_SECONDS,
    ) -> FirewallaFlowRecordSet | None:
        """Return blocked-only records, or ``None`` when they could not be read.

        This is the query behind "what did the box stop", and each record names the
        rule that stopped it, so it is the only path that can attribute a block to a
        rule.
        """
        return await self._async_collect_records(
            target_type=target_type,
            target=target,
            blocked_only=True,
            page_size=page_size,
            fetch_all=fetch_all,
            category=category,
            deadline_seconds=deadline_seconds,
        )

    async def _async_collect_records(
        self,
        *,
        target_type: str,
        target: str,
        blocked_only: bool,
        page_size: int,
        fetch_all: bool,
        include_blocked: bool = False,
        category: str | None = None,
        deadline_seconds: float = FLOW_LOG_PAGE_DEADLINE_SECONDS,
    ) -> FirewallaFlowRecordSet | None:
        """Fetch one page, optionally walking the cursor to exhaustion.

        Pages are deduplicated on the record's own serialised content rather than
        on a hand-picked key. A key built from fields that identify a *blocked*
        record is unsafe on a regular one: ``pid`` is absent there, so one device
        opening many connections to the same host within the same second would
        collide and silently under-count.
        """
        deadline = time.monotonic() + deadline_seconds
        records: list[Mapping[str, object]] = []
        seen: set[str] = set()
        dropped = 0
        pages = 0
        cursor: float | None = None
        rows_available: int | None = None
        is_first_page = True

        while True:
            since = cursor
            if blocked_only:
                page = await self.client.async_get_block_log_payload(
                    target_type=target_type,
                    target=target,
                    count=page_size,
                    since_timestamp=since,
                    category=category,
                )
            else:
                page = await self.client.async_get_flow_log_payload(
                    target_type=target_type,
                    target=target,
                    count=page_size,
                    since_timestamp=since,
                    include_blocked=include_blocked,
                )

            pages += 1
            if is_first_page:
                rows_available = page.reported_count
                is_first_page = False

            for record in page.records:
                fingerprint = json.dumps(record, sort_keys=True, default=str)
                if fingerprint in seen:
                    dropped += 1
                    continue
                seen.add(fingerprint)
                records.append(record)

            next_cursor = page.next_cursor
            if not fetch_all or next_cursor is None:
                return FirewallaFlowRecordSet(
                    records=tuple(records),
                    rows_available=rows_available,
                    next_cursor=next_cursor,
                    pages_fetched=pages,
                    records_dropped_as_duplicates=dropped,
                )

            if next_cursor == cursor:
                # A cursor that does not advance would repeat the same page
                # forever; that is the loop guard, so stop and say so.
                return FirewallaFlowRecordSet(
                    records=tuple(records),
                    rows_available=rows_available,
                    next_cursor=next_cursor,
                    truncated=True,
                    pages_fetched=pages,
                    records_dropped_as_duplicates=dropped,
                )

            if time.monotonic() >= deadline:
                return FirewallaFlowRecordSet(
                    records=tuple(records),
                    rows_available=rows_available,
                    next_cursor=next_cursor,
                    truncated=True,
                    pages_fetched=pages,
                    records_dropped_as_duplicates=dropped,
                )

            cursor = next_cursor

    async def async_get_report(
        self,
        *,
        target_type: str,
        target: str,
        window_hours: int = DEFAULT_FLOW_REPORT_WINDOW_HOURS,
        include_summary: bool = True,
        include_blocked_records: bool = False,
        include_flow_records: bool = False,
        fetch_all_records: bool = False,
        page_size: int = MAX_FLOW_LOG_PAGE_SIZE,
    ) -> FirewallaFlowReportView:
        """Build one flow report, reading only the sections that were asked for.

        A summary is a single rollup and needs no log read at all, so the common
        call costs one request. The record families are separate reads and are
        only made when requested, because a full day on a busy target is thousands
        of records.

        A section that could not be read comes back as ``None`` rather than
        failing the call, and the caller reports it as unavailable. Connectivity
        and auth failures still propagate.
        """
        summary = None
        if include_summary:
            rollup = await self.async_get_rollup(
                target_type=target_type,
                target=target,
                window_hours=window_hours,
            )
            if rollup is not None:
                summary = summarise_rollup(
                    rollup,
                    device_names=self._device_names(),
                    device_addresses=self._device_addresses(),
                )

        blocked_records = None
        if include_blocked_records:
            record_set = await self.async_get_block_log(
                target_type=target_type,
                target=target,
                page_size=page_size,
                fetch_all=fetch_all_records,
            )
            if record_set is not None:
                blocked_records = build_record_view(
                    record_set,
                    rule_names=self._rule_names(),
                    network_names=self._network_names(),
                    membership_names=self._membership_names(),
                )

        flow_records = None
        if include_flow_records:
            record_set = await self.async_get_flow_log(
                target_type=target_type,
                target=target,
                page_size=page_size,
                fetch_all=fetch_all_records,
            )
            if record_set is not None:
                flow_records = build_record_view(
                    record_set,
                    rule_names=self._rule_names(),
                    network_names=self._network_names(),
                    membership_names=self._membership_names(),
                )

        return FirewallaFlowReportView(
            target_type=target_type,
            target=target,
            summary=summary,
            blocked_records=blocked_records,
            flow_records=flow_records,
        )

    def _device_names(self) -> dict[str, str]:
        """Return the host inventory's device id to display name mapping.

        Used to name a rollup member. A member id that is not a host -- a VPN peer
        carries a ``wg_peer:`` prefix, an interface an ``if:`` one -- simply has no
        entry, which is why the name is optional on the member rather than
        defaulting to the id.
        """
        host_manager = self.coordinator.host_manager
        if host_manager is None:
            return {}
        return {
            host.mac: host.host_name
            for host in host_manager.get_hosts()
            if host.host_name
        }

    def _device_addresses(self) -> dict[str, str]:
        """Return the host inventory's device id to address mapping."""
        host_manager = self.coordinator.host_manager
        if host_manager is None:
            return {}
        return {
            host.mac: host.ip_address
            for host in host_manager.get_hosts()
            if host.ip_address is not None
        }

    def _rule_names(self) -> dict[int, str]:
        """Return the live rule id to name mapping, for the block-to-rule join.

        Read from the rule manager rather than the client, so this uses the same
        registry the rule surfaces do and cannot drift from it. A record reports
        its blocking rule as a number while a rule id is a string, so the join is
        keyed on the integer form.
        """
        rule_manager = self.coordinator.rule_manager
        if rule_manager is None:
            return {}
        return {
            int(rule.rule_id): name
            for rule in rule_manager.get_rules()
            if rule.rule_id.isdigit() and (name := format_policy_rule_name(rule))
        }

    def _network_names(self) -> dict[str, str]:
        """Return the network uuid to name mapping.

        A flow record's ``intf`` is the local network and ``oIntf`` / ``wanIntf``
        the remote side, both of which are uuids the network inventory already
        names -- so this is a lookup rather than a request.
        """
        integration_manager = self.coordinator.integration_manager
        if integration_manager is None:
            return {}
        return {
            network.uuid: network.name
            for network in integration_manager.get_available_networks()
        }

    def _membership_names(self) -> dict[str, str]:
        """Return the tag id to group or user name mapping.

        A record's ``tags`` / ``userTags`` / ``dTags`` / ``dstTags`` carry tag ids,
        and the tag collection names both plain groups and user affiliations.

        **Both identifiers are mapped**, because a record refers to a user
        membership through two different fields. Measured on the dev box, a device
        on KADENS_DEVICES carries ``tags: ["31"]`` and ``userTags: ["32"]``, and the
        collection models that one membership as ``group_id="31"`` (the affiliation
        tag, named ``KADENS_DEVICES``) with ``user_id="32"``. A record's ``userTags``
        holds the user id, so a map keyed only on the group id leaves every user tag
        unresolved.

        The two id spaces do not overlap -- measured, 18 plain group ids and 10 user
        entries sharing no value -- so one map is safe rather than ambiguous.
        """
        integration_manager = self.coordinator.integration_manager
        if integration_manager is None:
            return {}
        names: dict[str, str] = {}
        for group in integration_manager.get_groups():
            names[group.group_id] = group.name
            if group.user_id is not None:
                # setdefault: a user id must never overwrite a plain group's name
                # if the two spaces ever did collide.
                names.setdefault(group.user_id, group.name)
        return names


def _normalise_flow_families(
    raw_families: object,
) -> dict[str, tuple[Mapping[str, object], ...]]:
    """Return the rollup's family rows, dropping anything that is not a row.

    A family that is absent or empty is omitted rather than kept as an empty
    tuple: absent means the box had nothing for that family, and a caller should
    not have to distinguish that from a family that exists but is always empty.
    """
    if not isinstance(raw_families, Mapping):
        return {}

    families: dict[str, tuple[Mapping[str, object], ...]] = {}
    for name, raw_rows in raw_families.items():
        if not isinstance(name, str) or not name or not isinstance(raw_rows, list):
            continue
        rows = tuple(row for row in raw_rows if isinstance(row, Mapping))
        if rows:
            families[name] = rows
    return families


def _normalise_flow_hosts(
    raw_hosts: object,
) -> dict[str, Mapping[str, object]]:
    """Return the rollup's per-member rows.

    Only populated on a ``tag`` request: a device report has no members to rank, so
    an empty result here means "not applicable" rather than "no members".
    """
    if not isinstance(raw_hosts, Mapping):
        return {}
    return {
        host_id: row
        for host_id, row in raw_hosts.items()
        if isinstance(host_id, str) and isinstance(row, Mapping)
    }


def _build_served_window(
    families: Mapping[str, tuple[Mapping[str, object], ...]],
    *,
    requested_hours: int,
) -> FirewallaFlowWindow:
    """Build the served window from the row bounds the box returned.

    Every row carries the same ``begin``/``end``, so the widest pair is the window.
    Returns an unattributed window when no row carried bounds, which is the honest
    answer for an empty result rather than claiming the requested window.
    """
    begins: list[int] = []
    ends: list[int] = []
    for rows in families.values():
        for row in rows:
            begin = row.get(_RAW_FLOW_BEGIN_KEY)
            end = row.get(_RAW_FLOW_END_KEY)
            if isinstance(begin, int):
                begins.append(begin)
            if isinstance(end, int):
                ends.append(end)

    return FirewallaFlowWindow(
        requested_hours=requested_hours,
        begin_timestamp=min(begins) if begins else None,
        end_timestamp=max(ends) if ends else None,
    )


def _rate(value: object) -> float:
    """Return one rate as a float, treating a missing or malformed value as zero."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)


def _normalise_live_throughput(
    payload: Mapping[str, object],
    *,
    network_kinds: Mapping[str, FirewallaNetworkKind] | None = None,
    host_scope: str | None = None,
) -> FirewallaLiveThroughput:
    """Normalise one ``liveStats`` answer into interface and device rates.

    ``network_kinds`` maps a network UUID to its kind, because an interface's
    counters are named from the box's point of view and therefore mean opposite
    things on each edge. Without it a row keeps ``network_kind`` ``None`` and its
    direction stays unknown rather than guessed.

    ``host_scope`` is set for the single-host query, whose response carries one
    row keyed by the host's MAC rather than interface names.
    """
    interfaces: list[FirewallaLiveInterfaceThroughput] = []
    devices: list[FirewallaLiveHostThroughput] = []
    kinds = network_kinds or {}

    if host_scope is not None:
        devices.extend(
            _normalise_host_scope_rows(
                payload.get(_RAW_LIVE_THROUGHPUT_KEY), host_scope
            )
        )
        return FirewallaLiveThroughput(
            sampled_at_timestamp=int(time.time()),
            warming_up=False,
            devices=tuple(devices),
        )

    raw_rows = payload.get(_RAW_LIVE_THROUGHPUT_KEY)
    for row in raw_rows if isinstance(raw_rows, list) else ():
        if not isinstance(row, Mapping) or not isinstance(row.get("name"), str):
            continue
        target = row.get("target")
        network_uuid = target if isinstance(target, str) else None
        interfaces.append(
            FirewallaLiveInterfaceThroughput(
                interface_name=row["name"],
                network_uuid=network_uuid,
                rx_bytes_per_second=_rate(row.get("rx")),
                tx_bytes_per_second=_rate(row.get("tx")),
                network_kind=kinds.get(network_uuid or ""),
            )
        )
        raw_devices = row.get(_RAW_LIVE_DEVICES_KEY)
        if network_uuid is None or not isinstance(raw_devices, Mapping):
            continue
        for device_id, rates in raw_devices.items():
            if not isinstance(device_id, str) or not isinstance(rates, Mapping):
                continue
            devices.append(
                FirewallaLiveHostThroughput(
                    host_id=device_id,
                    network_uuid=network_uuid,
                    # The system view's device map is host-centric: `rx` is what
                    # the host received.
                    download_bytes_per_second=_rate(rates.get("rx")),
                    upload_bytes_per_second=_rate(rates.get("tx")),
                )
            )

    # A cold sampler answers with real interface traffic and no host rows at all,
    # then fills in over the next few readings. That is a warm-up, not an idle
    # network. Every rate being zero is the genuinely ambiguous case -- idle and
    # cold look identical there -- so it is not treated as a warm-up.
    warming_up = bool(interfaces) and not devices and _any_interface_busy(interfaces)
    return FirewallaLiveThroughput(
        sampled_at_timestamp=int(time.time()),
        warming_up=warming_up,
        interfaces=tuple(interfaces),
        devices=tuple(
            sorted(
                devices,
                key=lambda device: (
                    -(device.download_bytes_per_second + device.upload_bytes_per_second)
                ),
            )
        ),
    )


def _normalise_host_scope_rows(
    raw_rows: object, mac: str
) -> list[FirewallaLiveHostThroughput]:
    """Normalise the single row a host-scoped ``liveStats`` answer carries.

    The row is keyed by the target MAC and its counters are box-centric, the
    opposite of the system view's device map: `tx` is what the host downloaded.
    """
    if not isinstance(raw_rows, list):
        raise FirewallaProtocolError("liveStats host answer had no throughput list")
    for row in raw_rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("target") != mac:
            raise FirewallaProtocolError(
                "liveStats host answer did not describe the requested host"
            )
        return [
            FirewallaLiveHostThroughput(
                host_id=mac,
                network_uuid="",
                download_bytes_per_second=_rate(row.get("tx")),
                upload_bytes_per_second=_rate(row.get("rx")),
            )
        ]
    raise FirewallaProtocolError("liveStats host answer was empty")


def _any_interface_busy(
    interfaces: Sequence[FirewallaLiveInterfaceThroughput],
) -> bool:
    """Return whether any interface reported traffic."""
    return any(
        interface.rx_bytes_per_second or interface.tx_bytes_per_second
        for interface in interfaces
    )


def _average_live_readings(
    readings: list[FirewallaLiveThroughput], *, sample_seconds: int
) -> FirewallaLiveThroughput:
    """Average back-to-back readings per host and per interface.

    Readings that listed no host at all are dropped before averaging, because the
    box leaves an idle host out of a reading rather than listing it at zero. Two
    effects follow, and both point the same way: a host's average divides by every
    *remained* reading, and an empty reading can never enter the divisor, so a cold
    sampler cannot scale the whole answer down.

    The remaining division still spans every reading rather than only the ones a
    host appeared in: a player seen in one burst out of five played for one fifth
    of the window, so dividing by one would report five times its real rate.
    """
    warm = [reading for reading in readings if reading.devices]
    if not warm:
        # Nothing was listed in any reading. Report the last one so callers still
        # get the interface rates, and say the window covered it.
        return replace(
            readings[-1],
            warming_up=False,
            sample_seconds=sample_seconds,
            sample_count=len(readings),
        )

    count = len(warm)
    host_totals: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    interface_totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    interface_networks: dict[str, str | None] = {}
    interface_kinds: dict[str, FirewallaNetworkKind | None] = {}
    for reading in warm:
        for host in reading.devices:
            totals = host_totals[(host.host_id, host.network_uuid)]
            totals[0] += host.download_bytes_per_second
            totals[1] += host.upload_bytes_per_second
        for interface in reading.interfaces:
            totals = interface_totals[interface.interface_name]
            totals[0] += interface.rx_bytes_per_second
            totals[1] += interface.tx_bytes_per_second
            interface_networks[interface.interface_name] = interface.network_uuid
            interface_kinds[interface.interface_name] = interface.network_kind

    hosts = [
        FirewallaLiveHostThroughput(
            host_id=host_id,
            network_uuid=network_uuid,
            download_bytes_per_second=down / count,
            upload_bytes_per_second=up / count,
        )
        for (host_id, network_uuid), (down, up) in host_totals.items()
    ]
    return FirewallaLiveThroughput(
        sampled_at_timestamp=warm[-1].sampled_at_timestamp,
        warming_up=False,
        sample_seconds=sample_seconds,
        sample_count=count,
        interfaces=tuple(
            FirewallaLiveInterfaceThroughput(
                interface_name=name,
                network_uuid=interface_networks[name],
                rx_bytes_per_second=rx / count,
                tx_bytes_per_second=tx / count,
                network_kind=interface_kinds[name],
            )
            for name, (rx, tx) in interface_totals.items()
        ),
        devices=tuple(
            sorted(
                hosts,
                key=lambda host: (
                    -(host.download_bytes_per_second + host.upload_bytes_per_second)
                ),
            )
        ),
    )
