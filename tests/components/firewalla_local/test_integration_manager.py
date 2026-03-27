"""Tests for the Firewalla Local integration manager."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import CONF_LICENSE, DOMAIN
from custom_components.firewalla_local.managers.integration_manager import (
    FirewallaIntegrationManager,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaDiskUsageInput,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
)


def _build_manager(
    snapshot: FirewallaRuntimeSnapshot,
    *,
    unique_id: str | None = None,
) -> FirewallaIntegrationManager:
    """Return an integration manager with minimal coordinator state."""
    coordinator = SimpleNamespace(data=snapshot, hass=None)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data={CONF_LICENSE: "license-123"},
    )
    return FirewallaIntegrationManager(coordinator, entry, MagicMock())


def test_handle_refresh_shapes_appliance_views() -> None:
    """Test the manager shapes appliance identity, status, and speed-test views."""
    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name=None,
            device_name="Hallway Box",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(
            booting_complete=True,
            cloud_connected=False,
            ddns="box.example.firewalla.org",
            firmware_release_type="alpha",
            public_ip=None,
            public_ips={"wan": "23.245.207.179"},
            cpu_usage_1m=37.5,
            memory_usage_ratio=0.25,
            total_memory_mb=1000,
            disk_usages=(
                FirewallaDiskUsageInput(
                    mount="/",
                    capacity_ratio=0.29,
                    used_bytes=None,
                    size_bytes=None,
                ),
                FirewallaDiskUsageInput(
                    mount="/data",
                    capacity_ratio=None,
                    used_bytes=30,
                    size_bytes=500,
                ),
                FirewallaDiskUsageInput(
                    mount="/home",
                    capacity_ratio=0.9,
                    used_bytes=None,
                    size_bytes=None,
                ),
            ),
        ),
        policy_rules=(),
        exception_rule_count=0,
        speed_test_results=(
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1000,
                download_mbps=100,
                upload_mbps=20,
                latency_ms=10,
                jitter_ms=1,
                packet_loss_percent=0,
                download_megabytes=50,
                upload_megabytes=10,
                isp="ISP",
                public_ip="23.245.207.179",
                server_country="United States",
                server_host="server-a",
                server_id="1",
                server_location="Columbus, OH",
                server_sponsor="Boost Mobile",
                manual=False,
                success=True,
                vendor="ookla",
            ),
            FirewallaSpeedTestRecord(
                tested_at_timestamp=2000,
                download_mbps=200,
                upload_mbps=30,
                latency_ms=11,
                jitter_ms=2,
                packet_loss_percent=0,
                download_megabytes=60,
                upload_megabytes=11,
                isp="ISP",
                public_ip="23.245.207.180",
                server_country="United States",
                server_host="server-b",
                server_id="2",
                server_location="Chicago, IL",
                server_sponsor="Carrier",
                manual=True,
                success=False,
                vendor="ookla",
            ),
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1500,
                download_mbps=150,
                upload_mbps=25,
                latency_ms=9,
                jitter_ms=1.5,
                packet_loss_percent=0,
                download_megabytes=55,
                upload_megabytes=10.5,
                isp="ISP",
                public_ip="23.245.207.181",
                server_country="United States",
                server_host="server-c",
                server_id="3",
                server_location="Cleveland, OH",
                server_sponsor="Carrier",
                manual=True,
                success=True,
                vendor="ookla",
            ),
        ),
    )

    manager = _build_manager(snapshot)

    manager.handle_refresh(snapshot)

    assert manager.system_info.name == "Hallway Box"
    assert manager.system_info.host == "192.168.200.1"
    assert manager.system_status is not None
    assert manager.system_status.wan_ip == "23.245.207.179"
    assert manager.system_status.cpu_usage_1m == 37.5
    assert manager.system_status.memory_usage_percent == 25.0
    assert manager.system_status.memory_free_mb == 750.0
    assert manager.system_status.disk_usage_percent_by_mount == {
        "/": 29,
        "/data": 6,
    }
    assert manager.latest_speed_test is not None
    assert manager.latest_speed_test.tested_at_timestamp == 1500
    assert manager.latest_speed_test.download_mbps == 150
    assert manager.latest_speed_test.success is True


def test_build_device_info_uses_default_name_and_entry_unique_id() -> None:
    """Test device info uses the shaped appliance name and config entry identity."""
    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name=None,
            device_name=None,
            model="purple",
            serial_number="serial-999",
            software_version="2.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
    )

    manager = _build_manager(snapshot, unique_id="entry-123")

    device_info = manager.build_device_info()

    assert device_info["name"] == "Firewalla"
    assert device_info["model"] == "purple"
    assert device_info["serial_number"] == "serial-999"
    assert device_info["sw_version"] == "2.0.0"
    assert device_info["identifiers"] == {(DOMAIN, "entry-123")}


def test_latest_speed_test_is_none_without_successful_records() -> None:
    """Test unsuccessful speed tests do not produce a latest-speed-test view."""
    snapshot = FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model=None,
            serial_number=None,
            software_version=None,
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
        speed_test_results=(
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1000,
                download_mbps=None,
                upload_mbps=None,
                latency_ms=None,
                jitter_ms=None,
                packet_loss_percent=None,
                download_megabytes=None,
                upload_megabytes=None,
                isp=None,
                public_ip=None,
                server_country=None,
                server_host=None,
                server_id=None,
                server_location=None,
                server_sponsor=None,
                manual=False,
                success=False,
                vendor=None,
            ),
        ),
    )

    manager = _build_manager(snapshot)

    manager.handle_refresh(snapshot)

    assert manager.latest_speed_test is None
