"""Tests for the Firewalla Local sensor platform."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import (
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
    ATTR_SYSTEM_RUNTIME_DATA_UPDATED_AT,
    ATTR_SYSTEM_UPTIME,
    ATTR_SYSTEM_UPTIME_SECONDS,
    ATTR_SYSTEM_WAN_IP,
    ATTR_SYSTEM_WAN_IPS,
    ATTR_WATCHED_USER_APP_USAGE_BY_APP,
    ATTR_WATCHED_USER_ASSOCIATED_DEVICE_COUNT,
    ATTR_WATCHED_USER_ASSOCIATED_DEVICE_GROUP,
    ATTR_WATCHED_USER_ASSOCIATED_DEVICES,
    ATTR_WATCHED_USER_LAST_ACTIVE,
    ATTR_WATCHED_USER_UNIQUE_USAGE_TODAY,
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
    CONF_WATCHED_USERS,
    DOMAIN,
    TRANS_KEY_PURPOSE_SPEED_TEST,
    TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS,
    TRANS_KEY_PURPOSE_WATCHED_USER_USAGE,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaDiskUsageInput,
    FirewallaHostRuntime,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
    FirewallaUserAppUsage,
    FirewallaUserRuntime,
)


def _state_for_unique_suffix(hass: HomeAssistant, domain: str, unique_suffix: str):
    """Return the entity state matching one unique-ID suffix."""
    entity_entry = next(
        entry
        for entry in er.async_get(hass).entities.values()
        if entry.domain == domain and entry.unique_id.endswith(unique_suffix)
    )
    state = hass.states.get(entity_entry.entity_id)
    assert state is not None
    return state


def _runtime_payload() -> dict[str, object]:
    """Return a minimal raw init payload for coordinator setup tests."""
    return {
        "policyRules": [],
        "monthlyDataUsageOnWans": {
            "wan-1": {
                "download": [[1_743_480_000, 1024]],
                "upload": [[1_743_480_000, 512]],
                "totalDownload": 3072,
                "totalUpload": 1280,
                "monthlyBeginTs": 1_743_292_800,
                "monthlyEndTs": 1_745_971_199,
            },
            "wan-2": {
                "download": [[1_743_480_000, 900]],
                "upload": [[1_743_480_000, 450]],
                "totalDownload": 900,
                "totalUpload": 450,
                "monthlyBeginTs": 1_743_292_800,
                "monthlyEndTs": 1_745_971_199,
            },
        },
        "networkMonitorData": {
            "overall_wan_state:overall_wan_state": {
                "labels": {
                    "wanStatus": {
                        "eth0": {
                            "wan_intf_name": "WAN-ONE",
                            "wan_intf_uuid": "wan-1",
                        },
                        "eth1": {
                            "wan_intf_name": "WAN-TWO",
                            "wan_intf_uuid": "wan-2",
                        },
                    }
                }
            }
        },
    }


def _snapshot_with_monitoring(*, with_speed_test: bool) -> FirewallaRuntimeSnapshot:
    """Return a runtime snapshot with system-monitoring data."""
    return FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(
            booting_complete=bool(with_speed_test),
            cloud_connected=bool(with_speed_test),
            ddns="box.example.firewalla.org" if with_speed_test else None,
            firmware_release_type="alpha" if with_speed_test else None,
            public_ip="23.245.207.179" if with_speed_test else None,
            public_ips={"eth0": "23.245.207.179"} if with_speed_test else None,
            cpu_usage_1m=42.1 if with_speed_test else 22.5,
            memory_usage_ratio=0.7638814708714687 if with_speed_test else 0.25,
            total_memory_mb=3861.65625 if with_speed_test else 1000.0,
            uptime_seconds=22690936 if with_speed_test else None,
            disk_usages=(
                FirewallaDiskUsageInput(
                    mount="/",
                    capacity_ratio=0.29,
                    used_bytes=None,
                    size_bytes=None,
                ),
                FirewallaDiskUsageInput(
                    mount="/boot",
                    capacity_ratio=0.18,
                    used_bytes=None,
                    size_bytes=None,
                ),
                FirewallaDiskUsageInput(
                    mount="/boot/efi",
                    capacity_ratio=0.01,
                    used_bytes=None,
                    size_bytes=None,
                ),
                FirewallaDiskUsageInput(
                    mount="/var/lib/docker",
                    capacity_ratio=0.03,
                    used_bytes=None,
                    size_bytes=None,
                ),
                FirewallaDiskUsageInput(
                    mount="/log",
                    capacity_ratio=0.8,
                    used_bytes=None,
                    size_bytes=None,
                ),
                FirewallaDiskUsageInput(
                    mount="/data",
                    capacity_ratio=0.06,
                    used_bytes=None,
                    size_bytes=None,
                ),
            ),
        ),
        policy_rules=(),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:01",
                display_name="Online device 1",
                fallback_name=None,
                ip_address="192.168.200.11",
                group_name=None,
                network_name=None,
                connection_type=None,
                last_active=None,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
            ),
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:02",
                display_name="Online device 2",
                fallback_name=None,
                ip_address="192.168.200.12",
                group_name=None,
                network_name=None,
                connection_type=None,
                last_active=None,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
            ),
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:03",
                display_name="Offline device",
                fallback_name=None,
                ip_address="192.168.200.13",
                group_name=None,
                network_name=None,
                connection_type=None,
                last_active=None,
                download_bytes=None,
                upload_bytes=None,
                stale=True,
            ),
        ),
        speed_test_results=(
            (
                FirewallaSpeedTestRecord(
                    tested_at_timestamp=1774293094.481,
                    download_mbps=507.17651748657227,
                    upload_mbps=49.001976013183594,
                    latency_ms=29.107863,
                    jitter_ms=1.703425,
                    packet_loss_percent=-1,
                    download_megabytes=276.21396827697754,
                    upload_megabytes=60.733930587768555,
                    isp="Atlantic Broadband",
                    public_ip="23.245.207.179",
                    server_country="United States",
                    server_host="speedtest-cmh.dish-wireless.com:8080",
                    server_id="53971",
                    server_location="Columbus, OH",
                    server_sponsor="Boost Mobile",
                    manual=True,
                    success=True,
                    vendor="ookla",
                ),
            )
            if with_speed_test
            else ()
        ),
    )


async def test_sensor_setup_exposes_system_status_and_speed_test(
    hass: HomeAssistant,
) -> None:
    """Test the sensor platform exposes the planned monitoring entities."""
    refresh_timestamp = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.coordinator.dt_util.utcnow",
            return_value=refresh_timestamp,
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_monitoring(with_speed_test=True),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    system_state = _state_for_unique_suffix(
        hass, "binary_sensor", "_system_status_binary_sensor"
    )
    speedtest_state = _state_for_unique_suffix(
        hass, "sensor", "_latest_speed_test_download_sensor"
    )

    assert system_state is not None
    assert system_state.name == "Firewalla System Status"
    assert system_state.state == STATE_ON
    assert system_state.attributes[ATTR_PURPOSE] == TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS
    assert system_state.attributes[ATTR_SYSTEM_BOOT_COMPLETE] is True
    assert system_state.attributes[ATTR_SYSTEM_WAN_IP] == "23.245.207.179"
    assert system_state.attributes[ATTR_SYSTEM_WAN_IPS] == {"eth0": "23.245.207.179"}
    assert system_state.attributes[ATTR_SYSTEM_CURRENT_WAN_USAGE] == {
        "WAN-ONE": {"download_bytes": 3072, "upload_bytes": 1280},
        "WAN-TWO": {"download_bytes": 900, "upload_bytes": 450},
    }
    assert system_state.attributes[ATTR_SYSTEM_CPU_USAGE_1M] == 42.1
    assert system_state.attributes[ATTR_SYSTEM_MEMORY_USAGE_PERCENT] == 76.4
    assert system_state.attributes[ATTR_SYSTEM_MEMORY_FREE_MB] == 911.8
    assert (
        system_state.attributes[ATTR_SYSTEM_RUNTIME_DATA_UPDATED_AT]
        == refresh_timestamp.isoformat()
    )
    assert system_state.attributes[ATTR_SYSTEM_UPTIME] == "262d 15h 02m"
    assert system_state.attributes[ATTR_SYSTEM_UPTIME_SECONDS] == 22690936
    assert system_state.attributes[ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT] == {
        "/": 29,
        "/boot": 18,
        "/boot/efi": 1,
        "/var/lib/docker": 3,
        "/log": 80,
        "/data": 6,
    }
    assert system_state.attributes[ATTR_SYSTEM_CLOUD_CONNECTED] is True
    assert system_state.attributes[ATTR_SYSTEM_DEVICES_TOTAL] == 3
    assert system_state.attributes[ATTR_SYSTEM_DEVICES_ONLINE] == 2
    assert system_state.attributes[ATTR_SYSTEM_DEVICES_OFFLINE] == 1
    assert system_state.attributes[ATTR_SYSTEM_DDNS] == "box.example.firewalla.org"
    assert system_state.attributes[ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE] == "alpha"

    system_entry = next(
        entry
        for entry in registry.entities.values()
        if entry.unique_id.endswith("_system_status_binary_sensor")
    )
    assert system_entry is not None
    assert system_entry.unique_id.endswith("_system_status_binary_sensor")

    assert speedtest_state is not None
    assert speedtest_state.name == "Firewalla Speed Test"
    assert float(speedtest_state.state) == pytest.approx(507.17651748657227)
    assert speedtest_state.attributes[ATTR_PURPOSE] == TRANS_KEY_PURPOSE_SPEED_TEST
    assert speedtest_state.attributes[ATTR_SPEED_TEST_ISP] == "Atlantic Broadband"
    assert speedtest_state.attributes[ATTR_SPEED_TEST_PUBLIC_IP] == "23.245.207.179"
    assert speedtest_state.attributes[ATTR_SPEED_TEST_UPLOAD] == 49.001976013183594
    assert speedtest_state.attributes[ATTR_SPEED_TEST_LATENCY] == 29.107863
    assert speedtest_state.attributes[ATTR_SPEED_TEST_JITTER] == 1.703425
    assert speedtest_state.attributes[ATTR_SPEED_TEST_PACKET_LOSS] == -1
    assert (
        speedtest_state.attributes[ATTR_SPEED_TEST_DOWNLOAD_MBYTES]
        == 276.21396827697754
    )
    assert (
        speedtest_state.attributes[ATTR_SPEED_TEST_UPLOAD_MBYTES] == 60.733930587768555
    )
    assert speedtest_state.attributes[ATTR_SPEED_TEST_SERVER_COUNTRY] == "United States"
    assert (
        speedtest_state.attributes[ATTR_SPEED_TEST_SERVER_HOST]
        == "speedtest-cmh.dish-wireless.com:8080"
    )
    assert speedtest_state.attributes[ATTR_SPEED_TEST_SERVER_ID] == "53971"
    assert speedtest_state.attributes[ATTR_SPEED_TEST_SERVER_LOCATION] == "Columbus, OH"
    assert speedtest_state.attributes[ATTR_SPEED_TEST_SERVER_SPONSOR] == "Boost Mobile"
    assert speedtest_state.attributes[ATTR_SPEED_TEST_MANUAL] is True
    assert speedtest_state.attributes[ATTR_SPEED_TEST_SUCCESS] is True
    assert speedtest_state.attributes[ATTR_SPEED_TEST_VENDOR] == "ookla"
    assert (
        speedtest_state.attributes[ATTR_SPEED_TEST_TESTED_AT]
        == datetime.fromtimestamp(1774293094.481, UTC).isoformat()
    )

    speedtest_entry = next(
        entry
        for entry in registry.entities.values()
        if entry.unique_id.endswith("_latest_speed_test_download_sensor")
    )
    assert speedtest_entry is not None
    assert speedtest_entry.unique_id.endswith("_latest_speed_test_download_sensor")


async def test_sensor_setup_handles_missing_speed_test_history(
    hass: HomeAssistant,
) -> None:
    """Test the speed-test sensor stays present with no data history."""
    refresh_timestamp = datetime(2026, 4, 2, 12, 5, tzinfo=UTC)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.coordinator.dt_util.utcnow",
            return_value=refresh_timestamp,
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value={"policyRules": []}),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_monitoring(with_speed_test=False),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    system_state = _state_for_unique_suffix(
        hass, "binary_sensor", "_system_status_binary_sensor"
    )
    speedtest_state = _state_for_unique_suffix(
        hass, "sensor", "_latest_speed_test_download_sensor"
    )

    assert system_state is not None
    assert system_state.state == STATE_ON
    assert system_state.attributes[ATTR_PURPOSE] == TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS
    assert system_state.attributes[ATTR_SYSTEM_BOOT_COMPLETE] is False
    assert system_state.attributes[ATTR_SYSTEM_WAN_IP] is None
    assert system_state.attributes[ATTR_SYSTEM_WAN_IPS] is None
    assert system_state.attributes[ATTR_SYSTEM_CURRENT_WAN_USAGE] == {}
    assert system_state.attributes[ATTR_SYSTEM_CPU_USAGE_1M] == 22.5
    assert system_state.attributes[ATTR_SYSTEM_MEMORY_USAGE_PERCENT] == 25.0
    assert system_state.attributes[ATTR_SYSTEM_MEMORY_FREE_MB] == 750.0
    assert (
        system_state.attributes[ATTR_SYSTEM_RUNTIME_DATA_UPDATED_AT]
        == refresh_timestamp.isoformat()
    )
    assert system_state.attributes[ATTR_SYSTEM_UPTIME] is None
    assert system_state.attributes[ATTR_SYSTEM_UPTIME_SECONDS] is None
    assert system_state.attributes[ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT] == {
        "/": 29,
        "/boot": 18,
        "/boot/efi": 1,
        "/var/lib/docker": 3,
        "/log": 80,
        "/data": 6,
    }
    assert system_state.attributes[ATTR_SYSTEM_CLOUD_CONNECTED] is False
    assert system_state.attributes[ATTR_SYSTEM_DEVICES_TOTAL] == 3
    assert system_state.attributes[ATTR_SYSTEM_DEVICES_ONLINE] == 2
    assert system_state.attributes[ATTR_SYSTEM_DEVICES_OFFLINE] == 1
    assert system_state.attributes[ATTR_SYSTEM_DDNS] is None
    assert system_state.attributes[ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE] is None

    assert speedtest_state.state == "unknown"
    assert speedtest_state.name == "Firewalla Speed Test"
    assert speedtest_state.attributes[ATTR_PURPOSE] == TRANS_KEY_PURPOSE_SPEED_TEST


async def test_sensor_setup_exposes_watched_user_usage_sensor(
    hass: HomeAssistant,
) -> None:
    """Test a selected watched user becomes a today-usage sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_WATCHED_USERS: ["21"]},
    )
    entry.add_to_hass(hass)

    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:01",
                display_name="Kaden Phone",
                fallback_name=None,
                ip_address="192.168.200.25",
                group_name="KADEN's Devices",
                network_name=None,
                connection_type=None,
                last_active=1774287984.272,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
                user_ids=("21",),
            ),
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:02",
                display_name="Kaden Chromebook",
                fallback_name=None,
                ip_address="192.168.200.26",
                group_name="KADEN's Devices",
                network_name=None,
                connection_type=None,
                last_active=1774287000.1,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
                user_ids=("21",),
            ),
        ),
        users=(
            FirewallaUserRuntime(
                user_id="21",
                name="KADEN",
                affiliated_group_id="10",
                affiliated_group_name="KADEN's Devices",
                total_minutes_today=410,
                unique_minutes_today=381,
                app_usage_today=(
                    FirewallaUserAppUsage(
                        app_id="youtube",
                        category="av",
                        total_minutes=47,
                        unique_minutes=44,
                    ),
                    FirewallaUserAppUsage(
                        app_id="roblox",
                        category="games",
                        total_minutes=23,
                        unique_minutes=20,
                    ),
                ),
            ),
        ),
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    watched_user_entry = next(
        entity_entry
        for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity_entry.unique_id.endswith("_21_sensor")
    )
    watched_user_state = hass.states.get(watched_user_entry.entity_id)
    assert watched_user_state is not None
    assert watched_user_state.name is not None
    assert "KADEN" in watched_user_state.name
    assert watched_user_state.state == "410"
    assert (
        watched_user_state.attributes[ATTR_PURPOSE]
        == TRANS_KEY_PURPOSE_WATCHED_USER_USAGE
    )
    assert (
        watched_user_state.attributes[ATTR_WATCHED_USER_ASSOCIATED_DEVICE_GROUP]
        == "KADEN's Devices"
    )
    assert watched_user_state.attributes[ATTR_WATCHED_USER_ASSOCIATED_DEVICES] == [
        "Kaden Chromebook",
        "Kaden Phone",
    ]
    assert watched_user_state.attributes[ATTR_WATCHED_USER_ASSOCIATED_DEVICE_COUNT] == 2
    assert watched_user_state.attributes[ATTR_WATCHED_USER_UNIQUE_USAGE_TODAY] == 381
    assert watched_user_state.attributes[ATTR_WATCHED_USER_APP_USAGE_BY_APP] == {
        "youtube": 47,
        "roblox": 23,
    }
    assert (
        watched_user_state.attributes[ATTR_WATCHED_USER_LAST_ACTIVE]
        == datetime.fromtimestamp(1774287984.272, UTC).isoformat()
    )


