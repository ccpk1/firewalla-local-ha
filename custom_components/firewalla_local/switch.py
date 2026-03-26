"""Switch platform for Firewalla Local rule-backed controls."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    ATTR_RULE_ACTION,
    ATTR_RULE_CURRENT_STATE_REASON,
    ATTR_RULE_CUSTOM_NAME,
    ATTR_RULE_ID,
    ATTR_RULE_IS_PAUSED,
    ATTR_RULE_NAME,
    ATTR_RULE_NOTES,
    ATTR_RULE_PAUSE_REMAINING_SECONDS,
    ATTR_RULE_PAUSE_UNTIL,
    ATTR_RULE_PURPOSE,
    ATTR_RULE_SCHEDULE_DAYS,
    ATTR_RULE_SCHEDULE_DURATION,
    ATTR_RULE_SCHEDULE_NEXT_END,
    ATTR_RULE_SCHEDULE_NEXT_START,
    ATTR_RULE_SCHEDULE_START_CRON,
    ATTR_RULE_TIME_LIMIT_PERIOD_CRON,
    ATTR_RULE_TIME_LIMIT_QUOTA,
    ATTR_RULE_TIME_LIMIT_USED,
    ENTITY_SUFFIX_SWITCH,
    RULE_ACTION_BLOCK,
    TRANS_KEY_ENTITY_SWITCH_ALLOW_RULE,
    TRANS_KEY_ENTITY_SWITCH_BLOCK_RULE,
    TRANS_KEY_PURPOSE_RULE_SWITCH,
    TRANS_PLACEHOLDER_RULE_NAME,
)
from .coordinator import FirewallaConfigEntry
from .entity import FirewallaEntity
from .models import (
    FirewallaRuleTemplate,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: FirewallaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Firewalla Local rule-backed switches from a config entry."""
    del _hass
    templates = entry.runtime_data.rule_manager.selected_templates
    async_add_entities(FirewallaRuleSwitch(entry, template) for template in templates)


