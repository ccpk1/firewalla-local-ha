"""Shared serialization for usage reports.

The per-network usage summary is projected to JSON by two surfaces: the network
entity's ``network_usage`` attribute and the ``get_network_segment_*`` service
responses. Both had their own window and summary serializer producing an
identical shape, including the same five window keys, so a change to one would
have left the other describing the same data differently.

This module is the single projection. It lives in ``helpers/`` because it is
read-only report rendering over manager-owned data, which is exactly what the
architecture assigns to helper modules rather than to a surface or a manager.
"""

from __future__ import annotations

from homeassistant.util.json import JsonObjectType

from ..models import FirewallaNetworkUsageSummary, FirewallaNetworkUsageWindow


def serialize_usage_window(
    window: FirewallaNetworkUsageWindow | None,
) -> JsonObjectType:
    """Serialize one usage window into download/upload byte keys.

    Returns both keys as ``None`` when the window is absent, rather than an
    empty object, so a consumer can distinguish "no data reported" from "the
    field was not serialized".
    """
    return {
        "download_bytes": window.download_bytes if window is not None else None,
        "upload_bytes": window.upload_bytes if window is not None else None,
    }


def serialize_usage_summary(
    usage: FirewallaNetworkUsageSummary | None,
) -> JsonObjectType:
    """Serialize one usage summary across all of its named windows.

    ``monthly`` is the current calendar-month total from the WAN monthly source
    and is not the same measurement as the rolling ``last_30d`` window; both are
    reported so a consumer is not left to infer which one it has.
    """
    return {
        "last_24h": serialize_usage_window(
            usage.last_24h if usage is not None else None
        ),
        "last_60m": serialize_usage_window(
            usage.last_60m if usage is not None else None
        ),
        "last_30d": serialize_usage_window(
            usage.last_30d if usage is not None else None
        ),
        "last_12m": serialize_usage_window(
            usage.last_12m if usage is not None else None
        ),
        "monthly": serialize_usage_window(usage.monthly if usage is not None else None),
    }
