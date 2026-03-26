"""Home Assistant service handling for Firewalla Local."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonObjectType

from .const import (
    DOMAIN,
    LOGGER,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIG_ENTRY_NAME,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_GET_RUNTIME_INVENTORY,
    SERVICE_PAUSE_RULE,
    SERVICE_RESUME_RULE,
    TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_AMBIGUOUS,
    TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_NOT_FOUND,
    TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_FOUND,
    TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_LOADED,
    TRANS_KEY_EXCEPTION_INVALID_DURATION,
    TRANS_KEY_EXCEPTION_MULTIPLE_ENTRIES_LOADED,
    TRANS_KEY_EXCEPTION_PAUSE_RULE_TIMING_CONFLICT,
    TRANS_KEY_EXCEPTION_RESUME_AT_IN_PAST,
    TRANS_KEY_EXCEPTION_RULE_TARGET_NOT_FOUND,
    TRANS_KEY_EXCEPTION_WRONG_INTEGRATION_ENTRY,
    TRANS_PLACEHOLDER_DURATION,
    TRANS_PLACEHOLDER_RULE_TARGET,
)
from .coordinator import FirewallaConfigEntry
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
    if hass.services.has_service(DOMAIN, SERVICE_PAUSE_RULE):
        hass.services.async_remove(DOMAIN, SERVICE_PAUSE_RULE)
    if hass.services.has_service(DOMAIN, SERVICE_RESUME_RULE):
        hass.services.async_remove(DOMAIN, SERVICE_RESUME_RULE)
