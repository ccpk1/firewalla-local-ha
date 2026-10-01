"""LLM control tools for Firewalla Local.

Imported only by ``llm_api.py``, which is imported only when LLM tools are
supported, so the Core 2026.10-only ``homeassistant.helpers.llm`` names are never
imported on older Home Assistant.

Each control tool delegates to an admin-gated Firewalla Local service and
returns the documented action-result envelope. Control tools therefore require
an admin caller; the caller's permissions flow through the service call. The
tool injects its own ``config_entry_id``.
"""

from __future__ import annotations

from typing import Any, Final, override

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import llm

from .const import (
    DOMAIN,
    SERVICE_ARCHIVE_ALARMS,
    SERVICE_CREATE_RULE,
    SERVICE_DELETE_ALARMS,
    SERVICE_DELETE_HOST,
    SERVICE_DELETE_RULE,
    SERVICE_FIELD_ALARM_ID,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIRM,
    SERVICE_FIELD_DNS_HOSTNAME,
    SERVICE_FIELD_DURATION,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_EXCEPTION_ID,
    SERVICE_FIELD_HOST_DEVICE_TYPE,
    SERVICE_FIELD_HOST_MAC,
    SERVICE_FIELD_HOST_NAME,
    SERVICE_FIELD_MODE,
    SERVICE_FIELD_NEW_NAME,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_RESERVED_IPV4,
    SERVICE_FIELD_RULE_ID,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_FIELD_SCOPE_KIND,
    SERVICE_FIELD_SCOPE_TARGET,
    SERVICE_FIELD_SSID_PROFILE_ID,
    SERVICE_FIELD_TARGET_TYPE,
    SERVICE_FIELD_TARGET_VALUE,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_MUTE_ALARM,
    SERVICE_PAUSE_RULE,
    SERVICE_RESUME_RULE,
    SERVICE_RUN_INTERNET_SPEED_TEST,
    SERVICE_SET_HOST_DEVICE_TYPE,
    SERVICE_SET_HOST_DHCP_RESERVATION,
    SERVICE_SET_HOST_DNS_HOSTNAME,
    SERVICE_SET_HOST_NAME,
    SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_OFFLINE,
    SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_ONLINE,
    SERVICE_SET_SSID_PAUSED,
    SERVICE_UNMUTE_ALARM,
    SERVICE_WAKE_HOST,
)

_PREFERRED_PREFIX: Final = (
    "Purpose-built Firewalla Local tool — prefer it over any generic "
    "firewalla_local service/action tool another client may expose. "
)

_CONTROL_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=False,
    destructive=False,
    idempotent=True,
    open_world=False,
)

_DESTRUCTIVE_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=False,
    destructive=True,
    idempotent=True,
    open_world=False,
)

_NON_IDEMPOTENT_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=False,
    destructive=False,
    idempotent=False,
    open_world=False,
)

_HOST_MAC_DESCRIPTION: Final = (
    "Optional. The device's MAC address (from list_hosts). Provide this or host_name."
)

_HOST_NAME_DESCRIPTION: Final = (
    "Optional. The device's host name. Provide this or host_mac; names must be "
    "unique among hosts."
)


class _FirewallaControlTool(llm.Tool):
    """Base class for a Firewalla Local control tool backed by a service."""

    integration = DOMAIN
    annotations = _CONTROL_ANNOTATIONS

    _service: str
    # True for SupportsResponse.ONLY services (returns a payload); False for
    # SupportsResponse.NONE services (returns nothing).
    _returns_response: bool = False

    def __init__(self, *, entry_id: str) -> None:
        """Bind the tool to the config entry it was registered for."""
        self._entry_id = entry_id

    async def _call_service(
        self,
        hass: HomeAssistant,
        llm_context: llm.LLMContext,
        data: dict[str, Any],
    ) -> Any:
        """Call the backing service with this entry bound."""
        return await hass.services.async_call(
            DOMAIN,
            self._service,
            {**data, SERVICE_FIELD_CONFIG_ENTRY_ID: self._entry_id},
            blocking=True,
            return_response=self._returns_response,
            context=llm_context.context,
        )

    def _result(
        self,
        *,
        status: str,
        changed: bool,
        target: dict[str, Any],
        undo: str | None = None,
        warnings: list[str] | None = None,
        result: Any = None,
    ) -> llm.ToolResult:
        """Build the standard action-result envelope."""
        data: dict[str, Any] = {
            "status": status,
            "changed": changed,
            "target": target,
            "undo": undo,
            "warnings": warnings or [],
        }
        if result is not None:
            data["result"] = result
        return llm.ToolResult(data=data)

    def _rule_manager(self, hass: HomeAssistant) -> Any:
        """Return the rule manager for this entry, when loaded."""
        entry = hass.config_entries.async_get_entry(self._entry_id)
        runtime_data = getattr(entry, "runtime_data", None)
        return getattr(runtime_data, "rule_manager", None)


