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
    SERVICE_FIELD_ALARM_TARGET_TYPE,
    SERVICE_FIELD_ALARM_TARGET_VALUE,
    SERVICE_FIELD_CONFIRM,
    SERVICE_FIELD_DURATION,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_GROUP_NAME,
    SERVICE_FIELD_HOST_DEVICE_TYPE,
    SERVICE_FIELD_HOST_MAC,
    SERVICE_FIELD_NEW_NAME,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_ID,
    SERVICE_FIELD_SSID_PROFILE_ID,
    SERVICE_FIELD_USER_NAME,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
)
from custom_components.firewalla_local.models import (
    FirewallaAlarm,
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaGroupRuntime,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
    FirewallaUserRuntime,
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
SET_HOST_GROUP = "firewalla_local__set_host_group"
CLEAR_HOST_GROUP = "firewalla_local__clear_host_group"
SET_HOST_USER = "firewalla_local__set_host_user"
CLEAR_HOST_USER = "firewalla_local__clear_host_user"
RUN_INTERNET_SPEED_TEST = "firewalla_local__run_internet_speed_test"

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
        groups=(
            FirewallaGroupRuntime(group_id="53", name="IOT_LIGHTS", kind="group"),
            FirewallaGroupRuntime(
                group_id="73",
                name="KADENS_PHONE",
                kind="user",
                user_id="74",
            ),
        ),
        users=(
            FirewallaUserRuntime(
                user_id="74",
                name="KADENS_PHONE",
                affiliated_group_id="73",
                affiliated_group_name="KADENS_PHONE",
                total_minutes_today=None,
                unique_minutes_today=None,
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
        return await llm.async_get_api(hass, _api_id(hass), _llm_context())


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
                SERVICE_FIELD_RULE_ID: "761",
                SERVICE_FIELD_RULE_DURATION: "30m",
            },
        )

    assert update_rule.await_count == 1
    assert result.error is False
    assert result.data["status"] == "applied"
    assert result.data["changed"] is True
    assert result.data["target"] == {"kind": "rule", "id": "761"}
    assert result.data["before"] == {"enabled": True, "is_paused": False}
    assert result.data["after"] == {"enabled": False, "is_paused": True}
    assert 'resume_rule(rule_id="761")' in result.data["undo"]


async def test_run_internet_speed_test_reports_a_network_target(
    hass: HomeAssistant,
) -> None:
    """A speed test names the WAN as a network target, not as a bare `wan`.

    The report services publish every network target as `kind: "network"` plus a
    `network_kind`, so a tool result must not reintroduce the second vocabulary a
    `kind: "wan"` here would create.
    """
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        new=AsyncMock(return_value={"ok": True}),
    ):
        api_instance = await _setup(hass)
        result = await _call(
            api_instance,
            RUN_INTERNET_SPEED_TEST,
            {SERVICE_FIELD_WAN_UUID: "wan-1", SERVICE_FIELD_WAN_NAME: "WAN-ONE"},
        )

    assert result.error is False
    assert result.data["target"] == {
        "kind": "network",
        "network_kind": "wan",
        "id": "wan-1",
        "name": "WAN-ONE",
    }


async def test_pause_rule_reports_already_in_state(hass: HomeAssistant) -> None:
    """pause_rule on an already-paused rule reports a no-op *and still writes*.

    A disabled rule *is* paused -- Firewalla has one pair of states, enabled or
    disabled, and a resume boundary is what makes a pause timed rather than
    indefinite. So a disabled rule with no boundary reports `is_paused: true`.

    The write happens anyway, and that is the point. The snapshot the precheck reads
    can be a poll interval old, so skipping the write on its say-so meant a rule
    resumed on the box in that window was reported as already-paused and left
    running. The call is idempotent, so making it costs one request and is the only
    way the answer is true; the precheck now shapes the report and nothing else.
    """
    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient."
        "async_update_rule_control_only",
        new=AsyncMock(),
    ) as update_rule:
        api_instance = await _setup(hass, rule_enabled=False)
        result = await _call(api_instance, PAUSE_RULE, {SERVICE_FIELD_RULE_ID: "761"})

    assert update_rule.await_count == 1
    assert result.data["status"] == "already_in_state"
    assert result.data["changed"] is False
    assert result.data["before"] == {"enabled": False, "is_paused": True}
    assert result.data["after"] == result.data["before"]


