"""Tests for the Firewalla Local sensor platform."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
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
    ATTR_SYSTEM_CPU_LOAD_5M,
    ATTR_SYSTEM_DDNS,
    ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT,
    ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE,
    ATTR_SYSTEM_MEMORY_FREE_MB,
    ATTR_SYSTEM_MEMORY_USAGE_PERCENT,
    ATTR_SYSTEM_WAN_IP,
    ATTR_SYSTEM_WAN_IPS,
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
    DOMAIN,
    SYSTEM_STATUS_STATE_AVAILABLE,
    TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS,
)
from custom_components.firewalla_local.models import (
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestResult,
    FirewallaSystemInfo,
    FirewallaSystemStatus,
)


def _runtime_payload() -> dict[str, object]:
    """Return a minimal raw init payload for coordinator setup tests."""
    return {"policyRules": []}


def _snapshot_with_monitoring(*, with_speed_test: bool) -> FirewallaRuntimeSnapshot:
    """Return a runtime snapshot with system-monitoring data."""
    return FirewallaRuntimeSnapshot(
        system_info=FirewallaSystemInfo(
            host="192.168.200.1",
            name="Firewalla",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        policy_rules=(),
        exception_rule_count=0,
        system_status=FirewallaSystemStatus(
            booting_complete=bool(with_speed_test),
            cloud_connected=bool(with_speed_test),
            ddns="box.example.firewalla.org" if with_speed_test else None,
            firmware_release_type="alpha" if with_speed_test else None,
            wan_ip="23.245.207.179" if with_speed_test else None,
            wan_ips={"eth0": "23.245.207.179"} if with_speed_test else None,
            cpu_load_5m=2.8037109375 if with_speed_test else 1.25,
            memory_usage_percent=76.4 if with_speed_test else 25.0,
            memory_free_mb=911.8 if with_speed_test else 750.0,
            disk_usage_percent_by_mount={
                "/": 29,
                "/boot": 18,
                "/boot/efi": 1,
                "/var/lib/docker": 3,
                "/log": 80,
                "/data": 6,
            },
        ),
        latest_speed_test=(
            FirewallaSpeedTestResult(
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
            )
            if with_speed_test
            else None
        ),
    )


async def test_sensor_setup_exposes_system_status_and_speed_test(
    hass: HomeAssistant,
) -> None:
    """Test the sensor platform exposes the planned monitoring entities."""
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
    system_state = hass.states.get("sensor.firewalla_system_status")
    speedtest_state = hass.states.get("sensor.firewalla_latest_speed_test_download")

    assert system_state is not None
    assert system_state.name == "Firewalla System status"
    assert system_state.state == SYSTEM_STATUS_STATE_AVAILABLE
    assert system_state.attributes[ATTR_PURPOSE] == TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS
    assert system_state.attributes[ATTR_SYSTEM_BOOT_COMPLETE] is True
    assert system_state.attributes[ATTR_SYSTEM_WAN_IP] == "23.245.207.179"
    assert system_state.attributes[ATTR_SYSTEM_WAN_IPS] == {"eth0": "23.245.207.179"}
    assert system_state.attributes[ATTR_SYSTEM_CPU_LOAD_5M] == 2.8037109375
    assert system_state.attributes[ATTR_SYSTEM_MEMORY_USAGE_PERCENT] == 76.4
    assert system_state.attributes[ATTR_SYSTEM_MEMORY_FREE_MB] == 911.8
    assert system_state.attributes[ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT] == {
        "/": 29,
        "/boot": 18,
        "/boot/efi": 1,
        "/var/lib/docker": 3,
        "/log": 80,
        "/data": 6,
    }
    assert system_state.attributes[ATTR_SYSTEM_CLOUD_CONNECTED] is True
    assert system_state.attributes[ATTR_SYSTEM_DDNS] == "box.example.firewalla.org"
    assert system_state.attributes[ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE] == "alpha"

    system_entry = registry.async_get("sensor.firewalla_system_status")
    assert system_entry is not None
    assert system_entry.unique_id.endswith("_system_status_sensor")

    assert speedtest_state is not None
    assert speedtest_state.name == "Firewalla Latest speed test download"
    assert float(speedtest_state.state) == pytest.approx(507.17651748657227)
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

    speedtest_entry = registry.async_get("sensor.firewalla_latest_speed_test_download")
    assert speedtest_entry is not None
    assert speedtest_entry.unique_id.endswith("_latest_speed_test_download_sensor")


async def test_sensor_setup_handles_missing_speed_test_history(
    hass: HomeAssistant,
) -> None:
    """Test the speed-test sensor stays present with no data history."""
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_monitoring(with_speed_test=False),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    system_state = hass.states.get("sensor.firewalla_system_status")
    speedtest_state = hass.states.get("sensor.firewalla_latest_speed_test_download")

    assert system_state is not None
    assert system_state.state == SYSTEM_STATUS_STATE_AVAILABLE
    assert system_state.attributes[ATTR_PURPOSE] == TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS
    assert system_state.attributes[ATTR_SYSTEM_BOOT_COMPLETE] is False
    assert system_state.attributes[ATTR_SYSTEM_WAN_IP] is None
    assert system_state.attributes[ATTR_SYSTEM_WAN_IPS] is None
    assert system_state.attributes[ATTR_SYSTEM_CPU_LOAD_5M] == 1.25
    assert system_state.attributes[ATTR_SYSTEM_MEMORY_USAGE_PERCENT] == 25.0
    assert system_state.attributes[ATTR_SYSTEM_MEMORY_FREE_MB] == 750.0
    assert system_state.attributes[ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT] == {
        "/": 29,
        "/boot": 18,
        "/boot/efi": 1,
        "/var/lib/docker": 3,
        "/log": 80,
        "/data": 6,
    }
    assert system_state.attributes[ATTR_SYSTEM_CLOUD_CONNECTED] is False
    assert system_state.attributes[ATTR_SYSTEM_DDNS] is None
    assert system_state.attributes[ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE] is None

    assert speedtest_state is not None
    assert speedtest_state.state == "unknown"
    assert speedtest_state.attributes[ATTR_SPEED_TEST_TESTED_AT] is None
    assert speedtest_state.attributes[ATTR_SPEED_TEST_ISP] is None
    assert speedtest_state.attributes[ATTR_SPEED_TEST_PUBLIC_IP] is None
