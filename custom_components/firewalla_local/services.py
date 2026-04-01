"""Home Assistant service handling for Firewalla Local."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, tzinfo
from typing import cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonObjectType, JsonValueType

from .api import FirewallaApiError
from .const import (
    DOMAIN,
    LOGGER,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIG_ENTRY_NAME,
    SERVICE_FIELD_CURRENT_PERIODS,
    SERVICE_FIELD_DETAIL,
    SERVICE_FIELD_HISTORY_COUNT,
    SERVICE_FIELD_HISTORY_PERIOD,
    SERVICE_FIELD_INCLUDE,
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_NETWORK_NAME,
    SERVICE_FIELD_NETWORK_UUID,
    SERVICE_FIELD_OFFSET,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_FIELD_SECTIONS,
    SERVICE_FIELD_TOP_N,
    SERVICE_FIELD_USAGE_HISTORY_APP_IDS,
    SERVICE_FIELD_USAGE_HISTORY_BEGIN,
    SERVICE_FIELD_USAGE_HISTORY_END,
    SERVICE_FIELD_USAGE_HISTORY_GRANULARITY,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_FIELD_WINDOW,
    SERVICE_GET_NETWORK_SEGMENT_REPORT,
    SERVICE_GET_NETWORK_SEGMENT_USAGE,
    SERVICE_GET_RUNTIME_INVENTORY,
    SERVICE_GET_SPEED_TEST_RESULTS,
    SERVICE_GET_TIME_USAGE_REPORT,
    SERVICE_GET_WAN_DATA_USAGE,
    SERVICE_GET_WAN_EVENTS,
    SERVICE_PAUSE_RULE,
    SERVICE_RESUME_RULE,
    SERVICE_RUN_INTERNET_SPEED_TEST,
    TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_AMBIGUOUS,
    TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_NOT_FOUND,
    TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_FOUND,
    TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_LOADED,
    TRANS_KEY_EXCEPTION_INVALID_DURATION,
    TRANS_KEY_EXCEPTION_MULTIPLE_ENTRIES_LOADED,
    TRANS_KEY_EXCEPTION_NETWORK_NAME_AMBIGUOUS,
    TRANS_KEY_EXCEPTION_NETWORK_NOT_FOUND,
    TRANS_KEY_EXCEPTION_NETWORK_REQUIRED,
    TRANS_KEY_EXCEPTION_NETWORK_SELECTOR_CONFLICT,
    TRANS_KEY_EXCEPTION_NETWORK_USAGE_WINDOW_REQUIRED,
    TRANS_KEY_EXCEPTION_PAUSE_RULE_TIMING_CONFLICT,
    TRANS_KEY_EXCEPTION_RESUME_AT_IN_PAST,
    TRANS_KEY_EXCEPTION_RULE_TARGET_NOT_FOUND,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NAME_AMBIGUOUS,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NOT_FOUND,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_REQUIRED,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_SELECTOR_CONFLICT,
    TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_END_BEFORE_BEGIN,
    TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_AMBIGUOUS,
    TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_NOT_FOUND,
    TRANS_KEY_EXCEPTION_WAN_DATA_USAGE_HISTORY_PERIOD_REQUIRED,
    TRANS_KEY_EXCEPTION_WRONG_INTEGRATION_ENTRY,
    TRANS_PLACEHOLDER_DURATION,
    TRANS_PLACEHOLDER_NETWORK_NAME,
    TRANS_PLACEHOLDER_NETWORK_UUID,
    TRANS_PLACEHOLDER_RULE_TARGET,
    TRANS_PLACEHOLDER_SCOPE_KIND,
    TRANS_PLACEHOLDER_SCOPE_TARGET,
    TRANS_PLACEHOLDER_WAN_NAME,
    TRANS_PLACEHOLDER_WAN_UUID,
)
from .coordinator import FirewallaConfigEntry
from .models import (
    FirewallaGroupRuntime,
    FirewallaNetworkDhcpConfig,
    FirewallaNetworkHostActions,
    FirewallaNetworkHostDetail,
    FirewallaNetworkHostIpAssignment,
    FirewallaNetworkHostNotifications,
    FirewallaNetworkHostRanking,
    FirewallaNetworkHostTotals,
    FirewallaNetworkMetricSample,
    FirewallaNetworkMetricSeries,
    FirewallaNetworkSegment,
    FirewallaNetworkSegmentView,
    FirewallaNetworkUsageBucket,
    FirewallaReportProvenance,
    FirewallaReportTarget,
    FirewallaReportTimeBasis,
    FirewallaReportWarning,
    FirewallaSpeedTestResult,
    FirewallaUsageHistoryDeviceUsage,
    FirewallaUsageHistoryEntry,
    FirewallaUsageHistoryInterval,
    FirewallaUsageHistoryMetric,
    FirewallaUsageHistorySlot,
    FirewallaUsageHistoryTarget,
    FirewallaUsageHistoryView,
    FirewallaWanDataUsage,
    FirewallaWanDataUsagePeriod,
    FirewallaWanDataUsageReport,
    FirewallaWanDataUsageRow,
    FirewallaWanEvent,
    FirewallaWanEventFailure,
    FirewallaWanEventStatus,
    FirewallaWanInterface,
)
from .utils.duration import parse_duration_to_seconds

_TIME_USAGE_REPORT_ALL_SECTIONS = (
    "internet",
    "app_totals",
    "apps",
    "categories",
)
_TIME_USAGE_REPORT_SUMMARY_SECTIONS = (
    "internet",
    "app_totals",
)

GET_RUNTIME_INVENTORY_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

GET_NETWORK_SEGMENT_REPORT_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_NETWORK_UUID): cv.string,
        vol.Optional(SERVICE_FIELD_NETWORK_NAME): cv.string,
        vol.Optional(SERVICE_FIELD_REFRESH, default=True): cv.boolean,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

GET_NETWORK_SEGMENT_USAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_NETWORK_UUID): cv.string,
        vol.Optional(SERVICE_FIELD_NETWORK_NAME): cv.string,
        vol.Optional(SERVICE_FIELD_WINDOW): vol.In(
            (
                "last_60_minutes",
                "last_24_hours",
                "last_30_days",
                "last_12_months",
            )
        ),
        vol.Optional(SERVICE_FIELD_TOP_N, default=5): cv.positive_int,
        vol.Optional(SERVICE_FIELD_INCLUDE): vol.All(
            cv.ensure_list_csv,
            [vol.In(("series",))],
        ),
        vol.Optional(SERVICE_FIELD_REFRESH, default=True): cv.boolean,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

PAUSE_RULE_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_FIELD_RULE_TARGET): cv.string,
        vol.Optional(SERVICE_FIELD_RULE_DURATION): cv.string,
        vol.Optional(SERVICE_FIELD_RULE_RESUME_AT): cv.datetime,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

RESUME_RULE_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_FIELD_RULE_TARGET): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

RUN_INTERNET_SPEED_TEST_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_WAN_UUID): cv.string,
        vol.Optional(SERVICE_FIELD_WAN_NAME): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

GET_SPEED_TEST_RESULTS_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_WAN_UUID): cv.string,
        vol.Optional(SERVICE_FIELD_WAN_NAME): cv.string,
        vol.Optional(SERVICE_FIELD_LIMIT, default=1): cv.positive_int,
        vol.Optional(SERVICE_FIELD_REFRESH, default=True): cv.boolean,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

GET_TIME_USAGE_REPORT_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND): vol.In(
            ("device", "group", "user")
        ),
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET): cv.string,
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_BEGIN): cv.datetime,
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_END): cv.datetime,
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_GRANULARITY): vol.In(("day", "hour")),
        vol.Optional(SERVICE_FIELD_SECTIONS): vol.All(
            cv.ensure_list_csv,
            [vol.In(_TIME_USAGE_REPORT_ALL_SECTIONS)],
        ),
        vol.Optional(SERVICE_FIELD_INCLUDE): vol.All(
            cv.ensure_list_csv,
            [vol.In(("intervals",))],
        ),
        vol.Optional(SERVICE_FIELD_DETAIL, default="standard"): vol.In(
            ("summary", "standard")
        ),
        vol.Optional(SERVICE_FIELD_USAGE_HISTORY_APP_IDS): vol.All(
            cv.ensure_list_csv,
            [cv.string],
        ),
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

GET_WAN_DATA_USAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_WAN_UUID): cv.string,
        vol.Optional(SERVICE_FIELD_WAN_NAME): cv.string,
        vol.Optional(SERVICE_FIELD_INCLUDE): vol.All(
            cv.ensure_list_csv,
            [vol.In(("history", "subperiods"))],
        ),
        vol.Optional(SERVICE_FIELD_CURRENT_PERIODS): vol.All(
            cv.ensure_list_csv,
            [vol.In(("month", "week", "day"))],
        ),
        vol.Optional(SERVICE_FIELD_HISTORY_PERIOD): vol.In(("month", "week", "day")),
        vol.Optional(
            SERVICE_FIELD_HISTORY_COUNT,
            default=0,
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=366)),
        vol.Optional(SERVICE_FIELD_DETAIL, default="summary"): vol.In(
            ("summary", "full")
        ),
        vol.Optional(SERVICE_FIELD_REFRESH, default=True): cv.boolean,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

GET_WAN_EVENTS_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_WAN_UUID): cv.string,
        vol.Optional(SERVICE_FIELD_WAN_NAME): cv.string,
        vol.Optional(SERVICE_FIELD_LIMIT, default=100): cv.positive_int,
        vol.Optional(SERVICE_FIELD_OFFSET, default=0): cv.positive_int,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

_USAGE_HISTORY_REQUEST_SCOPE_HOST = "host"
_USAGE_HISTORY_REQUEST_SCOPE_TAG = "tag"


def _get_loaded_entry(
    hass: HomeAssistant,
    *,
    entry_id: str | None,
    entry_name: str | None,
) -> FirewallaConfigEntry:
    """Return a loaded Firewalla config entry or raise a validation error."""
    loaded_entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.runtime_data is not None
    ]

    if entry_id:
        if not (entry := hass.config_entries.async_get_entry(entry_id)):
            raise ServiceValidationError(
                "Config entry not found",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_FOUND,
            )
        if entry.domain != DOMAIN:
            raise ServiceValidationError(
                "Config entry does not belong to Firewalla Local",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_WRONG_INTEGRATION_ENTRY,
            )
        if entry.runtime_data is None:
            raise ServiceValidationError(
                "Config entry is not loaded",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_LOADED,
            )
        return cast(FirewallaConfigEntry, entry)

    if entry_name:
        matching_entries = [
            entry for entry in loaded_entries if entry.title == entry_name
        ]
        if not matching_entries:
            raise ServiceValidationError(
                "Config entry name not found",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_NOT_FOUND,
            )
        if len(matching_entries) > 1:
            raise ServiceValidationError(
                "Config entry name is ambiguous; use config_entry_id",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_AMBIGUOUS,
            )
        return cast(FirewallaConfigEntry, matching_entries[0])

    if len(loaded_entries) == 1:
        return cast(FirewallaConfigEntry, loaded_entries[0])

    raise ServiceValidationError(
        (
            "Multiple Firewalla entries are loaded; "
            "use config_entry_id or config_entry_name"
        ),
        translation_domain=DOMAIN,
        translation_key=TRANS_KEY_EXCEPTION_MULTIPLE_ENTRIES_LOADED,
    )


async def _async_refresh_runtime_state(entry: FirewallaConfigEntry) -> None:
    """Force a fresh runtime refresh before mutating rules."""
    await entry.runtime_data.coordinator.async_request_refresh()


def _serialize_speed_test_result(
    speed_test_result: FirewallaSpeedTestResult,
) -> JsonObjectType:
    """Serialize one shaped speed-test result for service responses."""
    return {
        "tested_at": datetime.fromtimestamp(
            speed_test_result.tested_at_timestamp,
            UTC,
        ).isoformat(),
        "tested_at_timestamp": speed_test_result.tested_at_timestamp,
        "download_mbps": speed_test_result.download_mbps,
        "upload_mbps": speed_test_result.upload_mbps,
        "latency_ms": speed_test_result.latency_ms,
        "jitter_ms": speed_test_result.jitter_ms,
        "packet_loss_percent": speed_test_result.packet_loss_percent,
        "download_megabytes": speed_test_result.download_megabytes,
        "upload_megabytes": speed_test_result.upload_megabytes,
        "isp": speed_test_result.isp,
        "public_ip": speed_test_result.public_ip,
        "server_country": speed_test_result.server_country,
        "server_host": speed_test_result.server_host,
        "server_id": speed_test_result.server_id,
        "server_location": speed_test_result.server_location,
        "server_sponsor": speed_test_result.server_sponsor,
        "manual": speed_test_result.manual,
        "success": speed_test_result.success,
        "vendor": speed_test_result.vendor,
        "wan_uuid": speed_test_result.wan_uuid,
        "wan_name": speed_test_result.wan_name,
    }


def _serialize_wan_interface(wan: FirewallaWanInterface) -> JsonObjectType:
    """Serialize one WAN interface for service responses."""
    return {"uuid": wan.uuid, "name": wan.name}


def _serialize_network_segment(network: FirewallaNetworkSegment) -> JsonObjectType:
    """Serialize one network-segment selector for service responses."""
    return {"uuid": network.uuid, "name": network.name}


def _serialize_unix_timestamp(timestamp: int | None) -> str | None:
    """Serialize one optional Unix timestamp to UTC ISO format."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


