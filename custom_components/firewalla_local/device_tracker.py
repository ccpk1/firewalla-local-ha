"""Device tracker platform for Firewalla Local router-backed presence."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_PURPOSE,
    ATTR_WATCHED_DEVICE_CONNECTION_TYPE,
    ATTR_WATCHED_DEVICE_DEVICE_GROUP,
    ATTR_WATCHED_DEVICE_IP_ADDRESS,
    ATTR_WATCHED_DEVICE_LAST_ACTIVE,
    ATTR_WATCHED_DEVICE_NETWORK_NAME,
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
    CoordinatorEntity[FirewallaDataUpdateCoordinator], ScannerEntity
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

    def find_device_entry(self) -> dr.DeviceEntry | None:
        """Return the tracked-client device entry for this tracker."""
        return dr.async_get(self.hass).async_get_device(
            identifiers={
                self._entry.runtime_data.integration_manager.build_tracked_client_device_identifier(
                    self._mac
                )
            }
        )

    @property
    def _host(self) -> FirewallaHostRuntime | None:
        """Return the currently resolved device-tracker host."""
        return self.host_manager.get_host(self._mac)

    def _handle_coordinator_update(self) -> None:
        """Write updated state from the coordinator."""
        super()._handle_coordinator_update()

    async def async_internal_added_to_hass(self) -> None:
        """Attach the tracker to its client device and normalize auto IDs."""
        await super().async_internal_added_to_hass()

        if self.registry_entry is None:
            return

        entity_registry = er.async_get(self.hass)
        new_entity_id = entity_registry.async_regenerate_entity_id(self.registry_entry)

        if new_entity_id == self.entity_id:
            return

        if not self._is_auto_generated_entity_id():
            return

        self.registry_entry = entity_registry.async_update_entity(
            self.entity_id,
            new_entity_id=new_entity_id,
        )
        self.entity_id = self.registry_entry.entity_id

    def _is_auto_generated_entity_id(self) -> bool:
        """Return whether the current entity ID can be safely normalized."""
        current_object_id = self.entity_id.split(".", maxsplit=1)[1]
        if current_object_id == "presence":
            return True

        if (
            current_object_id.startswith("presence_")
            and current_object_id[9:].isdigit()
        ):
            return True

        if (device_entry := self.find_device_entry()) is None:
            return False

        device_name = device_entry.name_by_user or device_entry.name
        if device_name is None:
            return False

        return current_object_id == slugify(device_name)

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
        return host.display_name if host is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return bounded device-tracker metadata attributes."""
        host = self._host
        return {
            ATTR_PURPOSE: TRANS_KEY_PURPOSE_DEVICE_TRACKER_PRESENCE,
            ATTR_WATCHED_DEVICE_IP_ADDRESS: (
                host.ip_address if host is not None else None
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
