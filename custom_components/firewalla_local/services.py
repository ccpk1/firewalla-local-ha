"""Home Assistant service handling for Firewalla Local."""

from __future__ import annotations

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
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_NETWORK_NAME,
    SERVICE_FIELD_NETWORK_UUID,
    SERVICE_FIELD_OFFSET,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_FIELD_USAGE_HISTORY_APP_IDS,
    SERVICE_FIELD_USAGE_HISTORY_BEGIN,
    SERVICE_FIELD_USAGE_HISTORY_END,
    SERVICE_FIELD_USAGE_HISTORY_GRANULARITY,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_GET_NETWORK_INTERFACES,
    SERVICE_GET_RUNTIME_INVENTORY,
    SERVICE_GET_SPEED_TEST_RESULTS,
    SERVICE_GET_USAGE_HISTORY,
    SERVICE_GET_WAN_EVENTS,
    SERVICE_GET_WAN_USAGE,
    SERVICE_GET_WAN_USAGE_HISTORY,
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
    TRANS_KEY_EXCEPTION_NETWORK_SELECTOR_CONFLICT,
    TRANS_KEY_EXCEPTION_PAUSE_RULE_TIMING_CONFLICT,
    TRANS_KEY_EXCEPTION_RESUME_AT_IN_PAST,
    TRANS_KEY_EXCEPTION_RULE_TARGET_NOT_FOUND,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NAME_AMBIGUOUS,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NOT_FOUND,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_REQUIRED,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_SELECTOR_CONFLICT,
    TRANS_KEY_EXCEPTION_WRONG_INTEGRATION_ENTRY,
    TRANS_PLACEHOLDER_DURATION,
    TRANS_PLACEHOLDER_NETWORK_NAME,
    TRANS_PLACEHOLDER_NETWORK_UUID,
    TRANS_PLACEHOLDER_RULE_TARGET,
    TRANS_PLACEHOLDER_WAN_NAME,
    TRANS_PLACEHOLDER_WAN_UUID,
)
from .coordinator import FirewallaConfigEntry
from .models import (
    FirewallaGroupRuntime,
    FirewallaNetworkHostRanking,
    FirewallaNetworkHostTotals,
    FirewallaNetworkMetricSample,
    FirewallaNetworkMetricSeries,
    FirewallaNetworkSegment,
    FirewallaNetworkSegmentView,
    FirewallaSpeedTestResult,
    FirewallaUsageHistoryDeviceUsage,
    FirewallaUsageHistoryEntry,
    FirewallaUsageHistoryInterval,
    FirewallaUsageHistoryMetric,
    FirewallaUsageHistorySlot,
    FirewallaUsageHistoryTarget,
    FirewallaUsageHistoryView,
    FirewallaWanEvent,
    FirewallaWanEventFailure,
    FirewallaWanEventStatus,
    FirewallaWanInterface,
    FirewallaWanUsagePeriod,
    FirewallaWanUsageSample,
    FirewallaWanUsageView,
)
from .utils.duration import parse_duration_to_seconds

GET_RUNTIME_INVENTORY_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

GET_NETWORK_INTERFACES_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_NETWORK_UUID): cv.string,
        vol.Optional(SERVICE_FIELD_NETWORK_NAME): cv.string,
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

GET_USAGE_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND): vol.In(
            ("device", "group", "user")
        ),
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET): cv.string,
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_BEGIN): cv.datetime,
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_END): cv.datetime,
        vol.Required(SERVICE_FIELD_USAGE_HISTORY_GRANULARITY): vol.In(("day", "hour")),
        vol.Optional(SERVICE_FIELD_USAGE_HISTORY_APP_IDS): vol.All(
            cv.ensure_list_csv,
            [cv.string],
        ),
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

GET_WAN_USAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_WAN_UUID): cv.string,
        vol.Optional(SERVICE_FIELD_WAN_NAME): cv.string,
        vol.Optional(SERVICE_FIELD_REFRESH, default=True): cv.boolean,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)

GET_WAN_USAGE_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_FIELD_WAN_UUID): cv.string,
        vol.Optional(SERVICE_FIELD_WAN_NAME): cv.string,
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
) -> JsonObjectType:
    """Serialize one usage-history interval for service responses."""
    return {
        "begin_timestamp": interval.begin_timestamp,
        "begin_timestamp_iso": _serialize_unix_timestamp(interval.begin_timestamp),
        "end_timestamp": interval.end_timestamp,
        "end_timestamp_iso": _serialize_unix_timestamp(interval.end_timestamp),
        "duration_seconds": interval.duration_seconds,
        "duration_minutes": interval.duration_minutes,
    }


