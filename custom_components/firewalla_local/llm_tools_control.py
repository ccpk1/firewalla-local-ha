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

from typing import Any, Final, cast, override

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import llm

from .const import (
    ALARM_STATUS_ACTIVE,
    ALARM_STATUS_ARCHIVED,
    ALARM_TARGET_TYPES,
    DOMAIN,
    SERVICE_ARCHIVE_ALARMS,
    SERVICE_CREATE_RULE,
    SERVICE_DELETE_ALARMS,
    SERVICE_DELETE_HOST,
    SERVICE_DELETE_RULE,
    SERVICE_FIELD_ALARM_ID,
    SERVICE_FIELD_ALARM_STATUS,
    SERVICE_FIELD_ALARM_TARGET_TYPE,
    SERVICE_FIELD_ALARM_TARGET_VALUE,
    SERVICE_FIELD_ALL_HOSTS,
    SERVICE_FIELD_CLEAR,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIRM,
    SERVICE_FIELD_DNS_HOSTNAME,
    SERVICE_FIELD_DURATION,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_EXCEPTION_ID,
    SERVICE_FIELD_GROUP_ID,
    SERVICE_FIELD_GROUP_NAME,
    SERVICE_FIELD_HOST_DEVICE_TYPE,
    SERVICE_FIELD_HOST_MAC,
    SERVICE_FIELD_HOST_NAME,
    SERVICE_FIELD_MODE,
    SERVICE_FIELD_NETWORK_NAME,
    SERVICE_FIELD_NETWORK_UUID,
    SERVICE_FIELD_NEW_NAME,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_RESERVED_IPV4,
    SERVICE_FIELD_RULE_ID,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_SSID_PROFILE_ID,
    SERVICE_FIELD_TARGET_TYPE,
    SERVICE_FIELD_TARGET_VALUE,
    SERVICE_FIELD_USER_ID,
    SERVICE_FIELD_USER_NAME,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_MUTE_ALARM,
    SERVICE_PAUSE_RULE,
    SERVICE_RESUME_RULE,
    SERVICE_RUN_INTERNET_SPEED_TEST,
    SERVICE_SET_HOST_DEVICE_TYPE,
    SERVICE_SET_HOST_DHCP_RESERVATION,
    SERVICE_SET_HOST_DNS_HOSTNAME,
    SERVICE_SET_HOST_MEMBERSHIP,
    SERVICE_SET_HOST_NAME,
    SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_OFFLINE,
    SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_ONLINE,
    SERVICE_SET_SSID_PAUSED,
    SERVICE_UNMUTE_ALARM,
    SERVICE_WAKE_HOST,
    TARGET_KIND_ALARM,
    TARGET_KIND_HOST,
    TARGET_KIND_NETWORK,
    TARGET_KIND_RULE,
    TARGET_KIND_SILENCE,
    TARGET_KIND_SSID,
)
from .llm_tools_common import (
    CONTROL_INJECTION,
    DESTRUCTIVE_INJECTION,
    format_tool_name,
)
from .models import FirewallaNetworkKind

# Every tool here acts on the user's Firewalla box, not on Home Assistant, so
# `open_world` is true for all of them: the server the data comes from and the
# thing a control tool changes are both outside Home Assistant. A caller that
# treats these as closed-world would under-warn about what a call reaches.
_CONTROL_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=False,
    destructive=False,
    idempotent=True,
    open_world=True,
)

_DESTRUCTIVE_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=False,
    destructive=True,
    idempotent=True,
    open_world=True,
)

_NON_IDEMPOTENT_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=False,
    destructive=False,
    idempotent=False,
    open_world=True,
)

_HOST_MAC_DESCRIPTION: Final = (
    "Optional. The host's MAC address (from list_hosts). Provide this or host_name."
)

_HOST_NAME_DESCRIPTION: Final = (
    "Optional. The host's name. Provide this or host_mac; names must be "
)

# Every membership tool carries this. A membership change deletes the rules
# attached to the host -- confirmed by two captures, for both a group and a user
# target -- while leaving rules attached to a group or user untouched.
_MEMBERSHIP_RULE_WARNING: Final = (
    "DELETES the rules attached to this host, including rules you created, and "
    "they cannot be restored. Rules attached to groups or users are NOT affected."
)


