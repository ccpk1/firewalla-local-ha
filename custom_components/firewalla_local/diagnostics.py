"""Diagnostics support for Firewalla Local."""

from __future__ import annotations

from dataclasses import asdict
from typing import Final

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
)
from .coordinator import FirewallaConfigEntry

TO_REDACT: Final = {
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
}


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant, entry: FirewallaConfigEntry
) -> dict[str, object]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(getattr(entry, "options", {})),
        "runtime_snapshot": (
            asdict(coordinator.data) if coordinator.data is not None else None
        ),
        "runtime_init_payload": (
            async_redact_data(coordinator.last_init_payload, TO_REDACT)
            if coordinator.last_init_payload is not None
            else None
        ),
    }
