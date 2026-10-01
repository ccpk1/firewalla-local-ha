"""Effect tests for the Firewalla Local LLM control tools (Phase 4.3).

These exercise each control tool end to end through the LLM API: the tool calls
an admin-gated service, which calls a manager or client method. Manager/client
methods are mocked so the assertions cover tool -> service -> mutation wiring and
the action-result envelope without touching a real box.
"""

from __future__ import annotations

from types import SimpleNamespace
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
    SERVICE_FIELD_ALARM_ID,
    SERVICE_FIELD_DURATION,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_HOST_DEVICE_TYPE,
    SERVICE_FIELD_HOST_MAC,
    SERVICE_FIELD_NEW_NAME,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_FIELD_SCOPE_KIND,
    SERVICE_FIELD_SCOPE_TARGET,
    SERVICE_FIELD_SSID_PROFILE_ID,
    SERVICE_FIELD_TARGET_TYPE,
    SERVICE_FIELD_TARGET_VALUE,
)
from custom_components.firewalla_local.models import (
    FirewallaAlarm,
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
)

PAUSE_RULE = "firewalla_local__pause_rule"
RESUME_RULE = "firewalla_local__resume_rule"
SET_HOST_NAME = "firewalla_local__set_host_name"
SET_HOST_DEVICE_TYPE = "firewalla_local__set_host_device_type"
SET_SSID_PAUSED = "firewalla_local__set_ssid_paused"
WAKE_HOST = "firewalla_local__wake_host"
BLOCK_ALARM_TARGET = "firewalla_local__block_alarm_target"
SET_ALARM_MUTED = "firewalla_local__set_alarm_muted"
ARCHIVE_ALARM = "firewalla_local__archive_alarm"
ARCHIVE_ALL_ALARMS = "firewalla_local__archive_all_alarms"
DELETE_ALARM = "firewalla_local__delete_alarm"
DELETE_ALL_ALARMS = "firewalla_local__delete_all_alarms"
DELETE_HOST = "firewalla_local__delete_host"
DELETE_RULE = "firewalla_local__delete_rule"

_HOST_MAC = "0C:85:E1:B0:1D:1C"


def _entry(*, mode: str = "read_and_control") -> MockConfigEntry:
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


def _snapshot(*, rule_enabled: bool = True) -> FirewallaRuntimeSnapshot:
    """Return a snapshot with one rule and one alarm."""
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
                enabled=rule_enabled,
                purpose=None,
                scope=(_HOST_MAC,),
                target_name="player.vimeo.com",
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
            FirewallaHostRuntime(
                mac=_HOST_MAC,
                host_name="Kids-iPad",
                ip_address="192.168.200.42",
                group_name=None,
                network_name="Primary LAN",
                connection_type="tablet",
                last_active=1774287000.5,
                download_bytes=1,
                upload_bytes=2,
                stale=False,
            ),
        ),
        alarms=(
            FirewallaAlarm(
                alarm_id="1728",
                alarm_type="ALARM_VIDEO",
                device_name="Kids-iPad",
                message=None,
                state="active",
                is_archived=False,
                fired_at=None,
                remote_category=None,
                remote_host="vimeo.com",
                remote_ip="162.159.128.61",
                remote_app=None,
                remote_region=None,
                remote_latitude=None,
                remote_longitude=None,
                interface_name=None,
                protocol=None,
                severity=None,
                raw_payload={"p.device.mac": _HOST_MAC},
            ),
        ),
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


