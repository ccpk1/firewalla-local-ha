"""Tests for the pure flow-report aggregation.

The fixtures mirror the live shapes recorded in
``docs/REVERSE_ENGINEERING_WORKFLOW.md``, including the awkward ones: one hostname
across several addresses, `count` meaning bytes on one family and a block count on
another, and a per-member block that is only populated on a tag request.
"""

from __future__ import annotations

import pytest

from custom_components.firewalla_local.const import (
    FLOW_DIRECTION_INBOUND,
    FLOW_DIRECTION_LOCAL,
    FLOW_DIRECTION_OUTBOUND,
)
from custom_components.firewalla_local.models import (
    FirewallaFlowRecordSet,
    FirewallaFlowRollup,
    FirewallaFlowWindow,
)
from custom_components.firewalla_local.utils.flow_report import (
    build_record_view,
    resolve_member_devices,
    summarise_rollup,
)

_BEGIN = 1_790_948_400
_END = 1_791_034_800


def _window() -> FirewallaFlowWindow:
    """Return one served window matching the live measurement."""
    return FirewallaFlowWindow(
        requested_hours=24, begin_timestamp=_BEGIN, end_timestamp=_END
    )


def _row(**fields: object) -> dict[str, object]:
    """Return one rollup row carrying the window bounds."""
    return {"begin": _BEGIN, "end": _END, **fields}


def _rollup(
    families: dict[str, tuple[dict[str, object], ...]] | None = None,
    hosts: dict[str, dict[str, object]] | None = None,
) -> FirewallaFlowRollup:
    """Build a rollup fixture."""
    return FirewallaFlowRollup(
        target_type="tag",
        target="31",
        window=_window(),
        families=families or {},
        hosts=hosts or {},
    )


def test_totals_sum_each_unit_without_adding_bytes_to_counts() -> None:
    """Test bytes and block counts are totalled separately.

    `count` is overloaded per family, so adding a byte total to a block count
    would be meaningless. Measured, the two differ by orders of magnitude.
    """
    summary = summarise_rollup(
        _rollup(
            {
                "download": (_row(count="1000"), _row(count="2500")),
                "upload": (_row(count="400"),),
                "local:download": (_row(count="70"),),
                "dnsB": (_row(count="9"),),
                "ipB:in": (_row(count="3"),),
                "ipB:out": (_row(count="2"),),
                "local:in": (_row(count="11"),),
                "local:out": (_row(count="5"),),
            }
        )
    )

    assert summary.totals.download_bytes == 3500
    assert summary.totals.upload_bytes == 400
    assert summary.totals.local_download_bytes == 70
    assert summary.totals.blocked_dns_count == 9
    assert summary.totals.blocked_ip_count == 5
    assert summary.totals.connection_count == 16
    assert summary.totals.total_bytes == 3900


def test_a_destination_is_merged_across_addresses_and_both_directions() -> None:
    """Test one hostname yields one row, carrying its addresses and both totals.

    Measured, 43 of 116 hosts in a single window resolved to more than one
    address, so keying per address listed one hostname repeatedly and understated
    each entry.
    """
    summary = summarise_rollup(
        _rollup(
            {
                "download": (
                    _row(
                        host="speed.cloudflare.com", ip="162.159.140.220", count="100"
                    ),
                    _row(host="speed.cloudflare.com", ip="172.66.0.218", count="250"),
                ),
                "upload": (
                    _row(host="speed.cloudflare.com", ip="162.159.140.220", count="7"),
                ),
            }
        )
    )

    download_rows = summary.top_download
    assert len(download_rows) == 1
    assert download_rows[0].destination == "speed.cloudflare.com"
    assert download_rows[0].download_bytes == 350
    assert download_rows[0].destination_ips == ("162.159.140.220", "172.66.0.218")
    assert download_rows[0].rollup_rows == 2

    # The upload list is ranked over the same rows but by the other direction, so
    # it reports the upload figure for the same destination.
    assert len(summary.top_upload) == 1
    assert summary.top_upload[0].destination == "speed.cloudflare.com"
    assert summary.top_upload[0].upload_bytes == 7
    assert summary.top_upload[0].download_bytes == 0


def test_the_two_direction_lists_rank_differently() -> None:
    """Test ranking by one direction is not the same as ranking by the total.

    A destination can be the top downloader and a minor uploader, so ranking both
    lists by the combined total would make them the same list twice.
    """
    summary = summarise_rollup(
        _rollup(
            {
                "download": (
                    _row(host="big-download.example", ip="1.1.1.1", count="900"),
                    _row(host="big-upload.example", ip="2.2.2.2", count="10"),
                ),
                "upload": (
                    _row(host="big-download.example", ip="1.1.1.1", count="1"),
                    _row(host="big-upload.example", ip="2.2.2.2", count="800"),
                ),
            }
        )
    )

    assert summary.top_download[0].destination == "big-download.example"
    assert summary.top_upload[0].destination == "big-upload.example"


