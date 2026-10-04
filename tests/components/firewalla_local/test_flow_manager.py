"""Tests for Firewalla Local flow manager behavior.

The values used here mirror the live measurements recorded in
``docs/REVERSE_ENGINEERING_WORKFLOW.md``: a rollup served as 24 hours regardless
of what was requested, page boundaries that can overlap, and a cursor that is a
float.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientSession

from custom_components.firewalla_local.api import FirewallaApiClient
from custom_components.firewalla_local.api.exceptions import (
    FirewallaConnectionError,
    FirewallaProtocolError,
)
from custom_components.firewalla_local.api.models import FlowLogPage
from custom_components.firewalla_local.coordinator import (
    FirewallaConfigEntry,
    FirewallaDataUpdateCoordinator,
)
from custom_components.firewalla_local.managers.flow_manager import (
    FirewallaFlowManager,
)
from custom_components.firewalla_local.models import (
    FirewallaFlowRecordSet,
    FirewallaFlowWindow,
)

_WINDOW_BEGIN = 1_790_948_400
_WINDOW_END = 1_791_034_800


def _client() -> FirewallaApiClient:
    """Build a client whose transport is replaced by these tests."""
    return FirewallaApiClient(
        session=cast(ClientSession, Mock()),
        host="192.0.2.1",
        gid="gid",
        eid="eid",
        aid="aid",
        symmetric_key="key",
        device_name="test",
    )


def _manager(client: FirewallaApiClient) -> FirewallaFlowManager:
    """Build a flow manager with isolated entry/coordinator dependencies."""
    return FirewallaFlowManager(
        cast(FirewallaDataUpdateCoordinator, Mock()),
        cast(FirewallaConfigEntry, Mock()),
        client,
    )


def _rollup_payload(
    *,
    begin: int = _WINDOW_BEGIN,
    end: int = _WINDOW_END,
    families: dict[str, object] | None = None,
    hosts: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a rollup response shaped like the box's."""
    if families is None:
        families = {
            "download": [
                {"host": "a.example", "count": "10", "begin": begin, "end": end}
            ],
            "upload": [
                {"host": "b.example", "count": "20", "begin": begin, "end": end}
            ],
        }
    payload: dict[str, object] = {"flows": families}
    if hosts is not None:
        payload["hosts"] = hosts
    return payload


def _page(
    *,
    records: list[dict[str, object]] | None = None,
    reported: int | None = None,
    cursor: float | None = None,
) -> FlowLogPage:
    """Build a flow page as the client would return it."""
    return FlowLogPage(
        records=tuple(records or []),
        reported_count=reported,
        next_cursor=cursor,
    )


@pytest.mark.asyncio
async def test_a_rollup_that_cannot_be_read_reports_unavailable() -> None:
    """Test a protocol failure yields None rather than propagating.

    The client raises on an unexpected shape, which is right for a protocol
    boundary; the manager turns that into "unavailable" so the service can report
    what it could not read instead of failing the whole call.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_rollup_payload = AsyncMock(
        side_effect=FirewallaProtocolError("unexpected shape")
    )

    assert await manager.async_get_rollup(target_type="tag", target="31") is None


@pytest.mark.asyncio
async def test_a_connectivity_failure_is_not_swallowed() -> None:
    """Test only shape failures are softened.

    A connection or auth failure is not "data unavailable" -- the coordinator owns
    how those surface -- so the manager must not hide them.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_rollup_payload = AsyncMock(
        side_effect=FirewallaConnectionError("box unreachable")
    )

    with pytest.raises(FirewallaConnectionError):
        await manager.async_get_rollup(target_type="tag", target="31")


@pytest.mark.asyncio
async def test_the_served_window_is_read_back_and_reported_as_clamped() -> None:
    """Test a 168h request served as 24h is reported as 24h and clamped.

    The box clamps silently, so the requested window is not evidence of what came
    back. A report claiming 168 hours would be describing data it does not have.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_rollup_payload = AsyncMock(return_value=_rollup_payload())

    rollup = await manager.async_get_rollup(
        target_type="tag",
        target="31",
        window_hours=168,
    )

    assert rollup is not None
    assert rollup.window.requested_hours == 168
    assert rollup.window.served_hours == pytest.approx(24.0)
    assert rollup.window.is_clamped is True
    assert rollup.window.begin_timestamp == _WINDOW_BEGIN
    assert rollup.window.end_timestamp == _WINDOW_END


@pytest.mark.asyncio
async def test_an_exactly_served_window_is_not_reported_as_clamped() -> None:
    """Test the clamp flag does not fire on a matching window.

    A 24h request answered with exactly 24h is the normal case, and calling it
    clamped would make the warning meaningless.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_rollup_payload = AsyncMock(return_value=_rollup_payload())

    rollup = await manager.async_get_rollup(
        target_type="tag",
        target="31",
        window_hours=24,
    )

    assert rollup is not None
    assert rollup.window.is_clamped is False


