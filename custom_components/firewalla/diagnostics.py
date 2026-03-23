"""Diagnostics support for Firewalla."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import FirewallaConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FirewallaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry_data": dict(entry.data),
        "system_info": (
            asdict(entry.runtime_data.coordinator.data)
            if entry.runtime_data.coordinator.data is not None
            else None
        ),
    }
