"""Contract tests for the Firewalla Local LLM tool surface (Phase 4.4).

These assert the cross-cutting contract every tool must satisfy, derived from
``docs/MCP_TOOL_REFERENCE.md``: the response envelopes, parameter descriptions,
annotations, name prefix, integration, prompt coverage, and JSON safety.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Final
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_LLM_TOOL_MODE,
    CONF_SYMMETRIC_KEY,
    DOMAIN,
)
from custom_components.firewalla_local.llm_tools_common import PROMPT
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
)

# Response field names that carry a unit and must follow the suffix convention.
_UNIT_SUFFIXES: Final = (
    "_bytes",
    "_mbps",
    "_megabytes",
    "_ms",
    "_percent",
    "_seconds",
    "_minutes",
    "_count",
    "_timestamp",
    "_at",
    "_id",
    "_name",
    "_uuid",
)

# Suffixes that must never be attached to a non-conforming base. The _at/_timestamp
# pair is the one place an epoch could be mistaken for an ISO string.
_EPOCH_ONLY_SUFFIX: Final = "_timestamp"
_ISO_ONLY_SUFFIX: Final = "_at"


def _entry(*, mode: str = "full") -> MockConfigEntry:
    """Return a provisioned entry with the given LLM tool mode."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_LLM_TOOL_MODE: mode},
    )


def _snapshot() -> FirewallaRuntimeSnapshot:
    """Return a minimal snapshot with the required box host."""
    return FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="761",
                action="block",
                target="vimeo.com",
                target_type="dns",
                direction="bidirection",
                enabled=True,
                purpose=None,
                scope=(),
                raw_update_payload={"pid": "761"},
            ),
        ),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:00",
                host_name="Firewalla",
                ip_address="192.168.200.1",
                group_name=None,
                network_name=None,
                connection_type=None,
                last_active=None,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
            ),
        ),
        users=(),
    )


def _llm_context() -> llm.LLMContext:
    """Return a minimal LLM context."""
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


async def _api_instance(hass: HomeAssistant, *, mode: str = "full") -> llm.APIInstance:
    """Set up the entry and return the API instance for the given mode."""
    entry = _entry(mode=mode)
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "async_get_runtime_init_payload",
            new=AsyncMock(return_value={"policyRules": []}),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "build_runtime_snapshot",
            return_value=_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return await llm.async_get_api(hass, _api_id(hass), _llm_context())


async def test_every_tool_declares_the_full_contract(hass: HomeAssistant) -> None:
    """Every registered tool declares name, title, description, integration."""
    api_instance = await _api_instance(hass)

    assert api_instance.tools, "expected at least one registered tool"
    for tool in api_instance.tools:
        assert tool.name.startswith(f"{DOMAIN}__"), tool.name
        assert tool.title, tool.name
        assert tool.description, tool.name
        assert tool.integration == DOMAIN, tool.name
        # open_world is always false: these tools act on the user's own box.
        assert tool.annotations.open_world is False, tool.name


async def test_every_parameter_has_a_description(hass: HomeAssistant) -> None:
    """Every tool parameter carries a description for the model."""
    api_instance = await _api_instance(hass)

    for tool in api_instance.tools:
        for marker in tool.parameters.schema:
            assert marker.description, f"{tool.name} field {marker} lacks a description"


async def test_destructive_annotation_matches_the_documented_set(
    hass: HomeAssistant,
) -> None:
    """Only the Full-mode destructive tools declare destructive=True."""
    documented_destructive = {
        "firewalla_local__archive_all_alarms",
        "firewalla_local__delete_alarm",
        "firewalla_local__delete_all_alarms",
        "firewalla_local__delete_host",
        "firewalla_local__delete_rule",
        # A membership change deletes the rules attached to the device and cannot
        # restore them, so all four are destructive rather than controls.
        "firewalla_local__set_host_group",
        "firewalla_local__clear_host_group",
        "firewalla_local__set_host_user",
        "firewalla_local__clear_host_user",
    }
    api_instance = await _api_instance(hass)

    declared = {
        tool.name for tool in api_instance.tools if tool.annotations.destructive
    }
    assert declared == documented_destructive