@pytest.mark.asyncio
async def test_an_empty_rollup_does_not_claim_the_requested_window() -> None:
    """Test a rollup with no rows reports no window rather than the request.

    With no row bounds there is nothing to say the box covered the requested
    span, so attributing it would be an invention.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_rollup_payload = AsyncMock(
        return_value=_rollup_payload(families={"ipB:in": []})
    )

    rollup = await manager.async_get_rollup(target_type="tag", target="31")

    assert rollup is not None
    assert rollup.families == {}
    assert rollup.window.served_hours is None
    assert rollup.window.is_clamped is False


@pytest.mark.asyncio
async def test_empty_families_are_omitted_and_junk_rows_dropped() -> None:
    """Test a family is absent rather than an empty placeholder.

    An empty family and an absent one mean the same thing here, so keeping both
    would only make a caller distinguish them.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_rollup_payload = AsyncMock(
        return_value=_rollup_payload(
            families={
                "download": [
                    {"host": "a.example", "begin": _WINDOW_BEGIN, "end": _WINDOW_END},
                    "not-a-row",
                    None,
                ],
                "dnsB": [],
                "ipB:in": "not-a-list",
                42: [{"host": "ignored"}],
            }
        )
    )

    rollup = await manager.async_get_rollup(target_type="tag", target="31")

    assert rollup is not None
    assert set(rollup.families) == {"download"}
    assert len(rollup.families["download"]) == 1


@pytest.mark.asyncio
async def test_member_rows_are_exposed_only_when_the_box_sends_them() -> None:
    """Test the member block is empty rather than invented on a device target.

    Only a tag request carries per-member rows, so an empty result means "not
    applicable" and the caller must not read it as "no members".
    """
    client = _client()
    manager = _manager(client)

    client.async_get_flow_rollup_payload = AsyncMock(
        return_value=_rollup_payload(hosts={"CC:28:AA:11:06:B7": {"download": 5}})
    )
    with_hosts = await manager.async_get_rollup(target_type="tag", target="31")
    assert with_hosts is not None
    assert with_hosts.hosts == {"CC:28:AA:11:06:B7": {"download": 5}}

    client.async_get_flow_rollup_payload = AsyncMock(return_value=_rollup_payload())
    without_hosts = await manager.async_get_rollup(
        target_type="host", target="CC:28:AA"
    )
    assert without_hosts is not None
    assert without_hosts.hosts == {}


@pytest.mark.asyncio
async def test_a_single_page_promises_nothing_about_completeness() -> None:
    """Test the default reads one page and surfaces the cursor.

    Auto-paging by default would turn a summary call into an unbounded number of
    box requests.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_log_payload = AsyncMock(
        return_value=_page(
            records=[{"ltype": "flow"}],
            reported=9001,
            cursor=1_791_017_277.18,
        )
    )

    result = await manager.async_get_flow_log(target_type="tag", target="31")

    assert result is not None
    assert result.pages_fetched == 1
    assert result.truncated is False
    assert result.next_cursor == 1_791_017_277.18
    assert result.rows_available == 9001
    assert client.async_get_flow_log_payload.await_count == 1


@pytest.mark.asyncio
async def test_fetch_all_walks_the_cursor_to_exhaustion() -> None:
    """Test the all-available mode follows next_cursor until it stops."""
    client = _client()
    manager = _manager(client)
    client.async_get_flow_log_payload = AsyncMock(
        side_effect=[
            _page(records=[{"id": 1}], reported=2, cursor=1_791_000_000.5),
            _page(records=[{"id": 2}], reported=2, cursor=None),
        ]
    )

    result = await manager.async_get_flow_log(
        target_type="tag",
        target="31",
        fetch_all=True,
    )

    assert result is not None
    assert result.pages_fetched == 2
    assert result.truncated is False
    assert [record["id"] for record in result.records] == [1, 2]


@pytest.mark.asyncio
async def test_a_non_advancing_cursor_stops_the_walk_and_is_reported_truncated() -> (
    None
):
    """Test a cursor that does not advance does not loop forever.

    The guard is on non-advance rather than equality-with-previous alone, because
    a page can legitimately end where the next one starts.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_log_payload = AsyncMock(
        return_value=_page(records=[{"id": 1}], cursor=1_791_000_000.5)
    )

    result = await manager.async_get_flow_log(
        target_type="tag",
        target="31",
        fetch_all=True,
    )

    assert result is not None
    assert result.truncated is True
    assert result.pages_fetched == 2
    assert result.next_cursor == 1_791_000_000.5


