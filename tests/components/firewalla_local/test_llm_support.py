"""Tests for the LLM/MCP tool surface foundation (Phase 4.1)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Final
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.firewalla_local as firewalla_local
from custom_components.firewalla_local.const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_LLM_TOOL_MODE,
    CONF_SYMMETRIC_KEY,
    DEFAULT_LLM_TOOL_MODE,
    DOMAIN,
    LLM_TOOL_MODE_OFF,
    LLM_TOOL_MODE_READ_ONLY,
    MIN_LLM_TOOLS_HA_VERSION,
)
from custom_components.firewalla_local.helpers.llm_support import llm_tools_supported
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaHostRuntime,
    FirewallaRuntimeSnapshot,
)

# Modules that are guard-loaded (imported only when LLM tools are supported) and
# are therefore allowed to import Core 2026.10-only LLM names at module level.
_GUARD_LOADED_MODULES: Final = frozenset(
    {
        "llm_api.py",
        "llm_tools_read.py",
        "llm_tools_control.py",
        "llm_tools_common.py",
    }
)

_PROBATIO: Final = "probatio"
_LLM_HELPER_MODULE: Final = "homeassistant.helpers.llm"
_LLM_API_MODULE: Final = "custom_components.firewalla_local.llm_api"
_LLM_TOOL_CONTRACT_NAMES: Final = frozenset({"ToolResult", "ToolAnnotations"})


def _entry(*, options: dict[str, object] | None = None) -> MockConfigEntry:
    """Return a provisioned Firewalla config entry."""
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
        options=options or {},
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


def _mock_snapshot() -> FirewallaRuntimeSnapshot:
    """Return a minimal runtime snapshot for setup tests."""
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
        policy_rules=(),
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


@pytest.mark.parametrize(
    ("major", "minor", "expected"),
    [
        pytest.param(
            MIN_LLM_TOOLS_HA_VERSION[0],
            MIN_LLM_TOOLS_HA_VERSION[1] - 1,
            False,
            id="just_below",
        ),
        pytest.param(*MIN_LLM_TOOLS_HA_VERSION, True, id="at_boundary"),
        pytest.param(
            MIN_LLM_TOOLS_HA_VERSION[0],
            MIN_LLM_TOOLS_HA_VERSION[1] + 1,
            True,
            id="just_above",
        ),
    ],
)
def test_llm_tools_supported_boundaries(major: int, minor: int, expected: bool) -> None:
    """The version predicate compares the integration's bound version tuple."""
    with (
        patch(
            "custom_components.firewalla_local.helpers.llm_support.MAJOR_VERSION",
            major,
        ),
        patch(
            "custom_components.firewalla_local.helpers.llm_support.MINOR_VERSION",
            minor,
        ),
    ):
        assert llm_tools_supported() is expected


@pytest.mark.parametrize(
    ("mode", "expected_registered"),
    [
        pytest.param(DEFAULT_LLM_TOOL_MODE, True, id="default_mode_registers"),
        pytest.param(LLM_TOOL_MODE_OFF, False, id="off_registers_nothing"),
    ],
)
async def test_setup_registers_api_only_when_enabled(
    hass: HomeAssistant, mode: str, expected_registered: bool
) -> None:
    """Setup registers the LLM API for enabled modes and nothing for off."""
    entry = _entry(options={CONF_LLM_TOOL_MODE: mode})
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
            return_value=_mock_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    registered_ids = {api.id for api in llm.async_get_apis(hass)}
    assert (DOMAIN in registered_ids) is expected_registered


async def test_default_mode_registers_only_the_anonymous_summary(
    hass: HomeAssistant,
) -> None:
    """A fresh entry defaults to summary_only with exactly one tool registered."""
    entry = _entry()
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
            return_value=_mock_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        api_instance = await llm.async_get_api(hass, DOMAIN, _llm_context())

    assert {tool.name for tool in api_instance.tools} == {
        "firewalla_local__get_system_overview"
    }


async def test_anonymous_summary_cannot_request_identifiers(
    hass: HomeAssistant,
) -> None:
    """The anonymous tier's tool offers no way to ask for group/user identity.

    The privacy claim is structural: rather than filtering identities out of a
    response, the tier's tool has no parameter that could ask for them, and the
    other tools are not registered at all.
    """
    entry = _entry()
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
            return_value=_mock_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        api_instance = await llm.async_get_api(hass, DOMAIN, _llm_context())

    (tool,) = api_instance.tools
    assert not tool.parameters.schema


async def test_read_mode_registers_the_full_read_set(
    hass: HomeAssistant,
) -> None:
    """read_only registers the summary alongside every other read tool."""
    entry = _entry(options={CONF_LLM_TOOL_MODE: LLM_TOOL_MODE_READ_ONLY})
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
            return_value=_mock_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        api_instance = await llm.async_get_api(hass, DOMAIN, _llm_context())

    names = {tool.name for tool in api_instance.tools}
    assert "firewalla_local__get_system_overview" in names
    assert "firewalla_local__list_hosts" in names