async def test_read_tools_are_read_only_and_writes_are_not(
    hass: HomeAssistant,
) -> None:
    """read_only splits cleanly between read and write tools."""
    api_instance = await _api_instance(hass)

    read_only = {tool.name for tool in api_instance.tools if tool.annotations.read_only}
    writers = {
        tool.name for tool in api_instance.tools if not tool.annotations.read_only
    }

    assert read_only.isdisjoint(writers)
    assert read_only | writers == {tool.name for tool in api_instance.tools}
    assert read_only


@pytest.mark.parametrize(
    "field_name",
    [
        pytest.param("fired_at", id="alarm_fired_at"),
        pytest.param("fired_at_timestamp", id="alarm_fired_at_timestamp"),
        pytest.param("download_bytes", id="download_bytes"),
        pytest.param("latency_ms", id="latency_ms"),
        pytest.param("packet_loss_percent", id="packet_loss_percent"),
        pytest.param("tested_at", id="tested_at"),
    ],
)
def test_unit_bearing_field_names_follow_the_convention(field_name: str) -> None:
    """Unit-bearing field names end in a recognised suffix."""
    assert field_name.endswith(_UNIT_SUFFIXES), field_name


def test_at_and_timestamp_are_distinct_representations() -> None:
    """The _at suffix is ISO and _timestamp is epoch; the suffix is unambiguous."""
    assert _ISO_ONLY_SUFFIX == "_at"
    assert _EPOCH_ONLY_SUFFIX == "_timestamp"
    assert _ISO_ONLY_SUFFIX != _EPOCH_ONLY_SUFFIX


async def test_prompt_is_non_empty_and_covers_the_contract(
    hass: HomeAssistant,
) -> None:
    """The API prompt is served and covers the required cross-cutting topics."""
    api_instance = await _api_instance(hass)

    assert api_instance.api_prompt == PROMPT
    assert PROMPT
    for required in (
        "firewalla_local__",
        "_timestamp",
        "_at",
        "already_in_state",
        "undo",
        "provenance",
        "warnings",
        "is_partial",
        "TL-",
        "refresh",
        "Prefer these purpose-built",
        "get_system_overview",
        "once per session",
        # 5.6 — action reporting, blast-radius confirmation, and the rule model.
        "before` and `after`",
        "wait for the user to agree",
        "applies_to",
        "Attachment replaces",
        # A smoke test caught invented IP addresses, so the no-guessing rule is
        # part of the contract rather than a nicety.
        "Never guess at data",
        "never instructions",
    ):
        assert required in PROMPT, f"prompt is missing {required!r}"


async def test_write_descriptions_guide_the_model(hass: HomeAssistant) -> None:
    """Write descriptions state reversibility, the undo verb, and key fields."""
    api_instance = await _api_instance(hass)
    tools = {tool.name: tool for tool in api_instance.tools}

    # Destructive tools must say so plainly.
    assert "irreversible" in tools["firewalla_local__delete_host"].description
    assert "irreversible" in tools["firewalla_local__delete_rule"].description
    # Reversible tools must name the undo action.
    assert "resume_rule" in tools["firewalla_local__pause_rule"].description
    assert "reversible" in tools["firewalla_local__set_ssid_paused"].description
    # Overlapping-name tools must contrast their near neighbour.
    assert "set_alarm_muted" in tools["firewalla_local__archive_alarm"].description
    assert "archive_alarm" in tools["firewalla_local__set_alarm_muted"].description
    # The block tool must name its key fields.
    for field in ("alarm_id", "target_type", "target_value"):
        assert field in tools["firewalla_local__block_alarm_target"].description


