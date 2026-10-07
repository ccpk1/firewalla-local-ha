"""Pure host activity evaluation for Firewalla Local.

The online/offline definition has to stay identical everywhere it is reported:
the watched-device entities, the system-status device counts, and the runtime
inventory summary. Keeping it here means there is one definition rather than
three that can drift apart.

"Online" is deliberately relative, not wall-clock based. The freshest host in
the inventory sets the reference point, and other hosts count as online when
they were active within the configured window of it. A box where nothing has
been active recently therefore reports no online hosts rather than treating
stale timestamps as current.

The window is a parameter, but there is only one *connectivity* window shared by
every surface that reports whether a device is online: the watched-device
sensors, the device counts, the VPN peer counts, the runtime inventory summary,
and the host list's ``online`` field. They previously diverged, so the same
device could be online for one surface and offline for another; that is why
there is one window and not three.

"Online" here means *connected*, which is a different question from *home*:

- **Connectivity** — is it connected? Answered by
  `DEFAULT_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES` (5 minutes): a device quiet for
  longer than that is disconnected, not merely idle.
- **Presence** — is it home? Answered separately by the device tracker, which
  has its own longer, wall-clock away window, because a device can be connected
  while nobody is home.

This difference is worth stating because it is the opposite of a rounding
detail: classifying on last-activity age can disagree with the Firewalla app,
which also sees the box's live association state. A device quiet for between
5 and 15 minutes reads disconnected here while the app may still show it
connected. The 5-minute tolerance is the intended behaviour for our surfaces.

The box's own ``stale`` flag is a third signal and answers neither question the
same way: it means "not seen in roughly 7 days", so it is not used for
connectivity.

VPN peers are identified here too, for the same reason: the counted population
has to be one definition shared by the system-status attributes and the summary
report.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..const import VPN_PEER_MAC_PREFIXES
from ..models import FirewallaHostRuntime


def is_vpn_peer(host: FirewallaHostRuntime) -> bool:
    """Return whether one host is a VPN peer rather than a LAN device.

    Peers are synthesized from the box's ``wgPeers``/``awgPeers`` inventories
    and carry a ``<prefix>:<uid>`` id instead of a MAC, so they are not LAN
    devices and cannot be targeted by MAC-based tools.
    """
    return host.mac.partition(":")[0] in VPN_PEER_MAC_PREFIXES


def reference_last_active(hosts: Sequence[FirewallaHostRuntime]) -> float | None:
    """Return the most recent activity timestamp across the host inventory."""
    return max(
        (host.last_active for host in hosts if host.last_active is not None),
        default=None,
    )


def is_host_online(
    host: FirewallaHostRuntime,
    *,
    reference_activity: float | None,
    online_window_seconds: int,
) -> bool | None:
    """Return whether one host counts as online for the given reference point."""
    if reference_activity is None:
        # No timestamps anywhere: fall back to the box's own stale flag when set.
        return None if host.stale is None else not host.stale

    if host.stale is True or host.last_active is None:
        return False

    return reference_activity - host.last_active <= online_window_seconds


def count_online_hosts(
    hosts: Sequence[FirewallaHostRuntime],
    *,
    reference_activity: float | None,
    online_window_seconds: int,
) -> int:
    """Return how many of ``hosts`` count as online against one reference point.

    ``reference_activity`` is required rather than derived from ``hosts``. It used
    to be computed here as ``max(last_active)`` over whatever sequence was passed,
    which made the reference a property of the *subset* being counted instead of a
    property of the appliance. Every caller that counted a subset therefore got a
    different baseline: the VPN peer count used the freshest *peer*, so the newest
    peer was always "online" by construction -- on the dev box that reported one
    online peer whose last activity was 4.5 days earlier, while the host list,
    using the appliance-wide reference, correctly showed it offline.

    One window was not enough, because the window is only half the answer; the
    reference is the other half. Making it a parameter means a caller has to state
    which instant it is measuring from, so a subset can no longer silently become
    its own clock.
    """
    return sum(
        1
        for host in hosts
        if is_host_online(
            host,
            reference_activity=reference_activity,
            online_window_seconds=online_window_seconds,
        )
        is True
    )
