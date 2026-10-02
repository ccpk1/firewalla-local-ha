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
    DEFAULT_NETWORK_USAGE_WINDOW,
    DOMAIN,
    SERVICE_FIELD_ACTION,
    SERVICE_FIELD_ALARM_TYPE,
    SERVICE_FIELD_APPLIES_TO,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CURRENT_PERIODS,
    SERVICE_FIELD_DETAIL,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_GROUP_NAME,
    SERVICE_FIELD_HISTORY_COUNT,
    SERVICE_FIELD_HISTORY_PERIOD,
    SERVICE_FIELD_HOST_MAC,
    SERVICE_FIELD_HOST_NAME,
    SERVICE_FIELD_INCLUDE,
    SERVICE_FIELD_INCLUDE_ARCHIVED,
    SERVICE_FIELD_INCLUDE_DNS,
    SERVICE_FIELD_INCLUDE_PURPOSE,
    SERVICE_FIELD_INCLUDE_SYSTEM_MANAGED,
    SERVICE_FIELD_KIND,
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_NETWORK_NAME,
    SERVICE_FIELD_NETWORK_UUID,
    SERVICE_FIELD_OFFSET,
    SERVICE_FIELD_ONLINE,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_SECTIONS,
    SERVICE_FIELD_TARGET_TYPE,
    SERVICE_FIELD_TOP_N,
    SERVICE_FIELD_USAGE_HISTORY_APP_IDS,
    SERVICE_FIELD_USAGE_HISTORY_BEGIN,
    SERVICE_FIELD_USAGE_HISTORY_END,
    SERVICE_FIELD_USAGE_HISTORY_GRANULARITY,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET,
    SERVICE_FIELD_USER,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_FIELD_WINDOW,
    SERVICE_FIELD_WINDOW_DAYS,
    SERVICE_GET_ALARMS,
    SERVICE_GET_HOST_NAME_MAPPING,
    SERVICE_GET_INTERNET_QUALITY_REPORT,
    SERVICE_GET_NETWORK_SEGMENT_REPORT,
    SERVICE_GET_NETWORK_SEGMENT_USAGE,
    SERVICE_GET_RULES,
    SERVICE_GET_SPEED_TEST_RESULTS,
    SERVICE_GET_SYSTEM_OVERVIEW,
    SERVICE_GET_TIME_USAGE_REPORT,
    SERVICE_GET_WAN_DATA_USAGE,
    SERVICE_GET_WAN_EVENTS,
    SERVICE_GET_WIRELESS_STATUS,
    SERVICE_SYNC_RUNTIME,
)
from .llm_tools_common import format_tool_name

# Every read tool is a bounded, read-only query against the user's own box.
_READ_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=False,
)

_REFRESH_DESCRIPTION: Final = (
    "Optional. Defaults to true. Poll the Firewalla box for current data before "
    "building the result; this is slower and usually unnecessary when a recent "
    "refresh already happened. Set false to read the last snapshot."
)

_NETWORK_UUID_DESCRIPTION: Final = (
    "Optional. A Firewalla network UUID (from get_system_overview) for a "
    "deterministic match. Provide this or network_name."
)

