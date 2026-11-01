"""Device-registry helpers that work across supported Home Assistant versions."""

from __future__ import annotations

import inspect
from typing import Any, Final

from homeassistant.helpers import device_registry as dr

# Core 2026.8 replaced `via_device` — a device identifier tuple — with
# `via_device_id`, and deprecates the old name until 2027.8. The parameter name
# and the value it expects differ, so the running Core decides both.
_VIA_DEVICE_TAKES_ID: Final = (
    "via_device_id"
    in inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters
)


def via_device_kwargs(device_id: str, identifier: tuple[str, str]) -> dict[str, Any]:
    """Return the keyword that links a child device to its parent.

    ``device_id`` is the parent's registry id and ``identifier`` its
    ``(domain, value)`` pair; callers pass both because only one is used.
    """
    if _VIA_DEVICE_TAKES_ID:
        return {"via_device_id": device_id}
    return {"via_device": identifier}


def async_get_entry_device(
    registry: dr.DeviceRegistry,
    identifier: tuple[str, str],
    config_entry_id: str,
) -> dr.DeviceEntry | None:
    """Return the device with ``identifier`` that belongs to one config entry.

    Core 2026.8 added :meth:`async_get_device_by_identifier` and deprecated the
    unfiltered :meth:`async_get_device` that older Core requires, so neither name
    covers the supported range. Feature detection picks whichever is there.
    """
    if hasattr(registry, "async_get_device_by_identifier"):
        return registry.async_get_device_by_identifier(identifier, config_entry_id)
    return registry.async_get_device(identifiers={identifier})