class _FirewallaControlTool(llm.Tool):
    """Base class for a Firewalla Local control tool backed by a service."""

    integration = DOMAIN
    annotations = _CONTROL_ANNOTATIONS

    # Prepended at construction rather than written into each description, so a new
    # control tool cannot be added without the family block. The genuinely
    # destructive tools override this with `DESTRUCTIVE_INJECTION`.
    _injection: str = CONTROL_INJECTION

    _service: str
    # True for SupportsResponse.ONLY services (returns a payload); False for
    # SupportsResponse.NONE services (returns nothing).
    _returns_response: bool = False

    def __init__(self, *, entry_id: str) -> None:
        """Bind the tool to the config entry it was registered for."""
        self._entry_id = entry_id
        if self.description:
            self.description = f"{self._injection}\n\n{self.description}"

    def _args(self, tool_input: llm.ToolInput) -> dict[str, Any]:
        """Return tool args validated against the declared schema.

        The LLM provider validates args, but an MCP client can call directly, so
        validate here to turn a missing or unknown argument into a clean error
        instead of a bare KeyError.
        """
        return cast(dict[str, Any], self.parameters(tool_input.tool_args))

    @staticmethod
    def _host_target(tool_input: llm.ToolInput) -> dict[str, Any]:
        """Echo the host selector the caller supplied."""
        args = tool_input.tool_args
        return {
            "kind": TARGET_KIND_HOST,
            "id": args.get(SERVICE_FIELD_HOST_MAC),
            "name": args.get(SERVICE_FIELD_HOST_NAME),
        }

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
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        undo: str | None = None,
        warnings: list[str] | None = None,
        result: Any = None,
    ) -> llm.ToolResult:
        """Build the standard action-result envelope.

        ``before`` is the state observed before the action, when the tool read
        it. ``after`` is the state the action requested — a statement of intent,
        not a re-read of the box.
        """
        data: dict[str, Any] = {
            "status": status,
            "changed": changed,
            "target": target,
            "before": before,
            "after": after,
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

    name = format_tool_name("pause_rule")
    title = "Pause rule"
    description = (
        "Pause one firewall rule, either for a set time or until it is resumed. "
        "Resolve rule_id from list_rules. Fully reversible: `undo` is "
        "resume_rule.\n"
        "\n"
        "The rule is not deleted. Firewalla disables it in place and keeps its "
        "id, so resuming restores the same rule. Two modes:\n"
        "- **timed** -- pass `duration` or `resume_at`. The box stores a resume "
        "boundary and brings the rule back on its own.\n"
        "- **indefinite** -- pass neither. The rule stays off until "
        "resume_rule.\n"
        "\n"
        "Indefinite is the *same underlying state* as switching the rule off in "
        "the Firewalla app: one disabled rule with no resume boundary. The two "
        "are interchangeable and cannot be told apart afterwards. "
        "`list_rules` reports both as `is_paused: true`; its `pause_until` is "
        "what separates them -- a timestamp means the box will resume it, "
        "`null` means it will not.\n"
        "\n"
        "A rule pause applies to every host the rule governs, so pausing a "
        "group or user rule pauses it for all of that group's or user's hosts. "
        "Allow a short delay before the change takes effect on the wire."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_RULE_ID,
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
        args = self._args(tool_input)
        rule_id = args[SERVICE_FIELD_RULE_ID]
        target = {"kind": TARGET_KIND_RULE, "id": rule_id}
        before: dict[str, Any] | None = None
        after = {"enabled": False, "is_paused": True}
        if (manager := self._rule_manager(hass)) is not None:
            rule = next((r for r in manager.get_rules() if r.rule_id == rule_id), None)
            if rule is not None:
                before = {"enabled": rule.enabled, "is_paused": rule.is_paused}
                if rule.is_paused:
                    return self._result(
                        status="already_in_state",
                        changed=False,
                        target=target,
                        before=before,
                        after=before,
                    )

        await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied",
            changed=True,
            target=target,
            before=before,
            after=after,
            undo=f'firewalla_local__resume_rule(rule_id="{rule_id}")',
        )


class ResumeRuleTool(_FirewallaControlTool):
    """Resume one paused Firewalla firewall rule."""

    name = format_tool_name("resume_rule")
    title = "Resume rule"
    description = (
        "Resume one paused rule, clearing any resume boundary. This is the undo "
        "for pause_rule, and it works for both a timed pause and an indefinite "
        "one -- including a rule switched off in the Firewalla app, which is the "
        "same state.\n"
        "\n"
        "Firewalla re-enables the existing rule in place rather than creating a "
        "new one, so a rule id survives a pause/resume cycle and anything "
        "referencing it stays valid. Resuming an already-enabled rule is a "
        "no-op.\n"
        "\n"
        "After resuming, `list_rules` reports `enabled: true`, `is_paused: "
        "false` and `pause_until: null`. Allow a short delay before the change "
        "takes effect on the wire."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_RULE_ID,
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
        args = self._args(tool_input)
        rule_id = args[SERVICE_FIELD_RULE_ID]
        target = {"kind": TARGET_KIND_RULE, "id": rule_id}
        before: dict[str, Any] | None = None
        after = {"enabled": True, "is_paused": False}
        if (manager := self._rule_manager(hass)) is not None:
            rule = next((r for r in manager.get_rules() if r.rule_id == rule_id), None)
            if rule is not None:
                before = {"enabled": rule.enabled, "is_paused": rule.is_paused}
                if rule.enabled:
                    return self._result(
                        status="already_in_state",
                        changed=False,
                        target=target,
                        before=before,
                        after=before,
                    )

        await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied",
            changed=True,
            target=target,
            before=before,
            after=after,
            undo=f'firewalla_local__pause_rule(rule_id="{rule_id}")',
        )


class SetSsidPausedTool(_FirewallaControlTool):
    """Pause or resume one wireless SSID across all access points."""

    name = format_tool_name("set_ssid_paused")
    title = "Set SSID paused"
    description = (
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
        args = self._args(tool_input)
        profile_id = args[SERVICE_FIELD_SSID_PROFILE_ID]
        paused = args[SERVICE_FIELD_ENABLED]
        target = {"kind": TARGET_KIND_SSID, "id": profile_id}
        await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"paused": paused},
            undo=(
                "firewalla_local__set_ssid_paused"
                f'(ssid_profile_id="{profile_id}", enabled={not paused})'
            ),
        )


