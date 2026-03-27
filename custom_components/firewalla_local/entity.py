"""Shared entity primitives for Firewalla Local."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator
from .managers import (
    FirewallaHostManager,
    FirewallaIntegrationManager,
    FirewallaRuleManager,
    FirewallaUserManager,
)
from .models import (
    FirewallaSpeedTestResult,
    FirewallaSystemInfo,
    FirewallaSystemStatus,
    FirewallaWatchedUser,
)


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
    def integration_manager(self) -> FirewallaIntegrationManager:
        """Return the entry-scoped integration manager."""
        return self._entry.runtime_data.integration_manager

    @property
    def host_manager(self) -> FirewallaHostManager:
        """Return the entry-scoped host manager."""
        return self._entry.runtime_data.host_manager

    @property
    def rule_manager(self) -> FirewallaRuleManager:
        """Return the entry-scoped rule manager."""
        return self._entry.runtime_data.rule_manager

    @property
    def user_manager(self) -> FirewallaUserManager:
        """Return the entry-scoped user manager."""
        return self._entry.runtime_data.user_manager

    @property
    def system_info(self) -> FirewallaSystemInfo:
        """Return the shaped appliance identity view."""
        return self.integration_manager.system_info

    @property
    def system_status(self) -> FirewallaSystemStatus | None:
        """Return the shaped appliance status view."""
        return self.integration_manager.system_status

    @property
    def latest_speed_test(self) -> FirewallaSpeedTestResult | None:
        """Return the shaped latest speed-test view."""
        return self.integration_manager.latest_speed_test

    def get_watched_user(self, user_id: str) -> FirewallaWatchedUser | None:
        """Return one manager-owned watched-user view."""
        return self.user_manager.get_user(user_id)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the shared license-anchored device information."""
        return self.integration_manager.build_device_info()

    @property
    def available(self) -> bool:
        """Return coordinator-backed availability for Firewalla entities."""
        return super().available and self.coordinator.data is not None
