"""Alarm inventory and command orchestration for Firewalla Local."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import UTC, timedelta
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ..api import FirewallaApiClient
from ..const import (
    ALARM_STATUS_ARCHIVED,
    MATCH_TYPE_ALARM_TYPE,
    MATCH_TYPE_DOMAIN,
    MATCH_TYPE_IP,
)
from ..models import FirewallaAlarm, FirewallaAlarmException, FirewallaRuntimeSnapshot
from ..utils.duration import parse_duration_to_seconds
from .base_manager import FirewallaBaseManager

if TYPE_CHECKING:
    from ..coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator

_ALARM_TYPE_GROUPS: dict[str, tuple[str, ...]] = {
    "security": (
        "ALARM_INTEL",
        "ALARM_BRO_NOTICE",
        "ALARM_CUSTOMIZED_SECURITY",
        "ALARM_SURICATA_NOTICE",
    ),
    "abnormal_upload": ("ALARM_LARGE_UPLOAD", "ALARM_LARGE_UPLOAD_2"),
    "open_port": ("ALARM_UPNP",),
}


class FirewallaAlarmManager(FirewallaBaseManager):
    """Own the entry-scoped alarm read model and alarm operations."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        entry: FirewallaConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the alarm manager."""
        super().__init__(coordinator, entry, client)
        self._alarms: tuple[FirewallaAlarm, ...] = ()
        self._exceptions: tuple[FirewallaAlarmException, ...] = ()
        self._active_count = 0
        self._archived_count = 0
        self._pending_count = 0

    def handle_refresh(self, snapshot: FirewallaRuntimeSnapshot) -> None:
        """Replace alarm state from one runtime snapshot."""
        self._alarms = snapshot.alarms
        self._exceptions = snapshot.alarm_exceptions
        self._active_count = snapshot.active_alarm_count
        self._archived_count = snapshot.archived_alarm_count
        self._pending_count = snapshot.pending_alarm_count

    @property
    def active_count(self) -> int:
        """Return the authoritative active count supplied by Firewalla."""
        return self._active_count

    @property
    def archived_count(self) -> int:
        """Return the authoritative archived count supplied by Firewalla."""
        return self._archived_count

    @property
    def pending_count(self) -> int:
        """Return the authoritative pending count supplied by Firewalla."""
        return self._pending_count

    @property
    def active_alarms(self) -> tuple[FirewallaAlarm, ...]:
        """Return the active alarms included in the current runtime snapshot."""
        return self._alarms

    @property
    def active_by_category(self) -> dict[str, int]:
        """Return snapshot-visible active-alarm counts by raw category."""
        counts = Counter(
            alarm.remote_category
            for alarm in self._alarms
            if alarm.remote_category is not None
        )
        return dict(sorted(counts.items()))

    @property
    def active_category_counts_complete(self) -> bool:
        """Return whether the capped alarm snapshot contains every active alarm."""
        return self._active_count == len(self._alarms)

    @property
    def exceptions(self) -> tuple[FirewallaAlarmException, ...]:
        """Return the normalized mute rules visible in the latest init payload."""
        return self._exceptions

    def get_alarm(self, alarm_id: str) -> FirewallaAlarm | None:
        """Return one alarm from the current active snapshot by ID."""
        return next(
            (alarm for alarm in self._alarms if alarm.alarm_id == alarm_id), None
        )

    async def async_get_alarms(
        self,
        *,
        limit: int,
        include_archived: bool,
        alarm_type: str | None,
        detail: bool,
    ) -> tuple[FirewallaAlarm, ...]:
        """Fetch and normalize active alarms, optionally archived and enriched."""
        active_records = await self.client.async_get_alarms(limit=limit)
        alarms = [
            alarm
            for raw_alarm in active_records
            if (alarm := self.client.normalize_alarm_record(raw_alarm)) is not None
        ]
        if include_archived:
            archived_records = await self.client.async_get_archived_alarms(limit=limit)
            alarms.extend(
                alarm
                for raw_alarm in archived_records
                if (
                    alarm := self.client.normalize_alarm_record(
                        raw_alarm, is_archived=True
                    )
                )
                is not None
            )

        if alarm_type is not None:
            matching_types = _ALARM_TYPE_GROUPS.get(alarm_type, (alarm_type,))
            alarms = [alarm for alarm in alarms if alarm.alarm_type in matching_types]

        alarms.sort(
            key=lambda alarm: (alarm.fired_at or 0, alarm.alarm_id), reverse=True
        )
        alarms = alarms[:limit]
        if detail:
            alarms = [await self._async_enrich_alarm(alarm) for alarm in alarms]
        return tuple(alarms)

    async def _async_enrich_alarm(self, alarm: FirewallaAlarm) -> FirewallaAlarm:
        """Return an alarm copy carrying opt-in detail payload keys."""
        detail_payload = await self.client.async_get_alarm_detail(alarm.alarm_id)
        severity = detail_payload.get("p.severity")
        return replace(
            alarm,
            raw_payload={**alarm.raw_payload, "detail": detail_payload},
            severity=severity.strip() if isinstance(severity, str) else alarm.severity,
        )

    async def async_archive_alarms(self, *, alarm_id: str | None) -> None:
        """Archive one alarm, or the active set when no id is given.

        No set parameter: archiving is only meaningful for an active alarm, so the
        bulk case is always the active set and a status argument would be a value the
        caller supplies and this method ignores.
        """
        if alarm_id is not None:
            await self.client.async_archive_alarm(alarm_id)
            return
        await self.client.async_archive_all_alarms()

    async def async_delete_alarms(
        self, *, alarm_id: str | None, alarm_status: str | None
    ) -> None:
        """Permanently delete one alarm, or every alarm in the named set."""
        if alarm_id is not None:
            await self.client.async_delete_alarm(alarm_id)
            return
        await self.client.async_delete_all_alarms(
            archived=alarm_status == ALARM_STATUS_ARCHIVED
        )

    async def async_mute_alarm(
        self,
        *,
        alarm_id: str | None,
        match_type: str,
        match_value: str | None,
        scope_kind: str,
        scope_target: str | None,
        duration: str,
    ) -> None:
        """Create a scoped silence using verified local mute payload shapes."""
        expiry = self._get_expiry_timestamp(duration)
        alarm = await self._async_find_alarm(alarm_id) if alarm_id is not None else None
        if alarm_id is not None and alarm is None:
            raise ValueError("Alarm was not found in the active or archived set")
        scope = self._get_scope_payload(scope_kind, scope_target)

        if match_type == MATCH_TYPE_ALARM_TYPE:
            muted_alarm_type = match_value or (
                alarm.alarm_type if alarm is not None else None
            )
            if muted_alarm_type is None:
                raise ValueError("An alarm type is required for a type-wide mute")
            value: dict[str, object] = {"type": muted_alarm_type, **scope}
            if expiry is not None:
                value["expireTs"] = expiry
            await self.client.async_create_alarm_exception(value)
            return

        # The caller's match vocabulary and the wire's are different words for the
        # same three things, so the translation is named for what it produces rather
        # than reusing `match_*`, which the caller's values already mean here.
        wire_key, match_target = self._get_match(match_type, match_value)
        if match_target is None and alarm is not None:
            match_target = (
                alarm.remote_host
                if match_type == MATCH_TYPE_DOMAIN
                else alarm.remote_ip
            )
        if match_target is None:
            raise ValueError("A domain or IP target is required for this mute")

        if (
            alarm is not None
            and not alarm.is_archived
            and scope_kind in ("device", "all")
        ):
            info: dict[str, object] = {"type": wire_key, "target": match_target}
            if scope_kind == "device":
                info["device"] = scope_target or ""
            if expiry is not None:
                info["expireTs"] = expiry
            await self.client.async_mute_alarm(
                {"alarmID": alarm.alarm_id, "matchAll": 1, "info": info}
            )
            return

        value = {**scope}
        if alarm is not None and alarm.alarm_type is not None:
            value["type"] = alarm.alarm_type
        value.update(
            {
                "if.type": wire_key,
                "if.target": match_target,
                "target_name": match_target,
                "p.dest.name" if wire_key == "dns" else "p.dest.ip": match_target,
            }
        )
        if expiry is not None:
            value["expireTs"] = expiry
        await self.client.async_create_alarm_exception(value)

    async def async_unmute_alarm(
        self, *, alarm_id: str | None, exception_id: str | None
    ) -> None:
        """Remove any silence by its exception ID, or by originating alarm ID."""
        if exception_id is not None:
            await self.client.async_delete_alarm_exception(exception_id)
            return
        exception = next(
            (item for item in self._exceptions if item.alarm_id == alarm_id), None
        )
        if exception is not None:
            await self.client.async_delete_alarm_exception(exception.exception_id)
        elif alarm_id is not None:
            await self.client.async_unmute_alarm(alarm_id)

    async def _async_find_alarm(self, alarm_id: str) -> FirewallaAlarm | None:
        """Look up an alarm in the active and archived local sets."""
        if alarm := self.get_alarm(alarm_id):
            return alarm
        for raw_alarm in await self.client.async_get_archived_alarms(limit=500):
            if (
                alarm := self.client.normalize_alarm_record(raw_alarm, is_archived=True)
            ) and alarm.alarm_id == alarm_id:
                return alarm
        return None

    @staticmethod
    def _get_match(match_type: str, match_value: str | None) -> tuple[str, str | None]:
        """Return the wire key and target for one caller-side match selection."""
        if match_type == MATCH_TYPE_ALARM_TYPE:
            return "alarmType", match_value
        if match_type == MATCH_TYPE_DOMAIN:
            return "dns", match_value
        if match_type == MATCH_TYPE_IP:
            return "ip", match_value
        raise ValueError(f"Unsupported alarm match type: {match_type}")

    @staticmethod
    def _get_scope_payload(
        scope_kind: str, scope_target: str | None
    ) -> dict[str, object]:
        """Map explicit scope selections to the local exception scope keys."""
        if scope_kind == "all":
            return {}
        if scope_kind == "device":
            return {"p.device.mac": scope_target or ""}
        if scope_kind in ("group", "user"):
            return {"p.tag.ids": [scope_target or ""]}
        return {"p.intf.id": scope_target or ""}

    def _get_expiry_timestamp(self, duration: str) -> int | None:
        """Return the verified local-runtime expiry timestamp for one duration."""
        if duration == "always":
            return None
        if duration == "today":
            time_zone = dt_util.get_time_zone(self.client.timezone_name or "UTC") or UTC
            now = dt_util.now(time_zone)
            return int(
                (now + timedelta(days=1))
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
            )
        seconds = parse_duration_to_seconds(duration)
        return int(dt_util.utcnow().timestamp()) + seconds