def test_a_destination_records_the_devices_that_reached_it() -> None:
    """Test the per-destination attribution is collected from the rows.

    This is what is gated at serialization rather than discarded here, so the gate
    stays a presentation decision instead of a data loss.
    """
    summary = summarise_rollup(
        _rollup(
            {
                "download": (
                    _row(host="a.example", ip="1.1.1.1", device="AA:BB:CC:DD:EE:01"),
                    _row(host="a.example", ip="1.1.1.1", device="AA:BB:CC:DD:EE:02"),
                ),
            }
        )
    )

    assert summary.top_download[0].device_ids == (
        "AA:BB:CC:DD:EE:01",
        "AA:BB:CC:DD:EE:02",
    )


def test_a_blocked_destination_keeps_its_kind_and_direction_apart() -> None:
    """Test DNS versus IP and in versus out are not folded together.

    "What did this device try to reach" and "what tried to reach it" are different
    questions, and a DNS block is a different event from an IP block.
    """
    summary = summarise_rollup(
        _rollup(
            {
                "dnsB": (_row(domain="blocked.example", count="5"),),
                "ipB:in": (_row(host="in.example", ip="1.1.1.1", count="3"),),
                "ipB:out": (_row(host="out.example", ip="2.2.2.2", count="4"),),
            }
        )
    )

    by_key = {
        (row.destination, row.block_type, row.direction) for row in summary.blocked
    }
    assert by_key == {
        ("blocked.example", "dns", None),
        ("in.example", "ip", FLOW_DIRECTION_INBOUND),
        ("out.example", "ip", FLOW_DIRECTION_OUTBOUND),
    }
    assert [row.block_count for row in summary.blocked] == [5, 4, 3]


def test_a_blocked_destination_is_a_separate_model_from_a_traffic_one() -> None:
    """Test a block count is not presented as bytes.

    A blocked flow never travelled, so its `count` is a number of blocks. Keeping
    it in its own model means a caller cannot read one as the other.
    """
    summary = summarise_rollup(
        _rollup({"dnsB": (_row(domain="blocked.example", count="42"),)})
    )

    assert not hasattr(summary.blocked[0], "download_bytes")
    assert summary.blocked[0].block_count == 42
    assert summary.top_download == ()


def test_a_local_peer_is_identified_by_its_mac() -> None:
    """Test LAN traffic is listed separately, by peer MAC.

    Traffic that never left the network has no hostname to resolve to, so a peer
    cannot be represented as a destination.
    """
    summary = summarise_rollup(
        _rollup(
            {
                "local:in": (
                    _row(dstMac="F8:0F:F9:3B:22:2E", count="1000"),
                    _row(dstMac="F8:0F:F9:3B:22:2E", count="39"),
                ),
                "local:out": (_row(dstMac="F8:0F:F9:3B:22:2E", count="1"),),
            }
        )
    )

    assert len(summary.local_peers) == 1
    assert summary.local_peers[0].peer_id == "F8:0F:F9:3B:22:2E"
    assert summary.local_peers[0].connection_count == 1040


def test_members_are_named_from_the_inventory_and_ranked_by_traffic() -> None:
    """Test a member is named when the inventory knows it, and ranked by total."""
    summary = summarise_rollup(
        _rollup(
            hosts={
                "AA:BB:CC:DD:EE:01": {"download": 10, "upload": 90},
                "AA:BB:CC:DD:EE:02": {"download": 500, "upload": 0},
            }
        ),
        device_names={
            "AA:BB:CC:DD:EE:01": "quiet-device",
            "AA:BB:CC:DD:EE:02": "busy-device",
        },
        device_addresses={"AA:BB:CC:DD:EE:02": "192.168.200.5"},
    )

    assert [member.device_name for member in summary.top_members] == [
        "busy-device",
        "quiet-device",
    ]
    assert summary.top_members[0].device_ip == "192.168.200.5"
    assert summary.top_members[0].total_bytes == 500
    assert summary.top_members[1].total_bytes == 100


def test_a_member_the_inventory_does_not_know_keeps_no_name() -> None:
    """Test an unknown device id is not given a name or dropped.

    An `if:` device names a network interface and has no inventory entry, so the
    name is absent rather than defaulted to the id.
    """
    summary = summarise_rollup(
        _rollup(hosts={"if:913620a3-8f17-4987-beb0-a91b12eb4476": {"download": 1}})
    )

    assert summary.top_members[0].device_name is None
    assert summary.top_members[0].device_id.startswith("if:")


def test_member_counters_map_to_their_own_fields_including_local_variants() -> None:
    """Test the `:lo` LAN counters do not land in the WAN-facing fields."""
    summary = summarise_rollup(
        _rollup(
            hosts={
                "AA:BB:CC:DD:EE:01": {
                    "download": 100,
                    "upload": 200,
                    "download:lo": 7,
                    "upload:lo": 8,
                    "conn": 9,
                    "dns": 2,
                    "dnsB": 3,
                    "ipB": 4,
                    "ipD": 5,
                    "ntp": 6,
                }
            }
        )
    )

    member = summary.top_members[0]
    assert member.download_bytes == 100
    assert member.upload_bytes == 200
    assert member.local_download_bytes == 7
    assert member.local_upload_bytes == 8
    assert member.connection_count == 9
    assert member.dns_count == 2
    assert member.blocked_dns_count == 3
    assert member.blocked_ip_count == 4
    assert member.denied_ip_count == 5
    assert member.ntp_count == 6
    assert member.blocked_total == 12