@pytest.mark.asyncio
async def test_the_deadline_stops_the_walk_and_is_reported_truncated() -> None:
    """Test the wall-clock deadline bounds an all-available walk.

    The only stops are the deadline and the loop guard -- never a row count, since
    the page ceiling is the box's and could change.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_log_payload = AsyncMock(
        return_value=_page(records=[{"id": 1}], cursor=1_791_000_000.5)
    )

    result = await manager.async_get_flow_log(
        target_type="tag",
        target="31",
        fetch_all=True,
        deadline_seconds=0,
    )

    assert result is not None
    assert result.truncated is True
    assert result.pages_fetched == 1


@pytest.mark.asyncio
async def test_records_repeated_across_a_page_boundary_are_dropped_and_counted() -> (
    None
):
    """Test the boundary dedupe is exact and visible.

    Deduplicated on the record's own content rather than a hand-picked key: a key
    built for blocked records is unsafe on regular ones, where ``pid`` is absent
    and one device's many same-second connections would collide.
    """
    client = _client()
    manager = _manager(client)
    shared = {"ltype": "flow", "device": "CC:28:AA:11:06:B7", "port": 443}
    client.async_get_flow_log_payload = AsyncMock(
        side_effect=[
            _page(records=[shared, {"id": "first-only"}], cursor=1_791_000_000.5),
            _page(records=[shared, {"id": "second-only"}], cursor=None),
        ]
    )

    result = await manager.async_get_flow_log(
        target_type="tag",
        target="31",
        fetch_all=True,
    )

    assert result is not None
    assert len(result.records) == 3
    assert result.records_dropped_as_duplicates == 1


@pytest.mark.asyncio
async def test_records_that_differ_only_in_a_fractional_timestamp_are_kept() -> None:
    """Test near-identical records are not merged.

    Sub-second ``ts`` values are how distinct flows separate, so a dedupe that
    rounded them would under-count.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_flow_log_payload = AsyncMock(
        side_effect=[
            _page(records=[{"ts": 1_791_000_000.1}], cursor=1_791_000_000.5),
            _page(records=[{"ts": 1_791_000_000.2}], cursor=None),
        ]
    )

    result = await manager.async_get_flow_log(
        target_type="tag",
        target="31",
        fetch_all=True,
    )

    assert result is not None
    assert len(result.records) == 2
    assert result.records_dropped_as_duplicates == 0


@pytest.mark.asyncio
async def test_the_block_log_uses_the_blocked_query_and_passes_its_filter() -> None:
    """Test blocked-only reads route to the block-log client method.

    The flow log cannot answer "what was blocked" alone -- `audit` adds blocked
    records to a page rather than filtering to them.
    """
    client = _client()
    manager = _manager(client)
    client.async_get_block_log_payload = AsyncMock(
        return_value=_page(records=[{"ltype": "audit"}], reported=1)
    )

    result = await manager.async_get_block_log(
        target_type="tag",
        target="31",
        category="games",
    )

    assert result is not None
    assert result.rows_returned == 1
    assert client.async_get_block_log_payload.await_args.kwargs["category"] == "games"
    assert client.async_get_block_log_payload.await_args.kwargs["target_type"] == "tag"


@pytest.mark.asyncio
async def test_the_flow_log_passes_the_include_blocked_flag() -> None:
    """Test the flow log forwards `include_blocked` rather than reinterpreting it."""
    client = _client()
    manager = _manager(client)
    client.async_get_flow_log_payload = AsyncMock(return_value=_page())

    await manager.async_get_flow_log(
        target_type="host",
        target="CC:28:AA:11:06:B7",
        include_blocked=True,
    )

    assert (
        client.async_get_flow_log_payload.await_args.kwargs["include_blocked"] is True
    )


def test_the_served_window_reports_no_span_without_both_bounds() -> None:
    """Test a half-known window reports no span rather than a wrong one."""
    window = FirewallaFlowWindow(
        requested_hours=24,
        begin_timestamp=_WINDOW_BEGIN,
        end_timestamp=None,
    )

    assert window.served_hours is None
    assert window.is_clamped is False


def test_the_record_set_keeps_rows_returned_apart_from_rows_available() -> None:
    """Test the two counts stay distinguishable.

    The box caps a page silently, so a truncated page and a quiet target must not
    read the same.
    """
    record_set = FirewallaFlowRecordSet(
        records=({"id": 1},),
        rows_available=9001,
        truncated=True,
    )

    assert record_set.rows_returned == 1
    assert record_set.rows_available == 9001
    assert record_set.truncated is True