def _serialize_local_timestamp(
    timestamp: int | None,
    *,
    time_zone: tzinfo,
) -> str | None:
    """Serialize one optional Unix timestamp to local ISO format."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, UTC).astimezone(time_zone).isoformat()


def _serialize_usage_history_interval(
    interval: FirewallaUsageHistoryInterval,
    *,
    time_zone: tzinfo,
) -> JsonObjectType:
    """Serialize one usage-history interval for service responses."""
    return {
        "time_period": {
            "kind": "interval",
            "start_timestamp": interval.begin_timestamp,
            "start": _serialize_local_timestamp(
                interval.begin_timestamp,
                time_zone=time_zone,
            ),
            "end_timestamp": interval.end_timestamp,
            "end": _serialize_local_timestamp(
                interval.end_timestamp,
                time_zone=time_zone,
            ),
        },
        "duration_seconds": interval.duration_seconds,
        "duration_minutes": interval.duration_minutes,
    }


def _serialize_usage_history_summary(
    *,
    total_minutes: int | None,
    unique_minutes: int | None,
) -> JsonObjectType:
    """Serialize one usage summary section."""
    return {
        "total_minutes": total_minutes,
        "unique_minutes": unique_minutes,
    }


def _serialize_usage_history_device_usage(
    device_usage: FirewallaUsageHistoryDeviceUsage,
    *,
    time_zone: tzinfo,
    include_intervals: bool,
) -> JsonObjectType:
    """Serialize one device-level usage-history breakdown."""
    payload: JsonObjectType = {
        "device_id": device_usage.device_id,
        "device_name": device_usage.device_name,
        "summary": _serialize_usage_history_summary(
            total_minutes=device_usage.total_minutes,
            unique_minutes=device_usage.unique_minutes,
        ),
    }
    if include_intervals and device_usage.intervals:
        payload["intervals"] = [
            _serialize_usage_history_interval(interval, time_zone=time_zone)
            for interval in device_usage.intervals
        ]
    return payload


def _build_time_usage_period_label(
    begin_timestamp: int,
    *,
    granularity: str,
    time_zone: tzinfo,
) -> str:
    """Return a concise local label for one usage-report period."""
    local_begin = datetime.fromtimestamp(begin_timestamp, UTC).astimezone(time_zone)
    if granularity == "day":
        return local_begin.strftime("%Y-%m-%d")
    return local_begin.strftime("%Y-%m-%d %H:00")


def _serialize_usage_history_period(
    slot: FirewallaUsageHistorySlot,
    *,
    query_begin_timestamp: int,
    query_end_timestamp: int,
    granularity: str,
    time_zone: tzinfo,
) -> JsonObjectType:
    """Serialize one primary report period derived from a Firewalla slot."""
    slot_begin_timestamp = slot.timestamp
    slot_end_timestamp = slot.timestamp + (86_400 if granularity == "day" else 3_600)
    begin_timestamp = max(query_begin_timestamp, slot_begin_timestamp)
    end_timestamp = min(query_end_timestamp, slot_end_timestamp)
    return {
        "time_period": {
            "kind": granularity,
            "label": _build_time_usage_period_label(
                slot_begin_timestamp,
                granularity=granularity,
                time_zone=time_zone,
            ),
            "start_timestamp": begin_timestamp,
            "start": _serialize_local_timestamp(
                begin_timestamp,
                time_zone=time_zone,
            ),
            "end_timestamp": end_timestamp,
            "end": _serialize_local_timestamp(
                end_timestamp,
                time_zone=time_zone,
            ),
            "is_partial": (
                begin_timestamp != slot_begin_timestamp
                or end_timestamp != slot_end_timestamp
            ),
            "boundary_source": (
                "query_window"
                if begin_timestamp != slot_begin_timestamp
                or end_timestamp != slot_end_timestamp
                else "firewalla_slot"
            ),
        },
        "usage": _serialize_usage_history_summary(
            total_minutes=slot.total_minutes,
            unique_minutes=slot.unique_minutes,
        ),
    }


def _serialize_usage_history_metric(
    metric: FirewallaUsageHistoryMetric | None,
    *,
    query_begin_timestamp: int,
    query_end_timestamp: int,
    granularity: str,
    time_zone: tzinfo,
    include_intervals: bool,
) -> JsonObjectType | None:
    """Serialize one usage-history metric section."""
    if metric is None:
        return None

    payload: JsonObjectType = {
        "category": metric.category,
        "summary": _serialize_usage_history_summary(
            total_minutes=metric.total_minutes,
            unique_minutes=metric.unique_minutes,
        ),
        "periods": [
            _serialize_usage_history_period(
                slot,
                query_begin_timestamp=query_begin_timestamp,
                query_end_timestamp=query_end_timestamp,
                granularity=granularity,
                time_zone=time_zone,
            )
            for slot in metric.slots
        ],
        "devices": [
            _serialize_usage_history_device_usage(
                device,
                time_zone=time_zone,
                include_intervals=include_intervals,
            )
            for device in metric.devices
        ],
    }
    if not payload["devices"]:
        payload.pop("devices")
    return payload


def _serialize_usage_history_entry(
    entry: FirewallaUsageHistoryEntry,
    *,
    query_begin_timestamp: int,
    query_end_timestamp: int,
    granularity: str,
    time_zone: tzinfo,
    include_intervals: bool,
) -> JsonObjectType:
    """Serialize one named usage-history entry."""
    return {
        "key": entry.key,
        **cast(
            JsonObjectType,
            _serialize_usage_history_metric(
                entry.metric,
                query_begin_timestamp=query_begin_timestamp,
                query_end_timestamp=query_end_timestamp,
                granularity=granularity,
                time_zone=time_zone,
                include_intervals=include_intervals,
            ),
        ),
    }


def _serialize_usage_history_target(
    target: FirewallaUsageHistoryTarget,
) -> JsonObjectType:
    """Serialize resolved usage-history target metadata."""
    return {
        "scope_kind": target.scope_kind,
        "target_id": target.target_id,
        "target_name": target.target_name,
        "request_scope_type": target.request_scope_type,
    }


def _serialize_report_target(target: FirewallaReportTarget) -> JsonObjectType:
    """Serialize one shared report target object."""
    return {
        "kind": target.kind,
        "id": target.id,
        "name": target.name,
    }


def _serialize_report_time_basis(
    time_basis: FirewallaReportTimeBasis,
    *,
    time_zone: tzinfo | None = None,
) -> JsonObjectType:
    """Serialize one shared report time-basis object."""
    payload: JsonObjectType = {
        "kind": time_basis.kind,
        "label": time_basis.label,
        "begin_timestamp": time_basis.begin_timestamp,
        "end_timestamp": time_basis.end_timestamp,
        "anchor_timestamp": time_basis.anchor_timestamp,
        "is_partial": time_basis.is_partial,
        "boundary_source": time_basis.boundary_source,
        "time_zone": time_basis.time_zone,
    }
    if time_zone is not None:
        payload["begin_timestamp_iso"] = _serialize_local_timestamp(
            time_basis.begin_timestamp,
            time_zone=time_zone,
        )
        payload["end_timestamp_iso"] = _serialize_local_timestamp(
            time_basis.end_timestamp,
            time_zone=time_zone,
        )
        payload["anchor_timestamp_iso"] = _serialize_local_timestamp(
            time_basis.anchor_timestamp,
            time_zone=time_zone,
        )
    return payload


def _serialize_report_metadata(
    *,
    applied: JsonObjectType | None = None,
    warnings: tuple[FirewallaReportWarning, ...] = (),
    unavailable_sections: tuple[str, ...] = (),
    provenance: tuple[FirewallaReportProvenance, ...] = (),
) -> JsonObjectType:
    """Serialize shared report metadata."""
    return {
        "applied": applied or {},
        "warnings": [
            {"code": warning.code, "message": warning.message} for warning in warnings
        ],
        "unavailable_sections": list(unavailable_sections),
        "provenance": {
            item.section: {
                "source": item.source,
                "source_field": item.source_field,
                "note": item.note,
            }
            for item in provenance
        },
    }


def _normalize_report_include(
    raw_include: object,
    *,
    allowed: tuple[str, ...],
) -> tuple[str, ...]:
    """Return a stable ordered include tuple limited to allowed values."""
    if raw_include is None:
        return ()

    include: list[str] = []
    for value in cast(list[str], raw_include):
        if value in allowed and value not in include:
            include.append(value)
    return tuple(include)


def _serialize_usage_history_view(
    view: FirewallaUsageHistoryView,
    *,
    time_zone: tzinfo,
    time_zone_name: str,
    detail: str,
    requested_sections: tuple[str, ...],
    applied_sections: tuple[str, ...],
    requested_include: tuple[str, ...],
    applied_include: tuple[str, ...],
) -> JsonObjectType:
    """Serialize one normalized usage-history response in the shared envelope."""
    include_intervals = "intervals" in applied_include
    app_entries = _select_usage_history_entries(
        view.apps,
        requested_keys=view.app_ids,
        drop_zero_only=view.app_ids is None,
    )
    category_entries = _select_usage_history_entries(
        view.categories,
        drop_zero_only=True,
    )
    internet_section = _serialize_usage_history_metric(
        view.internet,
        query_begin_timestamp=view.begin_timestamp,
        query_end_timestamp=view.end_timestamp,
        granularity=view.granularity,
        time_zone=time_zone,
        include_intervals=include_intervals,
    )
    app_totals_section = _serialize_usage_history_metric(
        view.app_totals,
        query_begin_timestamp=view.begin_timestamp,
        query_end_timestamp=view.end_timestamp,
        granularity=view.granularity,
        time_zone=time_zone,
        include_intervals=include_intervals,
    )
    sections: JsonObjectType = {}
    provenance: list[FirewallaReportProvenance] = []
    unavailable_sections: list[str] = []

    if "internet" in applied_sections:
        sections["internet"] = internet_section
        if internet_section is None:
            unavailable_sections.append("internet")
        else:
            provenance.append(
                FirewallaReportProvenance(
                    section="internet",
                    source="direct",
                    source_field="internetTimeUsage",
                    note=(
                        "Primary scoped internet usage comes from the direct "
                        "history payload"
                    ),
                )
            )
    if "app_totals" in applied_sections:
        sections["app_totals"] = app_totals_section
        if app_totals_section is None:
            unavailable_sections.append("app_totals")
        else:
            provenance.append(
                FirewallaReportProvenance(
                    section="app_totals",
                    source="direct",
                    source_field="appTimeUsageTotal",
                    note="Aggregate app totals come from the direct history payload",
                )
            )
    if "apps" in applied_sections:
        sections["apps"] = [
            _serialize_usage_history_entry(
                entry,
                query_begin_timestamp=view.begin_timestamp,
                query_end_timestamp=view.end_timestamp,
                granularity=view.granularity,
                time_zone=time_zone,
                include_intervals=include_intervals,
            )
            for entry in app_entries
        ]
        provenance.append(
            FirewallaReportProvenance(
                section="apps",
                source="direct",
                source_field="appTimeUsage",
                note="Per-app usage sections are ranked by returned usage totals",
            )
        )
    if "categories" in applied_sections:
        sections["categories"] = [
            _serialize_usage_history_entry(
                entry,
                query_begin_timestamp=view.begin_timestamp,
                query_end_timestamp=view.end_timestamp,
                granularity=view.granularity,
                time_zone=time_zone,
                include_intervals=include_intervals,
            )
            for entry in category_entries
        ]
        provenance.append(
            FirewallaReportProvenance(
                section="categories",
                source="direct",
                source_field="categoryTimeUsage",
                note="Per-category usage sections are ranked by returned usage totals",
            )
        )
    if include_intervals and "apps" in applied_sections:
        provenance.append(
            FirewallaReportProvenance(
                section="apps.devices.intervals",
                source="direct",
                source_field="appTimeUsage.*.devices.*.intervals",
                note=(
                    "Interval detail appears only when requested and when "
                    "Firewalla returns device intervals"
                ),
            )
        )

    internet_section_payload = cast(
        JsonObjectType,
        internet_section
        or {
            "summary": _serialize_usage_history_summary(
                total_minutes=None,
                unique_minutes=None,
            ),
            "periods": [],
        },
    )
    internet_summary = cast(JsonObjectType, internet_section_payload["summary"])
    app_totals_summary = (
        cast(JsonObjectType, app_totals_section["summary"])
        if app_totals_section is not None
        else None
    )
    internet_periods = cast(list[JsonValueType], internet_section_payload["periods"])
    return {
        "target": _serialize_report_target(
            FirewallaReportTarget(
                kind=view.target.scope_kind,
                id=view.target.target_id,
                name=view.target.target_name,
            )
        ),
        "query": {
            "detail": detail,
            "sections": list(requested_sections),
            "include": list(requested_include),
            "time_zone": time_zone_name,
            "begin_timestamp": view.begin_timestamp,
            "begin": _serialize_local_timestamp(
                view.begin_timestamp,
                time_zone=time_zone,
            ),
            "end_timestamp": view.end_timestamp,
            "end": _serialize_local_timestamp(
                view.end_timestamp,
                time_zone=time_zone,
            ),
            "granularity": view.granularity,
            "app_ids": list(view.app_ids) if view.app_ids is not None else None,
        },
        "time_basis": _serialize_report_time_basis(
            FirewallaReportTimeBasis(
                kind="custom_range",
                label=f"Requested {view.granularity} usage range",
                begin_timestamp=view.begin_timestamp,
                end_timestamp=view.end_timestamp,
                anchor_timestamp=view.end_timestamp,
                is_partial=False,
                boundary_source="query_window",
                time_zone=time_zone_name,
            ),
            time_zone=time_zone,
        ),
        "summary": {
            "total_minutes": internet_summary["total_minutes"],
            "unique_minutes": internet_summary["unique_minutes"],
            "app_total_minutes": (
                app_totals_summary["total_minutes"]
                if app_totals_summary is not None
                else None
            ),
            "app_count": len(app_entries),
            "category_count": len(category_entries),
            "period_count": len(internet_periods),
        },
        "sections": sections,
        "metadata": _serialize_report_metadata(
            applied={
                "detail": detail,
                "sections": list(applied_sections),
                "include": list(applied_include),
                "request_scope_type": view.target.request_scope_type,
            },
            unavailable_sections=tuple(unavailable_sections),
            provenance=tuple(provenance),
        ),
    }


def _resolve_time_usage_report_inputs(
    call: ServiceCall,
) -> tuple[
    str,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...] | None,
]:
    """Resolve shared detail and include options for time-usage reports."""
    detail = cast(str, call.data[SERVICE_FIELD_DETAIL])
    requested_sections = _normalize_report_include(
        call.data.get(SERVICE_FIELD_SECTIONS),
        allowed=_TIME_USAGE_REPORT_ALL_SECTIONS,
    )
    requested_include = _normalize_report_include(
        call.data.get(SERVICE_FIELD_INCLUDE),
        allowed=("intervals",),
    )

    raw_app_ids = call.data.get(SERVICE_FIELD_USAGE_HISTORY_APP_IDS)
    app_ids = (
        tuple(str(app_id) for app_id in cast(list[str], raw_app_ids))
        if raw_app_ids is not None
        else None
    )
    applied_sections = list(requested_sections)
    if not applied_sections:
        applied_sections = list(
            _TIME_USAGE_REPORT_SUMMARY_SECTIONS
            if detail == "summary"
            else _TIME_USAGE_REPORT_ALL_SECTIONS
        )
    if app_ids and "apps" not in applied_sections:
        applied_sections.append("apps")

    applied_include = list(requested_include)
    return (
        detail,
        requested_sections,
        tuple(applied_sections),
        requested_include,
        tuple(applied_include),
        app_ids,
    )


def _usage_history_metric_has_activity(metric: FirewallaUsageHistoryMetric) -> bool:
    """Return whether a usage-history metric contains meaningful activity."""
    if (metric.total_minutes or 0) > 0 or (metric.unique_minutes or 0) > 0:
        return True
    if any(
        (slot.total_minutes or 0) > 0 or (slot.unique_minutes or 0) > 0
        for slot in metric.slots
    ):
        return True
    if any(
        (device.total_minutes or 0) > 0
        or (device.unique_minutes or 0) > 0
        or bool(device.intervals)
        for device in metric.devices
    ):
        return True
    return bool(metric.intervals)


def _select_usage_history_entries(
    entries: Sequence[FirewallaUsageHistoryEntry],
    *,
    requested_keys: tuple[str, ...] | None = None,
    drop_zero_only: bool = False,
) -> tuple[FirewallaUsageHistoryEntry, ...]:
    """Return user-facing usage-history entries in a stable, useful order."""
    filtered_entries = [
        entry
        for entry in entries
        if not drop_zero_only or _usage_history_metric_has_activity(entry.metric)
    ]
    requested_order = {
        key: index
        for index, key in enumerate(requested_keys or ())
        if key != "internet"
    }
    return tuple(
        sorted(
            filtered_entries,
            key=lambda entry: (
                requested_order.get(entry.key, len(requested_order)),
                -(entry.metric.total_minutes or 0),
                -(entry.metric.unique_minutes or 0),
                entry.key.casefold(),
            ),
        )
    )


def _serialize_wan_data_usage_period(
    period: FirewallaWanDataUsagePeriod,
    *,
    time_zone: tzinfo,
) -> JsonObjectType:
    """Serialize one WAN data-usage time period."""
    return _serialize_report_time_basis(
        FirewallaReportTimeBasis(
            kind=period.kind,
            label=_build_wan_data_usage_label(period, time_zone=time_zone),
            begin_timestamp=period.begin_timestamp,
            end_timestamp=period.end_timestamp,
            anchor_timestamp=period.anchor_timestamp,
            is_partial=period.is_partial,
            boundary_source=period.boundary_source,
        ),
        time_zone=time_zone,
    )


def _build_wan_data_usage_label(
    period: FirewallaWanDataUsagePeriod,
    *,
    time_zone: tzinfo,
) -> str | None:
    """Build a stable user-facing label for one WAN data-usage time period."""
    reference_timestamp = (
        period.begin_timestamp or period.anchor_timestamp or period.end_timestamp
    )
    if reference_timestamp is None:
        return None

    local_time = datetime.fromtimestamp(reference_timestamp, UTC).astimezone(time_zone)
    if period.kind == "month":
        return local_time.strftime("%Y-%m")
    if period.kind == "week" and period.begin_timestamp is not None:
        week_begin = datetime.fromtimestamp(period.begin_timestamp, UTC).astimezone(
            time_zone
        )
        return week_begin.strftime("Week of %Y-%m-%d")
    if period.kind == "day":
        return local_time.strftime("%Y-%m-%d")
    return local_time.isoformat()


def _serialize_wan_data_usage(
    usage: FirewallaWanDataUsage,
) -> JsonObjectType:
    """Serialize normalized WAN data-usage totals."""
    return {
        "download_bytes": usage.download_bytes,
        "upload_bytes": usage.upload_bytes,
        "total_bytes": usage.total_bytes,
    }


def _serialize_wan_data_usage_row(
    row: FirewallaWanDataUsageRow,
    *,
    time_zone: tzinfo,
) -> JsonObjectType:
    """Serialize one WAN data-usage row."""
    return {
        "time_period": _serialize_wan_data_usage_period(
            row.time_period,
            time_zone=time_zone,
        ),
        "usage": _serialize_wan_data_usage(row.usage),
        "detail": row.detail,
        "weeks": [
            _serialize_wan_data_usage_row(week_row, time_zone=time_zone)
            for week_row in row.weeks
        ],
        "days": [
            _serialize_wan_data_usage_row(day_row, time_zone=time_zone)
            for day_row in row.days
        ],
    }


def _serialize_wan_data_usage_report(
    report: FirewallaWanDataUsageReport,
    *,
    time_zone: tzinfo,
) -> JsonObjectType:
    """Serialize one WAN data-usage report."""
    return {
        "target": _serialize_report_target(
            FirewallaReportTarget(
                kind="wan",
                id=report.wan_uuid,
                name=report.wan_name,
            )
        ),
        "summary": {
            "current_periods_present": [
                period
                for period, row in (
                    ("month", report.current_month),
                    ("week", report.current_week),
                    ("day", report.current_day),
                )
                if row is not None
            ],
            "history_counts": {
                "months": len(report.history_months),
                "weeks": len(report.history_weeks),
                "days": len(report.history_days),
            },
        },
        "current": {
            "month": (
                _serialize_wan_data_usage_row(report.current_month, time_zone=time_zone)
                if report.current_month is not None
                else None
            ),
            "week": (
                _serialize_wan_data_usage_row(report.current_week, time_zone=time_zone)
                if report.current_week is not None
                else None
            ),
            "day": (
                _serialize_wan_data_usage_row(report.current_day, time_zone=time_zone)
                if report.current_day is not None
                else None
            ),
        },
        "history": {
            "months": [
                _serialize_wan_data_usage_row(row, time_zone=time_zone)
                for row in report.history_months
            ],
            "weeks": [
                _serialize_wan_data_usage_row(row, time_zone=time_zone)
                for row in report.history_weeks
            ],
            "days": [
                _serialize_wan_data_usage_row(row, time_zone=time_zone)
                for row in report.history_days
            ],
        },
    }


def _serialize_network_metric_sample(
    sample: FirewallaNetworkMetricSample,
) -> JsonObjectType:
    """Serialize one network metric sample for service responses."""
    return {
        "timestamp": sample.timestamp,
        "timestamp_iso": _serialize_unix_timestamp(sample.timestamp),
        "value": sample.value,
    }


def _serialize_network_metric_series(
    series: FirewallaNetworkMetricSeries,
) -> JsonObjectType:
    """Serialize one named network metric series."""
    return {
        "metric": series.metric,
        "samples": [
            _serialize_network_metric_sample(sample) for sample in series.samples
        ],
    }


def _serialize_network_host_totals(
    host: FirewallaNetworkHostTotals,
) -> JsonObjectType:
    """Serialize one per-host network totals row."""
    return {
        "host_id": host.host_id,
        "host_name": host.host_name,
        "ip_address": host.ip_address,
        "conn": host.conn,
        "dns": host.dns,
        "dns_blocked": host.dns_blocked,
        "ip_blocked": host.ip_blocked,
        "ip_denied": host.ip_denied,
        "ntp": host.ntp,
        "download_bytes": host.download_bytes,
        "upload_bytes": host.upload_bytes,
    }


def _serialize_network_host_ranking(
    host: FirewallaNetworkHostRanking,
) -> JsonObjectType:
    """Serialize one derived network host ranking entry."""
    return {
        "host_id": host.host_id,
        "host_name": host.host_name,
        "ip_address": host.ip_address,
        "remote_host": host.remote_host,
        "remote_ip": host.remote_ip,
        "value": host.value,
    }


def _serialize_network_usage_bucket(
    bucket: FirewallaNetworkUsageBucket,
    *,
    time_zone: tzinfo,
) -> JsonObjectType:
    """Serialize one aggregated network usage bucket."""
    return {
        "key": bucket.key,
        "download_bytes": bucket.download_bytes,
        "upload_bytes": bucket.upload_bytes,
        "total_bytes": bucket.download_bytes + bucket.upload_bytes,
        "duration_seconds": round(bucket.duration_seconds, 3),
        "session_count": bucket.session_count,
        "active_device_count": bucket.active_device_count,
        "latest_timestamp": bucket.latest_timestamp,
        "latest": _serialize_local_timestamp(
            bucket.latest_timestamp,
            time_zone=time_zone,
        ),
    }


def _serialize_network_host_ip_assignment(
    assignment: FirewallaNetworkHostIpAssignment | None,
) -> JsonObjectType | None:
    """Serialize one host IP assignment section."""
    if assignment is None:
        return None
    return {
        "mode": assignment.mode,
        "network_uuid": assignment.network_uuid,
        "reserved_ipv4": assignment.reserved_ipv4,
    }


def _serialize_network_host_notifications(
    notifications: FirewallaNetworkHostNotifications | None,
) -> JsonObjectType | None:
    """Serialize one host notification settings section."""
    if notifications is None:
        return None
    return {
        "notify_when_next_online": notifications.notify_when_next_online,
        "notify_when_next_offline": notifications.notify_when_next_offline,
    }


def _serialize_network_host_actions(
    actions: FirewallaNetworkHostActions | None,
) -> JsonObjectType | None:
    """Serialize one host action-affordance section."""
    if actions is None:
        return None
    return {"wake_on_lan_supported": actions.wake_on_lan_supported}


def _serialize_network_host_detail(
    host: FirewallaNetworkHostDetail,
) -> JsonObjectType:
    """Serialize one configuration-oriented host detail row."""
    return {
        "host_id": host.host_id,
        "host_name": host.host_name,
        "ip_address": host.ip_address,
        "dhcp_name": host.dhcp_name,
        "device_type": host.device_type,
        "ip_assignment": _serialize_network_host_ip_assignment(host.ip_assignment),
        "notifications": _serialize_network_host_notifications(host.notifications),
        "actions": _serialize_network_host_actions(host.actions),
    }


def _serialize_network_dhcp_config(
    dhcp: FirewallaNetworkDhcpConfig | None,
) -> JsonObjectType | None:
    """Serialize one DHCP config section for a segment report."""
    if dhcp is None:
        return None
    return {
        "gateway": dhcp.gateway,
        "subnet_mask": dhcp.subnet_mask,
        "lease_seconds": dhcp.lease_seconds,
        "range": {
            "start": dhcp.range_start,
            "end": dhcp.range_end,
        },
        "name_servers": list(dhcp.name_servers),
        "search_domains": list(dhcp.search_domains),
        "extra_options": cast(JsonObjectType | None, dhcp.extra_options),
    }


def _serialize_network_metric_summary(
    series: FirewallaNetworkMetricSeries,
    *,
    time_zone: tzinfo,
) -> JsonObjectType:
    """Serialize the summary metadata for one network metric series."""
    latest_sample = series.samples[-1] if series.samples else None
    latest_timestamp = latest_sample.timestamp if latest_sample is not None else None
    return {
        "sample_count": len(series.samples),
        "total_value": sum(sample.value for sample in series.samples),
        "max_value": max((sample.value for sample in series.samples), default=None),
        "latest_timestamp": latest_timestamp,
        "latest": _serialize_local_timestamp(
            latest_timestamp,
            time_zone=time_zone,
        ),
    }


def _network_host_has_activity(host: FirewallaNetworkHostTotals) -> bool:
    """Return whether a host totals row carries meaningful activity."""
    return any(
        value not in (None, 0)
        for value in (
            host.conn,
            host.dns,
            host.dns_blocked,
            host.ip_blocked,
            host.ip_denied,
            host.ntp,
            host.download_bytes,
            host.upload_bytes,
        )
    )


def _calculate_window_transfer_totals(
    series_list: tuple[FirewallaNetworkMetricSeries, ...],
) -> tuple[int | None, int | None]:
    """Calculate transfer totals from the selected window when available."""
    download_total: int | None = None
    upload_total: int | None = None

    for series in series_list:
        total_value = int(sum(sample.value for sample in series.samples))
        if series.metric == "download":
            download_total = total_value
        elif series.metric == "upload":
            upload_total = total_value

    return download_total, upload_total


def _serialize_network_usage_metric(
    series: FirewallaNetworkMetricSeries,
    *,
    include_samples: bool,
    time_zone: tzinfo,
) -> JsonObjectType:
    """Serialize one usage-oriented network metric section."""
    payload: JsonObjectType = {
        "metric": series.metric,
        "summary": _serialize_network_metric_summary(series, time_zone=time_zone),
    }
    if include_samples:
        payload["samples"] = [
            _serialize_network_metric_sample(sample) for sample in series.samples
        ]
    return payload


def _serialize_network_time_window(
    *,
    series_list: tuple[FirewallaNetworkMetricSeries, ...],
    source: str,
    label: str,
    include_samples: bool,
    time_zone: tzinfo,
) -> JsonObjectType:
    """Serialize one named network usage time window."""
    return {
        "source": source,
        "label": label,
        "metrics": [
            _serialize_network_usage_metric(
                series,
                include_samples=include_samples,
                time_zone=time_zone,
            )
            for series in series_list
        ],
    }


def _resolve_network_segment_usage_window(
    view: FirewallaNetworkSegmentView,
    *,
    window: str,
) -> tuple[str, str, tuple[FirewallaNetworkMetricSeries, ...]]:
    """Resolve the requested public window key to one network metric series set."""
    match window:
        case "last_60_minutes":
            return "last60", "Last 60 minutes", view.last60
        case "last_24_hours":
            return "newLast24", "Last 24 hours", view.new_last24
        case "last_30_days":
            return "last30", "Last 30 days", view.last30
        case "last_12_months":
            return "last12Months", "Last 12 months", view.last12_months
        case _:
            raise ValueError(f"Unsupported network usage window: {window}")


def _build_network_segment_usage_time_basis(
    *,
    series_list: tuple[FirewallaNetworkMetricSeries, ...],
    source: str,
    label: str,
    time_zone_name: str,
) -> FirewallaReportTimeBasis:
    """Build the time basis for one selected network usage window."""
    timestamps = [
        sample.timestamp
        for series in series_list
        for sample in series.samples
        if sample.timestamp is not None
    ]
    begin_timestamp = min(timestamps) if timestamps else None
    end_timestamp = max(timestamps) if timestamps else None
    return FirewallaReportTimeBasis(
        kind="window",
        label=label,
        begin_timestamp=begin_timestamp,
        end_timestamp=end_timestamp,
        anchor_timestamp=end_timestamp,
        is_partial=None,
        boundary_source=source,
        time_zone=time_zone_name,
    )


def _optional_string(value: object) -> str | None:
    """Return a stripped string when one is present."""
    if not isinstance(value, str):
        return None
    stripped_value = value.strip()
    return stripped_value or None


def _optional_bool(value: object) -> bool | None:
    """Return a normalized boolean when one is present."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return None


