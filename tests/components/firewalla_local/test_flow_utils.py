"""Tests for the shared flow-row reading helpers."""

from __future__ import annotations

import pytest

from custom_components.firewalla_local.utils.flow import (
    FlowHostActivity,
    build_flow_record,
    flow_family_direction,
    flow_family_unit,
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


def test_a_regular_record_is_read_with_its_bytes_and_session_detail() -> None:
    """Test a `ltype: flow` record yields everything it carries.

    These are the fields the previous rule-hit reader dropped, so a rule surface
    could not say how much a rule matched or for how long.
    """
    record = build_flow_record(
        {
            "ltype": "flow",
            "ts": 1791082504.38,
            "device": "CC:28:AA:11:06:B7",
            "deviceIP": "192.168.200.122",
            "host": "api.epicgames.dev",
            "ip": "104.18.125.108",
            "port": 443,
            "devicePort": 51103,
            "protocol": "udp",
            "download": 4046,
            "upload": 8597,
            "duration": 0.09,
            "count": 1,
            "apid": 50,
            "category": "games",
            "country": "US",
            "intf": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
            "oIntf": "8d5a7f20-2923-49a3-8e2b-338f9428a632",
            "tags": ["31"],
            "userTags": ["32"],
            "flowTags": ["noise"],
        }
    )

    assert record.is_blocked is False
    assert record.download_bytes == 4046
    assert record.upload_bytes == 8597
    assert record.total_bytes == 12643
    assert record.duration_seconds == pytest.approx(0.09)
    assert record.event_count == 1
    assert record.apid == 50
    assert record.device_port == 51103
    assert record.category == "games"
    assert record.region == "US"
    assert record.tags == ("31",)
    assert record.user_tags == ("32",)
    assert record.flow_tags == ("noise",)
    # A regular record is not blocked, so it names no rule.
    assert record.blocked_by_rule_id is None
    assert record.block_type is None


def test_a_blocked_record_names_its_rule_and_reports_no_bytes() -> None:
    """Test a blocked record's absent bytes stay absent rather than becoming 0.

    Firewalla intercepts a blocked flow before it travels, so there is no byte
    total to report. A `0` would read as a measured empty transfer.
    """
    record = build_flow_record(
        {
            "ltype": "audit",
            "ts": 1791082508.949,
            "device": "CC:28:AA:11:06:B7",
            "deviceIP": "192.168.200.122",
            "domain": "updates.discord.com",
            "port": 53,
            "protocol": "dns",
            "pid": 455,
            "type": "dns",
            "count": 1,
            "intf": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2",
        }
    )

    assert record.is_blocked is True
    assert record.blocked_by_rule_id == 455
    assert record.block_type == "dns"
    assert record.destination == "updates.discord.com"
    assert record.destination_kind == "domain"
    assert record.download_bytes is None
    assert record.upload_bytes is None
    assert record.total_bytes is None
    assert record.duration_seconds is None


@pytest.mark.parametrize(
    ("raw_row", "expected"),
    [
        pytest.param(None, None, id="ltype_absent_is_not_false"),
        pytest.param("weird", False, id="unknown_ltype_is_not_blocked"),
        pytest.param("audit", True, id="blocked"),
        pytest.param("flow", False, id="regular"),
    ],
)
def test_blockedness_is_tri_state_when_ltype_is_absent(
    raw_row: str | None,
    expected: bool | None,
) -> None:
    """Test an absent `ltype` reads as unknown rather than as "allowed through".

    The box reported `ltype` on every record measured, so this is a guard rather
    than a live case -- but `False` would be a positive claim about a record we
    cannot classify.
    """
    row: dict[str, object] = {} if raw_row is None else {"ltype": raw_row}
    assert build_flow_record(row).is_blocked is expected


@pytest.mark.parametrize(
    ("raw_row", "expected_kind"),
    [
        pytest.param(
            {"host": "a.example", "ip": "1.2.3.4"}, "host", id="resolved_host"
        ),
        pytest.param({"domain": "b.example"}, "domain", id="dns_match"),
        pytest.param({"ip": "1.2.3.4"}, "ip", id="ip_only"),
        pytest.param({"dstMac": "F8:0F:F9:3B:22:2E"}, "peer", id="lan_peer"),
        pytest.param({}, None, id="no_destination_at_all"),
    ],
)
def test_a_destination_is_classified_by_the_name_it_resolved_to(
    raw_row: dict[str, object],
    expected_kind: str | None,
) -> None:
    """Test host, domain, ip and a LAN peer's id are told apart.

    A LAN peer is a **peer id** rather than a MAC: measured, 20 of 21 live local
    records held a MAC and 1 held an `awg_peer:` id, and that id can appear in
    either `device` or `dstMac`, so the field says nothing about which side is the
    peer.
    """
    assert build_flow_record(raw_row).destination_kind == expected_kind


def test_the_ip_is_exposed_alongside_a_resolved_name() -> None:
    """Test a resolved destination still reports the address it resolved to."""
    record = build_flow_record({"host": "a.example", "ip": "1.2.3.4"})

    assert record.destination == "a.example"
    assert record.destination_ip == "1.2.3.4"


@pytest.mark.parametrize(
    ("family", "expected"),
    [
        pytest.param("download", "bytes", id="download_is_bytes"),
        pytest.param("upload", "bytes", id="upload_is_bytes"),
        pytest.param("local:download", "bytes", id="local_byte_family"),
        pytest.param("dnsB", "blocked", id="dns_block_count"),
        pytest.param("ipB:in", "blocked", id="ip_block_count"),
        pytest.param("local:ipB:out", "blocked", id="local_block_count"),
        pytest.param("local:in", "connections", id="lan_connection_count"),
        pytest.param("brand:new", None, id="unknown_family_is_not_assumed_bytes"),
    ],
)
def test_a_family_declares_which_unit_its_count_is_in(
    family: str,
    expected: str | None,
) -> None:
    """Test `count` is never assumed to be bytes.

    The box overloads `count` and documents doing so. Measured, the byte families
    are orders of magnitude larger than the blocked ones, so reading a blocked
    family as bytes understates it by thousands of times. An unrecognised family
    reports `None` rather than guessing, because guessing bytes is the specific
    misreading this prevents.
    """
    assert flow_family_unit(family) == expected


@pytest.mark.parametrize(
    ("family", "expected"),
    [
        pytest.param("download", "inbound", id="download"),
        pytest.param("upload", "outbound", id="upload"),
        pytest.param("ipB:in", "inbound", id="blocked_in"),
        pytest.param("ipB:out", "outbound", id="blocked_out"),
        pytest.param("local:download", "local", id="lan_stays_local"),
        pytest.param("local:ipB:out", "local", id="lan_blocked_is_still_local"),
        pytest.param("brand:new", None, id="unknown"),
    ],
)
def test_direction_comes_from_the_family_name(
    family: str, expected: str | None
) -> None:
    """Test direction is read from the family, never from `fd`.

    Measured: `fd` is "in" on all 199 `download` rows *and* all 199 `upload`
    rows, so it cannot be a byte direction. A `local:` family is neither inbound
    nor outbound -- it never leaves the network.
    """
    assert flow_family_direction(family) == expected


def test_the_reader_does_not_read_fd_as_a_direction() -> None:
    """Test a record carrying only `fd` reports no direction.

    A record has no family name, and `fd` is not a direction, so there is nothing
    to derive one from. Reporting `inbound` from `fd: "in"` would be the exact
    inversion this avoids.
    """
    record = build_flow_record({"ltype": "flow", "fd": "in", "download": 1})

    assert not hasattr(record, "direction")


def test_an_explicit_zero_byte_total_is_kept_as_zero_not_absent() -> None:
    """Test a measured empty transfer is distinguishable from no transfer at all.

    The box sends `download: 0` on real regular records -- 188 of one 5,000-record
    page -- while a blocked record omits the field entirely. Both must survive as
    themselves, so `0` means "transferred nothing" and `None` means "never
    travelled".
    """
    measured_zero = build_flow_record({"ltype": "flow", "download": 0, "upload": 0})
    absent = build_flow_record({"ltype": "audit", "count": 3})

    assert measured_zero.download_bytes == 0
    assert measured_zero.upload_bytes == 0
    assert measured_zero.total_bytes == 0

    assert absent.download_bytes is None
    assert absent.upload_bytes is None
    assert absent.total_bytes is None


def test_a_peer_id_in_dst_mac_is_still_a_peer_not_a_mac() -> None:
    """Test an `awg_peer:` value in `dstMac` is read as a peer id.

    Measured: 1 of 21 live local records held a peer id there while the other 20
    held a MAC, and that record carried the MAC in `device` instead. So neither
    field is 'the MAC field'.
    """
    record = build_flow_record(
        {
            "ltype": "flow",
            "device": "02:42:0B:C8:00:28",
            "dstMac": "awg_peer:NyiNpEGJhGMdfgALgzbyuXPf346uXZA2JNNuQABwzUM=",
            "local": True,
            "download": 64,
        }
    )

    assert record.destination_kind == "peer"
    assert record.destination is not None
    assert record.destination.startswith("awg_peer:")
    assert record.device_id == "02:42:0B:C8:00:28"


def test_a_record_without_ltype_is_not_classified_either_way() -> None:
    """Test an unclassifiable record is not silently called regular.

    `ltype` was `audit` or `flow` on all 12,315 records measured, so this is a
    guard rather than a live case -- but answering `False` would be a positive
    claim that a record we could not read was allowed through.
    """
    record = build_flow_record({"download": 10, "upload": 20})

    assert record.is_blocked is None
    assert record.total_bytes == 30
