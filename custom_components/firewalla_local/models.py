"""Typed models for Firewalla Local."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FirewallaSystemInfo:
    """Basic system information for a Firewalla appliance."""

    host: str
    name: str
    model: str | None
    serial_number: str | None
    software_version: str | None
