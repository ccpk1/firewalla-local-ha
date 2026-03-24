"""Typed models for Firewalla Local."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def _looks_like_internal_identifier(value: str) -> bool:
    """Return whether a target value looks like an internal Firewalla identifier."""
    segments = value.split("-")
    if len(segments) == 5 and all(segments):
        expected_lengths = (8, 4, 4, 4, 12)
        segment_lengths_match = all(
            len(segment) == length
            for segment, length in zip(segments, expected_lengths, strict=True)
        )
        if segment_lengths_match:
            return all(
                character in "0123456789abcdefABCDEF"
                for segment in segments
                for character in segment
            )
    return False


def _normalize_ref_values(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return a stable tuple for scope and tag matching."""
    return tuple(sorted(dict.fromkeys(values)))


@dataclass(slots=True)
class FirewallaSystemInfo:
    """Basic system information for a Firewalla appliance."""

    host: str
    name: str
    model: str | None
    serial_number: str | None
    software_version: str | None


@dataclass(slots=True, frozen=True)
class FirewallaPolicyRule:
    """Normalized local policy rule data from the Firewalla init payload."""

    rule_id: str
    action: str
    target: str
    target_type: str
    direction: str | None
    enabled: bool
    purpose: str | None
    scope: tuple[str, ...]
    tag_refs: tuple[str, ...] = ()
    target_name: str | None = None
    applies_to: tuple[str, ...] = ()
    activated_time: float | None = None
    updated_time: float | None = None
    last_activated_time: float | None = None
    expire_seconds: int | None = None
    expires_at: float | None = None
    auto_delete_when_expires: bool | None = None
    dnsmasq_only: bool | None = None
    raw_update_payload: dict[str, object] = field(default_factory=dict, compare=False)

    @property
    def is_temporary(self) -> bool:
        """Return whether this rule currently behaves like a temporary rule."""
        return self.expire_seconds is not None and self.auto_delete_when_expires is True

    @property
    def notes(self) -> str | None:
        """Return user-visible notes carried on the live rule payload."""
        raw_notes = self.raw_update_payload.get("notes")
        if not isinstance(raw_notes, str):
            return None
        stripped_notes = raw_notes.strip()
        return stripped_notes or None

    @property
    def pause_until(self) -> float | None:
        """Return the pause boundary timestamp carried by Firewalla, if any."""
        raw_idle_ts = self.raw_update_payload.get("idleTs")
        if isinstance(raw_idle_ts, (int, float)):
            return float(raw_idle_ts)
        if isinstance(raw_idle_ts, str) and raw_idle_ts:
            try:
                return float(raw_idle_ts)
            except ValueError:
                return None
        return None

    @property
    def is_paused(self) -> bool:
        """Return whether the rule is currently in a timed paused state."""
        if self.enabled:
            return False

        if (pause_until := self.pause_until) is None:
            return False

        return pause_until > time.time()

    @property
    def pause_remaining_seconds(self) -> int | None:
        """Return remaining seconds for a timed pause, if the rule is paused."""
        if not self.is_paused:
            return None

        assert self.pause_until is not None
        return max(0, int(self.pause_until - time.time()))


@dataclass(slots=True)
class FirewallaRuntimeSnapshot:
    """Coordinator-ready runtime snapshot fetched from the local API."""

    system_info: FirewallaSystemInfo
    policy_rules: tuple[FirewallaPolicyRule, ...]
    exception_rule_count: int


def format_policy_rule_name(rule: FirewallaPolicyRule) -> str:
    """Build a readable state-free name for one normalized policy rule."""
    applicability = f" for {', '.join(rule.applies_to)}" if rule.applies_to else ""

    if rule.target_type == "mac" and rule.target == "TAG":
        if rule.target_name:
            return f"{rule.action} internet for {rule.target_name}"
        return f"{rule.action} internet{applicability}"

    display_target = rule.target
    if rule.target_name:
        prettified_target = rule.target.replace("_", " ")
        target_is_internal_id = rule.target_type in {
            "network",
            "category",
        } and _looks_like_internal_identifier(rule.target)
        if (
            rule.target_name.casefold() == prettified_target.casefold()
            or target_is_internal_id
        ):
            display_target = rule.target_name
        elif rule.target_name != rule.target:
            display_target = f"{rule.target_name} [{rule.target}]"
        else:
            display_target = rule.target_name

    if (
        applicability
        and rule.target_name
        and applicability == f" for {rule.target_name}"
    ):
        applicability = ""

    return f"{rule.action} {rule.target_type} {display_target}{applicability}"


def format_policy_rule_label(rule: FirewallaPolicyRule) -> str:
    """Build a readable label for one normalized Firewalla policy rule."""
    status = "enabled" if rule.enabled else "disabled"
    return f"{format_policy_rule_name(rule)} ({status})"


