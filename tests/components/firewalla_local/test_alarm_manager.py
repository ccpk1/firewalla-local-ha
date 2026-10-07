"""Tests for Firewalla Local alarm manager behavior."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import ClientSession

from custom_components.firewalla_local.api import FirewallaApiClient
from custom_components.firewalla_local.coordinator import (
    FirewallaConfigEntry,
    FirewallaDataUpdateCoordinator,
)
from custom_components.firewalla_local.managers.alarm_manager import (
    FirewallaAlarmManager,
)
from custom_components.firewalla_local.models import (
    FirewallaAlarm,
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaRuntimeSnapshot,
)


def _alarm(
    alarm_id: str,
    *,
    alarm_type: str,
    fired_at: float,
    category: str | None,
    remote_host: str | None = None,
    remote_ip: str | None = None,
    archived: bool = False,
) -> FirewallaAlarm:
    """Build a normalized alarm for manager tests."""
    return FirewallaAlarm(
        alarm_id=alarm_id,
        alarm_type=alarm_type,
        device_name="test host",
        message="test alarm",
        state="active",
        is_archived=archived,
        fired_at=fired_at,
        remote_category=category,
        remote_host=remote_host,
        remote_ip=remote_ip,
        remote_app=None,
        remote_region=None,
        remote_latitude=None,
        remote_longitude=None,
        interface_name=None,
        protocol=None,
        severity=None,
    )


class _StubCoordinator:
    """A coordinator stub whose update method republishes `data` like the real one."""

    def __init__(self, data: FirewallaRuntimeSnapshot) -> None:
        """Hold one snapshot."""
        self.data = data
        self.updates: list[FirewallaRuntimeSnapshot] = []

    def async_set_updated_data(self, data: FirewallaRuntimeSnapshot) -> None:
        """Replace the held snapshot, as the coordinator does."""
        self.data = data
        self.updates.append(data)


def _snapshot_with(
    alarms: tuple[FirewallaAlarm, ...],
    *,
    active_count: int,
    archived_count: int,
) -> FirewallaRuntimeSnapshot:
    """Return a snapshot carrying the given alarm state."""
    return FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.0.2.1",
            group_name=None,
            device_name=None,
            model=None,
            serial_number=None,
            software_version=None,
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
        alarms=alarms,
        active_alarm_count=active_count,
        archived_alarm_count=archived_count,
        pending_alarm_count=0,
    )


def _manager_with_alarms(
    client: FirewallaApiClient,
    alarms: tuple[FirewallaAlarm, ...],
    *,
    active_count: int = 2,
    archived_count: int = 0,
) -> tuple[FirewallaAlarmManager, _StubCoordinator]:
    """Return an alarm manager holding the given alarms, plus its coordinator."""
    snapshot = _snapshot_with(
        alarms, active_count=active_count, archived_count=archived_count
    )
    coordinator = _StubCoordinator(snapshot)
    manager = FirewallaAlarmManager(
        cast(FirewallaDataUpdateCoordinator, coordinator),
        cast(FirewallaConfigEntry, Mock()),
        client,
    )
    manager.handle_refresh(snapshot)
    return manager, coordinator


def _manager(client: FirewallaApiClient) -> FirewallaAlarmManager:
    """Build an alarm manager with isolated entry/coordinator dependencies."""
    return FirewallaAlarmManager(
        cast(FirewallaDataUpdateCoordinator, Mock()),
        cast(FirewallaConfigEntry, Mock()),
        client,
    )


def _client() -> FirewallaApiClient:
    """Build a client whose transport is unused by these manager tests."""
    return FirewallaApiClient(
        session=cast(ClientSession, Mock()),
        host="192.0.2.1",
        gid="gid",
        eid="eid",
        aid="aid",
        symmetric_key="key",
        device_name="test",
    )


def test_alarm_manager_uses_authoritative_counts_and_categories() -> None:
    """The count comes from Firewalla, not the capped alarm list length."""
    manager = _manager(_client())
    active_alarms = (
        _alarm(
            "alarm-1",
            alarm_type="ALARM_VIDEO",
            fired_at=10,
            category="av",
        ),
        _alarm(
            "alarm-2",
            alarm_type="ALARM_GAME",
            fired_at=20,
            category="games",
        ),
        _alarm(
            "alarm-3",
            alarm_type="ALARM_PORN",
            fired_at=30,
            category="av",
        ),
    )
    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.0.2.1",
            group_name=None,
            device_name=None,
            model=None,
            serial_number=None,
            software_version=None,
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
        alarms=active_alarms,
        active_alarm_count=12,
        archived_alarm_count=7,
        pending_alarm_count=2,
    )

    manager.handle_refresh(snapshot)

    assert manager.active_count == 12
    assert manager.archived_count == 7
    assert manager.pending_count == 2
    assert manager.active_by_category == {"av": 2, "games": 1}
    assert not manager.active_category_counts_complete


def test_alarm_manager_defaults_to_empty_inventory() -> None:
    """Missing alarm data produces a stable empty inventory and zero counts."""
    manager = _manager(_client())

    assert manager.active_count == 0
    assert manager.archived_count == 0
    assert manager.pending_count == 0
    assert manager.active_alarms == ()
    assert manager.active_by_category == {}
    assert manager.active_category_counts_complete


@pytest.mark.asyncio
async def test_mute_alarm_type_creates_explicit_scoped_exception() -> None:
    """Type-wide mutes use the verified exception:create payload shape."""
    client = _client()
    manager = _manager(client)
    with patch.object(
        client, "async_create_alarm_exception", AsyncMock()
    ) as create_exception:
        await manager.async_mute_alarm(
            alarm_id=None,
            target_type="alarm_type",
            target_value="ALARM_GAME",
            scope_kind="host",
            scope_target="00:11:22:33:44:55",
            duration="always",
        )

    create_exception.assert_awaited_once_with(
        {"type": "ALARM_GAME", "p.device.mac": "00:11:22:33:44:55"}
    )


@pytest.mark.asyncio
async def test_mute_active_alarm_uses_alarm_allow_for_dns_device_scope() -> None:
    """A verified active alarm uses alarm:allow for DNS and device matching."""
    client = _client()
    manager = _manager(client)
    alarm = _alarm(
        "alarm-1",
        alarm_type="ALARM_VIDEO",
        fired_at=10,
        category="av",
        remote_host="example.com",
    )
    manager.handle_refresh(
        FirewallaRuntimeSnapshot(
            appliance_identity=FirewallaApplianceIdentityInput(
                host="192.0.2.1",
                group_name=None,
                device_name=None,
                model=None,
                serial_number=None,
                software_version=None,
            ),
            appliance_runtime=FirewallaApplianceRuntimeInput(),
            policy_rules=(),
            exception_rule_count=0,
            alarms=(alarm,),
        )
    )
    with patch.object(client, "async_mute_alarm", AsyncMock()) as mute_alarm:
        await manager.async_mute_alarm(
            alarm_id="alarm-1",
            target_type="domain",
            target_value=None,
            scope_kind="host",
            scope_target="00:11:22:33:44:55",
            duration="always",
        )

    mute_alarm.assert_awaited_once_with(
        {
            "alarmID": "alarm-1",
            "matchAll": 1,
            "info": {
                "type": "dns",
                "target": "example.com",
                "device": "00:11:22:33:44:55",
            },
        }
    )


@pytest.mark.asyncio
async def test_get_alarms_filters_companion_types_before_detail() -> None:
    """Security includes its implicit companions; detail only enriches results."""
    client = _client()
    manager = _manager(client)
    active_payloads = (
        {"aid": "active-security", "type": "ALARM_INTEL", "alarmTimestamp": "10"},
        {"aid": "active-video", "type": "ALARM_VIDEO", "alarmTimestamp": "30"},
    )
    archived_payloads = (
        {
            "aid": "archived-security",
            "type": "ALARM_SURICATA_NOTICE",
            "alarmTimestamp": "20",
        },
    )
    with (
        patch.object(
            client, "async_get_alarms", AsyncMock(return_value=active_payloads)
        ),
        patch.object(
            client,
            "async_get_archived_alarms",
            AsyncMock(return_value=archived_payloads),
        ),
        patch.object(
            client,
            "async_get_alarm_detail",
            AsyncMock(return_value={"p.severity": "high"}),
        ) as get_detail,
    ):
        alarms = await manager.async_get_alarms(
            limit=2,
            include_archived=True,
            alarm_type="security",
            detail=True,
        )

    assert [alarm.alarm_id for alarm in alarms] == [
        "archived-security",
        "active-security",
    ]
    assert alarms[0].is_archived
    assert all(alarm.severity == "high" for alarm in alarms)
    assert get_detail.await_count == 2


@pytest.mark.asyncio
async def test_archive_one_alarm_updates_state_and_counts() -> None:
    """Archiving an alarm moves it out of the active set and both counts with it.

    `ARCHITECTURE.md` requires a successful command to update runtime state so the
    next read agrees with it. Without this the alarm stayed active in every read for
    up to the update interval, which is why these services forced a poll.
    """
    client = _client()
    client.async_archive_alarm = AsyncMock()
    first = _alarm(
        "a1", alarm_type="ALARM_INTEL", fired_at=1_700_000_000.0, category="security"
    )
    second = _alarm(
        "a2", alarm_type="ALARM_INTEL", fired_at=1_700_000_100.0, category="security"
    )
    manager, coordinator = _manager_with_alarms(client, (first, second))

    await manager.async_archive_alarms(alarm_id="a1")

    assert client.async_archive_alarm.await_count == 1
    assert [alarm.alarm_id for alarm in manager.active_alarms] == ["a2"]
    assert manager.active_count == 1
    assert manager.archived_count == 1
    # the snapshot carries the same state, so a later refresh or diagnostics read
    # cannot disagree with the manager
    assert coordinator.data.active_alarm_count == 1
    assert coordinator.data.archived_alarm_count == 1
    assert [alarm.alarm_id for alarm in coordinator.data.alarms] == ["a2"]


@pytest.mark.asyncio
async def test_archive_all_moves_the_whole_active_set() -> None:
    """Bulk archive clears the active set and folds its size into the archive."""
    client = _client()
    client.async_archive_all_alarms = AsyncMock()
    manager, coordinator = _manager_with_alarms(
        client,
        (
            _alarm(
                "a1",
                alarm_type="ALARM_INTEL",
                fired_at=1_700_000_000.0,
                category="security",
            ),
            _alarm(
                "a2",
                alarm_type="ALARM_INTEL",
                fired_at=1_700_000_100.0,
                category="security",
            ),
        ),
        archived_count=3,
    )

    await manager.async_archive_alarms(alarm_id=None)

    assert manager.active_alarms == ()
    assert manager.active_count == 0
    assert manager.archived_count == 5
    assert coordinator.data.archived_alarm_count == 5


@pytest.mark.asyncio
async def test_delete_from_the_archived_set_changes_only_the_count() -> None:
    """Deleting the archived set leaves the active list and count alone.

    The archived set is not held locally — `_alarms` is the active set — so there is
    nothing to remove from it, and dropping the active list here would hide alarms
    that still exist.
    """
    client = _client()
    client.async_delete_all_alarms = AsyncMock()
    manager, _ = _manager_with_alarms(
        client,
        (
            _alarm(
                "a1",
                alarm_type="ALARM_INTEL",
                fired_at=1_700_000_000.0,
                category="security",
            ),
        ),
        active_count=1,
        archived_count=4,
    )

    await manager.async_delete_alarms(alarm_id=None, alarm_status="archived")

    assert [alarm.alarm_id for alarm in manager.active_alarms] == ["a1"]
    assert manager.active_count == 1
    assert manager.archived_count == 0


@pytest.mark.asyncio
async def test_delete_one_alarm_that_is_not_held_leaves_state_untouched() -> None:
    """A delete for an alarm outside the active set publishes nothing.

    The counts include archived alarms this manager does not hold, so decrementing
    for an id it never had would report a count that no operation justified.
    """
    client = _client()
    client.async_delete_alarm = AsyncMock()
    manager, coordinator = _manager_with_alarms(
        client,
        (
            _alarm(
                "a1",
                alarm_type="ALARM_INTEL",
                fired_at=1_700_000_000.0,
                category="security",
            ),
        ),
        active_count=1,
        archived_count=4,
    )

    await manager.async_delete_alarms(alarm_id="archived-only", alarm_status=None)

    assert coordinator.updates == []
    assert manager.active_count == 1
    assert manager.archived_count == 4
