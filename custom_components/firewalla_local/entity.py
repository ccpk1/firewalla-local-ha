"""Shared entity primitives for Firewalla Local."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator
from .managers import FirewallaRuleManager, FirewallaSystemManager


class FirewallaEntity(CoordinatorEntity[FirewallaDataUpdateCoordinator]):
    """Shared base entity for Firewalla Local platforms."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: FirewallaConfigEntry,
        coordinator: FirewallaDataUpdateCoordinator,
    ) -> None:
        """Initialize the shared entity state."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def system_manager(self) -> FirewallaSystemManager:
        """Return the entry-scoped system manager."""
        return self._entry.runtime_data.system_manager

    @property
    def rule_manager(self) -> FirewallaRuleManager:
        """Return the entry-scoped rule manager."""
        return self._entry.runtime_data.rule_manager

    @property
    def device_info(self) -> DeviceInfo:
        """Return the shared license-anchored device information."""
        return self.system_manager.build_device_info()

    @property
    def available(self) -> bool:
        """Return coordinator-backed availability for Firewalla entities."""
        return super().available and self.coordinator.data is not None