def _optional_int(value: object) -> int | None:
    """Return one integer when one can be safely derived."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value:
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _string_tuple(value: object) -> tuple[str, ...]:
    """Return a stable tuple of non-empty strings."""
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str) and item)
    return ()


def _normalized_dict(value: object) -> dict[str, object] | None:
    """Return a shallow normalized dictionary when one is present."""
    if not isinstance(value, dict):
        return None

    normalized: dict[str, object] = {}
    for key, nested_value in value.items():
        if not isinstance(key, str):
            continue
        if not isinstance(nested_value, (str, bool, int, float, dict, list)):
            continue
        normalized[key] = nested_value

    return normalized or None


def _resolve_requested_network_required(
    entry: FirewallaConfigEntry,
    *,
    network_uuid: str | None,
    network_name: str | None,
) -> FirewallaNetworkSegment:
    """Resolve one required network selector against runtime metadata."""
    resolved_network = _resolve_requested_network(
        entry,
        network_uuid=network_uuid,
        network_name=network_name,
    )
    if resolved_network is not None:
        return resolved_network

    raise ServiceValidationError(
        "Provide network_uuid or network_name",
        translation_domain=DOMAIN,
        translation_key=TRANS_KEY_EXCEPTION_NETWORK_REQUIRED,
    )


def _build_raw_host_lookup(entry: FirewallaConfigEntry) -> dict[str, dict[str, object]]:
    """Build a raw runtime host lookup keyed by MAC address."""
    raw_hosts = (entry.runtime_data.coordinator.last_init_payload or {}).get("hosts")
    if not isinstance(raw_hosts, list):
        return {}

    host_lookup: dict[str, dict[str, object]] = {}
    for raw_host in raw_hosts:
        if not isinstance(raw_host, dict):
            continue
        if not (host_id := _optional_string(raw_host.get("mac"))):
            continue
        host_lookup[host_id] = raw_host
    return host_lookup


def _build_device_tag_lookup(entry: FirewallaConfigEntry) -> dict[str, str]:
    """Build a device-tag ID to readable name lookup from the init payload."""
    raw_device_tags = (entry.runtime_data.coordinator.last_init_payload or {}).get(
        "deviceTags"
    )
    if not isinstance(raw_device_tags, dict):
        return {}

    tag_lookup: dict[str, str] = {}
    for tag_id, raw_tag in raw_device_tags.items():
        if not isinstance(tag_id, str) or not isinstance(raw_tag, dict):
            continue
        if not (tag_name := _optional_string(raw_tag.get("name"))):
            continue
        tag_lookup[tag_id] = tag_name
    return tag_lookup


def _resolve_host_device_type(
    raw_host: dict[str, object] | None,
    *,
    device_tag_lookup: dict[str, str],
) -> str | None:
    """Resolve one host device type from feedback, detect, or device tags."""
    if raw_host is None:
        return None

    raw_detect = raw_host.get("detect")
    if isinstance(raw_detect, dict):
        raw_feedback = raw_detect.get("feedback")
        if isinstance(raw_feedback, dict) and (
            feedback_type := _optional_string(raw_feedback.get("type"))
        ):
            return feedback_type
        if detect_type := _optional_string(raw_detect.get("type")):
            return detect_type

    raw_device_tags = raw_host.get("deviceTags")
    if isinstance(raw_device_tags, list):
        for tag_id in raw_device_tags:
            if isinstance(tag_id, str) and tag_id in device_tag_lookup:
                return device_tag_lookup[tag_id]

    return None


def _resolve_host_ip_assignment(
    raw_host: dict[str, object] | None,
    *,
    network_uuid: str,
) -> FirewallaNetworkHostIpAssignment | None:
    """Resolve one host IP assignment section for the requested network."""
    if raw_host is None:
        return None

    default_assignment = FirewallaNetworkHostIpAssignment(
        mode="dynamic",
        network_uuid=network_uuid,
    )

    raw_policy = raw_host.get("policy")
    if not isinstance(raw_policy, dict):
        return default_assignment

    raw_ip_allocation = raw_policy.get("ipAllocation")
    if not isinstance(raw_ip_allocation, dict):
        return default_assignment

    raw_allocations = raw_ip_allocation.get("allocations")
    if not isinstance(raw_allocations, dict):
        return default_assignment

    raw_allocation = raw_allocations.get(network_uuid)
    if not isinstance(raw_allocation, dict):
        return default_assignment

    mode = _optional_string(raw_allocation.get("type")) or "dynamic"
    reserved_ipv4 = _optional_string(raw_allocation.get("ipv4"))
    return FirewallaNetworkHostIpAssignment(
        mode=mode,
        network_uuid=network_uuid,
        reserved_ipv4=reserved_ipv4 if mode == "static" else None,
    )


def _resolve_host_notifications(
    raw_host: dict[str, object] | None,
) -> FirewallaNetworkHostNotifications | None:
    """Resolve one host notification settings section."""
    if raw_host is None:
        return None

    raw_policy = raw_host.get("policy")
    if not isinstance(raw_policy, dict):
        return FirewallaNetworkHostNotifications()

    return FirewallaNetworkHostNotifications(
        notify_when_next_online=bool(_optional_bool(raw_policy.get("devicePresence"))),
        notify_when_next_offline=bool(_optional_bool(raw_policy.get("deviceOffline"))),
    )


def _supports_wake_on_lan(host_id: str) -> bool:
    """Return whether one host ID looks like a WOL-targetable MAC address."""
    parts = host_id.split(":")
    if len(parts) != 6:
        return False
    return all(len(part) == 2 for part in parts)


def _build_network_host_detail_rows(
    entry: FirewallaConfigEntry,
    view: FirewallaNetworkSegmentView,
) -> tuple[FirewallaNetworkHostDetail, ...]:
    """Build configuration-oriented host detail rows for one segment report."""
    raw_host_lookup = _build_raw_host_lookup(entry)
    device_tag_lookup = _build_device_tag_lookup(entry)

    return tuple(
        FirewallaNetworkHostDetail(
            host_id=host.host_id,
            host_name=host.host_name,
            ip_address=host.ip_address,
            dhcp_name=(
                _optional_string(raw_host.get("dhcpName"))
                if (raw_host := raw_host_lookup.get(host.host_id)) is not None
                else None
            ),
            device_type=_resolve_host_device_type(
                raw_host_lookup.get(host.host_id),
                device_tag_lookup=device_tag_lookup,
            ),
            ip_assignment=_resolve_host_ip_assignment(
                raw_host_lookup.get(host.host_id),
                network_uuid=view.target.uuid,
            ),
            notifications=_resolve_host_notifications(
                raw_host_lookup.get(host.host_id)
            ),
            actions=FirewallaNetworkHostActions(
                wake_on_lan_supported=_supports_wake_on_lan(host.host_id)
            ),
        )
        for host in view.hosts
    )


def _build_network_dhcp_config(
    entry: FirewallaConfigEntry,
    *,
    interface_name: str | None,
) -> FirewallaNetworkDhcpConfig | None:
    """Build one normalized DHCP config section for the requested interface."""
    if interface_name is None:
        return None

    raw_network_config = (entry.runtime_data.coordinator.last_init_payload or {}).get(
        "networkConfig"
    )
    if not isinstance(raw_network_config, dict):
        return None

    raw_dhcp_by_interface = raw_network_config.get("dhcp")
    if not isinstance(raw_dhcp_by_interface, dict):
        return None

    raw_dhcp = raw_dhcp_by_interface.get(interface_name)
    if not isinstance(raw_dhcp, dict):
        return None

    raw_range = raw_dhcp.get("range")
    range_start = None
    range_end = None
    if isinstance(raw_range, dict):
        range_start = _optional_string(raw_range.get("from"))
        range_end = _optional_string(raw_range.get("to"))

    return FirewallaNetworkDhcpConfig(
        gateway=_optional_string(raw_dhcp.get("gateway")),
        subnet_mask=_optional_string(raw_dhcp.get("subnetMask")),
        lease_seconds=_optional_int(raw_dhcp.get("lease")),
        range_start=range_start,
        range_end=range_end,
        name_servers=_string_tuple(raw_dhcp.get("nameservers")),
        search_domains=_string_tuple(raw_dhcp.get("searchDomain")),
        extra_options=_normalized_dict(raw_dhcp.get("extraOptions")),
    )


def _serialize_network_segment_report(
    entry: FirewallaConfigEntry,
    *,
    view: FirewallaNetworkSegmentView,
    refresh_requested: bool,
) -> JsonObjectType:
    """Serialize one configuration-oriented network segment report."""
    host_details = _build_network_host_detail_rows(entry, view)
    dhcp_config = _build_network_dhcp_config(entry, interface_name=view.interface_name)
    return {
        "config_entry_id": entry.entry_id,
        "refreshed": refresh_requested,
        "target": _serialize_report_target(
            FirewallaReportTarget(
                kind="network_segment",
                id=view.target.uuid,
                name=view.target.name,
            )
        ),
        "query": {"refresh": refresh_requested},
        "time_basis": _serialize_report_time_basis(
            FirewallaReportTimeBasis(
                kind="snapshot",
                label="Current network segment configuration snapshot",
                boundary_source="runtime_snapshot",
            )
        ),
        "summary": {
            "host_count": len(host_details),
            "has_dhcp_config": dhcp_config is not None,
            "has_ipv4_addressing": bool(view.ipv4_addresses or view.ipv4_subnets),
            "has_ipv6_addressing": bool(view.ipv6_addresses or view.ipv6_subnets),
        },
        "sections": {
            "configuration": {
                "interface_name": view.interface_name,
                "type": view.network_type,
                "monitoring": view.monitoring,
                "active": view.active,
                "ready": view.ready,
                "pending_test": view.pending_test,
                "policy": cast(JsonObjectType | None, view.policy),
            },
            "addressing": {
                "gateway": view.gateway,
                "gateway6": view.gateway6,
                "route_id": view.route_id,
                "ipv4_addresses": list(view.ipv4_addresses),
                "ipv4_subnets": list(view.ipv4_subnets),
                "ipv6_addresses": list(view.ipv6_addresses),
                "ipv6_subnets": list(view.ipv6_subnets),
                "route4_subnets": list(view.route4_subnets),
                "route6_subnets": list(view.route6_subnets),
            },
            "dns": {
                "servers": list(view.dns_servers),
                "servers6": list(view.dns6_servers),
                "original_servers": list(view.original_dns_servers),
                "original_servers6": list(view.original_dns6_servers),
            },
            "dhcp": _serialize_network_dhcp_config(dhcp_config),
            "hosts": {
                "count": len(host_details),
                "items": [
                    _serialize_network_host_detail(host_detail)
                    for host_detail in host_details
                ],
            },
        },
        "metadata": _serialize_report_metadata(
            applied={"refresh": refresh_requested},
            provenance=(
                FirewallaReportProvenance(
                    section="configuration",
                    source="direct",
                    source_field="networkInterface",
                    note="Interface state comes from the direct network view",
                ),
                FirewallaReportProvenance(
                    section="addressing",
                    source="direct",
                    source_field="networkInterface",
                    note="Addressing fields come from the direct network view",
                ),
                FirewallaReportProvenance(
                    section="dns",
                    source="direct",
                    source_field="networkInterface",
                    note="DNS fields come from the direct network view",
                ),
                FirewallaReportProvenance(
                    section="dhcp",
                    source="derived",
                    source_field="logic.dhcpRange",
                    note=(
                        "DHCP settings are derived from the runtime snapshot for "
                        "the matching interface"
                    ),
                ),
                FirewallaReportProvenance(
                    section="hosts",
                    source="derived",
                    source_field="hostManager",
                    note="Host rows are derived from runtime host inventory",
                ),
            ),
        ),
    }


def _serialize_network_segment_usage(
    entry: FirewallaConfigEntry,
    *,
    view: FirewallaNetworkSegmentView,
    refresh_requested: bool,
    window: str,
    top_n: int,
    requested_include: tuple[str, ...],
    applied_include: tuple[str, ...],
    time_zone: tzinfo,
    time_zone_name: str,
) -> JsonObjectType:
    """Serialize one usage-oriented network segment report."""
    source, label, series_list = _resolve_network_segment_usage_window(
        view,
        window=window,
    )
    include_series = "series" in applied_include
    device_rows = view.activity_hosts or tuple(
        host for host in view.hosts if _network_host_has_activity(host)
    )
    serialized_top_download_hosts: list[JsonValueType] = [
        _serialize_network_host_ranking(host)
        for host in view.top_download_hosts[:top_n]
    ]
    serialized_top_upload_hosts: list[JsonValueType] = [
        _serialize_network_host_ranking(host) for host in view.top_upload_hosts[:top_n]
    ]
    serialized_devices: list[JsonValueType] = [
        _serialize_network_host_totals(host) for host in device_rows
    ]
    serialized_apps: list[JsonValueType] = [
        _serialize_network_usage_bucket(bucket, time_zone=time_zone)
        for bucket in view.top_apps[:top_n]
    ]
    serialized_categories: list[JsonValueType] = [
        _serialize_network_usage_bucket(bucket, time_zone=time_zone)
        for bucket in view.top_categories[:top_n]
    ]
    window_download_total, window_upload_total = _calculate_window_transfer_totals(
        series_list
    )
    derived_download_total = sum(host.download_bytes or 0 for host in device_rows)
    derived_upload_total = sum(host.upload_bytes or 0 for host in device_rows)
    activity_section = _serialize_network_time_window(
        series_list=series_list,
        source=source,
        label=label,
        include_samples=False,
        time_zone=time_zone,
    )
    sections: JsonObjectType = {
        "devices": {
            "count": len(serialized_devices),
            "items": serialized_devices,
        },
        "rankings": {
            "top_download_hosts": serialized_top_download_hosts,
            "top_upload_hosts": serialized_top_upload_hosts,
        },
        "activity": activity_section,
    }
    provenance_items: list[FirewallaReportProvenance] = [
        FirewallaReportProvenance(
            section="rankings",
            source="direct",
            source_field="flows",
            note=(
                "Top upload and download rankings come from the direct flow "
                "ranking payload"
            ),
        ),
        FirewallaReportProvenance(
            section="activity",
            source="direct",
            source_field=source,
            note=(
                "Selected activity window metrics come from the direct "
                "network interface payload"
            ),
        ),
    ]
    if serialized_devices:
        if view.activity_hosts:
            provenance_items.append(
                FirewallaReportProvenance(
                    section="devices",
                    source="derived",
                    source_field=(
                        "flows.appDetails|flows.recent|flows.download|flows.upload"
                    ),
                    note=(
                        "Per-device activity is derived from richer flow "
                        "families when raw host counters are sparse"
                    ),
                )
            )
        else:
            provenance_items.append(
                FirewallaReportProvenance(
                    section="devices",
                    source="direct",
                    source_field="hosts",
                    note=(
                        "Per-device totals come from the direct network "
                        "interface payload"
                    ),
                )
            )
    if serialized_apps:
        sections["apps"] = {
            "count": len(serialized_apps),
            "items": serialized_apps,
        }
        provenance_items.append(
            FirewallaReportProvenance(
                section="apps",
                source="derived",
                source_field="flows.appDetails",
                note="Top apps are aggregated from classified flow activity",
            )
        )
    if serialized_categories:
        sections["categories"] = {
            "count": len(serialized_categories),
            "items": serialized_categories,
        }
        provenance_items.append(
            FirewallaReportProvenance(
                section="categories",
                source="derived",
                source_field="flows.categoryDetails",
                note="Top categories are aggregated from classified flow activity",
            )
        )
    if include_series:
        sections["series"] = _serialize_network_time_window(
            series_list=series_list,
            source=source,
            label=label,
            include_samples=True,
            time_zone=time_zone,
        )
        provenance_items.append(
            FirewallaReportProvenance(
                section="series",
                source="direct",
                source_field=source,
                note=(
                    "Series samples expose the raw points for the selected "
                    "activity window"
                ),
            )
        )

    return {
        "config_entry_id": entry.entry_id,
        "refreshed": refresh_requested,
        "target": _serialize_report_target(
            FirewallaReportTarget(
                kind="network_segment",
                id=view.target.uuid,
                name=view.target.name,
            )
        ),
        "query": {
            "refresh": refresh_requested,
            "window": window,
            "top_n": top_n,
            "include": list(requested_include),
            "time_zone": time_zone_name,
        },
        "time_basis": _serialize_report_time_basis(
            _build_network_segment_usage_time_basis(
                series_list=series_list,
                source=source,
                label=label,
                time_zone_name=time_zone_name,
            ),
            time_zone=time_zone,
        ),
        "summary": {
            "host_count": len(serialized_devices),
            "known_host_count": len(view.hosts),
            "active_device_count": len(serialized_devices),
            "metric_count": len(series_list),
            "sample_count": sum(len(series.samples) for series in series_list),
            "top_download_count": len(serialized_top_download_hosts),
            "top_upload_count": len(serialized_top_upload_hosts),
            "app_count": len(view.top_apps),
            "category_count": len(view.top_categories),
            "total_download_bytes": (
                window_download_total
                if window_download_total not in (None, 0)
                else derived_download_total
            ),
            "total_upload_bytes": (
                window_upload_total
                if window_upload_total not in (None, 0)
                else derived_upload_total
            ),
            "includes_series": include_series,
        },
        "sections": sections,
        "metadata": _serialize_report_metadata(
            applied={
                "window": window,
                "top_n": top_n,
                "include": list(applied_include),
                "time_zone": time_zone_name,
            },
            provenance=tuple(provenance_items),
        ),
    }


def _serialize_wan_event_failure(
    failure: FirewallaWanEventFailure,
) -> JsonObjectType:
    """Serialize one normalized WAN event failure."""
    return {"type": failure.type, "target": failure.target}


def _serialize_wan_event_status(
    status: FirewallaWanEventStatus,
) -> JsonObjectType:
    """Serialize one normalized WAN event status."""
    return {
        "interface_key": status.interface_key,
        "wan_uuid": status.wan_uuid,
        "wan_name": status.wan_name,
        "active": status.active,
        "ready": status.ready,
        "ip4_addresses": list(status.ip4_addresses),
        "seq": status.seq,
    }


def _serialize_wan_event(event: FirewallaWanEvent) -> JsonObjectType:
    """Serialize one normalized WAN event for service responses."""
    return {
        "family": event.family,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "timestamp_iso": datetime.fromtimestamp(event.timestamp, UTC).isoformat(),
        "value": event.value,
        "previous_value": event.previous_value,
        "ok_value": event.ok_value,
        "state_key": event.state_key,
        "wan_uuid": event.wan_uuid,
        "wan_name": event.wan_name,
        "active": event.active,
        "ready": event.ready,
        "changed_interface": event.changed_interface,
        "primary_interface": event.primary_interface,
        "wan_type": event.wan_type,
        "wan_switched": event.wan_switched,
        "target": event.target,
        "name_server": event.name_server,
        "dns_test_domain": event.dns_test_domain,
        "wan_interface_address": event.wan_interface_address,
        "measurement_kind": event.measurement_kind,
        "measurement_value": event.measurement_value,
        "threshold_value": event.threshold_value,
        "failures": [
            _serialize_wan_event_failure(failure) for failure in event.failures
        ],
        "wan_statuses": [
            _serialize_wan_event_status(status) for status in event.wan_statuses
        ],
    }


def _resolve_requested_wan(
    entry: FirewallaConfigEntry,
    *,
    wan_uuid: str | None,
    wan_name: str | None,
    required: bool,
) -> FirewallaWanInterface | None:
    """Resolve one optional or required WAN selector against runtime metadata."""
    if wan_uuid and wan_name:
        raise ServiceValidationError(
            "Provide either wan_uuid or wan_name, not both",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_SELECTOR_CONFLICT,
        )

    available_wans = entry.runtime_data.integration_manager.get_available_wans()

    if wan_uuid:
        if resolved_wan := next(
            (wan for wan in available_wans if wan.uuid == wan_uuid),
            None,
        ):
            return resolved_wan
        raise ServiceValidationError(
            f"No WAN matched UUID {wan_uuid}",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NOT_FOUND,
            translation_placeholders={TRANS_PLACEHOLDER_WAN_UUID: wan_uuid},
        )

    if wan_name:
        matching_wans = [
            wan for wan in available_wans if wan.name.casefold() == wan_name.casefold()
        ]
        if not matching_wans:
            raise ServiceValidationError(
                f"No WAN matched name {wan_name}",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NOT_FOUND,
                translation_placeholders={TRANS_PLACEHOLDER_WAN_NAME: wan_name},
            )
        if len(matching_wans) > 1:
            raise ServiceValidationError(
                f"More than one WAN matched name {wan_name}",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NAME_AMBIGUOUS,
                translation_placeholders={TRANS_PLACEHOLDER_WAN_NAME: wan_name},
            )
        return matching_wans[0]

    if required:
        if len(available_wans) == 1:
            return available_wans[0]
        raise ServiceValidationError(
            "A WAN selector is required for this service call",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_REQUIRED,
        )

    return None


def _resolve_requested_network(
    entry: FirewallaConfigEntry,
    *,
    network_uuid: str | None,
    network_name: str | None,
) -> FirewallaNetworkSegment | None:
    """Resolve one optional network selector against runtime metadata."""
    if network_uuid and network_name:
        raise ServiceValidationError(
            "Provide either network_uuid or network_name, not both",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_NETWORK_SELECTOR_CONFLICT,
        )

    available_networks = entry.runtime_data.integration_manager.get_available_networks()

    if network_uuid:
        if resolved_network := next(
            (network for network in available_networks if network.uuid == network_uuid),
            None,
        ):
            return resolved_network
        raise ServiceValidationError(
            f"No network matched UUID {network_uuid}",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_NETWORK_NOT_FOUND,
            translation_placeholders={TRANS_PLACEHOLDER_NETWORK_UUID: network_uuid},
        )

    if network_name:
        matching_networks = [
            network
            for network in available_networks
            if network.name.casefold() == network_name.casefold()
        ]
        if not matching_networks:
            raise ServiceValidationError(
                f"No network matched name {network_name}",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_NETWORK_NOT_FOUND,
                translation_placeholders={TRANS_PLACEHOLDER_NETWORK_NAME: network_name},
            )
        if len(matching_networks) > 1:
            raise ServiceValidationError(
                f"More than one network matched name {network_name}",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_NETWORK_NAME_AMBIGUOUS,
                translation_placeholders={TRANS_PLACEHOLDER_NETWORK_NAME: network_name},
            )
        return matching_networks[0]

    return None


def _resolve_usage_history_target(
    entry: FirewallaConfigEntry,
    *,
    scope_kind: str,
    scope_target: str,
) -> FirewallaUsageHistoryTarget:
    """Resolve one usage-history target against normalized runtime metadata."""
    if scope_kind == "device":
        host_manager = entry.runtime_data.host_manager
        if host := host_manager.get_host(scope_target):
            return FirewallaUsageHistoryTarget(
                scope_kind=scope_kind,
                target_id=host.mac,
                target_name=host.display_name,
                request_scope_type=_USAGE_HISTORY_REQUEST_SCOPE_HOST,
            )

        choices = host_manager.get_watched_device_choices()
        matches = [
            host.mac
            for host in host_manager.get_hosts()
            if host.display_name.casefold() == scope_target.casefold()
            or choices.get(host.mac, "").casefold() == scope_target.casefold()
        ]
        if (
            len(matches) == 1
            and (host := host_manager.get_host(matches[0])) is not None
        ):
            return FirewallaUsageHistoryTarget(
                scope_kind=scope_kind,
                target_id=host.mac,
                target_name=host.display_name,
                request_scope_type=_USAGE_HISTORY_REQUEST_SCOPE_HOST,
            )
        if len(matches) > 1:
            raise ServiceValidationError(
                f"More than one {scope_kind} matched {scope_target}",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_AMBIGUOUS,
                translation_placeholders={
                    TRANS_PLACEHOLDER_SCOPE_KIND: scope_kind,
                    TRANS_PLACEHOLDER_SCOPE_TARGET: scope_target,
                },
            )
        raise ServiceValidationError(
            f"No {scope_kind} matched {scope_target}",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_NOT_FOUND,
            translation_placeholders={
                TRANS_PLACEHOLDER_SCOPE_KIND: scope_kind,
                TRANS_PLACEHOLDER_SCOPE_TARGET: scope_target,
            },
        )

    if scope_kind == "user":
        user_manager = entry.runtime_data.user_manager
        if user := user_manager.get_user(scope_target):
            return FirewallaUsageHistoryTarget(
                scope_kind=scope_kind,
                target_id=user.user_id,
                target_name=user.name,
                request_scope_type=_USAGE_HISTORY_REQUEST_SCOPE_TAG,
            )

        choices = user_manager.get_watched_user_choices()
        matches = [
            user.user_id
            for user in user_manager.get_users()
            if user.name.casefold() == scope_target.casefold()
            or choices.get(user.user_id, "").casefold() == scope_target.casefold()
        ]
        if (
            len(matches) == 1
            and (user := user_manager.get_user(matches[0])) is not None
        ):
            return FirewallaUsageHistoryTarget(
                scope_kind=scope_kind,
                target_id=user.user_id,
                target_name=user.name,
                request_scope_type=_USAGE_HISTORY_REQUEST_SCOPE_TAG,
            )
        if len(matches) > 1:
            raise ServiceValidationError(
                f"More than one {scope_kind} matched {scope_target}",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_AMBIGUOUS,
                translation_placeholders={
                    TRANS_PLACEHOLDER_SCOPE_KIND: scope_kind,
                    TRANS_PLACEHOLDER_SCOPE_TARGET: scope_target,
                },
            )
        raise ServiceValidationError(
            f"No {scope_kind} matched {scope_target}",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_NOT_FOUND,
            translation_placeholders={
                TRANS_PLACEHOLDER_SCOPE_KIND: scope_kind,
                TRANS_PLACEHOLDER_SCOPE_TARGET: scope_target,
            },
        )

    groups = entry.runtime_data.integration_manager.get_groups()
    exact_match = next(
        (group for group in groups if group.group_id == scope_target),
        None,
    )
    if exact_match is not None:
        return FirewallaUsageHistoryTarget(
            scope_kind=scope_kind,
            target_id=exact_match.group_id,
            target_name=exact_match.name,
            request_scope_type=_USAGE_HISTORY_REQUEST_SCOPE_TAG,
        )

    group_matches: list[FirewallaGroupRuntime] = [
        group for group in groups if group.name.casefold() == scope_target.casefold()
    ]
    if len(group_matches) == 1:
        return FirewallaUsageHistoryTarget(
            scope_kind=scope_kind,
            target_id=group_matches[0].group_id,
            target_name=group_matches[0].name,
            request_scope_type=_USAGE_HISTORY_REQUEST_SCOPE_TAG,
        )
    if len(group_matches) > 1:
        raise ServiceValidationError(
            f"More than one {scope_kind} matched {scope_target}",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_AMBIGUOUS,
            translation_placeholders={
                TRANS_PLACEHOLDER_SCOPE_KIND: scope_kind,
                TRANS_PLACEHOLDER_SCOPE_TARGET: scope_target,
            },
        )
    raise ServiceValidationError(
        f"No {scope_kind} matched {scope_target}",
        translation_domain=DOMAIN,
        translation_key=TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_NOT_FOUND,
        translation_placeholders={
            TRANS_PLACEHOLDER_SCOPE_KIND: scope_kind,
            TRANS_PLACEHOLDER_SCOPE_TARGET: scope_target,
        },
    )


async def _async_handle_get_runtime_inventory(call: ServiceCall) -> JsonObjectType:
    """Return the current runtime inventory as markdown and structured data."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )
    response = (
        await entry.runtime_data.rule_manager.async_get_runtime_inventory_response()
    )
    LOGGER.info("Generated runtime inventory for config entry %s", entry.entry_id)
    return {
        "config_entry_id": entry.entry_id,
        "inventory": cast(JsonObjectType, response["inventory"]),
        "markdown": cast(str, response["markdown"]),
    }


