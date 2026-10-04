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

import json
import logging
import time
from collections.abc import Mapping
from typing import Final

from ..api.exceptions import FirewallaProtocolError
from ..const import (
    DEFAULT_FLOW_REPORT_WINDOW_HOURS,
    FLOW_LOG_PAGE_DEADLINE_SECONDS,
    MAX_FLOW_LOG_PAGE_SIZE,
)
from ..models import (
    FirewallaFlowRecordSet,
    FirewallaFlowRollup,
    FirewallaFlowWindow,
)
from .base_manager import FirewallaBaseManager

_LOGGER: Final = logging.getLogger(__package__)

_FLOW_TARGET_TYPE_TAG: Final = "tag"
_FLOW_TARGET_TYPE_HOST: Final = "host"

_RAW_FLOW_FAMILIES_KEY: Final = "flows"
_RAW_FLOW_HOSTS_KEY: Final = "hosts"
_RAW_FLOW_BEGIN_KEY: Final = "begin"
_RAW_FLOW_END_KEY: Final = "end"

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
