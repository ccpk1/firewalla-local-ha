"""User-scoped orchestration for Firewalla Local watched-user surfaces."""

from __future__ import annotations

from collections.abc import Mapping

from ..api import FirewallaApiClient
from ..const import CONF_WATCHED_USERS
from ..coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator
from ..models import (
    FirewallaRuntimeSnapshot,
    FirewallaUserRuntime,
    FirewallaWatchedUser,
)
from .base_manager import FirewallaBaseManager

_UNAVAILABLE_USER_LABEL = "Unavailable user"


class FirewallaUserManager(FirewallaBaseManager):
    """Own normalized watched-user lookups and host associations."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        entry: FirewallaConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the watched-user manager."""
        super().__init__(coordinator, entry, client)
        self._user_index: dict[str, FirewallaWatchedUser] = {}
        self._configured_watched_user_ids = self._get_configured_watched_user_ids(
            entry.options
        )

    @staticmethod
    def _get_configured_watched_user_ids(
        options: Mapping[str, object],
    ) -> tuple[str, ...]:
        """Return configured watched-user identifiers in stable order."""
        raw_watched_users = options.get(CONF_WATCHED_USERS, [])
        if not isinstance(raw_watched_users, list):
            return ()
        return tuple(
            sorted(
                user_id
                for user_id in raw_watched_users
                if isinstance(user_id, str) and user_id
            )
        )

    @staticmethod
    def _format_user_choice_label(user: FirewallaWatchedUser) -> str:
        """Build the best available user-facing label."""
        if (
            user.affiliated_group_name is not None
            and user.affiliated_group_name != user.name
        ):
            return f"{user.name} ({user.affiliated_group_name})"
        return user.name

    @classmethod
    def get_watched_user_choices_for_users(
        cls, users: tuple[FirewallaWatchedUser, ...]
    ) -> dict[str, str]:
        """Return watched-user choices keyed by user identifier."""
        return {
            user.user_id: cls._format_user_choice_label(user)
            for user in sorted(
                users,
                key=lambda user: (
                    cls._format_user_choice_label(user).casefold(),
                    user.user_id,
                ),
            )
        }

    @classmethod
    def get_watched_user_choices_for_snapshot(
        cls, snapshot: FirewallaRuntimeSnapshot
    ) -> dict[str, str]:
        """Return watched-user choices directly from one runtime snapshot."""
        return cls.get_watched_user_choices_for_users(
            tuple(
                cls._build_watched_user_view(
                    user,
                    cls._get_associated_hosts_for_user(user, snapshot),
                )
                for user in snapshot.users
            )
        )

    def handle_refresh(self, snapshot: FirewallaRuntimeSnapshot) -> None:
        """Route refreshed user and host data into manager-owned views."""
        self._user_index = {
            user.user_id: self._build_watched_user_view(
                user,
                self._get_associated_hosts_for_user(user, snapshot),
            )
            for user in snapshot.users
        }

    @staticmethod
    def _get_associated_hosts_for_user(
        user: FirewallaUserRuntime,
        snapshot: FirewallaRuntimeSnapshot,
    ) -> list[tuple[str, str, float | None]]:
        """Return hosts associated to one user by direct or affiliated-group linkage."""
        associated_hosts: list[tuple[str, str, float | None]] = []
        for host in snapshot.hosts:
            if user.user_id in host.user_ids or (
                user.affiliated_group_id is not None
                and user.affiliated_group_id in host.group_ids
            ):
                associated_hosts.append((host.mac, host.display_name, host.last_active))
        return associated_hosts

    @staticmethod
    def _build_watched_user_view(
        user: FirewallaUserRuntime,
        associated_hosts: list[tuple[str, str, float | None]],
    ) -> FirewallaWatchedUser:
        """Build one watched-user view with resolved host associations."""
        sorted_hosts = sorted(
            associated_hosts,
            key=lambda host: (host[1].casefold(), host[0]),
        )
        last_active = max(
            (
                host_last_active
                for _mac, _name, host_last_active in sorted_hosts
                if host_last_active is not None
            ),
            default=None,
        )
        total_minutes_today = user.total_minutes_today
        if total_minutes_today is None and user.app_usage_today:
            total_minutes_today = sum(
                usage.total_minutes for usage in user.app_usage_today
            )

        unique_minutes_today = user.unique_minutes_today
        if unique_minutes_today is None and user.app_usage_today:
            unique_minutes_today = sum(
                usage.unique_minutes for usage in user.app_usage_today
            )

        return FirewallaWatchedUser(
            user_id=user.user_id,
            name=user.name,
            affiliated_group_name=user.affiliated_group_name,
            total_minutes_today=total_minutes_today,
            unique_minutes_today=unique_minutes_today,
            app_usage_today=user.app_usage_today,
            associated_host_names=tuple(
                host_name for _mac, host_name, _last_active in sorted_hosts
            ),
            associated_host_macs=tuple(
                host_mac for host_mac, _name, _last_active in sorted_hosts
            ),
            last_active=last_active,
        )

    @property
    def configured_watched_user_ids(self) -> tuple[str, ...]:
        """Return the watched-user identifiers configured for this entry."""
        return self._configured_watched_user_ids

    def get_users(self) -> tuple[FirewallaWatchedUser, ...]:
        """Return the currently resolved watched-user views."""
        return tuple(self._user_index.values())

    def get_watched_user_choices(self) -> dict[str, str]:
        """Return watched-user choices from the latest normalized runtime data."""
        return self.get_watched_user_choices_for_users(self.get_users())

    def get_missing_watched_user_choices(
        self, configured_watched_user_ids: tuple[str, ...]
    ) -> dict[str, str]:
        """Return unavailable watched-user labels for missing configured users."""
        live_choices = self.get_watched_user_choices()
        return {
            user_id: f"[{user_id}] {_UNAVAILABLE_USER_LABEL}"
            for user_id in configured_watched_user_ids
            if user_id not in live_choices
        }

    def get_user(self, user_id: str) -> FirewallaWatchedUser | None:
        """Return one watched-user view by identifier."""
        return self._user_index.get(user_id)