async def _async_handle_run_internet_speed_test(call: ServiceCall) -> JsonObjectType:
    """Start one internet speed test on the resolved WAN interface."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )
    await _async_refresh_runtime_state(entry)
    wan = _resolve_requested_wan(
        entry,
        wan_uuid=call.data.get(SERVICE_FIELD_WAN_UUID),
        wan_name=call.data.get(SERVICE_FIELD_WAN_NAME),
        required=True,
    )
    assert wan is not None

    try:
        command_response = (
            await entry.runtime_data.integration_manager.async_run_internet_speed_test(
                wan.uuid
            )
        )
    except FirewallaApiError as err:
        raise HomeAssistantError(
            f"Could not start the internet speed test: {err}"
        ) from err

    return {
        "config_entry_id": entry.entry_id,
        "wan": _serialize_wan_interface(wan),
        "command": {
            "item": "runInternetSpeedtest",
            "value": {SERVICE_FIELD_WAN_UUID: wan.uuid},
        },
        "command_response": cast(JsonObjectType, command_response),
    }


async def _async_handle_get_speed_test_results(call: ServiceCall) -> JsonObjectType:
    """Return shaped speed-test results from the coordinator snapshot path."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )

    refresh_requested = cast(bool, call.data[SERVICE_FIELD_REFRESH])
    if refresh_requested:
        await _async_refresh_runtime_state(entry)

    wan = _resolve_requested_wan(
        entry,
        wan_uuid=call.data.get(SERVICE_FIELD_WAN_UUID),
        wan_name=call.data.get(SERVICE_FIELD_WAN_NAME),
        required=False,
    )

    speed_test_results = entry.runtime_data.integration_manager.get_speed_test_results(
        wan_uuid=wan.uuid if wan is not None else None,
        limit=cast(int, call.data[SERVICE_FIELD_LIMIT]),
    )
    serialized_results: list[JsonValueType] = [
        _serialize_speed_test_result(speed_test_result)
        for speed_test_result in speed_test_results
    ]

    return {
        "config_entry_id": entry.entry_id,
        "refreshed": refresh_requested,
        "wan": _serialize_wan_interface(wan) if wan is not None else None,
        "count": len(serialized_results),
        "latest": serialized_results[0] if serialized_results else None,
        "results": serialized_results,
    }


