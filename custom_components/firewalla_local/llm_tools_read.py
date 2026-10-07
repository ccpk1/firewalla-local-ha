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
    DEFAULT_FLOW_REPORT_RECORD_COUNT,
    DEFAULT_FLOW_REPORT_WINDOW_HOURS,
    DEFAULT_NETWORK_USAGE_WINDOW,
    DETAIL_FULL,
    DETAIL_LEVELS,
    DETAIL_SUMMARY,
    DOMAIN,
    FLOW_REPORT_INCLUDE_HOST_DETAIL,
    MAX_FLOW_LOG_PAGE_SIZE,
    MIN_FLOW_LOG_PAGE_SIZE,
    SERVICE_FIELD_ACTION,
    SERVICE_FIELD_ALARM_ID,
    SERVICE_FIELD_ALARM_TYPE,
    SERVICE_FIELD_APPLIES_TO,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CURRENT_PERIODS,
    SERVICE_FIELD_DETAIL,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_GROUP_ID,
    SERVICE_FIELD_GROUP_NAME,
    SERVICE_FIELD_HISTORY_COUNT,
    SERVICE_FIELD_HISTORY_PERIOD,
    SERVICE_FIELD_HOST_MAC,
    SERVICE_FIELD_HOST_NAME,
    SERVICE_FIELD_INCLUDE,
    SERVICE_FIELD_INCLUDE_ARCHIVED,
    SERVICE_FIELD_INCLUDE_DNS,
    SERVICE_FIELD_INCLUDE_EXCEPTIONS,
    SERVICE_FIELD_INCLUDE_PURPOSE,
    SERVICE_FIELD_INCLUDE_SYSTEM_MANAGED,
    SERVICE_FIELD_KIND,
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_NETWORK_NAME,
    SERVICE_FIELD_NETWORK_UUID,
    SERVICE_FIELD_OFFSET,
    SERVICE_FIELD_ONLINE,
    SERVICE_FIELD_RECORD_COUNT,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_SECTIONS,
    SERVICE_FIELD_TARGET_TYPE,
    SERVICE_FIELD_TOP_N,
    SERVICE_FIELD_USAGE_HISTORY_APP_IDS,
    SERVICE_FIELD_USAGE_HISTORY_BEGIN,
    SERVICE_FIELD_USAGE_HISTORY_END,
    SERVICE_FIELD_USAGE_HISTORY_GRANULARITY,
    SERVICE_FIELD_USER,
    SERVICE_FIELD_USER_ID,
    SERVICE_FIELD_USER_NAME,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_FIELD_WINDOW,
    SERVICE_FIELD_WINDOW_DAYS,
    SERVICE_FIELD_WINDOW_HOURS,
    SERVICE_GET_ALARMS,
    SERVICE_GET_FLOW_REPORT,
    SERVICE_GET_HOSTS,
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
from .llm_tools_common import READ_INJECTION, format_tool_name

# Every read tool is a bounded, read-only query against the user's own box,
# which is outside Home Assistant -- so `open_world` is true even though nothing
# is written. The flag describes where the data comes from, not whether the call
# changes anything.
_READ_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=True,
)

