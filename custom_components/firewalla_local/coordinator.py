"""DataUpdateCoordinator for Firewalla Local."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FirewallaApiClient, FirewallaApiError, FirewallaAuthError
from .const import (
    CONF_HOST,
    CONF_LOCAL_IP,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
)
from .models import FirewallaRuntimeSnapshot

if TYPE_CHECKING:
    from .managers import FirewallaRuleManager, FirewallaSystemManager


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
        self.last_init_payload: dict[str, object] | None = None
        self.system_manager: FirewallaSystemManager | None = None
        self.rule_manager: FirewallaRuleManager | None = None
        self._unavailable_logged = False
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            config_entry=config_entry,
        )

    def attach_managers(
        self,
        *,
        system_manager: FirewallaSystemManager,
        rule_manager: FirewallaRuleManager,
    ) -> None:
        """Attach the entry-scoped manager objects to refresh routing."""
        self.system_manager = system_manager
        self.rule_manager = rule_manager

    async def _async_update_data(self) -> FirewallaRuntimeSnapshot:
        """Fetch data from Firewalla Local."""
        try:
            payload = await self.client.async_get_runtime_init_payload()
            self.last_init_payload = payload
            snapshot = self.client.build_runtime_snapshot(payload)
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

        if self.rule_manager is not None:
            self.rule_manager.handle_refresh(self.last_init_payload or {}, snapshot)

        return snapshot

    async def async_handle_entry_reload_requested(
        self, hass: HomeAssistant, entry: FirewallaConfigEntry
    ) -> None:
        """Reload a config entry after mutable updates such as options changes."""
        await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry_host(
    hass: HomeAssistant, entry: FirewallaConfigEntry
) -> FirewallaConfigEntry:
    """Normalize alternate local_ip connection data into host."""
    if CONF_HOST in entry.data or CONF_LOCAL_IP not in entry.data:
        return entry

    updated_data = dict(entry.data)
    updated_data[CONF_HOST] = updated_data.pop(CONF_LOCAL_IP)
    hass.config_entries.async_update_entry(entry, data=updated_data)
    return entry


@dataclass(slots=True)
class FirewallaRuntimeData:
    """Runtime data stored on the config entry."""

    client: FirewallaApiClient
    coordinator: FirewallaDataUpdateCoordinator
    system_manager: FirewallaSystemManager
    rule_manager: FirewallaRuleManager


type FirewallaConfigEntry = ConfigEntry[FirewallaRuntimeData]