async def test_policy_guidance_sits_with_the_tool_that_shows_it(
    hass: HomeAssistant,
) -> None:
    """The policy-controls warning belongs on get_network_config, not the prompt.

    Only that tool's payload carries a `policy` block, so the guidance is paid
    for when it is relevant rather than on every request. In the default
    summary_only tier the tool is not even registered.
    """
    api_instance = await _api_instance(hass)
    tools = {tool.name: tool for tool in api_instance.tools}
    config_description = tools["firewalla_local__get_network_config"].description

    assert "settings, not rules" in config_description
    assert "`family` rule purpose" in config_description
    assert "policy" not in PROMPT


async def test_rule_scope_precedence_is_stated_consistently(
    hass: HomeAssistant,
) -> None:
    """The prompt and list_rules agree that attachment replaces device rules.

    Two different mental models here would be worse than one imprecise one: the
    agent would have to guess which to believe when asked what covers a device.
    """
    api_instance = await _api_instance(hass)
    tools = {tool.name: tool for tool in api_instance.tools}
    rules_description = tools["firewalla_local__list_rules"].description

    assert "Attachment replaces" in PROMPT
    assert "no longer apply" in PROMPT
    assert "no longer apply" in rules_description


async def test_membership_change_warns_that_it_deletes_host_rules(
    hass: HomeAssistant,
) -> None:
    """The prompt says a membership change deletes the host's rules.

    This is destructive and cannot be undone by the tool, so a model that
    discovers it only from the call result has already done the damage. Verified
    by capture: assigning an unassigned device to a group deleted every rule it
    owned — enabled ones included — and the box removed them outright rather than
    detaching them.

    Checked against the prompt, which is served as the API prompt, because the
    four membership tools are added in a later phase and this guidance must exist
    before a model can call one.
    """
    assert "DELETES THE RULES ATTACHED TO THAT HOST" in PROMPT
    assert "enabled rules the user created" in PROMPT
    assert "host_rules.removed" in PROMPT
    # The blast radius must be bounded, or a model will over-warn and a user may
    # refuse a harmless change: only this host's rules go.
    assert "are NOT affected" in PROMPT
    # And it must check first, so the confirmation is proportionate rather than
    # blanket on a call that often destroys nothing.
    assert "Check before you ask" in PROMPT
    # It must also be in the confirm-first list, or a model scanning that list
    # would classify a membership change as routine.
    confirm_paragraph = PROMPT.split("Confirm before wide-reaching changes", 1)[1]
    assert "membership" in confirm_paragraph.split(".", 2)[1]


async def test_host_group_to_rules_chain_is_stated(hass: HomeAssistant) -> None:
    """A host's group_name is named as the input to list_rules' applies_to.

    A smoke test asked "what rules apply to <device>", and the model found the
    host and its group_name, then stopped. Both descriptions were individually
    complete but nothing connected them, so the answer required inferring that
    the two fields share a vocabulary. They do — both resolve tag references
    through affiliated users then tags — but that has to be said, not inferred.
    """
    api_instance = await _api_instance(hass)
    tools = {tool.name: tool for tool in api_instance.tools}

    hosts_description = tools["firewalla_local__list_hosts"].description
    applies_to = next(
        marker.description
        for marker in tools["firewalla_local__list_rules"].parameters.schema
        if marker.schema == "applies_to"
    )

    assert "`group_name`" in hosts_description
    assert "rule lookup" in hosts_description
    assert "group_name" in applies_to
    assert "`applies_to`" in PROMPT
    assert "group_name" in PROMPT


# Each entry pairs a tool that returns a large payload with the phrase in its
# description that tells the model how to avoid paying for all of it.
_PAYLOAD_GUIDANCE: Final = (
    ("firewalla_local__list_hosts", "filters to narrow"),
    ("firewalla_local__list_rules", "Filters narrow the result"),
    ("firewalla_local__get_network_config", "not included by default"),
    ("firewalla_local__get_user_usage", "pass `sections`"),
)


