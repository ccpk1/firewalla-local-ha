"""Host-scoped orchestration for Firewalla Local host surfaces."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace

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
from ..models import (
    FirewallaActivityBasis,
    FirewallaHostRuntime,
    FirewallaRuntimeSnapshot,
)
from ..utils.host_activity import (
    count_online_hosts,
    is_host_online,
    is_vpn_peer,
    reference_last_active,
)
from ..utils.mac import normalize_mac_address
from .base_manager import FirewallaBaseManager


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
        if host.ip_address is not None and host.ip_address != host.host_name:
            return f"{host.host_name} ({host.ip_address})"
        return host.host_name

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
        self._host_index = {
            normalized_mac: host
            for host in snapshot.hosts
            if (normalized_mac := normalize_mac_address(host.mac)) is not None
        }

    def apply_optimistic_host_update(
        self,
        mac: str,
        *,
        transform: Callable[[FirewallaHostRuntime], FirewallaHostRuntime] | None = None,
        removed: bool = False,
    ) -> None:
        """Publish a successful host mutation to the in-memory snapshot.

        `ARCHITECTURE.md` requires a successful command to update runtime state so
        the next read agrees with it, with the coordinator refresh as the later
        source of truth. Without this a host write was invisible until the next poll
        — up to the update interval — which is why these services forced a poll
        instead.

        `transform` is a callable rather than a field mapping because it keeps the
        dataclass field types checkable: `replace(host, **mapping)` erases them, and
        the caller knows the concrete field it is setting, so it should say so.

        The index and the snapshot are republished together and from the same tuple.
        That is the fix for a real inconsistency: deletion popped the host out of
        `_host_index` while `coordinator.data.hosts` still carried it, so
        `get_host(mac)` returned nothing while `list_hosts` — which reads the
        snapshot — still listed it. One inventory, two answers.
        """
        snapshot = self.coordinator.data
        if snapshot is None:
            return

        normalized_mac = normalize_mac_address(mac)
        if normalized_mac is None:
            return

        if removed:
            updated_hosts = tuple(
                host
                for host in snapshot.hosts
                if normalize_mac_address(host.mac) != normalized_mac
            )
        elif transform is not None:
            updated_hosts = tuple(
                (
                    transform(host)
                    if normalize_mac_address(host.mac) == normalized_mac
                    else host
                )
                for host in snapshot.hosts
            )
        else:
            return

        if updated_hosts == snapshot.hosts:
            return

        updated_snapshot = replace(snapshot, hosts=updated_hosts)
        # rebuilds `_host_index` from the same tuple, so the two cannot disagree
        self.handle_refresh(updated_snapshot)
        self.coordinator.async_set_updated_data(updated_snapshot)

    def remove_host_from_index(self, mac: str) -> None:
        """Drop one normalized MAC from the host index after a deletion."""
        if normalized_mac := normalize_mac_address(mac):
            self._host_index.pop(normalized_mac, None)

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

    def get_host(self, mac: str) -> FirewallaHostRuntime | None:
        """Return one normalized host by its Firewalla MAC identifier."""
        if normalized_mac := normalize_mac_address(mac):
            return self._host_index.get(normalized_mac)
        return None

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
        """Return the online window in seconds.

        Shared by every connectivity surface — the watched-device sensors and
        the device and VPN-peer counts — so they cannot disagree about whether
        the same device is online.
        """
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

    def activity_basis(self) -> FirewallaActivityBasis:
        """Return the frame this manager's connectivity booleans are measured in.

        Every connectivity surface measures from the freshness of the whole host
        inventory rather than from the wall clock, so a stale snapshot does not
        mark the entire network offline. It is published as a pair so a caller
        that reports a boolean can also report what it was measured against: the
        reference and the window are only meaningful together, and a surface that
        paired the appliance reference with a window of its own would reopen
        exactly the disagreement this replaced.
        """
        return FirewallaActivityBasis(
            reference_at=reference_last_active(self.get_hosts()),
            window_seconds=self.watched_device_online_window_seconds,
        )

    def count_total_devices(self) -> int:
        """Return the total number of normalized hosts in the latest snapshot."""
        return len(self.get_hosts())

    def is_watched_device_online(self, host: FirewallaHostRuntime) -> bool | None:
        """Return whether one normalized host appears online for watched devices."""
        if not self.get_hosts():
            return None

        basis = self.activity_basis()
        return is_host_online(
            host,
            reference_activity=basis.reference_at,
            online_window_seconds=basis.window_seconds,
        )

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
        basis = self.activity_basis()
        return count_online_hosts(
            self.get_hosts(),
            reference_activity=basis.reference_at,
            online_window_seconds=basis.window_seconds,
        )

    def count_offline_devices(self) -> int:
        """Return the number of hosts that do not appear online."""
        return self.count_total_devices() - self.count_online_devices()

    def get_vpn_peers(self) -> tuple[FirewallaHostRuntime, ...]:
        """Return the VPN peers from the latest snapshot.

        Peers are a subset of the host inventory, not an additional
        population, so their counts are a breakdown of the device counts.
        """
        return tuple(host for host in self.get_hosts() if is_vpn_peer(host))

    def count_vpn_total_devices(self) -> int:
        """Return the number of VPN peers in the latest snapshot."""
        return len(self.get_vpn_peers())

    def count_vpn_online_devices(self) -> int:
        """Return the number of VPN peers that appear online.

        Peers carry ``last_active`` from the peer inventory, so the shared
        online definition applies unchanged — no peer-specific window.

        The reference is the *appliance-wide* freshest activity, not the freshest
        peer. Measuring from the peers alone made the newest peer online by
        construction, however long ago it was: it reported one connected VPN peer
        whose last activity was 4.5 days earlier, while the host list -- using the
        appliance reference -- showed all five offline.
        """
        basis = self.activity_basis()
        return count_online_hosts(
            self.get_vpn_peers(),
            reference_activity=basis.reference_at,
            online_window_seconds=basis.window_seconds,
        )

    def count_vpn_offline_devices(self) -> int:
        """Return the number of VPN peers that do not appear online."""
        return self.count_vpn_total_devices() - self.count_vpn_online_devices()
