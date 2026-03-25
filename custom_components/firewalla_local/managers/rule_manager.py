"""Rule-domain orchestration for Firewalla Local."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final, Literal, TypedDict

from ..api import FirewallaApiClient
from ..const import (
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    RULE_TARGET_TAG,
)
from ..coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator
from ..models import (
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    FirewallaRuntimeSnapshot,
    format_policy_rule_label,
    supports_rule_switch,
)
from .base_manager import FirewallaBaseManager

_RAW_POLICY_RULES_KEY: Final = "policyRules"
_RAW_RULE_ACTION_KEY: Final = "action"
_RAW_RULE_ALARM_TYPE_KEY: Final = "alarm_type"
_RAW_RULE_BLOCKBY_KEY: Final = "blockby"
_RAW_RULE_CATEGORY_KEY: Final = "category"
_RAW_RULE_DIRECTION_KEY: Final = "direction"
_RAW_RULE_DISABLED_KEY: Final = "disabled"
_RAW_RULE_METHOD_KEY: Final = "method"
_RAW_RULE_NOTES_KEY: Final = "notes"
_RAW_RULE_PID_KEY: Final = "pid"
_RAW_RULE_PURPOSE_KEY: Final = "purpose"
_RAW_RULE_REASON_KEY: Final = "reason"
_RAW_RULE_SCOPE_KEY: Final = "scope"
_RAW_RULE_STATE_KEY: Final = "state"
_RAW_RULE_TAGS_KEY: Final = "tag"
_RAW_RULE_TARGET_KEY: Final = "target"
_RAW_RULE_TARGET_NAME_KEY: Final = "target_name"
_RAW_RULE_TYPE_KEY: Final = "type"
_RAW_RULE_UPDATED_TIME_KEY: Final = "updatedTime"
_RAW_RULE_IDLE_TS_KEY: Final = "idleTs"

_RULE_MANAGEMENT_CLASSIFICATION_SYSTEM: Final = "system_managed"
_RULE_MANAGEMENT_CLASSIFICATION_USER: Final = "user_managed"

_RAW_RULE_METHOD_AUTO_VALUE: Final = "auto"
_RAW_RULE_REASON_ALARM_INTEL_VALUE: Final = "ALARM_INTEL"
_AUTO_CREATED_NOTE_FRAGMENT: Final = "automatically created"
_RAW_RULE_DISABLED_FALSE_VALUE: Final = 0
_RAW_RULE_DISABLED_TRUE_VALUE: Final = 1
_RAW_RULE_IDLE_TS_EMPTY_VALUE: Final = ""

_RULE_MANAGEMENT_REASON_ALARM_BACKED: Final = "alarm_backed_rule"
_RULE_MANAGEMENT_REASON_ALARM_INTEL: Final = "alarm_intel_reason"
_RULE_MANAGEMENT_REASON_AUTO_CREATION_NOTE: Final = "automatic_creation_note"
_RULE_MANAGEMENT_REASON_INTEL_CATEGORY: Final = "intel_category"
_RULE_MANAGEMENT_REASON_METHOD_AUTO: Final = "method_auto"
_RULE_MANAGEMENT_REASON_SECURITY_ENGINE: Final = "security_engine_managed"

_RULE_REVIEW_REASON_MISSING_READABLE_TARGET_NAME: Final = "missing_readable_target_name"
_RULE_REVIEW_REASON_MISSING_SCOPE_RESOLUTION: Final = "missing_scope_resolution"
_RULE_REVIEW_REASON_MISSING_TAG_TARGET_RESOLUTION: Final = (
    "missing_tag_target_resolution"
)
_RULE_REVIEW_REASON_MISSING_TARGET_LIST_NAME: Final = "missing_target_list_name"
_RULE_REVIEW_REASON_TARGET_LIST_REFERENCE: Final = "target_list_reference"

_RULE_TARGET_LIST_PREFIX: Final = "TL-"
_RULE_TARGET_TYPE_CATEGORY: Final = "category"
_RULE_TARGET_TYPE_MAC: Final = "mac"
_RULE_TARGET_TYPE_NETWORK: Final = "network"

_RAW_POLICY_NORMALIZED_KEYS: Final = {
    _RAW_RULE_ACTION_KEY,
    _RAW_RULE_DIRECTION_KEY,
    _RAW_RULE_DISABLED_KEY,
    _RAW_RULE_PID_KEY,
    _RAW_RULE_PURPOSE_KEY,
    _RAW_RULE_SCOPE_KEY,
    _RAW_RULE_TAGS_KEY,
    _RAW_RULE_TARGET_KEY,
    _RAW_RULE_TARGET_NAME_KEY,
    _RAW_RULE_TYPE_KEY,
}


RuleManagementClassification = Literal[
    "system_managed",
    "user_managed",
]


class RuleManagementInfo(TypedDict):
    """Classified ownership information for one live rule."""

    classification: RuleManagementClassification
    reasons: list[str]


def _flatten_policy(value: object) -> object:
    """Flatten nested Firewalla policy values into stable simple values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if _RAW_RULE_STATE_KEY in value and isinstance(
            value[_RAW_RULE_STATE_KEY], bool
        ):
            return value[_RAW_RULE_STATE_KEY]
        return {
            key: flattened_value
            for key, nested_value in value.items()
            if (flattened_value := _flatten_policy(nested_value)) is not None
        }
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, (int, float, str)):
        return value
    return None