async def test_count_totals_are_not_presented_as_connected(
    hass: HomeAssistant,
) -> None:
    """The counts describe themselves, so `total` is not read as "connected".

    A smoke test asked "are there any VPN devices connected?" and got five, all
    named, because `list_hosts` returned every configured peer with no
    connectivity signal and the overview's counts were the only place `online`
    appeared. Every surface that reports a total now says what it means, and
    `list_hosts` carries the per-device `online` the answer actually needs.
    """
    api_instance = await _api_instance(hass)
    tools = {tool.name: tool for tool in api_instance.tools}

    for tool_name in (
        "firewalla_local__get_system_overview",
        "firewalla_local__list_hosts",
    ):
        description = tools[tool_name].description
        assert "connected" in description, tool_name
        assert "online" in description, tool_name

    # Past hosts ARE included: the init request sets includeInactiveHosts,
    # which is what the app's "Show past devices" toggle does. A live Quarantine
    # group returned 10 hosts, 7 of them long-idle, so membership here is the
    # group's full host list.
    assert "Past hosts are included" in tools["firewalla_local__list_hosts"].description

    config = tools["firewalla_local__list_hosts"].parameters.schema
    assert any(marker.schema == "online" for marker in config)


# Tool parameters deliberately not exposed, keyed by tool name, with the reason.
# Anything not listed here must be reachable from the tool that wraps it.
_INTENTIONAL_OMISSIONS: Final = frozenset(
    {
        # The destructive gate is set internally; asking the model to confirm
        # itself would prove nothing.
        ("unblock_alarm_target", "confirm"),
        # The flow report's `detail` and `record_count` ARE exposed, because
        # diagnosis needs the individual records: a record names the rule that
        # blocked it, and the rollup's blocked families carry no rule reference at
        # all -- verified by dumping every key of a live rollup, where the only
        # `policy` key is the target's own policy block, not a rule id. So
        # "which rule stopped this" is answerable only at records detail.
        #
        # `fetch_all_records` stays internal: it walks the cursor to exhaustion
        # with only a wall-clock deadline as a stop, so a single call could return
        # an unbounded number of rows into a model's context.
        ("get_flow_report", "fetch_all_records"),
        # Flow data is read live on every call, so this only refreshes the
        # runtime snapshot the report's names are resolved from. The service
        # defaults it to true, which is what the tool wants, so omitting it
        # avoids a lever the model would have no reason to move.
        ("get_flow_report", "refresh"),
        # Bulk tools act on the set they name; single-alarm tools act on an
        # alarm id. Splitting them means neither tool exposes the other's
        # selector: `archive_all_alarms` acts on the active set, which its own
        # name already states, and `archive_alarm`/`delete_alarm` act on one
        # alarm, so a status would be a second selector for a call that has
        # already made its choice.
        ("archive_alarm", "alarm_status"),
        ("archive_all_alarms", "alarm_id"),
        ("archive_all_alarms", "alarm_status"),
        ("delete_alarm", "alarm_status"),
        ("delete_all_alarms", "alarm_id"),
        # `detail` and `include: ['subperiods']` both select the nested
        # breakdown, so the tool offers one lever rather than two.
        ("get_wan_usage", "detail"),
        # Writes refresh internally, and host_id is never threaded by hand
        # because the tools take a human-meaningful name or MAC.
        ("set_host_name", "host_id"),
        ("set_host_name", "refresh"),
        ("set_host_dns_hostname", "host_id"),
        ("set_host_dns_hostname", "refresh"),
        ("set_host_device_type", "host_id"),
        ("set_host_device_type", "refresh"),
        ("set_host_dhcp_reservation", "host_id"),
        ("set_host_dhcp_reservation", "refresh"),
        ("set_host_notify_when_next_online", "host_id"),
        ("set_host_notify_when_next_online", "refresh"),
        ("set_host_notify_when_next_offline", "host_id"),
        ("set_host_notify_when_next_offline", "refresh"),
        ("wake_host", "host_id"),
        ("wake_host", "refresh"),
        ("delete_host", "refresh"),
        # The four membership tools each expose only their own kind's selector,
        # which is the whole reason there are four of them rather than one tool
        # with a free-text target. A group and a user can share a name on a real
        # box, so a tool that accepted both could silently target the wrong kind.
        # Exposing the other kind's fields here would reintroduce exactly that.
        ("set_host_group", "user_name"),
        ("set_host_group", "user_id"),
        ("set_host_group", "clear"),
        ("set_host_group", "host_id"),
        ("set_host_group", "refresh"),
        ("set_host_user", "group_name"),
        ("set_host_user", "group_id"),
        ("set_host_user", "clear"),
        ("set_host_user", "host_id"),
        ("set_host_user", "refresh"),
        # The clear tools take a host and nothing else; the kind is in the tool
        # name, so both selectors are absent.
        ("clear_host_group", "group_name"),
        ("clear_host_group", "group_id"),
        ("clear_host_group", "user_name"),
        ("clear_host_group", "user_id"),
        ("clear_host_group", "host_id"),
        ("clear_host_group", "refresh"),
        ("clear_host_user", "group_name"),
        ("clear_host_user", "group_id"),
        ("clear_host_user", "user_name"),
        ("clear_host_user", "user_id"),
        ("clear_host_user", "host_id"),
        ("clear_host_user", "refresh"),
    }
)


