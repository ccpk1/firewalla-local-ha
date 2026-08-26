"""Binary sensor platform for Firewalla Local system-monitoring surfaces."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_NETWORK_BLOCK_ICMP,
    ATTR_NETWORK_DEVICE_COUNT,
    ATTR_NETWORK_DHCP,
    ATTR_NETWORK_DNS_SERVERS,
    ATTR_NETWORK_ENABLED,
    ATTR_NETWORK_GATEWAY,
    ATTR_NETWORK_IPV4_ADDRESSES,
    ATTR_NETWORK_IPV4_SUBNETS,
    ATTR_NETWORK_IPV6_ADDRESSES,
    ATTR_NETWORK_IPV6_SUBNETS,
    ATTR_NETWORK_KIND,
    ATTR_NETWORK_MDNS_RELAY,
    ATTR_NETWORK_PORTS,
    ATTR_NETWORK_SSDP_RELAY,
    ATTR_NETWORK_USAGE,
    ATTR_NETWORK_VLAN_ID,
    ATTR_SYSTEM_BOOT_COMPLETE,
    ATTR_SYSTEM_BOX_IMAGE_CODENAME,
    ATTR_SYSTEM_BOX_IMAGE_VERSION,
    ATTR_SYSTEM_CLOUD_CONNECTED,
    ATTR_SYSTEM_CPU_USAGE_1M,
    ATTR_SYSTEM_CURRENT_WAN_USAGE,
    ATTR_SYSTEM_DDNS,
    ATTR_SYSTEM_DEVICES_OFFLINE,
    ATTR_SYSTEM_DEVICES_ONLINE,
    ATTR_SYSTEM_DEVICES_TOTAL,
    ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT,
    ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE,
    ATTR_SYSTEM_MEMORY_FREE_MB,
    ATTR_SYSTEM_MEMORY_USAGE_PERCENT,
    ATTR_SYSTEM_PORTS,
    ATTR_SYSTEM_RUNTIME_DATA_UPDATED_AT,
    ATTR_SYSTEM_SOFTWARE_VERSION,
    ATTR_SYSTEM_UPTIME,
    ATTR_SYSTEM_UPTIME_SECONDS,
    ATTR_SYSTEM_WAN_IP,
    ATTR_SYSTEM_WAN_IPS,
    ATTR_WATCHED_DEVICE_CONNECTION_TYPE,
    ATTR_WATCHED_DEVICE_DEVICE_GROUP,
    ATTR_WATCHED_DEVICE_DNS_DOMAIN,
    ATTR_WATCHED_DEVICE_DNS_FQDN,
    ATTR_WATCHED_DEVICE_DNS_HOSTNAME,
    ATTR_WATCHED_DEVICE_DOWNLOAD_USAGE,
    ATTR_WATCHED_DEVICE_HOST_DEVICE_TYPE,
    ATTR_WATCHED_DEVICE_HOST_NAME,
    ATTR_WATCHED_DEVICE_IP_ADDRESS,
    ATTR_WATCHED_DEVICE_LAST_ACTIVE,
    ATTR_WATCHED_DEVICE_NETWORK_NAME,
    ATTR_WATCHED_DEVICE_UPLOAD_USAGE,
    ENTITY_SUFFIX_BINARY_SENSOR,
    TRANS_KEY_ENTITY_BINARY_SENSOR_NETWORK,
    TRANS_KEY_ENTITY_BINARY_SENSOR_SYSTEM_STATUS,
    TRANS_KEY_ENTITY_BINARY_SENSOR_WATCHED_DEVICE,
    TRANS_KEY_PURPOSE_NETWORK,
    TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS,
    TRANS_KEY_PURPOSE_WATCHED_DEVICE_CONNECTIVITY,
    TRANS_PLACEHOLDER_NETWORK_KIND,
    TRANS_PLACEHOLDER_NETWORK_NAME,
)
from .coordinator import FirewallaConfigEntry, get_enabled_network_entities
from .entity import FirewallaEntity
from .models import (
    FirewallaHostRuntime,
    FirewallaNetwork,
    FirewallaNetworkUsageSummary,
    FirewallaWanUsageSummary,
)

PARALLEL_UPDATES = 0

_SYSTEM_STATUS_OBJECT_ID = "system_status"


def _serialize_usage_window(window: object) -> dict[str, int | None]:
    """Serialize one usage window into download/upload byte keys."""
    return {
        "download_bytes": getattr(window, "download_bytes", None),
        "upload_bytes": getattr(window, "upload_bytes", None),
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FirewallaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Firewalla Local binary sensors from a config entry."""
    network_entities = []
    if get_enabled_network_entities(entry.options):
        network_entities = [
            FirewallaNetworkBinarySensor(entry, network.uuid)
            for network in entry.runtime_data.integration_manager.get_networks()
        ]

    async_add_entities(
        [
            FirewallaSystemStatusBinarySensor(entry),
            *network_entities,
            *[
                FirewallaWatchedDeviceBinarySensor(entry, mac)
                for mac in (
                    entry.runtime_data.host_manager.configured_watched_device_macs
                )
            ],
        ]
    )