def _serialize_usage_history_slot(slot: FirewallaUsageHistorySlot) -> JsonObjectType:
    """Serialize one usage-history slot for service responses."""
    return {
        "timestamp": slot.timestamp,
        "timestamp_iso": _serialize_unix_timestamp(slot.timestamp),
        "total_minutes": slot.total_minutes,
        "unique_minutes": slot.unique_minutes,
    }


def _serialize_usage_history_device_usage(
    device_usage: FirewallaUsageHistoryDeviceUsage,
) -> JsonObjectType:
    """Serialize one device-level usage-history breakdown."""
    return {
        "device_id": device_usage.device_id,
        "device_name": device_usage.device_name,
        "total_minutes": device_usage.total_minutes,
        "unique_minutes": device_usage.unique_minutes,
        "intervals": [
            _serialize_usage_history_interval(interval)
            for interval in device_usage.intervals
        ],
    }


def _serialize_usage_history_metric(
    metric: FirewallaUsageHistoryMetric | None,
) -> JsonObjectType | None:
    """Serialize one usage-history metric section."""
    if metric is None:
        return None

    return {
        "category": metric.category,
        "total_minutes": metric.total_minutes,
        "unique_minutes": metric.unique_minutes,
        "slots": [_serialize_usage_history_slot(slot) for slot in metric.slots],
        "intervals": [
            _serialize_usage_history_interval(interval) for interval in metric.intervals
        ],
        "devices": [
            _serialize_usage_history_device_usage(device) for device in metric.devices
        ],
    }


def _serialize_usage_history_entry(entry: FirewallaUsageHistoryEntry) -> JsonObjectType:
    """Serialize one named usage-history entry."""
    return {
        "key": entry.key,
        "metric": _serialize_usage_history_metric(entry.metric),
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


def _serialize_usage_history_view(
    view: FirewallaUsageHistoryView,
    *,
    time_zone: tzinfo,
    time_zone_name: str,
) -> JsonObjectType:
    """Serialize one normalized usage-history response."""
    return {
        "scope": _serialize_usage_history_target(view.target),
        "query": {
            "begin_timestamp": view.begin_timestamp,
            "begin_timestamp_iso": _serialize_unix_timestamp(view.begin_timestamp),
            "begin_local": _serialize_local_timestamp(
                view.begin_timestamp,
                time_zone=time_zone,
            ),
            "end_timestamp": view.end_timestamp,
            "end_timestamp_iso": _serialize_unix_timestamp(view.end_timestamp),
            "end_local": _serialize_local_timestamp(
                view.end_timestamp,
                time_zone=time_zone,
            ),
            "time_zone": time_zone_name,
            "granularity": view.granularity,
            "app_ids": list(view.app_ids) if view.app_ids is not None else None,
        },
        "internet": _serialize_usage_history_metric(view.internet),
        "app_totals": _serialize_usage_history_metric(view.app_totals),
        "apps": [_serialize_usage_history_entry(entry) for entry in view.apps],
        "categories": [
            _serialize_usage_history_entry(entry) for entry in view.categories
        ],
    }


def _serialize_wan_usage_sample(sample: FirewallaWanUsageSample) -> JsonObjectType:
    """Serialize one WAN usage sample for service responses."""
    return {
        "timestamp": sample.timestamp,
        "timestamp_iso": _serialize_unix_timestamp(sample.timestamp),
        "value": sample.value,
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


def _serialize_network_segment_view(
    view: FirewallaNetworkSegmentView,
) -> JsonObjectType:
    """Serialize one normalized network interface summary response."""
    return {
        "network": _serialize_network_segment(view.target),
        "interface_name": view.interface_name,
        "type": view.network_type,
        "monitoring": view.monitoring,
        "active": view.active,
        "ready": view.ready,
        "pending_test": view.pending_test,
        "gateway": view.gateway,
        "gateway6": view.gateway6,
        "route_id": view.route_id,
        "dns_servers": list(view.dns_servers),
        "dns6_servers": list(view.dns6_servers),
        "original_dns_servers": list(view.original_dns_servers),
        "original_dns6_servers": list(view.original_dns6_servers),
        "ipv4_addresses": list(view.ipv4_addresses),
        "ipv4_subnets": list(view.ipv4_subnets),
        "ipv6_addresses": list(view.ipv6_addresses),
        "ipv6_subnets": list(view.ipv6_subnets),
        "route4_subnets": list(view.route4_subnets),
        "route6_subnets": list(view.route6_subnets),
        "policy": cast(JsonObjectType | None, view.policy),
        "host_count": view.host_count,
        "hosts": [_serialize_network_host_totals(host) for host in view.hosts],
        "top_download_hosts": [
            _serialize_network_host_ranking(host) for host in view.top_download_hosts
        ],
        "top_upload_hosts": [
            _serialize_network_host_ranking(host) for host in view.top_upload_hosts
        ],
        "newLast24": [
            _serialize_network_metric_series(series) for series in view.new_last24
        ],
        "last60": [_serialize_network_metric_series(series) for series in view.last60],
        "last30": [_serialize_network_metric_series(series) for series in view.last30],
        "last12Months": [
            _serialize_network_metric_series(series) for series in view.last12_months
        ],
    }


def _serialize_wan_usage_period(period: FirewallaWanUsagePeriod) -> JsonObjectType:
    """Serialize one WAN usage period for service responses."""
    return {
        "bucket_timestamp": period.bucket_timestamp,
        "bucket_timestamp_iso": _serialize_unix_timestamp(period.bucket_timestamp),
        "begin_timestamp": period.begin_timestamp,
        "begin_timestamp_iso": _serialize_unix_timestamp(period.begin_timestamp),
        "end_timestamp": period.end_timestamp,
        "end_timestamp_iso": _serialize_unix_timestamp(period.end_timestamp),
        "total_download_bytes": period.total_download_bytes,
        "total_upload_bytes": period.total_upload_bytes,
        "download_samples": [
            _serialize_wan_usage_sample(sample) for sample in period.download_samples
        ],
        "upload_samples": [
            _serialize_wan_usage_sample(sample) for sample in period.upload_samples
        ],
    }


def _serialize_wan_usage_view(view: FirewallaWanUsageView) -> JsonObjectType:
    """Serialize one WAN usage view for service responses."""
    return {
        "wan_uuid": view.wan_uuid,
        "wan_name": view.wan_name,
        "periods": [_serialize_wan_usage_period(period) for period in view.periods],
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
                f"More than one device matched {scope_target}; use the device MAC"
            )
        raise ServiceValidationError(f"No device matched {scope_target}")

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
                f"More than one user matched {scope_target}; use the user ID"
            )
        raise ServiceValidationError(f"No user matched {scope_target}")

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
            f"More than one group matched {scope_target}; use the group ID"
        )
    raise ServiceValidationError(f"No group matched {scope_target}")


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