async def test_resume_rule_reports_already_in_state(hass: HomeAssistant) -> None:
    """resume_rule on an enabled rule reports a no-op and still writes."""
    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient."
        "async_update_rule_control_only",
        new=AsyncMock(),
    ) as update_rule:
        api_instance = await _setup(hass)
        result = await _call(api_instance, RESUME_RULE, {SERVICE_FIELD_RULE_ID: "761"})

    assert update_rule.await_count == 1
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
    """archive_alarm archives exactly one alarm, by id."""
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
    assert archive.await_args.kwargs == {"alarm_id": "1728"}
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
                SERVICE_FIELD_ALARM_TARGET_TYPE: "domain",
                SERVICE_FIELD_ALARM_TARGET_VALUE: "vimeo.com",
                SERVICE_FIELD_HOST_MAC: _HOST_MAC,
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
    """archive_all_alarms names the active set explicitly."""
    with patch(
        "custom_components.firewalla_local.managers.alarm_manager."
        "FirewallaAlarmManager.async_archive_alarms",
        new=AsyncMock(return_value={}),
    ) as archive:
        api_instance = await _setup(hass, mode="full")
        result = await _call(api_instance, ARCHIVE_ALL_ALARMS, {})

    assert archive.await_args is not None
    assert archive.await_args.kwargs == {"alarm_id": None}
    assert "bulk action" in result.data["warnings"]


async def test_delete_alarm_uses_single_mode(hass: HomeAssistant) -> None:
    """delete_alarm deletes exactly one alarm when confirmed."""
    with patch(
        "custom_components.firewalla_local.managers.alarm_manager."
        "FirewallaAlarmManager.async_delete_alarms",
        new=AsyncMock(return_value={}),
    ) as delete:
        api_instance = await _setup(hass, mode="full")
        result = await _call(
            api_instance,
            DELETE_ALARM,
            {SERVICE_FIELD_ALARM_ID: "1728", SERVICE_FIELD_CONFIRM: True},
        )

    assert delete.await_args is not None
    assert delete.await_args.kwargs["alarm_id"] == "1728"
    assert result.data["status"] == "applied"
    assert result.data["target"] == {"kind": "alarm", "id": "1728"}


@pytest.mark.parametrize(
    "alarm_status",
    [
        pytest.param("active", id="active"),
        pytest.param("archived", id="archived"),
    ],
)
async def test_delete_all_alarms_uses_bulk_mode(
    hass: HomeAssistant, alarm_status: str
) -> None:
    """delete_all_alarms deletes the requested set with a bulk warning."""
    with patch(
        "custom_components.firewalla_local.managers.alarm_manager."
        "FirewallaAlarmManager.async_delete_alarms",
        new=AsyncMock(return_value={}),
    ) as delete:
        api_instance = await _setup(hass, mode="full")
        result = await _call(
            api_instance,
            DELETE_ALL_ALARMS,
            {"alarm_status": alarm_status, SERVICE_FIELD_CONFIRM: True},
        )

    assert delete.await_args is not None
    assert delete.await_args.kwargs["alarm_status"] == alarm_status
    assert "irreversible" in result.data["warnings"]


async def test_delete_rule_deletes_rule(hass: HomeAssistant) -> None:
    """delete_rule permanently removes the resolved rule."""
    with patch(
        "custom_components.firewalla_local.managers.rule_manager."
        "FirewallaRuleManager.async_delete_rule",
        new=AsyncMock(return_value=True),
    ) as delete_rule:
        api_instance = await _setup(hass, mode="full")
        result = await _call(
            api_instance, DELETE_RULE, {"rule_id": "761", SERVICE_FIELD_CONFIRM: True}
        )

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
        result = await _call(
            api_instance,
            DELETE_HOST,
            {SERVICE_FIELD_HOST_MAC: _HOST_MAC, SERVICE_FIELD_CONFIRM: True},
        )

    assert delete_host.await_count == 1
    assert result.data["status"] == "applied"
    assert result.data["warnings"] == ["irreversible"]


async def test_set_host_group_deletes_the_host_rules_and_reports_them(
    hass: HomeAssistant,
) -> None:
    """set_host_group assigns the group, deletes the host's rules, names the undo.

    A membership change deletes the rules attached to the host -- confirmed by
    two captures -- so the tool must surface that in `warnings` rather than report
    a clean success, and its `undo` must point at the clear tool without implying
    the deleted rules come back.
    """
    with (
        patch(
            "custom_components.firewalla_local.managers.integration_manager."
            "FirewallaIntegrationManager.async_set_host_policy",
            new=AsyncMock(return_value={}),
        ) as set_policy,
        patch(
            "custom_components.firewalla_local.managers.rule_manager."
            "FirewallaRuleManager.async_delete_rule",
            new=AsyncMock(return_value=True),
        ) as delete_rule,
    ):
        api_instance = await _setup(hass, mode="full")
        result = await _call(
            api_instance,
            SET_HOST_GROUP,
            {
                SERVICE_FIELD_HOST_MAC: _HOST_MAC,
                SERVICE_FIELD_GROUP_NAME: "IOT_LIGHTS",
            },
        )

    # The device's own rule (761, scoped to its MAC) is deleted before the write.
    assert delete_rule.await_args is not None
    assert delete_rule.await_args.args[0] == "761"
    assert set_policy.await_args is not None
    assert set_policy.await_args.args[1] == {"tags": [53]}

    assert result.error is False
    assert result.data["status"] == "applied"
    assert result.data["changed"] is True
    assert result.data["before"] is None
    assert result.data["after"] == {"kind": "group", "id": "53", "name": "IOT_LIGHTS"}
    assert "clear_host_group" in result.data["undo"]
    assert len(result.data["warnings"]) == 1
    assert "Deleted 1 rule" in result.data["warnings"][0]
    assert "761" in result.data["warnings"][0]