async def test_tools_expose_their_service_parameters(hass: HomeAssistant) -> None:
    """A tool must accept everything its service accepts, or say why not.

    `get_network_config`'s description told the model to pass `include: ['hosts']`
    while the tool declared only the network selector and `refresh`, so the device
    list the description promised was unreachable. `set_host_dhcp_reservation` had
    the same shape: the service takes a network selector for multi-network
    ambiguity, and the tool did not expose it.

    The allowlist is deliberately explicit — an omission has to be justified here
    rather than discovered in a user's session.
    """
    from custom_components.firewalla_local.services import _SERVICE_REGISTRATIONS

    schemas = {name: schema for name, _h, schema, *_ in _SERVICE_REGISTRATIONS}
    api_instance = await _api_instance(hass)

    gaps: list[str] = []
    for tool in api_instance.tools:
        action = tool.name.removeprefix(f"{DOMAIN}__")
        declared = {marker.schema for marker in tool.parameters.schema}
        # config entry selectors are injected by the base class, not declared.
        declared |= {"config_entry_id", "config_entry_name"}
        service_fields = {marker.schema for marker in schemas[tool._service].schema}
        for field in sorted(service_fields - declared):
            if (action, field) in _INTENTIONAL_OMISSIONS:
                continue
            gaps.append(f"{tool.name} does not expose {tool._service}.{field}")

    assert gaps == [], f"service parameters missing from tools: {gaps}"


async def test_large_payload_tools_tell_the_model_to_narrow(
    hass: HomeAssistant,
) -> None:
    """Tools with filters must say so, or the model lists everything first.

    These descriptions are the model's only cue that narrowing is possible. The
    observed failure without them is "list everything, then narrow", and the
    full host inventory alone is roughly 18k tokens. Each tool already has the
    filters — this is one line of guidance, not a new capability — so the test
    pins the guidance rather than the filters.
    """
    api_instance = await _api_instance(hass)
    tools = {tool.name: tool for tool in api_instance.tools}

    for tool_name, expected_phrase in _PAYLOAD_GUIDANCE:
        assert expected_phrase in tools[tool_name].description, tool_name


_REFERENCE_PATH: Final = Path(__file__).parents[3] / "docs" / "MCP_TOOL_REFERENCE.md"