class FirewallaSystemStatusBinarySensor(FirewallaEntity, BinarySensorEntity):
    """Expose the Firewalla boot-status binary sensor surface."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = TRANS_KEY_ENTITY_BINARY_SENSOR_SYSTEM_STATUS

    def __init__(self, entry: FirewallaConfigEntry) -> None:
        """Initialize the system-status binary sensor."""
        super().__init__(entry, entry.runtime_data.coordinator)
        self._attr_unique_id = self.integration_manager.build_entity_unique_id(
            object_id=_SYSTEM_STATUS_OBJECT_ID,
            suffix=ENTITY_SUFFIX_BINARY_SENSOR,
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether system status data is currently available."""
        return self.system_status is not None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return stable system-status metadata attributes."""
        system_status = self.system_status
        return {
            **self.build_state_attributes(TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS),
            ATTR_SYSTEM_UPTIME: (
                self._format_uptime(system_status.uptime_seconds)
                if system_status is not None
                else None
            ),
            ATTR_SYSTEM_UPTIME_SECONDS: (
                system_status.uptime_seconds if system_status is not None else None
            ),
            ATTR_SYSTEM_BOOT_COMPLETE: (
                system_status.booting_complete if system_status is not None else None
            ),
            ATTR_SYSTEM_BOX_IMAGE_VERSION: (
                system_status.box_image_version if system_status is not None else None
            ),
            ATTR_SYSTEM_SOFTWARE_VERSION: self.system_info.software_version,
            ATTR_SYSTEM_BOX_IMAGE_CODENAME: (
                system_status.box_image_codename if system_status is not None else None
            ),
            ATTR_SYSTEM_CLOUD_CONNECTED: (
                system_status.cloud_connected if system_status is not None else None
            ),
            ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE: (
                system_status.firmware_release_type
                if system_status is not None
                else None
            ),
            ATTR_SYSTEM_DDNS: system_status.ddns if system_status is not None else None,
            ATTR_SYSTEM_WAN_IP: (
                system_status.wan_ip if system_status is not None else None
            ),
            ATTR_SYSTEM_WAN_IPS: (
                system_status.wan_ips if system_status is not None else None
            ),
            ATTR_SYSTEM_CURRENT_WAN_USAGE: self._build_current_wan_usage_attribute(),
            ATTR_SYSTEM_DEVICES_TOTAL: self.host_manager.count_total_devices(),
            ATTR_SYSTEM_DEVICES_ONLINE: self.host_manager.count_online_devices(),
            ATTR_SYSTEM_DEVICES_OFFLINE: self.host_manager.count_offline_devices(),
            ATTR_SYSTEM_CPU_USAGE_1M: (
                system_status.cpu_usage_1m if system_status is not None else None
            ),
            ATTR_SYSTEM_MEMORY_USAGE_PERCENT: (
                system_status.memory_usage_percent
                if system_status is not None
                else None
            ),
            ATTR_SYSTEM_MEMORY_FREE_MB: (
                system_status.memory_free_mb if system_status is not None else None
            ),
            ATTR_SYSTEM_RUNTIME_DATA_UPDATED_AT: (
                self.coordinator.last_runtime_data_updated_at.isoformat()
                if self.coordinator.last_runtime_data_updated_at is not None
                else None
            ),
            ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT: (
                system_status.disk_usage_percent_by_mount
                if system_status is not None
                else None
            ),
            ATTR_SYSTEM_PORTS: self._build_ports_attribute(),
        }

    def _build_ports_attribute(self) -> dict[str, str]:
        """Return the physical port link-state map from nicStates."""
        raw_nic_states = (self.coordinator.last_init_payload or {}).get("nicStates")
        if not isinstance(raw_nic_states, dict):
            return {}

        ports: dict[str, str] = {}
        for port_name, raw_state in raw_nic_states.items():
            if not isinstance(port_name, str) or not port_name:
                continue
            if not isinstance(raw_state, dict):
                continue
            carrier = raw_state.get("carrier")
            ports[port_name] = "up" if carrier == "1" else "down"
        return ports

    def _build_current_wan_usage_attribute(
        self,
    ) -> dict[str, dict[str, int | None]]:
        """Return the current WAN usage summary keyed by WAN name."""
        usage_by_wan_name: dict[str, dict[str, int | None]] = {}

        for usage_summary in self.integration_manager.get_current_wan_usage_summaries():
            wan_name = self._resolve_wan_usage_name(usage_summary, usage_by_wan_name)
            usage_by_wan_name[wan_name] = {
                "download_bytes": usage_summary.download_bytes,
                "upload_bytes": usage_summary.upload_bytes,
            }

        return usage_by_wan_name

    @staticmethod
    def _resolve_wan_usage_name(
        usage_summary: FirewallaWanUsageSummary,
        usage_by_wan_name: dict[str, dict[str, int | None]],
    ) -> str:
        """Return a stable WAN usage key without clobbering duplicates."""
        wan_name = usage_summary.wan_name or usage_summary.wan_uuid
        if wan_name not in usage_by_wan_name:
            return wan_name
        return usage_summary.wan_uuid

    @staticmethod
    def _format_uptime(uptime_seconds: int | None) -> str | None:
        """Return uptime as a readable duration string."""
        if uptime_seconds is None:
            return None

        total_minutes = uptime_seconds // 60
        total_hours, minutes = divmod(total_minutes, 60)
        days, hours = divmod(total_hours, 24)

        if days > 0:
            return f"{days}d {hours:02d}h {minutes:02d}m"
        if total_hours > 0:
            return f"{total_hours}h {minutes:02d}m"
        return f"{total_minutes}m"


class FirewallaNetworkBinarySensor(FirewallaEntity, BinarySensorEntity):
    """Expose one Firewalla unified network (LAN/VLAN/VPN/WAN) surface."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = TRANS_KEY_ENTITY_BINARY_SENSOR_NETWORK

    def __init__(self, entry: FirewallaConfigEntry, network_uuid: str) -> None:
        """Initialize one network binary sensor."""
        super().__init__(entry, entry.runtime_data.coordinator)
        self._network_uuid = network_uuid
        self._update_translation_placeholders()
        self._attr_unique_id = self.integration_manager.build_entity_unique_id(
            object_id=f"network_{network_uuid}",
            suffix=ENTITY_SUFFIX_BINARY_SENSOR,
        )

    @property
    def _network(self) -> FirewallaNetwork | None:
        """Return the current network view for this sensor."""
        for network in self.integration_manager.get_networks():
            if network.uuid == self._network_uuid:
                return network
        return None

    def _update_translation_placeholders(self) -> None:
        """Refresh name placeholders from the latest network view."""
        network = self._network
        self._attr_translation_placeholders = {
            TRANS_PLACEHOLDER_NETWORK_KIND: (
                network.kind.display_name if network is not None else "Network"
            ),
            TRANS_PLACEHOLDER_NETWORK_NAME: (
                network.name if network is not None else self._network_uuid
            ),
        }
        self.__dict__.pop("name", None)

    def _handle_coordinator_update(self) -> None:
        """Refresh dynamic placeholders before writing updated state."""
        self._update_translation_placeholders()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return whether the network is present in the runtime inventory."""
        return super().available and self._network is not None

    @property
    def is_on(self) -> bool | None:
        """Return whether the network is configured/enabled."""
        network = self._network
        if network is None:
            return None
        return network.enabled

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return bounded network metadata attributes."""
        network = self._network
        return {
            **self.build_state_attributes(TRANS_KEY_PURPOSE_NETWORK),
            ATTR_NETWORK_KIND: (network.kind.value if network is not None else None),
            ATTR_NETWORK_VLAN_ID: (network.vlan_id if network is not None else None),
            ATTR_NETWORK_PORTS: (list(network.ports) if network is not None else None),
            ATTR_NETWORK_IPV4_ADDRESSES: (
                list(network.ipv4_addresses) if network is not None else None
            ),
            ATTR_NETWORK_IPV4_SUBNETS: (
                list(network.ipv4_subnets) if network is not None else None
            ),
            ATTR_NETWORK_IPV6_ADDRESSES: (
                list(network.ipv6_addresses) if network is not None else None
            ),
            ATTR_NETWORK_IPV6_SUBNETS: (
                list(network.ipv6_subnets) if network is not None else None
            ),
            ATTR_NETWORK_GATEWAY: (network.gateway if network is not None else None),
            ATTR_NETWORK_DNS_SERVERS: (
                list(network.dns_servers) if network is not None else None
            ),
            ATTR_NETWORK_DHCP: (
                self._serialize_dhcp(network.dhcp) if network is not None else None
            ),
            ATTR_NETWORK_DEVICE_COUNT: (
                network.device_host_count if network is not None else None
            ),
            ATTR_NETWORK_USAGE: (
                self._serialize_usage(network.usage) if network is not None else None
            ),
            ATTR_NETWORK_ENABLED: (network.enabled if network is not None else None),
            ATTR_NETWORK_MDNS_RELAY: (
                network.mdns_relay if network is not None else None
            ),
            ATTR_NETWORK_SSDP_RELAY: (
                network.ssdp_relay if network is not None else None
            ),
            ATTR_NETWORK_BLOCK_ICMP: (
                network.block_icmp if network is not None else None
            ),
        }

    @staticmethod
    def _serialize_usage(
        usage: FirewallaNetworkUsageSummary | None,
    ) -> dict[str, dict[str, int | None]] | None:
        """Serialize one network usage summary into a bounded attribute dict."""
        if usage is None:
            return None
        return {
            window: _serialize_usage_window(getattr(usage, attr))
            for attr, window in (
                ("last_24h", "last_24h"),
                ("last_60m", "last_60m"),
                ("last_30d", "last_30d"),
                ("last_12m", "last_12m"),
            )
        }

    @staticmethod
    def _serialize_dhcp(dhcp: object) -> dict[str, object] | None:
        """Serialize one DHCP config into a bounded attribute dict."""
        if dhcp is None:
            return None
        return {
            "gateway": getattr(dhcp, "gateway", None),
            "subnet_mask": getattr(dhcp, "subnet_mask", None),
            "lease_seconds": getattr(dhcp, "lease_seconds", None),
            "range_start": getattr(dhcp, "range_start", None),
            "range_end": getattr(dhcp, "range_end", None),
            "name_servers": list(getattr(dhcp, "name_servers", ())),
            "search_domains": list(getattr(dhcp, "search_domains", ())),
        }


