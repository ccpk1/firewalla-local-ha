"""Integration-scoped orchestration for Firewalla Local."""

from __future__ import annotations

from collections.abc import Mapping
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
    FirewallaWanInterface,
    FirewallaWanUsagePeriod,
    FirewallaWanUsageSample,
    FirewallaWanUsageView,
)
from .base_manager import FirewallaBaseManager

if TYPE_CHECKING:
    from ..api import FirewallaApiClient
    from ..coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator

ORPHAN_POLICY_RETAIN_UNAVAILABLE_UNTIL_DESELECTED: Final = (
    "retain_unavailable_until_deselected"
)
_DEFAULT_BOX_NAME: Final = "Firewalla"
_RAW_MONTHLY_WAN_USAGE_KEY: Final = "monthlyDataUsageOnWans"
_RAW_WAN_INTERFACE_NAME_KEY: Final = "wan_intf_name"
_RAW_WAN_INTERFACE_UUID_KEY: Final = "wan_intf_uuid"
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

    def get_available_wans(self) -> tuple[FirewallaWanInterface, ...]:
        """Return the available WAN interfaces discovered in the runtime payload."""
        wan_by_uuid: dict[str, FirewallaWanInterface] = {}
        self._collect_wan_interfaces(
            self.coordinator.last_init_payload or {},
            wan_by_uuid,
        )

        if self.coordinator.data is not None:
            for speed_test in self.coordinator.data.speed_test_results:
                if speed_test.wan_uuid is None or speed_test.wan_uuid in wan_by_uuid:
                    continue
                wan_by_uuid[speed_test.wan_uuid] = FirewallaWanInterface(
                    uuid=speed_test.wan_uuid,
                    name=speed_test.wan_uuid,
                )

        return tuple(
            sorted(
                wan_by_uuid.values(),
                key=lambda wan: (wan.name.casefold(), wan.uuid),
            )
        )

    def get_speed_test_results(
        self,
        *,
        wan_uuid: str | None = None,
        limit: int | None = None,
    ) -> tuple[FirewallaSpeedTestResult, ...]:
        """Return shaped speed-test results from the coordinator snapshot."""
        if self.coordinator.data is None:
            return ()

        return self._build_speed_test_results(
            self.coordinator.data.speed_test_results,
            wan_uuid=wan_uuid,
            limit=limit,
        )

    async def async_run_internet_speed_test(self, wan_uuid: str) -> dict[str, object]:
        """Start one internet speed test for the requested WAN interface."""
        return await self.client.async_run_internet_speed_test(wan_uuid)

    def get_current_wan_usage(
        self,
        *,
        wan_uuid: str | None = None,
    ) -> tuple[FirewallaWanUsageView, ...]:
        """Return the current-month WAN usage view from the runtime payload."""
        raw_usage = (self.coordinator.last_init_payload or {}).get(
            _RAW_MONTHLY_WAN_USAGE_KEY
        )
        return self._build_current_wan_usage_views(raw_usage, wan_uuid=wan_uuid)

    async def async_get_wan_usage_history(
        self,
        *,
        wan_uuid: str | None = None,
    ) -> tuple[FirewallaWanUsageView, ...]:
        """Return the last-12-month WAN usage view from the local runtime."""
        raw_usage = await self.client.async_get_last12_monthly_wan_usage_payload()
        return self._build_last12_wan_usage_views(raw_usage, wan_uuid=wan_uuid)

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
            cpu_usage_1m=appliance_runtime.cpu_usage_1m,
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
        successful_results = tuple(
            result
            for result in self._build_speed_test_results(speed_test_records)
            if result.success is True
        )
        if not successful_results:
            return None
        return successful_results[0]

    def _build_speed_test_results(
        self,
        speed_test_records: tuple[FirewallaSpeedTestRecord, ...],
        *,
        wan_uuid: str | None = None,
        limit: int | None = None,
    ) -> tuple[FirewallaSpeedTestResult, ...]:
        """Shape protocol-facing speed tests into one stable result list."""
        wan_name_by_uuid = {wan.uuid: wan.name for wan in self.get_available_wans()}
        results = [
            result
            for record in speed_test_records
            if (result := self._build_speed_test_result(record, wan_name_by_uuid))
            is not None
            and (wan_uuid is None or result.wan_uuid == wan_uuid)
        ]
        results.sort(key=lambda result: result.tested_at_timestamp, reverse=True)
        if limit is not None:
            results = results[:limit]
        return tuple(results)

    def _build_speed_test_result(
        self,
        speed_test_record: FirewallaSpeedTestRecord,
        wan_name_by_uuid: Mapping[str, str],
    ) -> FirewallaSpeedTestResult | None:
        """Shape one protocol-facing speed-test record into a stable result."""
        if (
            speed_test_record.tested_at_timestamp is None
            or speed_test_record.success is None
        ):
            return None

        wan_uuid = speed_test_record.wan_uuid
        return FirewallaSpeedTestResult(
            tested_at_timestamp=speed_test_record.tested_at_timestamp,
            download_mbps=speed_test_record.download_mbps,
            upload_mbps=speed_test_record.upload_mbps,
            latency_ms=speed_test_record.latency_ms,
            jitter_ms=speed_test_record.jitter_ms,
            packet_loss_percent=speed_test_record.packet_loss_percent,
            download_megabytes=speed_test_record.download_megabytes,
            upload_megabytes=speed_test_record.upload_megabytes,
            isp=speed_test_record.isp,
            public_ip=speed_test_record.public_ip,
            server_country=speed_test_record.server_country,
            server_host=speed_test_record.server_host,
            server_id=speed_test_record.server_id,
            server_location=speed_test_record.server_location,
            server_sponsor=speed_test_record.server_sponsor,
            manual=speed_test_record.manual,
            success=speed_test_record.success,
            vendor=speed_test_record.vendor,
            wan_uuid=wan_uuid,
            wan_name=wan_name_by_uuid.get(wan_uuid) if wan_uuid is not None else None,
        )

    def _collect_wan_interfaces(
        self,
        raw_value: object,
        wan_by_uuid: dict[str, FirewallaWanInterface],
    ) -> None:
        """Collect WAN interface metadata from nested raw runtime structures."""
        if isinstance(raw_value, dict):
            wan_uuid = raw_value.get(_RAW_WAN_INTERFACE_UUID_KEY)
            if isinstance(wan_uuid, str) and wan_uuid:
                wan_name = raw_value.get(_RAW_WAN_INTERFACE_NAME_KEY)
                resolved_name = (
                    wan_name if isinstance(wan_name, str) and wan_name else wan_uuid
                )
                existing_wan = wan_by_uuid.get(wan_uuid)
                if existing_wan is None or existing_wan.name == existing_wan.uuid:
                    wan_by_uuid[wan_uuid] = FirewallaWanInterface(
                        uuid=wan_uuid,
                        name=resolved_name,
                    )

            for nested_value in raw_value.values():
                self._collect_wan_interfaces(nested_value, wan_by_uuid)
            return

        if isinstance(raw_value, list):
            for nested_value in raw_value:
                self._collect_wan_interfaces(nested_value, wan_by_uuid)

    def _build_current_wan_usage_views(
        self,
        raw_usage: object,
        *,
        wan_uuid: str | None = None,
    ) -> tuple[FirewallaWanUsageView, ...]:
        """Build the current-month WAN usage view from raw payload data."""
        if not isinstance(raw_usage, dict):
            return ()

        wan_name_by_uuid = {wan.uuid: wan.name for wan in self.get_available_wans()}
        views: list[FirewallaWanUsageView] = []
        for raw_wan_uuid, raw_period in raw_usage.items():
            if not isinstance(raw_wan_uuid, str) or not raw_wan_uuid:
                continue
            if wan_uuid is not None and raw_wan_uuid != wan_uuid:
                continue
            if not isinstance(raw_period, dict):
                continue

            period = self._build_wan_usage_period(
                raw_period,
                bucket_timestamp=None,
                begin_timestamp=self._normalized_int(raw_period.get("monthlyBeginTs")),
                end_timestamp=self._normalized_int(raw_period.get("monthlyEndTs")),
            )
            if period is None:
                continue

            views.append(
                FirewallaWanUsageView(
                    wan_uuid=raw_wan_uuid,
                    wan_name=wan_name_by_uuid.get(raw_wan_uuid, raw_wan_uuid),
                    periods=(period,),
                )
            )

        return tuple(
            sorted(
                views,
                key=lambda view: ((view.wan_name or "").casefold(), view.wan_uuid),
            )
        )

    def _build_last12_wan_usage_views(
        self,
        raw_usage: object,
        *,
        wan_uuid: str | None = None,
    ) -> tuple[FirewallaWanUsageView, ...]:
        """Build the last-12-month WAN usage view from raw payload data."""
        if not isinstance(raw_usage, dict):
            return ()

        wan_name_by_uuid = {wan.uuid: wan.name for wan in self.get_available_wans()}
        views: list[FirewallaWanUsageView] = []
        for raw_wan_uuid, raw_periods in raw_usage.items():
            if not isinstance(raw_wan_uuid, str) or not raw_wan_uuid:
                continue
            if wan_uuid is not None and raw_wan_uuid != wan_uuid:
                continue
            if not isinstance(raw_periods, list):
                continue

            periods = tuple(
                period
                for raw_period in raw_periods
                if isinstance(raw_period, dict)
                and (
                    period := self._build_wan_usage_period(
                        raw_period.get("stats"),
                        bucket_timestamp=self._normalized_int(raw_period.get("ts")),
                        begin_timestamp=None,
                        end_timestamp=None,
                    )
                )
                is not None
            )
            if not periods:
                continue

            views.append(
                FirewallaWanUsageView(
                    wan_uuid=raw_wan_uuid,
                    wan_name=wan_name_by_uuid.get(raw_wan_uuid, raw_wan_uuid),
                    periods=periods,
                )
            )

        return tuple(
            sorted(
                views,
                key=lambda view: ((view.wan_name or "").casefold(), view.wan_uuid),
            )
        )

    def _build_wan_usage_period(
        self,
        raw_stats: object,
        *,
        bucket_timestamp: int | None,
        begin_timestamp: int | None,
        end_timestamp: int | None,
    ) -> FirewallaWanUsagePeriod | None:
        """Build one normalized WAN usage period from raw payload data."""
        if not isinstance(raw_stats, dict):
            return None

        download_samples = self._build_wan_usage_samples(raw_stats.get("download"))
        upload_samples = self._build_wan_usage_samples(raw_stats.get("upload"))
        resolved_begin_timestamp, resolved_end_timestamp = (
            self._derive_wan_usage_period_bounds(
                bucket_timestamp=bucket_timestamp,
                begin_timestamp=begin_timestamp,
                end_timestamp=end_timestamp,
                download_samples=download_samples,
                upload_samples=upload_samples,
            )
        )

        return FirewallaWanUsagePeriod(
            bucket_timestamp=bucket_timestamp,
            begin_timestamp=resolved_begin_timestamp,
            end_timestamp=resolved_end_timestamp,
            total_download_bytes=self._normalized_int(raw_stats.get("totalDownload")),
            total_upload_bytes=self._normalized_int(raw_stats.get("totalUpload")),
            download_samples=download_samples,
            upload_samples=upload_samples,
        )

    def _derive_wan_usage_period_bounds(
        self,
        *,
        bucket_timestamp: int | None,
        begin_timestamp: int | None,
        end_timestamp: int | None,
        download_samples: tuple[FirewallaWanUsageSample, ...],
        upload_samples: tuple[FirewallaWanUsageSample, ...],
    ) -> tuple[int | None, int | None]:
        """Derive period bounds when the raw payload omits explicit begin and end."""
        if begin_timestamp is not None and end_timestamp is not None:
            return begin_timestamp, end_timestamp

        sample_timestamps = sorted(
            {sample.timestamp for sample in (*download_samples, *upload_samples)}
        )
        if sample_timestamps:
            return (
                (
                    begin_timestamp
                    if begin_timestamp is not None
                    else sample_timestamps[0]
                ),
                (end_timestamp if end_timestamp is not None else sample_timestamps[-1]),
            )

        return begin_timestamp or bucket_timestamp, end_timestamp or bucket_timestamp

    def _build_wan_usage_samples(
        self,
        raw_samples: object,
    ) -> tuple[FirewallaWanUsageSample, ...]:
        """Build normalized WAN usage samples from a raw list payload."""
        if not isinstance(raw_samples, list):
            return ()

        samples: list[FirewallaWanUsageSample] = []
        for raw_sample in raw_samples:
            if not isinstance(raw_sample, list) or len(raw_sample) < 2:
                continue
            timestamp = self._normalized_int(raw_sample[0])
            value = self._normalized_int(raw_sample[1])
            if timestamp is None or value is None:
                continue
            samples.append(FirewallaWanUsageSample(timestamp=timestamp, value=value))

        return tuple(samples)

    def _normalized_int(self, value: object) -> int | None:
        """Return an integer from a Firewalla numeric field when possible."""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return None
            try:
                return int(stripped_value)
            except ValueError:
                return None
        return None

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