async def _async_handle_get_usage_history(call: ServiceCall) -> JsonObjectType:
    """Return one normalized usage-history response from the local runtime."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )

    begin_input = cast(datetime, call.data[SERVICE_FIELD_USAGE_HISTORY_BEGIN])
    end_input = cast(datetime, call.data[SERVICE_FIELD_USAGE_HISTORY_END])
    begin_utc = dt_util.as_utc(begin_input)
    end_utc = dt_util.as_utc(end_input)
    time_zone = (
        begin_input.tzinfo or dt_util.get_time_zone(call.hass.config.time_zone) or UTC
    )
    time_zone_name = (
        getattr(time_zone, "key", None)
        or time_zone.tzname(begin_utc)
        or call.hass.config.time_zone
    )
    if end_utc <= begin_utc:
        raise ServiceValidationError("end must be after begin")

    target = _resolve_usage_history_target(
        entry,
        scope_kind=cast(str, call.data[SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND]),
        scope_target=cast(str, call.data[SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET]),
    )

    raw_app_ids = call.data.get(SERVICE_FIELD_USAGE_HISTORY_APP_IDS)
    app_ids = (
        tuple(str(app_id) for app_id in cast(list[str], raw_app_ids))
        if raw_app_ids is not None
        else None
    )

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
                app_ids=app_ids,
            )
        )
    except FirewallaApiError as err:
        raise HomeAssistantError(f"Could not read usage history: {err}") from err

    return {
        "config_entry_id": entry.entry_id,
        **_serialize_usage_history_view(
            usage_history,
            time_zone=time_zone,
            time_zone_name=time_zone_name,
        ),
    }


async def _async_handle_get_wan_usage(call: ServiceCall) -> JsonObjectType:
    """Return current-month WAN usage from the coordinator payload."""
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

    usage_views = entry.runtime_data.integration_manager.get_current_wan_usage(
        wan_uuid=wan.uuid if wan is not None else None
    )
    serialized_views: list[JsonValueType] = [
        _serialize_wan_usage_view(view) for view in usage_views
    ]

    return {
        "config_entry_id": entry.entry_id,
        "refreshed": refresh_requested,
        "wan": _serialize_wan_interface(wan) if wan is not None else None,
        "count": len(serialized_views),
        "results": serialized_views,
    }


async def _async_handle_get_network_interfaces(call: ServiceCall) -> JsonObjectType:
    """Return normalized network-interface summaries from the local runtime."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID),
        entry_name=call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME),
    )

    refresh_requested = cast(bool, call.data[SERVICE_FIELD_REFRESH])
    if refresh_requested:
        await _async_refresh_runtime_state(entry)

    network = _resolve_requested_network(
        entry,
        network_uuid=call.data.get(SERVICE_FIELD_NETWORK_UUID),
        network_name=call.data.get(SERVICE_FIELD_NETWORK_NAME),
    )

    try:
        network_views = (
            await entry.runtime_data.integration_manager.async_get_network_interfaces(
                network_uuid=network.uuid if network is not None else None,
            )
        )
    except FirewallaApiError as err:
        raise HomeAssistantError(f"Could not read network interfaces: {err}") from err

    serialized_views: list[JsonValueType] = [
        _serialize_network_segment_view(view) for view in network_views
    ]

    return {
        "config_entry_id": entry.entry_id,
        "refreshed": refresh_requested,
        "network": _serialize_network_segment(network) if network is not None else None,
        "count": len(serialized_views),
        "results": serialized_views,
    }


