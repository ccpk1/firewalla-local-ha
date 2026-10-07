"""Contract tests for the Firewalla Local LLM tool surface (Phase 4.4).

These assert the cross-cutting contract every tool must satisfy, derived from
``docs/MCP_TOOL_REFERENCE.md``: the response envelopes, parameter descriptions,
annotations, name prefix, integration, prompt coverage, and JSON safety.
"""

from __future__ import annotations

import ast
import json
import re
from importlib import import_module
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
from custom_components.firewalla_local.llm_tools_common import (
    CONTROL_INJECTION,
    DESTRUCTIVE_INJECTION,
    PROMPT,
    READ_INJECTION,
)
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

# Keys a response carries by passing the box's own object through unchanged, so they
# exist in the payload and can never appear as a literal in this package. Named as a
# **category** rather than a work list of exemptions: these are unreachable by any
# static scan, which is a different thing from a name we forgot to rename.
_PASSTHROUGH_PAYLOAD_KEYS: Final = frozenset(
    {"adblock", "safeSearch", "family", "doh", "monitor", "qos"}
)

# Backticked values a description quotes as literal data rather than naming a field.
_PROSE_IDENTIFIERS: Final = frozenset(
    {"null", "true", "false", "applied", "already_in_state", "failed"}
)

# The control tools whose manager applies the write to the in-memory snapshot, so
# their result reports `runtime: updated`. Everything else reports `pending`, either
# because it deliberately does not update local state or because it has none to
# update. Pinned here so a change to a tool's optimism is a deliberate edit.
_EXPECTED_UPDATED_TOOLS: Final = frozenset(
    {
        "PauseRuleTool",
        "ResumeRuleTool",
        "SetSsidPausedTool",
        "SetHostNameTool",
        "SetHostDnsHostnameTool",
        "SetHostDeviceTypeTool",
        "SetHostDhcpReservationTool",
        "SetHostNotifyWhenNextOnlineTool",
        "SetHostNotifyWhenNextOfflineTool",
        "BlockAlarmTargetTool",
        "UnblockAlarmTargetTool",
        "ArchiveAlarmTool",
        "ArchiveAllAlarmsTool",
        "DeleteAlarmTool",
        "DeleteAlarmsTool",
        "DeleteHostTool",
        "DeleteRuleTool",
    }
)

# Constants whose *value* names something a client sends or reads: an argument, an
# entity attribute, or a key this integration writes into a request to the box.
_NAME_CONSTANT_PREFIXES: Final = (
    "SERVICE_FIELD_",
    "ATTR_",
    "DETAIL_",
    "TARGET_KIND_",
    "_RAW_",
    "_COMMAND_",
)

_IDENTIFIER = re.compile(r"`([A-Za-z][A-Za-z0-9_.]*)`")

_PACKAGE_ROOT: Final = (
    Path(__file__).resolve().parents[3] / "custom_components" / "firewalla_local"
)


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """Return the ids of Constant nodes that are docstrings.

    Docstrings are the one kind of string literal that must **not** be in the corpus,
    and they are why the first attempt at this guard was decorative: a docstring in
    ``host_manager.py`` says ``host.last_active``, so collecting every string pulled
    the internal attribute name in and the stale reference resolved. They are
    identifiable by position — the first statement of a module, class or function —
    which is a property of where they sit rather than of what they say.
    """
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return docstrings