class PauseRuleTool(_FirewallaControlTool):
    """Pause one Firewalla firewall rule, optionally until a resume time."""

    name = "firewalla_local__pause_rule"
    title = "Pause rule"
    description = _PREFERRED_PREFIX + (
        "Temporarily disable one firewall rule. Resolve rule_target from "
        "list_rules. Fully reversible: undo with resume_rule. Pausing an "
        "already-paused rule is a no-op."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_RULE_TARGET,
                description="Required. The rule id from list_rules.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_DURATION,
                description=(
                    "Optional. How long to pause, e.g. '30m', '4h', '2d 4h'. "
                    "Provide this, resume_at, or neither (pauses until resumed)."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_RULE_RESUME_AT,
                description=(
                    "Optional. Local date-time when the rule should resume. "
                    "Provide this, duration, or neither."
                ),
            ): cv.datetime,
        }
    )
    _service = SERVICE_PAUSE_RULE

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Pause one rule, reporting a no-op when it is already paused."""
        rule_id = tool_input.tool_args[SERVICE_FIELD_RULE_TARGET]
        target = {"kind": "rule", "id": rule_id}
        if (manager := self._rule_manager(hass)) is not None:
            rule = next((r for r in manager.get_rules() if r.rule_id == rule_id), None)
            if rule is not None and (rule.is_paused or not rule.enabled):
                return self._result(
                    status="already_in_state", changed=False, target=target
                )

        await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(
            status="applied",
            changed=True,
            target=target,
            undo=f'firewalla_local__resume_rule(rule_target="{rule_id}")',
        )


class ResumeRuleTool(_FirewallaControlTool):
    """Resume one paused Firewalla firewall rule."""

    name = "firewalla_local__resume_rule"
    title = "Resume rule"
    description = _PREFERRED_PREFIX + (
        "Resume (re-enable) one firewall rule. This is the undo for pause_rule. "
        "Resuming an already-running rule is a no-op."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_RULE_TARGET,
                description="Required. The rule id from list_rules.",
            ): str,
        }
    )
    _service = SERVICE_RESUME_RULE

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Resume one rule, reporting a no-op when it is already enabled."""
        rule_id = tool_input.tool_args[SERVICE_FIELD_RULE_TARGET]
        target = {"kind": "rule", "id": rule_id}
        if (manager := self._rule_manager(hass)) is not None:
            rule = next((r for r in manager.get_rules() if r.rule_id == rule_id), None)
            if rule is not None and rule.enabled:
                return self._result(
                    status="already_in_state", changed=False, target=target
                )

        await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(
            status="applied",
            changed=True,
            target=target,
            undo=f'firewalla_local__pause_rule(rule_target="{rule_id}")',
        )


