"""The Firewalla Local integration."""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.json import JsonObjectType

from .api import FirewallaApiClient
from .const import (
    CONF_AID,
    CONF_CONFIG_ENTRY_ID,
    CONF_CONFIG_ENTRY_NAME,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_SYMMETRIC_KEY,
    DEFAULT_PAIRING_DEVICE_NAME,
    DOMAIN,
    LEGACY_CONF_LOCAL_IP,
    LOGGER,
    SERVICE_GET_RUNTIME_INVENTORY,
)
from .coordinator import (
    FirewallaConfigEntry,
    FirewallaDataUpdateCoordinator,
    FirewallaRuntimeData,
)
from .runtime_inventory import (
    build_runtime_inventory_report,
    render_runtime_inventory_markdown,
)

PLATFORMS: list[Platform] = [Platform.SWITCH]
GET_RUNTIME_INVENTORY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(CONF_CONFIG_ENTRY_NAME): cv.string,
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
            raise ServiceValidationError("Config entry not found")
        if entry.domain != DOMAIN:
            raise ServiceValidationError(
                "Config entry does not belong to Firewalla Local"
            )
        if entry.runtime_data is None:
            raise ServiceValidationError("Config entry is not loaded")
        return entry

    if entry_name:
        matching_entries = [
            entry for entry in loaded_entries if entry.title == entry_name
        ]
        if not matching_entries:
            raise ServiceValidationError("Config entry name not found")
        if len(matching_entries) > 1:
            raise ServiceValidationError(
                "Config entry name is ambiguous; use config_entry_id"
            )
        return matching_entries[0]

    if len(loaded_entries) == 1:
        return loaded_entries[0]

    raise ServiceValidationError(
        "Multiple Firewalla entries are loaded; "
        "use config_entry_id or config_entry_name"
    )


async def _async_handle_get_runtime_inventory(call: ServiceCall) -> JsonObjectType:
    """Return the current runtime inventory as markdown and structured data."""
    entry = _get_loaded_entry(
        call.hass,
        entry_id=call.data.get(CONF_CONFIG_ENTRY_ID),
        entry_name=call.data.get(CONF_CONFIG_ENTRY_NAME),
    )
    runtime_payload = await entry.runtime_data.client.async_get_runtime_init_payload()
    runtime_snapshot = entry.runtime_data.client.build_runtime_snapshot(runtime_payload)
    report = build_runtime_inventory_report(
        runtime_payload,
        runtime_snapshot.policy_rules,
    )
    LOGGER.info("Generated runtime inventory for config entry %s", entry.entry_id)
    return {
        "config_entry_id": entry.entry_id,
        "inventory": cast(JsonObjectType, report),
        "markdown": render_runtime_inventory_markdown(report),
    }


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Firewalla Local services."""
    del config
    if not hass.services.has_service(DOMAIN, SERVICE_GET_RUNTIME_INVENTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_RUNTIME_INVENTORY,
            _async_handle_get_runtime_inventory,
            schema=GET_RUNTIME_INVENTORY_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: FirewallaConfigEntry) -> None:
    """Reload a config entry after mutable updates such as options changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_migrate_entry_host(
    hass: HomeAssistant, entry: FirewallaConfigEntry
) -> FirewallaConfigEntry:
    """Migrate legacy local_ip connection data to host."""
    if CONF_HOST in entry.data or LEGACY_CONF_LOCAL_IP not in entry.data:
        return entry

    updated_data = dict(entry.data)
    updated_data[CONF_HOST] = updated_data.pop(LEGACY_CONF_LOCAL_IP)
    hass.config_entries.async_update_entry(entry, data=updated_data)
    return entry


async def async_setup_entry(hass: HomeAssistant, entry: FirewallaConfigEntry) -> bool:
    """Set up Firewalla Local from a config entry."""
    entry = await _async_migrate_entry_host(hass, entry)
    client = FirewallaApiClient(
        session=async_get_clientsession(hass),
        host=entry.data[CONF_HOST],
        gid=entry.data[CONF_GID],
        eid=entry.data[CONF_EID],
        aid=entry.data[CONF_AID],
        symmetric_key=entry.data[CONF_SYMMETRIC_KEY],
        device_name=DEFAULT_PAIRING_DEVICE_NAME,
    )
    coordinator = FirewallaDataUpdateCoordinator(hass, entry, client)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = FirewallaRuntimeData(client=client, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: FirewallaConfigEntry) -> bool:
    """Unload a Firewalla Local config entry."""
    if not PLATFORMS:
        unloaded = True
    else:
        unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        remaining_entries = [
            config_entry
            for config_entry in hass.config_entries.async_entries(DOMAIN)
            if config_entry.entry_id != entry.entry_id
        ]
        if not remaining_entries and hass.services.has_service(
            DOMAIN, SERVICE_GET_RUNTIME_INVENTORY
        ):
            hass.services.async_remove(DOMAIN, SERVICE_GET_RUNTIME_INVENTORY)

    return unloaded