async def test_reference_documents_every_registered_tool(
    hass: HomeAssistant,
) -> None:
    """Every registered tool is named in the reference, in some form.

    The reference is the authoritative spec, but nothing tied it to the code:
    `sync_runtime` and `unmute_alarm` shipped without a word in it, and the
    `get_network_config` entry described an optional network selector the handler
    requires. This asserts the cheap half of that contract — the reference must
    at least name every tool — so a new tool cannot land undocumented.
    """
    reference = _REFERENCE_PATH.read_text(encoding="utf-8")
    api_instance = await _api_instance(hass)

    # Section headings use the full prefixed name; the index, the destructive
    # list, and combined headings (the notify pair) use the bare action name.
    undocumented = sorted(
        tool.name
        for tool in api_instance.tools
        if f"`{tool.name}`" not in reference
        and f"`{tool.name.removeprefix(f'{DOMAIN}__')}`" not in reference
    )

    assert undocumented == [], f"tools missing from the reference: {undocumented}"


# Parameters documented once for every tool in the Conventions section rather
# than repeated per tool, so sections are not required to name them.
_SHARED_PARAMS: Final = frozenset(
    {
        "refresh",
        # "Host-targeting tools accept a human-meaningful `host` (name or MAC)".
        "host_mac",
        "host_name",
        # The per-tool "wan_uuid / wan_name (optional — for multi-WAN)" wording.
        "wan_uuid",
        "wan_name",
    }
)


async def test_reference_documents_each_tools_declared_inputs(
    hass: HomeAssistant,
) -> None:
    """A tool's Inputs line must name the parameters the tool actually accepts.

    The reference drifted in ways only a reader would notice — a
    documented-but-required-optional network, `count`/`type` where the schema
    says `limit`/`alarm_type`, and a "default 10" that the tool sets to 1. Each
    would have caused a wrong or wasteful call.

    The check reads only the **Inputs** bullet, not the whole section. Matching
    the whole section gave a false negative for exactly the case above: `type`
    was misspelled as the input name but appeared in the *Returns* line as an
    output field, so the check passed on the wrong word.
    """
    reference = _REFERENCE_PATH.read_text(encoding="utf-8")
    sections = {
        match.group(1): match.group(2)
        for match in re.finditer(
            r"^### `firewalla_local__([a-z_]+)`(.*?)(?=^### |^## |\Z)",
            reference,
            re.S | re.M,
        )
    }
    api_instance = await _api_instance(hass)

    gaps: list[str] = []
    for tool in api_instance.tools:
        action = tool.name.removeprefix(f"{DOMAIN}__")
        section = sections.get(action)
        if section is None:
            # Combined headings (the notify pair) and the destructive list are
            # covered by the coverage test above.
            continue
        inputs_match = re.search(
            r"\*\*Inputs[^:]*:\*\*(.*?)(?=\n- \*\*|\Z)", section, re.S
        )
        inputs = inputs_match.group(1) if inputs_match else ""
        for marker in tool.parameters.schema:
            name = marker.schema
            if name in _SHARED_PARAMS or f"`{name}`" in inputs:
                continue
            gaps.append(f"{tool.name}: {name}")

    assert gaps == [], f"parameters missing from the reference: {gaps}"


async def test_read_envelope_is_json_serializable(hass: HomeAssistant) -> None:
    """A read tool's result serializes with the stdlib JSON encoder."""
    api_instance = await _api_instance(hass)

    result = await api_instance.async_call_tool(
        llm.ToolInput(tool_name="firewalla_local__list_rules", tool_args={})
    )

    assert result.error is False
    json.dumps(result.data)  # raises TypeError if a value is not JSON-safe
    assert "result" in result.data
    assert "meta" in result.data