class SetSsidPausedTool(_FirewallaControlTool):
    """Pause or resume one wireless SSID across all access points."""

    name = "firewalla_local__set_ssid_paused"
    title = "Set SSID paused"
    description = _PREFERRED_PREFIX + (
        "Pause or resume one WiFi network (SSID) across every access point. Wide "
        "blast radius: every client on that SSID is disconnected, possibly "
        "including the client or Home Assistant host making the request. Resolve "
        "ssid_profile_id from get_wireless_status. Fully reversible."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_SSID_PROFILE_ID,
                description=("Required. The SSID profile id from get_wireless_status."),
            ): str,
            vol.Required(
                SERVICE_FIELD_ENABLED,
                description="Required. True to pause the SSID, false to resume it.",
            ): bool,
        }
    )
    _service = SERVICE_SET_SSID_PAUSED

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Pause or resume one SSID."""
        profile_id = tool_input.tool_args[SERVICE_FIELD_SSID_PROFILE_ID]
        paused = tool_input.tool_args[SERVICE_FIELD_ENABLED]
        target = {"kind": "ssid", "id": profile_id}
        await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(
            status="applied",
            changed=True,
            target=target,
            undo=(
                "firewalla_local__set_ssid_paused"
                f'(ssid_profile_id="{profile_id}", enabled={not paused})'
            ),
        )


class SetHostNameTool(_FirewallaControlTool):
    """Rename one Firewalla host."""

    name = "firewalla_local__set_host_name"
    title = "Set host name"
    description = _PREFERRED_PREFIX + (
        "Rename a device. Cosmetic and fully reversible. For a DNS name use "
        "set_host_dns_hostname instead."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
            vol.Required(
                SERVICE_FIELD_NEW_NAME,
                description="Required. The new display name for the device.",
            ): str,
        }
    )
    _service = SERVICE_SET_HOST_NAME
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Rename one host."""
        target = self._host_target(tool_input)
        result = await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(
            status="applied", changed=True, target=target, result=result
        )

    @staticmethod
    def _host_target(tool_input: llm.ToolInput) -> dict[str, Any]:
        """Echo the host selector the caller supplied."""
        args = tool_input.tool_args
        return {
            "kind": "host",
            "id": args.get(SERVICE_FIELD_HOST_MAC),
            "name": args.get(SERVICE_FIELD_HOST_NAME),
        }


class SetHostDnsHostnameTool(_FirewallaControlTool):
    """Set the DNS hostname for one Firewalla host."""

    name = "firewalla_local__set_host_dns_hostname"
    title = "Set host DNS hostname"
    description = _PREFERRED_PREFIX + (
        "Set the per-host DNS name used for local name resolution. Can break "
        "resolution for that host if set incorrectly. Reversible. Not the display "
        "name (use set_host_name)."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
            vol.Required(
                SERVICE_FIELD_DNS_HOSTNAME,
                description="Required. The DNS hostname to assign.",
            ): str,
        }
    )
    _service = SERVICE_SET_HOST_DNS_HOSTNAME
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Set a host DNS hostname."""
        target = SetHostNameTool._host_target(tool_input)
        result = await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(
            status="applied", changed=True, target=target, result=result
        )


class SetHostDeviceTypeTool(_FirewallaControlTool):
    """Set the device-type classification for one Firewalla host."""

    name = "firewalla_local__set_host_device_type"
    title = "Set host device type"
    description = _PREFERRED_PREFIX + (
        "Classify a device (desktop, phone, tablet, tv, …) so reports and "
        "summaries make sense. Cosmetic and reversible."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
            vol.Required(
                SERVICE_FIELD_HOST_DEVICE_TYPE,
                description="Required. The device type to assign.",
            ): str,
        }
    )
    _service = SERVICE_SET_HOST_DEVICE_TYPE
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Set a host device type."""
        target = SetHostNameTool._host_target(tool_input)
        result = await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(
            status="applied", changed=True, target=target, result=result
        )


class SetHostDhcpReservationTool(_FirewallaControlTool):
    """Set or clear a DHCP reservation for one Firewalla host."""

    name = "firewalla_local__set_host_dhcp_reservation"
    title = "Set host DHCP reservation"
    description = _PREFERRED_PREFIX + (
        "Give a device a fixed IP address (or return it to dynamic). Pair with "
        "list_hosts to find devices without a reservation. Strong built-in "
        "validation rejects conflicting, in-use, or out-of-range addresses. "
        "Reversible by setting mode back to 'dynamic'."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
            vol.Required(
                SERVICE_FIELD_MODE,
                description=(
                    "Required. 'static' to reserve an address, 'dynamic' to release it."
                ),
            ): vol.In(("static", "dynamic")),
            vol.Optional(
                SERVICE_FIELD_RESERVED_IPV4,
                description=(
                    "Optional. The IPv4 address to reserve (required for 'static')."
                ),
            ): str,
        }
    )
    _service = SERVICE_SET_HOST_DHCP_RESERVATION
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Set or clear a DHCP reservation."""
        target = SetHostNameTool._host_target(tool_input)
        result = await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(
            status="applied", changed=True, target=target, result=result
        )


class _SetHostNotifyTool(_FirewallaControlTool):
    """Base for the host notification-preference toggles."""

    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Set one host notification preference."""
        target = SetHostNameTool._host_target(tool_input)
        result = await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(
            status="applied", changed=True, target=target, result=result
        )

    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
            vol.Required(
                SERVICE_FIELD_ENABLED,
                description=(
                    "Required. True to enable the notification, false to disable it."
                ),
            ): bool,
        }
    )


