"""DataUpdateCoordinator for Firewalla Local."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import FirewallaApiClient, FirewallaApiError, FirewallaAuthError
from .const import (
    CONF_DEVICE_TRACKERS,
    CONF_ENABLE_NETWORK_ENTITIES,
    CONF_HOST,
    CONF_LICENSE,
    CONF_LOCAL_IP,
    CONF_SELECTED_RULE_IDS,
    CONF_UPDATE_INTERVAL,
    CONF_WATCHED_DEVICES,
    CONF_WATCHED_USERS,
    DEFAULT_ENABLE_NETWORK_ENTITIES,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    LOGGER,
    MAX_UPDATE_INTERVAL_MINUTES,
    MIN_UPDATE_INTERVAL_MINUTES,
)
from .models import FirewallaRuntimeSnapshot

_PENDING_PAIRING_INIT_PAYLOADS: str = "pending_pairing_init_payloads"

if TYPE_CHECKING:
    from .managers import (
        FirewallaHostManager,
        FirewallaIntegrationManager,
        FirewallaRuleManager,
        FirewallaUserManager,
        FirewallaWirelessManager,
    )


def _get_selected_rule_ids(options: Mapping[str, object]) -> tuple[str, ...]:
    """Return the stored selected rule IDs in a stable order."""
    raw_selected_rule_ids = options.get(CONF_SELECTED_RULE_IDS, [])
    if not isinstance(raw_selected_rule_ids, list):
        return ()

    return tuple(
        sorted(rule_id for rule_id in raw_selected_rule_ids if isinstance(rule_id, str))
    )


def _get_watched_device_macs(options: Mapping[str, object]) -> tuple[str, ...]:
    """Return the stored watched-device MACs in a stable order."""
    raw_watched_devices = options.get(CONF_WATCHED_DEVICES, [])
    if not isinstance(raw_watched_devices, list):
        return ()

    return tuple(
        sorted(mac for mac in raw_watched_devices if isinstance(mac, str) and mac)
    )


def _get_watched_user_ids(options: Mapping[str, object]) -> tuple[str, ...]:
    """Return the stored watched-user identifiers in a stable order."""
    raw_watched_users = options.get(CONF_WATCHED_USERS, [])
    if not isinstance(raw_watched_users, list):
        return ()

    return tuple(
        sorted(
            user_id
            for user_id in raw_watched_users
            if isinstance(user_id, str) and user_id
        )
    )


def _get_device_tracker_macs(options: Mapping[str, object]) -> tuple[str, ...]:
    """Return the stored device-tracker MACs in a stable order."""
    raw_device_trackers = options.get(CONF_DEVICE_TRACKERS, [])
    if not isinstance(raw_device_trackers, list):
        return ()

    return tuple(
        sorted(mac for mac in raw_device_trackers if isinstance(mac, str) and mac)
    )


def get_enabled_network_entities(options: Mapping[str, object]) -> bool:
    """Return whether per-network status entities should be created."""
    raw_value = options.get(
        CONF_ENABLE_NETWORK_ENTITIES, DEFAULT_ENABLE_NETWORK_ENTITIES
    )
    return raw_value if isinstance(raw_value, bool) else DEFAULT_ENABLE_NETWORK_ENTITIES


def get_configured_update_interval(options: Mapping[str, object]) -> timedelta:
    """Return the validated polling interval configured in entry options."""
    raw_update_interval = options.get(
        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MINUTES
    )
    if isinstance(raw_update_interval, bool) or not isinstance(
        raw_update_interval, int
    ):
        return DEFAULT_UPDATE_INTERVAL

    if not (
        MIN_UPDATE_INTERVAL_MINUTES
        <= raw_update_interval
        <= MAX_UPDATE_INTERVAL_MINUTES
    ):
        return DEFAULT_UPDATE_INTERVAL

    return timedelta(minutes=raw_update_interval)


@callback
def cache_pending_pairing_init_payload(
    hass: HomeAssistant, license_id: str, payload: dict[str, object]
) -> None:
    """Store one validated pairing payload for the next entry setup refresh."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    pending_payloads = domain_data.setdefault(_PENDING_PAIRING_INIT_PAYLOADS, {})
    if not isinstance(pending_payloads, dict):
        domain_data[_PENDING_PAIRING_INIT_PAYLOADS] = {license_id: dict(payload)}
        return

    pending_payloads[license_id] = dict(payload)


@callback
def pop_pending_pairing_init_payload(
    hass: HomeAssistant, license_id: str
) -> dict[str, object] | None:
    """Return and clear one cached pairing payload for entry setup."""
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, dict):
        return None

    pending_payloads = domain_data.get(_PENDING_PAIRING_INIT_PAYLOADS)
    if not isinstance(pending_payloads, dict):
        return None

    payload = pending_payloads.pop(license_id, None)
    if not pending_payloads:
        domain_data.pop(_PENDING_PAIRING_INIT_PAYLOADS, None)

    return payload if isinstance(payload, dict) else None


