"""LLM read tools for Firewalla Local.

Imported only by ``llm_api.py``, which is imported only when LLM tools are
supported, so the Core 2026.10-only ``homeassistant.helpers.llm`` names below
are never imported on older Home Assistant.

Each read tool delegates to an existing Firewalla Local service and wraps the
service payload in the documented response envelope. The tool injects its own
``config_entry_id`` so the caller never selects a Firewalla setup.
"""

from __future__ import annotations

from typing import Any, Final, cast, override

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import llm

from .const import (
    DOMAIN,
    SERVICE_FIELD_ALARM_TYPE,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CURRENT_PERIODS,
    SERVICE_FIELD_DETAIL,
    SERVICE_FIELD_HISTORY_COUNT,
    SERVICE_FIELD_HISTORY_PERIOD,
    SERVICE_FIELD_INCLUDE,
    SERVICE_FIELD_INCLUDE_ARCHIVED,
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_NETWORK_NAME,
    SERVICE_FIELD_NETWORK_UUID,
    SERVICE_FIELD_OFFSET,
    SERVICE_FIELD_REFRESH,
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
    SERVICE_GET_ALARMS,
    SERVICE_GET_HOST_NAME_MAPPING,
    SERVICE_GET_INTERNET_QUALITY_REPORT,
    SERVICE_GET_NETWORK_SEGMENT_REPORT,
    SERVICE_GET_NETWORK_SEGMENT_USAGE,
    SERVICE_GET_RULES,
    SERVICE_GET_SPEED_TEST_RESULTS,
    SERVICE_GET_TIME_USAGE_REPORT,
    SERVICE_GET_WAN_DATA_USAGE,
    SERVICE_GET_WAN_EVENTS,
    SERVICE_GET_WIRELESS_STATUS,
)

# Every read tool is a bounded, read-only query against the user's own box.
_READ_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=False,
)

_PREFERRED_PREFIX: Final = (
    "Purpose-built Firewalla Local tool — prefer it over any generic "
    "firewalla_local service/action tool another client may expose. "
)

_REFRESH_DESCRIPTION: Final = (
    "Optional. Defaults to true. Poll the Firewalla box for current data before "
    "building the result; this is slower and usually unnecessary when a recent "
    "refresh already happened. Set false to read the last snapshot."
)

_NETWORK_UUID_DESCRIPTION: Final = (
    "Optional. A Firewalla network UUID (from list_hosts / get_network_config) "
    "for a deterministic match. Provide this or network_name."
)

_NETWORK_NAME_DESCRIPTION: Final = (
    "Optional. A Firewalla network display name for interactive use. Provide "
    "this or network_uuid."
)

_WAN_UUID_DESCRIPTION: Final = (
    "Optional. A Firewalla WAN UUID for a deterministic match. Omit to use the "
    "only WAN when there is one."
)

_WAN_NAME_DESCRIPTION: Final = (
    "Optional. A Firewalla WAN display name. Omit to use the only WAN when "
    "there is one."
)


