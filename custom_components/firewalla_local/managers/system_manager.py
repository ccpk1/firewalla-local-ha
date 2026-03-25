"""System-scoped orchestration for Firewalla Local."""

from __future__ import annotations

from typing import Final

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from ..const import (
    CONF_LICENSE,
    DOMAIN,
    ENTITY_SUFFIX_SWITCH,
    MANUFACTURER,
    PLATFORM_SWITCH,
)
from ..models import FirewallaRuleTemplate
from .base_manager import FirewallaBaseManager

ORPHAN_POLICY_RETAIN_UNAVAILABLE_UNTIL_DESELECTED: Final = (
    "retain_unavailable_until_deselected"
)


class FirewallaSystemManager(FirewallaBaseManager):
    """Own shared entry-scoped lifecycle and device behavior."""

    ORPHAN_POLICY: Final = ORPHAN_POLICY_RETAIN_UNAVAILABLE_UNTIL_DESELECTED

    def build_device_info(self) -> DeviceInfo:
        """Build the license-anchored device entry for this config entry."""
        system_info = self.coordinator.data.system_info
        return DeviceInfo(
            identifiers={
                (DOMAIN, self.entry.unique_id or self.entry.data[CONF_LICENSE])
            },
            manufacturer=MANUFACTURER,
            model=system_info.model,
            name=system_info.name,
            serial_number=system_info.serial_number,
            sw_version=system_info.software_version,
        )

    def build_entity_unique_id(self, *, object_id: str, suffix: str) -> str:
        """Build a multi-instance-safe unique ID for one entity surface."""
        return f"{self.entry.entry_id}_{object_id}_{suffix}"

    async def async_reconcile_rule_switch_entities(
        self, templates: tuple[FirewallaRuleTemplate, ...]
    ) -> None:
        """Remove stale rule-switch registry entries for deselected templates."""
        entity_registry = er.async_get(self.coordinator.hass)
        expected_unique_ids = {
            self.build_entity_unique_id(
                object_id=template.source_rule_id,
                suffix=ENTITY_SUFFIX_SWITCH,
            )
            for template in templates
        }

        for entity_entry in er.async_entries_for_config_entry(
            entity_registry,
            self.entry.entry_id,
        ):
            if (
                entity_entry.domain != PLATFORM_SWITCH
                or entity_entry.platform != DOMAIN
            ):
                continue
            if not entity_entry.unique_id.endswith(f"_{ENTITY_SUFFIX_SWITCH}"):
                continue
            if entity_entry.unique_id in expected_unique_ids:
                continue

            entity_registry.async_remove(entity_entry.entity_id)
