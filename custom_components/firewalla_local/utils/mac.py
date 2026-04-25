"""MAC address helpers for Firewalla Local."""

from __future__ import annotations


def normalize_mac_address(mac: str | None) -> str | None:
    """Return one uppercase MAC string when one is present."""
    if mac is None:
        return None

    normalized_mac = mac.strip().upper()
    return normalized_mac or None
