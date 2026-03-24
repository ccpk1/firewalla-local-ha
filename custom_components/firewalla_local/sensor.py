"""Sensor platform for Firewalla Local system-monitoring surfaces."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_PURPOSE,
    ATTR_SPEED_TEST_DOWNLOAD_MBYTES,
    ATTR_SPEED_TEST_ISP,
    ATTR_SPEED_TEST_JITTER,
    ATTR_SPEED_TEST_LATENCY,
    ATTR_SPEED_TEST_MANUAL,
    ATTR_SPEED_TEST_PACKET_LOSS,
    ATTR_SPEED_TEST_PUBLIC_IP,
    ATTR_SPEED_TEST_SERVER_COUNTRY,
    ATTR_SPEED_TEST_SERVER_HOST,
    ATTR_SPEED_TEST_SERVER_ID,
    ATTR_SPEED_TEST_SERVER_LOCATION,
    ATTR_SPEED_TEST_SERVER_SPONSOR,
    ATTR_SPEED_TEST_SUCCESS,
    ATTR_SPEED_TEST_TESTED_AT,
    ATTR_SPEED_TEST_UPLOAD,
    ATTR_SPEED_TEST_UPLOAD_MBYTES,
    ATTR_SPEED_TEST_VENDOR,
    ATTR_SYSTEM_BOOT_COMPLETE,
    ATTR_SYSTEM_CLOUD_CONNECTED,
    ATTR_SYSTEM_CPU_LOAD_5M,
    ATTR_SYSTEM_DDNS,
    ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT,
    ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE,
    ATTR_SYSTEM_MEMORY_FREE_MB,
    ATTR_SYSTEM_MEMORY_USAGE_PERCENT,
    ATTR_SYSTEM_WAN_IP,
    ATTR_SYSTEM_WAN_IPS,
    ENTITY_SUFFIX_SENSOR,
    SYSTEM_STATUS_STATE_AVAILABLE,
    SYSTEM_STATUS_STATE_UNAVAILABLE,
    TRANS_KEY_ENTITY_SENSOR_LATEST_SPEED_TEST_DOWNLOAD,
    TRANS_KEY_ENTITY_SENSOR_SYSTEM_STATUS,
    TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS,
)
from .coordinator import FirewallaConfigEntry
from .entity import FirewallaEntity

PARALLEL_UPDATES = 0

_SYSTEM_STATUS_OBJECT_ID = "system_status"
_LATEST_SPEED_TEST_OBJECT_ID = "latest_speed_test_download"


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: FirewallaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Firewalla Local sensors from a config entry."""
    del _hass
    async_add_entities(
        [
            FirewallaSystemStatusSensor(entry),
            FirewallaLatestSpeedTestDownloadSensor(entry),
        ]
    )


class FirewallaSystemStatusSensor(FirewallaEntity, SensorEntity):
    """Expose the Firewalla boot-status sensor surface."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = TRANS_KEY_ENTITY_SENSOR_SYSTEM_STATUS

    def __init__(self, entry: FirewallaConfigEntry) -> None:
        """Initialize the system-status sensor."""
        super().__init__(entry, entry.runtime_data.coordinator)
        self._attr_unique_id = self.system_manager.build_entity_unique_id(
            object_id=_SYSTEM_STATUS_OBJECT_ID,
            suffix=ENTITY_SUFFIX_SENSOR,
        )
        self._attr_suggested_object_id = _SYSTEM_STATUS_OBJECT_ID

    @property
    def native_value(self) -> str | None:
        """Return the overall availability-style system state for the box."""
        system_status = self.coordinator.data.system_status
        if system_status is None:
            return SYSTEM_STATUS_STATE_UNAVAILABLE
        return SYSTEM_STATUS_STATE_AVAILABLE

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return stable system-status metadata attributes."""
        system_status = self.coordinator.data.system_status
        return {
            ATTR_PURPOSE: TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS,
            ATTR_SYSTEM_BOOT_COMPLETE: (
                system_status.booting_complete if system_status is not None else None
            ),
            ATTR_SYSTEM_WAN_IP: (
                system_status.wan_ip if system_status is not None else None
            ),
            ATTR_SYSTEM_WAN_IPS: (
                system_status.wan_ips if system_status is not None else None
            ),
            ATTR_SYSTEM_CPU_LOAD_5M: (
                system_status.cpu_load_5m if system_status is not None else None
            ),
            ATTR_SYSTEM_MEMORY_USAGE_PERCENT: (
                system_status.memory_usage_percent
                if system_status is not None
                else None
            ),
            ATTR_SYSTEM_MEMORY_FREE_MB: (
                system_status.memory_free_mb if system_status is not None else None
            ),
            ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT: (
                system_status.disk_usage_percent_by_mount
                if system_status is not None
                else None
            ),
            ATTR_SYSTEM_CLOUD_CONNECTED: (
                system_status.cloud_connected if system_status is not None else None
            ),
            ATTR_SYSTEM_DDNS: system_status.ddns if system_status is not None else None,
            ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE: (
                system_status.firmware_release_type
                if system_status is not None
                else None
            ),
        }


class FirewallaLatestSpeedTestDownloadSensor(FirewallaEntity, SensorEntity):
    """Expose the latest successful speed-test download result."""

    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = TRANS_KEY_ENTITY_SENSOR_LATEST_SPEED_TEST_DOWNLOAD

    def __init__(self, entry: FirewallaConfigEntry) -> None:
        """Initialize the latest-speed-test download sensor."""
        super().__init__(entry, entry.runtime_data.coordinator)
        self._attr_unique_id = self.system_manager.build_entity_unique_id(
            object_id=_LATEST_SPEED_TEST_OBJECT_ID,
            suffix=ENTITY_SUFFIX_SENSOR,
        )
        self._attr_suggested_object_id = _LATEST_SPEED_TEST_OBJECT_ID

    @property
    def native_value(self) -> float | None:
        """Return the latest successful download speed in Mbps."""
        speed_test = self.coordinator.data.latest_speed_test
        return speed_test.download_mbps if speed_test is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return stable attributes describing the latest speed test."""
        speed_test = self.coordinator.data.latest_speed_test
        return {
            ATTR_SPEED_TEST_TESTED_AT: (
                datetime.fromtimestamp(speed_test.tested_at_timestamp, UTC).isoformat()
                if speed_test is not None
                else None
            ),
            ATTR_SPEED_TEST_ISP: speed_test.isp if speed_test is not None else None,
            ATTR_SPEED_TEST_PUBLIC_IP: (
                speed_test.public_ip if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_UPLOAD: (
                speed_test.upload_mbps if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_LATENCY: (
                speed_test.latency_ms if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_JITTER: (
                speed_test.jitter_ms if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_PACKET_LOSS: (
                speed_test.packet_loss_percent if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_DOWNLOAD_MBYTES: (
                speed_test.download_megabytes if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_UPLOAD_MBYTES: (
                speed_test.upload_megabytes if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_SERVER_COUNTRY: (
                speed_test.server_country if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_SERVER_HOST: (
                speed_test.server_host if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_SERVER_ID: (
                speed_test.server_id if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_SERVER_LOCATION: (
                speed_test.server_location if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_SERVER_SPONSOR: (
                speed_test.server_sponsor if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_MANUAL: (
                speed_test.manual if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_SUCCESS: (
                speed_test.success if speed_test is not None else None
            ),
            ATTR_SPEED_TEST_VENDOR: (
                speed_test.vendor if speed_test is not None else None
            ),
        }
