"""Switch platform for Firewalla Local rule-backed controls."""

from __future__ import annotations

import asyncio

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    DOMAIN,
)
from .coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator
from .models import (
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    FirewallaRuntimeSnapshot,
    supports_rule_switch,
)

PARALLEL_UPDATES = 1


def _load_selected_templates(
    entry: FirewallaConfigEntry, snapshot: FirewallaRuntimeSnapshot | None
) -> list[FirewallaRuleTemplate]:
    """Load persisted switch templates, falling back to selected live rules."""
    templates: list[FirewallaRuleTemplate] = []
    raw_templates = entry.options.get(CONF_SELECTED_RULE_TEMPLATES, [])
    if isinstance(raw_templates, list):
        for raw_template in raw_templates:
            if not isinstance(raw_template, dict):
                continue
            if template := FirewallaRuleTemplate.from_dict(raw_template):
                templates.append(template)

    if templates or snapshot is None:
        return templates

    selected_rule_ids = entry.options.get(CONF_SELECTED_RULE_IDS, [])
    if not isinstance(selected_rule_ids, list):
        return []

    live_rule_index = {
        rule.rule_id: rule
        for rule in snapshot.policy_rules
        if supports_rule_switch(rule)
    }
    return [
        FirewallaRuleTemplate.from_rule(rule)
        for rule_id in selected_rule_ids
        if isinstance(rule_id, str) and (rule := live_rule_index.get(rule_id))
    ]


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: FirewallaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Firewalla Local rule-backed switches from a config entry."""
    del _hass
    templates = _load_selected_templates(entry, entry.runtime_data.coordinator.data)
    async_add_entities(
        FirewallaRuleSwitch(entry, entry.runtime_data.coordinator, template)
        for template in templates
    )


class FirewallaRuleSwitch(
    CoordinatorEntity[FirewallaDataUpdateCoordinator], SwitchEntity
):
    """Expose one persisted Firewalla rule template as a switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: FirewallaConfigEntry,
        coordinator: FirewallaDataUpdateCoordinator,
        template: FirewallaRuleTemplate,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        if not entry.unique_id:
            raise ValueError("Firewalla config entry is missing its license unique ID")

        self._entry = entry
        self._license = entry.unique_id
        self._template = template
        self._attr_name = template.source_rule_id
        self._attr_suggested_object_id = f"rule_{template.source_rule_id}"
        self._attr_unique_id = f"{self._license}_rule_{template.source_rule_id}"
        self._attr_icon = (
            "mdi:shield-lock" if template.action == "block" else "mdi:shield-check"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the parent Firewalla device information."""
        system_info = self.coordinator.data.system_info
        return DeviceInfo(
            identifiers={(DOMAIN, self._license)},
            manufacturer="Firewalla",
            model=system_info.model,
            name=system_info.name,
            serial_number=system_info.serial_number,
            sw_version=system_info.software_version,
        )

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return stable attributes that describe the selected rule template."""
        matching_rules = self._matching_rules()
        matched_rule_details = [
            {
                "rule_id": rule.rule_id,
                "enabled": rule.enabled,
                "notes": rule.notes,
                "is_paused": rule.is_paused,
                "pause_until": rule.pause_until,
                "pause_remaining_seconds": rule.pause_remaining_seconds,
            }
            for rule in matching_rules
        ]
        notes = [
            detail["notes"]
            for detail in matched_rule_details
            if isinstance(detail["notes"], str)
        ]
        paused_rule_ids = [
            detail["rule_id"]
            for detail in matched_rule_details
            if detail["is_paused"] is True
        ]

        return {
            "rule_id": matching_rules[0].rule_id if len(matching_rules) == 1 else None,
            "matching_rule_count": len(matching_rules),
            "backing_rule_present": bool(matching_rules),
            "target": self._template.target,
            "target_type": self._template.target_type,
            "tag_refs": list(self._template.tag_refs),
            "notes": notes,
            "is_paused": bool(paused_rule_ids),
            "paused_rule_ids": paused_rule_ids,
            "matched_rules": matched_rule_details,
        }

    @property
    def available(self) -> bool:
        """Return whether the selected backing rule still exists."""
        return super().available and bool(self._matching_rules())

    @property
    def is_on(self) -> bool:
        """Return whether a matching enabled rule currently exists."""
        return bool(self._enabled_matching_rules())

    def _matching_rules(self) -> tuple[FirewallaPolicyRule, ...]:
        """Return the current live rules that match this switch template."""
        snapshot = self.coordinator.data
        if snapshot is None:
            return ()
        return tuple(
            rule for rule in snapshot.policy_rules if self._template.matches_rule(rule)
        )

    def _enabled_matching_rules(self) -> tuple[FirewallaPolicyRule, ...]:
        """Return matching live rules that are currently enabled."""
        return tuple(rule for rule in self._matching_rules() if rule.enabled)

    def _disabled_matching_rules(self) -> tuple[FirewallaPolicyRule, ...]:
        """Return matching live rules that are currently disabled."""
        return tuple(rule for rule in self._matching_rules() if not rule.enabled)

    def turn_on(self, **kwargs: object) -> None:
        """Satisfy the sync toggle contract; Home Assistant calls async_turn_on."""
        raise NotImplementedError

    def turn_off(self, **kwargs: object) -> None:
        """Satisfy the sync toggle contract; Home Assistant calls async_turn_off."""
        raise NotImplementedError

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable matching disabled rules without recreating them."""
        if self.is_on:
            return

        rules = self._disabled_matching_rules()
        if not rules:
            return

        await asyncio.gather(
            *(
                self.coordinator.client.async_update_rule(rule, enabled=True)
                for rule in rules
            )
        )
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable matching enabled rules without deleting them."""
        rules = self._enabled_matching_rules()
        if not rules:
            return

        await asyncio.gather(
            *(
                self.coordinator.client.async_update_rule(rule, enabled=False)
                for rule in rules
            )
        )
        await self.coordinator.async_refresh()