def test_family_row_counts_let_a_caller_see_the_rollup_size() -> None:
    """Test the summary reports how many rows each family carried."""
    summary = summarise_rollup(
        _rollup(
            {
                "download": (_row(count="1"), _row(count="2")),
                "dnsB": (_row(count="3"),),
            }
        )
    )

    assert summary.family_row_counts == {"download": 2, "dnsB": 1}
    assert summary.rollup_rows == 3


def test_an_empty_rollup_summarises_to_empty_sections() -> None:
    """Test nothing to report is not an error, and claims no window."""
    summary = summarise_rollup(_rollup())

    assert summary.top_download == ()
    assert summary.top_upload == ()
    assert summary.blocked == ()
    assert summary.top_members == ()
    assert summary.rollup_rows == 0
    assert summary.window.served_hours == pytest.approx(24.0)


def test_a_block_is_joined_to_its_rule_by_id() -> None:
    """Test a blocked record resolves its rule name when the rule still exists."""
    view = build_record_view(
        FirewallaFlowRecordSet(
            records=(
                {"ltype": "audit", "pid": 455, "domain": "discord.com", "ts": 1.0},
                {"ltype": "audit", "pid": 406, "domain": "x.com", "ts": 2.0},
            ),
            rows_available=2,
        ),
        rule_names={455: "block discord", 406: "block social"},
    )

    assert view.rows_returned == 2
    assert view.blocked_count == 2
    assert view.rule_names == {455: "block discord", 406: "block social"}
    assert view.unattributed_blocks == 0


def test_a_block_whose_rule_is_gone_is_kept_and_counted() -> None:
    """Test an unresolvable rule id does not drop the record.

    Rule ids are not durable across a delete and re-create, so an id that resolves
    to nothing is expected. The block still happened, and an unattributable block
    is exactly the signal worth surfacing.
    """
    view = build_record_view(
        FirewallaFlowRecordSet(
            records=(
                {"ltype": "audit", "pid": 999, "domain": "gone.example", "ts": 1.0},
                {"ltype": "audit", "pid": 455, "domain": "known.example", "ts": 2.0},
            )
        ),
        rule_names={455: "block known"},
    )

    assert view.rows_returned == 2
    assert view.unattributed_blocks == 1
    assert view.rule_names == {455: "block known"}
    assert view.records[0].blocked_by_rule_id == 999


def test_regular_records_are_not_counted_as_unattributed_blocks() -> None:
    """Test a regular record has no rule to resolve and is not counted as an orphan.

    Only a blocked record names a rule, so counting a regular one would report
    every allowed flow as an attribution failure.
    """
    view = build_record_view(
        FirewallaFlowRecordSet(records=({"ltype": "flow", "download": 10, "ts": 1.0},)),
        rule_names={},
    )

    assert view.unattributed_blocks == 0
    assert view.blocked_count == 0


def test_the_record_view_carries_the_completeness_and_truncation_fields() -> None:
    """Test the page bookkeeping survives into the view.

    A capped page and a quiet target must not read the same, and a dedupe that
    merged distinct records has to be visible.
    """
    view = build_record_view(
        FirewallaFlowRecordSet(
            records=({"ltype": "audit", "pid": 1, "ts": 1.0},),
            rows_available=9001,
            next_cursor=1_791_017_277.18,
            truncated=True,
            pages_fetched=3,
            records_dropped_as_duplicates=2,
        )
    )

    assert view.rows_returned == 1
    assert view.rows_available == 9001
    assert view.next_cursor == 1_791_017_277.18
    assert view.truncated is True
    assert view.pages_fetched == 3
    assert view.records_dropped_as_duplicates == 2


def test_member_device_ids_are_reported_with_an_unresolved_count() -> None:
    """Test a caller can tell how many members could not be named."""
    summary = summarise_rollup(
        _rollup(
            hosts={
                "AA:BB:CC:DD:EE:01": {"download": 1},
                "if:abc": {"download": 1},
                "wg_peer:xyz": {"download": 1},
            }
        ),
        device_names={
            "AA:BB:CC:DD:EE:01": "known",
            "wg_peer:xyz": "kadens-chromebook",
        },
    )

    device_ids, unresolved = resolve_member_devices(summary.top_members)

    assert len(device_ids) == 3
    assert unresolved == 1


def test_a_summary_does_not_call_a_local_family_inbound_or_outbound() -> None:
    """Test a local family is `local` even when it also says `:in` or `:out`.

    That suffix describes the interface side; the traffic never left the network,
    so neither inbound nor outbound is right.
    """
    summary = summarise_rollup(
        _rollup({"local:ipB:out": (_row(ip="192.168.200.5", count="1"),)})
    )

    assert summary.blocked[0].direction == FLOW_DIRECTION_LOCAL