class _FirewallaReadTool(llm.Tool):
    """Base class for a Firewalla Local read tool backed by a service."""

    integration = DOMAIN
    annotations = _READ_ANNOTATIONS

    _service: str
    _response_type: str

    def __init__(self, *, entry_id: str) -> None:
        """Bind the tool to the config entry it was registered for."""
        self._entry_id = entry_id

    def _args(self, tool_input: llm.ToolInput) -> dict[str, Any]:
        """Return tool args validated against the declared schema.

        The LLM provider validates args, but an MCP client can call directly, so
        validate here to turn a missing or unknown argument into a clean error
        instead of a bare KeyError.
        """
        return cast(dict[str, Any], self.parameters(tool_input.tool_args))

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Call the backing service and return the wrapped payload."""
        service_data = self._args(tool_input)
        service_data[SERVICE_FIELD_CONFIG_ENTRY_ID] = self._entry_id
        result = await hass.services.async_call(
            DOMAIN,
            self._service,
            service_data,
            blocking=True,
            return_response=True,
            context=llm_context.context,
        )
        return llm.ToolResult(
            data={
                "result": result,
                "meta": {"response_type": self._response_type},
            },
        )


class ListHostsTool(_FirewallaReadTool):
    """List Firewalla hosts (devices) with identity and IP assignment."""

    name = "firewalla_local__list_hosts"
    title = "List hosts"
    description = _PREFERRED_PREFIX + (
        "List the devices on your Firewalla network with their name, device "
        "type, IP address, and DNS/DHCP identity. Use it to find a host before "
        "renaming it or setting a DHCP reservation. Refreshing first polls the "
        "box and is slower than reading the last snapshot."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_REFRESH,
                default=True,
                description=(
                    "Optional. Defaults to true. Poll the Firewalla box for "
                    "current host data; set false to read the last snapshot "
                    "faster."
                ),
            ): bool,
        }
    )
    _service = SERVICE_GET_HOST_NAME_MAPPING
    _response_type = "hosts"


class ListRulesTool(_FirewallaReadTool):
    """List Firewalla policy rules with their current state."""

    name = "firewalla_local__list_rules"
    title = "List rules"
    description = _PREFERRED_PREFIX + (
        "List your Firewalla firewall rules with id, name, action, "
        "enabled/paused state, target, scope, and any originating alarm. Use it "
        "to resolve the rule target that pause_rule and resume_rule require."
    )
    parameters = vol.Schema({})
    _service = SERVICE_GET_RULES
    _response_type = "rules"


class GetNetworkConfigTool(_FirewallaReadTool):
    """Return configuration-oriented detail for one network segment."""

    name = "firewalla_local__get_network_config"
    title = "Get network config"
    description = _PREFERRED_PREFIX + (
        "Show how a network (LAN/VLAN) is configured: addressing, gateway, DNS, "
        "DHCP range, and ports. Use it for network structure. For per-device "
        "traffic use get_network_usage."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_NETWORK_UUID, description=_NETWORK_UUID_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_NETWORK_NAME, description=_NETWORK_NAME_DESCRIPTION
            ): str,
            vol.Optional(SERVICE_FIELD_REFRESH, description=_REFRESH_DESCRIPTION): bool,
        }
    )
    _service = SERVICE_GET_NETWORK_SEGMENT_REPORT
    _response_type = "network_config"


class GetNetworkUsageTool(_FirewallaReadTool):
    """Return windowed usage: top talkers, apps, and categories."""

    name = "firewalla_local__get_network_usage"
    title = "Get network usage"
    description = _PREFERRED_PREFIX + (
        "Answer 'what is eating my bandwidth?' with windowed top talkers, apps, "
        "and categories for one network. Note: windowed WAN usage is not "
        "available; use get_wan_usage for WAN totals."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_NETWORK_UUID, description=_NETWORK_UUID_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_NETWORK_NAME, description=_NETWORK_NAME_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_WINDOW,
                description=(
                    "Optional. Activity window to report. Defaults to the "
                    "service default when omitted."
                ),
            ): vol.In(
                (
                    "last_60_minutes",
                    "last_24_hours",
                    "last_30_days",
                    "last_12_months",
                )
            ),
            vol.Optional(
                SERVICE_FIELD_TOP_N,
                description=(
                    "Optional. Limit how many top device/app/category ranking "
                    "rows are returned. Defaults to 5."
                ),
            ): int,
            vol.Optional(
                SERVICE_FIELD_INCLUDE,
                description=(
                    "Optional. Add raw metric sample sections for the selected "
                    "window. Allowed: 'series'."
                ),
            ): vol.All(cv.ensure_list, [vol.In(("series",))]),
            vol.Optional(SERVICE_FIELD_REFRESH, description=_REFRESH_DESCRIPTION): bool,
        }
    )
    _service = SERVICE_GET_NETWORK_SEGMENT_USAGE
    _response_type = "network_usage"


class GetWanUsageTool(_FirewallaReadTool):
    """Return WAN/internet data totals over time."""

    name = "firewalla_local__get_wan_usage"
    title = "Get WAN usage"
    description = _PREFERRED_PREFIX + (
        "Answer 'how much internet data have I used?' with WAN download/upload "
        "totals and, optionally, history and subperiod breakdowns. This is WAN "
        "totals, not per-device usage (see get_network_usage)."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_WAN_UUID, description=_WAN_UUID_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_WAN_NAME, description=_WAN_NAME_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_INCLUDE,
                description=(
                    "Optional. Add history and/or subperiod breakdown sections. "
                    "Allowed: 'history', 'subperiods'."
                ),
            ): vol.All(cv.ensure_list, [vol.In(("history", "subperiods"))]),
            vol.Optional(
                SERVICE_FIELD_CURRENT_PERIODS,
                description=(
                    "Optional. Current-period totals to include. Allowed: "
                    "'month', 'week', 'day'."
                ),
            ): vol.All(cv.ensure_list, [vol.In(("month", "week", "day"))]),
            vol.Optional(
                SERVICE_FIELD_HISTORY_PERIOD,
                description=(
                    "Optional. Period granularity for history. Allowed: 'month', "
                    "'week', 'day'."
                ),
            ): vol.In(("month", "week", "day")),
            vol.Optional(
                SERVICE_FIELD_HISTORY_COUNT,
                description=(
                    "Optional. Number of history periods to return. Defaults to 0."
                ),
            ): vol.All(int, vol.Range(min=0, max=366)),
            vol.Optional(SERVICE_FIELD_REFRESH, description=_REFRESH_DESCRIPTION): bool,
        }
    )
    _service = SERVICE_GET_WAN_DATA_USAGE
    _response_type = "wan_usage"


class GetWanEventsTool(_FirewallaReadTool):
    """Return WAN health events (outages and status changes)."""

    name = "firewalla_local__get_wan_events"
    title = "Get WAN events"
    description = _PREFERRED_PREFIX + (
        "Answer 'why did my internet drop?' with WAN link events such as outages "
        "and status changes. For volume over time use get_wan_usage."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_WAN_UUID, description=_WAN_UUID_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_WAN_NAME, description=_WAN_NAME_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_LIMIT,
                description="Optional. Maximum events to return. Defaults to 100.",
            ): int,
            vol.Optional(
                SERVICE_FIELD_OFFSET,
                description="Optional. Skip this many events. Defaults to 0.",
            ): int,
        }
    )
    _service = SERVICE_GET_WAN_EVENTS
    _response_type = "wan_events"


class GetUserUsageTool(_FirewallaReadTool):
    """Return time-based usage for one person, group, or device."""

    name = "firewalla_local__get_user_usage"
    title = "Get user usage"
    description = _PREFERRED_PREFIX + (
        "Answer 'how much time did a person/device spend online?' with a "
        "time-based usage report over a begin/end range. This is time (minutes), "
        "not bandwidth volume (see get_network_usage). Resolve scope from "
        "list_hosts (for a device) or the watched-user surfaces."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND,
                description="Required. What the scope target identifies.",
            ): vol.In(("device", "group", "user")),
            vol.Required(
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET,
                description=(
                    "Required. The scope identifier for the chosen kind (a MAC "
                    "for a device, a group id, or a user id)."
                ),
            ): str,
            vol.Required(
                SERVICE_FIELD_USAGE_HISTORY_BEGIN,
                description="Required. Local start date-time of the range.",
            ): cv.datetime,
            vol.Required(
                SERVICE_FIELD_USAGE_HISTORY_END,
                description="Required. Local end date-time of the range.",
            ): cv.datetime,
            vol.Required(
                SERVICE_FIELD_USAGE_HISTORY_GRANULARITY,
                description="Required. Bucket size for the report.",
            ): vol.In(("day", "hour")),
            vol.Optional(
                SERVICE_FIELD_SECTIONS,
                description=(
                    "Optional. Sections to include. Allowed: 'internet', "
                    "'app_totals', 'apps', 'categories'."
                ),
            ): vol.All(
                cv.ensure_list,
                [vol.In(("internet", "app_totals", "apps", "categories"))],
            ),
            vol.Optional(
                SERVICE_FIELD_INCLUDE,
                description="Optional. Add raw intervals. Allowed: 'intervals'.",
            ): vol.All(cv.ensure_list, [vol.In(("intervals",))]),
            vol.Optional(
                SERVICE_FIELD_DETAIL,
                description="Optional. Level of detail. Defaults to 'standard'.",
            ): vol.In(("summary", "standard")),
            vol.Optional(
                SERVICE_FIELD_USAGE_HISTORY_APP_IDS,
                description="Optional. Limit app usage to these app ids.",
            ): vol.All(cv.ensure_list, [str]),
        }
    )
    _service = SERVICE_GET_TIME_USAGE_REPORT
    _response_type = "user_usage"


class GetInternetQualityTool(_FirewallaReadTool):
    """Return internet-quality measurements (latency, loss, jitter)."""

    name = "firewalla_local__get_internet_quality"
    title = "Get internet quality"
    description = _PREFERRED_PREFIX + (
        "Answer 'how good is my internet right now?' with quality samples such "
        "as latency, jitter, and packet loss. For a point-in-time throughput "
        "test run run_internet_speed_test; for past results use get_speed_tests."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_WAN_UUID, description=_WAN_UUID_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_WAN_NAME, description=_WAN_NAME_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_LIMIT,
                description="Optional. Maximum samples to return. Defaults to 1.",
            ): int,
            vol.Optional(SERVICE_FIELD_REFRESH, description=_REFRESH_DESCRIPTION): bool,
        }
    )
    _service = SERVICE_GET_INTERNET_QUALITY_REPORT
    _response_type = "internet_quality"


class GetSpeedTestsTool(_FirewallaReadTool):
    """Return historical speed-test results."""

    name = "firewalla_local__get_speed_tests"
    title = "Get speed tests"
    description = _PREFERRED_PREFIX + (
        "Answer 'what were my last speed test results?' with stored download, "
        "upload, latency, and packet-loss measurements. To run a new test use "
        "run_internet_speed_test."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_WAN_UUID, description=_WAN_UUID_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_WAN_NAME, description=_WAN_NAME_DESCRIPTION
            ): str,
            vol.Optional(
                SERVICE_FIELD_LIMIT,
                description="Optional. Maximum results to return. Defaults to 1.",
            ): int,
            vol.Optional(SERVICE_FIELD_REFRESH, description=_REFRESH_DESCRIPTION): bool,
        }
    )
    _service = SERVICE_GET_SPEED_TEST_RESULTS
    _response_type = "speed_tests"


class GetWirelessStatusTool(_FirewallaReadTool):
    """Return wireless status: SSIDs, access points, and clients."""

    name = "firewalla_local__get_wireless_status"
    title = "Get wireless status"
    description = _PREFERRED_PREFIX + (
        "Show WiFi state: SSID profiles (with paused state), access points, and "
        "connected clients. Use it to resolve the ssid_profile_id that "
        "set_ssid_paused requires."
    )
    parameters = vol.Schema({})
    _service = SERVICE_GET_WIRELESS_STATUS
    _response_type = "wireless_status"


class GetAlarmsTool(_FirewallaReadTool):
    """Return recent active and optionally archived alarms."""

    name = "firewalla_local__get_alarms"
    title = "Get alarms"
    description = _PREFERRED_PREFIX + (
        "Answer 'what is happening on my network?' with the most recent alarms "
        "(active, and archived when requested). Defaults to the 10 newest; raise "
        "limit deliberately, since a large alarm payload is expensive context. "
        "The box keeps roughly 30 days and offers no time-window filter."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_LIMIT,
                description=(
                    "Optional. Maximum alarms to return, newest first. Defaults "
                    "to 10; maximum 500."
                ),
            ): vol.All(int, vol.Range(min=1, max=500)),
            vol.Optional(
                SERVICE_FIELD_INCLUDE_ARCHIVED,
                description="Optional. Include archived alarms. Defaults to false.",
            ): bool,
            vol.Optional(
                SERVICE_FIELD_ALARM_TYPE,
                description=(
                    "Optional. A raw ALARM_* type or a supported group such as "
                    "'security', 'abnormal_upload', or 'open_port'."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_DETAIL,
                description=(
                    "Optional. Fetch extended detail with one extra request per "
                    "returned alarm. Defaults to false."
                ),
            ): bool,
        }
    )
    _service = SERVICE_GET_ALARMS
    _response_type = "alarms"


_READ_TOOL_CLASSES: Final = (
    ListHostsTool,
    ListRulesTool,
    GetNetworkConfigTool,
    GetNetworkUsageTool,
    GetWanUsageTool,
    GetWanEventsTool,
    GetUserUsageTool,
    GetInternetQualityTool,
    GetSpeedTestsTool,
    GetWirelessStatusTool,
    GetAlarmsTool,
)


def build_read_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the read tools bound to one config entry."""
    return [tool_class(entry_id=entry_id) for tool_class in _READ_TOOL_CLASSES]
