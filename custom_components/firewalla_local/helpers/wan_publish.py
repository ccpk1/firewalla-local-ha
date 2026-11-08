"""Publish-layer shaping for WAN routing and health.

Both the entities and the report services surface the same routing state, and
they must agree on its vocabulary: a `mode`, a per-WAN `role`, and the
mode-specific settings. Keeping the shaping here means the attribute on the
System Status entity and the `routing` object in `get_system_overview` cannot
drift into two slightly different shapes.

Interface names are translated to WAN labels by the caller, because only the
caller can ask the manager which label belongs to an interface, and a service
response and an attribute should use the same label either way.
"""

from __future__ import annotations

from collections.abc import Callable

from ..models import FirewallaWanRouting
from ..utils.values import iso_instant

# Placeholder-free: a label is the caller's answer, so this module never guesses.
InterfaceLabel = Callable[[str], str]


def serialize_wan_routing(
    routing: FirewallaWanRouting | None,
    *,
    label_for_interface: InterfaceLabel,
) -> dict[str, object] | None:
    """Return the multi-WAN mode and its settings, or ``None`` when unstated.

    Only the fields the stated mode uses are published: failover names a primary
    and a standby with a fallback toggle, load balance carries a traffic share and
    names no primary, and a mode with nothing to configure carries its name alone.
    A reader therefore sees exactly what the box configured, and the absence of a
    key is the answer "this mode has no such setting".
    """
    if routing is None:
        return None

    payload: dict[str, object] = {"mode": routing.mode}
    if routing.primary is not None:
        payload["primary"] = label_for_interface(routing.primary)
    if routing.standby is not None:
        payload["standby"] = label_for_interface(routing.standby)
    if routing.failback is not None:
        payload["failback"] = routing.failback
    if routing.traffic_share_percent is not None:
        payload["traffic_share_percent"] = {
            label_for_interface(interface_name): percent
            for interface_name, percent in routing.traffic_share_percent.items()
        }
    return payload


def serialize_wan_health(health: dict[str, object] | None) -> dict[str, object] | None:
    """Return one WAN's health test result in publish form.

    Timestamps are published twice, as an instant and as a raw epoch, matching the
    rest of the integration: automations compare the number, humans read the
    instant.
    """
    if health is None:
        return None

    tested_at = health.get("tested_at_timestamp")
    recent_down_at = health.get("recent_down_at_timestamp")
    raw_failures = health.get("failures")
    return {
        "tested_at": iso_instant(tested_at),
        "tested_at_timestamp": tested_at,
        "carrier": health.get("carrier"),
        "dns": health.get("dns"),
        "ping": health.get("ping"),
        "http_status": health.get("http_status"),
        "failures": list(raw_failures) if isinstance(raw_failures, tuple) else [],
        "recent_down_at": iso_instant(recent_down_at),
        "recent_down_at_timestamp": recent_down_at,
    }
