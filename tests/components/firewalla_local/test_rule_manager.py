"""Tests for Firewalla Local rule manager behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

from custom_components.firewalla_local.api.client import FirewallaApiClient
from custom_components.firewalla_local.coordinator import (
    FirewallaConfigEntry,
    FirewallaDataUpdateCoordinator,
)
from custom_components.firewalla_local.managers.rule_manager import FirewallaRuleManager
from custom_components.firewalla_local.models import (
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    FirewallaRuntimeSnapshot,
    FirewallaSystemInfo,
)


class _StubCoordinator:
    """Minimal coordinator stub for manager tests."""

    def __init__(self, snapshot: FirewallaRuntimeSnapshot) -> None:
        """Initialize the stub coordinator."""
        self.data = snapshot
        self.updated_snapshots: list[FirewallaRuntimeSnapshot] = []

    def async_set_updated_data(self, snapshot: FirewallaRuntimeSnapshot) -> None:
        """Mirror DataUpdateCoordinator state updates for assertions."""
        self.data = snapshot
        self.updated_snapshots.append(snapshot)


def _build_rule(
    rule_id: str,
    *,
    action: str = "block",
    target: str = "social",
    target_type: str = "category",
    enabled: bool = True,
    target_name: str | None = "social",
    applies_to: tuple[str, ...] = ("AV_SMART_TV",),
    auto_delete_when_expires: bool | None = None,
    expire_seconds: int | None = None,
    raw_update_payload: dict[str, object] | None = None,
) -> FirewallaPolicyRule:
    """Build one normalized rule for manager tests."""
    return FirewallaPolicyRule(
        rule_id=rule_id,
        action=action,
        target=target,
        target_type=target_type,
        direction="bidirection",
        enabled=enabled,
        purpose=None,
        scope=(),
        tag_refs=("tag:17",),
        target_name=target_name,
        applies_to=applies_to,
        expire_seconds=expire_seconds,
        auto_delete_when_expires=auto_delete_when_expires,
        dnsmasq_only=True,
        raw_update_payload=raw_update_payload
        or {
            "pid": rule_id,
            "action": action,
            "target": target,
            "type": target_type,
            "tag": ["tag:17"],
            "dnsmasq_only": True,
            "disabled": 0 if enabled else 1,
        },
    )


def _build_snapshot(*rules: FirewallaPolicyRule) -> FirewallaRuntimeSnapshot:
    """Build one runtime snapshot for manager tests."""
    return FirewallaRuntimeSnapshot(
        system_info=FirewallaSystemInfo(
            host="192.168.200.1",
            name="Firewalla",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        policy_rules=rules,
        exception_rule_count=0,
    )


def _build_manager(
    snapshot: FirewallaRuntimeSnapshot,
    *,
    options: dict[str, object] | None = None,
) -> tuple[FirewallaRuleManager, _StubCoordinator, AsyncMock, AsyncMock]:
    """Build a rule manager with typed stubs for isolated tests."""
    coordinator = _StubCoordinator(snapshot)
    update_rule = AsyncMock()
    update_rule_control_only = AsyncMock()
    client = cast(
        FirewallaApiClient,
        SimpleNamespace(
            async_update_rule=update_rule,
            async_update_rule_control_only=update_rule_control_only,
        ),
    )
    entry = cast(
        FirewallaConfigEntry,
        SimpleNamespace(
            options=options or {},
            data={},
            entry_id="entry-123",
        ),
    )
    manager = FirewallaRuleManager(
        cast(FirewallaDataUpdateCoordinator, coordinator),
        entry,
        client,
    )
    return manager, coordinator, update_rule, update_rule_control_only


def test_get_switch_candidate_rule_ids_filters_system_managed_rules() -> None:
    """Test candidate filtering excludes only system-managed rules."""
    candidate_rule = _build_rule("744")
    system_managed_rule = _build_rule("745", target="games", target_name="games")
    unnamed_network_rule = _build_rule(
        "746",
        target="5799d896-5e0f-40a5-a776-38a5d7746204",
        target_type="network",
        target_name=None,
    )
    target_list_rule = _build_rule(
        "747",
        action="allow",
        target="TL-56d856bb-efdc-4894-8e5f-c483555e09f6",
        target_name=None,
        applies_to=("caddy-int",),
    )
    ip_rule = _build_rule(
        "748",
        action="allow",
        target="192.168.200.124",
        target_type="ip",
        target_name=None,
        applies_to=("VLAN60 IOT",),
    )
    remote_port_rule = _build_rule(
        "749",
        action="allow",
        target="20002",
        target_type="remotePort",
        target_name=None,
        applies_to=("xtool-d1",),
    )
    internet_quota_rule = _build_rule(
        "750",
        target="TAG",
        target_type="mac",
        target_name="KADEN's Devices (KADEN)",
        applies_to=("KADEN's Devices (KADEN)",),
        auto_delete_when_expires=True,
        raw_update_payload={
            "pid": "750",
            "action": "block",
            "target": "TAG",
            "type": "mac",
            "tag": ["tag:10"],
            "disabled": 0,
            "autoDeleteWhenExpires": "1",
            "cronTime": "0 0 * * *",
            "duration": "86390",
            "appTimeUsage": {
                "app": "internet",
                "quota": 225,
                "apps": ["internet"],
                "period": "0 0 * * *",
                "uniqueMinute": True,
            },
            "appTimeUsed": 62,
        },
    )
    temporary_rule = _build_rule(
        "751",
        target="TAG",
        target_type="mac",
        target_name="KADEN's Devices (KADEN)",
        applies_to=("KADEN's Devices (KADEN)",),
        auto_delete_when_expires=True,
        expire_seconds=3600,
        raw_update_payload={
            "pid": "751",
            "action": "block",
            "target": "TAG",
            "type": "mac",
            "tag": ["tag:10"],
            "disabled": 0,
            "autoDeleteWhenExpires": "1",
            "expire": 3600,
        },
    )
    snapshot = _build_snapshot(
        candidate_rule,
        system_managed_rule,
        unnamed_network_rule,
        target_list_rule,
        ip_rule,
        remote_port_rule,
        internet_quota_rule,
        temporary_rule,
    )
    manager, _, _, _ = _build_manager(snapshot)

    manager.handle_refresh(
        {
            "policyRules": [
                candidate_rule.raw_update_payload,
                {**system_managed_rule.raw_update_payload, "method": "auto"},
                unnamed_network_rule.raw_update_payload,
                target_list_rule.raw_update_payload,
                ip_rule.raw_update_payload,
                remote_port_rule.raw_update_payload,
                internet_quota_rule.raw_update_payload,
                temporary_rule.raw_update_payload,
            ]
        },
        snapshot,
    )

    assert manager.get_switch_candidate_rule_ids() == {
        "744",
        "746",
        "747",
        "748",
        "749",
        "750",
    }
    assert manager.get_switch_candidate_choices() == {
        "744": "[744] block category social for AV_SMART_TV (enabled)",
        "746": (
            "[746] block network 5799d896-5e0f-40a5-a776-38a5d7746204 "
            "for AV_SMART_TV (enabled)"
        ),
        "747": (
            "[747] allow category TL-56d856bb-efdc-4894-8e5f-c483555e09f6 "
            "for caddy-int (enabled)"
        ),
        "748": "[748] allow ip 192.168.200.124 for VLAN60 IOT (enabled)",
        "749": "[749] allow remotePort 20002 for xtool-d1 (enabled)",
        "750": ("[750] block internet for KADEN's Devices (KADEN) (enabled)"),
    }


def test_get_switch_candidate_choices_prefers_custom_rule_name() -> None:
    """Test candidate choices use the user-defined rule name when available."""
    custom_named_rule = _build_rule(
        "772",
        action="allow",
        target="choreops.com",
        target_type="dns",
        target_name=None,
        applies_to=("AV_SMART_TV",),
        raw_update_payload={
            "pid": "772",
            "action": "allow",
            "target": "choreops.com",
            "type": "dns",
            "direction": "bidirection",
            "tag": ["tag:17"],
            "disabled": 0,
            "dnsmasq_only": False,
            "trust": True,
            "_name": "ChoreOps Custom Allow",
        },
    )
    snapshot = _build_snapshot(custom_named_rule)
    manager, _, _, _ = _build_manager(snapshot)

    manager.handle_refresh(
        {"policyRules": [custom_named_rule.raw_update_payload]},
        snapshot,
    )

    assert manager.get_switch_candidate_choices() == {
        "772": "[772] ChoreOps Custom Allow (enabled)"
    }


def test_load_selected_templates_refreshes_live_custom_name() -> None:
    """Test persisted templates adopt the live custom name when available."""
    live_rule = _build_rule(
        "772",
        action="allow",
        target="choreops.com",
        target_type="dns",
        target_name=None,
        applies_to=("AV_SMART_TV",),
        raw_update_payload={
            "pid": "772",
            "action": "allow",
            "target": "choreops.com",
            "type": "dns",
            "direction": "bidirection",
            "tag": ["tag:17"],
            "disabled": 0,
            "dnsmasq_only": False,
            "trust": True,
            "_name": "ChoreOps Custom Allow",
        },
    )
    snapshot = _build_snapshot(live_rule)

    templates = FirewallaRuleManager.load_selected_templates(
        {
            "selected_rule_templates": [
                {
                    "source_rule_id": "772",
                    "name": "allow dns choreops.com for AV_SMART_TV",
                    "action": "allow",
                    "target": "choreops.com",
                    "target_type": "dns",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": False,
                    "use_bf": True,
                }
            ]
        },
        snapshot,
    )

    assert templates[0].name == "ChoreOps Custom Allow"


async def test_async_set_template_enabled_updates_snapshot_optimistically() -> None:
    """Test enabling a selected template updates the in-memory snapshot immediately."""
    snapshot = _build_snapshot(
        _build_rule(
            "744",
            enabled=False,
            raw_update_payload={
                "pid": "744",
                "action": "block",
                "target": "social",
                "type": "category",
                "tag": ["tag:17"],
                "dnsmasq_only": True,
                "disabled": 1,
                "idleTs": "1774324800",
            },
        )
    )
    manager, coordinator, update_rule, _ = _build_manager(
        snapshot,
        options={
            "selected_rule_templates": [
                FirewallaRuleTemplate.from_rule(snapshot.policy_rules[0]).to_dict()
            ]
        },
    )
    manager.handle_refresh(
        {"policyRules": [snapshot.policy_rules[0].raw_update_payload]},
        snapshot,
    )
    template = manager.selected_templates[0]

    with patch(
        "custom_components.firewalla_local.managers.rule_manager.time.time",
        return_value=1_700_000_000.0,
    ):
        await manager.async_set_template_enabled(template, enabled=True)

    assert update_rule.await_args is not None
    assert update_rule.await_count == 1
    assert update_rule.await_args.args[0].rule_id == "744"
    assert update_rule.await_args.kwargs == {"enabled": True}
    assert coordinator.data.policy_rules[0].enabled is True
    assert coordinator.data.policy_rules[0].raw_update_payload["disabled"] == 0
    assert coordinator.data.policy_rules[0].raw_update_payload["idleTs"] == ""


async def test_async_pause_and_resume_rule_update_snapshot_optimistically() -> None:
    """Test pause and resume apply manager-owned state updates without a refresh."""
    snapshot = _build_snapshot(_build_rule("744"))
    manager, coordinator, _, update_rule_control_only = _build_manager(snapshot)
    manager.handle_refresh(
        {"policyRules": [snapshot.policy_rules[0].raw_update_payload]},
        snapshot,
    )

    with patch(
        "custom_components.firewalla_local.managers.rule_manager.time.time",
        side_effect=[1_700_000_000.0, 1_700_000_100.0],
    ):
        await manager.async_pause_rule("744", 1_700_001_800)
        await manager.async_resume_rule("744")

    assert update_rule_control_only.await_count == 2
    assert update_rule_control_only.await_args_list[0].args == ("744",)
    assert update_rule_control_only.await_args_list[0].kwargs == {
        "enabled": False,
        "idle_ts": 1_700_001_800,
    }
    assert update_rule_control_only.await_args_list[1].args == ("744",)
    assert update_rule_control_only.await_args_list[1].kwargs == {"enabled": True}
    assert coordinator.updated_snapshots[0].policy_rules[0].enabled is False
    assert (
        coordinator.updated_snapshots[0].policy_rules[0].raw_update_payload["idleTs"]
        == 1_700_001_800
    )
    assert coordinator.data.policy_rules[0].enabled is True
    assert coordinator.data.policy_rules[0].raw_update_payload["idleTs"] == ""


async def test_async_pause_rule_ignores_missing_targets() -> None:
    """Test missing rule targets do not trigger client mutations."""
    snapshot = _build_snapshot(_build_rule("744"))
    manager, coordinator, _, update_rule_control_only = _build_manager(snapshot)
    manager.handle_refresh(
        {"policyRules": [snapshot.policy_rules[0].raw_update_payload]},
        snapshot,
    )

    with patch.object(manager, "_apply_optimistic_rule_update", Mock()) as optimistic:
        await manager.async_pause_rule("999", 1_700_001_800)

    assert update_rule_control_only.await_count == 0
    optimistic.assert_not_called()
    assert coordinator.data.policy_rules[0].rule_id == "744"