async def test_setup_succeeds_without_llm_tools_on_old_core(
    hass: HomeAssistant,
) -> None:
    """On unsupported Core, setup succeeds and no LLM API is registered."""
    entry = _entry(options={CONF_LLM_TOOL_MODE: DEFAULT_LLM_TOOL_MODE})
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
            return_value=_mock_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=False,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert DOMAIN not in {api.id for api in llm.async_get_apis(hass)}


async def test_setup_survives_llm_layer_failure(hass: HomeAssistant) -> None:
    """A failure in the optional AI layer must not break entry setup.

    Reproduces the real failure mode: on Core older than the tool contract the
    guard-loaded tool modules raise on import. Setup must still succeed and the
    integration must stay usable.
    """
    entry = _entry(options={CONF_LLM_TOOL_MODE: DEFAULT_LLM_TOOL_MODE})
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
            return_value=_mock_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
        patch.dict(sys.modules, {_LLM_API_MODULE: None}),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert DOMAIN not in {api.id for api in llm.async_get_apis(hass)}


async def test_api_is_unregistered_on_entry_unload(hass: HomeAssistant) -> None:
    """Unloading the entry removes the registered LLM API."""
    entry = _entry(options={CONF_LLM_TOOL_MODE: DEFAULT_LLM_TOOL_MODE})
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
            return_value=_mock_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert DOMAIN in {api.id for api in llm.async_get_apis(hass)}

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert DOMAIN not in {api.id for api in llm.async_get_apis(hass)}


async def test_options_change_to_llm_mode_re_registers_without_manual_reload(
    hass: HomeAssistant,
) -> None:
    """Changing the LLM tool mode must re-register the API on its own.

    The options update listener only reloads when a *meaningful* setting changed.
    The LLM tool mode was missing from that comparison, so a mode change left the
    API registered with its old tool set until the user reloaded by hand.
    """
    entry = _entry(options={CONF_LLM_TOOL_MODE: LLM_TOOL_MODE_OFF})
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
            return_value=_mock_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert DOMAIN not in {api.id for api in llm.async_get_apis(hass)}

        # A mode change alone must trigger the reload, with no manual reload.
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_LLM_TOOL_MODE: DEFAULT_LLM_TOOL_MODE},
        )
        await hass.async_block_till_done()

        assert DOMAIN in {api.id for api in llm.async_get_apis(hass)}


async def test_options_change_unrelated_to_llm_does_not_reload(
    hass: HomeAssistant,
) -> None:
    """An option change that alters nothing meaningful must not reload.

    Guard against over-correcting: adding the LLM mode to the reload comparison
    must not make every options save reload the entry.
    """
    entry = _entry(options={CONF_LLM_TOOL_MODE: DEFAULT_LLM_TOOL_MODE})
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
            return_value=_mock_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with patch.object(
            hass.config_entries, "async_reload", new=AsyncMock()
        ) as mock_reload:
            hass.config_entries.async_update_entry(
                entry,
                options={
                    **entry.options,
                    CONF_LLM_TOOL_MODE: DEFAULT_LLM_TOOL_MODE,
                },
            )
            await hass.async_block_till_done()

        mock_reload.assert_not_awaited()

    assert DOMAIN in {api.id for api in llm.async_get_apis(hass)}


@pytest.mark.parametrize(
    ("supported", "expected_present"),
    [
        pytest.param(True, True, id="supported_shows_field"),
        pytest.param(False, False, id="unsupported_hides_field"),
    ],
)
async def test_options_toggle_visibility(
    hass: HomeAssistant, supported: bool, expected_present: bool
) -> None:
    """The LLM tool-mode field appears in options only when supported."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.firewalla_local.config_flow.llm_tools_supported",
        return_value=supported,
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={"next_step_id": "general_options"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={"next_step_id": "system_settings"}
        )

    schema_keys = {marker.schema for marker in result["data_schema"].schema}
    assert (CONF_LLM_TOOL_MODE in schema_keys) is expected_present


def test_no_eager_llm_imports() -> None:
    """Unconditionally-loaded modules must not import Core 2026.10-only names.

    A module-level import of ``probatio`` or of ``ToolResult``/``ToolAnnotations``
    is an ``ImportError`` at load time on older Core, which a latest-only CI run
    never surfaces. Only the guard-loaded ``llm_api.py`` may contain them.
    """
    package_root = Path(firewalla_local.__file__).parent
    offenders: list[str] = []

    for path in package_root.rglob("*.py"):
        if path.name in _GUARD_LOADED_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # module level only
            if isinstance(node, ast.Import):
                if any(
                    alias.name.partition(".")[0] == _PROBATIO for alias in node.names
                ):
                    offenders.append(f"{path}: import {_PROBATIO}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.partition(".")[0] == _PROBATIO:
                    offenders.append(f"{path}: from {module} import ...")
                elif module == _LLM_HELPER_MODULE:
                    imported = {alias.name for alias in node.names}
                    forbidden = imported & _LLM_TOOL_CONTRACT_NAMES
                    if forbidden:
                        offenders.append(
                            f"{path}: from {module} import {sorted(forbidden)}"
                        )

    assert not offenders, "Eager LLM imports found:\n" + "\n".join(offenders)
