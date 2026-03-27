"""Typed models for Firewalla Local."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Final, TypedDict

from cronsim import CronSim, CronSimError

from .const import (
    RULE_ACTION_ALLOW,
    RULE_ACTION_BLOCK,
    RULE_ACTION_DISTURB,
    RULE_ACTION_QOS,
    RULE_PURPOSE_DAP,
    RULE_PURPOSE_FAMILY,
    RULE_PURPOSE_FIREWALL,
    RULE_PURPOSE_PORT_FORWARDING,
    RULE_STATE_REASON_DISABLED,
    RULE_STATE_REASON_ENABLED,
    RULE_STATE_REASON_OFF_SCHEDULE,
    RULE_STATE_REASON_ON_SCHEDULE,
    RULE_STATE_REASON_PAUSED,
    RULE_STATE_REASON_TIME_LIMIT_ACTIVE,
    RULE_STATE_REASON_TIME_LIMIT_REACHED,
    RULE_TARGET_TAG,
    RULE_TARGET_TYPE_CATEGORY,
    RULE_TARGET_TYPE_MAC,
    RULE_TARGET_TYPE_NETWORK,
)

_RAW_UPDATE_IDLE_TS_KEY: Final = "idleTs"
_RAW_UPDATE_NOTES_KEY: Final = "notes"
_RAW_UPDATE_CUSTOM_NAME_KEY: Final = "_name"
_RAW_UPDATE_CRON_TIME_KEY: Final = "cronTime"
_RAW_UPDATE_APP_TIME_USAGE_KEY: Final = "appTimeUsage"
_RAW_UPDATE_APP_TIME_USED_KEY: Final = "appTimeUsed"
_RAW_UPDATE_LOCAL_PORT_KEY: Final = "localPort"
_RAW_UPDATE_PROTOCOL_KEY: Final = "protocol"
_RAW_UPDATE_TRUST_KEY: Final = "trust"
_RAW_UPDATE_USE_BF_KEY: Final = "useBf"
_RAW_UPDATE_UPNP_KEY: Final = "upnp"
_RAW_UPDATE_QDISC_KEY: Final = "qdisc"
_RAW_UPDATE_RATE_LIMIT_KEY: Final = "rateLimit"
_RAW_UPDATE_TRAFFIC_DIRECTION_KEY: Final = "trafficDirection"
_RAW_UPDATE_APP_NAME_KEY: Final = "app_name"
_RAW_UPDATE_APP_UID_KEY: Final = "app_uid"
_RAW_UPDATE_DISTURB_LEVEL_KEY: Final = "disturbLevel"
_RAW_UPDATE_DISTURB_METHOD_KEY: Final = "disturbMethod"
_RAW_UPDATE_DURATION_KEY: Final = "duration"
_RAW_UPDATE_AUTO_DELETE_WHEN_EXPIRES_KEY: Final = "autoDeleteWhenExpires"
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
_WEEKDAY_LABELS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_WEEKDAY_ORDER: Final = {
    weekday: index for index, weekday in enumerate(_WEEKDAY_LABELS)
}
_SUPPORTED_SWITCH_RULE_ACTIONS: Final = frozenset(
    {
        RULE_ACTION_ALLOW,
        RULE_ACTION_BLOCK,
        RULE_ACTION_DISTURB,
        RULE_ACTION_QOS,
    }
)
_SUPPORTED_SWITCH_RULE_PURPOSES: Final = frozenset({None, RULE_PURPOSE_PORT_FORWARDING})
_EXCLUDED_SWITCH_RULE_PURPOSES: Final = frozenset(
    {RULE_PURPOSE_DAP, RULE_PURPOSE_FAMILY, RULE_PURPOSE_FIREWALL}
)


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


def _normalized_optional_string(value: object) -> str | None:
    """Return a stripped string when one is present."""
    if not isinstance(value, str):
        return None
    stripped_value = value.strip()
    return stripped_value or None


def _normalized_optional_bool(value: object) -> bool | None:
    """Return a normalized boolean when Firewalla exposes one."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        stripped_value = value.strip().casefold()
        if stripped_value == "true":
            return True
        if stripped_value == "false":
            return False
    return None


def _normalized_metadata_value(value: object) -> object | None:
    """Return a JSON-like metadata value when it is safe to expose."""
    if isinstance(value, str):
        return _normalized_optional_string(value)
    if isinstance(value, (bool, int, float, dict, list)):
        return value
    return None


def _normalized_optional_dict(value: object) -> dict[str, object] | None:
    """Return a dictionary payload when the value is a mapping-like dict."""
    if not isinstance(value, dict):
        return None

    normalized: dict[str, object] = {}
    for key, nested_value in value.items():
        if not isinstance(key, str):
            continue
        if (normalized_value := _normalized_metadata_value(nested_value)) is None:
            continue
        normalized[key] = normalized_value

    return normalized or None


