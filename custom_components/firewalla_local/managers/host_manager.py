"""Host-scoped orchestration for Firewalla Local watched-device surfaces."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from ..api import FirewallaApiClient
from ..const import CONF_WATCHED_DEVICES
from ..coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator
from ..models import FirewallaHostRuntime, FirewallaRuntimeSnapshot
from .base_manager import FirewallaBaseManager

_UNAVAILABLE_HOST_LABEL = "Unavailable device"
_ONLINE_ACTIVITY_WINDOW_SECONDS: Final = 300


class FirewallaHostManager(FirewallaBaseManager):
    """Own normalized host lookups for watched-device features."""

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

    @staticmethod
    def _get_configured_watched_device_macs(
        options: Mapping[str, object],
    ) -> tuple[str, ...]:
        """Return the configured watched-device MACs in a stable order."""
        raw_watched_devices = options.get(CONF_WATCHED_DEVICES, [])
        if not isinstance(raw_watched_devices, list):
            return ()

        return tuple(
            sorted(mac for mac in raw_watched_devices if isinstance(mac, str) and mac)
        )

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

    def handle_refresh(self, snapshot: FirewallaRuntimeSnapshot) -> None:
        """Route refreshed host inventory into manager-owned indexes."""
        self._host_index = {host.mac: host for host in snapshot.hosts}

    @property
    def configured_watched_device_macs(self) -> tuple[str, ...]:
        """Return the watched-device MACs configured when this manager loaded."""
        return self._configured_watched_device_macs

    def get_hosts(self) -> tuple[FirewallaHostRuntime, ...]:
        """Return the normalized host inventory from the latest snapshot."""
        if self.coordinator.data is None:
            return ()
        return self.coordinator.data.hosts

    def get_watched_device_choices(self) -> dict[str, str]:
        """Return watched-device choices from the latest normalized host inventory."""
        return self.get_watched_device_choices_for_hosts(self.get_hosts())

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

    def get_host(self, mac: str) -> FirewallaHostRuntime | None:
        """Return one normalized host by its Firewalla MAC identifier."""
        return self._host_index.get(mac)

    def count_total_devices(self) -> int:
        """Return the total number of normalized hosts in the latest snapshot."""
        return len(self.get_hosts())

    def is_host_online(self, host: FirewallaHostRuntime) -> bool | None:
        """Return whether one normalized host appears online."""
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
            reference_last_active - host.last_active <= _ONLINE_ACTIVITY_WINDOW_SECONDS
        )

    def count_online_devices(self) -> int:
        """Return the number of hosts that appear online in the latest snapshot."""
        return sum(1 for host in self.get_hosts() if self.is_host_online(host) is True)

    def count_offline_devices(self) -> int:
        """Return the number of hosts that do not appear online."""
        return self.count_total_devices() - self.count_online_devices()