async def test_action_result_envelope_is_json_serializable(
    hass: HomeAssistant,
) -> None:
    """A control tool's action-result envelope serializes with the stdlib encoder."""
    api_instance = await _api_instance(hass)

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient."
        "async_update_rule_control_only",
        new=AsyncMock(),
    ):
        result = await api_instance.async_call_tool(
            llm.ToolInput(
                tool_name="firewalla_local__pause_rule",
                tool_args={"rule_id": "761"},
            )
        )

    json.dumps(result.data)
    for key in ("status", "changed", "target", "before", "after", "undo", "warnings"):
        assert key in result.data, key
    # `before` is the observed state and `after` the requested state; both are
    # present even when unknown, so the envelope shape is stable.
    assert result.data["before"] == {"enabled": True, "is_paused": False}
    assert result.data["after"] == {"enabled": False, "is_paused": True}


# The credential-bearing config keys. A module that never names one cannot
# serialize it, which is the guarantee the user-facing docs make.
_CREDENTIAL_CONSTANTS: Final = frozenset(
    {"CONF_SYMMETRIC_KEY", "CONF_LICENSE", "CONF_AID", "CONF_EID", "CONF_GID"}
)
_CREDENTIAL_LITERALS: Final = frozenset(
    {"symmetric_key", "license", "aid", "eid", "gid"}
)

# Every module that builds tool output: the service layer the tools delegate to,
# plus the tool modules themselves.
_TOOL_OUTPUT_MODULES: Final = (
    "services.py",
    "llm_tools_read.py",
    "llm_tools_control.py",
    "llm_tools_common.py",
)


def test_tool_output_paths_cannot_reach_credentials() -> None:
    """No module that produces tool output references credential material.

    This is the structural form of the published claim that pairing keys,
    symmetric keys, and passwords cannot appear in tool output "by construction,
    not by filtering": entry.data holds them, no service reads it, and every raw
    payload read pulls a named non-sensitive subkey instead of the whole payload.

    Asserting on the source rather than on a sample response means a new field
    cannot quietly start leaking — wiring a credential in fails here first.
    """
    package_root = Path(__file__).parents[3] / "custom_components" / "firewalla_local"
    offenders: list[str] = []

    for module_name in _TOOL_OUTPUT_MODULES:
        tree = ast.parse((package_root / module_name).read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        for name in sorted(names & _CREDENTIAL_CONSTANTS):
            offenders.append(f"{module_name}: references {name}")
        for literal in sorted(literals & _CREDENTIAL_LITERALS):
            offenders.append(f"{module_name}: literal {literal!r}")

    assert offenders == []


def _api_id(hass: HomeAssistant) -> str:
    """Return the id of the registered Firewalla LLM API.

    The id always carries a per-entry suffix, so it is never the bare domain;
    the suffix is derived from the entry title.
    """
    return next(
        api.id for api in llm.async_get_apis(hass) if api.id.startswith(f"{DOMAIN}-")
    )


def test_reference_does_not_offer_a_config_entry_input() -> None:
    """Tools are pre-bound to one box, so no tool input selects an entry.

    The entry id is injected into the backing service call by the tool wrapper.
    Documenting `config_entry_id` / `config_entry_name` as an input invites a
    call the tool must reject, which is exactly the guidance an agent would
    follow. The reference states the rule once, in Conventions; it must not
    appear in any tool's Inputs.
    """
    reference = _REFERENCE_PATH.read_text(encoding="utf-8")
    offenders: list[str] = []

    for match in re.finditer(
        r"^### `firewalla_local__([a-z_]+)`(.*?)(?=^### |^## |\Z)",
        reference,
        re.S | re.M,
    ):
        action, section = match.group(1), match.group(2)
        for inputs in re.finditer(
            r"\*\*Inputs[^:]*:\*\*(.*?)(?=\n- \*\*|\Z)", section, re.S
        ):
            if "config_entry_id" in inputs.group(1) or (
                "config_entry_name" in inputs.group(1)
            ):
                offenders.append(action)

    assert offenders == [], f"tools advertising a config-entry input: {offenders}"