class SetHostNotifyWhenNextOnlineTool(_SetHostNotifyTool):
    """Enable or disable notify-when-next-online for one host."""

    name = "firewalla_local__set_host_notify_when_next_online"
    title = "Set host notify when next online"
    description = _PREFERRED_PREFIX + (
        "Turn the 'notify when this device comes online' preference on or off. "
        "Notification preference only, no network effect. Reversible."
    )
    _service = SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_ONLINE


class SetHostNotifyWhenNextOfflineTool(_SetHostNotifyTool):
    """Enable or disable notify-when-next-offline for one host."""

    name = "firewalla_local__set_host_notify_when_next_offline"
    title = "Set host notify when next offline"
    description = _PREFERRED_PREFIX + (
        "Turn the 'notify when this device drops offline' preference on or off. "
        "Notification preference only, no network effect. Reversible."
    )
    _service = SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_OFFLINE


class WakeHostTool(_FirewallaControlTool):
    """Send a Wake-on-LAN packet to one Firewalla host."""

    name = "firewalla_local__wake_host"
    title = "Wake host"
    description = _PREFERRED_PREFIX + (
        "Send a Wake-on-LAN packet to wake a device. Sends one packet and makes "
        "no persistent change; not idempotent, since each call sends a packet."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
        }
    )
    annotations = _NON_IDEMPOTENT_ANNOTATIONS
    _service = SERVICE_WAKE_HOST
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Send a Wake-on-LAN packet."""
        target = SetHostNameTool._host_target(tool_input)
        result = await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(
            status="applied", changed=False, target=target, result=result
        )


class RunInternetSpeedTestTool(_FirewallaControlTool):
    """Run an on-demand internet speed test on one WAN."""

    name = "firewalla_local__run_internet_speed_test"
    title = "Run internet speed test"
    description = _PREFERRED_PREFIX + (
        "Run a new internet speed test now. Consumes WAN bandwidth and takes "
        "time; for recent results prefer get_speed_tests. Not idempotent — each "
        "call runs a new test."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_WAN_UUID,
                description="Optional. A WAN UUID. Omit to use the only WAN.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_WAN_NAME,
                description="Optional. A WAN display name. Omit to use the only WAN.",
            ): str,
        }
    )
    annotations = _NON_IDEMPOTENT_ANNOTATIONS
    _service = SERVICE_RUN_INTERNET_SPEED_TEST
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Run a speed test."""
        args = tool_input.tool_args
        target = {
            "kind": "wan",
            "id": args.get(SERVICE_FIELD_WAN_UUID),
            "name": args.get(SERVICE_FIELD_WAN_NAME),
        }
        result = await self._call_service(hass, llm_context, dict(args))
        return self._result(
            status="applied", changed=False, target=target, result=result
        )


