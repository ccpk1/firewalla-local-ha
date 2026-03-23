"""DataUpdateCoordinator for Firewalla Local."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FirewallaApiClient, FirewallaApiError, FirewallaAuthError
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, LOGGER
from .models import FirewallaRuntimeSnapshot


class FirewallaDataUpdateCoordinator(DataUpdateCoordinator[FirewallaRuntimeSnapshot]):
    """Coordinate Firewalla Local data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: FirewallaConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self._unavailable_logged = False
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            config_entry=config_entry,
        )

    async def _async_update_data(self) -> FirewallaRuntimeSnapshot:
        """Fetch data from Firewalla Local."""
        try:
            snapshot = await self.client.async_get_runtime_snapshot()
        except FirewallaAuthError as err:
            raise ConfigEntryAuthFailed(
                "Firewalla local credentials were rejected"
            ) from err
        except FirewallaApiError as err:
            if not self._unavailable_logged:
                LOGGER.info("The Firewalla box is unavailable: %s", err)
                self._unavailable_logged = True
            raise UpdateFailed(f"Unable to fetch Firewalla Local data: {err}") from err

        if self._unavailable_logged:
            LOGGER.info("The Firewalla box is back online")
            self._unavailable_logged = False

        return snapshot


@dataclass(slots=True)
class FirewallaRuntimeData:
    """Runtime data stored on the config entry."""

    client: FirewallaApiClient
    coordinator: FirewallaDataUpdateCoordinator


type FirewallaConfigEntry = ConfigEntry[FirewallaRuntimeData]