class SetHostNameTool(_FirewallaControlTool):
    """Rename one Firewalla host."""

    name = format_tool_name("set_host_name")
    title = "Set host name"
    description = (
        "Rename a host. Cosmetic and fully reversible. For a DNS name use "
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
                description="Required. The new display name for the host.",
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
        args = self._args(tool_input)
        target = self._host_target(tool_input)
        result = await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"host_name": args[SERVICE_FIELD_NEW_NAME]},
            result=result,
        )


class SetHostDnsHostnameTool(_FirewallaControlTool):
    """Set the DNS hostname for one Firewalla host."""

    name = format_tool_name("set_host_dns_hostname")
    title = "Set host DNS hostname"
    description = (
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
        args = self._args(tool_input)
        target = self._host_target(tool_input)
        result = await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"dns_hostname": args[SERVICE_FIELD_DNS_HOSTNAME]},
            result=result,
        )


class SetHostDeviceTypeTool(_FirewallaControlTool):
    """Set the Firewalla host device type."""

    name = format_tool_name("set_host_device_type")
    title = "Set host device type"
    description = (
        "Classify a host (desktop, phone, tablet, tv, …) so reports and "
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
                description="Required. The host device type to assign.",
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
        args = self._args(tool_input)
        target = self._host_target(tool_input)
        result = await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"host_device_type": args[SERVICE_FIELD_HOST_DEVICE_TYPE]},
            result=result,
        )