class SetAlarmMutedTool(_FirewallaControlTool):
    """Mute or unmute an alarm silence."""

    name = "firewalla_local__set_alarm_muted"
    title = "Set alarm muted"
    description = _PREFERRED_PREFIX + (
        "Create or remove a silence so matching alarms stop alerting. This does "
        "NOT block traffic (use block_alarm_target) and does not clear the alarm "
        "(use archive_alarm). Scope is required: an 'all' scope silences the "
        "target for every device. Reversible."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_ALARM_ID,
                description=(
                    "Optional. The alarm to derive the silence target from (from "
                    "get_alarms)."
                ),
            ): str,
            vol.Required(
                SERVICE_FIELD_TARGET_TYPE,
                description="Required. What to silence.",
            ): vol.In(("alarm_type", "domain", "ip")),
            vol.Optional(
                SERVICE_FIELD_TARGET_VALUE,
                description=(
                    "Optional. The domain or IP to silence (required unless "
                    "alarm_id supplies it)."
                ),
            ): str,
            vol.Required(
                SERVICE_FIELD_SCOPE_KIND,
                description=(
                    "Required. Where the silence applies. Choose narrowly — "
                    "'all' silences for every device."
                ),
            ): vol.In(("device", "group", "user", "network", "all")),
            vol.Optional(
                SERVICE_FIELD_SCOPE_TARGET,
                description=(
                    "Optional. The scope value for the chosen kind (a MAC for "
                    "device, etc.)."
                ),
            ): str,
            vol.Required(
                SERVICE_FIELD_DURATION,
                description="Required. How long the silence lasts.",
            ): vol.In(("1h", "today", "always")),
        }
    )
    _service = SERVICE_MUTE_ALARM

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Mute matching alarms."""
        alarm_id = tool_input.tool_args.get(SERVICE_FIELD_ALARM_ID)
        target = {
            "kind": "silence",
            "id": alarm_id,
            "name": tool_input.tool_args.get(SERVICE_FIELD_TARGET_VALUE),
        }
        await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        undo = (
            f'firewalla_local__unmute_alarm(alarm_id="{alarm_id}")'
            if alarm_id
            else None
        )
        return self._result(
            status="applied",
            changed=True,
            target=target,
            undo=undo,
        )


class UnmuteAlarmTool(_FirewallaControlTool):
    """Remove an alarm silence."""

    name = "firewalla_local__unmute_alarm"
    title = "Unmute alarm"
    description = _PREFERRED_PREFIX + (
        "Remove a silence so matching alarms alert again. This is the undo for "
        "set_alarm_muted. Provide either the alarm id or the silence (exception) "
        "id."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_ALARM_ID,
                description="Optional. The alarm whose silence to remove.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_EXCEPTION_ID,
                description="Optional. The silence id to remove directly.",
            ): str,
        }
    )
    _service = SERVICE_UNMUTE_ALARM

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Remove an alarm silence."""
        target = {
            "kind": "silence",
            "id": tool_input.tool_args.get(SERVICE_FIELD_ALARM_ID),
        }
        await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        return self._result(status="applied", changed=True, target=target)


class BlockAlarmTargetTool(_FirewallaControlTool):
    """Block an alarm's target by creating an ordinary policy rule."""

    name = "firewalla_local__block_alarm_target"
    title = "Block alarm target"
    description = _PREFERRED_PREFIX + (
        "Block the domain/IP that caused an alarm by creating a firewall rule, "
        "recording the alarm id on it. This actually blocks traffic (unlike "
        "set_alarm_muted). Reversible with unblock_alarm_target."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_ALARM_ID,
                description=(
                    "Optional. Derive the blocked target and device scope from "
                    "this alarm. Provide this or target_type and target_value."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_TARGET_TYPE,
                description=(
                    "Optional. Required with target_value when alarm_id is omitted."
                ),
            ): vol.In(("dns", "ip", "mac")),
            vol.Optional(
                SERVICE_FIELD_TARGET_VALUE,
                description="Optional. The domain, IP, or MAC to block.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_SCOPE_KIND,
                description="Optional. Where the block applies.",
            ): vol.In(("device", "network", "all")),
            vol.Optional(
                SERVICE_FIELD_SCOPE_TARGET,
                description="Optional. The scope value for the chosen kind.",
            ): str,
        }
    )
    _service = SERVICE_CREATE_RULE
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Create a block rule for an alarm's target."""
        result = await self._call_service(hass, llm_context, dict(tool_input.tool_args))
        rule_id = result.get("rule_id") if isinstance(result, dict) else None
        target = {
            "kind": "rule",
            "id": rule_id,
            "name": tool_input.tool_args.get(SERVICE_FIELD_TARGET_VALUE),
        }
        undo = (
            f'firewalla_local__unblock_alarm_target(rule_id="{rule_id}")'
            if rule_id
            else None
        )
        return self._result(
            status="applied", changed=True, target=target, undo=undo, result=result
        )