async def _setup(
    hass: HomeAssistant, *, rule_enabled: bool = True, mode: str = "read_and_control"
) -> llm.APIInstance:
    """Set up the entry with mocked runtime data and return the API instance."""
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
            return_value=_snapshot(rule_enabled=rule_enabled),
        ),
        patch(
            "custom_components.firewalla_local.llm_tools_supported",
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return await llm.async_get_api(hass, DOMAIN, _llm_context())


async def _call(
    api_instance: llm.APIInstance, tool_name: str, args: dict[str, object]
) -> llm.ToolResult:
    """Call one tool and return its result."""
    return await api_instance.async_call_tool(
        llm.ToolInput(tool_name=tool_name, tool_args=args)
    )


async def test_pause_rule_applies_and_reports_undo(hass: HomeAssistant) -> None:
    """pause_rule disables the rule and returns an undo pointing at resume_rule."""
    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient."
        "async_update_rule_control_only",
        new=AsyncMock(),
    ) as update_rule:
        api_instance = await _setup(hass)

        result = await _call(
            api_instance,
            PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_TARGET: "761",
                SERVICE_FIELD_RULE_DURATION: "30m",
            },
        )

    assert update_rule.await_count == 1
    assert result.error is False
    assert result.data["status"] == "applied"
    assert result.data["changed"] is True
    assert result.data["target"] == {"kind": "rule", "id": "761"}
    assert 'resume_rule(rule_target="761")' in result.data["undo"]


async def test_pause_rule_reports_already_in_state(hass: HomeAssistant) -> None:
    """pause_rule on an already-paused rule is a no-op with no service call."""
    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient."
        "async_update_rule_control_only",
        new=AsyncMock(),
    ) as update_rule:
        api_instance = await _setup(hass, rule_enabled=False)
        result = await _call(
            api_instance, PAUSE_RULE, {SERVICE_FIELD_RULE_TARGET: "761"}
        )

    assert update_rule.await_count == 0
    assert result.data["status"] == "already_in_state"
    assert result.data["changed"] is False


async def test_resume_rule_reports_already_in_state(hass: HomeAssistant) -> None:
    """resume_rule on an enabled rule is a no-op with no service call."""
    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient."
        "async_update_rule_control_only",
        new=AsyncMock(),
    ) as update_rule:
        api_instance = await _setup(hass)
        result = await _call(
            api_instance, RESUME_RULE, {SERVICE_FIELD_RULE_TARGET: "761"}
        )

    assert update_rule.await_count == 0
    assert result.data["status"] == "already_in_state"


async def test_set_host_name_calls_manager(hass: HomeAssistant) -> None:
    """set_host_name renames the host and echoes the resolved target."""
    with patch(
        "custom_components.firewalla_local.managers.integration_manager."
        "FirewallaIntegrationManager.async_set_host_name",
        new=AsyncMock(return_value={}),
    ) as set_name:
        api_instance = await _setup(hass)
        result = await _call(
            api_instance,
            SET_HOST_NAME,
            {
                SERVICE_FIELD_HOST_MAC: _HOST_MAC,
                SERVICE_FIELD_NEW_NAME: "Kids-iPad",
            },
        )

    assert set_name.await_args is not None
    assert set_name.await_args.args[1] == "Kids-iPad"
    assert result.data["status"] == "applied"
    assert result.data["target"]["id"] == _HOST_MAC


async def test_set_host_device_type_calls_manager(hass: HomeAssistant) -> None:
    """set_host_device_type forwards the classification to the manager."""
    with patch(
        "custom_components.firewalla_local.managers.integration_manager."
        "FirewallaIntegrationManager.async_set_host_device_type",
        new=AsyncMock(return_value={}),
    ) as set_type:
        api_instance = await _setup(hass)
        await _call(
            api_instance,
            SET_HOST_DEVICE_TYPE,
            {
                SERVICE_FIELD_HOST_MAC: _HOST_MAC,
                SERVICE_FIELD_HOST_DEVICE_TYPE: "tablet",
            },
        )

    assert set_type.await_args is not None
    assert set_type.await_args.args[1] == "tablet"