def _build_cron_sim(
    expression: str,
    reference_time: datetime,
    *,
    reverse: bool = False,
) -> CronSim | None:
    """Return a cron iterator for one Firewalla schedule expression."""
    try:
        return CronSim(expression, reference_time, reverse=reverse)
    except CronSimError:
        return None


def _reference_datetime(
    reference_ts: float | None,
    time_zone: tzinfo | None,
) -> datetime:
    """Return the schedule reference time in the requested timezone."""
    seed_ts = time.time() if reference_ts is None else reference_ts
    return datetime.fromtimestamp(seed_ts, time_zone or UTC)


@dataclass(slots=True)
class FirewallaSystemInfo:
    """Basic system information for a Firewalla appliance."""

    host: str
    name: str
    model: str | None
    serial_number: str | None
    software_version: str | None


@dataclass(slots=True, frozen=True)
class FirewallaApplianceIdentityInput:
    """Protocol-facing appliance identity input extracted from one payload."""

    host: str
    group_name: str | None
    device_name: str | None
    model: str | None
    serial_number: str | None
    software_version: str | None


@dataclass(slots=True, frozen=True)
class FirewallaDiskUsageInput:
    """Protocol-facing disk usage input for one system mount."""

    mount: str
    capacity_ratio: float | None
    used_bytes: float | None
    size_bytes: float | None


@dataclass(slots=True, frozen=True)
class FirewallaApplianceRuntimeInput:
    """Protocol-facing appliance runtime input extracted from one payload."""

    booting_complete: bool | None = None
    cloud_connected: bool | None = None
    ddns: str | None = None
    firmware_release_type: str | None = None
    public_ip: str | None = None
    public_ips: dict[str, str] | None = None
    cpu_usage_1m: float | None = None
    memory_usage_ratio: float | None = None
    total_memory_mb: float | None = None
    uptime_seconds: int | None = None
    disk_usages: tuple[FirewallaDiskUsageInput, ...] = ()


@dataclass(slots=True)
class FirewallaSystemStatus:
    """Normalized system-status state for the Firewalla appliance."""

    booting_complete: bool | None = None
    cloud_connected: bool | None = None
    ddns: str | None = None
    firmware_release_type: str | None = None
    wan_ip: str | None = None
    wan_ips: dict[str, str] | None = None
    cpu_usage_1m: float | None = None
    memory_usage_percent: float | None = None
    memory_free_mb: float | None = None
    uptime_seconds: int | None = None
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
class FirewallaSpeedTestRecord:
    """Protocol-facing speed-test record extracted from one payload item."""

    tested_at_timestamp: float | None
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
    success: bool | None
    vendor: str | None


@dataclass(slots=True, frozen=True)
class FirewallaHostVpnClient:
    """Minimal VPN client reference carried on one normalized host."""

    profile_id: str | None = None
    state: bool | None = None


@dataclass(slots=True, frozen=True)
class FirewallaHostRuntime:
    """Minimal normalized host inventory used for watched-device surfaces."""

    mac: str
    display_name: str
    fallback_name: str | None
    ip_address: str | None
    group_name: str | None
    network_name: str | None
    connection_type: str | None
    last_active: float | None
    download_bytes: int | None
    upload_bytes: int | None
    stale: bool | None
    vpn_client: FirewallaHostVpnClient | None = None
    group_ids: tuple[str, ...] = ()
    user_ids: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class FirewallaUserAppUsage:
    """Normalized per-app usage bucket for one Firewalla user."""

    app_id: str
    category: str | None
    total_minutes: int
    unique_minutes: int


@dataclass(slots=True, frozen=True)
class FirewallaUserRuntime:
    """Normalized user usage extracted from the local runtime payload."""

    user_id: str
    name: str
    affiliated_group_id: str | None
    affiliated_group_name: str | None
    total_minutes_today: int | None
    unique_minutes_today: int | None
    app_usage_today: tuple[FirewallaUserAppUsage, ...] = ()