def _resolve_report_time_zone(
    hass: HomeAssistant,
    entry: FirewallaConfigEntry,
) -> tuple[tzinfo, str]:
    """Return the effective timezone used for report shaping and display."""
    snapshot = entry.runtime_data.coordinator.data
    if (
        snapshot is not None
        and snapshot.appliance_runtime.timezone_name is not None
        and (
            firewalla_time_zone := dt_util.get_time_zone(
                snapshot.appliance_runtime.timezone_name
            )
        )
    ):
        return firewalla_time_zone, snapshot.appliance_runtime.timezone_name

    time_zone = dt_util.get_time_zone(hass.config.time_zone) or UTC
    return time_zone, getattr(time_zone, "key", None) or hass.config.time_zone


async def _async_handle_get_time_usage_report(call: ServiceCall) -> JsonObjectType:
    """Return one normalized time-usage report from the local runtime."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )

    begin_input = cast(datetime, call.data[SERVICE_FIELD_USAGE_HISTORY_BEGIN])
    end_input = cast(datetime, call.data[SERVICE_FIELD_USAGE_HISTORY_END])
    begin_utc = dt_util.as_utc(begin_input)
    end_utc = dt_util.as_utc(end_input)
    time_zone, time_zone_name = _resolve_report_time_zone(call.hass, entry)
    if end_utc <= begin_utc:
        raise ServiceValidationError(
            "end must be after begin",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_END_BEFORE_BEGIN,
        )

    target = _resolve_usage_history_target(
        entry,
        scope_kind=cast(str, call.data[SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND]),
        scope_target=cast(str, call.data[SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET]),
    )
    (
        detail,
        requested_sections,
        applied_sections,
        requested_include,
        applied_include,
        app_ids,
    ) = _resolve_time_usage_report_inputs(call)

    try:
        usage_history = (
            await entry.runtime_data.integration_manager.async_get_usage_history(
                target=target,
                begin_timestamp=int(begin_utc.timestamp()),
                end_timestamp=int(end_utc.timestamp()),
                granularity=cast(
                    str,
                    call.data[SERVICE_FIELD_USAGE_HISTORY_GRANULARITY],
                ),
                include_intervals="intervals" in applied_include,
                app_ids=app_ids,
            )
        )
    except FirewallaApiError as err:
        raise HomeAssistantError(f"Could not read time usage report: {err}") from err

    return {
        "config_entry_id": entry.entry_id,
        **_serialize_usage_history_view(
            usage_history,
            time_zone=time_zone,
            time_zone_name=time_zone_name,
            detail=detail,
            requested_sections=requested_sections,
            applied_sections=applied_sections,
            requested_include=requested_include,
            applied_include=applied_include,
        ),
    }


def _resolve_wan_data_usage_inputs(
    call: ServiceCall,
) -> tuple[
    tuple[str, ...],
    str | None,
    int,
    str,
    tuple[str, ...],
    tuple[str, ...],
    tuple[FirewallaReportWarning, ...],
    tuple[str, ...],
]:
    """Resolve and validate WAN data-usage service inputs."""
    raw_current_periods = call.data.get(SERVICE_FIELD_CURRENT_PERIODS)
    history_period = cast(str | None, call.data.get(SERVICE_FIELD_HISTORY_PERIOD))
    history_count = cast(int, call.data[SERVICE_FIELD_HISTORY_COUNT])
    detail = cast(str, call.data[SERVICE_FIELD_DETAIL])
    requested_include = _normalize_report_include(
        call.data.get(SERVICE_FIELD_INCLUDE),
        allowed=("history", "subperiods"),
    )

    current_periods = (
        tuple(str(period) for period in cast(list[str], raw_current_periods))
        if raw_current_periods is not None
        else (() if history_count > 0 else ("month",))
    )

    if history_count > 0 and history_period is None:
        raise ServiceValidationError(
            "history_period is required when history_count is greater than zero",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_WAN_DATA_USAGE_HISTORY_PERIOD_REQUIRED,
        )

    warnings: list[FirewallaReportWarning] = []
    unavailable_sections: list[str] = []
    applied_include: list[str] = []

    if history_count > 0:
        applied_include.append("history")
    elif "history" in requested_include:
        unavailable_sections.append("history")
        warnings.append(
            FirewallaReportWarning(
                code="history_not_available",
                message="History was requested but history_count is 0",
            )
        )

    subperiods_requested = detail == "full" or "subperiods" in requested_include
    if subperiods_requested:
        if (
            "month" in current_periods
            or "week" in current_periods
            or (history_period in {"month", "week"} and history_count > 0)
        ):
            applied_include.append("subperiods")
        else:
            unavailable_sections.append("subperiods")
            warnings.append(
                FirewallaReportWarning(
                    code="subperiods_not_available",
                    message=(
                        "Subperiod breakdowns are only available for month "
                        "or week usage rows"
                    ),
                )
            )

    return (
        current_periods,
        history_period,
        history_count,
        detail,
        requested_include,
        tuple(applied_include),
        tuple(warnings),
        tuple(unavailable_sections),
    )


def _iter_wan_data_usage_rows(
    reports: Sequence[FirewallaWanDataUsageReport],
) -> list[FirewallaWanDataUsageRow]:
    """Return all WAN data-usage rows included in the current response."""
    rows: list[FirewallaWanDataUsageRow] = []
    for report in reports:
        for current_row in (
            report.current_month,
            report.current_week,
            report.current_day,
        ):
            if current_row is not None:
                rows.append(current_row)
        rows.extend(report.history_months)
        rows.extend(report.history_weeks)
        rows.extend(report.history_days)
    return rows


def _build_wan_data_usage_time_basis(
    reports: Sequence[FirewallaWanDataUsageReport],
    *,
    time_zone_name: str,
) -> FirewallaReportTimeBasis:
    """Build the top-level time-basis object for WAN usage reports."""
    rows = _iter_wan_data_usage_rows(reports)
    begin_values = [
        row.time_period.begin_timestamp
        for row in rows
        if row.time_period.begin_timestamp is not None
    ]
    end_values = [
        row.time_period.end_timestamp
        for row in rows
        if row.time_period.end_timestamp is not None
    ]
    anchor_values = [
        row.time_period.anchor_timestamp
        for row in rows
        if row.time_period.anchor_timestamp is not None
    ]

    return FirewallaReportTimeBasis(
        kind="period_bundle",
        label="Current and historical WAN usage periods",
        begin_timestamp=min(begin_values) if begin_values else None,
        end_timestamp=max(end_values) if end_values else None,
        anchor_timestamp=max(anchor_values) if anchor_values else None,
        is_partial=any(row.time_period.is_partial for row in rows) if rows else None,
        boundary_source="firewalla_periods",
        time_zone=time_zone_name,
    )


async def _async_handle_get_wan_data_usage(call: ServiceCall) -> JsonObjectType:
    """Return one normalized WAN data-usage report from direct local reads."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )

    refresh_requested = cast(bool, call.data[SERVICE_FIELD_REFRESH])
    if refresh_requested:
        await _async_refresh_runtime_state(entry)

    wan = _resolve_requested_wan(
        entry,
        wan_uuid=call.data.get(SERVICE_FIELD_WAN_UUID),
        wan_name=call.data.get(SERVICE_FIELD_WAN_NAME),
        required=False,
    )
    (
        current_periods,
        history_period,
        history_count,
        detail,
        requested_include,
        applied_include,
        warnings,
        unavailable_sections,
    ) = _resolve_wan_data_usage_inputs(call)
    time_zone, time_zone_name = _resolve_report_time_zone(call.hass, entry)
    integration_manager = entry.runtime_data.integration_manager
    manager_detail = "daily" if "subperiods" in applied_include else "summary"

    try:
        usage_reports = await integration_manager.async_get_wan_data_usage_reports(
            wan_uuid=wan.uuid if wan is not None else None,
            current_periods=current_periods,
            history_period=history_period,
            history_count=history_count,
            detail=manager_detail,
            time_zone=time_zone,
        )
    except FirewallaApiError as err:
        raise HomeAssistantError(f"Could not read WAN data usage: {err}") from err
    serialized_reports: list[JsonValueType] = [
        _serialize_wan_data_usage_report(report, time_zone=time_zone)
        for report in usage_reports
    ]
    provenance: list[FirewallaReportProvenance] = [
        FirewallaReportProvenance(
            section="reports",
            source="direct",
            source_field="monthlyDataUsageOnWans",
            note="Current and history rows come from direct WAN usage payloads",
        )
    ]
    if "history" in applied_include:
        provenance.append(
            FirewallaReportProvenance(
                section="reports.history",
                source="direct",
                source_field="last12MonthlyDataUsageOnWans",
                note="History rows appear only when history_count is greater than zero",
            )
        )
    if "subperiods" in applied_include:
        provenance.append(
            FirewallaReportProvenance(
                section="reports.current.subperiods",
                source="derived",
                source_field="monthlyDataUsageOnWans",
                note=(
                    "Nested week and day breakdowns are derived from current "
                    "WAN usage samples"
                ),
            )
        )
    target_kind = "wan" if wan is not None else "wan_collection"
    time_basis = _build_wan_data_usage_time_basis(
        usage_reports,
        time_zone_name=time_zone_name,
    )

    return {
        "config_entry_id": entry.entry_id,
        "refreshed": refresh_requested,
        "target": _serialize_report_target(
            FirewallaReportTarget(
                kind=target_kind,
                id=wan.uuid if wan is not None else None,
                name=wan.name if wan is not None else None,
            )
        ),
        "query": {
            "detail": detail,
            "include": list(requested_include),
            "time_zone": time_zone_name,
            "refresh": refresh_requested,
            "current_periods": list(current_periods),
            "history_period": history_period,
            "history_count": history_count,
        },
        "time_basis": _serialize_report_time_basis(time_basis, time_zone=time_zone),
        "summary": {
            "wan_count": len(serialized_reports),
            "current_periods": list(current_periods),
            "history_period": history_period,
            "history_count": history_count,
            "includes_history": "history" in applied_include,
            "includes_subperiods": "subperiods" in applied_include,
        },
        "sections": {
            "reports": serialized_reports,
        },
        "metadata": _serialize_report_metadata(
            applied={
                "detail": detail,
                "include": list(applied_include),
            },
            warnings=warnings,
            unavailable_sections=unavailable_sections,
            provenance=tuple(provenance),
        ),
    }