async def test_set_ssid_paused_calls_wireless_manager(hass: HomeAssistant) -> None:
    """set_ssid_paused toggles the SSID and offers the inverse as undo."""
    profile_uuid = "f185dc47-2730-48a8-844c-b57aa31af4ba"
    with (
        patch(
            "custom_components.firewalla_local.managers.wireless_manager."
            "FirewallaWirelessManager.resolve_ssid_profile",
            return_value=SimpleNamespace(profile_uuid=profile_uuid),
        ),
        patch(
            "custom_components.firewalla_local.managers.wireless_manager."
            "FirewallaWirelessManager.async_set_ssid_paused",
            new=AsyncMock(return_value={}),
        ) as set_paused,
    ):
        api_instance = await _setup(hass)
        result = await _call(
            api_instance,
            SET_SSID_PAUSED,
            {
                SERVICE_FIELD_SSID_PROFILE_ID: profile_uuid,
                SERVICE_FIELD_ENABLED: True,
            },
        )

    assert set_paused.await_count == 1
    assert "enabled=False" in result.data["undo"]


async def test_wake_host_calls_manager(hass: HomeAssistant) -> None:
    """wake_host sends a Wake-on-LAN through the manager."""
    with patch(
        "custom_components.firewalla_local.managers.integration_manager."
        "FirewallaIntegrationManager.async_wake_host",
        new=AsyncMock(return_value={}),
    ) as wake:
        api_instance = await _setup(hass)
        result = await _call(
            api_instance, WAKE_HOST, {SERVICE_FIELD_HOST_MAC: _HOST_MAC}
        )

    assert wake.await_args is not None
    assert wake.await_args.args[0] == _HOST_MAC
    assert result.data["status"] == "applied"
    assert result.data["changed"] is False


async def test_archive_alarm_uses_single_mode(hass: HomeAssistant) -> None:
    """archive_alarm archives exactly one alarm (mode=this)."""
    with patch(
        "custom_components.firewalla_local.managers.alarm_manager."
        "FirewallaAlarmManager.async_archive_alarms",
        new=AsyncMock(return_value={}),
    ) as archive:
        api_instance = await _setup(hass)
        result = await _call(
            api_instance, ARCHIVE_ALARM, {SERVICE_FIELD_ALARM_ID: "1728"}
        )

    assert archive.await_args is not None
    assert archive.await_args.kwargs == {"mode": "this", "alarm_id": "1728"}
    assert result.data["status"] == "applied"
    assert result.data["warnings"] == ["no un-archive"]


async def test_set_alarm_muted_calls_alarm_manager(hass: HomeAssistant) -> None:
    """set_alarm_muted creates a silence and offers an alarm-scoped undo."""
    with patch(
        "custom_components.firewalla_local.managers.alarm_manager."
        "FirewallaAlarmManager.async_mute_alarm",
        new=AsyncMock(return_value={}),
    ) as mute:
        api_instance = await _setup(hass)
        result = await _call(
            api_instance,
            SET_ALARM_MUTED,
            {
                SERVICE_FIELD_ALARM_ID: "1728",
                SERVICE_FIELD_TARGET_TYPE: "domain",
                SERVICE_FIELD_TARGET_VALUE: "vimeo.com",
                SERVICE_FIELD_SCOPE_KIND: "device",
                SERVICE_FIELD_SCOPE_TARGET: _HOST_MAC,
                SERVICE_FIELD_DURATION: "always",
            },
        )

    assert mute.await_count == 1
    assert 'unmute_alarm(alarm_id="1728")' in result.data["undo"]


async def test_block_alarm_target_creates_rule_with_undo(
    hass: HomeAssistant,
) -> None:
    """block_alarm_target creates a rule and reports the new id for unblocking."""
    with patch(
        "custom_components.firewalla_local.managers.rule_manager."
        "FirewallaRuleManager.async_create_rule",
        new=AsyncMock(return_value="652"),
    ) as create_rule:
        api_instance = await _setup(hass)
        result = await _call(
            api_instance, BLOCK_ALARM_TARGET, {SERVICE_FIELD_ALARM_ID: "1728"}
        )

    assert create_rule.await_count == 1
    template = create_rule.await_args.args[0]
    assert template.target == "vimeo.com"
    assert template.alarm_id == "1728"
    assert result.data["target"]["id"] == "652"
    assert 'unblock_alarm_target(rule_id="652")' in result.data["undo"]


