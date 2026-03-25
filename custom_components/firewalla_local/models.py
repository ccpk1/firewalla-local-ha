"""Typed models for Firewalla Local."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Final, TypedDict

from .const import (
    RULE_ACTION_ALLOW,
    RULE_ACTION_BLOCK,
    RULE_PURPOSE_FAMILY,
    RULE_TARGET_TAG,
    RULE_TARGET_TYPE_CATEGORY,
    RULE_TARGET_TYPE_DNS,
    RULE_TARGET_TYPE_IP,
    RULE_TARGET_TYPE_MAC,
    RULE_TARGET_TYPE_NETWORK,
    RULE_TARGET_TYPE_REMOTE_PORT,
)

_RAW_UPDATE_IDLE_TS_KEY: Final = "idleTs"
_RAW_UPDATE_NOTES_KEY: Final = "notes"
_STATUS_DISABLED: Final = "disabled"
_STATUS_ENABLED: Final = "enabled"
_TEMPLATE_DATA_ACTION_KEY: Final = "action"
_TEMPLATE_DATA_DNSMASQ_ONLY_KEY: Final = "dnsmasq_only"
_TEMPLATE_DATA_NAME_KEY: Final = "name"
_TEMPLATE_DATA_SCOPE_KEY: Final = "scope"
_TEMPLATE_DATA_SOURCE_RULE_ID_KEY: Final = "source_rule_id"
_TEMPLATE_DATA_TAG_REFS_KEY: Final = "tag_refs"
_TEMPLATE_DATA_TARGET_KEY: Final = "target"
_TEMPLATE_DATA_TARGET_TYPE_KEY: Final = "target_type"
_TEMPLATE_DATA_USE_BF_KEY: Final = "use_bf"
_CREATE_PAYLOAD_ACTION_KEY: Final = "action"
_CREATE_PAYLOAD_APP_TIME_USAGE_KEY: Final = "appTimeUsage"
_CREATE_PAYLOAD_DISTURB_LEVEL_KEY: Final = "disturbLevel"
_CREATE_PAYLOAD_DISTURB_METHOD_KEY: Final = "disturbMethod"
_CREATE_PAYLOAD_DNSMASQ_ONLY_KEY: Final = "dnsmasq_only"
_CREATE_PAYLOAD_DURATION_KEY: Final = "duration"
_CREATE_PAYLOAD_SCOPE_KEY: Final = "scope"
_CREATE_PAYLOAD_TAG_KEY: Final = "tag"
_CREATE_PAYLOAD_TARGET_KEY: Final = "target"
_CREATE_PAYLOAD_TRUST_KEY: Final = "trust"
_CREATE_PAYLOAD_TYPE_KEY: Final = "type"
_CREATE_PAYLOAD_UPDATED_TIME_KEY: Final = "updatedTime"
_CREATE_PAYLOAD_USE_BF_KEY: Final = "useBf"
_INTERNAL_IDENTIFIER_SEPARATOR: Final = "-"
_PRETTIFIED_TARGET_SEPARATOR: Final = "_"
_PRETTIFIED_TARGET_REPLACEMENT: Final = " "
_TARGET_LIST_PREFIX: Final = "TL-"


class FirewallaRuleTemplateDict(TypedDict):
    """Serialized config-entry storage shape for a rule template."""

    source_rule_id: str
    name: str
    action: str
    target: str
    target_type: str
    scope: list[str]
    tag_refs: list[str]
    dnsmasq_only: bool | None
    use_bf: bool


class FirewallaRuleCreatePayload(TypedDict, total=False):
    """Confirmed create payload shape for a Firewalla rule template."""

    action: str
    appTimeUsage: dict[str, object]
    disturbLevel: str
    disturbMethod: dict[str, object]
    duration: str
    scope: list[str]
    target: str
    trust: str
    type: str
    updatedTime: float
    useBf: bool
    tag: list[str]
    dnsmasq_only: bool


def _looks_like_internal_identifier(value: str) -> bool:
    """Return whether a target value looks like an internal Firewalla identifier."""
    segments = value.split(_INTERNAL_IDENTIFIER_SEPARATOR)
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


@dataclass(slots=True)
class FirewallaSystemStatus:
    """Normalized system-status state for the Firewalla appliance."""

    booting_complete: bool | None = None
    cloud_connected: bool | None = None
    ddns: str | None = None
    firmware_release_type: str | None = None
    wan_ip: str | None = None
    wan_ips: dict[str, str] | None = None
    cpu_load_5m: float | None = None
    memory_usage_percent: float | None = None
    memory_free_mb: float | None = None
    disk_usage_percent_by_mount: dict[str, int] | None = None


@dataclass(slots=True)
class FirewallaSpeedTestResult:
    """Normalized latest internet speed-test result."""

    tested_at_timestamp: float
    download_mbps: float | None
    upload_mbps: float | None
    latency_ms: float | None
    jitter_ms: float | None
    packet_loss_percent: float | None
    download_megabytes: float | None
    upload_megabytes: float | None
    isp: str | None
    public_ip: str | None
    server_country: str | None
    server_host: str | None
    server_id: str | None
    server_location: str | None
    server_sponsor: str | None
    manual: bool | None
    success: bool
    vendor: str | None


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
        raw_notes = self.raw_update_payload.get(_RAW_UPDATE_NOTES_KEY)
        if not isinstance(raw_notes, str):
            return None
        stripped_notes = raw_notes.strip()
        return stripped_notes or None

    @property
    def pause_until(self) -> float | None:
        """Return the pause boundary timestamp carried by Firewalla, if any."""
        raw_idle_ts = self.raw_update_payload.get(_RAW_UPDATE_IDLE_TS_KEY)
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
    system_status: FirewallaSystemStatus | None = None
    latest_speed_test: FirewallaSpeedTestResult | None = None


def format_policy_rule_name(rule: FirewallaPolicyRule) -> str:
    """Build a readable state-free name for one normalized policy rule."""
    applicability = f" for {', '.join(rule.applies_to)}" if rule.applies_to else ""

    if rule.target_type == RULE_TARGET_TYPE_MAC and rule.target == RULE_TARGET_TAG:
        if rule.target_name:
            return f"{rule.action} internet for {rule.target_name}"
        return f"{rule.action} internet{applicability}"

    display_target = rule.target
    if rule.target_name:
        prettified_target = rule.target.replace(
            _PRETTIFIED_TARGET_SEPARATOR,
            _PRETTIFIED_TARGET_REPLACEMENT,
        )
        target_is_internal_id = rule.target_type in {
            RULE_TARGET_TYPE_NETWORK,
            RULE_TARGET_TYPE_CATEGORY,
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
    status = _STATUS_ENABLED if rule.enabled else _STATUS_DISABLED
    return f"{format_policy_rule_name(rule)} ({status})"


def supports_rule_switch(rule: FirewallaPolicyRule) -> bool:
    """Return whether a persistent existing rule can back an update-only switch."""
    if rule.auto_delete_when_expires is True or rule.is_temporary:
        return False

    if rule.purpose == RULE_PURPOSE_FAMILY:
        return False

    if (
        rule.action == RULE_ACTION_BLOCK
        and rule.target_type == RULE_TARGET_TYPE_MAC
        and rule.target == RULE_TARGET_TAG
    ):
        return True

    if rule.target_type == RULE_TARGET_TYPE_DNS:
        return (
            rule.action in {RULE_ACTION_ALLOW, RULE_ACTION_BLOCK}
            and rule.purpose is None
        )

    if rule.target_type == RULE_TARGET_TYPE_IP:
        return (
            rule.action in {RULE_ACTION_ALLOW, RULE_ACTION_BLOCK}
            and rule.purpose is None
        )

    if rule.target_type == RULE_TARGET_TYPE_REMOTE_PORT:
        return (
            rule.action in {RULE_ACTION_ALLOW, RULE_ACTION_BLOCK}
            and rule.purpose is None
        )

    if rule.target_type == RULE_TARGET_TYPE_NETWORK:
        return (
            rule.action in {RULE_ACTION_ALLOW, RULE_ACTION_BLOCK}
            and rule.purpose is None
            and rule.target_name is not None
        )

    if rule.target_type == RULE_TARGET_TYPE_CATEGORY:
        return (
            rule.action in {RULE_ACTION_ALLOW, RULE_ACTION_BLOCK}
            and rule.purpose is None
        )

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
        source_rule_id = data.get(_TEMPLATE_DATA_SOURCE_RULE_ID_KEY)
        name = data.get(_TEMPLATE_DATA_NAME_KEY)
        action = data.get(_TEMPLATE_DATA_ACTION_KEY)
        target = data.get(_TEMPLATE_DATA_TARGET_KEY)
        target_type = data.get(_TEMPLATE_DATA_TARGET_TYPE_KEY)
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

        raw_scope = data.get(_TEMPLATE_DATA_SCOPE_KEY)
        scope = (
            tuple(item for item in raw_scope if isinstance(item, str) and item)
            if isinstance(raw_scope, list)
            else ()
        )
        raw_tag_refs = data.get(_TEMPLATE_DATA_TAG_REFS_KEY)
        tag_refs = (
            tuple(item for item in raw_tag_refs if isinstance(item, str) and item)
            if isinstance(raw_tag_refs, list)
            else ()
        )
        dnsmasq_only = data.get(_TEMPLATE_DATA_DNSMASQ_ONLY_KEY)
        if dnsmasq_only is not None and not isinstance(dnsmasq_only, bool):
            dnsmasq_only = None
        use_bf = data.get(_TEMPLATE_DATA_USE_BF_KEY)

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

    def to_dict(self) -> FirewallaRuleTemplateDict:
        """Serialize the template for config entry option storage."""
        return {
            _TEMPLATE_DATA_SOURCE_RULE_ID_KEY: self.source_rule_id,
            _TEMPLATE_DATA_NAME_KEY: self.name,
            _TEMPLATE_DATA_ACTION_KEY: self.action,
            _TEMPLATE_DATA_TARGET_KEY: self.target,
            _TEMPLATE_DATA_TARGET_TYPE_KEY: self.target_type,
            _TEMPLATE_DATA_SCOPE_KEY: list(self.scope),
            _TEMPLATE_DATA_TAG_REFS_KEY: list(self.tag_refs),
            _TEMPLATE_DATA_DNSMASQ_ONLY_KEY: self.dnsmasq_only,
            _TEMPLATE_DATA_USE_BF_KEY: self.use_bf,
        }

    def build_create_value(self, *, updated_time: float) -> FirewallaRuleCreatePayload:
        """Build the confirmed persistent create payload for this template."""
        payload: FirewallaRuleCreatePayload = {
            _CREATE_PAYLOAD_ACTION_KEY: self.action,
            _CREATE_PAYLOAD_APP_TIME_USAGE_KEY: {},
            _CREATE_PAYLOAD_DISTURB_LEVEL_KEY: "",
            _CREATE_PAYLOAD_DISTURB_METHOD_KEY: {},
            _CREATE_PAYLOAD_DURATION_KEY: "",
            _CREATE_PAYLOAD_SCOPE_KEY: list(self.scope),
            _CREATE_PAYLOAD_TARGET_KEY: self.target,
            _CREATE_PAYLOAD_TRUST_KEY: "",
            _CREATE_PAYLOAD_TYPE_KEY: self.target_type,
            _CREATE_PAYLOAD_UPDATED_TIME_KEY: updated_time,
            _CREATE_PAYLOAD_USE_BF_KEY: self.use_bf,
        }
        if self.tag_refs:
            payload[_CREATE_PAYLOAD_TAG_KEY] = list(self.tag_refs)
        if self.dnsmasq_only is not None:
            payload[_CREATE_PAYLOAD_DNSMASQ_ONLY_KEY] = self.dnsmasq_only
        return payload