_NETWORK_NAME_DESCRIPTION: Final = (
    "Optional. A Firewalla network display name (from get_system_overview) for "
    "interactive use. Provide this or network_uuid."
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

    name = format_tool_name("list_hosts")
    title = "List hosts"
    description = (
        "List the devices on your Firewalla network with their name, device "
        "type, IP address, and DNS/DHCP identity. Use it to find a host before "
        "renaming it or setting a DHCP reservation. Refreshing first polls the "
        "box and is slower than reading the last snapshot.\n"
        "\n"
        "Naming: `host_name` is the primary human-facing label and the one to "
        "match a user's words against. `dns_hostname`/`dns_domain`/`dns_fqdn` "
        "are the DNS-facing names. `dhcp_name` is device-supplied and "
        "unreliable (`nvidia-shield` carries `android-66fc79bd9bb55411`) — "
        "never use it to identify a device.\n"
        "\n"
        'VPN peers: a device with `kind: "pseudo_host"` is a VPN peer. Those '
        "have NO MAC address (`mac` is null and `host_id` is a `wg_peer:`/"
        "`awg_peer:` identifier), so they cannot be passed to any host tool "
        "that takes a MAC. `ip_assignment` is also null for them; do not assume "
        "it is always an object.\n"
        "\n"
        "Connectivity: `online` is whether the device is active now, and "
        "`last_active` is its last activity (epoch seconds). A peer in this list "
        "is a *configured* peer, not necessarily a connected one — several may be "
        "idle for weeks. When asked how many are connected, count `online: true` "
        "(or filter `online=true`), never the length of the list.\n"
        "\n"
        "This lists every host by default. Pass the filters to narrow it — a "
        "name, one network, online state or kind — rather than pulling the whole "
        "inventory, and keep the default `detail: summary` unless the full "
        "record is needed."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_DETAIL,
                default="summary",
                description=(
                    "Optional. 'summary' omits the derivable `dns_fqdn`, the "
                    "unreliable `dhcp_name`, and the nested `ip_assignment` "
                    "(its useful parts are flattened to `ip_assignment_mode` "
                    "and `reserved_ipv4`). Use 'full' for the complete record."
                ),
            ): vol.In(("summary", "full")),
            vol.Optional(
                SERVICE_FIELD_HOST_NAME,
                description=(
                    "Optional. Substring match on the host name. Use it to find "
                    "one device instead of listing every host."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_MAC,
                description="Optional. Exact host MAC address.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_NAME,
                description="Optional. Exact group name to filter by.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_KIND,
                description=(
                    "Optional. 'mac_host' for a normal device, 'pseudo_host' to "
                    "return only VPN peers."
                ),
            ): vol.In(("mac_host", "pseudo_host")),
            vol.Optional(
                SERVICE_FIELD_NETWORK_UUID,
                description="Optional. Filter to one network by its uuid.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_ONLINE,
                description="Optional. Filter to hosts currently online or offline.",
            ): bool,
            vol.Optional(
                SERVICE_FIELD_USER,
                description="Optional. Filter to hosts belonging to one user id.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_REFRESH,
                default=True,
                description=(
                    "Optional. Poll the Firewalla box for "
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

    name = format_tool_name("list_rules")
    title = "List rules"
    description = (
        "List your Firewalla firewall rules with id, name, action, "
        "enabled/paused state, target, scope, and any originating alarm. Use it "
        "to resolve the rule target that pause_rule and resume_rule require.\n"
        "\n"
        "`applies_to` names the groups, users or networks a rule governs, and "
        "`tag_refs` carries the matching ids. A rule with neither applies "
        "globally. Rules do not stack by scope: once a device belongs to a group "
        "or user, its rules come from that group or user and its device-level "
        "rules no longer apply, so check a device's membership before concluding "
        "which rules cover it.\n"
        "\n"
        "Defaults to user-visible rules. The box also carries large numbers of "
        "product-owned DAP and family rules, plus rules owned by a Firewalla "
        "subsystem (the alarm-intel auto-blocks); those are hidden unless "
        "requested via include_purpose or include_system_managed.\n"
        "\n"
        "Filters narrow the result on the box. Pass `enabled`, `action`, "
        "`target_type` or `applies_to` to answer a question about specific "
        "rules rather than listing every one."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_ENABLED,
                description="Optional. Filter by enabled state.",
            ): bool,
            vol.Optional(
                SERVICE_FIELD_ACTION,
                description="Optional. Filter by action.",
            ): vol.In(("block", "allow", "qos", "disturb")),
            vol.Optional(
                SERVICE_FIELD_TARGET_TYPE,
                description=(
                    "Optional. Filter by target type, e.g. 'category', 'mac', "
                    "'ip', 'dns', 'network'."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_APPLIES_TO,
                description=(
                    "Optional. Filter to rules governing one group, user or "
                    "network name."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_INCLUDE_PURPOSE,
                description=(
                    "Optional. Include product-owned rules that are hidden by "
                    "default. Allowed: 'dap' (Device Active Protect), 'family'."
                ),
            ): vol.All(
                cv.ensure_list,
                [vol.In(("dap", "family"))],
            ),
            vol.Optional(
                SERVICE_FIELD_INCLUDE_SYSTEM_MANAGED,
                description=(
                    "Optional. Include rules owned by a Firewalla subsystem, "
                    "such as alarm-intel auto-blocks. Hidden by default."
                ),
            ): bool,
        }
    )
    _service = SERVICE_GET_RULES
    _response_type = "rules"


class GetNetworkConfigTool(_FirewallaReadTool):
    """Return configuration-oriented detail for one network segment."""

    name = format_tool_name("get_network_config")
    title = "Get network config"
    description = (
        "Show how a network (LAN/VLAN) is configured: addressing, gateway, DNS, "
        "DHCP range, and ports. Use it for network structure. For per-device "
        "traffic use get_network_usage.\n"
        "\n"
        "The `policy` block holds network-level Firewalla settings (`adblock`, "
        "`safeSearch`, `family`, `doh`, `monitor`, `qos`, and similar). They are "
        "settings, not rules: they neither create nor correspond to any rule, so "
        "a `family` setting here has nothing to do with a `family` rule purpose "
        "in list_rules.\n"
        "\n"
        "The network's device list is not included by default. Ask for it with "
        "`include: ['hosts']` only when the user wants the devices on that "
        "network; use list_hosts for device questions."
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

    name = format_tool_name("get_network_usage")
    title = "Get network usage"
    description = (
        "Answer 'what is using the most bandwidth on this network?' with windowed "
        "top talkers, apps, and categories. A network must be selected: this is "
        "per network segment over a time window, not a whole-box total. Note: "
        "windowed WAN usage is not available; use get_wan_usage for WAN totals."
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
                default=DEFAULT_NETWORK_USAGE_WINDOW,
                description=(
                    "Optional. Activity window to report. The smallest window "
                    "is 'last_60_minutes'. Allowed: "
                    "'last_60_minutes', 'last_24_hours', 'last_30_days', "
                    "'last_12_months'."
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

    name = format_tool_name("get_wan_usage")
    title = "Get WAN usage"
    description = (
        "Answer 'how much internet data have I used?' with WAN download/upload "
        "totals. Defaults to the day and week periods, which is what this "
        "question usually means; add history only when a trend is wanted, since "
        "it is roughly 12x the size. This is WAN totals, not per-device usage "
        "(see get_network_usage)."
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

    name = format_tool_name("get_wan_events")
    title = "Get WAN events"
    description = (
        "Answer 'why did my internet drop?' with WAN link events such as outages "
        "and status changes. Defaults to the last 7 days of real connectivity "
        "events. For volume over time use get_wan_usage; for latency and packet "
        "loss samples use get_internet_quality."
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
            vol.Optional(
                SERVICE_FIELD_WINDOW_DAYS,
                description=(
                    "Optional. How many days back to look. Defaults to 7; use 0 "
                    "for no time bound."
                ),
            ): int,
            vol.Optional(
                SERVICE_FIELD_INCLUDE_DNS,
                description=(
                    "Optional. Defaults to false. Include the box's internal "
                    "DNS health probes (roughly every 3 minutes), which are not "
                    "WAN events and are excluded by default."
                ),
            ): bool,
        }
    )
    _service = SERVICE_GET_WAN_EVENTS
    _response_type = "wan_events"


class GetUserUsageTool(_FirewallaReadTool):
    """Return time-based usage for one person, group, or device."""

    name = format_tool_name("get_user_usage")
    title = "Get user usage"
    description = (
        "Answer 'how much time did a person/device spend online?' with a "
        "time-based usage report over a begin/end range. This is time (minutes), "
        "not bandwidth volume (see get_network_usage). Resolve scope from "
        "list_hosts (for a device) or the watched-user surfaces.\n"
        "\n"
        "Every section is returned by default; pass `sections` to keep only what "
        "the question needs."
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

    name = format_tool_name("get_internet_quality")
    title = "Get internet quality"
    description = (
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

    name = format_tool_name("get_speed_tests")
    title = "Get speed tests"
    description = (
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


class SyncRuntimeTool(_FirewallaReadTool):
    """Poll the Firewalla box now and report the resulting snapshot time."""

    name = format_tool_name("sync_runtime")
    title = "Sync runtime"
    description = (
        "Poll the Firewalla box for a fresh snapshot and report when it was "
        "taken. Use it when the user needs current data and the last snapshot "
        "may be stale; then read other tools with refresh=false. Requests "
        "within about 10 seconds are coalesced, so calling it before several "
        "other tools costs at most one poll."
    )
    parameters = vol.Schema({})
    _service = SERVICE_SYNC_RUNTIME
    _response_type = "runtime_sync"


class GetSystemOverviewTool(_FirewallaReadTool):
    """Return the curated system summary that anchors a session."""

    name = format_tool_name("get_system_overview")
    title = "Get system overview"
    description = (
        "Start here. Call this once at the beginning of a session for any "
        "general question about the network. It returns appliance health, the "
        "networks with their device counts, and counts for devices, VPN peers, "
        "groups, users, rules, and alarms, plus the network, group and user "
        "identifiers the other tools accept as selectors.\n"
        "\n"
        "It returns counts and identifiers only — never device or rule records. "
        "Use list_hosts for devices and list_rules for rules; do not answer a "
        "per-device question from this summary. Call it once per session unless "
        "the network has changed.\n"
        "\n"
        "Reading the counts: `devices` and `vpn_devices` each report `total` "
        "(everything known), `online` (active now), and `offline`. `total` is "
        "not the connected count — a VPN peer is *configured*, and may have been "
        'idle for weeks, so answer "how many are connected?" from `online`, '
        "never from `total`. The two sections overlap: peers are already inside "
        "`devices`, so `vpn_devices` is a breakdown of it, not a group to add."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_INCLUDE,
                description=(
                    "Optional. Add the group and user names and ids that "
                    "get_user_usage and the rule tools accept as selectors. "
                    "Allowed: 'identifiers'."
                ),
            ): vol.All(cv.ensure_list, [vol.In(("identifiers",))]),
        }
    )
    _service = SERVICE_GET_SYSTEM_OVERVIEW
    _response_type = "system_overview"


class GetSystemOverviewSummaryTool(GetSystemOverviewTool):
    """The curated report alone, without the identity identifiers.

    This is the only tool registered in the anonymous tier. It deliberately
    cannot request the identifiers: the capability is absent rather than
    filtered, so the tier's privacy claim holds by construction.
    """

    description = (
        "Answer general questions about this Firewalla network: appliance "
        "health, the networks with their device counts, and counts for devices, "
        "VPN peers, and alarms.\n"
        "\n"
        "Reading the counts: `devices` and `vpn_devices` each report `total` "
        "(everything known), `online` (active now), and `offline`. `total` is "
        "not the connected count — a VPN peer is *configured*, and may have been "
        'idle for weeks, so answer "how many are connected?" from `online`, '
        "never from `total`. The two sections overlap: peers are already inside "
        "`devices`, so `vpn_devices` is a breakdown of it, not a group to add.\n"
        "\n"
        "This report is intentionally limited to counts, network names, and "
        "performance metrics — it carries no device addresses, no hardware "
        "identifiers, and no group or user names. For device names and "
        "addresses, rules, alarms, or usage detail, the user must raise "
        "Firewalla's AI access level in the integration options."
    )
    parameters = vol.Schema({})


class GetWirelessStatusTool(_FirewallaReadTool):
    """Return wireless status: SSIDs, access points, and clients."""

    name = format_tool_name("get_wireless_status")
    title = "Get wireless status"
    description = (
        "Show WiFi state: SSID profiles (with paused state), access points, and "
        "connected clients. Use it to resolve the ssid_profile_id that "
        "set_ssid_paused requires."
    )
    parameters = vol.Schema({})
    _service = SERVICE_GET_WIRELESS_STATUS
    _response_type = "wireless_status"


class GetAlarmsTool(_FirewallaReadTool):
    """Return recent active and optionally archived alarms."""

    name = format_tool_name("get_alarms")
    title = "Get alarms"
    description = (
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
    GetSystemOverviewTool,
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
    SyncRuntimeTool,
)


_ANONYMOUS_TOOL_CLASSES: Final = (GetSystemOverviewSummaryTool,)


def build_read_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the read tools bound to one config entry."""
    return [tool_class(entry_id=entry_id) for tool_class in _READ_TOOL_CLASSES]


def build_anonymous_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the anonymous tier's tools: the curated summary, and nothing else."""
    return [tool_class(entry_id=entry_id) for tool_class in _ANONYMOUS_TOOL_CLASSES]