def _published_key_corpus() -> set[str]:
    """Return every name a description may legitimately reference.

    Three positions, and the distinction is the whole difference between a working
    guard and a decorative one.

    **Every string literal except a docstring.** That covers an enum value, a tool
    action, a field name, and a payload key wherever it is written — including the
    inline form ``"kind": "mac_host" if ... else "pseudo_host"``, whose strings are
    values inside a conditional and so are invisible to a scan that reads only dict
    keys. Excluding docstrings is what keeps it honest: they describe the code rather
    than the payload, so a docstring naming an internal attribute would let a stale
    field name resolve. The first version of this function collected every string,
    docstrings included, and passed on the very defect it exists to find.

    **A key in key position**, which is the payload field a description names.

    **A constant whose value is an argument or attribute name**, since
    `SERVICE_FIELD_*` and `ATTR_*` are how those are declared.
    """
    corpus: set[str] = set()

    for path in _PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(tree)

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                corpus.add(node.value)
            elif isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        corpus.add(key.value)
            elif isinstance(node, ast.Subscript):
                subscript = node.slice
                if isinstance(subscript, ast.Constant) and isinstance(
                    subscript.value, str
                ):
                    corpus.add(subscript.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if (
                    node.target.id.startswith(_NAME_CONSTANT_PREFIXES)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    corpus.add(node.value.value)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "format_tool_name"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                corpus.add(node.args[0].value)

    return corpus


def _unresolved_identifiers(text: str, corpus: set[str]) -> list[str]:
    """Return the identifiers one description names that resolve to nothing.

    A dotted path resolves if either the whole path or its final segment is known, so
    ``summary.host_count`` is satisfied by ``host_count``.
    """
    misses: list[str] = []
    for identifier in _IDENTIFIER.findall(text):
        head = identifier.split("(")[0].strip()
        if head in _PASSTHROUGH_PAYLOAD_KEYS or head in _PROSE_IDENTIFIERS:
            continue
        if head in corpus or head.rsplit(".", 1)[-1] in corpus:
            continue
        misses.append(head)
    return misses


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
        # open_world is always true: these tools reach the user's Firewalla box,
        # which is outside Home Assistant.
        assert tool.annotations.open_world is True, tool.name


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


async def test_every_identifier_in_a_description_resolves(
    hass: HomeAssistant,
) -> None:
    """No description names a field the package cannot produce.

    A description is prose *about* the payload, so it drifts the moment a field is
    renamed — and nothing noticed. The Time and Derived State renames updated the
    payload, the constants, the translations and the reference document, and left
    ``list_hosts`` telling the model to read ``` `last_active` ``` (epoch seconds)
    for a field that no longer existed under that name, in a form that had moved to
    its twin. The pairing guards could not see it: they assert key names in
    *payloads*, and a description is a string literal.

    Read from the **registered tools** rather than from source, so this checks the
    text a client actually receives — after composition, and including any family
    block. An AST scan of `description =` assignments misses the five membership
    tools, which build theirs by concatenating a shared constant, and those are the
    highest-risk descriptions on the surface.
    """
    api_instance = await _api_instance(hass)
    corpus = _published_key_corpus()

    unresolved = {
        tool.name: misses
        for tool in api_instance.tools
        if (misses := _unresolved_identifiers(tool.description, corpus))
    }

    assert unresolved == {}, (
        "these tool descriptions name identifiers the package does not produce, so a "
        "model is being told to read fields that do not exist — most likely a rename "
        f"that reached the payload but not the prose: {unresolved}"
    )


def test_the_description_identifier_scan_reads_real_text() -> None:
    """Test the scan found a corpus and reports a stale name, so a pass means something.

    Both failure modes are pinned. A corpus collected wrongly resolves too much: the
    first attempt took every string literal, which pulled ``last_active`` in through
    the model's own docstrings and made the scan pass on the exact defect it exists
    to find. A corpus collected too narrowly would flag every tool. So this asserts
    size, asserts a known key resolves, and **replays the defect** to prove the scan
    can still see it.
    """
    corpus = _published_key_corpus()

    assert len(corpus) > 500, (
        f"the corpus holds only {len(corpus)} names, so it is not reading the "
        "package; too little would resolve and every tool would fail"
    )
    assert "last_active_at" in corpus, "the corpus is missing a known published key"
    assert "list_rules" in corpus, "the corpus is missing a known tool action"

    # The defect, replayed. If prose naming the pre-rename field resolves, the corpus
    # has been contaminated by an internal name and the guard proves nothing.
    stale = _unresolved_identifiers("Read `last_active` for the last activity.", corpus)
    assert stale == ["last_active"], (
        "the scan does not report a stale field name — the corpus is resolving a name "
        "the package no longer publishes, so this guard would pass on the defect "
        "that prompted it"
    )

    # And a valid identifier must pass, so the scan is not flagging everything.
    assert _unresolved_identifiers("Read `last_active_at` instead.", corpus) == []


async def test_every_tool_carries_its_family_injection(
    hass: HomeAssistant,
) -> None:
    """Every description is composed as `injection + body`, and no tool is missed.

    The failure mode this guards is not a *wrong* block but a **missing** one. The
    composition lives in the base classes so a tool cannot be registered without it,
    and this asserts that from the outside — against the registered tools, so it
    holds for the composed text rather than for the class attribute.

    It also pins the destructive split in both directions. A destructive tool that
    kept the plain control block would omit the one thing a caller must know before
    writing, and a tool that is *not* destructive must not claim to be — that is how
    a model learns to distrust the warning.

    The channels are not equivalent, which is why this matters more than it looks:
    the API prompt reaches an MCP client only through MCP's `prompts` primitive,
    which the client must invoke explicitly, and `system_model` only arrives once
    `get_system_overview` has been called. A client that sends `tools/list` and goes
    straight to a write tool receives **only** these descriptions.
    """
    api_instance = await _api_instance(hass)

    control_names = {
        "firewalla_local__pause_rule",
        "firewalla_local__resume_rule",
    }

    missing: list[str] = []
    wrong_family: list[str] = []
    destructive_misfiled: list[str] = []

    for tool in api_instance.tools:
        carries_read = tool.description.startswith(READ_INJECTION)
        carries_control = tool.description.startswith(CONTROL_INJECTION)
        carries_destructive = tool.description.startswith(DESTRUCTIVE_INJECTION)

        if not (carries_read or carries_control or carries_destructive):
            missing.append(tool.name)
            continue

        # A destructive tool is the only kind that may carry the destructive block.
        if carries_destructive and not tool.annotations.destructive:
            destructive_misfiled.append(tool.name)

        if tool.name in control_names and carries_read:
            wrong_family.append(tool.name)

    assert missing == [], (
        "these tools carry no family injection, so a client that sends only "
        "`tools/list` receives none of the cross-cutting context: "
        f"{missing}"
    )
    assert destructive_misfiled == [], (
        "these tools carry the destructive block without being destructive, which "
        f"teaches a model to distrust it: {destructive_misfiled}"
    )
    assert wrong_family == [], (
        f"these control tools carry the read block: {wrong_family}"
    )

    # Every destructive tool must carry the destructive block, checked as its own
    # direction so a whole family cannot silently keep the weaker one.
    undecorated = [
        tool.name
        for tool in api_instance.tools
        if tool.annotations.destructive
        and not tool.description.startswith(DESTRUCTIVE_INJECTION)
    ]
    assert undecorated == [], (
        f"these destructive tools do not warn that they cannot be undone: {undecorated}"
    )


async def test_family_injections_say_what_the_model_cannot_get_elsewhere(
    hass: HomeAssistant,
) -> None:
    """Each block carries a rule the system model genuinely lacks.

    Modelled on the Control D finding that the control block should add *nothing*
    beyond orientation, because every control-wide rule it could carry (read state
    before writing, confirm wide-reaching changes, act on `undo`) was already in the
    system model — and repeating it would mean paying for the same sentence on every
    control tool.

    So this asserts the split rather than the wording: the read block adds the
    bounded-result rule, the destructive block adds no-undo, and the control block
    adds only orientation. If a future edit moves a rule into the control block that
    the model already states, this fails and the rule goes back.
    """
    api_instance = await _api_instance(hass)
    tools = {tool.name: tool for tool in api_instance.tools}

    # Read adds the bounded-result rule, which is not in the model.
    read_body = tools["firewalla_local__list_hosts"].description
    assert "truncated" in read_body
    assert "truncated" not in PROMPT, (
        "the model already covers truncated results, so the read block is repeating "
        "it on every read tool"
    )

    # Destructive adds no-undo, which is also not in the model.
    destructive_body = tools["firewalla_local__delete_host"].description
    assert "cannot be undone" in destructive_body
    assert "cannot be undone" not in PROMPT, (
        "the model already covers irreversibility, so the destructive block is "
        "repeating it on every destructive tool"
    )

    # Control adds orientation only, so it must be exactly that plus nothing.
    control_body = tools["firewalla_local__pause_rule"].description
    assert CONTROL_INJECTION in control_body
    assert len(CONTROL_INJECTION) < len(READ_INJECTION), (
        "the control block is longer than the read block, which suggests a rule "
        "crept in that the system model already states"
    )


async def test_every_control_tool_declares_its_runtime_contract(
    hass: HomeAssistant,
) -> None:
    """Each control result states whether the next read agrees with it.

    `ARCHITECTURE.md` requires a successful command to update in-memory runtime
    state. Some tools do not, deliberately: a membership change is not applied
    locally, muting an alarm changes nothing the snapshot carries, and neither a
    wake nor a speed test has state to reflect. So the contract is not "always
    true" — it is "always *stated*", and the result answers it in `runtime`.

    The declaration is checked per tool rather than against the base-class default,
    because that default is `pending`: a tool that forgets to declare under-claims
    freshness, which is recoverable, while a wrong `updated` would have a model
    present pre-change state as current. A family base may declare it for its
    members, but `_FirewallaControlTool` may not — that *is* the default.

    The expected split is pinned both ways, so flipping a tool's optimism means
    changing this list too, and cannot happen by accident.
    """
    control_module = import_module(
        "custom_components.firewalla_local.llm_tools_control"
    )
    control_base = control_module._FirewallaControlTool
    tool_classes = (
        *control_module._CONTROL_TOOL_CLASSES,
        *control_module._DESTRUCTIVE_TOOL_CLASSES,
    )

    undeclared: list[str] = []
    reporting_updated: set[str] = set()
    for tool_class in tool_classes:
        declares = [
            base
            for base in tool_class.__mro__
            if "_updates_runtime" in base.__dict__ and base is not control_base
        ]
        if not declares:
            undeclared.append(tool_class.__name__)
            continue
        if tool_class._updates_runtime:
            reporting_updated.add(tool_class.__name__)

    assert undeclared == [], (
        "these control tools inherit the default instead of stating whether the "
        f"local snapshot reflects the write: {undeclared}"
    )
    assert reporting_updated == _EXPECTED_UPDATED_TOOLS, (
        "the set of tools reporting `runtime: updated` changed; either the "
        "optimistic update was removed, or the declaration is wrong"
    )

    # And the field has to reach the model, because no tool description explains
    # the envelope: `status`, `undo` and `warnings` are enumerated in the system
    # model, so `runtime` belongs there with them and not in a family block.
    assert "`runtime`" in PROMPT
    assert "`runtime`" not in CONTROL_INJECTION, (
        "the envelope is documented in the system model; one field of it in the "
        "control block would make control the only family carrying envelope text"
    )


async def test_the_injection_check_distinguishes_the_families(
    hass: HomeAssistant,
) -> None:
    """Test the blocks are genuinely different, so the check above means something.

    A guard asserting "every tool carries its family block" is vacuous if all three
    blocks are the same string or if one is a prefix of another. This pins that each
    opens with the shared orientation sentence, that the three are distinct, and that
    none is a prefix of another.
    """
    assert READ_INJECTION != CONTROL_INJECTION != DESTRUCTIVE_INJECTION
    assert not CONTROL_INJECTION.startswith(DESTRUCTIVE_INJECTION)
    assert not DESTRUCTIVE_INJECTION.startswith(CONTROL_INJECTION)

    # All three open with the same orientation question, which is the one thing they
    # are meant to share.
    assert READ_INJECTION.startswith("**If you cannot clearly explain")
    assert CONTROL_INJECTION.startswith("**If you cannot clearly explain")
    assert DESTRUCTIVE_INJECTION.startswith("**If you cannot clearly explain")


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
        "wait for agreement",
        "applies_to",
        "Attachment **replaces**",
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

    assert "settings**, not rules" in config_description
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

    assert "Attachment **replaces**" in PROMPT
    assert "no longer reach it" in PROMPT
    assert "attachment replaces" in rules_description


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

    It reaches through a second channel that this test predates: the destructive
    tools carry `DESTRUCTIVE_INJECTION` in every description, and all four
    membership tools are in that family. That matters because the API prompt
    reaches an MCP client only if it invokes MCP's `prompts` primitive
    explicitly, so before the injections existed a client could reach
    `set_host_group` having received none of this.
    """
    assert "destroys the host's own rules" in PROMPT
    assert "enabled rules the user created" in PROMPT
    assert "host_rules.removed" in PROMPT
    # The blast radius must be bounded, or a model will over-warn and a user may
    # refuse a harmless change: only this host's rules go.
    assert "are unaffected" in PROMPT
    # And it must check first, so the confirmation is proportionate rather than
    # blanket on a call that often destroys nothing.
    assert "something to lose" in PROMPT
    # It must also be in the confirm-first list, or a model scanning that list
    # would classify a membership change as routine. Asserted against the whole
    # paragraph rather than a sentence index, so rewording the block cannot make
    # this pass or fail for a reason unrelated to what it checks.
    confirm_section = PROMPT.split("Confirm before anything wide-reaching", 1)[1]
    confirm_paragraph = confirm_section.split("\n\n", 1)[0]
    assert "membership change" in confirm_paragraph


async def test_the_user_filter_description_matches_what_the_filters_do(
    hass: HomeAssistant,
) -> None:
    """The two membership filters are described as they behave, not as they read.

    `group_name` matches the host's membership *label*, and for a host assigned to a
    user that label is the **user's name** — the box stores a group and a user as the
    same tag and resolves the label through the affiliated user first. Measured on
    the dev box: 32 of 218 hosts carry a user's name in `group_name`, and no name
    appears in both collections.

    The descriptions used to claim the opposite — "a user's name does not match here",
    "a user's name is never a valid group" — which was wrong in the one place a model
    would act on it. A model told a user's name cannot match would have chosen the
    wrong filter for "which hosts belong to KADENS_PHONE", or concluded the user had
    no hosts.

    The `user` filter is the exact one for that question, because it resolves the
    affiliated tag rather than matching a label, so the descriptions must point at it
    rather than deny the overlap exists.
    """
    api_instance = await _api_instance(hass)
    tools = {tool.name: tool for tool in api_instance.tools}

    hosts = tools["firewalla_local__list_hosts"]
    # The description lives on the marker, not on the schema value.
    group_param = next(
        marker for marker in hosts.parameters.schema if marker.schema == "group_name"
    )
    user_param = next(
        marker for marker in hosts.parameters.schema if marker.schema == "user"
    )

    # Neither may deny that a user's name appears in a host's membership label.
    assert "does not match" not in group_param.description
    assert "never a valid" not in group_param.description
    # The group filter states it takes either kind's name.
    assert "user's name" in group_param.description
    # The user filter says how it differs — exact by tag, not by label.
    assert "affiliated tag" in user_param.description


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
    assert "as `applies_to` to find the rules" in hosts_description
    assert "group_name" in applies_to
    assert "`applies_to`" in PROMPT
    assert "group_name" in PROMPT


# Each entry pairs a tool that returns a large payload with the phrase in its
# description that tells the model how to avoid paying for all of it.
_PAYLOAD_GUIDANCE: Final = (
    ("firewalla_local__list_hosts", "filters narrow on the box"),
    ("firewalla_local__list_rules", "User-visible rules only by default"),
    ("firewalla_local__get_network_config", "off by default"),
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
    assert (
        "Inactive hosts are included"
        in tools["firewalla_local__list_hosts"].description
    )

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
