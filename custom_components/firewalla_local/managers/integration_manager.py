"""Integration-scoped orchestration for Firewalla Local."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, time, timedelta, tzinfo
from typing import TYPE_CHECKING, Final, cast

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
    FirewallaGroupRuntime,
    FirewallaHostRuntime,
    FirewallaNetworkHostRanking,
    FirewallaNetworkHostTotals,
    FirewallaNetworkMetricSample,
    FirewallaNetworkMetricSeries,
    FirewallaNetworkSegment,
    FirewallaNetworkSegmentView,
    FirewallaNetworkUsageBucket,
    FirewallaRuleTemplate,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
    FirewallaSpeedTestResult,
    FirewallaSystemInfo,
    FirewallaSystemStatus,
    FirewallaUsageHistoryDeviceUsage,
    FirewallaUsageHistoryEntry,
    FirewallaUsageHistoryInterval,
    FirewallaUsageHistoryMetric,
    FirewallaUsageHistorySlot,
    FirewallaUsageHistoryTarget,
    FirewallaUsageHistoryView,
    FirewallaWanDataUsage,
    FirewallaWanDataUsagePeriod,
    FirewallaWanDataUsageReport,
    FirewallaWanDataUsageRow,
    FirewallaWanDataUsageSample,
    FirewallaWanEvent,
    FirewallaWanEventFailure,
    FirewallaWanEventStatus,
    FirewallaWanInterface,
    FirewallaWanUsageSummary,
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
_RAW_NETWORK_CONFIG_KEY: Final = "networkConfig"
_RAW_NETWORK_PROFILES_KEY: Final = "networkProfiles"
_RAW_INTERFACE_KEY: Final = "interface"
_RAW_META_KEY: Final = "meta"
_RAW_NAME_KEY: Final = "name"
_RAW_DESC_KEY: Final = "desc"
_RAW_INTF_KEY: Final = "intf"
_RAW_UUID_KEY: Final = "uuid"
_RAW_WAN_INTERFACE_NAME_KEY: Final = "wan_intf_name"
_RAW_WAN_INTERFACE_UUID_KEY: Final = "wan_intf_uuid"
_WEEK_START_MONDAY: Final = 0
_SUPPORTED_WAN_EVENT_STATE_FAMILIES: Final = frozenset(
    {"wan_state", "overall_wan_state", "dualwan_state", "dns"}
)
_SUPPORTED_WAN_EVENT_ACTION_FAMILIES: Final = frozenset({"ping_RTT", "ping_lossrate"})
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

    def get_groups(self) -> tuple[FirewallaGroupRuntime, ...]:
        """Return normalized group inventory from the current snapshot."""
        if self.coordinator.data is None:
            return ()
        return self.coordinator.data.groups

    def get_available_networks(self) -> tuple[FirewallaNetworkSegment, ...]:
        """Return the available network segments discovered in runtime metadata."""
        network_lookup = self._build_network_lookup(
            self.coordinator.last_init_payload or {}
        )
        return tuple(
            sorted(
                (
                    FirewallaNetworkSegment(uuid=network_id, name=network_name)
                    for network_id, network_name in network_lookup.items()
                ),
                key=lambda network: (network.name.casefold(), network.uuid),
            )
        )

    async def async_run_internet_speed_test(self, wan_uuid: str) -> dict[str, object]:
        """Start one internet speed test for the requested WAN interface."""
        return await self.client.async_run_internet_speed_test(wan_uuid)

    async def async_wake_host(self, host_mac: str) -> dict[str, object]:
        """Send one Wake-on-LAN command to the requested host."""
        return await self.client.async_wake_host(host_mac)

    async def async_get_usage_history(
        self,
        *,
        target: FirewallaUsageHistoryTarget,
        begin_timestamp: int,
        end_timestamp: int,
        granularity: str,
        include_intervals: bool,
        app_ids: tuple[str, ...] | None,
    ) -> FirewallaUsageHistoryView:
        """Return one normalized usage-history response for the resolved target."""
        raw_payload = await self.client.async_get_usage_history_payload(
            scope_type=target.request_scope_type,
            target=target.target_id,
            begin_timestamp=begin_timestamp,
            end_timestamp=end_timestamp,
            granularity=granularity,
            app_ids=app_ids,
        )
        return self._build_usage_history_view(
            raw_payload,
            target=target,
            begin_timestamp=begin_timestamp,
            end_timestamp=end_timestamp,
            granularity=granularity,
            include_intervals=include_intervals,
            app_ids=app_ids,
        )

    def get_current_wan_usage_summaries(
        self,
        *,
        wan_uuid: str | None = None,
    ) -> tuple[FirewallaWanUsageSummary, ...]:
        """Return current WAN usage totals from the coordinator payload."""
        raw_usage = (self.coordinator.last_init_payload or {}).get(
            _RAW_MONTHLY_WAN_USAGE_KEY
        )
        return self._build_current_wan_usage_summaries(raw_usage, wan_uuid=wan_uuid)

    async def async_get_wan_data_usage_reports(
        self,
        *,
        wan_uuid: str | None = None,
        current_periods: tuple[str, ...],
        history_period: str | None,
        history_count: int,
        detail: str,
        time_zone: tzinfo,
    ) -> tuple[FirewallaWanDataUsageReport, ...]:
        """Return normalized WAN data-usage reports from direct local reads."""
        current_requested = any(
            period in current_periods for period in ("month", "week", "day")
        )
        history_requested = history_period is not None and history_count > 0

        current_raw: object = {}
        history_raw: object = {}
        if current_requested and history_requested:
            current_raw, history_raw = await asyncio.gather(
                self.client.async_get_monthly_wan_usage_payload(),
                self.client.async_get_last12_monthly_wan_usage_payload(),
            )
        elif current_requested:
            current_raw = await self.client.async_get_monthly_wan_usage_payload()
        elif history_requested:
            history_raw = await self.client.async_get_last12_monthly_wan_usage_payload()

        current_rows, current_day_rows = self._build_current_wan_data_usage_rows(
            current_raw,
            wan_uuid=wan_uuid,
            detail=detail,
            time_zone=time_zone,
        )
        history_rows, history_day_rows = self._build_history_wan_data_usage_rows(
            history_raw,
            wan_uuid=wan_uuid,
            history_count=history_count,
            history_period=history_period,
            detail=detail,
            time_zone=time_zone,
        )
        wan_name_by_uuid = {wan.uuid: wan.name for wan in self.get_available_wans()}
        report_wan_ids = tuple(
            sorted(
                set(current_rows)
                | set(current_day_rows)
                | set(history_rows)
                | set(history_day_rows),
                key=lambda candidate: (
                    (wan_name_by_uuid.get(candidate, candidate) or "").casefold(),
                    candidate,
                ),
            )
        )

        return tuple(
            FirewallaWanDataUsageReport(
                wan_uuid=report_wan_id,
                wan_name=wan_name_by_uuid.get(report_wan_id, report_wan_id),
                current_month=(
                    current_rows.get(report_wan_id)
                    if "month" in current_periods
                    else None
                ),
                current_week=self._build_current_week_row(
                    current_day_rows.get(report_wan_id, ()),
                    detail=detail,
                    time_zone=time_zone,
                )
                if "week" in current_periods
                else None,
                current_day=self._build_current_day_row(
                    current_day_rows.get(report_wan_id, ())
                )
                if "day" in current_periods
                else None,
                history_months=history_rows.get(report_wan_id, ()),
                history_weeks=(
                    self._build_history_week_rows(
                        history_day_rows.get(report_wan_id, ()),
                        history_count=history_count,
                        detail=detail,
                        time_zone=time_zone,
                    )
                    if history_period == "week"
                    else ()
                ),
                history_days=(
                    self._build_history_day_rows(
                        history_day_rows.get(report_wan_id, ()),
                        history_count=history_count,
                    )
                    if history_period == "day"
                    else ()
                ),
            )
            for report_wan_id in report_wan_ids
        )

    async def async_get_wan_events(
        self,
        *,
        wan_uuid: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[FirewallaWanEvent, ...]:
        """Return normalized WAN health events from the local runtime."""
        raw_events = await self.client.async_get_wan_events_payload(
            limit_count=limit,
            limit_offset=offset,
        )
        return self._build_wan_events(raw_events, wan_uuid=wan_uuid)

    async def async_get_network_interfaces(
        self,
        *,
        network_uuid: str | None = None,
    ) -> tuple[FirewallaNetworkSegmentView, ...]:
        """Return normalized network-interface summaries from the local runtime."""
        available_networks = self.get_available_networks()
        requested_networks = tuple(
            network
            for network in available_networks
            if network_uuid is None or network.uuid == network_uuid
        )
        if not requested_networks:
            return ()

        raw_payloads = await asyncio.gather(
            *(
                self.client.async_get_network_interface_payload(
                    network_uuid=network.uuid,
                )
                for network in requested_networks
            )
        )
        host_lookup = self._build_host_lookup()
        return tuple(
            self._build_network_segment_view(
                raw_payload,
                target=network,
                host_lookup=host_lookup,
            )
            for network, raw_payload in zip(
                requested_networks,
                raw_payloads,
                strict=True,
            )
        )

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

    def _build_host_lookup(self) -> dict[str, FirewallaHostRuntime]:
        """Build a host-id to normalized host lookup from the current snapshot."""
        if self.coordinator.data is None:
            return {}
        return {host.mac: host for host in self.coordinator.data.hosts if host.mac}

    def _build_network_lookup(self, data: dict[str, object]) -> dict[str, str]:
        """Build a lookup of network UUIDs to readable network names."""
        raw_network_profiles = data.get(_RAW_NETWORK_PROFILES_KEY)
        network_lookup: dict[str, str] = {}

        if isinstance(raw_network_profiles, dict):
            for network_id, raw_profile in raw_network_profiles.items():
                if not isinstance(network_id, str) or not network_id:
                    continue
                if not isinstance(raw_profile, dict):
                    continue

                if display_name := self._resolve_network_display_name(raw_profile):
                    network_lookup[network_id] = display_name

        raw_network_config = data.get(_RAW_NETWORK_CONFIG_KEY)
        if isinstance(raw_network_config, dict):
            self._merge_network_config_lookup(
                raw_network_config.get(_RAW_INTERFACE_KEY),
                network_lookup,
            )

        return network_lookup

    def _resolve_network_display_name(
        self, raw_profile: dict[str, object]
    ) -> str | None:
        """Resolve the best available display name from one network profile."""
        for key in (_RAW_DESC_KEY, _RAW_NAME_KEY, _RAW_INTF_KEY):
            value = raw_profile.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _merge_network_config_lookup(
        self, raw_interfaces: object, network_lookup: dict[str, str]
    ) -> None:
        """Merge readable network names from networkConfig interface metadata."""
        if isinstance(raw_interfaces, dict):
            meta = raw_interfaces.get(_RAW_META_KEY)
            if isinstance(meta, dict):
                network_id = meta.get(_RAW_UUID_KEY)
                if isinstance(network_id, str) and network_id:
                    for candidate in (
                        meta.get(_RAW_NAME_KEY),
                        raw_interfaces.get(_RAW_DESC_KEY),
                        raw_interfaces.get(_RAW_NAME_KEY),
                    ):
                        if isinstance(candidate, str) and candidate:
                            network_lookup[network_id] = candidate
                            break

            for value in raw_interfaces.values():
                self._merge_network_config_lookup(value, network_lookup)
            return

        if isinstance(raw_interfaces, list):
            for value in raw_interfaces:
                self._merge_network_config_lookup(value, network_lookup)

    def _build_network_segment_view(
        self,
        raw_payload: dict[str, object],
        *,
        target: FirewallaNetworkSegment,
        host_lookup: dict[str, FirewallaHostRuntime],
    ) -> FirewallaNetworkSegmentView:
        """Normalize one raw item=intf payload into a bounded segment view."""
        raw_flows = raw_payload.get("flows")
        flows = raw_flows if isinstance(raw_flows, Mapping) else {}
        hosts = self._build_network_hosts(
            raw_payload.get("hosts"),
            host_lookup=host_lookup,
        )
        activity_hosts = self._build_network_activity_hosts(
            flows,
            host_lookup=host_lookup,
        )
        return FirewallaNetworkSegmentView(
            target=FirewallaNetworkSegment(
                uuid=target.uuid,
                name=self._optional_string(raw_payload.get("name")) or target.name,
            ),
            interface_name=self._optional_string(raw_payload.get("intf")),
            network_type=self._optional_string(raw_payload.get("type")),
            monitoring=self._optional_bool(raw_payload.get("monitoring")),
            active=self._optional_bool(raw_payload.get("active")),
            ready=self._optional_bool(raw_payload.get("ready")),
            pending_test=self._optional_bool(raw_payload.get("pendingTest")),
            gateway=self._optional_string(raw_payload.get("gateway")),
            gateway6=self._optional_string(raw_payload.get("gateway6")),
            route_id=self._optional_string(raw_payload.get("rtid")),
            dns_servers=self._string_tuple(raw_payload.get("dns")),
            dns6_servers=self._string_tuple(raw_payload.get("dns6")),
            original_dns_servers=self._string_tuple(raw_payload.get("origDns")),
            original_dns6_servers=self._string_tuple(raw_payload.get("origDns6")),
            ipv4_addresses=self._combine_string_values(
                raw_payload.get("ipv4"),
                raw_payload.get("ipv4s"),
            ),
            ipv4_subnets=self._combine_string_values(
                raw_payload.get("ipv4Subnet"),
                raw_payload.get("ipv4Subnets"),
            ),
            ipv6_addresses=self._string_tuple(raw_payload.get("ipv6")),
            ipv6_subnets=self._string_tuple(raw_payload.get("ipv6Subnets")),
            route4_subnets=self._string_tuple(raw_payload.get("rt4Subnets")),
            route6_subnets=self._string_tuple(raw_payload.get("rt6Subnets")),
            policy=self._normalized_dict(raw_payload.get("policy")),
            hosts=hosts,
            top_download_hosts=self._build_network_flow_rankings(
                self._resolve_network_ranking_payload(
                    flows.get("download") or raw_payload.get("download")
                ),
                host_lookup=host_lookup,
                metric_key="download",
            ),
            top_upload_hosts=self._build_network_flow_rankings(
                self._resolve_network_ranking_payload(
                    flows.get("upload") or raw_payload.get("upload")
                ),
                host_lookup=host_lookup,
                metric_key="upload",
            ),
            activity_hosts=activity_hosts,
            top_apps=self._build_network_usage_buckets(flows.get("appDetails")),
            top_categories=self._build_network_usage_buckets(
                flows.get("categoryDetails")
            ),
            new_last24=self._build_network_metric_series(raw_payload.get("newLast24")),
            last60=self._build_network_metric_series(raw_payload.get("last60")),
            last30=self._build_network_metric_series(raw_payload.get("last30")),
            last12_months=self._build_network_metric_series(
                raw_payload.get("last12Months")
            ),
        )

    def _build_network_hosts(
        self,
        raw_hosts: object,
        *,
        host_lookup: dict[str, FirewallaHostRuntime],
    ) -> tuple[FirewallaNetworkHostTotals, ...]:
        """Normalize per-host totals exposed by one item=intf payload."""
        if not isinstance(raw_hosts, Mapping):
            return ()

        hosts: list[FirewallaNetworkHostTotals] = []
        for host_id, raw_totals in raw_hosts.items():
            if not isinstance(host_id, str) or not host_id:
                continue
            if not isinstance(raw_totals, Mapping):
                continue

            host = host_lookup.get(host_id)
            hosts.append(
                FirewallaNetworkHostTotals(
                    host_id=host_id,
                    host_name=host.display_name if host is not None else None,
                    ip_address=host.ip_address if host is not None else None,
                    conn=self._optional_int(raw_totals.get("conn")),
                    dns=self._optional_int(raw_totals.get("dns")),
                    dns_blocked=self._optional_int(raw_totals.get("dnsB")),
                    ip_blocked=self._optional_int(raw_totals.get("ipB")),
                    ip_denied=self._optional_int(raw_totals.get("ipD")),
                    ntp=self._optional_int(raw_totals.get("ntp")),
                    download_bytes=self._optional_int(raw_totals.get("download")),
                    upload_bytes=self._optional_int(raw_totals.get("upload")),
                )
            )

        return tuple(
            sorted(
                hosts,
                key=lambda host: (
                    -((host.download_bytes or 0) + (host.upload_bytes or 0)),
                    host.host_name.casefold() if host.host_name else "",
                    host.host_id,
                ),
            )
        )

    def _build_network_activity_hosts(
        self,
        raw_flows: Mapping[str, object],
        *,
        host_lookup: dict[str, FirewallaHostRuntime],
    ) -> tuple[FirewallaNetworkHostTotals, ...]:
        """Build per-device activity rows from richer flow families."""
        activity_by_host: dict[str, dict[str, object]] = {}

        def ensure_activity_host(
            host_id: str,
            *,
            ip_address: str | None = None,
        ) -> dict[str, object]:
            host = host_lookup.get(host_id)
            activity = activity_by_host.setdefault(
                host_id,
                {
                    "host_name": host.display_name if host is not None else None,
                    "ip_address": host.ip_address if host is not None else ip_address,
                    "conn": 0,
                    "download_bytes": 0,
                    "upload_bytes": 0,
                },
            )
            if activity["ip_address"] is None and ip_address is not None:
                activity["ip_address"] = ip_address
            return activity

        raw_app_details = raw_flows.get("appDetails")
        if isinstance(raw_app_details, Mapping):
            for raw_rows in raw_app_details.values():
                if not isinstance(raw_rows, list):
                    continue
                for raw_row in raw_rows:
                    if not isinstance(raw_row, Mapping):
                        continue
                    host_id = (
                        self._optional_string(raw_row.get("device"))
                        or self._optional_string(raw_row.get("mac"))
                        or self._optional_string(raw_row.get("deviceMac"))
                    )
                    if host_id is None:
                        continue
                    activity = ensure_activity_host(host_id)
                    activity["download_bytes"] = cast(
                        int, activity["download_bytes"]
                    ) + (self._optional_int(raw_row.get("download")) or 0)
                    activity["upload_bytes"] = cast(int, activity["upload_bytes"]) + (
                        self._optional_int(raw_row.get("upload")) or 0
                    )

        raw_recent = raw_flows.get("recent")
        if isinstance(raw_recent, list):
            for raw_row in raw_recent:
                if not isinstance(raw_row, Mapping):
                    continue
                host_id = (
                    self._optional_string(raw_row.get("device"))
                    or self._optional_string(raw_row.get("mac"))
                    or self._optional_string(raw_row.get("deviceMac"))
                )
                if host_id is None:
                    continue
                activity = ensure_activity_host(
                    host_id,
                    ip_address=self._optional_string(raw_row.get("deviceIP")),
                )
                activity["conn"] = cast(int, activity["conn"]) + (
                    self._optional_int(raw_row.get("count")) or 0
                )

        for metric_key in ("download", "upload"):
            raw_rankings = self._resolve_network_ranking_payload(
                raw_flows.get(metric_key)
            )
            if not isinstance(raw_rankings, list):
                continue
            for raw_row in raw_rankings:
                if not isinstance(raw_row, Mapping):
                    continue
                host_id = (
                    self._optional_string(raw_row.get("device"))
                    or self._optional_string(raw_row.get("mac"))
                    or self._optional_string(raw_row.get("deviceMac"))
                )
                if host_id is None:
                    continue
                activity = ensure_activity_host(
                    host_id,
                    ip_address=self._optional_string(raw_row.get("deviceIP")),
                )
                ranking_value = (
                    self._optional_int(raw_row.get(metric_key))
                    or self._optional_int(raw_row.get("bytes"))
                    or self._optional_int(raw_row.get("count"))
                    or 0
                )
                current_value = cast(int, activity[f"{metric_key}_bytes"])
                if ranking_value > current_value:
                    activity[f"{metric_key}_bytes"] = ranking_value

        hosts = [
            FirewallaNetworkHostTotals(
                host_id=host_id,
                host_name=cast(str | None, values["host_name"]),
                ip_address=cast(str | None, values["ip_address"]),
                conn=cast(int, values["conn"]),
                download_bytes=cast(int, values["download_bytes"]),
                upload_bytes=cast(int, values["upload_bytes"]),
            )
            for host_id, values in activity_by_host.items()
            if cast(int, values["conn"]) > 0
            or cast(int, values["download_bytes"]) > 0
            or cast(int, values["upload_bytes"]) > 0
        ]

        return tuple(
            sorted(
                hosts,
                key=lambda host: (
                    -((host.download_bytes or 0) + (host.upload_bytes or 0)),
                    -(host.conn or 0),
                    host.host_name.casefold() if host.host_name else "",
                    host.host_id,
                ),
            )
        )

    def _build_network_usage_buckets(
        self,
        raw_buckets: object,
    ) -> tuple[FirewallaNetworkUsageBucket, ...]:
        """Build aggregated app or category activity buckets."""
        if not isinstance(raw_buckets, Mapping):
            return ()

        buckets: list[FirewallaNetworkUsageBucket] = []
        for key, raw_rows in raw_buckets.items():
            if not isinstance(key, str) or not key or not isinstance(raw_rows, list):
                continue

            download_bytes = 0
            upload_bytes = 0
            duration_seconds = 0.0
            session_count = 0
            latest_timestamp: int | None = None
            active_devices: set[str] = set()

            for raw_row in raw_rows:
                if not isinstance(raw_row, Mapping):
                    continue
                session_count += 1
                download_bytes += self._optional_int(raw_row.get("download")) or 0
                upload_bytes += self._optional_int(raw_row.get("upload")) or 0
                duration_value = raw_row.get("duration")
                if isinstance(duration_value, (int, float)):
                    duration_seconds += float(duration_value)
                if device_id := (
                    self._optional_string(raw_row.get("device"))
                    or self._optional_string(raw_row.get("mac"))
                    or self._optional_string(raw_row.get("deviceMac"))
                ):
                    active_devices.add(device_id)
                timestamp = self._optional_int(raw_row.get("ts"))
                if timestamp is not None and (
                    latest_timestamp is None or timestamp > latest_timestamp
                ):
                    latest_timestamp = timestamp

            if session_count == 0:
                continue

            buckets.append(
                FirewallaNetworkUsageBucket(
                    key=key,
                    download_bytes=download_bytes,
                    upload_bytes=upload_bytes,
                    duration_seconds=duration_seconds,
                    session_count=session_count,
                    active_device_count=len(active_devices),
                    latest_timestamp=latest_timestamp,
                )
            )

        return tuple(
            sorted(
                buckets,
                key=lambda bucket: (
                    -(bucket.download_bytes + bucket.upload_bytes),
                    -bucket.session_count,
                    bucket.key,
                ),
            )
        )

    def _build_network_flow_rankings(
        self,
        raw_rankings: object,
        *,
        host_lookup: dict[str, FirewallaHostRuntime],
        metric_key: str,
    ) -> tuple[FirewallaNetworkHostRanking, ...]:
        """Build ranked traffic summaries from one raw flows ranking list."""
        if not isinstance(raw_rankings, list):
            return ()

        rankings: list[FirewallaNetworkHostRanking] = []
        for raw_ranking in raw_rankings:
            if not isinstance(raw_ranking, Mapping):
                continue

            host_id = (
                self._optional_string(raw_ranking.get("device"))
                or self._optional_string(raw_ranking.get("mac"))
                or self._optional_string(raw_ranking.get("deviceMac"))
            )
            if host_id is None:
                continue

            value = (
                self._optional_int(raw_ranking.get(metric_key))
                or self._optional_int(raw_ranking.get("bytes"))
                or self._optional_int(raw_ranking.get("count"))
            )
            if value is None:
                continue

            host = host_lookup.get(host_id)
            rankings.append(
                FirewallaNetworkHostRanking(
                    host_id=host_id,
                    host_name=host.display_name if host is not None else None,
                    ip_address=(
                        host.ip_address
                        if host is not None
                        else self._optional_string(raw_ranking.get("deviceIP"))
                    ),
                    remote_host=(
                        self._optional_string(raw_ranking.get("host"))
                        or self._optional_string(raw_ranking.get("domain"))
                    ),
                    remote_ip=self._optional_string(raw_ranking.get("ip")),
                    value=value,
                )
            )

        return tuple(
            sorted(
                rankings,
                key=lambda ranking: (
                    -ranking.value,
                    ranking.host_name or "",
                    ranking.host_id,
                ),
            )
        )

    def _resolve_network_ranking_payload(self, value: object) -> object:
        """Resolve one ranking payload to the list of ranking rows when possible."""
        if isinstance(value, list):
            return value
        if not isinstance(value, Mapping):
            return value

        if isinstance(nested_flows := value.get("flows"), list):
            return nested_flows

        for key in ("download", "upload", "items", "results"):
            nested_value = value.get(key)
            if isinstance(nested_value, list):
                return nested_value

        return value

    def _build_network_metric_series(
        self,
        raw_window: object,
    ) -> tuple[FirewallaNetworkMetricSeries, ...]:
        """Normalize one network summary window keyed by metric name."""
        if not isinstance(raw_window, Mapping):
            return ()

        series_collection: list[FirewallaNetworkMetricSeries] = []
        for metric, raw_samples in raw_window.items():
            if not isinstance(metric, str) or not metric:
                continue
            if not isinstance(raw_samples, list):
                continue

            samples: list[FirewallaNetworkMetricSample] = []
            for raw_sample in raw_samples:
                if (
                    not isinstance(raw_sample, list)
                    or len(raw_sample) != 2
                    or (timestamp := self._optional_int(raw_sample[0])) is None
                ):
                    continue

                value = raw_sample[1]
                if not isinstance(value, (int, float)):
                    continue

                samples.append(
                    FirewallaNetworkMetricSample(
                        timestamp=timestamp,
                        value=value,
                    )
                )

            series_collection.append(
                FirewallaNetworkMetricSeries(
                    metric=metric,
                    samples=tuple(samples),
                )
            )

        return tuple(sorted(series_collection, key=lambda series: series.metric))

    def _optional_string(self, value: object) -> str | None:
        """Return a stripped string when one is present."""
        if not isinstance(value, str):
            return None
        stripped_value = value.strip()
        return stripped_value or None

    def _optional_bool(self, value: object) -> bool | None:
        """Return a normalized boolean when one is present."""
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        return None

    def _optional_int(self, value: object) -> int | None:
        """Return an integer when one can be safely derived."""
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value:
            try:
                return int(value)
            except ValueError:
                return None
        return None

    def _string_tuple(self, value: object) -> tuple[str, ...]:
        """Return a stable tuple of non-empty strings."""
        if isinstance(value, str):
            return (value,) if value else ()
        if isinstance(value, list):
            return tuple(item for item in value if isinstance(item, str) and item)
        return ()

    def _combine_string_values(self, *values: object) -> tuple[str, ...]:
        """Combine one or more string or list-like string sources."""
        combined: list[str] = []
        seen: set[str] = set()
        for value in values:
            for item in self._string_tuple(value):
                if item in seen:
                    continue
                seen.add(item)
                combined.append(item)
        return tuple(combined)

    def _normalized_dict(self, value: object) -> dict[str, object] | None:
        """Return a shallow normalized dictionary when one is present."""
        if not isinstance(value, Mapping):
            return None

        normalized: dict[str, object] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                continue
            if not isinstance(nested_value, (str, bool, int, float, dict, list)):
                continue
            normalized[key] = nested_value

        return normalized or None

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

    def _build_current_wan_usage_summaries(
        self,
        raw_usage: object,
        *,
        wan_uuid: str | None = None,
    ) -> tuple[FirewallaWanUsageSummary, ...]:
        """Build compact current WAN usage summaries from raw payload data."""
        if not isinstance(raw_usage, dict):
            return ()

        wan_name_by_uuid = {wan.uuid: wan.name for wan in self.get_available_wans()}
        summaries: list[FirewallaWanUsageSummary] = []
        for raw_wan_uuid, raw_period in raw_usage.items():
            if not isinstance(raw_wan_uuid, str) or not raw_wan_uuid:
                continue
            if wan_uuid is not None and raw_wan_uuid != wan_uuid:
                continue
            if not isinstance(raw_period, dict):
                continue

            summaries.append(
                FirewallaWanUsageSummary(
                    wan_uuid=raw_wan_uuid,
                    wan_name=wan_name_by_uuid.get(raw_wan_uuid, raw_wan_uuid),
                    download_bytes=self._normalized_int(
                        raw_period.get("totalDownload")
                    ),
                    upload_bytes=self._normalized_int(raw_period.get("totalUpload")),
                )
            )

        return tuple(
            sorted(
                summaries,
                key=lambda summary: (
                    (summary.wan_name or "").casefold(),
                    summary.wan_uuid,
                ),
            )
        )

    def _build_current_wan_data_usage_rows(
        self,
        raw_usage: object,
        *,
        wan_uuid: str | None,
        detail: str,
        time_zone: tzinfo,
    ) -> tuple[
        dict[str, FirewallaWanDataUsageRow],
        dict[str, tuple[FirewallaWanDataUsageRow, ...]],
    ]:
        """Build current-month WAN data-usage rows from raw payload data."""
        if not isinstance(raw_usage, dict):
            return {}, {}

        rows: dict[str, FirewallaWanDataUsageRow] = {}
        day_rows_by_wan: dict[str, tuple[FirewallaWanDataUsageRow, ...]] = {}
        for raw_wan_uuid, raw_period in raw_usage.items():
            if not isinstance(raw_wan_uuid, str) or not raw_wan_uuid:
                continue
            if wan_uuid is not None and raw_wan_uuid != wan_uuid:
                continue
            if not isinstance(raw_period, dict):
                continue

            if (
                result := self._build_current_month_wan_data_usage_row(
                    raw_period,
                    detail=detail,
                    time_zone=time_zone,
                )
            ) is None:
                continue
            row, day_rows = result
            rows[raw_wan_uuid] = row
            day_rows_by_wan[raw_wan_uuid] = day_rows

        return rows, day_rows_by_wan

    def _build_history_wan_data_usage_rows(
        self,
        raw_usage: object,
        *,
        wan_uuid: str | None,
        history_count: int,
        history_period: str | None,
        detail: str,
        time_zone: tzinfo,
    ) -> tuple[
        dict[str, tuple[FirewallaWanDataUsageRow, ...]],
        dict[str, tuple[FirewallaWanDataUsageRow, ...]],
    ]:
        """Build trailing monthly WAN data-usage rows from raw payload data."""
        if not isinstance(raw_usage, dict):
            return {}, {}

        rows_by_wan: dict[str, tuple[FirewallaWanDataUsageRow, ...]] = {}
        day_rows_by_wan: dict[str, tuple[FirewallaWanDataUsageRow, ...]] = {}
        for raw_wan_uuid, raw_periods in raw_usage.items():
            if not isinstance(raw_wan_uuid, str) or not raw_wan_uuid:
                continue
            if wan_uuid is not None and raw_wan_uuid != wan_uuid:
                continue
            if not isinstance(raw_periods, list):
                continue

            month_results = [
                result
                for raw_period in raw_periods
                if isinstance(raw_period, dict)
                and (
                    result := self._build_history_month_wan_data_usage_row(
                        raw_period,
                        detail=detail,
                        time_zone=time_zone,
                    )
                )
                is not None
            ]
            sorted_results = tuple(
                sorted(
                    month_results,
                    key=lambda result: result[0].time_period.anchor_timestamp or 0,
                    reverse=True,
                )
            )

            if history_period == "month" and history_count > 0:
                sorted_results = sorted_results[:history_count]

            rows = tuple(result[0] for result in sorted_results)
            day_rows = tuple(
                day_row for result in sorted_results for day_row in result[1]
            )
            if rows:
                rows_by_wan[raw_wan_uuid] = rows
            if day_rows:
                day_rows_by_wan[raw_wan_uuid] = day_rows

        return rows_by_wan, day_rows_by_wan

    def _build_current_month_wan_data_usage_row(
        self,
        raw_stats: dict[str, object],
        *,
        detail: str,
        time_zone: tzinfo,
    ) -> tuple[FirewallaWanDataUsageRow, tuple[FirewallaWanDataUsageRow, ...]] | None:
        """Build one current-month WAN data-usage row."""
        usage = self._build_wan_data_usage(raw_stats)
        if usage is None:
            return None

        month_begin_timestamp = self._normalized_int(raw_stats.get("monthlyBeginTs"))
        month_end_timestamp = self._normalized_int(raw_stats.get("monthlyEndTs"))
        all_day_rows = self._build_daily_wan_data_usage_rows(
            raw_stats,
            month_begin_timestamp=month_begin_timestamp,
            is_current=True,
            time_zone=time_zone,
        )
        week_rows = (
            self._build_week_rows(
                all_day_rows,
                detail=detail,
                is_current=True,
                time_zone=time_zone,
            )
            if detail == "weekly"
            else ()
        )
        day_rows = all_day_rows if detail == "daily" else ()

        return (
            FirewallaWanDataUsageRow(
                time_period=FirewallaWanDataUsagePeriod(
                    kind="month",
                    begin_timestamp=month_begin_timestamp,
                    end_timestamp=month_end_timestamp,
                    anchor_timestamp=month_begin_timestamp,
                    is_partial=True,
                    boundary_source="firewalla_explicit_bounds",
                ),
                usage=usage,
                detail=detail if week_rows or day_rows else "summary",
                weeks=week_rows,
                days=day_rows,
            ),
            all_day_rows,
        )

    def _build_history_month_wan_data_usage_row(
        self,
        raw_period: dict[str, object],
        *,
        detail: str,
        time_zone: tzinfo,
    ) -> tuple[FirewallaWanDataUsageRow, tuple[FirewallaWanDataUsageRow, ...]] | None:
        """Build one historical monthly WAN data-usage row."""
        raw_stats = raw_period.get("stats")
        if not isinstance(raw_stats, dict):
            return None

        usage = self._build_wan_data_usage(raw_stats)
        if usage is None:
            return None

        month_anchor_timestamp = self._normalized_int(raw_period.get("ts"))
        all_day_rows = self._build_daily_wan_data_usage_rows(
            raw_stats,
            month_begin_timestamp=month_anchor_timestamp,
            is_current=False,
            time_zone=time_zone,
        )
        week_rows = (
            self._build_week_rows(
                all_day_rows,
                detail=detail,
                is_current=False,
                time_zone=time_zone,
            )
            if detail == "weekly"
            else ()
        )
        day_rows = all_day_rows if detail == "daily" else ()
        begin_timestamp, end_timestamp = self._derive_month_bounds(
            month_anchor_timestamp,
            time_zone=time_zone,
        )

        return (
            FirewallaWanDataUsageRow(
                time_period=FirewallaWanDataUsagePeriod(
                    kind="month",
                    begin_timestamp=begin_timestamp,
                    end_timestamp=end_timestamp,
                    anchor_timestamp=month_anchor_timestamp,
                    is_partial=False,
                    boundary_source="firewalla_month_bucket",
                ),
                usage=usage,
                detail=detail if week_rows or day_rows else "summary",
                weeks=week_rows,
                days=day_rows,
            ),
            all_day_rows,
        )

    def _build_daily_wan_data_usage_rows(
        self,
        raw_stats: dict[str, object],
        *,
        month_begin_timestamp: int | None,
        is_current: bool,
        time_zone: tzinfo,
    ) -> tuple[FirewallaWanDataUsageRow, ...]:
        """Build daily WAN data-usage rows from monthly samples."""
        if month_begin_timestamp is None:
            return ()

        download_by_timestamp = {
            sample.timestamp: sample.value
            for sample in self._build_wan_usage_samples(raw_stats.get("download"))
        }
        upload_by_timestamp = {
            sample.timestamp: sample.value
            for sample in self._build_wan_usage_samples(raw_stats.get("upload"))
        }
        ordered_sample_timestamps = sorted(
            set(download_by_timestamp) | set(upload_by_timestamp)
        )
        if not ordered_sample_timestamps:
            return ()

        month_start_local = self._local_datetime(month_begin_timestamp, time_zone)

        rows: list[FirewallaWanDataUsageRow] = []
        for day_index, sample_timestamp in enumerate(ordered_sample_timestamps):
            day_begin_local = month_start_local + timedelta(days=day_index)
            day_end_local = day_begin_local + timedelta(days=1)
            begin_timestamp = int(day_begin_local.astimezone(UTC).timestamp())
            end_timestamp = int(day_end_local.astimezone(UTC).timestamp())
            rows.append(
                FirewallaWanDataUsageRow(
                    time_period=FirewallaWanDataUsagePeriod(
                        kind="day",
                        begin_timestamp=begin_timestamp,
                        end_timestamp=end_timestamp,
                        anchor_timestamp=begin_timestamp,
                        is_partial=(
                            is_current
                            and day_index == len(ordered_sample_timestamps) - 1
                        ),
                        boundary_source="derived_local_day_from_firewalla_samples",
                    ),
                    usage=FirewallaWanDataUsage(
                        download_bytes=download_by_timestamp.get(sample_timestamp),
                        upload_bytes=upload_by_timestamp.get(sample_timestamp),
                    ),
                )
            )

        return tuple(reversed(rows))

    def _build_current_day_row(
        self,
        day_rows: tuple[FirewallaWanDataUsageRow, ...],
    ) -> FirewallaWanDataUsageRow | None:
        """Return the latest current-day row when one is available."""
        return day_rows[0] if day_rows else None

    def _build_current_week_row(
        self,
        day_rows: tuple[FirewallaWanDataUsageRow, ...],
        *,
        detail: str,
        time_zone: tzinfo,
    ) -> FirewallaWanDataUsageRow | None:
        """Return the latest current-week row when one is available."""
        week_rows = self._build_week_rows(
            day_rows,
            detail=detail,
            is_current=True,
            time_zone=time_zone,
        )
        return week_rows[0] if week_rows else None

    def _build_history_day_rows(
        self,
        day_rows: tuple[FirewallaWanDataUsageRow, ...],
        *,
        history_count: int,
    ) -> tuple[FirewallaWanDataUsageRow, ...]:
        """Return the requested trailing historical day rows."""
        return day_rows[:history_count] if history_count > 0 else ()

    def _build_history_week_rows(
        self,
        day_rows: tuple[FirewallaWanDataUsageRow, ...],
        *,
        history_count: int,
        detail: str,
        time_zone: tzinfo,
    ) -> tuple[FirewallaWanDataUsageRow, ...]:
        """Return the requested trailing historical week rows."""
        week_rows = self._build_week_rows(
            day_rows,
            detail=detail,
            is_current=False,
            time_zone=time_zone,
        )
        return week_rows[:history_count] if history_count > 0 else ()

    def _build_week_rows(
        self,
        day_rows: tuple[FirewallaWanDataUsageRow, ...],
        *,
        detail: str,
        is_current: bool,
        time_zone: tzinfo,
    ) -> tuple[FirewallaWanDataUsageRow, ...]:
        """Build week rows from day rows using a configurable local week start."""
        if not day_rows:
            return ()

        grouped_days: dict[datetime, list[FirewallaWanDataUsageRow]] = {}
        for day_row in sorted(
            day_rows,
            key=lambda row: row.time_period.begin_timestamp or 0,
        ):
            begin_timestamp = day_row.time_period.begin_timestamp
            if begin_timestamp is None:
                continue
            day_begin_local = self._local_datetime(begin_timestamp, time_zone)
            week_start_date = day_begin_local.date() - timedelta(
                days=(day_begin_local.weekday() - _WEEK_START_MONDAY) % 7
            )
            week_start_local = datetime.combine(
                week_start_date,
                time.min,
                tzinfo=time_zone,
            )
            grouped_days.setdefault(week_start_local, []).append(day_row)

        week_rows: list[FirewallaWanDataUsageRow] = []
        latest_week_start = max(grouped_days) if grouped_days else None
        for week_start_local, grouped_row_days in grouped_days.items():
            if not grouped_row_days:
                continue
            if not is_current and len(grouped_row_days) < 7:
                continue

            week_end_local = week_start_local + timedelta(days=7)
            begin_timestamp = int(week_start_local.astimezone(UTC).timestamp())
            end_timestamp = int(week_end_local.astimezone(UTC).timestamp())
            week_rows.append(
                FirewallaWanDataUsageRow(
                    time_period=FirewallaWanDataUsagePeriod(
                        kind="week",
                        begin_timestamp=begin_timestamp,
                        end_timestamp=end_timestamp,
                        anchor_timestamp=begin_timestamp,
                        is_partial=is_current and week_start_local == latest_week_start,
                        boundary_source="derived_local_week_monday_start",
                    ),
                    usage=FirewallaWanDataUsage(
                        download_bytes=sum(
                            day_row.usage.download_bytes or 0
                            for day_row in grouped_row_days
                        ),
                        upload_bytes=sum(
                            day_row.usage.upload_bytes or 0
                            for day_row in grouped_row_days
                        ),
                    ),
                    detail="daily" if detail == "daily" else "summary",
                    days=(tuple(grouped_row_days) if detail == "daily" else ()),
                )
            )

        return tuple(
            sorted(
                week_rows,
                key=lambda row: row.time_period.begin_timestamp or 0,
                reverse=True,
            )
        )

    def _derive_month_bounds(
        self,
        month_begin_timestamp: int | None,
        *,
        time_zone: tzinfo,
    ) -> tuple[int | None, int | None]:
        """Derive one local month window from its local start timestamp."""
        if month_begin_timestamp is None:
            return None, None

        month_start_local = self._local_datetime(month_begin_timestamp, time_zone)
        next_month_local = self._next_month_start(month_start_local)
        return (
            int(month_start_local.astimezone(UTC).timestamp()),
            int(next_month_local.astimezone(UTC).timestamp()),
        )

    @staticmethod
    def _next_month_start(current_month_start: datetime) -> datetime:
        """Return the next local calendar month start."""
        if current_month_start.month == 12:
            return current_month_start.replace(
                year=current_month_start.year + 1,
                month=1,
                day=1,
            )
        return current_month_start.replace(month=current_month_start.month + 1, day=1)

    @staticmethod
    def _local_datetime(timestamp: int, time_zone: tzinfo) -> datetime:
        """Return one timestamp converted into the requested local timezone."""
        return datetime.fromtimestamp(timestamp, UTC).astimezone(time_zone)

    def _build_wan_data_usage(
        self,
        raw_stats: object,
    ) -> FirewallaWanDataUsage | None:
        """Build normalized WAN data-usage totals from raw stats."""
        if not isinstance(raw_stats, dict):
            return None

        return FirewallaWanDataUsage(
            download_bytes=self._normalized_int(raw_stats.get("totalDownload")),
            upload_bytes=self._normalized_int(raw_stats.get("totalUpload")),
        )

    def _build_wan_usage_samples(
        self,
        raw_samples: object,
    ) -> tuple[FirewallaWanDataUsageSample, ...]:
        """Build normalized WAN data-usage samples from a raw list payload."""
        if not isinstance(raw_samples, list):
            return ()

        samples: list[FirewallaWanDataUsageSample] = []
        for raw_sample in raw_samples:
            if not isinstance(raw_sample, list) or len(raw_sample) < 2:
                continue
            timestamp = self._normalized_int(raw_sample[0])
            value = self._normalized_int(raw_sample[1])
            if timestamp is None or value is None:
                continue
            samples.append(
                FirewallaWanDataUsageSample(
                    timestamp=timestamp,
                    value=value,
                )
            )

        return tuple(samples)

    def _build_wan_events(
        self,
        raw_events: object,
        *,
        wan_uuid: str | None,
    ) -> tuple[FirewallaWanEvent, ...]:
        """Build normalized WAN events from one raw list payload."""
        if not isinstance(raw_events, list):
            return ()

        events: list[FirewallaWanEvent] = []
        for raw_event in raw_events:
            if not isinstance(raw_event, dict):
                continue
            if (event := self._build_wan_event(raw_event)) is None:
                continue
            if wan_uuid is not None and not self._wan_event_matches_wan(
                event,
                wan_uuid,
            ):
                continue
            events.append(event)

        return tuple(events)

    def _build_wan_event(
        self,
        raw_event: dict[str, object],
    ) -> FirewallaWanEvent | None:
        """Build one normalized WAN event from one raw record."""
        event_type = raw_event.get("event_type")
        if not isinstance(event_type, str) or not event_type:
            return None

        timestamp_ms = self._normalized_int(raw_event.get("ts"))
        if timestamp_ms is None:
            return None
        timestamp = timestamp_ms / 1000

        raw_labels = raw_event.get("labels")
        labels = raw_labels if isinstance(raw_labels, dict) else {}

        if event_type == "state":
            family = raw_event.get("state_type")
            if not isinstance(family, str) or (
                family not in _SUPPORTED_WAN_EVENT_STATE_FAMILIES
            ):
                return None

            wan_statuses = self._build_wan_event_statuses(labels.get("wanStatus"))
            changed_interface = self._normalized_string(labels.get("changedInterface"))
            wan_uuid, wan_name = self._resolve_wan_event_identity(
                labels=labels,
                wan_statuses=wan_statuses,
                interface_key=changed_interface,
            )
            return FirewallaWanEvent(
                family=family,
                event_type=event_type,
                timestamp=timestamp,
                value=self._normalized_number(raw_event.get("state_value")),
                previous_value=self._normalized_number(
                    raw_event.get("prev_state_value")
                ),
                ok_value=self._normalized_number(labels.get("ok_value")),
                state_key=self._normalized_string(raw_event.get("state_key")),
                wan_uuid=wan_uuid,
                wan_name=wan_name,
                active=self._normalized_bool(labels.get("active")),
                ready=self._normalized_bool(labels.get("ready")),
                changed_interface=changed_interface,
                primary_interface=self._normalized_string(
                    labels.get("primaryInterface")
                ),
                wan_type=self._normalized_string(labels.get("wanType")),
                wan_switched=self._normalized_bool(labels.get("wanSwitched")),
                name_server=self._normalized_string(labels.get("name_server")),
                dns_test_domain=self._normalized_string(labels.get("dns_test_domain")),
                wan_interface_address=self._normalized_string(
                    labels.get("wan_intf_address")
                ),
                failures=self._build_wan_event_failures(labels.get("failures")),
                wan_statuses=wan_statuses,
            )

        if event_type == "action":
            family = raw_event.get("action_type")
            if not isinstance(family, str) or (
                family not in _SUPPORTED_WAN_EVENT_ACTION_FAMILIES
            ):
                return None

            measurement_kind = "rtt" if family == "ping_RTT" else "lossrate"
            return FirewallaWanEvent(
                family=family,
                event_type=event_type,
                timestamp=timestamp,
                value=self._normalized_number(raw_event.get("action_value")),
                wan_uuid=self._normalized_string(
                    labels.get(_RAW_WAN_INTERFACE_UUID_KEY)
                ),
                wan_name=self._normalized_string(
                    labels.get(_RAW_WAN_INTERFACE_NAME_KEY)
                ),
                target=self._normalized_string(labels.get("target")),
                measurement_kind=measurement_kind,
                measurement_value=self._normalized_float(labels.get(measurement_kind)),
                threshold_value=self._normalized_float(
                    labels.get(f"{measurement_kind}Limit")
                ),
            )

        return None

    def _build_wan_event_failures(
        self,
        raw_failures: object,
    ) -> tuple[FirewallaWanEventFailure, ...]:
        """Build normalized WAN event failures from a raw list payload."""
        if not isinstance(raw_failures, list):
            return ()

        failures: list[FirewallaWanEventFailure] = []
        for raw_failure in raw_failures:
            if not isinstance(raw_failure, dict):
                continue
            failure_type = self._normalized_string(raw_failure.get("type"))
            if failure_type is None:
                continue
            failures.append(
                FirewallaWanEventFailure(
                    type=failure_type,
                    target=self._normalized_string(raw_failure.get("target")),
                )
            )

        return tuple(failures)

    def _build_wan_event_statuses(
        self,
        raw_statuses: object,
    ) -> tuple[FirewallaWanEventStatus, ...]:
        """Build normalized WAN interface statuses from a raw mapping."""
        if not isinstance(raw_statuses, dict):
            return ()

        statuses: list[FirewallaWanEventStatus] = []
        for interface_key, raw_status in raw_statuses.items():
            if not isinstance(interface_key, str) or not interface_key:
                continue
            if not isinstance(raw_status, dict):
                continue
            statuses.append(
                FirewallaWanEventStatus(
                    interface_key=interface_key,
                    wan_uuid=self._normalized_string(
                        raw_status.get(_RAW_WAN_INTERFACE_UUID_KEY)
                    ),
                    wan_name=self._normalized_string(
                        raw_status.get(_RAW_WAN_INTERFACE_NAME_KEY)
                    ),
                    active=self._normalized_bool(raw_status.get("active")),
                    ready=self._normalized_bool(raw_status.get("ready")),
                    ip4_addresses=self._normalized_string_list(raw_status.get("ip4s")),
                    seq=self._normalized_int(raw_status.get("seq")),
                )
            )

        return tuple(
            sorted(statuses, key=lambda status: status.interface_key.casefold())
        )

    def _resolve_wan_event_identity(
        self,
        *,
        labels: dict[str, object],
        wan_statuses: tuple[FirewallaWanEventStatus, ...],
        interface_key: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve the primary WAN identity for one event when Firewalla exposes one."""
        wan_uuid = self._normalized_string(labels.get(_RAW_WAN_INTERFACE_UUID_KEY))
        wan_name = self._normalized_string(labels.get(_RAW_WAN_INTERFACE_NAME_KEY))
        if wan_uuid is not None or wan_name is not None:
            return wan_uuid, wan_name

        if interface_key is not None:
            matched_status = next(
                (
                    status
                    for status in wan_statuses
                    if status.interface_key == interface_key
                ),
                None,
            )
            if matched_status is not None:
                return matched_status.wan_uuid, matched_status.wan_name

        if len(wan_statuses) == 1:
            return wan_statuses[0].wan_uuid, wan_statuses[0].wan_name

        return None, None

    def _wan_event_matches_wan(
        self,
        event: FirewallaWanEvent,
        wan_uuid: str,
    ) -> bool:
        """Return whether one normalized event applies to the selected WAN."""
        return event.wan_uuid == wan_uuid or any(
            status.wan_uuid == wan_uuid for status in event.wan_statuses
        )

    def _build_usage_history_view(
        self,
        raw_payload: object,
        *,
        target: FirewallaUsageHistoryTarget,
        begin_timestamp: int,
        end_timestamp: int,
        granularity: str,
        include_intervals: bool,
        app_ids: tuple[str, ...] | None,
    ) -> FirewallaUsageHistoryView:
        """Build one normalized usage-history response from raw payload data."""
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        return FirewallaUsageHistoryView(
            target=target,
            begin_timestamp=begin_timestamp,
            end_timestamp=end_timestamp,
            granularity=granularity,
            app_ids=app_ids,
            internet=self._build_usage_history_metric(
                payload.get("internetTimeUsage"),
                include_intervals=include_intervals,
            ),
            app_totals=self._build_usage_history_metric(
                payload.get("appTimeUsageTotal"),
                include_intervals=include_intervals,
            ),
            apps=self._build_usage_history_entries(
                payload.get("appTimeUsage"),
                include_intervals=include_intervals,
            ),
            categories=self._build_usage_history_entries(
                payload.get("categoryTimeUsage"),
                include_intervals=include_intervals,
            ),
        )

    def _build_usage_history_entries(
        self,
        raw_entries: object,
        *,
        include_intervals: bool,
    ) -> tuple[FirewallaUsageHistoryEntry, ...]:
        """Build normalized usage-history entries from a raw keyed section."""
        if not isinstance(raw_entries, dict):
            return ()

        entries: list[FirewallaUsageHistoryEntry] = []
        for key, raw_entry in raw_entries.items():
            if not isinstance(key, str) or not key or not isinstance(raw_entry, dict):
                continue
            if (
                metric := self._build_usage_history_metric(
                    raw_entry,
                    include_intervals=include_intervals,
                )
            ) is None:
                continue
            entries.append(
                FirewallaUsageHistoryEntry(
                    key=key,
                    metric=metric,
                )
            )

        return tuple(sorted(entries, key=lambda entry: entry.key.casefold()))

    def _build_usage_history_metric(
        self,
        raw_metric: object,
        *,
        include_intervals: bool,
    ) -> FirewallaUsageHistoryMetric | None:
        """Build one normalized usage-history metric from raw payload data."""
        if not isinstance(raw_metric, dict):
            return None

        return FirewallaUsageHistoryMetric(
            category=(
                category
                if isinstance((category := raw_metric.get("category")), str)
                and category
                else None
            ),
            total_minutes=self._normalized_int(raw_metric.get("totalMins")),
            unique_minutes=self._normalized_int(raw_metric.get("uniqueMins")),
            slots=self._build_usage_history_slots(raw_metric.get("slots")),
            intervals=(
                self._build_usage_history_intervals(raw_metric.get("intervals"))
                if include_intervals
                else ()
            ),
            devices=self._build_usage_history_devices(
                raw_metric.get("devices"),
                include_intervals=include_intervals,
            ),
        )

    def _build_usage_history_slots(
        self, raw_slots: object
    ) -> tuple[FirewallaUsageHistorySlot, ...]:
        """Build normalized usage-history slots from a raw slot mapping."""
        if not isinstance(raw_slots, dict):
            return ()

        slots: list[FirewallaUsageHistorySlot] = []
        for raw_timestamp, raw_slot in raw_slots.items():
            timestamp = self._normalized_int(raw_timestamp)
            if timestamp is None or not isinstance(raw_slot, dict):
                continue
            slots.append(
                FirewallaUsageHistorySlot(
                    timestamp=timestamp,
                    total_minutes=self._normalized_int(raw_slot.get("totalMins")),
                    unique_minutes=self._normalized_int(raw_slot.get("uniqueMins")),
                )
            )

        return tuple(sorted(slots, key=lambda slot: slot.timestamp))

    def _build_usage_history_intervals(
        self, raw_intervals: object
    ) -> tuple[FirewallaUsageHistoryInterval, ...]:
        """Build normalized usage-history intervals from a raw list payload."""
        if not isinstance(raw_intervals, list):
            return ()

        intervals: list[FirewallaUsageHistoryInterval] = []
        for raw_interval in raw_intervals:
            if not isinstance(raw_interval, dict):
                continue
            begin_timestamp = self._normalized_int(raw_interval.get("begin"))
            end_timestamp = self._normalized_int(raw_interval.get("end"))
            if begin_timestamp is None or end_timestamp is None:
                continue
            intervals.append(
                FirewallaUsageHistoryInterval(
                    begin_timestamp=begin_timestamp,
                    end_timestamp=end_timestamp,
                )
            )

        return tuple(
            sorted(
                intervals,
                key=lambda interval: (
                    interval.begin_timestamp,
                    interval.end_timestamp,
                ),
            )
        )

    def _build_usage_history_devices(
        self,
        raw_devices: object,
        *,
        include_intervals: bool,
    ) -> tuple[FirewallaUsageHistoryDeviceUsage, ...]:
        """Build normalized device interval breakdowns from a raw mapping."""
        if not isinstance(raw_devices, dict):
            return ()

        host_name_by_id = (
            {host.mac: host.display_name for host in self.coordinator.data.hosts}
            if self.coordinator.data is not None
            else {}
        )
        devices: list[FirewallaUsageHistoryDeviceUsage] = []
        for device_id, raw_device in raw_devices.items():
            if not isinstance(device_id, str) or not device_id:
                continue
            if not isinstance(raw_device, dict):
                continue
            devices.append(
                FirewallaUsageHistoryDeviceUsage(
                    device_id=device_id,
                    device_name=host_name_by_id.get(device_id),
                    total_minutes=self._normalized_int(raw_device.get("totalMins")),
                    unique_minutes=self._normalized_int(raw_device.get("uniqueMins")),
                    intervals=(
                        self._build_usage_history_intervals(raw_device.get("intervals"))
                        if include_intervals
                        else ()
                    ),
                )
            )

        return tuple(sorted(devices, key=lambda device: device.device_id.casefold()))

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

    def _normalized_float(self, value: object) -> float | None:
        """Return a floating-point number from a Firewalla numeric field."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return None
            try:
                return float(stripped_value)
            except ValueError:
                return None
        return None

    def _normalized_number(self, value: object) -> int | float | None:
        """Return an integer or float from a Firewalla numeric field."""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return value
        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return None
            try:
                return int(stripped_value)
            except ValueError:
                try:
                    return float(stripped_value)
                except ValueError:
                    return None
        return None

    def _normalized_bool(self, value: object) -> bool | None:
        """Return a normalized boolean from a Firewalla field when possible."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            stripped_value = value.strip().casefold()
            if stripped_value == "true":
                return True
            if stripped_value == "false":
                return False
        return None

    def _normalized_string(self, value: object) -> str | None:
        """Return a non-empty stripped string when one is present."""
        if not isinstance(value, str):
            return None
        stripped_value = value.strip()
        return stripped_value or None

    def _normalized_string_list(self, value: object) -> tuple[str, ...]:
        """Return a stable tuple of non-empty strings from one raw list."""
        if not isinstance(value, list):
            return ()

        normalized_values = []
        for item in value:
            if not isinstance(item, str):
                continue
            stripped_value = item.strip()
            if not stripped_value:
                continue
            normalized_values.append(stripped_value)

        return tuple(normalized_values)

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
