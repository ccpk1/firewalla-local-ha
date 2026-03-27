"""Sensor platform for Firewalla Local system-monitoring surfaces."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfDataRate, UnitOfTime
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
    ATTR_WATCHED_USER_APP_USAGE_BY_APP,
    ATTR_WATCHED_USER_ASSOCIATED_DEVICE_COUNT,
    ATTR_WATCHED_USER_ASSOCIATED_DEVICE_GROUP,
    ATTR_WATCHED_USER_ASSOCIATED_DEVICES,
    ATTR_WATCHED_USER_LAST_ACTIVE,
    ATTR_WATCHED_USER_UNIQUE_USAGE_TODAY,
    ENTITY_SUFFIX_SENSOR,
    TRANS_KEY_ENTITY_SENSOR_LATEST_SPEED_TEST_DOWNLOAD,
    TRANS_KEY_ENTITY_SENSOR_WATCHED_USER_TODAY_USAGE,
    TRANS_KEY_PURPOSE_SPEED_TEST,
    TRANS_KEY_PURPOSE_WATCHED_USER_USAGE,
)
from .coordinator import FirewallaConfigEntry
from .entity import FirewallaEntity
from .models import FirewallaWatchedUser

PARALLEL_UPDATES = 0

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
            FirewallaLatestSpeedTestDownloadSensor(entry),
            *[
                FirewallaWatchedUserTodayUsageSensor(entry, user_id)
                for user_id in (
                    entry.runtime_data.user_manager.configured_watched_user_ids
                )
            ],
        ]
    )


class FirewallaLatestSpeedTestDownloadSensor(FirewallaEntity, SensorEntity):
    """Expose the latest successful speed-test download result."""

    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = TRANS_KEY_ENTITY_SENSOR_LATEST_SPEED_TEST_DOWNLOAD

    def __init__(self, entry: FirewallaConfigEntry) -> None:
        """Initialize the latest-speed-test download sensor."""
        super().__init__(entry, entry.runtime_data.coordinator)
        self._attr_unique_id = self.integration_manager.build_entity_unique_id(
            object_id=_LATEST_SPEED_TEST_OBJECT_ID,
            suffix=ENTITY_SUFFIX_SENSOR,
        )

    @property
    def native_value(self) -> float | None:
        """Return the latest successful download speed in Mbps."""
        speed_test = self.latest_speed_test
        return speed_test.download_mbps if speed_test is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return stable attributes describing the latest speed test."""
        speed_test = self.latest_speed_test
        return {
            ATTR_PURPOSE: TRANS_KEY_PURPOSE_SPEED_TEST,
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


class FirewallaWatchedUserTodayUsageSensor(FirewallaEntity, SensorEntity):
    """Expose today's total usage for one selected watched user."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = TRANS_KEY_ENTITY_SENSOR_WATCHED_USER_TODAY_USAGE

    def __init__(self, entry: FirewallaConfigEntry, user_id: str) -> None:
        """Initialize one watched-user today-usage sensor."""
        super().__init__(entry, entry.runtime_data.coordinator)
        self._user_id = user_id
        self._update_translation_placeholders()
        self._attr_unique_id = self.integration_manager.build_entity_unique_id(
            object_id=user_id,
            suffix=ENTITY_SUFFIX_SENSOR,
        )

    @property
    def _watched_user(self) -> FirewallaWatchedUser | None:
        """Return the current watched-user view."""
        return self.get_watched_user(self._user_id)

    def _update_translation_placeholders(self) -> None:
        """Refresh name placeholders from the latest watched-user view."""
        watched_user = self._watched_user
        self._attr_translation_placeholders = {
            "user_name": (
                watched_user.name if watched_user is not None else self._user_id
            )
        }
        self.__dict__.pop("name", None)

    def _handle_coordinator_update(self) -> None:
        """Refresh dynamic placeholders before writing updated state."""
        self._update_translation_placeholders()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return whether the selected watched user is present in the runtime."""
        return super().available and self._watched_user is not None

    @property
    def native_value(self) -> int | None:
        """Return today's total usage minutes for the watched user."""
        watched_user = self._watched_user
        return watched_user.total_minutes_today if watched_user is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return bounded watched-user metadata attributes."""
        watched_user = self._watched_user
        return {
            ATTR_PURPOSE: TRANS_KEY_PURPOSE_WATCHED_USER_USAGE,
            ATTR_WATCHED_USER_ASSOCIATED_DEVICE_GROUP: (
                watched_user.affiliated_group_name if watched_user is not None else None
            ),
            ATTR_WATCHED_USER_ASSOCIATED_DEVICES: (
                list(watched_user.associated_host_names)
                if watched_user is not None
                else None
            ),
            ATTR_WATCHED_USER_ASSOCIATED_DEVICE_COUNT: (
                len(watched_user.associated_host_names)
                if watched_user is not None
                else None
            ),
            ATTR_WATCHED_USER_UNIQUE_USAGE_TODAY: (
                watched_user.unique_minutes_today if watched_user is not None else None
            ),
            ATTR_WATCHED_USER_APP_USAGE_BY_APP: (
                {
                    usage.app_id: usage.total_minutes
                    for usage in watched_user.app_usage_today
                    if usage.total_minutes > 0
                }
                if watched_user is not None
                else None
            ),
            ATTR_WATCHED_USER_LAST_ACTIVE: (
                datetime.fromtimestamp(watched_user.last_active, UTC).isoformat()
                if watched_user is not None and watched_user.last_active is not None
                else None
            ),
        }