class FirewallaRuleSwitch(FirewallaEntity, SwitchEntity):
    """Expose one persisted Firewalla rule template as a switch."""

    def __init__(
        self,
        entry: FirewallaConfigEntry,
        template: FirewallaRuleTemplate,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(entry, entry.runtime_data.coordinator)
        self._template = template
        self._attr_translation_key = self._get_translation_key(template)
        self._attr_translation_placeholders = {
            TRANS_PLACEHOLDER_RULE_NAME: template.name
        }
        self._attr_suggested_object_id = slugify(template.name)
        self._attr_unique_id = self.system_manager.build_entity_unique_id(
            object_id=template.source_rule_id,
            suffix=ENTITY_SUFFIX_SWITCH,
        )

    @staticmethod
    def _get_translation_key(template: FirewallaRuleTemplate) -> str:
        """Return the translation-backed key for this rule-backed switch."""
        if template.action == RULE_ACTION_BLOCK:
            return TRANS_KEY_ENTITY_SWITCH_BLOCK_RULE
        return TRANS_KEY_ENTITY_SWITCH_ALLOW_RULE

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return stable attributes that describe the selected rule template."""
        matching_rules = self.rule_manager.get_matching_rules(self._template)
        matched_rule = matching_rules[0] if len(matching_rules) == 1 else None
        time_zone = dt_util.get_time_zone(self.coordinator.hass.config.time_zone)
        notes = [rule.notes for rule in matching_rules if isinstance(rule.notes, str)]
        schedule_next_start = (
            matched_rule.schedule_next_start(time_zone=time_zone)
            if matched_rule is not None
            else None
        )
        schedule_window = (
            matched_rule.schedule_window(time_zone=time_zone)
            if matched_rule is not None
            else None
        )
        pause_until = (
            datetime.fromtimestamp(matched_rule.pause_until, UTC).isoformat()
            if matched_rule is not None
            and matched_rule.is_paused
            and matched_rule.pause_until is not None
            else None
        )
        attributes: dict[str, object] = {
            ATTR_RULE_PURPOSE: TRANS_KEY_PURPOSE_RULE_SWITCH,
            ATTR_RULE_ID: matched_rule.rule_id if matched_rule is not None else None,
            ATTR_RULE_NAME: self._template.name,
        }

        if (
            matched_rule is not None
            and matched_rule.custom_name is not None
            and matched_rule.custom_name != self._template.name
        ):
            attributes[ATTR_RULE_CUSTOM_NAME] = matched_rule.custom_name

        if notes:
            attributes[ATTR_RULE_NOTES] = "; ".join(dict.fromkeys(notes))

        attributes[ATTR_RULE_ACTION] = self._template.action
        attributes[ATTR_RULE_IS_PAUSED] = any(rule.is_paused for rule in matching_rules)

        if pause_until is not None:
            attributes[ATTR_RULE_PAUSE_UNTIL] = pause_until

        if (
            matched_rule is not None
            and matched_rule.pause_remaining_seconds is not None
        ):
            attributes[ATTR_RULE_PAUSE_REMAINING_SECONDS] = (
                matched_rule.pause_remaining_seconds
            )

        if matched_rule is not None and matched_rule.schedule_start_cron is not None:
            attributes[ATTR_RULE_SCHEDULE_START_CRON] = matched_rule.schedule_start_cron

        if matched_rule is not None and matched_rule.schedule_duration is not None:
            attributes[ATTR_RULE_SCHEDULE_DURATION] = matched_rule.schedule_duration

        if matched_rule is not None and (
            schedule_days := matched_rule.schedule_days(time_zone=time_zone)
        ):
            attributes[ATTR_RULE_SCHEDULE_DAYS] = list(schedule_days)

        if schedule_next_start is not None:
            attributes[ATTR_RULE_SCHEDULE_NEXT_START] = schedule_next_start.isoformat()

        if schedule_window is not None:
            attributes[ATTR_RULE_SCHEDULE_NEXT_END] = schedule_window[1].isoformat()

        if matched_rule is not None and matched_rule.time_limit_period_cron is not None:
            attributes[ATTR_RULE_TIME_LIMIT_PERIOD_CRON] = (
                matched_rule.time_limit_period_cron
            )

        if matched_rule is not None and matched_rule.time_limit_quota is not None:
            attributes[ATTR_RULE_TIME_LIMIT_QUOTA] = matched_rule.time_limit_quota

        if matched_rule is not None and matched_rule.time_limit_used is not None:
            attributes[ATTR_RULE_TIME_LIMIT_USED] = matched_rule.time_limit_used

        if matched_rule is not None:
            attributes[ATTR_RULE_CURRENT_STATE_REASON] = (
                matched_rule.current_state_reason(time_zone=time_zone)
            )

        return attributes

    @property
    def available(self) -> bool:
        """Return whether the selected backing rule still exists."""
        return super().available and bool(
            self.rule_manager.get_matching_rules(self._template)
        )

    @property
    def is_on(self) -> bool:
        """Return whether a matching enabled rule currently exists."""
        return bool(self.rule_manager.get_enabled_matching_rules(self._template))

    def turn_on(self, **kwargs: object) -> None:
        """Satisfy the sync toggle contract; Home Assistant calls async_turn_on."""
        raise NotImplementedError

    def turn_off(self, **kwargs: object) -> None:
        """Satisfy the sync toggle contract; Home Assistant calls async_turn_off."""
        raise NotImplementedError

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable matching disabled rules without recreating them."""
        del kwargs
        if self.is_on:
            return
        await self.rule_manager.async_set_template_enabled(self._template, enabled=True)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable matching enabled rules without deleting them."""
        del kwargs
        await self.rule_manager.async_set_template_enabled(
            self._template, enabled=False
        )