async def test_watched_user_sensor_name_updates_after_user_rename(
    hass: HomeAssistant,
) -> None:
    """Test watched-user friendly names track app-side renames after refresh."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_WATCHED_USERS: ["21"]},
    )
    entry.add_to_hass(hass)

    initial_snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
        users=(
            FirewallaUserRuntime(
                user_id="21",
                name="KADEN",
                affiliated_group_id="10",
                affiliated_group_name="KADEN's Devices",
                total_minutes_today=410,
                unique_minutes_today=381,
            ),
        ),
    )
    renamed_snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=initial_snapshot.appliance_identity,
        appliance_runtime=initial_snapshot.appliance_runtime,
        policy_rules=(),
        exception_rule_count=0,
        users=(
            FirewallaUserRuntime(
                user_id="21",
                name="KADEN JR",
                affiliated_group_id="10",
                affiliated_group_name="KADEN's Devices",
                total_minutes_today=410,
                unique_minutes_today=381,
            ),
        ),
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=[initial_snapshot, renamed_snapshot],
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        registry = er.async_get(hass)
        watched_user_entry = next(
            entity_entry
            for entity_entry in er.async_entries_for_config_entry(
                registry, entry.entry_id
            )
            if entity_entry.unique_id.endswith("_21_sensor")
        )

        initial_state = hass.states.get(watched_user_entry.entity_id)
        assert initial_state is not None
        assert initial_state.name is not None
        assert "KADEN" in initial_state.name

        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()

    renamed_state = hass.states.get(watched_user_entry.entity_id)
    assert renamed_state is not None
    assert renamed_state.name is not None
    assert "KADEN JR" in renamed_state.name


async def test_sensor_setup_derives_watched_user_totals_and_group_associations(
    hass: HomeAssistant,
) -> None:
    """Test watched-user sensors derive missing totals and group-linked hosts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_WATCHED_USERS: ["23"]},
    )
    entry.add_to_hass(hass)

    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:23",
                display_name="Payton iPad",
                fallback_name=None,
                ip_address="192.168.200.27",
                group_name="PAYTON's Devices",
                network_name=None,
                connection_type=None,
                last_active=1774288123.5,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
                group_ids=("11",),
            ),
        ),
        users=(
            FirewallaUserRuntime(
                user_id="23",
                name="PAYTON",
                affiliated_group_id="11",
                affiliated_group_name="PAYTON's Devices",
                total_minutes_today=None,
                unique_minutes_today=None,
                app_usage_today=(
                    FirewallaUserAppUsage(
                        app_id="instagram",
                        category="social",
                        total_minutes=42,
                        unique_minutes=40,
                    ),
                    FirewallaUserAppUsage(
                        app_id="facebook",
                        category="social",
                        total_minutes=2,
                        unique_minutes=2,
                    ),
                    FirewallaUserAppUsage(
                        app_id="youtube",
                        category="av",
                        total_minutes=0,
                        unique_minutes=0,
                    ),
                ),
            ),
        ),
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    watched_user_entry = next(
        entity_entry
        for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity_entry.unique_id.endswith("_23_sensor")
    )
    watched_user_state = hass.states.get(watched_user_entry.entity_id)

    assert watched_user_state is not None
    assert watched_user_state.state == "44"
    assert watched_user_state.attributes[ATTR_WATCHED_USER_ASSOCIATED_DEVICES] == [
        "Payton iPad"
    ]
    assert watched_user_state.attributes[ATTR_WATCHED_USER_ASSOCIATED_DEVICE_COUNT] == 1
    assert watched_user_state.attributes[ATTR_WATCHED_USER_UNIQUE_USAGE_TODAY] == 42
    assert watched_user_state.attributes[ATTR_WATCHED_USER_APP_USAGE_BY_APP] == {
        "instagram": 42,
        "facebook": 2,
    }
    assert (
        watched_user_state.attributes[ATTR_WATCHED_USER_LAST_ACTIVE]
        == datetime.fromtimestamp(1774288123.5, UTC).isoformat()
    )