class SetHostDhcpReservationTool(_FirewallaControlTool):
    """Set or clear a DHCP reservation for one Firewalla host."""

    name = format_tool_name("set_host_dhcp_reservation")
    title = "Set host DHCP reservation"
    description = (
        "Give a host a fixed IP address (or return it to dynamic). Pair with "
        "list_hosts to find hosts without a reservation. Strong built-in "
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
            vol.Optional(
                SERVICE_FIELD_NETWORK_UUID,
                description=(
                    "Optional. The network to reserve in, when the address alone "
                    "is ambiguous across networks."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_NETWORK_NAME,
                description=(
                    "Optional. The network to reserve in, by name, when the "
                    "address alone is ambiguous across networks."
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
        args = self._args(tool_input)
        target = self._host_target(tool_input)
        result = await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={
                "mode": args[SERVICE_FIELD_MODE],
                "reserved_ipv4": args.get(SERVICE_FIELD_RESERVED_IPV4),
            },
            result=result,
        )


class _SetHostMembershipTool(_FirewallaControlTool):
    """Base for the four host-membership tools.

    A host holds exactly one membership, so each tool either sets that slot to
    a group or a user, or clears it. All four are destructive, because a
    membership change deletes the rules attached to the host: two captures on
    the dev box show the app sending `policy:delete` for every rule the host
    owned, then the tags write, in one batch. Rules attached to a group or a user
    are not affected, including the user the host is leaving.
    """

    annotations = _DESTRUCTIVE_ANNOTATIONS
    # Overrides the family block: this one cannot be undone.
    _injection: str = DESTRUCTIVE_INJECTION
    _returns_response = True

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Set or clear one host's membership."""
        args = self._args(tool_input)
        target = self._host_target(tool_input)
        result = await self._call_service(hass, llm_context, args)
        membership = (result or {}).get("membership") or {}
        removed = ((result or {}).get("host_rules") or {}).get("removed") or []
        return self._result(
            status="applied",
            changed=bool(membership.get("changed")),
            target=target,
            before=membership.get("before"),
            after=membership.get("after"),
            undo=self._undo(),
            warnings=self._warnings(removed),
            result=result,
        )

    def _warnings(self, removed: list[Any]) -> list[str]:
        """Name what the call deleted, so the model reports it rather than glosses."""
        if not removed:
            return []
        count = len(removed)
        noun = "rule" if count == 1 else "rules"
        return [
            f"Deleted {count} {noun} attached to this host (ids: "
            f"{', '.join(str(rule_id) for rule_id in removed)}). "
            "They cannot be restored."
        ]

    def _undo(self) -> str | None:
        """Return the inverse membership tool, or None when nothing to undo."""
        return None


class SetHostGroupTool(_SetHostMembershipTool):
    """Assign a host to one Firewalla group."""

    name = format_tool_name("set_host_group")
    title = "Set host group"
    description = (
        "Put a host in one Firewalla group, so it follows that group's rules. "
        "A host has exactly one membership, so this replaces any group or user "
        "it currently belongs to, as the app does. Resolve the group from "
        "get_system_overview (include 'identifiers') first; group and user names "
        "are separate, and a user's name is never a valid group. "
        + _MEMBERSHIP_RULE_WARNING
    )
    _service = SERVICE_SET_HOST_MEMBERSHIP

    def _undo(self) -> str | None:
        return format_tool_name("clear_host_group")

    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_NAME,
                description=(
                    "Optional. The group's name. Provide this or group_id. Use "
                    "group_id when two groups share a name."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_ID,
                description=(
                    "Optional. The group's Firewalla id. Provide this or group_name."
                ),
            ): str,
        }
    )


class ClearHostGroupTool(_SetHostMembershipTool):
    """Remove a host's group or user membership."""

    name = format_tool_name("clear_host_group")
    title = "Clear host group"
    description = (
        "Remove a host's group or user membership so it belongs to neither and "
        "no longer inherits that group's or user's rules. Use it to release a "
        "host, or to undo set_host_group or set_host_user. " + _MEMBERSHIP_RULE_WARNING
    )
    _service = SERVICE_SET_HOST_MEMBERSHIP

    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_CLEAR,
                description="Optional. Always true for this tool.",
                default=True,
            ): bool,
        }
    )


