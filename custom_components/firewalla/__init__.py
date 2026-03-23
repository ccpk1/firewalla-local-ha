"""The Firewalla integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FirewallaApiClient
from .coordinator import (
    FirewallaConfigEntry,
    FirewallaDataUpdateCoordinator,
    FirewallaRuntimeData,
)

PLATFORMS: list[Platform] = []


async def async_setup_entry(hass: HomeAssistant, entry: FirewallaConfigEntry) -> bool:
    """Set up Firewalla from a config entry."""
    client = FirewallaApiClient(
        session=async_get_clientsession(hass),
        host=entry.data[CONF_HOST],
    )
    coordinator = FirewallaDataUpdateCoordinator(hass, entry, client)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = FirewallaRuntimeData(client=client, coordinator=coordinator)

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: FirewallaConfigEntry) -> bool:
    """Unload a Firewalla config entry."""
    if not PLATFORMS:
        return True

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
