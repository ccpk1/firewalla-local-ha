"""Tests for the Firewalla Local LLM read tools (Phase 4.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
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
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
)

LIST_HOSTS_TOOL = "firewalla_local__list_hosts"
LIST_RULES_TOOL = "firewalla_local__list_rules"


def _entry() -> MockConfigEntry:
    """Return a provisioned Firewalla config entry with LLM tools enabled."""
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
        options={CONF_LLM_TOOL_MODE: "read_only"},
    )


def _mock_snapshot() -> FirewallaRuntimeSnapshot:
    """Return a snapshot with one rule and one host."""
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
                rule_id="652",
                action="block",
                target="vimeo.com",
                target_type="dns",
                direction="bidirection",
                enabled=True,
                purpose=None,
                scope=("0C:85:E1:B0:1D:1C",),
                target_name="player.vimeo.com",
                raw_update_payload={"pid": "652", "aid": "1728"},
            ),
        ),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:01",
                host_name="Kids-iPad",
                ip_address="192.168.200.42",
                group_name=None,
                network_name="LAN",
                connection_type="tablet",
                last_active=1774287000.5,
                download_bytes=1,
                upload_bytes=2,
                stale=False,
            ),
        ),
        users=(),
    )


def _llm_context() -> llm.LLMContext:
    """Return a minimal LLM context for a tool call."""
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


async def _setup_hass(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a provisioned entry with LLM tools enabled."""
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
    assert entry.state is ConfigEntryState.LOADED
    return entry


@pytest.mark.parametrize(
    ("tool_name", "response_type"),
    [
        pytest.param(LIST_HOSTS_TOOL, "hosts", id="list_hosts"),
        pytest.param(LIST_RULES_TOOL, "rules", id="list_rules"),
    ],
)
async def test_read_tool_returns_envelope(
    hass: HomeAssistant, tool_name: str, response_type: str
) -> None:
    """Every read tool returns the documented response envelope."""
    await _setup_hass(hass)
    api_instance = await llm.async_get_api(hass, DOMAIN, _llm_context())

    registered = {tool.name for tool in api_instance.tools}
    assert tool_name in registered

    result = await api_instance.async_call_tool(
        llm.ToolInput(tool_name=tool_name, tool_args={})
    )

    assert result.error is False
    assert result.data["meta"]["response_type"] == response_type
    assert isinstance(result.data["result"], dict)


async def test_list_rules_returns_flat_rule_shape(hass: HomeAssistant) -> None:
    """list_rules surfaces the flat rule shape including the alarm reference."""
    await _setup_hass(hass)
    api_instance = await llm.async_get_api(hass, DOMAIN, _llm_context())

    result = await api_instance.async_call_tool(
        llm.ToolInput(tool_name=LIST_RULES_TOOL, tool_args={})
    )

    rules = result.data["result"]["rules"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["rule_id"] == "652"
    assert rule["action"] == "block"
    assert rule["enabled"] is True
    assert rule["is_paused"] is False
    assert rule["target"] == "vimeo.com"
    assert rule["target_type"] == "dns"
    assert rule["scope"] == ["0C:85:E1:B0:1D:1C"]
    assert rule["alarm_id"] == "1728"


async def test_list_hosts_returns_host_records(hass: HomeAssistant) -> None:
    """list_hosts surfaces the host identity records from the host service."""
    await _setup_hass(hass)
    api_instance = await llm.async_get_api(hass, DOMAIN, _llm_context())

    result = await api_instance.async_call_tool(
        llm.ToolInput(tool_name=LIST_HOSTS_TOOL, tool_args={})
    )

    hosts = result.data["result"]["hosts"]
    assert len(hosts) == 1
    assert hosts[0]["host_id"] == "AA:BB:CC:DD:EE:01"
    assert hosts[0]["host_name"] == "Kids-iPad"


@pytest.mark.parametrize(
    "tool_name",
    [
        pytest.param(LIST_HOSTS_TOOL, id="list_hosts"),
        pytest.param(LIST_RULES_TOOL, id="list_rules"),
    ],
)
async def test_read_tools_are_annotated_read_only(
    hass: HomeAssistant, tool_name: str
) -> None:
    """Read tools declare the safe, explicit annotation set."""
    await _setup_hass(hass)
    api_instance = await llm.async_get_api(hass, DOMAIN, _llm_context())

    tool = next(tool for tool in api_instance.tools if tool.name == tool_name)
    assert tool.integration == DOMAIN
    assert tool.title
    assert tool.description
    assert tool.annotations.read_only is True
    assert tool.annotations.destructive is False
    assert tool.annotations.open_world is False


async def test_read_tools_absent_when_mode_is_off(hass: HomeAssistant) -> None:
    """With LLM tools off, no API is registered at all."""
    entry = MockConfigEntry(
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
        options={CONF_LLM_TOOL_MODE: "off"},
    )
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
