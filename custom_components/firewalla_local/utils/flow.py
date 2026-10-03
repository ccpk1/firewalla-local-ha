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

from ..models import FirewallaNetworkUsageWindow
from .values import normalized_int, normalized_string

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