class UnblockAlarmTargetTool(_FirewallaControlTool):
    """Remove the block rule created for an alarm by deleting it."""

    name = "firewalla_local__unblock_alarm_target"
    title = "Unblock alarm target"
    description = _PREFERRED_PREFIX + (
        "Remove a firewall block created for an alarm by deleting its rule. This "
        "is the undo for block_alarm_target and removes only that rule."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_RULE_ID,
                description="Required. The rule id to remove (from list_rules).",
            ): str,
            vol.Optional(
                SERVICE_FIELD_CONFIRM,
                description="Required. Set true to confirm deleting the rule.",
            ): bool,
        }
    )
    _service = SERVICE_DELETE_RULE
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Delete the alarm block rule."""
        rule_id = tool_input.tool_args[SERVICE_FIELD_RULE_ID]
        data = dict(tool_input.tool_args)
        data.setdefault(SERVICE_FIELD_CONFIRM, True)
        result = await self._call_service(hass, llm_context, data)
        target = {"kind": "rule", "id": rule_id}
        return self._result(
            status="applied", changed=True, target=target, result=result
        )


class ArchiveAlarmTool(_FirewallaControlTool):
    """Archive one alarm without deleting it."""

    name = "firewalla_local__archive_alarm"
    title = "Archive alarm"
    description = _PREFERRED_PREFIX + (
        "Dismiss one alarm from the active list while keeping the record. This "
        "does NOT stop future matching alarms (use set_alarm_muted). Note there "
        "is no un-archive if you change your mind."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_ALARM_ID,
                description="Required. The alarm id to archive (from get_alarms).",
            ): str,
        }
    )
    _service = SERVICE_ARCHIVE_ALARMS

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Archive a single alarm."""
        alarm_id = tool_input.tool_args[SERVICE_FIELD_ALARM_ID]
        data = {SERVICE_FIELD_MODE: "this", SERVICE_FIELD_ALARM_ID: alarm_id}
        await self._call_service(hass, llm_context, data)
        target = {"kind": "alarm", "id": alarm_id}
        return self._result(
            status="applied", changed=True, target=target, warnings=["no un-archive"]
        )


class ArchiveAllAlarmsTool(_FirewallaControlTool):
    """Archive every active alarm (bulk)."""

    name = "firewalla_local__archive_all_alarms"
    title = "Archive all alarms"
    description = _PREFERRED_PREFIX + (
        "Destructive bulk action: archive every active alarm at once. Records "
        "are kept but move to the archive, and there is no un-archive. Prefer "
        "archive_alarm for a single alarm."
    )
    parameters = vol.Schema({})
    annotations = _DESTRUCTIVE_ANNOTATIONS
    _service = SERVICE_ARCHIVE_ALARMS

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Archive every active alarm."""
        await self._call_service(hass, llm_context, {SERVICE_FIELD_MODE: "all_active"})
        return self._result(
            status="applied",
            changed=True,
            target={"kind": "alarm", "id": "all_active"},
            warnings=["bulk action", "no un-archive"],
        )


class DeleteAlarmTool(_FirewallaControlTool):
    """Permanently delete one alarm."""

    name = "firewalla_local__delete_alarm"
    title = "Delete alarm"
    description = _PREFERRED_PREFIX + (
        "Destructive: permanently delete one alarm record. This is "
        "irreversible. To dismiss without destroying the record use "
        "archive_alarm."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_ALARM_ID,
                description="Required. The alarm id to delete (from get_alarms).",
            ): str,
            vol.Required(
                SERVICE_FIELD_CONFIRM,
                description="Required. Set true to confirm the irreversible delete.",
            ): bool,
        }
    )
    annotations = _DESTRUCTIVE_ANNOTATIONS
    _service = SERVICE_DELETE_ALARMS

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Delete a single alarm."""
        alarm_id = tool_input.tool_args[SERVICE_FIELD_ALARM_ID]
        data = {
            SERVICE_FIELD_MODE: "this",
            SERVICE_FIELD_ALARM_ID: alarm_id,
            SERVICE_FIELD_CONFIRM: True,
        }
        await self._call_service(hass, llm_context, data)
        return self._result(
            status="applied",
            changed=True,
            target={"kind": "alarm", "id": alarm_id},
            warnings=["irreversible"],
        )


