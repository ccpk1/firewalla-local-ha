"""DataUpdateCoordinator for Firewalla Local."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FirewallaApiClient, FirewallaApiError
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, LOGGER
from .models import FirewallaSystemInfo


class FirewallaDataUpdateCoordinator(DataUpdateCoordinator[FirewallaSystemInfo]):
    """Coordinate Firewalla Local data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: FirewallaConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            config_entry=config_entry,
        )

    async def _async_update_data(self) -> FirewallaSystemInfo:
        """Fetch data from Firewalla Local."""
        try:
            return await self.client.async_get_system_info()
        except FirewallaApiError as err:
            raise UpdateFailed(f"Unable to fetch Firewalla Local data: {err}") from err


@dataclass(slots=True)
class FirewallaRuntimeData:
    """Runtime data stored on the config entry."""

    client: FirewallaApiClient
    coordinator: FirewallaDataUpdateCoordinator


type FirewallaConfigEntry = ConfigEntry[FirewallaRuntimeData]
