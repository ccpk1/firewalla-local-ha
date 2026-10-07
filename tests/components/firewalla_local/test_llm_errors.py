"""Error-path tests for the Firewalla Local LLM tools (Phase 4.5).

Every tool must fail cleanly: a malformed call should raise a validation error
that the MCP server surfaces as readable text, never a bare KeyError/TypeError.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
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
    SERVICE_FIELD_CONFIRM,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_HOST_MAC,
    SERVICE_FIELD_MODE,
    SERVICE_FIELD_NEW_NAME,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_ID,
    SERVICE_FIELD_TARGET_TYPE,
    SERVICE_FIELD_TARGET_VALUE,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
)

_HOST_MAC = "0C:85:E1:B0:1D:1C"


def _assert_clean_error(exc: BaseException) -> None:
    """Assert an exception is a readable validation error, never a bare crash."""
    assert not isinstance(exc, (KeyError, TypeError)), repr(exc)
    assert str(exc)


# Tools whose required parameters must be validated before use.
_TOOLS_REQUIRING_ARGS: tuple[tuple[str, dict[str, object]], ...] = (
    ("firewalla_local__pause_rule", {SERVICE_FIELD_RULE_ID: "761"}),
    ("firewalla_local__resume_rule", {SERVICE_FIELD_RULE_ID: "761"}),
    ("firewalla_local__set_ssid_paused", {SERVICE_FIELD_ENABLED: True}),
    ("firewalla_local__set_host_name", {SERVICE_FIELD_NEW_NAME: "x"}),
    ("firewalla_local__mute_alarm", {SERVICE_FIELD_TARGET_TYPE: "domain"}),
    ("firewalla_local__archive_alarm", {}),
    ("firewalla_local__delete_host", {}),
    ("firewalla_local__delete_rule", {}),
)


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


def _snapshot(*, host_count: int = 1) -> FirewallaRuntimeSnapshot:
    """Return a snapshot with the box host and one policy rule."""
    hosts = [
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
        )
    ]
    if host_count > 1:
        hosts.append(
            FirewallaHostRuntime(
                mac=_HOST_MAC,
                host_name="Kids-iPad",
                ip_address="192.168.200.42",
                group_name=None,
                network_name="Primary LAN",
                connection_type="tablet",
                last_active=None,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
            )
        )
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
        hosts=tuple(hosts),
        users=(),
    )


async def _api_instance(hass: HomeAssistant) -> llm.APIInstance:
    """Set up the entry and return the API instance.

    The runtime refresh is mocked for the lifetime of the entry so tools that
    trigger a poll (for example delete_host) never reach the network.
    """
    entry = _entry()
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.firewalla_local.coordinator."
            "FirewallaDataUpdateCoordinator.async_request_refresh",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "async_get_runtime_init_payload",
            new=AsyncMock(return_value={"policyRules": []}),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "build_runtime_snapshot",
            return_value=_snapshot(host_count=2),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return await llm.async_get_api(
            hass,
            _api_id(hass),
            llm.LLMContext(
                platform="test",
                context=Context(),
                language="en",
                assistant="conversation",
                device_id=None,
            ),
        )


@pytest.mark.parametrize(
    ("tool_name", "_supported_args"),
    [pytest.param(name, args, id=name) for name, args in _TOOLS_REQUIRING_ARGS],
)
async def test_missing_required_arg_raises_validation_error(
    hass: HomeAssistant, tool_name: str, _supported_args: dict[str, object]
) -> None:
    """A missing required argument is a validation error, not a KeyError."""
    api_instance = await _api_instance(hass)

    with pytest.raises(Exception) as err:
        await api_instance.async_call_tool(
            llm.ToolInput(tool_name=tool_name, tool_args={})
        )

    _assert_clean_error(err.value)


async def test_unknown_tool_raises_home_assistant_error(
    hass: HomeAssistant,
) -> None:
    """Calling an unregistered tool is a clean error."""
    api_instance = await _api_instance(hass)

    with pytest.raises(HomeAssistantError):
        await api_instance.async_call_tool(
            llm.ToolInput(tool_name="firewalla_local__nope", tool_args={})
        )


async def test_pause_rule_rejects_invalid_duration(hass: HomeAssistant) -> None:
    """An unparseable duration is rejected by the service layer."""
    api_instance = await _api_instance(hass)

    with pytest.raises(ServiceValidationError):
        await api_instance.async_call_tool(
            llm.ToolInput(
                tool_name="firewalla_local__pause_rule",
                tool_args={
                    SERVICE_FIELD_RULE_ID: "761",
                    SERVICE_FIELD_RULE_DURATION: "not-a-duration",
                },
            )
        )


async def test_set_host_dhcp_reservation_rejects_bad_mode(
    hass: HomeAssistant,
) -> None:
    """An out-of-enum mode is a validation error."""
    api_instance = await _api_instance(hass)

    with pytest.raises(Exception) as err:
        await api_instance.async_call_tool(
            llm.ToolInput(
                tool_name="firewalla_local__set_host_dhcp_reservation",
                tool_args={
                    SERVICE_FIELD_HOST_MAC: _HOST_MAC,
                    SERVICE_FIELD_MODE: "nonsense",
                },
            )
        )

    _assert_clean_error(err.value)


async def test_block_alarm_target_requires_a_selector(
    hass: HomeAssistant,
) -> None:
    """block_alarm_target needs an alarm id or an explicit target."""
    api_instance = await _api_instance(hass)

    with pytest.raises(ServiceValidationError):
        await api_instance.async_call_tool(
            llm.ToolInput(tool_name="firewalla_local__block_alarm_target", tool_args={})
        )


async def test_mute_alarm_requires_a_scope(hass: HomeAssistant) -> None:
    """A mute without an explicit scope is rejected (never a silent global mute)."""
    api_instance = await _api_instance(hass)

    with pytest.raises(Exception) as err:
        await api_instance.async_call_tool(
            llm.ToolInput(
                tool_name="firewalla_local__mute_alarm",
                tool_args={
                    SERVICE_FIELD_TARGET_TYPE: "domain",
                    SERVICE_FIELD_TARGET_VALUE: "vimeo.com",
                },
            )
        )

    _assert_clean_error(err.value)


async def test_delete_host_requires_confirmation(hass: HomeAssistant) -> None:
    """delete_host refuses to run without an explicit confirm, then succeeds."""
    with (
        patch(
            "custom_components.firewalla_local.coordinator."
            "FirewallaDataUpdateCoordinator.async_request_refresh",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager."
            "FirewallaIntegrationManager.async_delete_host",
            new=AsyncMock(return_value={}),
        ) as delete_host,
    ):
        api_instance = await _api_instance(hass)

        with pytest.raises(Exception):  # noqa: B017 - class varies by shim
            await api_instance.async_call_tool(
                llm.ToolInput(
                    tool_name="firewalla_local__delete_host",
                    tool_args={SERVICE_FIELD_HOST_MAC: _HOST_MAC},
                )
            )
        assert delete_host.await_count == 0

        await api_instance.async_call_tool(
            llm.ToolInput(
                tool_name="firewalla_local__delete_host",
                tool_args={
                    SERVICE_FIELD_HOST_MAC: _HOST_MAC,
                    SERVICE_FIELD_CONFIRM: True,
                },
            )
        )

    assert delete_host.await_count == 1


async def test_delete_rule_requires_confirmation(hass: HomeAssistant) -> None:
    """delete_rule refuses to run without an explicit confirm, then succeeds."""
    with patch(
        "custom_components.firewalla_local.managers.rule_manager."
        "FirewallaRuleManager.async_delete_rule",
        new=AsyncMock(return_value=True),
    ) as delete_rule:
        api_instance = await _api_instance(hass)

        with pytest.raises(Exception):  # noqa: B017 - class varies by shim
            await api_instance.async_call_tool(
                llm.ToolInput(
                    tool_name="firewalla_local__delete_rule",
                    tool_args={SERVICE_FIELD_RULE_ID: "761"},
                )
            )
        assert delete_rule.await_count == 0

        await api_instance.async_call_tool(
            llm.ToolInput(
                tool_name="firewalla_local__delete_rule",
                tool_args={SERVICE_FIELD_RULE_ID: "761", SERVICE_FIELD_CONFIRM: True},
            )
        )

    assert delete_rule.await_count == 1


async def test_read_tool_error_path_is_clean(hass: HomeAssistant) -> None:
    """A read tool called without a required service argument fails cleanly."""
    api_instance = await _api_instance(hass)

    with pytest.raises(Exception) as err:
        await api_instance.async_call_tool(
            llm.ToolInput(tool_name="firewalla_local__get_network_usage", tool_args={})
        )

    _assert_clean_error(err.value)


async def test_unknown_argument_is_rejected(hass: HomeAssistant) -> None:
    """An argument outside the declared schema is rejected."""
    api_instance = await _api_instance(hass)

    with pytest.raises(Exception) as err:
        await api_instance.async_call_tool(
            llm.ToolInput(
                tool_name="firewalla_local__pause_rule",
                tool_args={SERVICE_FIELD_RULE_ID: "761", "unexpected": 1},
            )
        )

    _assert_clean_error(err.value)


def _api_id(hass: HomeAssistant) -> str:
    """Return the id of the registered Firewalla LLM API.

    The id always carries a per-entry suffix, so it is never the bare domain;
    the suffix is derived from the entry title.
    """
    return next(
        api.id for api in llm.async_get_apis(hass) if api.id.startswith(f"{DOMAIN}-")
    )
