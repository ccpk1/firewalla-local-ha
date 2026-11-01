"""Diagnostics support for Firewalla Local."""

from __future__ import annotations

from dataclasses import asdict
from typing import Final

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AID,
    CONF_DEVICE_TRACKERS,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
    CONF_WATCHED_DEVICES,
    CONF_WATCHED_USERS,
)
from .coordinator import FirewallaConfigEntry
from .helpers.init_payload_redaction import redact_runtime_init_payload
from .helpers.snapshot_redaction import redact_runtime_snapshot

TO_REDACT: Final = {
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
}

# Options hold selections rather than credentials, but two of them are lists of
# MAC addresses and user ids, which name the household's devices and people.
TO_REDACT_OPTIONS: Final = TO_REDACT | {
    CONF_DEVICE_TRACKERS,
    CONF_WATCHED_DEVICES,
    CONF_WATCHED_USERS,
}


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant, entry: FirewallaConfigEntry
) -> dict[str, object]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": async_redact_data(dict(entry.options), TO_REDACT_OPTIONS),
        # The normalized snapshot names the household's people and devices, so it
        # is redacted by shape rather than dropped: the counts and the box's own
        # object ids are what make a report diagnosable.
        "runtime_snapshot": (
            redact_runtime_snapshot(asdict(coordinator.data))
            if coordinator.data is not None
            else None
        ),
        "runtime_init_payload": (
            redact_runtime_init_payload(coordinator.last_init_payload)
            if coordinator.last_init_payload is not None
            else None
        ),
    }