@pytest.mark.parametrize(
    ("tool_name", "args", "expected_tags"),
    [
        pytest.param(
            CLEAR_HOST_GROUP,
            {},
            [],
            id="clear_group",
        ),
        pytest.param(
            CLEAR_HOST_USER,
            {},
            [],
            id="clear_user",
        ),
        pytest.param(
            SET_HOST_USER,
            {SERVICE_FIELD_USER_NAME: "KADENS_PHONE"},
            # A user assignment writes the user's affiliated backing tag, not the
            # user id: the device carries the tag in group_ids.
            [73],
            id="set_user_by_name",
        ),
    ],
)
async def test_membership_tools_write_through_the_one_service(
    hass: HomeAssistant,
    tool_name: str,
    args: dict[str, object],
    expected_tags: list[int],
) -> None:
    """All four tools delegate to set_host_membership with the right payload."""
    with (
        patch(
            "custom_components.firewalla_local.managers.integration_manager."
            "FirewallaIntegrationManager.async_set_host_policy",
            new=AsyncMock(return_value={}),
        ) as set_policy,
        # Rule 761 is scoped to this host, so the membership change deletes it.
        patch(
            "custom_components.firewalla_local.managers.rule_manager."
            "FirewallaRuleManager.async_delete_rule",
            new=AsyncMock(return_value=True),
        ),
    ):
        api_instance = await _setup(hass, mode="full")
        result = await _call(
            api_instance,
            tool_name,
            {SERVICE_FIELD_HOST_MAC: _HOST_MAC, **args},
        )

    assert set_policy.await_args is not None
    assert set_policy.await_args.args[1] == {"tags": expected_tags}
    assert result.error is False
    assert result.data["status"] == "applied"


async def test_membership_tools_are_full_tier_only(hass: HomeAssistant) -> None:
    """Membership tools are destructive, so they need the explicit full opt-in.

    A membership change deletes the device's rules irreversibly, which is the
    definition the destructive tier exists for. At read-and-control the tools are
    absent rather than filtered, so the restriction holds by construction.
    """
    control_api = await _setup(hass, mode="read_and_control")
    control_names = {tool.name for tool in control_api.tools}

    for tool_name in (
        SET_HOST_GROUP,
        CLEAR_HOST_GROUP,
        SET_HOST_USER,
        CLEAR_HOST_USER,
    ):
        assert tool_name not in control_names


async def test_membership_tools_are_destructive_and_present_in_full(
    hass: HomeAssistant,
) -> None:
    """At full mode the four tools are registered and annotated destructive.

    Kept separate from the read-and-control check because each `_setup` call
    registers its own API, and looking one up by id would otherwise resolve to
    whichever entry was set up first.
    """
    full_api = await _setup(hass, mode="full")
    full_tools = {tool.name: tool for tool in full_api.tools}

    for tool_name in (
        SET_HOST_GROUP,
        CLEAR_HOST_GROUP,
        SET_HOST_USER,
        CLEAR_HOST_USER,
    ):
        assert tool_name in full_tools
        assert full_tools[tool_name].annotations.destructive is True


@pytest.mark.parametrize(
    ("tool_name", "forbidden"),
    [
        pytest.param(SET_HOST_GROUP, SERVICE_FIELD_USER_NAME, id="group_tool"),
        pytest.param(SET_HOST_USER, SERVICE_FIELD_GROUP_NAME, id="user_tool"),
    ],
)
async def test_membership_tools_expose_only_their_own_kind(
    hass: HomeAssistant,
    tool_name: str,
    forbidden: str,
) -> None:
    """Each tool declares only its own kind's selector.

    A group and a user can share a name on a real box, so a tool accepting both
    could silently target the wrong kind. The split is the whole reason there are
    four tools instead of one with a free-text target.
    """
    api_instance = await _setup(hass, mode="full")
    tool = next(tool for tool in api_instance.tools if tool.name == tool_name)

    declared = {marker.schema for marker in tool.parameters.schema}
    assert forbidden not in declared


def _api_id(hass: HomeAssistant) -> str:
    """Return the id of the registered Firewalla LLM API.

    The id always carries a per-entry suffix, so it is never the bare domain;
    the suffix is derived from the entry title.
    """
    return next(
        api.id for api in llm.async_get_apis(hass) if api.id.startswith(f"{DOMAIN}-")
    )
