"""The Firewalla Local integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import FirewallaApiClient
from .const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_SYMMETRIC_KEY,
    DEFAULT_PAIRING_DEVICE_NAME,
    DOMAIN,
)
from .coordinator import (
    FirewallaConfigEntry,
    FirewallaDataUpdateCoordinator,
    FirewallaRuntimeData,
    async_migrate_entry_host,
)
from .managers import (
    FirewallaHostManager,
    FirewallaIntegrationManager,
    FirewallaRuleManager,
    FirewallaUserManager,
)
from .services import async_remove_services, async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Firewalla Local services."""
    del config
    await async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FirewallaConfigEntry) -> bool:
    """Set up Firewalla Local from a config entry."""
    await async_setup_services(hass)
    entry = await async_migrate_entry_host(hass, entry)
    client = FirewallaApiClient(
        session=async_get_clientsession(hass),
        host=entry.data[CONF_HOST],
        gid=entry.data[CONF_GID],
        eid=entry.data[CONF_EID],
        aid=entry.data[CONF_AID],
        symmetric_key=entry.data[CONF_SYMMETRIC_KEY],
        device_name=DEFAULT_PAIRING_DEVICE_NAME,
        timezone_name=hass.config.time_zone,
    )
    coordinator = FirewallaDataUpdateCoordinator(hass, entry, client)
    host_manager = FirewallaHostManager(coordinator, entry, client)
    integration_manager = FirewallaIntegrationManager(coordinator, entry, client)
    rule_manager = FirewallaRuleManager(coordinator, entry, client)
    user_manager = FirewallaUserManager(coordinator, entry, client)
    coordinator.attach_managers(
        host_manager=host_manager,
        integration_manager=integration_manager,
        rule_manager=rule_manager,
        user_manager=user_manager,
    )

    await coordinator.async_config_entry_first_refresh()
    await integration_manager.async_reconcile_rule_switch_entities(
        rule_manager.selected_templates
    )
    await integration_manager.async_reconcile_device_tracker_entities(
        host_manager.configured_device_tracker_macs
    )
    integration_manager.async_reconcile_tracked_client_devices(
        host_manager.configured_device_tracker_macs,
        host_manager.get_hosts(),
    )

    entry.runtime_data = FirewallaRuntimeData(
        client=client,
        coordinator=coordinator,
        host_manager=host_manager,
        integration_manager=integration_manager,
        rule_manager=rule_manager,
        user_manager=user_manager,
    )
    entry.async_on_unload(
        entry.add_update_listener(coordinator.async_handle_entry_reload_requested)
    )

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
        if not remaining_entries:
            async_remove_services(hass)

    return unloaded
