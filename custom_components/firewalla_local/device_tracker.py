"""Device tracker platform for Firewalla Local router-backed presence."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.device_tracker import ScannerEntity  # type: ignore[attr-defined]
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_INTEGRATION,
    ATTR_WATCHED_DEVICE_CONNECTION_TYPE,
    ATTR_WATCHED_DEVICE_DEVICE_GROUP,
    ATTR_WATCHED_DEVICE_DNS_DOMAIN,
    ATTR_WATCHED_DEVICE_DNS_FQDN,
    ATTR_WATCHED_DEVICE_DNS_HOSTNAME,
    ATTR_WATCHED_DEVICE_HOST_DEVICE_TYPE,
    ATTR_WATCHED_DEVICE_HOST_NAME,
    ATTR_WATCHED_DEVICE_IP_ADDRESS,
    ATTR_WATCHED_DEVICE_LAST_ACTIVE,
    ATTR_WATCHED_DEVICE_NETWORK_NAME,
    DOMAIN,
    ENTITY_SUFFIX_DEVICE_TRACKER,
    TRANS_KEY_ENTITY_DEVICE_TRACKER_PRESENCE,
    TRANS_KEY_PURPOSE_DEVICE_TRACKER_PRESENCE,
)
from .coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator
from .managers import FirewallaHostManager
from .models import FirewallaHostRuntime

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: FirewallaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Firewalla Local device trackers from a config entry."""
    del _hass
    async_add_entities(
        FirewallaDeviceTracker(entry, mac)
        for mac in entry.runtime_data.host_manager.configured_device_tracker_macs
    )


class FirewallaDeviceTracker(
    CoordinatorEntity[FirewallaDataUpdateCoordinator],
    ScannerEntity,
):
    """Expose one selected Firewalla host as a router-backed device tracker."""

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = True
    _attr_translation_key = TRANS_KEY_ENTITY_DEVICE_TRACKER_PRESENCE

    def __init__(self, entry: FirewallaConfigEntry, mac: str) -> None:
        """Initialize one device tracker."""
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._mac = mac
        self._attr_mac_address = dr.format_mac(mac)
        self._attr_unique_id = (
            entry.runtime_data.integration_manager.build_entity_unique_id(
                object_id=mac,
                suffix=ENTITY_SUFFIX_DEVICE_TRACKER,
            )
        )

    @property
    def host_manager(self) -> FirewallaHostManager:
        """Return the entry-scoped host manager."""
        return self._entry.runtime_data.host_manager

    @property
    def unique_id(self) -> str:
        """Return the entry-scoped unique ID for this tracker."""
        return str(self._attr_unique_id)

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the entity category for this tracker."""
        return None

    def _build_state_attributes(self, purpose: str) -> dict[str, object]:
        """Return the common identifying state attributes for this tracker."""
        return {
            "purpose": purpose,
            ATTR_INTEGRATION: DOMAIN,
        }

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Device trackers are always enabled; device lifecycle is manager-owned."""
        return True

    def find_device_entry(self) -> dr.DeviceEntry | None:
        """Return the tracked-client device entry for this tracker."""
        return dr.async_get(self.hass).async_get_device_by_identifier(
            self._entry.runtime_data.integration_manager.build_tracked_client_device_identifier(
                self._mac
            ),
            self._entry.entry_id,
        )

    async def async_added_to_hass(self) -> None:
        """Attach the tracker to its client device."""
        await super().async_added_to_hass()

        if self.registry_entry is None:
            return

        entity_registry = er.async_get(self.hass)
        device_entry = self.find_device_entry()
        if (
            device_entry is not None
            and self.registry_entry.device_id != device_entry.id
        ):
            self.registry_entry = entity_registry.async_update_entity(
                self.entity_id,
                device_id=device_entry.id,
            )

    @property
    def _host(self) -> FirewallaHostRuntime | None:
        """Return the currently resolved device-tracker host."""
        return self.host_manager.get_host(self._mac)

    @property
    def available(self) -> bool:
        """Return whether the selected device-tracker host is present in runtime."""
        return super().available and self._host is not None

    @property
    def is_connected(self) -> bool:
        """Return whether the selected host is currently online."""
        host = self._host
        return bool(
            host is not None and self.host_manager.is_device_tracker_home(host) is True
        )

    @property
    def ip_address(self) -> str | None:
        """Return the primary IP address for the selected host."""
        host = self._host
        return host.ip_address if host is not None else None

    @property
    def mac_address(self) -> str | None:
        """Return the tracked client MAC address."""
        return self._attr_mac_address

    @property
    def hostname(self) -> str | None:
        """Return the hostname for the selected host."""
        host = self._host
        return host.dns_hostname if host is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return bounded device-tracker metadata attributes."""
        host = self._host
        return {
            **self._build_state_attributes(TRANS_KEY_PURPOSE_DEVICE_TRACKER_PRESENCE),
            ATTR_WATCHED_DEVICE_IP_ADDRESS: (
                host.ip_address if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_HOST_NAME: (
                host.host_name if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_DNS_HOSTNAME: (
                host.dns_hostname if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_DNS_DOMAIN: (
                host.dns_domain if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_DNS_FQDN: (host.dns_fqdn if host is not None else None),
            ATTR_WATCHED_DEVICE_HOST_DEVICE_TYPE: (
                host.host_device_type if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_DEVICE_GROUP: (
                host.group_name if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_NETWORK_NAME: (
                host.network_name if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_CONNECTION_TYPE: (
                host.connection_type if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_LAST_ACTIVE: (
                datetime.fromtimestamp(host.last_active, UTC).isoformat()
                if host is not None and host.last_active is not None
                else None
            ),
        }
