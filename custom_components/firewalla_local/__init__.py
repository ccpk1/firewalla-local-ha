"""The Firewalla Local integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import FirewallaApiClient
from .const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_SYMMETRIC_KEY,
    DEFAULT_LLM_TOOL_MODE,
    DEFAULT_PAIRING_DEVICE_NAME,
    DOMAIN,
    LLM_TOOL_MODE_OFF,
    LOGGER,
    MIN_LLM_TOOLS_HA_VERSION,
)
from .coordinator import (
    FirewallaConfigEntry,
    FirewallaDataUpdateCoordinator,
    FirewallaRuntimeData,
    async_migrate_entry_host,
    get_enabled_network_entities,
    get_enabled_ssid_entities,
    get_llm_tool_mode,
)
from .helpers.llm_support import llm_tools_supported
from .managers import (
    FirewallaAlarmManager,
    FirewallaFlowManager,
    FirewallaHostManager,
    FirewallaIntegrationManager,
    FirewallaRuleManager,
    FirewallaUserManager,
    FirewallaWirelessManager,
)
from .services import async_remove_services, async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
]


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _async_setup_llm_api(hass: HomeAssistant, entry: FirewallaConfigEntry) -> None:
    """Register the Firewalla Local LLM API when supported and enabled.

    Nothing is registered on Home Assistant Core older than the LLM tool
    contract, and the module that imports the Core 2026.10-only LLM names is
    imported lazily so it is never evaluated there.
    """
    mode = get_llm_tool_mode(entry.options)
    if mode == LLM_TOOL_MODE_OFF:
        return
    if not llm_tools_supported():
        if mode != DEFAULT_LLM_TOOL_MODE:
            LOGGER.warning(
                "LLM tool mode %r requires Home Assistant Core %d.%d or newer; "
                "no LLM tools were registered",
                mode,
                *MIN_LLM_TOOLS_HA_VERSION,
            )
        return

    # The AI tools are optional, so a failure here must never take the whole
    # integration down with it. The version guard above covers the known Core
    # boundary only; this contains unknown failures (a Core contract change, a
    # defect in a tool module) on any version.
    try:
        from .llm_api import async_register_firewalla_api

        unregister = async_register_firewalla_api(hass, entry)
    except Exception:
        LOGGER.exception(
            "Failed to register Firewalla Local AI tools; the integration "
            "continues without them"
        )
        return

    entry.async_on_unload(unregister)


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
    alarm_manager = FirewallaAlarmManager(coordinator, entry, client)
    user_manager = FirewallaUserManager(coordinator, entry, client)
    wireless_manager = FirewallaWirelessManager(coordinator, entry, client)
    flow_manager = FirewallaFlowManager(coordinator, entry, client)
    coordinator.attach_managers(
        host_manager=host_manager,
        integration_manager=integration_manager,
        rule_manager=rule_manager,
        user_manager=user_manager,
        wireless_manager=wireless_manager,
        alarm_manager=alarm_manager,
        flow_manager=flow_manager,
    )

    await coordinator.async_config_entry_first_refresh()
    await integration_manager.async_reconcile_rule_switch_entities(
        rule_manager.selected_templates
    )
    await integration_manager.async_reconcile_device_tracker_entities(
        host_manager.configured_device_tracker_macs
    )
    await integration_manager.async_reconcile_speed_test_sensor_entities(
        tuple(wan.uuid for wan in integration_manager.get_available_wans())
    )
    if get_enabled_network_entities(entry.options):
        await integration_manager.async_reconcile_network_entities(
            tuple(network.uuid for network in integration_manager.get_networks())
        )
    else:
        await integration_manager.async_reconcile_network_entities(())
    if get_enabled_ssid_entities(entry.options):
        await integration_manager.async_reconcile_ssid_entities(
            tuple(
                profile.profile_uuid for profile in wireless_manager.get_ssid_profiles()
            )
        )
    else:
        await integration_manager.async_reconcile_ssid_entities(())
    await integration_manager.async_reconcile_ap_entities(
        tuple(ap.asset_id for ap in wireless_manager.get_access_points())
    )
    integration_manager.async_reconcile_ap_devices(wireless_manager.get_access_points())
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
        wireless_manager=wireless_manager,
        alarm_manager=alarm_manager,
        flow_manager=flow_manager,
    )
    entry.async_on_unload(
        entry.add_update_listener(coordinator.async_handle_entry_reload_requested)
    )

    _async_setup_llm_api(hass, entry)

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