@callback
def async_update_entry_options(
    hass: HomeAssistant,
    entry: FirewallaConfigEntry | ConfigEntry,
    options: Mapping[str, object],
) -> None:
    """Persist config-entry options through the coordinator-owned boundary."""
    hass.config_entries.async_update_entry(entry, options=options)


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
        self._license = config_entry.data[CONF_LICENSE]
        self.last_init_payload: dict[str, object] | None = None
        self.last_runtime_data_updated_at: datetime | None = None
        self.host_manager: FirewallaHostManager | None = None
        self.integration_manager: FirewallaIntegrationManager | None = None
        self.rule_manager: FirewallaRuleManager | None = None
        self.user_manager: FirewallaUserManager | None = None
        self.wireless_manager: FirewallaWirelessManager | None = None
        self._enable_network_entities = get_enabled_network_entities(
            config_entry.options
        )
        self._unavailable_logged = False
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=get_configured_update_interval(config_entry.options),
            config_entry=config_entry,
        )

    def attach_managers(
        self,
        *,
        host_manager: FirewallaHostManager,
        integration_manager: FirewallaIntegrationManager,
        rule_manager: FirewallaRuleManager,
        user_manager: FirewallaUserManager,
        wireless_manager: FirewallaWirelessManager,
    ) -> None:
        """Attach the entry-scoped manager objects to refresh routing."""
        self.host_manager = host_manager
        self.integration_manager = integration_manager
        self.rule_manager = rule_manager
        self.user_manager = user_manager
        self.wireless_manager = wireless_manager

    async def _async_update_data(self) -> FirewallaRuntimeSnapshot:
        """Fetch data from Firewalla Local."""
        try:
            payload = pop_pending_pairing_init_payload(self.hass, self._license)
            if payload is None:
                payload = await self.client.async_get_runtime_init_payload()
            self.last_init_payload = payload
            snapshot = self.client.build_runtime_snapshot(payload)

            if not snapshot.hosts:
                # The box always reports itself in the host inventory, so an
                # empty host list means a degraded payload rather than a valid
                # empty box. Treat it as a failed refresh so managers are not
                # routed an empty index that would drop every configured host.
                raise UpdateFailed("Firewalla Local returned an empty host inventory")
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

        if self.integration_manager is not None:
            self.integration_manager.handle_refresh(snapshot)
            await self.integration_manager.async_refresh_network_usage()
        if self.host_manager is not None:
            self.host_manager.handle_refresh(snapshot)
        if self.user_manager is not None:
            self.user_manager.handle_refresh(snapshot)
        if self.rule_manager is not None:
            self.rule_manager.handle_refresh(self.last_init_payload or {}, snapshot)
        if self.wireless_manager is not None:
            self.wireless_manager.handle_refresh(self.last_init_payload or {})

        self.last_runtime_data_updated_at = dt_util.utcnow()

        return snapshot

    async def async_handle_entry_reload_requested(
        self, hass: HomeAssistant, entry: FirewallaConfigEntry
    ) -> None:
        """Reload a config entry after mutable updates such as options changes."""
        self.async_update_interval_from_entry(entry)

        current_selected_rule_ids = tuple(
            sorted(
                template.source_rule_id
                for template in entry.runtime_data.rule_manager.selected_templates
            )
        )
        current_watched_device_macs = (
            entry.runtime_data.host_manager.configured_watched_device_macs
        )
        current_device_tracker_macs = (
            entry.runtime_data.host_manager.configured_device_tracker_macs
        )
        current_watched_user_ids = (
            entry.runtime_data.user_manager.configured_watched_user_ids
        )
        current_enable_network_entities = self._enable_network_entities
        enable_network_entities = get_enabled_network_entities(entry.options)
        if (
            current_selected_rule_ids == _get_selected_rule_ids(entry.options)
            and current_watched_device_macs == _get_watched_device_macs(entry.options)
            and current_device_tracker_macs == _get_device_tracker_macs(entry.options)
            and current_watched_user_ids == _get_watched_user_ids(entry.options)
            and current_enable_network_entities == enable_network_entities
        ):
            self.async_update_listeners()
            return

        self._enable_network_entities = enable_network_entities
        await hass.config_entries.async_reload(entry.entry_id)

    @callback
    def async_update_interval_from_entry(self, entry: FirewallaConfigEntry) -> None:
        """Apply the configured polling interval from the latest entry options."""
        self.update_interval = get_configured_update_interval(entry.options)


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
    host_manager: FirewallaHostManager
    integration_manager: FirewallaIntegrationManager
    rule_manager: FirewallaRuleManager
    user_manager: FirewallaUserManager
    wireless_manager: FirewallaWirelessManager


type FirewallaConfigEntry = ConfigEntry[FirewallaRuntimeData]