async def _async_handle_get_wan_usage_history(call: ServiceCall) -> JsonObjectType:
    """Return the last-12-month WAN usage view from the local runtime."""
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

    try:
        usage_views = (
            await entry.runtime_data.integration_manager.async_get_wan_usage_history(
                wan_uuid=wan.uuid if wan is not None else None
            )
        )
    except FirewallaApiError as err:
        raise HomeAssistantError(f"Could not read WAN usage history: {err}") from err

    serialized_views: list[JsonValueType] = [
        _serialize_wan_usage_view(view) for view in usage_views
    ]

    return {
        "config_entry_id": entry.entry_id,
        "wan": _serialize_wan_interface(wan) if wan is not None else None,
        "count": len(serialized_views),
        "results": serialized_views,
    }


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

    if not hass.services.has_service(DOMAIN, SERVICE_GET_NETWORK_INTERFACES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_NETWORK_INTERFACES,
            _async_handle_get_network_interfaces,
            schema=GET_NETWORK_INTERFACES_SCHEMA,
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

    if not hass.services.has_service(DOMAIN, SERVICE_GET_USAGE_HISTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_USAGE_HISTORY,
            _async_handle_get_usage_history,
            schema=GET_USAGE_HISTORY_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_WAN_USAGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_WAN_USAGE,
            _async_handle_get_wan_usage,
            schema=GET_WAN_USAGE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_WAN_USAGE_HISTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_WAN_USAGE_HISTORY,
            _async_handle_get_wan_usage_history,
            schema=GET_WAN_USAGE_HISTORY_SCHEMA,
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
    if hass.services.has_service(DOMAIN, SERVICE_GET_NETWORK_INTERFACES):
        hass.services.async_remove(DOMAIN, SERVICE_GET_NETWORK_INTERFACES)
    if hass.services.has_service(DOMAIN, SERVICE_RUN_INTERNET_SPEED_TEST):
        hass.services.async_remove(DOMAIN, SERVICE_RUN_INTERNET_SPEED_TEST)
    if hass.services.has_service(DOMAIN, SERVICE_GET_SPEED_TEST_RESULTS):
        hass.services.async_remove(DOMAIN, SERVICE_GET_SPEED_TEST_RESULTS)
    if hass.services.has_service(DOMAIN, SERVICE_GET_USAGE_HISTORY):
        hass.services.async_remove(DOMAIN, SERVICE_GET_USAGE_HISTORY)
    if hass.services.has_service(DOMAIN, SERVICE_GET_WAN_USAGE):
        hass.services.async_remove(DOMAIN, SERVICE_GET_WAN_USAGE)
    if hass.services.has_service(DOMAIN, SERVICE_GET_WAN_USAGE_HISTORY):
        hass.services.async_remove(DOMAIN, SERVICE_GET_WAN_USAGE_HISTORY)
    if hass.services.has_service(DOMAIN, SERVICE_GET_WAN_EVENTS):
        hass.services.async_remove(DOMAIN, SERVICE_GET_WAN_EVENTS)
    if hass.services.has_service(DOMAIN, SERVICE_PAUSE_RULE):
        hass.services.async_remove(DOMAIN, SERVICE_PAUSE_RULE)
    if hass.services.has_service(DOMAIN, SERVICE_RESUME_RULE):
        hass.services.async_remove(DOMAIN, SERVICE_RESUME_RULE)