def extract_raw_rule_extras(raw_rule: Mapping[str, object]) -> dict[str, object]:
    """Return non-normalized raw rule fields for rule classification."""
    extras: dict[str, object] = {}
    for key, value in raw_rule.items():
        if key in _RAW_POLICY_NORMALIZED_KEYS:
            continue

        flattened_value = _flatten_policy(value)
        if flattened_value is None:
            continue

        extras[key] = flattened_value

    return extras


def build_rule_management_info(
    raw_extras: Mapping[str, object],
) -> RuleManagementInfo:
    """Classify whether a rule appears user-managed or Firewalla-managed."""
    reasons: list[str] = []

    if raw_extras.get(_RAW_RULE_METHOD_KEY) == _RAW_RULE_METHOD_AUTO_VALUE:
        reasons.append(_RULE_MANAGEMENT_REASON_METHOD_AUTO)
    if isinstance(raw_extras.get(_RAW_RULE_ALARM_TYPE_KEY), str):
        reasons.append(_RULE_MANAGEMENT_REASON_ALARM_BACKED)
    if isinstance(raw_extras.get(_RAW_RULE_BLOCKBY_KEY), str):
        reasons.append(_RULE_MANAGEMENT_REASON_SECURITY_ENGINE)
    if raw_extras.get(_RAW_RULE_REASON_KEY) == _RAW_RULE_REASON_ALARM_INTEL_VALUE:
        reasons.append(_RULE_MANAGEMENT_REASON_ALARM_INTEL)
    if raw_extras.get(_RAW_RULE_CATEGORY_KEY) == "intel":
        reasons.append(_RULE_MANAGEMENT_REASON_INTEL_CATEGORY)

    notes = raw_extras.get(_RAW_RULE_NOTES_KEY)
    if isinstance(notes, str) and _AUTO_CREATED_NOTE_FRAGMENT in notes.casefold():
        reasons.append(_RULE_MANAGEMENT_REASON_AUTO_CREATION_NOTE)

    classification: RuleManagementClassification = (
        _RULE_MANAGEMENT_CLASSIFICATION_SYSTEM
        if reasons
        else _RULE_MANAGEMENT_CLASSIFICATION_USER
    )
    return {
        "classification": classification,
        "reasons": reasons,
    }


def build_rule_review_reasons(
    rule: FirewallaPolicyRule, raw_rule: Mapping[str, object]
) -> list[str]:
    """Return heuristic review reasons for switch-candidate filtering."""
    reasons: list[str] = []
    raw_tags = raw_rule.get(_RAW_RULE_TAGS_KEY)

    if (
        rule.target_type
        in {
            _RULE_TARGET_TYPE_CATEGORY,
            _RULE_TARGET_TYPE_NETWORK,
            _RULE_TARGET_TYPE_MAC,
        }
        and rule.target_name is None
    ):
        reasons.append(_RULE_REVIEW_REASON_MISSING_READABLE_TARGET_NAME)
    if rule.target == RULE_TARGET_TAG and rule.target_name is None:
        reasons.append(_RULE_REVIEW_REASON_MISSING_TAG_TARGET_RESOLUTION)
    if (
        isinstance(raw_tags, list)
        and raw_tags
        and not rule.applies_to
        and not (rule.target == RULE_TARGET_TAG and rule.target_name)
    ):
        reasons.append(_RULE_REVIEW_REASON_MISSING_SCOPE_RESOLUTION)
    if rule.target.startswith(_RULE_TARGET_LIST_PREFIX):
        reasons.append(_RULE_REVIEW_REASON_TARGET_LIST_REFERENCE)
        if rule.target_name is None:
            reasons.append(_RULE_REVIEW_REASON_MISSING_TARGET_LIST_NAME)

    return reasons