class DeleteAlarmsTool(_FirewallaControlTool):
    """Permanently delete all active or all archived alarms."""

    name = "firewalla_local__delete_all_alarms"
    title = "Delete all alarms"
    description = _PREFERRED_PREFIX + (
        "Destructive bulk action: permanently delete every alarm in the chosen "
        "set. This is irreversible and cannot be undone. Deleting all active "
        "alarms destroys alarms that are not archived; deleting all archived "
        "alarms destroys the retained history."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_MODE,
                description="Required. Which set to delete permanently.",
            ): vol.In(("all_active", "all_archived")),
            vol.Required(
                SERVICE_FIELD_CONFIRM,
                description="Required. Set true to confirm the bulk delete.",
            ): bool,
        }
    )
    annotations = _DESTRUCTIVE_ANNOTATIONS
    _service = SERVICE_DELETE_ALARMS

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Delete all alarms in the chosen set."""
        mode = tool_input.tool_args[SERVICE_FIELD_MODE]
        data = {SERVICE_FIELD_MODE: mode, SERVICE_FIELD_CONFIRM: True}
        await self._call_service(hass, llm_context, data)
        return self._result(
            status="applied",
            changed=True,
            target={"kind": "alarm", "id": mode},
            warnings=["bulk action", "irreversible"],
        )


class DeleteHostTool(_FirewallaControlTool):
    """Permanently delete one Firewalla host record."""

    name = "firewalla_local__delete_host"
    title = "Delete host"
    description = _PREFERRED_PREFIX + (
        "Destructive: permanently delete a device record from Firewalla. This "
        "is irreversible. It removes the host's identity, reservations, and "
        "history; the device reappears as a new host if it rejoins the network."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_HOST_MAC,
                description="Required. The MAC address of the host to delete.",
            ): str,
            vol.Required(
                SERVICE_FIELD_CONFIRM,
                description="Required. Set true to confirm the irreversible delete.",
            ): bool,
        }
    )
    annotations = _DESTRUCTIVE_ANNOTATIONS
    _service = SERVICE_DELETE_HOST
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Delete one host record."""
        host_mac = tool_input.tool_args[SERVICE_FIELD_HOST_MAC]
        data = {
            SERVICE_FIELD_HOST_MAC: host_mac,
            SERVICE_FIELD_CONFIRM: True,
            SERVICE_FIELD_REFRESH: True,
        }
        result = await self._call_service(hass, llm_context, data)
        return self._result(
            status="applied",
            changed=True,
            target={"kind": "host", "id": host_mac},
            warnings=["irreversible"],
            result=result,
        )


class DeleteRuleTool(_FirewallaControlTool):
    """Permanently delete one policy rule."""

    name = "firewalla_local__delete_rule"
    title = "Delete rule"
    description = _PREFERRED_PREFIX + (
        "Destructive: permanently delete a firewall rule. This is irreversible. "
        "To disable a rule reversibly use pause_rule instead. Resolve rule_id "
        "from list_rules."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_RULE_ID,
                description="Required. The rule id to delete (from list_rules).",
            ): str,
            vol.Required(
                SERVICE_FIELD_CONFIRM,
                description="Required. Set true to confirm the irreversible delete.",
            ): bool,
        }
    )
    annotations = _DESTRUCTIVE_ANNOTATIONS
    _service = SERVICE_DELETE_RULE

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Delete one rule."""
        rule_id = tool_input.tool_args[SERVICE_FIELD_RULE_ID]
        data = {SERVICE_FIELD_RULE_ID: rule_id, SERVICE_FIELD_CONFIRM: True}
        await self._call_service(hass, llm_context, data)
        return self._result(
            status="applied",
            changed=True,
            target={"kind": "rule", "id": rule_id},
            warnings=["irreversible"],
        )


_CONTROL_TOOL_CLASSES: Final = (
    PauseRuleTool,
    ResumeRuleTool,
    SetSsidPausedTool,
    SetHostNameTool,
    SetHostDnsHostnameTool,
    SetHostDeviceTypeTool,
    SetHostDhcpReservationTool,
    SetHostNotifyWhenNextOnlineTool,
    SetHostNotifyWhenNextOfflineTool,
    WakeHostTool,
    RunInternetSpeedTestTool,
    SetAlarmMutedTool,
    UnmuteAlarmTool,
    BlockAlarmTargetTool,
    UnblockAlarmTargetTool,
    ArchiveAlarmTool,
)

# Destructive tools are registered only in the "full" mode. They are
# irreversible (no undo) or bulk, so they require an explicit, informed opt-in.
_DESTRUCTIVE_TOOL_CLASSES: Final = (
    ArchiveAllAlarmsTool,
    DeleteAlarmTool,
    DeleteAlarmsTool,
    DeleteHostTool,
    DeleteRuleTool,
)


def build_control_tools(*, entry_id: str, include_destructive: bool) -> list[llm.Tool]:
    """Return the control tools bound to one config entry.

    Destructive tools are included only when ``include_destructive`` is true.
    """
    tool_classes: tuple[type[_FirewallaControlTool], ...] = _CONTROL_TOOL_CLASSES
    if include_destructive:
        tool_classes = (*tool_classes, *_DESTRUCTIVE_TOOL_CLASSES)
    return [tool_class(entry_id=entry_id) for tool_class in tool_classes]
