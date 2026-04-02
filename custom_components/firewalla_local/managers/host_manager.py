"""Host-scoped orchestration for Firewalla Local host surfaces."""

from __future__ import annotations

from collections.abc import Mapping

from homeassistant.util import dt as dt_util

from ..api import FirewallaApiClient
from ..const import (
    CONF_DEVICE_TRACKER_AWAY_WINDOW,
    CONF_DEVICE_TRACKERS,
    CONF_WATCHED_DEVICE_ONLINE_WINDOW,
    CONF_WATCHED_DEVICES,
    DEFAULT_DEVICE_TRACKER_AWAY_WINDOW_MINUTES,
    DEFAULT_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES,
    MIN_DEVICE_TRACKER_AWAY_WINDOW_MINUTES,
    MIN_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES,
)
from ..coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator
from ..models import FirewallaHostRuntime, FirewallaRuntimeSnapshot
from .base_manager import FirewallaBaseManager

_UNAVAILABLE_HOST_LABEL = "Unavailable device"


class FirewallaHostManager(FirewallaBaseManager):
    """Own normalized host lookups for watched-device and device-tracker features."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        entry: FirewallaConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the host manager."""
        super().__init__(coordinator, entry, client)
        self._host_index: dict[str, FirewallaHostRuntime] = {}
        self._configured_watched_device_macs = self._get_configured_watched_device_macs(
            entry.options
        )
        self._configured_device_tracker_macs = self._get_configured_device_tracker_macs(
            entry.options
        )

    @staticmethod
    def _get_configured_device_macs(
        options: Mapping[str, object], option_key: str
    ) -> tuple[str, ...]:
        """Return one configured MAC-address list in a stable order."""
        raw_devices = options.get(option_key, [])
        if not isinstance(raw_devices, list):
            return ()

        return tuple(sorted(mac for mac in raw_devices if isinstance(mac, str) and mac))

    @staticmethod
    def _get_configured_watched_device_macs(
        options: Mapping[str, object],
    ) -> tuple[str, ...]:
        """Return the configured watched-device MACs in a stable order."""
        return FirewallaHostManager._get_configured_device_macs(
            options, CONF_WATCHED_DEVICES
        )

    @staticmethod
    def _get_configured_device_tracker_macs(
        options: Mapping[str, object],
    ) -> tuple[str, ...]:
        """Return the configured device-tracker MACs in a stable order."""
        return FirewallaHostManager._get_configured_device_macs(
            options, CONF_DEVICE_TRACKERS
        )

    @staticmethod
    def _looks_like_mac_address(value: str) -> bool:
        """Return whether a host identifier matches the MAC-backed LAN contract."""
        parts = value.split(":")
        if len(parts) != 6:
            return False
        return all(len(part) == 2 for part in parts)

    @classmethod
    def is_mac_backed_trackable_host(cls, host: FirewallaHostRuntime) -> bool:
        """Return whether one normalized host is eligible for device tracking."""
        return cls._looks_like_mac_address(host.mac)

    @staticmethod
    def _format_host_choice_label(host: FirewallaHostRuntime) -> str:
        """Build the best available user-facing host label."""
        if host.ip_address is not None and host.ip_address != host.display_name:
            return f"{host.display_name} ({host.ip_address})"
        return host.display_name

    @classmethod
    def get_watched_device_choices_for_hosts(
        cls, hosts: tuple[FirewallaHostRuntime, ...]
    ) -> dict[str, str]:
        """Return watched-device choices keyed by MAC from one host snapshot."""
        return {
            host.mac: cls._format_host_choice_label(host)
            for host in sorted(
                hosts,
                key=lambda host: (
                    cls._format_host_choice_label(host).casefold(),
                    host.mac,
                ),
            )
        }

    @classmethod
    def get_device_tracker_choices_for_hosts(
        cls, hosts: tuple[FirewallaHostRuntime, ...]
    ) -> dict[str, str]:
        """Return device-tracker choices for MAC-backed LAN hosts only."""
        return {
            host.mac: cls._format_host_choice_label(host)
            for host in sorted(
                (host for host in hosts if cls.is_mac_backed_trackable_host(host)),
                key=lambda host: (
                    cls._format_host_choice_label(host).casefold(),
                    host.mac,
                ),
            )
        }

    def handle_refresh(self, snapshot: FirewallaRuntimeSnapshot) -> None:
        """Route refreshed host inventory into manager-owned indexes."""
        self._host_index = {host.mac: host for host in snapshot.hosts}

    @property
    def configured_watched_device_macs(self) -> tuple[str, ...]:
        """Return the watched-device MACs configured when this manager loaded."""
        return self._configured_watched_device_macs

    @property
    def configured_device_tracker_macs(self) -> tuple[str, ...]:
        """Return the device-tracker MACs configured when this manager loaded."""
        return self._configured_device_tracker_macs

    def get_hosts(self) -> tuple[FirewallaHostRuntime, ...]:
        """Return the normalized host inventory from the latest snapshot."""
        if self.coordinator.data is None:
            return ()
        return self.coordinator.data.hosts

    def get_watched_device_choices(self) -> dict[str, str]:
        """Return watched-device choices from the latest normalized host inventory."""
        return self.get_watched_device_choices_for_hosts(self.get_hosts())

    def get_device_tracker_choices(self) -> dict[str, str]:
        """Return device-tracker choices from the latest normalized host inventory."""
        return self.get_device_tracker_choices_for_hosts(self.get_hosts())

    def get_missing_watched_device_choices(
        self, configured_watched_device_macs: tuple[str, ...]
    ) -> dict[str, str]:
        """Return unavailable watched-device labels for missing configured MACs."""
        live_choices = self.get_watched_device_choices()
        return {
            mac: f"[{mac}] {_UNAVAILABLE_HOST_LABEL}"
            for mac in configured_watched_device_macs
            if mac not in live_choices
        }

    def get_missing_device_tracker_choices(
        self, configured_device_tracker_macs: tuple[str, ...]
    ) -> dict[str, str]:
        """Return unavailable device-tracker labels for missing configured MACs."""
        live_choices = self.get_device_tracker_choices()
        return {
            mac: f"[{mac}] {_UNAVAILABLE_HOST_LABEL}"
            for mac in configured_device_tracker_macs
            if mac not in live_choices
        }

    def get_host(self, mac: str) -> FirewallaHostRuntime | None:
        """Return one normalized host by its Firewalla MAC identifier."""
        return self._host_index.get(mac)

    def _get_window_minutes(self, option_key: str, default: int, minimum: int) -> int:
        """Return one validated minute-based activity window from options."""
        raw_value: object = self.entry.options.get(option_key, default)
        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            return default
        if raw_value < minimum:
            return default
        return raw_value

    @property
    def watched_device_online_window_seconds(self) -> int:
        """Return the watched-device activity window in seconds."""
        return (
            self._get_window_minutes(
                CONF_WATCHED_DEVICE_ONLINE_WINDOW,
                DEFAULT_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES,
                MIN_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES,
            )
            * 60
        )

    @property
    def device_tracker_away_window_seconds(self) -> int:
        """Return the device-tracker away window in seconds."""
        return (
            self._get_window_minutes(
                CONF_DEVICE_TRACKER_AWAY_WINDOW,
                DEFAULT_DEVICE_TRACKER_AWAY_WINDOW_MINUTES,
                MIN_DEVICE_TRACKER_AWAY_WINDOW_MINUTES,
            )
            * 60
        )

    def count_total_devices(self) -> int:
        """Return the total number of normalized hosts in the latest snapshot."""
        return len(self.get_hosts())

    def is_watched_device_online(self, host: FirewallaHostRuntime) -> bool | None:
        """Return whether one normalized host appears online for watched devices."""
        hosts = self.get_hosts()
        if not hosts:
            return None

        reference_last_active = max(
            (
                candidate.last_active
                for candidate in hosts
                if candidate.last_active is not None
            ),
            default=None,
        )
        if reference_last_active is None:
            return None if host.stale is None else not host.stale

        if host.stale is True or host.last_active is None:
            return False

        return (
            reference_last_active - host.last_active
            <= self.watched_device_online_window_seconds
        )

    def is_host_online(self, host: FirewallaHostRuntime) -> bool | None:
        """Return whether one normalized host appears online."""
        return self.is_watched_device_online(host)

    def is_device_tracker_home(self, host: FirewallaHostRuntime) -> bool | None:
        """Return whether one normalized host should be considered home."""
        if host.last_active is not None:
            now_timestamp = dt_util.utcnow().timestamp()
            return (
                now_timestamp - host.last_active
                <= self.device_tracker_away_window_seconds
            )

        return None if host.stale is None else not host.stale

    def count_online_devices(self) -> int:
        """Return the number of hosts that appear online in the latest snapshot."""
        return sum(
            1
            for host in self.get_hosts()
            if self.is_watched_device_online(host) is True
        )

    def count_offline_devices(self) -> int:
        """Return the number of hosts that do not appear online."""
        return self.count_total_devices() - self.count_online_devices()