def build_rule_switch_candidate_ids(
    payload: Mapping[str, object],
    policy_rules: tuple[FirewallaPolicyRule, ...],
) -> set[str]:
    """Return the rule IDs that are valid switch candidates."""
    raw_policy_rules = payload.get(_RAW_POLICY_RULES_KEY)
    raw_rule_index: dict[str, Mapping[str, object]] = {}
    if isinstance(raw_policy_rules, list):
        raw_rule_index = {
            raw_rule[_RAW_RULE_PID_KEY]: raw_rule
            for raw_rule in raw_policy_rules
            if isinstance(raw_rule, dict)
            and isinstance(raw_rule.get(_RAW_RULE_PID_KEY), str)
        }

    candidate_rule_ids: set[str] = set()
    for rule in policy_rules:
        raw_rule = raw_rule_index.get(rule.rule_id, {})
        review_reasons = build_rule_review_reasons(rule, raw_rule)
        raw_extras = extract_raw_rule_extras(raw_rule)
        management = build_rule_management_info(raw_extras)
        blocking_review_reasons = {
            reason
            for reason in review_reasons
            if reason
            not in {
                _RULE_REVIEW_REASON_MISSING_READABLE_TARGET_NAME,
                _RULE_REVIEW_REASON_TARGET_LIST_REFERENCE,
                _RULE_REVIEW_REASON_MISSING_TARGET_LIST_NAME,
            }
        }
        if (
            supports_rule_switch(rule)
            and management["classification"] == _RULE_MANAGEMENT_CLASSIFICATION_USER
            and not blocking_review_reasons
        ):
            candidate_rule_ids.add(rule.rule_id)

    return candidate_rule_ids


@dataclass(slots=True, frozen=True)
class FirewallaSelectedRuleView:
    """Resolved manager view for one selected rule template."""

    template: FirewallaRuleTemplate
    matching_rules: tuple[FirewallaPolicyRule, ...]

    @property
    def primary_rule(self) -> FirewallaPolicyRule | None:
        """Return the first current live match, if any."""
        if not self.matching_rules:
            return None
        return self.matching_rules[0]