class SetHostUserTool(_SetHostMembershipTool):
    """Assign a host to one Firewalla user."""

    name = format_tool_name("set_host_user")
    title = "Set host user"
    description = (
        "Assign a host to one Firewalla user, so it follows that user's rules. "
        "A host has exactly one membership, so this replaces any group or user "
        "it currently belongs to. Resolve the user from get_system_overview "
        "(include 'identifiers') first; users and groups are separate collections "
        "and a group's name is never a valid user. " + _MEMBERSHIP_RULE_WARNING
    )
    _service = SERVICE_SET_HOST_MEMBERSHIP

    def _undo(self) -> str | None:
        return format_tool_name("clear_host_user")

    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_NAME,
                description=(
                    "Optional. The user's name. Provide this or user_id. Use "
                    "user_id when two users share a name."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_ID,
                description=(
                    "Optional. The user's Firewalla id. Provide this or user_name."
                ),
            ): str,
        }
    )


class ClearHostUserTool(_SetHostMembershipTool):
    """Remove a host's user or group membership."""

    name = format_tool_name("clear_host_user")
    title = "Clear host user"
    description = (
        "Remove a host's user or group membership so it belongs to neither and "
        "no longer inherits that user's rules. The user and their rules are left "
        "untouched and keep covering their other hosts; only this host leaves. "
        "Use it to release a host, or to undo set_host_user or set_host_group. "
        + _MEMBERSHIP_RULE_WARNING
    )
    _service = SERVICE_SET_HOST_MEMBERSHIP

    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC, description=_HOST_MAC_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME, description=_HOST_NAME_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_CLEAR,
                description="Optional. Always true for this tool.",
                default=True,
            ): bool,
        }
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
        args = self._args(tool_input)
        target = self._host_target(tool_input)
        result = await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"enabled": args[SERVICE_FIELD_ENABLED]},
            result=result,
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

    name = format_tool_name("set_host_notify_when_next_online")
    title = "Set host notify when next online"
    description = (
        "Turn the 'notify when this host comes online' preference on or off. "
        "Notification preference only, no network effect. Reversible."
    )
    _service = SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_ONLINE


class SetHostNotifyWhenNextOfflineTool(_SetHostNotifyTool):
    """Enable or disable notify-when-next-offline for one host."""

    name = format_tool_name("set_host_notify_when_next_offline")
    title = "Set host notify when next offline"
    description = (
        "Turn the 'notify when this host drops offline' preference on or off. "
        "Notification preference only, no network effect. Reversible."
    )
    _service = SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_OFFLINE


class WakeHostTool(_FirewallaControlTool):
    """Send a Wake-on-LAN packet to one Firewalla host."""

    name = format_tool_name("wake_host")
    title = "Wake host"
    description = (
        "Send a Wake-on-LAN packet to wake a host. Sends one packet and makes "
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
        target = self._host_target(tool_input)
        result = await self._call_service(hass, llm_context, self._args(tool_input))
        return self._result(
            status="applied", changed=False, target=target, result=result
        )


class RunInternetSpeedTestTool(_FirewallaControlTool):
    """Run an on-demand internet speed test on one WAN."""

    name = format_tool_name("run_internet_speed_test")
    title = "Run internet speed test"
    description = (
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
        args = self._args(tool_input)
        target = {
            "kind": TARGET_KIND_NETWORK,
            "network_kind": FirewallaNetworkKind.WAN.value,
            "id": args.get(SERVICE_FIELD_WAN_UUID),
            "name": args.get(SERVICE_FIELD_WAN_NAME),
        }
        result = await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied", changed=False, target=target, result=result
        )


class SetAlarmMutedTool(_FirewallaControlTool):
    """Mute or unmute an alarm silence."""

    name = format_tool_name("set_alarm_muted")
    title = "Set alarm muted"
    description = (
        "Create or remove a silence so matching alarms stop alerting. This does "
        "NOT block traffic (use block_alarm_target) and does not clear the alarm "
        "(use archive_alarm). Scope is required: an 'all' scope silences the "
        "target for every host. Reversible."
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
                SERVICE_FIELD_ALARM_TARGET_TYPE,
                description="Required. What to silence.",
            ): vol.In(ALARM_TARGET_TYPES),
            vol.Optional(
                SERVICE_FIELD_ALARM_TARGET_VALUE,
                description=(
                    "Optional. What the type refers to: the alarm type to "
                    "silence (e.g. 'ALARM_VIDEO') when alarm_target_type is "
                    "'alarm_type', or the domain or IP when it is 'domain' or "
                    "'ip'. Required unless alarm_id supplies it."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_MAC,
                description="Optional. Scope by host MAC.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME,
                description="Optional. Scope by host name.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_ID,
                description="Optional. Scope by group id.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_NAME,
                description="Optional. Scope by group name.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_ID,
                description="Optional. Scope by user id.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_NAME,
                description="Optional. Scope by user name.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_NETWORK_UUID,
                description="Optional. Scope by network UUID.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_NETWORK_NAME,
                description="Optional. Scope by network name.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_ALL_HOSTS,
                default=False,
                description=(
                    "Optional. Apply to every host. The wide scope must be "
                    "stated, because an empty scope means every host on the wire."
                ),
            ): bool,
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
        args = self._args(tool_input)
        alarm_id = args.get(SERVICE_FIELD_ALARM_ID)
        target = {
            "kind": TARGET_KIND_SILENCE,
            "id": alarm_id,
            "name": args.get(SERVICE_FIELD_ALARM_TARGET_VALUE),
        }
        await self._call_service(hass, llm_context, args)
        undo = (
            f'firewalla_local__unmute_alarm(alarm_id="{alarm_id}")'
            if alarm_id
            else None
        )
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"muted": True},
            undo=undo,
        )