def supports_rule_switch(rule: FirewallaPolicyRule) -> bool:
    """Return whether a persistent existing rule can back an update-only switch."""
    if rule.auto_delete_when_expires is True or rule.is_temporary:
        return False

    if rule.purpose == "family":
        return False

    if rule.action == "block" and rule.target_type == "mac" and rule.target == "TAG":
        return True

    if rule.target_type == "dns":
        return rule.action in {"allow", "block"} and rule.purpose is None

    if rule.target_type == "network":
        return (
            rule.action in {"allow", "block"}
            and rule.purpose is None
            and rule.target_name is not None
        )

    if rule.target_type == "category":
        if rule.action not in {"allow", "block"} or rule.purpose is not None:
            return False

        if rule.target_name:
            return True

        return not rule.target.startswith("TL-")

    return False


@dataclass(slots=True, frozen=True)
class FirewallaRuleTemplate:
    """Persisted template used to recreate and match one rule-backed switch."""

    source_rule_id: str
    name: str
    action: str
    target: str
    target_type: str
    scope: tuple[str, ...] = ()
    tag_refs: tuple[str, ...] = ()
    dnsmasq_only: bool | None = None
    use_bf: bool = True

    @classmethod
    def from_rule(cls, rule: FirewallaPolicyRule) -> FirewallaRuleTemplate:
        """Build a durable template from one currently selected policy rule."""
        return cls(
            source_rule_id=rule.rule_id,
            name=format_policy_rule_name(rule),
            action=rule.action,
            target=rule.target,
            target_type=rule.target_type,
            scope=_normalize_ref_values(rule.scope),
            tag_refs=_normalize_ref_values(rule.tag_refs),
            dnsmasq_only=rule.dnsmasq_only,
        )

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> FirewallaRuleTemplate | None:
        """Deserialize a stored rule template from config entry options."""
        source_rule_id = data.get("source_rule_id")
        name = data.get("name")
        action = data.get("action")
        target = data.get("target")
        target_type = data.get("target_type")
        if not all(
            isinstance(value, str) and value
            for value in (source_rule_id, name, action, target, target_type)
        ):
            return None
        assert isinstance(source_rule_id, str)
        assert isinstance(name, str)
        assert isinstance(action, str)
        assert isinstance(target, str)
        assert isinstance(target_type, str)

        raw_scope = data.get("scope")
        scope = (
            tuple(item for item in raw_scope if isinstance(item, str) and item)
            if isinstance(raw_scope, list)
            else ()
        )
        raw_tag_refs = data.get("tag_refs")
        tag_refs = (
            tuple(item for item in raw_tag_refs if isinstance(item, str) and item)
            if isinstance(raw_tag_refs, list)
            else ()
        )
        dnsmasq_only = data.get("dnsmasq_only")
        if dnsmasq_only is not None and not isinstance(dnsmasq_only, bool):
            dnsmasq_only = None
        use_bf = data.get("use_bf")

        return cls(
            source_rule_id=source_rule_id,
            name=name,
            action=action,
            target=target,
            target_type=target_type,
            scope=_normalize_ref_values(scope),
            tag_refs=_normalize_ref_values(tag_refs),
            dnsmasq_only=dnsmasq_only,
            use_bf=use_bf if isinstance(use_bf, bool) else True,
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize the template for config entry option storage."""
        return {
            "source_rule_id": self.source_rule_id,
            "name": self.name,
            "action": self.action,
            "target": self.target,
            "target_type": self.target_type,
            "scope": list(self.scope),
            "tag_refs": list(self.tag_refs),
            "dnsmasq_only": self.dnsmasq_only,
            "use_bf": self.use_bf,
        }

    def matches_rule(self, rule: FirewallaPolicyRule) -> bool:
        """Return whether a live rule matches this switch template identity."""
        return (
            rule.action == self.action
            and rule.target == self.target
            and rule.target_type == self.target_type
            and _normalize_ref_values(rule.scope) == self.scope
            and _normalize_ref_values(rule.tag_refs) == self.tag_refs
            and (self.dnsmasq_only is None or rule.dnsmasq_only == self.dnsmasq_only)
        )

    def build_create_value(self, *, updated_time: float) -> dict[str, object]:
        """Build the confirmed persistent create payload for this template."""
        payload: dict[str, object] = {
            "action": self.action,
            "appTimeUsage": {},
            "disturbLevel": "",
            "disturbMethod": {},
            "duration": "",
            "scope": list(self.scope),
            "target": self.target,
            "trust": "",
            "type": self.target_type,
            "updatedTime": updated_time,
            "useBf": self.use_bf,
        }
        if self.tag_refs:
            payload["tag"] = list(self.tag_refs)
        if self.dnsmasq_only is not None:
            payload["dnsmasq_only"] = self.dnsmasq_only
        return payload