async def _async_handle_get_network_segment_report(call: ServiceCall) -> JsonObjectType:
    """Return one configuration-oriented report for the requested segment."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )

    refresh_requested = cast(bool, call.data[SERVICE_FIELD_REFRESH])
    if refresh_requested:
        await _async_refresh_runtime_state(entry)

    network = _resolve_requested_network_required(
        entry,
        network_uuid=call.data.get(SERVICE_FIELD_NETWORK_UUID),
        network_name=call.data.get(SERVICE_FIELD_NETWORK_NAME),
    )

    try:
        network_views = (
            await entry.runtime_data.integration_manager.async_get_network_interfaces(
                network_uuid=network.uuid,
            )
        )
    except FirewallaApiError as err:
        raise HomeAssistantError(
            f"Could not read network segment report: {err}"
        ) from err

    if not network_views:
        raise ServiceValidationError(
            f"No network matched UUID {network.uuid}",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_NETWORK_NOT_FOUND,
            translation_placeholders={TRANS_PLACEHOLDER_NETWORK_UUID: network.uuid},
        )

    return _serialize_network_segment_report(
        entry,
        view=network_views[0],
        refresh_requested=refresh_requested,
    )


async def _async_handle_get_network_segment_usage(call: ServiceCall) -> JsonObjectType:
    """Return one usage-oriented report for the requested segment."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )

    refresh_requested = cast(bool, call.data[SERVICE_FIELD_REFRESH])
    if refresh_requested:
        await _async_refresh_runtime_state(entry)

    network = _resolve_requested_network_required(
        entry,
        network_uuid=call.data.get(SERVICE_FIELD_NETWORK_UUID),
        network_name=call.data.get(SERVICE_FIELD_NETWORK_NAME),
    )
    if not isinstance(call.data.get(SERVICE_FIELD_WINDOW), str):
        raise ServiceValidationError(
            "Provide window for this service call",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_NETWORK_USAGE_WINDOW_REQUIRED,
        )

    window = cast(str, call.data[SERVICE_FIELD_WINDOW])
    top_n = cast(int, call.data[SERVICE_FIELD_TOP_N])
    requested_include = _normalize_report_include(
        call.data.get(SERVICE_FIELD_INCLUDE),
        allowed=("series",),
    )
    time_zone, time_zone_name = _resolve_report_time_zone(call.hass, entry)

    try:
        network_views = (
            await entry.runtime_data.integration_manager.async_get_network_interfaces(
                network_uuid=network.uuid,
            )
        )
    except FirewallaApiError as err:
        raise HomeAssistantError(
            f"Could not read network segment usage: {err}"
        ) from err

    if not network_views:
        raise ServiceValidationError(
            f"No network matched UUID {network.uuid}",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_NETWORK_NOT_FOUND,
            translation_placeholders={TRANS_PLACEHOLDER_NETWORK_UUID: network.uuid},
        )

    return _serialize_network_segment_usage(
        entry,
        view=network_views[0],
        refresh_requested=refresh_requested,
        window=window,
        top_n=top_n,
        requested_include=requested_include,
        applied_include=requested_include,
        time_zone=time_zone,
        time_zone_name=time_zone_name,
    )