class UnmuteAlarmTool(_FirewallaControlTool):
    """Remove an alarm silence."""

    name = format_tool_name("unmute_alarm")
    title = "Unmute alarm"
    description = (
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
                description=(
                    "Optional. The silence id to remove directly. From "
                    "`get_alarms` with `include_exceptions: true`."
                ),
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
        args = self._args(tool_input)
        target = {
            "kind": TARGET_KIND_SILENCE,
            "id": args.get(SERVICE_FIELD_ALARM_ID),
        }
        await self._call_service(hass, llm_context, args)
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"muted": False},
        )


class BlockAlarmTargetTool(_FirewallaControlTool):
    """Block an alarm's target by creating an ordinary policy rule."""

    name = format_tool_name("block_alarm_target")
    title = "Block alarm target"
    description = (
        "Block the domain/IP that caused an alarm by creating a firewall rule, "
        "recording the alarm id on it. Provide either `alarm_id`, or "
        "`target_type` and `target_value` (optionally with `scope_kind` / "
        "`scope_target`) to widen or narrow where the block applies. This "
        "actually blocks traffic (unlike set_alarm_muted). Reversible with "
        "unblock_alarm_target."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_ALARM_ID,
                description=(
                    "Optional. Derive the blocked target and host scope from "
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
                SERVICE_FIELD_HOST_MAC,
                description="Optional. Scope by host MAC.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME,
                description="Optional. Scope by host name.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_ID,
                description="Optional. Scope by group id.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_NAME,
                description="Optional. Scope by group name.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_ID,
                description="Optional. Scope by user id.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_NAME,
                description="Optional. Scope by user name.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_NETWORK_UUID,
                description="Optional. Scope by network UUID.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_NETWORK_NAME,
                description="Optional. Scope by network name.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_ALL_HOSTS,
                default=False,
                description=(
                    "Optional. Apply to every host. The wide scope must be "
                    "stated, because an empty scope means every host on the wire."
                ),
            ): bool,
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
        args = self._args(tool_input)
        result = await self._call_service(hass, llm_context, args)
        rule_id = result.get("rule_id") if isinstance(result, dict) else None
        target = {
            "kind": TARGET_KIND_RULE,
            "id": rule_id,
            "name": args.get(SERVICE_FIELD_TARGET_VALUE),
        }
        undo = (
            f'firewalla_local__unblock_alarm_target(rule_id="{rule_id}")'
            if rule_id
            else None
        )
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"blocked": True},
            undo=undo,
            result=result,
        )