class FirewallaRuleManager(FirewallaBaseManager):
    """Own rule-template matching, lookups, and mutations."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        entry: FirewallaConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the manager."""
        super().__init__(coordinator, entry, client)
        self._selected_templates: tuple[FirewallaRuleTemplate, ...] = ()
        self._rule_index: dict[str, FirewallaPolicyRule] = {}
        self._matching_rules_by_source_id: dict[
            str, tuple[FirewallaPolicyRule, ...]
        ] = {}
        self._last_payload: dict[str, object] | None = None

    @staticmethod
    def load_selected_templates(
        options: Mapping[str, object],
        snapshot: FirewallaRuntimeSnapshot | None,
    ) -> tuple[FirewallaRuleTemplate, ...]:
        """Load persisted switch templates, falling back to supported live rules."""
        templates: list[FirewallaRuleTemplate] = []
        raw_templates = options.get(CONF_SELECTED_RULE_TEMPLATES, [])
        if isinstance(raw_templates, list):
            for raw_template in raw_templates:
                if not isinstance(raw_template, dict):
                    continue
                if template := FirewallaRuleTemplate.from_dict(raw_template):
                    templates.append(template)

        if templates or snapshot is None:
            return tuple(templates)

        selected_rule_ids = options.get(CONF_SELECTED_RULE_IDS, [])
        if not isinstance(selected_rule_ids, list):
            return ()

        live_rule_index = {
            rule.rule_id: rule
            for rule in snapshot.policy_rules
            if supports_rule_switch(rule)
        }
        return tuple(
            FirewallaRuleTemplate.from_rule(rule)
            for rule_id in selected_rule_ids
            if isinstance(rule_id, str) and (rule := live_rule_index.get(rule_id))
        )

    def handle_refresh(
        self,
        payload: dict[str, object],
        snapshot: FirewallaRuntimeSnapshot,
    ) -> None:
        """Route refreshed runtime data into manager-owned indexes."""
        self._last_payload = payload
        self._rule_index = {rule.rule_id: rule for rule in snapshot.policy_rules}
        self._selected_templates = self.load_selected_templates(
            self.entry.options, snapshot
        )
        self._matching_rules_by_source_id = {
            template.source_rule_id: (
                (rule,)
                if (rule := self._rule_index.get(template.source_rule_id)) is not None
                else ()
            )
            for template in self._selected_templates
        }

    @property
    def selected_templates(self) -> tuple[FirewallaRuleTemplate, ...]:
        """Return the currently selected persisted templates."""
        return self._selected_templates

    def get_switch_candidate_rule_ids(self) -> set[str]:
        """Return live rule IDs that should be exposed for selection."""
        rules = tuple(self._rule_index.values())
        if not rules:
            return set()
        if self._last_payload is None:
            return {rule.rule_id for rule in rules if supports_rule_switch(rule)}
        return build_rule_switch_candidate_ids(self._last_payload, rules)

    def get_switch_candidate_rules(self) -> tuple[FirewallaPolicyRule, ...]:
        """Return live rules that pass the manager-owned candidate policy."""
        candidate_rule_ids = self.get_switch_candidate_rule_ids()
        return tuple(
            sorted(
                (
                    rule
                    for rule_id, rule in self._rule_index.items()
                    if rule_id in candidate_rule_ids
                ),
                key=lambda rule: rule.rule_id,
            )
        )

    def get_switch_candidate_choices(self) -> dict[str, str]:
        """Return selectable rule choices for the options flow."""
        return {
            rule.rule_id: f"[{rule.rule_id}] {format_policy_rule_label(rule)}"
            for rule in self.get_switch_candidate_rules()
        }

    def get_switch_candidate_templates(self) -> dict[str, FirewallaRuleTemplate]:
        """Return selectable rule templates keyed by source rule ID."""
        return {
            rule.rule_id: FirewallaRuleTemplate.from_rule(rule)
            for rule in self.get_switch_candidate_rules()
        }

    def get_selected_rule_view(
        self, source_rule_id: str
    ) -> FirewallaSelectedRuleView | None:
        """Return the resolved current state for one selected source rule ID."""
        template = next(
            (
                selected_template
                for selected_template in self._selected_templates
                if selected_template.source_rule_id == source_rule_id
            ),
            None,
        )
        if template is None:
            return None
        return FirewallaSelectedRuleView(
            template=template,
            matching_rules=self._matching_rules_by_source_id.get(source_rule_id, ()),
        )

    def get_matching_rules(
        self, template: FirewallaRuleTemplate
    ) -> tuple[FirewallaPolicyRule, ...]:
        """Return the current live rule that still backs a persisted template."""
        return self._matching_rules_by_source_id.get(template.source_rule_id, ())

    def get_enabled_matching_rules(
        self, template: FirewallaRuleTemplate
    ) -> tuple[FirewallaPolicyRule, ...]:
        """Return matching live rules that are currently enabled."""
        return tuple(rule for rule in self.get_matching_rules(template) if rule.enabled)

    def get_disabled_matching_rules(
        self, template: FirewallaRuleTemplate
    ) -> tuple[FirewallaPolicyRule, ...]:
        """Return matching live rules that are currently disabled."""
        return tuple(
            rule for rule in self.get_matching_rules(template) if not rule.enabled
        )

    async def async_set_template_enabled(
        self,
        template: FirewallaRuleTemplate,
        *,
        enabled: bool,
        idle_ts: int | None = None,
    ) -> None:
        """Update all rules backing one selected template."""
        rules = (
            self.get_disabled_matching_rules(template)
            if enabled
            else self.get_enabled_matching_rules(template)
        )
        if not rules:
            return

        await asyncio.gather(
            *(
                self.client.async_update_rule(
                    rule,
                    enabled=enabled,
                    **({"idle_ts": idle_ts} if idle_ts is not None else {}),
                )
                for rule in rules
            )
        )
        self._apply_optimistic_rule_update(
            tuple(rule.rule_id for rule in rules), enabled=enabled, idle_ts=idle_ts
        )

    async def async_pause_rule(self, rule_target: str, resume_ts: int | None) -> None:
        """Pause one live rule or one selected template target."""
        rules = self._resolve_rules_for_target(rule_target)
        if not rules:
            return

        await asyncio.gather(
            *(
                self.client.async_update_rule(rule, enabled=False, idle_ts=resume_ts)
                for rule in rules
            )
        )
        self._apply_optimistic_rule_update(
            tuple(rule.rule_id for rule in rules), enabled=False, idle_ts=resume_ts
        )

    async def async_resume_rule(self, rule_target: str) -> None:
        """Resume one live rule or one selected template target immediately."""
        rules = self._resolve_rules_for_target(rule_target)
        if not rules:
            return

        await asyncio.gather(
            *(self.client.async_update_rule(rule, enabled=True) for rule in rules)
        )
        self._apply_optimistic_rule_update(
            tuple(rule.rule_id for rule in rules), enabled=True, idle_ts=None
        )

    def _resolve_rules_for_target(
        self, rule_target: str
    ) -> tuple[FirewallaPolicyRule, ...]:
        """Resolve a service target into one or more live rules."""
        if rule := self._rule_index.get(rule_target):
            return (rule,)

        if selected_rule_view := self.get_selected_rule_view(rule_target):
            return selected_rule_view.matching_rules

        return ()

    def has_rule_target(self, rule_target: str) -> bool:
        """Return whether a live rule or selected template target exists."""
        return bool(self._resolve_rules_for_target(rule_target))

    def _apply_optimistic_rule_update(
        self,
        rule_ids: tuple[str, ...],
        *,
        enabled: bool,
        idle_ts: int | None,
    ) -> None:
        """Apply a successful mutation to the in-memory coordinator state."""
        snapshot = self.coordinator.data
        if snapshot is None:
            return

        updated_time = time.time()
        updated_rules = tuple(
            self._build_optimistic_rule(
                rule, enabled=enabled, idle_ts=idle_ts, updated_time=updated_time
            )
            if rule.rule_id in rule_ids
            else rule
            for rule in snapshot.policy_rules
        )
        updated_snapshot = replace(snapshot, policy_rules=updated_rules)
        self.handle_refresh(self._last_payload or {}, updated_snapshot)
        self.coordinator.async_set_updated_data(updated_snapshot)

    def _build_optimistic_rule(
        self,
        rule: FirewallaPolicyRule,
        *,
        enabled: bool,
        idle_ts: int | None,
        updated_time: float,
    ) -> FirewallaPolicyRule:
        """Return one rule with optimistic command state applied."""
        raw_update_payload = dict(rule.raw_update_payload)
        raw_update_payload[_RAW_RULE_DISABLED_KEY] = (
            _RAW_RULE_DISABLED_FALSE_VALUE if enabled else _RAW_RULE_DISABLED_TRUE_VALUE
        )
        raw_update_payload[_RAW_RULE_UPDATED_TIME_KEY] = updated_time
        if enabled:
            raw_update_payload[_RAW_RULE_IDLE_TS_KEY] = _RAW_RULE_IDLE_TS_EMPTY_VALUE
        elif idle_ts is not None:
            raw_update_payload[_RAW_RULE_IDLE_TS_KEY] = idle_ts
        else:
            raw_update_payload[_RAW_RULE_IDLE_TS_KEY] = _RAW_RULE_IDLE_TS_EMPTY_VALUE

        return replace(
            rule,
            enabled=enabled,
            updated_time=updated_time,
            raw_update_payload=raw_update_payload,
        )

    async def async_get_runtime_inventory_response(self) -> dict[str, object]:
        """Return the current runtime inventory data and markdown view."""
        # pylint: disable=import-outside-toplevel
        from ..helpers.runtime_inventory import (
            build_runtime_inventory_report,
            render_runtime_inventory_markdown,
        )

        payload = await self.client.async_get_runtime_init_payload()
        snapshot = self.client.build_runtime_snapshot(payload)
        report = build_runtime_inventory_report(payload, snapshot.policy_rules)
        return {
            "inventory": report,
            "markdown": render_runtime_inventory_markdown(report),
        }