async def _async_handle_get_wan_events(call: ServiceCall) -> JsonObjectType:
    """Return normalized WAN health events from the local runtime."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )

    wan = _resolve_requested_wan(
        entry,
        wan_uuid=call.data.get(SERVICE_FIELD_WAN_UUID),
        wan_name=call.data.get(SERVICE_FIELD_WAN_NAME),
        required=False,
    )
    limit = cast(int, call.data[SERVICE_FIELD_LIMIT])
    offset = cast(int, call.data[SERVICE_FIELD_OFFSET])

    try:
        events = await entry.runtime_data.integration_manager.async_get_wan_events(
            wan_uuid=wan.uuid if wan is not None else None,
            limit=limit,
            offset=offset,
        )
    except FirewallaApiError as err:
        raise HomeAssistantError(f"Could not read WAN events: {err}") from err

    serialized_events: list[JsonValueType] = [
        _serialize_wan_event(event) for event in events
    ]

    return {
        "config_entry_id": entry.entry_id,
        "wan": _serialize_wan_interface(wan) if wan is not None else None,
        "query": {
            "limit": limit,
            "offset": offset,
        },
        "count": len(serialized_events),
        "results": serialized_events,
    }


async def _async_handle_pause_rule(call: ServiceCall) -> None:
    """Pause one managed rule target.

    Support indefinite, duration-based, and explicit resume-time pauses.
    """
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )
    await _async_refresh_runtime_state(entry)

    rule_target = call.data[SERVICE_FIELD_RULE_TARGET]
    duration = call.data.get(SERVICE_FIELD_RULE_DURATION)
    resume_at = call.data.get(SERVICE_FIELD_RULE_RESUME_AT)

    if not entry.runtime_data.rule_manager.has_rule_target(rule_target):
        raise ServiceValidationError(
            f"Rule target not found: {rule_target}",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_RULE_TARGET_NOT_FOUND,
            translation_placeholders={TRANS_PLACEHOLDER_RULE_TARGET: rule_target},
        )

    if duration is not None and resume_at is not None:
        raise ServiceValidationError(
            "Provide either duration or resume_at, not both",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_PAUSE_RULE_TIMING_CONFLICT,
        )

    resume_ts: int | None = None

    if duration is not None:
        try:
            duration_seconds = parse_duration_to_seconds(duration)
        except ValueError as err:
            raise ServiceValidationError(
                f"Invalid duration: {duration}",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_INVALID_DURATION,
                translation_placeholders={TRANS_PLACEHOLDER_DURATION: duration},
            ) from err

        resume_ts = int(dt_util.utcnow().timestamp()) + duration_seconds

    elif isinstance(resume_at, datetime):
        resume_at_utc = dt_util.as_utc(resume_at)
        if resume_at_utc <= dt_util.utcnow():
            raise ServiceValidationError(
                "resume_at must be in the future",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_EXCEPTION_RESUME_AT_IN_PAST,
            )
        resume_ts = int(resume_at_utc.timestamp())

    await entry.runtime_data.rule_manager.async_pause_rule(rule_target, resume_ts)


async def _async_handle_resume_rule(call: ServiceCall) -> None:
    """Resume one managed rule target immediately."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )
    await _async_refresh_runtime_state(entry)

    rule_target = call.data[SERVICE_FIELD_RULE_TARGET]

    if not entry.runtime_data.rule_manager.has_rule_target(rule_target):
        raise ServiceValidationError(
            f"Rule target not found: {rule_target}",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_EXCEPTION_RULE_TARGET_NOT_FOUND,
            translation_placeholders={TRANS_PLACEHOLDER_RULE_TARGET: rule_target},
        )

    await entry.runtime_data.rule_manager.async_resume_rule(rule_target)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register Firewalla Local services."""
    if not hass.services.has_service(DOMAIN, SERVICE_GET_RUNTIME_INVENTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_RUNTIME_INVENTORY,
            _async_handle_get_runtime_inventory,
            schema=GET_RUNTIME_INVENTORY_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_NETWORK_SEGMENT_REPORT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_REPORT,
            _async_handle_get_network_segment_report,
            schema=GET_NETWORK_SEGMENT_REPORT_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_NETWORK_SEGMENT_USAGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_USAGE,
            _async_handle_get_network_segment_usage,
            schema=GET_NETWORK_SEGMENT_USAGE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RUN_INTERNET_SPEED_TEST):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RUN_INTERNET_SPEED_TEST,
            _async_handle_run_internet_speed_test,
            schema=RUN_INTERNET_SPEED_TEST_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_SPEED_TEST_RESULTS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_SPEED_TEST_RESULTS,
            _async_handle_get_speed_test_results,
            schema=GET_SPEED_TEST_RESULTS_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_TIME_USAGE_REPORT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_TIME_USAGE_REPORT,
            _async_handle_get_time_usage_report,
            schema=GET_TIME_USAGE_REPORT_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_WAN_DATA_USAGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_WAN_DATA_USAGE,
            _async_handle_get_wan_data_usage,
            schema=GET_WAN_DATA_USAGE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_WAN_EVENTS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_WAN_EVENTS,
            _async_handle_get_wan_events,
            schema=GET_WAN_EVENTS_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_PAUSE_RULE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            _async_handle_pause_rule,
            schema=PAUSE_RULE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RESUME_RULE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESUME_RULE,
            _async_handle_resume_rule,
            schema=RESUME_RULE_SCHEMA,
        )


def async_remove_services(hass: HomeAssistant) -> None:
    """Remove Firewalla Local services."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_RUNTIME_INVENTORY):
        hass.services.async_remove(DOMAIN, SERVICE_GET_RUNTIME_INVENTORY)
    if hass.services.has_service(DOMAIN, SERVICE_GET_NETWORK_SEGMENT_REPORT):
        hass.services.async_remove(DOMAIN, SERVICE_GET_NETWORK_SEGMENT_REPORT)
    if hass.services.has_service(DOMAIN, SERVICE_GET_NETWORK_SEGMENT_USAGE):
        hass.services.async_remove(DOMAIN, SERVICE_GET_NETWORK_SEGMENT_USAGE)
    if hass.services.has_service(DOMAIN, SERVICE_RUN_INTERNET_SPEED_TEST):
        hass.services.async_remove(DOMAIN, SERVICE_RUN_INTERNET_SPEED_TEST)
    if hass.services.has_service(DOMAIN, SERVICE_GET_SPEED_TEST_RESULTS):
        hass.services.async_remove(DOMAIN, SERVICE_GET_SPEED_TEST_RESULTS)
    if hass.services.has_service(DOMAIN, SERVICE_GET_TIME_USAGE_REPORT):
        hass.services.async_remove(DOMAIN, SERVICE_GET_TIME_USAGE_REPORT)
    if hass.services.has_service(DOMAIN, SERVICE_GET_WAN_DATA_USAGE):
        hass.services.async_remove(DOMAIN, SERVICE_GET_WAN_DATA_USAGE)
    if hass.services.has_service(DOMAIN, SERVICE_GET_WAN_EVENTS):
        hass.services.async_remove(DOMAIN, SERVICE_GET_WAN_EVENTS)
    if hass.services.has_service(DOMAIN, SERVICE_PAUSE_RULE):
        hass.services.async_remove(DOMAIN, SERVICE_PAUSE_RULE)
    if hass.services.has_service(DOMAIN, SERVICE_RESUME_RULE):
        hass.services.async_remove(DOMAIN, SERVICE_RESUME_RULE)