class FirewallaWatchedDeviceBinarySensor(FirewallaEntity, BinarySensorEntity):
    """Expose one selected watched-device connectivity surface."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = TRANS_KEY_ENTITY_BINARY_SENSOR_WATCHED_DEVICE

    def __init__(self, entry: FirewallaConfigEntry, mac: str) -> None:
        """Initialize one watched-device binary sensor."""
        super().__init__(entry, entry.runtime_data.coordinator)
        self._mac = mac
        self._update_translation_placeholders()
        self._attr_unique_id = self.integration_manager.build_entity_unique_id(
            object_id=mac,
            suffix=ENTITY_SUFFIX_BINARY_SENSOR,
        )

    @property
    def _host(self) -> FirewallaHostRuntime | None:
        """Return the currently resolved watched host."""
        return self.host_manager.get_host(self._mac)

    def _update_translation_placeholders(self) -> None:
        """Refresh name placeholders from the latest watched-host view."""
        host = self._host
        self._attr_translation_placeholders = {
            "host_name": host.host_name if host is not None else self._mac
        }
        self.__dict__.pop("name", None)

    def _handle_coordinator_update(self) -> None:
        """Refresh dynamic placeholders before writing updated state."""
        self._update_translation_placeholders()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return whether the selected watched device is present in the runtime."""
        return super().available and self._host is not None

    @property
    def is_on(self) -> bool | None:
        """Return whether the watched device is currently online."""
        host = self._host
        if host is None:
            return None
        return self.host_manager.is_watched_device_online(host)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return bounded watched-device metadata attributes."""
        host = self._host
        return {
            **self.build_state_attributes(
                TRANS_KEY_PURPOSE_WATCHED_DEVICE_CONNECTIVITY
            ),
            ATTR_WATCHED_DEVICE_IP_ADDRESS: (
                host.ip_address if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_HOST_NAME: (
                host.host_name if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_DNS_HOSTNAME: (
                host.dns_hostname if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_DNS_DOMAIN: (
                host.dns_domain if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_DNS_FQDN: (host.dns_fqdn if host is not None else None),
            ATTR_WATCHED_DEVICE_HOST_DEVICE_TYPE: (
                host.host_device_type if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_DEVICE_GROUP: (
                host.group_name if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_NETWORK_NAME: (
                host.network_name if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_CONNECTION_TYPE: (
                host.connection_type if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_DOWNLOAD_USAGE: (
                host.download_bytes if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_UPLOAD_USAGE: (
                host.upload_bytes if host is not None else None
            ),
            ATTR_WATCHED_DEVICE_LAST_ACTIVE: (
                datetime.fromtimestamp(host.last_active, UTC).isoformat()
                if host is not None and host.last_active is not None
                else None
            ),
        }