@dataclass(slots=True, frozen=True)
class FirewallaWatchedUser:
    """Manager-owned watched-user view with resolved associations."""

    user_id: str
    name: str
    affiliated_group_name: str | None
    total_minutes_today: int | None
    unique_minutes_today: int | None
    app_usage_today: tuple[FirewallaUserAppUsage, ...]
    associated_host_names: tuple[str, ...]
    associated_host_macs: tuple[str, ...]
    last_active: float | None


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
    def custom_name(self) -> str | None:
        """Return the user-defined custom name carried on the live rule payload."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_CUSTOM_NAME_KEY)
        )

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

    @property
    def active_time_schedule(self) -> str | None:
        """Return the active-time schedule expression, if the rule carries one."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_CRON_TIME_KEY)
        )

    @property
    def schedule_start_cron(self) -> str | None:
        """Return the user-facing schedule start cron expression."""
        return self.active_time_schedule

    @property
    def app_time_period(self) -> str | None:
        """Return the app-time period expression, if the rule carries one."""
        raw_usage = self.raw_update_payload.get(_RAW_UPDATE_APP_TIME_USAGE_KEY)
        if not isinstance(raw_usage, dict):
            return None
        raw_period = raw_usage.get("period")
        if not isinstance(raw_period, str):
            return None
        stripped_period = raw_period.strip()
        return stripped_period or None

    @property
    def local_port(self) -> str | None:
        """Return the local port carried on the live rule payload, if any."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_LOCAL_PORT_KEY)
        )

    @property
    def protocol(self) -> str | None:
        """Return the protocol carried on the live rule payload, if any."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_PROTOCOL_KEY)
        )

    @property
    def trust(self) -> bool | None:
        """Return the normalized trust flag carried on the live rule payload."""
        return _normalized_optional_bool(
            self.raw_update_payload.get(_RAW_UPDATE_TRUST_KEY)
        )

    @property
    def use_bf(self) -> bool | None:
        """Return the normalized useBf flag carried on the live rule payload."""
        return _normalized_optional_bool(
            self.raw_update_payload.get(_RAW_UPDATE_USE_BF_KEY)
        )

    @property
    def upnp(self) -> bool | None:
        """Return the normalized UPnP flag carried on the live rule payload."""
        return _normalized_optional_bool(
            self.raw_update_payload.get(_RAW_UPDATE_UPNP_KEY)
        )

    @property
    def qdisc(self) -> str | None:
        """Return the QoS queueing discipline carried on the live rule payload."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_QDISC_KEY)
        )

    @property
    def rate_limit(self) -> object | None:
        """Return the rate-limit metadata carried on the live rule payload."""
        return _normalized_metadata_value(
            self.raw_update_payload.get(_RAW_UPDATE_RATE_LIMIT_KEY)
        )

    @property
    def traffic_direction(self) -> str | None:
        """Return the traffic-direction metadata carried on the live rule payload."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_TRAFFIC_DIRECTION_KEY)
        )

    @property
    def app_name(self) -> str | None:
        """Return the app name carried on the live rule payload, if any."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_APP_NAME_KEY)
        )

    @property
    def app_uid(self) -> str | None:
        """Return the app UID carried on the live rule payload, if any."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_APP_UID_KEY)
        )

    @property
    def disturb_level(self) -> str | None:
        """Return the disturb level carried on the live rule payload, if any."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_DISTURB_LEVEL_KEY)
        )

    @property
    def disturb_method(self) -> dict[str, object] | None:
        """Return the disturb-method payload carried on the live rule payload."""
        return _normalized_optional_dict(
            self.raw_update_payload.get(_RAW_UPDATE_DISTURB_METHOD_KEY)
        )

    @property
    def duration(self) -> str | None:
        """Return the duration carried on the live rule payload, if any."""
        return _normalized_optional_string(
            self.raw_update_payload.get(_RAW_UPDATE_DURATION_KEY)
        )

    @property
    def schedule_duration(self) -> int | None:
        """Return the schedule duration in seconds, when the rule carries one."""
        raw_duration = self.duration
        if raw_duration is None or not raw_duration.isdigit():
            return None
        return int(raw_duration)

    @property
    def auto_delete_when_expires_raw(self) -> bool | None:
        """Return the raw auto-delete flag when Firewalla carries a live variant."""
        return _normalized_optional_bool(
            self.raw_update_payload.get(_RAW_UPDATE_AUTO_DELETE_WHEN_EXPIRES_KEY)
        )

    @property
    def app_time_quota(self) -> int | None:
        """Return the configured app-time quota, if the rule carries one."""
        raw_usage = self.raw_update_payload.get(_RAW_UPDATE_APP_TIME_USAGE_KEY)
        if not isinstance(raw_usage, dict):
            return None
        raw_quota = raw_usage.get("quota")
        if isinstance(raw_quota, bool):
            return None
        if isinstance(raw_quota, int):
            return raw_quota
        if isinstance(raw_quota, float):
            return int(raw_quota)
        if isinstance(raw_quota, str):
            stripped_quota = raw_quota.strip()
            if stripped_quota.isdigit():
                return int(stripped_quota)
        return None

    @property
    def app_time_used(self) -> int | None:
        """Return the used app-time value, if the rule carries one."""
        raw_used = self.raw_update_payload.get(_RAW_UPDATE_APP_TIME_USED_KEY)
        if isinstance(raw_used, bool):
            return None
        if isinstance(raw_used, int):
            return raw_used
        if isinstance(raw_used, float):
            return int(raw_used)
        if isinstance(raw_used, str):
            stripped_used = raw_used.strip()
            if stripped_used.isdigit():
                return int(stripped_used)
        return None

    @property
    def time_limit_period_cron(self) -> str | None:
        """Return the user-facing time-limit period cron expression."""
        return self.app_time_period

    @property
    def time_limit_quota(self) -> int | None:
        """Return the configured user-facing time-limit quota."""
        return self.app_time_quota

    @property
    def time_limit_used(self) -> int | None:
        """Return the used user-facing time-limit value."""
        return self.app_time_used

    def schedule_days(
        self,
        reference_ts: float | None = None,
        time_zone: tzinfo | None = None,
    ) -> tuple[str, ...] | None:
        """Return weekday labels inferred from the active schedule."""
        if (schedule := self.schedule_start_cron) is None:
            return None

        cron = _build_cron_sim(schedule, _reference_datetime(reference_ts, time_zone))
        if cron is None:
            return None

        days: list[str] = []
        seen_days: set[str] = set()
        for _ in range(14):
            next_run = next(cron)
            weekday = _WEEKDAY_LABELS[next_run.weekday()]
            if weekday in seen_days:
                continue
            seen_days.add(weekday)
            days.append(weekday)
            if len(seen_days) == len(_WEEKDAY_LABELS):
                break

        if not days:
            return None

        return tuple(sorted(days, key=_WEEKDAY_ORDER.__getitem__))

    def schedule_next_start(
        self,
        reference_ts: float | None = None,
        time_zone: tzinfo | None = None,
    ) -> datetime | None:
        """Return the next scheduled start time, if one can be derived."""
        if (schedule := self.schedule_start_cron) is None:
            return None

        cron = _build_cron_sim(schedule, _reference_datetime(reference_ts, time_zone))
        if cron is None:
            return None
        return next(cron)

    def schedule_window(
        self,
        reference_ts: float | None = None,
        time_zone: tzinfo | None = None,
    ) -> tuple[datetime, datetime] | None:
        """Return the current or next schedule window for the rule."""
        if (schedule := self.schedule_start_cron) is None:
            return None
        if (duration := self.schedule_duration) is None:
            return None

        now = _reference_datetime(reference_ts, time_zone)
        previous_cron = _build_cron_sim(
            schedule,
            now + timedelta(seconds=1),
            reverse=True,
        )
        next_cron = _build_cron_sim(schedule, now)
        if previous_cron is None or next_cron is None:
            return None

        previous_start = next(previous_cron)
        previous_end = previous_start + timedelta(seconds=duration)
        if previous_start <= now < previous_end:
            return previous_start, previous_end

        next_start = next(next_cron)
        return next_start, next_start + timedelta(seconds=duration)

    def current_state_reason(
        self,
        reference_ts: float | None = None,
        time_zone: tzinfo | None = None,
    ) -> str:
        """Return a compact user-facing explanation for the rule's current state."""
        if self.is_paused:
            return RULE_STATE_REASON_PAUSED

        if (
            self.time_limit_quota is not None
            and self.time_limit_used is not None
            and self.time_limit_used >= self.time_limit_quota
        ):
            return RULE_STATE_REASON_TIME_LIMIT_REACHED

        if self.schedule_start_cron is not None and self.schedule_duration is not None:
            window = self.schedule_window(reference_ts, time_zone)
            if window is not None:
                now = _reference_datetime(reference_ts, time_zone)
                if window[0] <= now < window[1]:
                    return RULE_STATE_REASON_ON_SCHEDULE
                return RULE_STATE_REASON_OFF_SCHEDULE

        if self.time_limit_quota is not None:
            return RULE_STATE_REASON_TIME_LIMIT_ACTIVE

        if self.enabled:
            return RULE_STATE_REASON_ENABLED

        return RULE_STATE_REASON_DISABLED


@dataclass(slots=True)
class FirewallaRuntimeSnapshot:
    """Coordinator-ready runtime snapshot fetched from the local API."""

    appliance_identity: FirewallaApplianceIdentityInput
    appliance_runtime: FirewallaApplianceRuntimeInput
    policy_rules: tuple[FirewallaPolicyRule, ...]
    exception_rule_count: int
    hosts: tuple[FirewallaHostRuntime, ...] = ()
    users: tuple[FirewallaUserRuntime, ...] = ()
    speed_test_results: tuple[FirewallaSpeedTestRecord, ...] = ()


def format_policy_rule_name(rule: FirewallaPolicyRule) -> str:
    """Build a readable state-free name for one normalized policy rule."""
    if rule.custom_name is not None:
        return rule.custom_name

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
    if rule.is_temporary:
        return False

    if rule.action not in _SUPPORTED_SWITCH_RULE_ACTIONS:
        return False

    if rule.purpose in _EXCLUDED_SWITCH_RULE_PURPOSES:
        return False

    return rule.purpose in _SUPPORTED_SWITCH_RULE_PURPOSES


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