@pytest.mark.parametrize("tool_name", [BLOCK_ALARM_TARGET])
async def test_block_requires_alarm_or_target(
    hass: HomeAssistant, tool_name: str
) -> None:
    """block_alarm_target validates that a selector is supplied."""
    api_instance = await _setup(hass)

    with pytest.raises(Exception):  # noqa: B017 - service validation error
        await _call(api_instance, tool_name, {})


async def test_archive_all_alarms_is_bulk(hass: HomeAssistant) -> None:
    """archive_all_alarms uses the bulk all_active mode with warnings."""
    with patch(
        "custom_components.firewalla_local.managers.alarm_manager."
        "FirewallaAlarmManager.async_archive_alarms",
        new=AsyncMock(return_value={}),
    ) as archive:
        api_instance = await _setup(hass, mode="full")
        result = await _call(api_instance, ARCHIVE_ALL_ALARMS, {})

    assert archive.await_args is not None
    assert archive.await_args.kwargs == {"mode": "all_active", "alarm_id": None}
    assert "bulk action" in result.data["warnings"]


async def test_delete_alarm_uses_single_mode(hass: HomeAssistant) -> None:
    """delete_alarm deletes exactly one alarm and forces confirmation."""
    with patch(
        "custom_components.firewalla_local.managers.alarm_manager."
        "FirewallaAlarmManager.async_delete_alarms",
        new=AsyncMock(return_value={}),
    ) as delete:
        api_instance = await _setup(hass, mode="full")
        result = await _call(
            api_instance, DELETE_ALARM, {SERVICE_FIELD_ALARM_ID: "1728"}
        )

    assert delete.await_args is not None
    assert delete.await_args.kwargs["mode"] == "this"
    assert delete.await_args.kwargs["alarm_id"] == "1728"
    assert result.data["status"] == "applied"


@pytest.mark.parametrize(
    "mode",
    [
        pytest.param("all_active", id="all_active"),
        pytest.param("all_archived", id="all_archived"),
    ],
)
async def test_delete_all_alarms_uses_bulk_mode(hass: HomeAssistant, mode: str) -> None:
    """delete_all_alarms deletes the requested set with a bulk warning."""
    with patch(
        "custom_components.firewalla_local.managers.alarm_manager."
        "FirewallaAlarmManager.async_delete_alarms",
        new=AsyncMock(return_value={}),
    ) as delete:
        api_instance = await _setup(hass, mode="full")
        result = await _call(api_instance, DELETE_ALL_ALARMS, {"mode": mode})

    assert delete.await_args is not None
    assert delete.await_args.kwargs["mode"] == mode
    assert "irreversible" in result.data["warnings"]


async def test_delete_rule_deletes_rule(hass: HomeAssistant) -> None:
    """delete_rule permanently removes the resolved rule."""
    with patch(
        "custom_components.firewalla_local.managers.rule_manager."
        "FirewallaRuleManager.async_delete_rule",
        new=AsyncMock(return_value=True),
    ) as delete_rule:
        api_instance = await _setup(hass, mode="full")
        result = await _call(api_instance, DELETE_RULE, {"rule_id": "761"})

    assert delete_rule.await_args is not None
    assert delete_rule.await_args.args[0] == "761"
    assert result.data["warnings"] == ["irreversible"]


async def test_delete_host_deletes_host(hass: HomeAssistant) -> None:
    """delete_host permanently removes the host record."""
    with patch(
        "custom_components.firewalla_local.managers.integration_manager."
        "FirewallaIntegrationManager.async_delete_host",
        new=AsyncMock(return_value={}),
    ) as delete_host:
        api_instance = await _setup(hass, mode="full")
        result = await _call(api_instance, DELETE_HOST, {"host_mac": _HOST_MAC})

    assert delete_host.await_count == 1
    assert result.data["status"] == "applied"
    assert result.data["warnings"] == ["irreversible"]
