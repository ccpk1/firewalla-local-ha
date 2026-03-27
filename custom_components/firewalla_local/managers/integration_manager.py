"""Integration-scoped orchestration for Firewalla Local."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from ..const import (
    CONF_LICENSE,
    DOMAIN,
    ENTITY_SUFFIX_SWITCH,
    MANUFACTURER,
    PLATFORM_SWITCH,
)
from ..models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaDiskUsageInput,
    FirewallaRuleTemplate,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
    FirewallaSpeedTestResult,
    FirewallaSystemInfo,
    FirewallaSystemStatus,
)
from .base_manager import FirewallaBaseManager

if TYPE_CHECKING:
    from ..api import FirewallaApiClient
    from ..coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator

ORPHAN_POLICY_RETAIN_UNAVAILABLE_UNTIL_DESELECTED: Final = (
    "retain_unavailable_until_deselected"
)
_DEFAULT_BOX_NAME: Final = "Firewalla"
_SYSTEM_STATUS_PRIMARY_DISK_MOUNTS: Final = (
    "/",
    "/boot",
    "/boot/efi",
    "/var/lib/docker",
    "/log",
    "/data",
)


class FirewallaIntegrationManager(FirewallaBaseManager):
    """Own shared entry-scoped lifecycle and appliance behavior."""

    ORPHAN_POLICY: Final = ORPHAN_POLICY_RETAIN_UNAVAILABLE_UNTIL_DESELECTED

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        entry: FirewallaConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the integration manager."""
        super().__init__(coordinator, entry, client)
        self._system_info: FirewallaSystemInfo | None = None
        self._system_status: FirewallaSystemStatus | None = None
        self._latest_speed_test: FirewallaSpeedTestResult | None = None

    def handle_refresh(self, snapshot: FirewallaRuntimeSnapshot) -> None:
        """Shape manager-owned appliance views from one refresh snapshot."""
        self._system_info = self._build_system_info(snapshot.appliance_identity)
        self._system_status = self._build_system_status(snapshot.appliance_runtime)
        self._latest_speed_test = self._build_latest_speed_test(
            snapshot.speed_test_results
        )

    @property
    def system_info(self) -> FirewallaSystemInfo:
        """Return the current shaped appliance identity view."""
        if self._system_info is None:
            self._system_info = self._build_system_info(
                self.coordinator.data.appliance_identity
            )
        return self._system_info

    @property
    def system_status(self) -> FirewallaSystemStatus | None:
        """Return the current shaped appliance status view."""
        if self._system_status is None and self.coordinator.data is not None:
            self._system_status = self._build_system_status(
                self.coordinator.data.appliance_runtime
            )
        return self._system_status

    @property
    def latest_speed_test(self) -> FirewallaSpeedTestResult | None:
        """Return the latest successful shaped speed-test view."""
        if self._latest_speed_test is None and self.coordinator.data is not None:
            self._latest_speed_test = self._build_latest_speed_test(
                self.coordinator.data.speed_test_results
            )
        return self._latest_speed_test

    def _build_system_info(
        self, appliance_identity: FirewallaApplianceIdentityInput
    ) -> FirewallaSystemInfo:
        """Shape the appliance identity view from protocol-facing input."""
        return FirewallaSystemInfo(
            host=appliance_identity.host,
            name=(
                appliance_identity.group_name
                or appliance_identity.device_name
                or _DEFAULT_BOX_NAME
            ),
            model=appliance_identity.model,
            serial_number=appliance_identity.serial_number,
            software_version=appliance_identity.software_version,
        )

    def _build_system_status(
        self, appliance_runtime: FirewallaApplianceRuntimeInput
    ) -> FirewallaSystemStatus:
        """Shape the appliance status view from protocol-facing input."""
        return FirewallaSystemStatus(
            booting_complete=appliance_runtime.booting_complete,
            cloud_connected=appliance_runtime.cloud_connected,
            ddns=appliance_runtime.ddns,
            firmware_release_type=appliance_runtime.firmware_release_type,
            wan_ip=self._build_wan_ip(appliance_runtime),
            wan_ips=appliance_runtime.public_ips,
            cpu_load_5m=appliance_runtime.cpu_load_5m,
            memory_usage_percent=self._build_memory_usage_percent(appliance_runtime),
            memory_free_mb=self._build_memory_free_mb(appliance_runtime),
            uptime_seconds=appliance_runtime.uptime_seconds,
            disk_usage_percent_by_mount=self._build_disk_usage_percent_by_mount(
                appliance_runtime.disk_usages
            ),
        )

    def _build_wan_ip(
        self, appliance_runtime: FirewallaApplianceRuntimeInput
    ) -> str | None:
        """Build the primary WAN public IP from protocol-facing input."""
        if appliance_runtime.public_ip is not None:
            return appliance_runtime.public_ip
        if appliance_runtime.public_ips:
            return next(iter(appliance_runtime.public_ips.values()))
        return None

    def _build_memory_usage_percent(
        self, appliance_runtime: FirewallaApplianceRuntimeInput
    ) -> float | None:
        """Build the memory usage percentage from protocol-facing input."""
        if appliance_runtime.memory_usage_ratio is None:
            return None
        return round(appliance_runtime.memory_usage_ratio * 100, 1)

    def _build_memory_free_mb(
        self, appliance_runtime: FirewallaApplianceRuntimeInput
    ) -> float | None:
        """Build free memory in megabytes from protocol-facing input."""
        if (
            appliance_runtime.total_memory_mb is None
            or appliance_runtime.memory_usage_ratio is None
        ):
            return None
        return round(
            appliance_runtime.total_memory_mb
            * (1 - appliance_runtime.memory_usage_ratio),
            1,
        )

    def _build_disk_usage_percent_by_mount(
        self, disk_usages: tuple[FirewallaDiskUsageInput, ...]
    ) -> dict[str, int] | None:
        """Build a filtered disk usage map for important system mounts."""
        usage_by_mount: dict[str, int] = {}
        for disk_usage in disk_usages:
            if disk_usage.mount not in _SYSTEM_STATUS_PRIMARY_DISK_MOUNTS:
                continue

            usage_ratio = disk_usage.capacity_ratio
            if usage_ratio is None:
                if (
                    disk_usage.used_bytes is None
                    or disk_usage.size_bytes is None
                    or disk_usage.size_bytes == 0
                ):
                    continue
                usage_ratio = disk_usage.used_bytes / disk_usage.size_bytes

            usage_by_mount[disk_usage.mount] = round(usage_ratio * 100)

        filtered_usage = {
            mount: usage_by_mount[mount]
            for mount in _SYSTEM_STATUS_PRIMARY_DISK_MOUNTS
            if mount in usage_by_mount
        }
        return filtered_usage or None

    def _build_latest_speed_test(
        self, speed_test_records: tuple[FirewallaSpeedTestRecord, ...]
    ) -> FirewallaSpeedTestResult | None:
        """Shape the latest successful speed-test view from protocol-facing input."""
        successful_records = tuple(
            record
            for record in speed_test_records
            if record.success is True and record.tested_at_timestamp is not None
        )
        if not successful_records:
            return None

        latest_record = max(
            successful_records,
            key=lambda record: record.tested_at_timestamp or 0,
        )
        return FirewallaSpeedTestResult(
            tested_at_timestamp=latest_record.tested_at_timestamp or 0,
            download_mbps=latest_record.download_mbps,
            upload_mbps=latest_record.upload_mbps,
            latency_ms=latest_record.latency_ms,
            jitter_ms=latest_record.jitter_ms,
            packet_loss_percent=latest_record.packet_loss_percent,
            download_megabytes=latest_record.download_megabytes,
            upload_megabytes=latest_record.upload_megabytes,
            isp=latest_record.isp,
            public_ip=latest_record.public_ip,
            server_country=latest_record.server_country,
            server_host=latest_record.server_host,
            server_id=latest_record.server_id,
            server_location=latest_record.server_location,
            server_sponsor=latest_record.server_sponsor,
            manual=latest_record.manual,
            success=True,
            vendor=latest_record.vendor,
        )

    def build_device_info(self) -> DeviceInfo:
        """Build the license-anchored device entry for this config entry."""
        system_info = self.system_info
        return DeviceInfo(
            identifiers={
                (DOMAIN, self.entry.unique_id or self.entry.data[CONF_LICENSE])
            },
            manufacturer=MANUFACTURER,
            model=system_info.model,
            name=system_info.name,
            serial_number=system_info.serial_number,
            sw_version=system_info.software_version,
        )

    def build_entity_unique_id(self, *, object_id: str, suffix: str) -> str:
        """Build a multi-instance-safe unique ID for one entity surface."""
        return f"{self.entry.entry_id}_{object_id}_{suffix}"

    async def async_reconcile_rule_switch_entities(
        self, templates: tuple[FirewallaRuleTemplate, ...]
    ) -> None:
        """Remove stale rule-switch registry entries for deselected templates."""
        entity_registry = er.async_get(self.coordinator.hass)
        expected_unique_ids = {
            self.build_entity_unique_id(
                object_id=template.source_rule_id,
                suffix=ENTITY_SUFFIX_SWITCH,
            )
            for template in templates
        }

        for entity_entry in er.async_entries_for_config_entry(
            entity_registry,
            self.entry.entry_id,
        ):
            if (
                entity_entry.domain != PLATFORM_SWITCH
                or entity_entry.platform != DOMAIN
            ):
                continue
            if not entity_entry.unique_id.endswith(f"_{ENTITY_SUFFIX_SWITCH}"):
                continue
            if entity_entry.unique_id in expected_unique_ids:
                continue

            entity_registry.async_remove(entity_entry.entity_id)
