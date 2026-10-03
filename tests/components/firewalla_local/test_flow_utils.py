"""Tests for the shared flow-row reading helpers."""

from __future__ import annotations

import pytest

from custom_components.firewalla_local.utils.flow import (
    FlowHostActivity,
    flow_row_host_id,
    flow_row_metric_value,
    flow_row_remote_host,
    flow_row_remote_ip,
    host_traffic_sort_key,
    iter_flow_rows,
)


@pytest.mark.parametrize(
    ("raw_row", "expected"),
    [
        pytest.param({"device": "CC:28:AA:11:06:B7"}, "CC:28:AA:11:06:B7", id="device"),
        pytest.param({"mac": "CC:28:AA:11:06:B7"}, "CC:28:AA:11:06:B7", id="mac"),
        pytest.param(
            {"deviceMac": "CC:28:AA:11:06:B7"}, "CC:28:AA:11:06:B7", id="device_mac"
        ),
        pytest.param(
            {"device": "AA:BB:CC:DD:EE:FF", "mac": "11:22:33:44:55:66"},
            "AA:BB:CC:DD:EE:FF",
            id="device_wins_over_mac",
        ),
        pytest.param({"device": "  "}, None, id="blank_is_absent"),
        pytest.param({"domain": "graph.oculus.com"}, None, id="no_identifier"),
    ],
)
def test_the_same_host_identity_is_read_from_any_of_its_field_names(
    raw_row: dict[str, object],
    expected: str | None,
) -> None:
    """One host identity arrives under three names depending on the row family."""
    assert flow_row_host_id(raw_row) == expected


@pytest.mark.parametrize(
    ("raw_row", "expected"),
    [
        pytest.param({"download": 500}, 500, id="named_metric"),
        pytest.param({"bytes": 500}, 500, id="bytes_fallback"),
        pytest.param({"count": 500}, 500, id="count_fallback"),
        pytest.param({"download": "500"}, 500, id="numeric_string"),
        pytest.param({}, None, id="absent"),
        pytest.param({"download": "not a number"}, None, id="unparseable"),
        pytest.param({"download": None}, None, id="explicit_null"),
    ],
)
def test_a_metric_is_read_from_its_named_field_or_a_generic_one(
    raw_row: dict[str, object],
    expected: int | None,
) -> None:
    """The same measurement is named after the metric, or generically."""
    assert flow_row_metric_value(raw_row, metric_key="download") == expected


def test_a_zero_metric_still_falls_through_to_the_next_field() -> None:
    """Preserved from the `or` chain this replaced.

    A zero is falsy, so a row carrying both a zero metric and a populated
    generic field resolves to the populated one. The field names describe the
    same measurement and are not expected to coexist with differing values, so
    the case is not reachable in practice -- but it is existing behaviour and is
    asserted here rather than silently changed.
    """
    assert (
        flow_row_metric_value({"download": 0, "bytes": 700}, metric_key="download")
        == 700
    )


def test_an_all_zero_metric_reads_as_zero_not_absent() -> None:
    """A row that reports zero everywhere reports zero, not nothing."""
    assert flow_row_metric_value({"download": 0}, metric_key="download") == 0


@pytest.mark.parametrize(
    ("raw_row", "expected"),
    [
        pytest.param(
            {"host": "catalog.gamepass.com"}, "catalog.gamepass.com", id="host"
        ),
        pytest.param({"domain": "lencr.org"}, "lencr.org", id="domain"),
        pytest.param(
            {"host": "a.example", "domain": "b.example"}, "a.example", id="host_first"
        ),
        pytest.param({"ip": "23.1.254.210"}, None, id="ip_only_is_not_a_hostname"),
    ],
)
def test_a_destination_name_is_read_from_host_or_domain(
    raw_row: dict[str, object],
    expected: str | None,
) -> None:
    """A connection row says host and a DNS row says domain, for one destination."""
    assert flow_row_remote_host(raw_row) == expected