class UnblockAlarmTargetTool(_FirewallaControlTool):
    """Remove the block rule created for an alarm by deleting it."""

    name = format_tool_name("unblock_alarm_target")
    title = "Unblock alarm target"
    description = (
        "Remove a firewall block created for an alarm by deleting its rule. This "
        "is the undo for block_alarm_target and removes only that rule."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_RULE_ID,
                description="Required. The rule id to remove (from list_rules).",
            ): str,
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
        data = self._args(tool_input)
        rule_id = data[SERVICE_FIELD_RULE_ID]
        data[SERVICE_FIELD_CONFIRM] = True
        result = await self._call_service(hass, llm_context, data)
        target = {"kind": TARGET_KIND_RULE, "id": rule_id}
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"blocked": False},
            result=result,
        )


class ArchiveAlarmTool(_FirewallaControlTool):
    """Archive one alarm without deleting it."""

    name = format_tool_name("archive_alarm")
    title = "Archive alarm"
    description = (
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
        alarm_id = self._args(tool_input)[SERVICE_FIELD_ALARM_ID]
        data = {SERVICE_FIELD_ALARM_ID: alarm_id}
        await self._call_service(hass, llm_context, data)
        target = {"kind": TARGET_KIND_ALARM, "id": alarm_id}
        return self._result(
            status="applied",
            changed=True,
            target=target,
            after={"archived": True},
            warnings=["no un-archive"],
        )


class ArchiveAllAlarmsTool(_FirewallaControlTool):
    """Archive every active alarm (bulk)."""

    name = format_tool_name("archive_all_alarms")
    title = "Archive all alarms"
    description = (
        "Destructive bulk action: archive every active alarm at once. Records "
        "are kept but move to the archive, and there is no un-archive. Prefer "
        "archive_alarm for a single alarm."
    )
    parameters = vol.Schema({})
    annotations = _DESTRUCTIVE_ANNOTATIONS
    # Overrides the family block: this one cannot be undone.
    _injection: str = DESTRUCTIVE_INJECTION
    _service = SERVICE_ARCHIVE_ALARMS

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Archive every active alarm."""
        await self._call_service(
            hass,
            llm_context,
            {SERVICE_FIELD_ALARM_STATUS: ALARM_STATUS_ACTIVE},
        )
        return self._result(
            status="applied",
            changed=True,
            # No single alarm identity, so the set is named in `after` rather than
            # invented as a target id.
            target={"kind": TARGET_KIND_ALARM, "id": None},
            after={"archived": ALARM_STATUS_ACTIVE},
            warnings=["bulk action", "no un-archive"],
        )


class DeleteAlarmTool(_FirewallaControlTool):
    """Permanently delete one alarm."""

    name = format_tool_name("delete_alarm")
    title = "Delete alarm"
    description = (
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
    # Overrides the family block: this one cannot be undone.
    _injection: str = DESTRUCTIVE_INJECTION
    _service = SERVICE_DELETE_ALARMS

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Delete a single alarm."""
        args = self._args(tool_input)
        alarm_id = args[SERVICE_FIELD_ALARM_ID]
        data = {
            SERVICE_FIELD_ALARM_ID: alarm_id,
            SERVICE_FIELD_CONFIRM: args[SERVICE_FIELD_CONFIRM],
        }
        await self._call_service(hass, llm_context, data)
        return self._result(
            status="applied",
            changed=True,
            target={"kind": TARGET_KIND_ALARM, "id": alarm_id},
            after={"deleted": True},
            warnings=["irreversible"],
        )


class DeleteAlarmsTool(_FirewallaControlTool):
    """Permanently delete all active or all archived alarms."""

    name = format_tool_name("delete_all_alarms")
    title = "Delete all alarms"
    description = (
        "Destructive bulk action: permanently delete every alarm in the chosen "
        "set. This is irreversible and cannot be undone. Deleting all active "
        "alarms destroys alarms that are not archived; deleting all archived "
        "alarms destroys the retained history."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_ALARM_STATUS,
                description=(
                    "Required. Which set to delete permanently: 'active' or 'archived'."
                ),
            ): vol.In((ALARM_STATUS_ACTIVE, ALARM_STATUS_ARCHIVED)),
            vol.Required(
                SERVICE_FIELD_CONFIRM,
                description="Required. Set true to confirm the bulk delete.",
            ): bool,
        }
    )
    annotations = _DESTRUCTIVE_ANNOTATIONS
    # Overrides the family block: this one cannot be undone.
    _injection: str = DESTRUCTIVE_INJECTION
    _service = SERVICE_DELETE_ALARMS

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Delete all alarms in the chosen set."""
        args = self._args(tool_input)
        alarm_status = args[SERVICE_FIELD_ALARM_STATUS]
        data = {
            SERVICE_FIELD_ALARM_STATUS: alarm_status,
            SERVICE_FIELD_CONFIRM: args[SERVICE_FIELD_CONFIRM],
        }
        await self._call_service(hass, llm_context, data)
        return self._result(
            status="applied",
            changed=True,
            target={"kind": TARGET_KIND_ALARM, "id": None},
            after={"deleted": alarm_status},
            warnings=["bulk action", "irreversible"],
        )


class DeleteHostTool(_FirewallaControlTool):
    """Permanently delete one Firewalla host record."""

    name = format_tool_name("delete_host")
    title = "Delete host"
    description = (
        "Destructive: permanently delete a host record from Firewalla. This "
        "is irreversible. It removes the host's identity, reservations, and "
        "history; the host reappears as a new host if it rejoins the network."
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
    # Overrides the family block: this one cannot be undone.
    _injection: str = DESTRUCTIVE_INJECTION
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
        args = self._args(tool_input)
        host_mac = args[SERVICE_FIELD_HOST_MAC]
        data = {
            SERVICE_FIELD_HOST_MAC: host_mac,
            SERVICE_FIELD_CONFIRM: args[SERVICE_FIELD_CONFIRM],
            SERVICE_FIELD_REFRESH: True,
        }
        result = await self._call_service(hass, llm_context, data)
        return self._result(
            status="applied",
            changed=True,
            target={"kind": TARGET_KIND_HOST, "id": host_mac},
            after={"deleted": True},
            warnings=["irreversible"],
            result=result,
        )


class DeleteRuleTool(_FirewallaControlTool):
    """Permanently delete one policy rule."""

    name = format_tool_name("delete_rule")
    title = "Delete rule"
    description = (
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
    # Overrides the family block: this one cannot be undone.
    _injection: str = DESTRUCTIVE_INJECTION
    _service = SERVICE_DELETE_RULE

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Delete one rule."""
        args = self._args(tool_input)
        rule_id = args[SERVICE_FIELD_RULE_ID]
        data = {
            SERVICE_FIELD_RULE_ID: rule_id,
            SERVICE_FIELD_CONFIRM: args[SERVICE_FIELD_CONFIRM],
        }
        await self._call_service(hass, llm_context, data)
        return self._result(
            status="applied",
            changed=True,
            target={"kind": TARGET_KIND_RULE, "id": rule_id},
            after={"deleted": True},
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
#
# The four membership tools are here because a membership change deletes the rules
# attached to the host and nothing can restore them. The membership slot itself
# is reversible, which is why each set tool names its clear tool as `undo`, but the
# deleted rules are gone.
_DESTRUCTIVE_TOOL_CLASSES: Final = (
    ArchiveAllAlarmsTool,
    DeleteAlarmTool,
    DeleteAlarmsTool,
    DeleteHostTool,
    DeleteRuleTool,
    SetHostGroupTool,
    ClearHostGroupTool,
    SetHostUserTool,
    ClearHostUserTool,
)


def build_control_tools(*, entry_id: str, include_destructive: bool) -> list[llm.Tool]:
    """Return the control tools bound to one config entry.

    Destructive tools are included only when ``include_destructive`` is true.
    """
    tool_classes: tuple[type[_FirewallaControlTool], ...] = _CONTROL_TOOL_CLASSES
    if include_destructive:
        tool_classes = (*tool_classes, *_DESTRUCTIVE_TOOL_CLASSES)
    return [tool_class(entry_id=entry_id) for tool_class in tool_classes]