_REFRESH_DESCRIPTION: Final = (
    "Optional. Defaults to false: the result comes from the cached runtime "
    "snapshot, which is fast and current to within the poll interval. Set true to "
    "poll the box first — a full poll, worth it only when the user needs data "
    "newer than the last one."
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

# Both overview tools publish these counts, so the reading rule is stated once and
# composed into each rather than kept in two places that can drift.
_COUNTS_READING: Final = (
    "Reading the counts: `total` is everything known, not the connected count — a "
    "VPN peer is *configured* and may have been idle for weeks — so answer "
    '"how many are connected?" from `online`. `vpn_hosts` is a breakdown of '
    "`hosts`, already inside it: never add the two."
)


class _FirewallaReadTool(llm.Tool):
    """Base class for a Firewalla Local read tool backed by a service."""

    integration = DOMAIN
    annotations = _READ_ANNOTATIONS

    # Prepended at construction rather than written into each description, so a new
    # read tool cannot be added without the family block. A client that sends only
    # `tools/list` never receives the API prompt, and `system_model` only arrives
    # once `get_system_overview` has been called, so the descriptions are the one
    # channel every client is guaranteed to receive.
    _injection: Final = READ_INJECTION

    _service: str
    _response_type: str

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
    """List Firewalla hosts with identity and IP assignment."""

    name = format_tool_name("list_hosts")
    title = "List hosts"
    description = (
        "Hosts on the network: identity, IP assignment, and connectivity.\n"
        "\n"
        "`host_name` — the primary label; match a user's words against this one.\n"
        "`dns_hostname` / `dns_domain` / `dns_fqdn` — DNS-facing names.\n"
        "`dhcp_name` — host-supplied and unreliable (`nvidia-shield` reports "
        "`android-66fc79bd9bb55411`); never identify a host by it.\n"
        "`network_uuid` / `network_name` — the host's segment, stated rather than "
        "inferred from its IP. `network_uuid` also filters.\n"
        "`group_name` — the group or user this host follows; `membership_kind` "
        "names which. Pass `group_name` to `list_rules` as `applies_to` to find "
        "the rules that govern the host.\n"
        "`membership_kind` — `group` or `user`, or null when the host's tags mix "
        "the two.\n"
        "`kind` — `mac_host`, or `pseudo_host` for a VPN peer. A peer has no MAC "
        "(`mac` null, `host_id` a `wg_peer:` / `awg_peer:` id), so it cannot be "
        "passed to any MAC-taking tool, and its `ip_assignment` is null.\n"
        "`online` — derived, not a fact about the host: "
        "`activity_reference_at_timestamp - last_active_at_timestamp <= "
        "online_window_seconds`, and false when `stale`. All four are on every row, "
        "so recompute it rather than guess.\n"
        "\n"
        "Inactive hosts are included (`includeInactiveHosts`, the app's \"Show past "
        'devices"), so `online: false` beside an old `last_active_at` is normal. '
        "Count connected hosts from `online`, never from the row count — most rows "
        "are configured rather than active.\n"
        "\n"
        "`detail: summary` (the default) omits the derivable `dns_fqdn`, the "
        "unreliable `dhcp_name`, and flattens `ip_assignment` to "
        "`ip_assignment_mode` and `reserved_ipv4`; `full` returns the whole record. "
        "The filters narrow on the box, so prefer them to pulling the inventory."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_DETAIL,
                default=DETAIL_SUMMARY,
                description=(
                    "Optional. 'summary' omits the derivable `dns_fqdn`, the "
                    "unreliable `dhcp_name`, and the nested `ip_assignment` "
                    "(its useful parts are flattened to `ip_assignment_mode` "
                    "and `reserved_ipv4`). Use 'full' for the complete record."
                ),
            ): vol.In(DETAIL_LEVELS),
            vol.Optional(
                SERVICE_FIELD_HOST_NAME,
                description=(
                    "Optional. Substring match on the host name. Use it to find "
                    "a single host rather than listing them all."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_MAC,
                description="Optional. Exact host MAC address.",
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_NAME,
                description=(
                    "Optional. Exact match on the host's membership label, which is "
                    "the group's name **or the user's name** — the box stores both "
                    "as a tag and resolves the label through the affiliated user "
                    "first, so a host assigned to a user carries that user's name "
                    "here. Filtering one name at a time works for either kind."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_KIND,
                description=(
                    "Optional. 'mac_host' for a normal host, 'pseudo_host' to "
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
                description=(
                    "Optional. Filter to the hosts assigned to one user, by user "
                    "id or user name. Use this when the question is about a person: "
                    "it resolves the user's affiliated tag and matches that, which "
                    "is exact, where `group_name` would take the user's name as a "
                    "label."
                ),
            ): str,
            vol.Optional(SERVICE_FIELD_REFRESH, description=_REFRESH_DESCRIPTION): bool,
        }
    )
    _service = SERVICE_GET_HOSTS
    _response_type = "hosts"


class ListRulesTool(_FirewallaReadTool):
    """List Firewalla policy rules with their current state."""

    name = format_tool_name("list_rules")
    title = "List rules"
    description = (
        "Firewall rules with id, name, action, paused state, target, scope, and "
        "the alarm that created any.\n"
        "\n"
        "`applies_to` — the groups, users, or networks this rule governs, by name, "
        "each with a matching `applies_to_kind`. A rule with no entry applies "
        "globally. A host is never listed here: its rules are in `scope`, which is "
        "why a host's `group_name` is the value to pass as `applies_to` to find "
        "what covers it. `tag_refs` carries the underlying ids. A host's rules are "
        "not added to its group's — attachment replaces, so it follows only the "
        "group or user it belongs to.\n"
        "\n"
        "`hit_count` — matches recorded. Always a number, so `0` means no recorded "
        "match rather than unknown; enabled rules with `hit_count: 0` are cleanup "
        "candidates. `last_hit` — the most recent single match, with its host and "
        "destination, or null. The box keeps one match per rule and no history, so "
        'it cannot answer "everything this rule blocked".\n'
        "\n"
        "`is_paused` — whether the rule is running; `pause_until` — the boundary it "
        "comes back on its own, or null when it will not.\n"
        "\n"
        "User-visible rules only by default. Product-owned DAP and family rules "
        "and alarm-intel auto-blocks are hidden unless `include_purpose` or "
        "`include_system_managed` asks for them. `alarm_id` finds the auto-block an "
        "alarm created — that is the rule `unblock_alarm_target` needs, and it "
        "requires `include_system_managed: true`."
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
                    "network name. A host's `group_name` (from list_hosts) is "
                    "the value to pass here to find the rules that govern that "
                    "host. Matches exactly, so filter one name at a time."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_ALARM_ID,
                description=(
                    "Optional. Filter to the rule an alarm created, by alarm "
                    "id. Use it to find the rule to pass to "
                    "`unblock_alarm_target`; also pass "
                    "`include_system_managed: true`, since those rules are "
                    "hidden by default."
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
        "One network's configuration: addressing, gateway, DNS, DHCP range, and "
        "ports. Per-host traffic is `get_network_usage`.\n"
        "\n"
        "`policy` — network-level Firewalla **settings**, not rules (`adblock`, "
        "`safeSearch`, `family`, `doh`, `monitor`, `qos`). They neither create nor "
        "correspond to a rule, so a `family` setting here is unrelated to a "
        "`family` rule purpose in `list_rules`.\n"
        "\n"
        "`summary.host_count` is the network's host count from the host inventory "
        "and is the number to quote — it is the same with or without the host "
        "list. `summary.returned_host_count` appears only with "
        "`include: ['hosts']` and reports the rows that section returned.\n"
        "\n"
        "The host list is off by default. Ask for it only when the hosts "
        "themselves are wanted — those rows carry MAC addresses, hostnames, IPs "
        "and reservations — and use `list_hosts` for host questions. The filters "
        "narrow on the box, so prefer them to pulling the inventory."
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
                SERVICE_FIELD_INCLUDE,
                description=(
                    "Optional. Add the network's host list with "
                    "`include: ['hosts']`. Those rows carry MAC addresses, "
                    "hostnames, IPs, and reservations, so ask for them only "
                    "when the hosts themselves are wanted."
                ),
            ): vol.All(cv.ensure_list, [vol.In(("hosts",))]),
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
        "What is using the most bandwidth on one network — top talkers, apps, and "
        "categories over a window. A network must be selected: this is per segment, "
        "not a whole-box total. Windowed WAN usage is not available; `get_wan_usage` "
        "has WAN totals."
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
                    "Optional. Limit how many top host/app/category ranking "
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
        "How much internet data has been used — WAN download/upload totals, by "
        "day, week, month or year. Not per-host usage (`get_network_usage`). "
        "Defaults to the day and week periods, which is what the question usually "
        "means; add `history` only when a trend is wanted, since it is roughly 12x "
        "the size."
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
        "Why the internet dropped — WAN link events: outages and status changes. "
        "Defaults to the last 7 days of real connectivity events. The box's own "
        "DNS health probes are excluded unless `include_dns` asks for them, since "
        "they are not connectivity events. `get_wan_usage` is volume over time; "
        "`get_internet_quality` is latency and packet loss."
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
    """Return time-based usage for one person, group, or host."""

    name = format_tool_name("get_user_usage")
    title = "Get user usage"
    description = (
        "How much time a person, host, or group spent online, over a begin/end "
        "range. Minutes, not bandwidth volume (`get_network_usage`). Resolve the "
        "scope from `list_hosts` or the watched-user surfaces.\n"
        "\n"
        "Every section is returned by default; pass `sections` to keep only what "
        "the question needs."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC,
                description=(
                    "Optional. Select a host by MAC. Provide exactly one of the "
                    "scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME,
                description=(
                    "Optional. Select a host by name. Provide exactly one of the "
                    "scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_ID,
                description=(
                    "Optional. Select a group by id. Provide exactly one of the "
                    "scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_NAME,
                description=(
                    "Optional. Select a group by name. Provide exactly one of the "
                    "scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_ID,
                description=(
                    "Optional. Select a user by id. Provide exactly one of the "
                    "scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_NAME,
                description=(
                    "Optional. Select a user by name. Provide exactly one of the "
                    "scope selectors."
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
                default=DETAIL_FULL,
                description=(
                    "Optional. 'full' (default) is the normal report depth; "
                    "'summary' returns the smallest default section set."
                ),
            ): vol.In(DETAIL_LEVELS),
            vol.Optional(
                SERVICE_FIELD_USAGE_HISTORY_APP_IDS,
                description="Optional. Limit app usage to these app ids.",
            ): vol.All(cv.ensure_list, [str]),
        }
    )
    _service = SERVICE_GET_TIME_USAGE_REPORT
    _response_type = "user_usage"


class GetFlowReportTool(_FirewallaReadTool):
    """Return what one host, group, or user did, and what was blocked."""

    name = format_tool_name("get_flow_report")
    title = "Get flow report"
    description = (
        "What one host, group, or user did, and what was blocked: traffic totals, "
        "destinations reached, the blocked breakdown, and LAN peers.\n"
        "\n"
        "Two levels. `detail: summary` (the default) is one request answering "
        "*how much* and *to where*. `detail: full` adds the individual flow "
        'records, which name the rule that blocked each — so "which rule stopped '
        'this" is only answerable there, and it is the level to diagnose with. '
        "Records are large, so keep "
        "`record_count` small and widen only if the answer is not there.\n"
        "\n"
        "This is the box's own flow data, retained roughly "
        f"{DEFAULT_FLOW_REPORT_WINDOW_HOURS} hours — not history. A wider "
        "`window_hours` is accepted and quietly clamped, so read "
        "`summary.window` (`served_hours`, and `is_clamped` when it was "
        "shortened) and state the span served.\n"
        "\n"
        'Per-host detail is off by default. Add `include: ["host_detail"]` when '
        "the answer needs to know *which* host was behind a member row, a "
        "destination, or a record. A host scope always names its own host "
        "regardless."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_HOST_MAC,
                description=(
                    "Optional. Scope the report to a host by MAC. Provide exactly "
                    "one of the scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_HOST_NAME,
                description=(
                    "Optional. Scope the report to a host by name. Provide exactly "
                    "one of the scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_ID,
                description=(
                    "Optional. Scope the report to a group by id. Provide exactly "
                    "one of the scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_GROUP_NAME,
                description=(
                    "Optional. Scope the report to a group by name. Provide "
                    "exactly one of the scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_ID,
                description=(
                    "Optional. Scope the report to a user by id. Provide exactly "
                    "one of the scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_USER_NAME,
                description=(
                    "Optional. Scope the report to a user by name. Provide "
                    "exactly one of the scope selectors."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_WINDOW_HOURS,
                description=(
                    "Optional. Defaults to 24, which is what the box serves. The "
                    "response reports the span it actually covered."
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional(
                SERVICE_FIELD_DETAIL,
                default=DETAIL_SUMMARY,
                description=(
                    "Optional. 'summary' (default) is totals and rankings. "
                    "'full' adds the individual flow records, which carry the "
                    "blocking rule — use it to diagnose why traffic was stopped."
                ),
            ): vol.In(DETAIL_LEVELS),
            vol.Optional(
                SERVICE_FIELD_RECORD_COUNT,
                default=DEFAULT_FLOW_REPORT_RECORD_COUNT,
                description=(
                    "Optional. How many records 'full' detail returns. Defaults "
                    f"to {DEFAULT_FLOW_REPORT_RECORD_COUNT}. Records are large, so "
                    "ask for a small page first and only widen if the answer is "
                    "not there."
                ),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_FLOW_LOG_PAGE_SIZE, max=MAX_FLOW_LOG_PAGE_SIZE),
            ),
            vol.Optional(
                SERVICE_FIELD_REFRESH,
                default=False,
                description=(
                    "Optional. The rollup itself is always a live request against "
                    "the box; this only re-polls the runtime snapshot first, which "
                    "is what resolves host, rule and tag names. Defaults to false."
                ),
            ): bool,
            vol.Optional(
                SERVICE_FIELD_INCLUDE,
                description=(
                    "Optional. Add per-host detail, which is absent by default. "
                    "Allowed: 'host_detail'."
                ),
            ): vol.All(
                cv.ensure_list,
                [vol.In((FLOW_REPORT_INCLUDE_HOST_DETAIL,))],
            ),
        }
    )
    _service = SERVICE_GET_FLOW_REPORT
    _response_type = "flow_report"


class GetInternetQualityTool(_FirewallaReadTool):
    """Return internet-quality measurements (latency, loss, jitter)."""

    name = format_tool_name("get_internet_quality")
    title = "Get internet quality"
    description = (
        "How good the internet is right now — latency, jitter, and packet loss "
        "samples for one WAN. For a point-in-time throughput test use "
        "`run_internet_speed_test`; for past results use `get_speed_tests`."
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
        "What were the last speed test results — stored download, upload, "
        "latency, and packet loss. To run a new test use "
        "`run_internet_speed_test`."
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
        "Poll the Firewalla box now and report the snapshot time it filled, "
        "without answering any question itself. Use it when the cached snapshot "
        "is stale and the answer depends on what is true right now — then read "
        "whichever tools the question needs. Requests within about 10 seconds are "
        "coalesced, so calling it before several reads costs one box poll rather "
        "than one per read."
    )
    parameters = vol.Schema({})
    _service = SERVICE_SYNC_RUNTIME
    _response_type = "runtime_sync"


class GetSystemOverviewTool(_FirewallaReadTool):
    """Return the curated system summary that anchors a session."""

    name = format_tool_name("get_system_overview")
    title = "Get system overview"
    description = (
        "The session anchor: appliance health, the networks with their host "
        "counts, and counts for hosts, VPN peers, groups, users, rules, and "
        "alarms. It also returns `system_model`, the one statement of this "
        "surface's vocabulary.\n"
        "\n"
        "It returns counts and identifiers only — never host or rule records. "
        "Answer per-host questions from `list_hosts` and per-rule questions from "
        "`list_rules`.\n"
        "\n" + _COUNTS_READING
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_INCLUDE,
                description=(
                    "Optional. Add the group and user names and ids that "
                    "get_user_usage and the rule tools accept as selectors. Each "
                    "entry carries `kind` of 'group' or 'user', so the two are "
                    "told apart by that field and never by name. "
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
        "General questions about this Firewalla network: appliance health, the "
        "networks with their host counts, and counts for hosts, VPN peers, and "
        "alarms.\n"
        "\n" + _COUNTS_READING + "\n"
        "\n"
        "This report is intentionally limited to counts, network names, and "
        "performance metrics — no host addresses, no hardware identifiers, and no "
        "group or user names. For those, or for rules, alarms, or usage detail, "
        "the user must raise Firewalla's AI access level in the integration "
        "options."
    )
    parameters = vol.Schema({})


class GetWirelessStatusTool(_FirewallaReadTool):
    """Return wireless status: SSIDs, access points, and clients."""

    name = format_tool_name("get_wireless_status")
    title = "Get wireless status"
    description = (
        "WiFi state: SSID profiles (with paused state), access points, and "
        "connected clients. The source for the `ssid_profile_id` that "
        "`set_ssid_paused` requires.\n"
        "\n"
        "Empty is meaningful: when the box manages no Firewalla access points "
        "there is no SSID to pause, and an empty `ssid_profiles` means exactly "
        "that rather than a failed read. `get_system_overview` reports whether "
        "the box has access points at all."
    )
    parameters = vol.Schema(
        {
            vol.Optional(SERVICE_FIELD_REFRESH, description=_REFRESH_DESCRIPTION): bool,
        }
    )
    _service = SERVICE_GET_WIRELESS_STATUS
    _response_type = "wireless_status"


class GetAlarmsTool(_FirewallaReadTool):
    """Return recent active and optionally archived alarms."""

    name = format_tool_name("get_alarms")
    title = "Get alarms"
    description = (
        "What is happening on the network — recent alarms, active, and archived "
        "when asked. Defaults to the 10 newest; raise `limit` deliberately, since "
        "a large alarm payload is expensive context.\n"
        "\n"
        "Silence records are omitted by default, and each alarm already carries "
        "its own `exception_id`, so `include_exceptions` is only for finding a "
        "silence to remove — that list is unbounded and is the expensive part of "
        "this response. The box keeps roughly 30 days and takes no time filter."
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
                    "Optional. Filter by alarm type. A raw `ALARM_*` value "
                    "(`ALARM_INTEL`, `ALARM_LARGE_UPLOAD`, …) or a supported "
                    "group: `security`, `abnormal_upload`, `open_port`. Matches "
                    "the `alarm_type` field on the returned records."
                ),
            ): str,
            vol.Optional(
                SERVICE_FIELD_DETAIL,
                default=DETAIL_SUMMARY,
                description=(
                    "Optional. 'full' fetches extended detail with one extra "
                    "request per returned alarm. Defaults to 'summary'."
                ),
            ): vol.In(DETAIL_LEVELS),
            vol.Optional(
                SERVICE_FIELD_INCLUDE_EXCEPTIONS,
                description=(
                    "Optional. Add the full silence-exception table, which is "
                    "unbounded. Defaults to false: each alarm already carries "
                    "its `exception_id`. Set this only to find a silence to "
                    "unmute."
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
    GetFlowReportTool,
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