def test_a_destination_address_is_read_separately_from_its_name() -> None:
    """The address is a distinct field, not a fallback for the name."""
    raw_row = {"host": "catalog.gamepass.com", "ip": "23.1.254.210"}
    assert flow_row_remote_ip(raw_row) == "23.1.254.210"
    assert flow_row_remote_ip({"host": "catalog.gamepass.com"}) is None


def test_a_bare_list_of_rows_is_read_as_is() -> None:
    """Endpoints that return a plain list are the common case."""
    rows = iter_flow_rows([{"download": 1}, {"download": 2}])
    assert [row["download"] for row in rows] == [1, 2]


@pytest.mark.parametrize(
    "container_key",
    ["flows", "download", "upload", "items", "results"],
)
def test_a_wrapped_list_of_rows_is_unwrapped(container_key: str) -> None:
    """Ranking payloads wrap the row list inconsistently across endpoints."""
    rows = iter_flow_rows({container_key: [{"download": 1}]})
    assert [row["download"] for row in rows] == [1]


def test_entries_that_are_not_rows_are_dropped_rather_than_raising() -> None:
    """A shape change degrades to nothing to report, not a failed refresh."""
    rows = iter_flow_rows([{"download": 1}, "junk", None, 3, {"download": 2}])
    assert [row["download"] for row in rows] == [1, 2]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(None, id="none"),
        pytest.param("a string", id="string"),
        pytest.param(42, id="number"),
        pytest.param({}, id="empty_mapping"),
        pytest.param({"unexpected": []}, id="unrecognized_container"),
    ],
)
def test_a_payload_with_no_rows_yields_nothing(payload: object) -> None:
    """Anything that is not a row list reads as empty rather than raising."""
    assert iter_flow_rows(payload) == ()


def test_hosts_are_ordered_by_traffic_then_name_then_id() -> None:
    """Ordering has to be stable, because equal totals are common.

    The key negates the total so that an ascending sort puts the largest talker
    first.
    """
    key = host_traffic_sort_key

    assert key(download_bytes=20, upload_bytes=0, host_name="a", host_id="2") < key(
        download_bytes=10, upload_bytes=0, host_name="b", host_id="1"
    )
    assert key(download_bytes=10, upload_bytes=0, host_name="a", host_id="2") < key(
        download_bytes=10, upload_bytes=0, host_name="b", host_id="1"
    )
    assert key(download_bytes=10, upload_bytes=0, host_name="a", host_id="1") < key(
        download_bytes=10, upload_bytes=0, host_name="a", host_id="2"
    )


def test_upload_bytes_count_towards_the_total() -> None:
    """A host with the same download but more upload ranks higher."""
    key = host_traffic_sort_key

    assert key(download_bytes=10, upload_bytes=90, host_name="a", host_id="1") < key(
        download_bytes=10, upload_bytes=0, host_name="b", host_id="2"
    )


def test_the_name_tie_break_is_case_insensitive() -> None:
    """Mixed-case names must not order by codepoint, which would look random."""
    key = host_traffic_sort_key

    assert key(download_bytes=0, upload_bytes=0, host_name="apple", host_id="1") < key(
        download_bytes=0, upload_bytes=0, host_name="Banana", host_id="2"
    )


def test_a_host_with_no_name_still_orders_deterministically() -> None:
    """An unresolved host name sorts before named hosts rather than raising."""
    key = host_traffic_sort_key

    assert key(download_bytes=5, upload_bytes=0, host_name=None, host_id="1") < key(
        download_bytes=5, upload_bytes=0, host_name="aster", host_id="2"
    )


def test_activity_starts_absent_and_accumulates_across_families() -> None:
    """One host is described by three families, so it accumulates in place."""
    activity = FlowHostActivity()
    assert activity.conn == 0
    assert activity.download_bytes == 0
    assert activity.host_name is None

    activity.download_bytes += 500
    activity.conn += 2
    activity.host_name = "kids-ipad"

    assert activity.download_bytes == 500
    assert activity.conn == 2
    assert activity.host_name == "kids-ipad"
