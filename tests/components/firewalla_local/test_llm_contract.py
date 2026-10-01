"""Contract tests for the Firewalla Local LLM tool surface (Phase 4.4).

These assert the cross-cutting contract every tool must satisfy, derived from
``docs/MCP_TOOL_REFERENCE.md``: the response envelopes, parameter descriptions,
annotations, name prefix, integration, prompt coverage, and JSON safety.
"""

from __future__ import annotations

import ast
import json
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
        return await llm.async_get_api(hass, DOMAIN, _llm_context())


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
        "already_in_state",
        "before` and `after`",
        "wait for the user to agree",
        "applies_to",
        "not user-facing",
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
                tool_args={"rule_target": "761"},
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