async def test_system_status_device_counts_use_recent_activity_not_stale_only(
    hass: HomeAssistant,
) -> None:
    """Test device summary uses host recency when stale is not informative."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:01",
                display_name="Recent 1",
                fallback_name=None,
                ip_address="192.168.200.11",
                group_name=None,
                network_name=None,
                connection_type=None,
                last_active=10_000.0,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
            ),
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:02",
                display_name="Recent 2",
                fallback_name=None,
                ip_address="192.168.200.12",
                group_name=None,
                network_name=None,
                connection_type=None,
                last_active=9_760.0,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
            ),
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:03",
                display_name="Older 1",
                fallback_name=None,
                ip_address="192.168.200.13",
                group_name=None,
                network_name=None,
                connection_type=None,
                last_active=9_000.0,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
            ),
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:04",
                display_name="Older 2",
                fallback_name=None,
                ip_address="192.168.200.14",
                group_name=None,
                network_name=None,
                connection_type=None,
                last_active=8_000.0,
                download_bytes=None,
                upload_bytes=None,
                stale=False,
            ),
        ),
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    system_state = _state_for_unique_suffix(
        hass, "binary_sensor", "_system_status_binary_sensor"
    )

    assert system_state is not None
    assert system_state.attributes[ATTR_SYSTEM_DEVICES_TOTAL] == 4
    assert system_state.attributes[ATTR_SYSTEM_DEVICES_ONLINE] == 2
    assert system_state.attributes[ATTR_SYSTEM_DEVICES_OFFLINE] == 2
