"""Pure flow-row reading and ordering for Firewalla payloads.

The Firewalla app's flow report, the ``item=intf`` network summary, and the
per-target rollup all carry the *same* flow-row families, and the integration
decoded them by hand in five separate places. Four of those steps were exact
duplicates:

- the host identifier, which arrives as ``device``, ``mac``, or ``deviceMac``
  depending on which family the row came from (five copies)
- the metric value, which is named after the metric on a ranking row and
  ``bytes`` or ``count`` on an activity row (two copies)
- the remote destination, which is ``host`` on a connection row and ``domain``
  on a DNS row, with the address in ``ip``
- the envelope, which is sometimes a bare list and sometimes a list wrapped in
  ``flows``, ``download``, ``upload``, ``items``, or ``results``

A field-name variation therefore had to be fixed in five places at once, and a
caller that missed one silently read ``None``. These helpers are the single
definition so that cannot happen again.

Everything here is a pure function over a decoded payload. Deciding *which*
families to read, and shaping the result into the integration's models, stays
with the owning manager: that is view shaping and orchestration, and it belongs
in the manager layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ..const import (
    FLOW_DIRECTION_INBOUND,
    FLOW_DIRECTION_LOCAL,
    FLOW_DIRECTION_OUTBOUND,
    FLOW_UNIT_BLOCKED,
    FLOW_UNIT_BYTES,
    FLOW_UNIT_CONNECTIONS,
)
from ..models import FirewallaFlowRecord, FirewallaNetworkUsageWindow
from .values import normalized_float, normalized_int, normalized_string

# The same identity arrives under three names depending on the family: audit and
# activity rows say ``device``, ranking rows say ``mac``, and an older variant
# says ``deviceMac``.
_RAW_FLOW_HOST_ID_KEYS: Final = ("device", "mac", "deviceMac")

# A ranking row names the metric in the field itself; an activity row carries a
# generic ``bytes`` or ``count`` instead.
_RAW_FLOW_METRIC_FALLBACK_KEYS: Final = ("bytes", "count")

# Connection rows carry a resolved hostname, DNS rows a domain, and either may
# carry the address separately.
_RAW_FLOW_HOSTNAME_KEYS: Final = ("host", "domain")
_RAW_FLOW_IP_KEY: Final = "ip"

# The windowed totals the rollup and the ``item=intf`` payload both carry. The
# two sources use the same keys for the same measurement, which is why the parser
# lives here rather than in either consumer.
_RAW_USAGE_DOWNLOAD_KEY: Final = "totalDownload"
_RAW_USAGE_UPLOAD_KEY: Final = "totalUpload"

# Ranking payloads are wrapped inconsistently across endpoints and firmware.
_RAW_FLOW_LIST_CONTAINER_KEYS: Final = (
    "flows",
    "download",
    "upload",
    "items",
    "results",
)

# Wire keys for the event-level record the flow log, the block log and a rule's
# ``lastHitFlow`` all carry. Verified identical: every one of the 32 fields a live
# flow-log record had appears in ``lastHitFlow`` too.
_RAW_RECORD_TS_KEY: Final = "ts"
_RAW_RECORD_LTYPE_KEY: Final = "ltype"
_RAW_RECORD_DEVICE_IP_KEY: Final = "deviceIP"
_RAW_RECORD_PORT_KEY: Final = "port"
_RAW_RECORD_DEVICE_PORT_KEY: Final = "devicePort"
_RAW_RECORD_PROTOCOL_KEY: Final = "protocol"
_RAW_RECORD_PID_KEY: Final = "pid"
_RAW_RECORD_TYPE_KEY: Final = "type"
_RAW_RECORD_DOWNLOAD_KEY: Final = "download"
_RAW_RECORD_UPLOAD_KEY: Final = "upload"
_RAW_RECORD_DURATION_KEY: Final = "duration"
_RAW_RECORD_COUNT_KEY: Final = "count"
_RAW_RECORD_INTF_KEY: Final = "intf"
_RAW_RECORD_OINTF_KEY: Final = "oIntf"
_RAW_RECORD_DINTF_KEY: Final = "dIntf"
_RAW_RECORD_WANINTF_KEY: Final = "wanIntf"
_RAW_RECORD_APID_KEY: Final = "apid"
_RAW_RECORD_CATEGORY_KEY: Final = "category"
_RAW_RECORD_APP_KEY: Final = "app"
_RAW_RECORD_COUNTRY_KEY: Final = "country"
_RAW_RECORD_DSTMAC_KEY: Final = "dstMac"
_RAW_RECORD_TAGS_KEY: Final = "tags"
_RAW_RECORD_USER_TAGS_KEY: Final = "userTags"
_RAW_RECORD_DTAGS_KEY: Final = "dTags"
_RAW_RECORD_DST_TAGS_KEY: Final = "dstTags"
_RAW_RECORD_FLOW_TAGS_KEY: Final = "flowTags"

# `local: true` on the rollup adds family names carrying this segment, which marks
# a flow between two LAN hosts rather than one leaving the network.
_LOCAL_FAMILY_SEGMENT: Final = "local"

# Which unit a rollup family's `count` is in. The box overloads it, and it
# documents doing so: connections or sessions for a flow, block count for a
# blocked one. Measured, the byte families are orders of magnitude larger than
# the blocked ones (min 49,148 bytes versus max 5,410 blocks), so reading a
# blocked family as bytes would understate it by thousands of times.
_FLOW_UNIT_BY_FAMILY: Final = {
    "download": FLOW_UNIT_BYTES,
    "upload": FLOW_UNIT_BYTES,
    "local:download": FLOW_UNIT_BYTES,
    "local:upload": FLOW_UNIT_BYTES,
    "dnsB": FLOW_UNIT_BLOCKED,
    "ipB:in": FLOW_UNIT_BLOCKED,
    "ipB:out": FLOW_UNIT_BLOCKED,
    "local:ipB:in": FLOW_UNIT_BLOCKED,
    "local:ipB:out": FLOW_UNIT_BLOCKED,
    "local:in": FLOW_UNIT_CONNECTIONS,
    "local:out": FLOW_UNIT_CONNECTIONS,
}


def flow_row_host_id(raw_row: Mapping[str, object]) -> str | None:
    """Return the host identifier from one flow row.

    Tries ``device``, then ``mac``, then ``deviceMac``, so a caller does not have
    to know which family the row came from.
    """
    for key in _RAW_FLOW_HOST_ID_KEYS:
        host_id = normalized_string(raw_row.get(key))
        if host_id is not None:
            return host_id
    return None


def flow_row_metric_value(
    raw_row: Mapping[str, object],
    *,
    metric_key: str,
) -> int | None:
    """Return one flow row's value for ``metric_key``.

    Falls back to ``bytes`` and then ``count``, because the same measurement is
    named after the metric on a ranking row and generically on an activity row.

    A zero falls through to the next field, and an all-zero row reports zero
    rather than absent. That is preserved from the ``or`` chain this replaced
    rather than simplified, because both cases are observable: the field names
    describe one measurement and are not expected to coexist with differing
    values, so neither case is reachable in practice, but changing them would
    change which rows a report includes.
    """
    values = [
        normalized_int(raw_row.get(key))
        for key in (metric_key, *_RAW_FLOW_METRIC_FALLBACK_KEYS)
    ]
    for value in values:
        if value:
            return value
    return 0 if 0 in values else None


def flow_row_remote_host(raw_row: Mapping[str, object]) -> str | None:
    """Return the remote hostname or domain from one flow row.

    ``host`` and ``domain`` describe the same destination on different row
    families, so they are read as one field rather than two.
    """
    for key in _RAW_FLOW_HOSTNAME_KEYS:
        remote = normalized_string(raw_row.get(key))
        if remote is not None:
            return remote
    return None


def flow_row_remote_ip(raw_row: Mapping[str, object]) -> str | None:
    """Return the remote address from one flow row when it is resolved."""
    return normalized_string(raw_row.get(_RAW_FLOW_IP_KEY))


def iter_flow_rows(payload: object) -> tuple[Mapping[str, object], ...]:
    """Return the flow rows in one ranking payload.

    Accepts a bare list, or a mapping wrapping the list under ``flows``,
    ``download``, ``upload``, ``items``, or ``results``. Non-mapping entries are
    dropped rather than raising: these are optional protocol fields and a shape
    change should degrade to "nothing to report", not fail a refresh.
    """
    candidates: object = payload
    if isinstance(payload, Mapping):
        for key in _RAW_FLOW_LIST_CONTAINER_KEYS:
            nested = payload.get(key)
            if isinstance(nested, list):
                candidates = nested
                break

    if not isinstance(candidates, list):
        return ()

    return tuple(item for item in candidates if isinstance(item, Mapping))


def host_traffic_sort_key(
    *,
    download_bytes: int | None,
    upload_bytes: int | None,
    host_name: str | None,
    host_id: str,
) -> tuple[int, str, str]:
    """Return the ordering for per-host *traffic* rows.

    Total bytes descending, then name, then id. The name and id tie-breaks are
    not decoration: two hosts can carry the same total, and without a stable
    order the "top talkers" list would reorder itself between refreshes.

    Three related keys exist and their primary keys genuinely differ, so they are
    deliberately not merged:

    - this one, for a combined total across both directions
    - :func:`metric_ranking_sort_key`, for a single direction, used to build the
      separate top-download and top-upload lists. Ranking those by combined
      total would be wrong.
    - the bucket ordering in the usage-bucket builder, which adds a session-count
      tie-break because buckets carry one and hosts do not.

    All of them share the same name and id tie-breaks *and the same casefold
    rule*, so a list of destinations orders the same way whether it is ranked by
    one metric or two.
    """
    return (
        -((download_bytes or 0) + (upload_bytes or 0)),
        host_name.casefold() if host_name else "",
        host_id,
    )


def metric_ranking_sort_key(
    *,
    value: int,
    host_name: str | None,
    host_id: str,
) -> tuple[int, str, str]:
    """Return the ordering for a ranking built on one metric.

    Same tie-breaks as :func:`host_traffic_sort_key`, including the casefold on
    the name. Without the casefold a destination list ordered by codepoint can
    place ``"Zebra"`` ahead of ``"apple"``, so the two top-destination lists
    would order the same equal-valued pair differently.
    """
    return (-value, (host_name or "").casefold(), host_id)


def build_flow_record(raw_row: Mapping[str, object]) -> FirewallaFlowRecord:
    """Build one normalized flow record from a raw wire row.

    The flow log, the block log and a rule's ``lastHitFlow`` are the same shape,
    so they are read here rather than each keeping its own subset. Measured: all
    32 fields a live flow-log record carried appear in ``lastHitFlow`` too.

    The destination arrives under ``host`` for a resolved connection, ``domain``
    for a DNS match, ``ip`` when neither resolved, and ``dstMac`` for a peer
    inside the LAN (which has no hostname to resolve to). They collapse into one
    destination plus its kind so a caller does not have to know which family
    produced the row.

    Nothing is defaulted to a measurement. A blocked record has no bytes, so the
    byte fields stay ``None`` -- ``0`` would read as a measured empty transfer
    rather than as an intercepted one.
    """
    return FirewallaFlowRecord(
        timestamp=normalized_float(raw_row.get(_RAW_RECORD_TS_KEY)),
        ltype=normalized_string(raw_row.get(_RAW_RECORD_LTYPE_KEY)),
        device_id=flow_row_host_id(raw_row),
        device_ip=normalized_string(raw_row.get(_RAW_RECORD_DEVICE_IP_KEY)),
        destination=_flow_record_destination(raw_row)[0],
        destination_kind=_flow_record_destination(raw_row)[1],
        destination_ip=normalized_string(raw_row.get(_RAW_FLOW_IP_KEY)),
        destination_mac=normalized_string(raw_row.get(_RAW_RECORD_DSTMAC_KEY)),
        port=normalized_int(raw_row.get(_RAW_RECORD_PORT_KEY)),
        device_port=normalized_int(raw_row.get(_RAW_RECORD_DEVICE_PORT_KEY)),
        protocol=normalized_string(raw_row.get(_RAW_RECORD_PROTOCOL_KEY)),
        blocked_by_rule_id=normalized_int(raw_row.get(_RAW_RECORD_PID_KEY)),
        block_type=normalized_string(raw_row.get(_RAW_RECORD_TYPE_KEY)),
        download_bytes=normalized_int(raw_row.get(_RAW_RECORD_DOWNLOAD_KEY)),
        upload_bytes=normalized_int(raw_row.get(_RAW_RECORD_UPLOAD_KEY)),
        duration_seconds=normalized_float(raw_row.get(_RAW_RECORD_DURATION_KEY)),
        event_count=normalized_int(raw_row.get(_RAW_RECORD_COUNT_KEY)),
        network_id=normalized_string(raw_row.get(_RAW_RECORD_INTF_KEY)),
        remote_network_id=(
            normalized_string(raw_row.get(_RAW_RECORD_OINTF_KEY))
            or normalized_string(raw_row.get(_RAW_RECORD_DINTF_KEY))
            or normalized_string(raw_row.get(_RAW_RECORD_WANINTF_KEY))
        ),
        apid=normalized_int(raw_row.get(_RAW_RECORD_APID_KEY)),
        category=normalized_string(raw_row.get(_RAW_RECORD_CATEGORY_KEY)),
        app=normalized_string(raw_row.get(_RAW_RECORD_APP_KEY)),
        region=normalized_string(raw_row.get(_RAW_RECORD_COUNTRY_KEY)),
        tags=flow_record_tags(raw_row, _RAW_RECORD_TAGS_KEY),
        user_tags=flow_record_tags(raw_row, _RAW_RECORD_USER_TAGS_KEY),
        membership_tags=flow_record_tags(raw_row, _RAW_RECORD_DTAGS_KEY),
        destination_tags=flow_record_tags(raw_row, _RAW_RECORD_DST_TAGS_KEY),
        flow_tags=flow_record_tags(raw_row, _RAW_RECORD_FLOW_TAGS_KEY),
    )


def flow_record_tags(
    raw_row: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    """Return one tag list from a record, dropping anything that is not a tag.

    Tag fields are absent on most records, so an empty tuple means "the box did
    not say" rather than "no tags".
    """
    raw_tags = raw_row.get(key)
    if not isinstance(raw_tags, list):
        return ()
    return tuple(
        tag for tag in (normalized_string(item) for item in raw_tags) if tag is not None
    )


def flow_family_unit(family: str) -> str | None:
    """Return the unit one rollup family's ``count`` is expressed in.

    ``count`` is overloaded across families and Firewalla documents the overload,
    so this is a lookup rather than a guess. ``None`` for an unrecognised family
    is deliberate: treating an unknown family as bytes would be the exact
    misreading this exists to prevent.
    """
    return _FLOW_UNIT_BY_FAMILY.get(family)


def flow_family_direction(family: str) -> str | None:
    """Return the direction of one rollup family, from its name.

    ``fd`` is **not** used, and must not be: it reads ``"in"`` on both byte
    families and on every regular record measured, so it cannot be a direction.

    Only a name that actually carries a direction is answered. ``download`` /
    ``upload`` and an ``:in`` / ``:out`` suffix do; **``dnsB`` does not**, and
    returns ``None`` rather than being inferred as inbound. A DNS block is a
    query the device made being refused, so neither reading is obviously right,
    and inventing one would be a guess presented as a measurement.

    A ``local:`` family is ``local`` even when it also carries an ``:in`` /
    ``:out`` suffix: that suffix describes the interface side, while the traffic
    itself never left the network.
    """
    if family.startswith(f"{_LOCAL_FAMILY_SEGMENT}:"):
        return FLOW_DIRECTION_LOCAL
    if family == "download" or family.endswith(":in"):
        return FLOW_DIRECTION_INBOUND
    if family == "upload" or family.endswith(":out"):
        return FLOW_DIRECTION_OUTBOUND
    return None


def _flow_record_destination(
    raw_row: Mapping[str, object],
) -> tuple[str | None, str | None]:
    """Return the record's destination and the kind of name it is.

    ``host`` and ``domain`` describe the same thing at different resolutions and
    ``ip`` is the fallback, so the pair is resolved together. A ``local:`` peer
    carries only its MAC, which is a third kind rather than a missing name.
    """
    host = normalized_string(raw_row.get(_RAW_FLOW_HOSTNAME_KEYS[0]))
    if host is not None:
        return host, "host"
    domain = normalized_string(raw_row.get(_RAW_FLOW_HOSTNAME_KEYS[1]))
    if domain is not None:
        return domain, "domain"
    ip_address = normalized_string(raw_row.get(_RAW_FLOW_IP_KEY))
    if ip_address is not None:
        return ip_address, "ip"
    peer_mac = normalized_string(raw_row.get(_RAW_RECORD_DSTMAC_KEY))
    if peer_mac is not None:
        return peer_mac, "mac"
    return None, None


def extract_usage_window(
    raw_window: object,
) -> FirewallaNetworkUsageWindow | None:
    """Extract download/upload totals from one raw usage window.

    Both the per-network ``item=intf`` payload and the per-target flow rollup
    carry these windows under the same keys (``newLast24``, ``last60``,
    ``last30``, ``last12Months``), so one parser serves both. Returning ``None``
    when neither total is present lets a caller distinguish an absent window from
    a window that is genuinely all zero.
    """
    if not isinstance(raw_window, Mapping):
        return None
    download = normalized_int(raw_window.get(_RAW_USAGE_DOWNLOAD_KEY))
    upload = normalized_int(raw_window.get(_RAW_USAGE_UPLOAD_KEY))
    if download is None and upload is None:
        return None
    return FirewallaNetworkUsageWindow(
        download_bytes=download,
        upload_bytes=upload,
    )


@dataclass(slots=True)
class FlowHostActivity:
    """Mutable per-host accumulator for one flow aggregation pass.


    Mutable deliberately. The same host is described by three different
    families -- ``appDetails`` for bytes, ``recent`` for connection counts, and
    the ``download`` / ``upload`` rankings for peak bytes -- so the host has to
    be accumulated across all three and shaped once, rather than rebuilt into a
    frozen record on every row and then rebuilt again at the end.
    """

    host_name: str | None = None
    ip_address: str | None = None
    conn: int = 0
    download_bytes: int = 0
    upload_bytes: int = 0
