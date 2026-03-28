"""Home Assistant service handling for Firewalla Local."""

from __future__ import annotations

from datetime import UTC, datetime
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
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_GET_RUNTIME_INVENTORY,
    SERVICE_GET_SPEED_TEST_RESULTS,
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
    TRANS_KEY_EXCEPTION_PAUSE_RULE_TIMING_CONFLICT,
    TRANS_KEY_EXCEPTION_RESUME_AT_IN_PAST,
    TRANS_KEY_EXCEPTION_RULE_TARGET_NOT_FOUND,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NAME_AMBIGUOUS,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NOT_FOUND,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_REQUIRED,
    TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_SELECTOR_CONFLICT,
    TRANS_KEY_EXCEPTION_WRONG_INTEGRATION_ENTRY,
    TRANS_PLACEHOLDER_DURATION,
    TRANS_PLACEHOLDER_RULE_TARGET,
    TRANS_PLACEHOLDER_WAN_NAME,
    TRANS_PLACEHOLDER_WAN_UUID,
)
from .coordinator import FirewallaConfigEntry
from .models import (
    FirewallaSpeedTestResult,
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


def _serialize_unix_timestamp(timestamp: int | None) -> str | None:
    """Serialize one optional Unix timestamp to UTC ISO format."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


def _serialize_wan_usage_sample(sample: FirewallaWanUsageSample) -> JsonObjectType:
    """Serialize one WAN usage sample for service responses."""
    return {
        "timestamp": sample.timestamp,
        "timestamp_iso": _serialize_unix_timestamp(sample.timestamp),
        "value": sample.value,
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
    if hass.services.has_service(DOMAIN, SERVICE_RUN_INTERNET_SPEED_TEST):
        hass.services.async_remove(DOMAIN, SERVICE_RUN_INTERNET_SPEED_TEST)
    if hass.services.has_service(DOMAIN, SERVICE_GET_SPEED_TEST_RESULTS):
        hass.services.async_remove(DOMAIN, SERVICE_GET_SPEED_TEST_RESULTS)
    if hass.services.has_service(DOMAIN, SERVICE_GET_WAN_USAGE):
        hass.services.async_remove(DOMAIN, SERVICE_GET_WAN_USAGE)
    if hass.services.has_service(DOMAIN, SERVICE_GET_WAN_USAGE_HISTORY):
        hass.services.async_remove(DOMAIN, SERVICE_GET_WAN_USAGE_HISTORY)
    if hass.services.has_service(DOMAIN, SERVICE_PAUSE_RULE):
        hass.services.async_remove(DOMAIN, SERVICE_PAUSE_RULE)
    if hass.services.has_service(DOMAIN, SERVICE_RESUME_RULE):
        hass.services.async_remove(DOMAIN, SERVICE_RESUME_RULE)
