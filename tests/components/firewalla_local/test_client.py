"""Tests for Firewalla Local client normalization."""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientSession

from custom_components.firewalla_local.api.client import FirewallaApiClient
from custom_components.firewalla_local.api.crypto import aes256_cbc_encrypt_to_base64
from custom_components.firewalla_local.api.exceptions import (
    FirewallaAuthError,
    FirewallaLocalRuntimeNotReadyError,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaDiskUsageInput,
    FirewallaGroupRuntime,
    FirewallaHostRuntime,
    FirewallaHostVpnClient,
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    FirewallaSpeedTestRecord,
    FirewallaUserAppUsage,
    FirewallaUserRuntime,
)

TEST_SYMMETRIC_KEY = "0123456789abcdef0123456789abcdef"


@pytest.mark.asyncio
async def test_local_runtime_412_raises_not_ready_error() -> None:
    """Test HTTP 412 is treated as a temporary local pairing activation delay."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )

        with (
            patch.object(
                client,
                "_async_post_local_payload",
                AsyncMock(return_value=(412, '{"error":{}}')),
            ),
            pytest.raises(
                FirewallaLocalRuntimeNotReadyError,
                match="has not accepted the new pairing yet",
            ),
        ):
            await client.async_get_runtime_init_payload()


@pytest.mark.asyncio
async def test_local_runtime_init_logs_at_info_for_pairing(caplog) -> None:
    """Test pairing-time local init uses info-level request and response logs."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
            timezone_name="UTC",
        )
        encrypted_response = aes256_cbc_encrypt_to_base64(
            json.dumps({"code": 200, "data": {}}),
            TEST_SYMMETRIC_KEY,
        )
        caplog.set_level(logging.INFO, logger="custom_components.firewalla_local")

        with patch.object(
            client,
            "_async_post_local_payload",
            AsyncMock(
                return_value=(
                    200,
                    json.dumps({"message": encrypted_response}),
                )
            ),
        ):
            await client.async_get_runtime_init_payload(log_as_info=True)

    assert (
        "Requesting Firewalla local init payload from host 192.168.200.1" in caplog.text
    )
    assert (
        "Firewalla local init request metadata for host 192.168.200.1: "
        "aid present=True, device name=Home Assistant, timezone=UTC" in caplog.text
    )


@pytest.mark.asyncio
async def test_get_runtime_snapshot_normalizes_policy_rules() -> None:
    """Test runtime snapshots normalize policy rules into a stable typed shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(
                return_value={
                    "groupName": "Firewalla",
                    "model": "gold",
                    "cpuid": "serial-123",
                    "longVersion": "1.0.0",
                    "distCodename": "bionic",
                    "bootingComplete": True,
                    "cloudConnected": True,
                    "ddns": "box.example.firewalla.org",
                    "firmwareReleaseType": "alpha",
                    "publicIp": "23.245.207.179",
                    "publicIps": {"eth0": "23.245.207.179"},
                    "osUptime": 22690936,
                    "sysMetrics": {
                        "cpuUsage1": [
                            {"user": 21, "sys": 17, "iowait": 0},
                            {"user": 25, "sys": 19, "iowait": 0},
                            {"user": 18, "sys": 17, "iowait": 0},
                            {"user": 23, "sys": 17, "iowait": 0},
                            {"user": 19, "sys": 16, "iowait": 0},
                            {"user": 21, "sys": 18, "iowait": 0},
                            {"user": 20, "sys": 22, "iowait": 0},
                            {"user": 28, "sys": 29, "iowait": 0},
                            {"user": 33, "sys": 18, "iowait": 0},
                            {"user": 21, "sys": 19, "iowait": 0},
                            {"user": 20, "sys": 17, "iowait": 0},
                            {"user": 26, "sys": 21, "iowait": 0},
                        ],
                        "memUsage": 0.7638814708714687,
                        "totalMem": 3861.65625,
                        "diskInfo": [
                            {"mount": "/", "capacity": 0.29},
                            {"mount": "/boot", "capacity": 0.18},
                            {"mount": "/boot/efi", "capacity": 0.01},
                            {"mount": "/var/lib/docker", "capacity": 0.03},
                            {"mount": "/log", "capacity": 0.8},
                            {"mount": "/data", "capacity": 0.06},
                            {"mount": "/home", "capacity": 0.62},
                        ],
                    },
                    "customizedCategories": {
                        "dap_00089bfb01d9": {"name": "DAP - 00:08:9B:FB:01:D9"}
                    },
                    "timezone": "America/New_York",
                    "hosts": [{"mac": "00:08:9B:FB:01:D9", "name": "Kitchen speaker"}],
                    "networkConfig": {
                        "dhcp": {"bond0.10": {"searchDomain": ["int.ccpk.us"]}},
                        "interface": {
                            "bond": {
                                "bond0.10": {
                                    "meta": {
                                        "name": "VLAN10 CORE",
                                        "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
                                    }
                                }
                            }
                        },
                    },
                    "networkProfiles": {
                        "5799d896-5e0f-40a5-a776-38a5d7746204": {"intf": "bond0.10"}
                    },
                    "tags": {
                        "10": {"name": "KADEN's Devices"},
                        "12": {"name": "Quarantine"},
                    },
                    "internetSpeedtestResults": [
                        {
                            "client": {
                                "isp": "Atlantic Broadband",
                                "publicIp": "23.245.207.179",
                            },
                            "manual": False,
                            "result": {
                                "dlMbytes": 89.23129463195801,
                                "download": 63.15821075439453,
                                "jitter": 1.714381,
                                "latency": 27.404289,
                                "ploss": -1,
                                "ulMbytes": 60.53947830200195,
                                "upload": 51.20576858520508,
                            },
                            "server": {
                                "country": "United States",
                                "host": "speedtest-cmh.dish-wireless.com:8080",
                                "id": "53971",
                                "location": "Columbus, OH",
                                "sponsor": "Boost Mobile",
                            },
                            "success": True,
                            "timestamp": 1774260026.511,
                            "uuid": "wan-2",
                            "vendor": "ookla",
                        },
                        {
                            "client": {
                                "isp": "Atlantic Broadband",
                                "publicIp": "23.245.207.179",
                            },
                            "manual": True,
                            "result": {
                                "dlMbytes": 276.21396827697754,
                                "download": 507.17651748657227,
                                "jitter": 1.703425,
                                "latency": 29.107863,
                                "ploss": -1,
                                "ulMbytes": 60.733930587768555,
                                "upload": 49.001976013183594,
                            },
                            "server": {
                                "country": "United States",
                                "host": "speedtest-cmh.dish-wireless.com:8080",
                                "id": "53971",
                                "location": "Columbus, OH",
                                "sponsor": "Boost Mobile",
                            },
                            "success": True,
                            "timestamp": 1774293094.481,
                            "uuid": "wan-1",
                            "vendor": "ookla",
                        },
                        {
                            "client": {
                                "isp": "Atlantic Broadband",
                                "publicIp": "23.245.207.179",
                            },
                            "manual": False,
                            "result": {
                                "download": 1,
                            },
                            "success": False,
                            "timestamp": 1774300000,
                            "vendor": "ookla",
                        },
                    ],
                    "userTags": {"21": {"name": "KADEN", "affiliatedTag": "10"}},
                    "exceptionRules": [{"aid": "1"}, {"aid": "2"}],
                    "policyRules": [
                        {
                            "pid": "739",
                            "action": "block",
                            "target": "00:08:9B:FB:01:D9",
                            "type": "mac",
                            "direction": "bidirection",
                            "disabled": "1",
                            "purpose": "dap",
                        },
                        {
                            "pid": "738",
                            "action": "allow",
                            "target": "dap_00089bfb01d9",
                            "type": "category",
                            "direction": "outbound",
                            "disabled": "0",
                            "purpose": "dap",
                            "scope": ["00:08:9B:FB:01:D9"],
                        },
                        {
                            "pid": "737",
                            "action": "block",
                            "target": "5799d896-5e0f-40a5-a776-38a5d7746204",
                            "type": "network",
                            "direction": "bidirection",
                            "disabled": "0",
                        },
                        {
                            "pid": "736",
                            "action": "block",
                            "target": "TAG",
                            "type": "mac",
                            "direction": "bidirection",
                            "disabled": "0",
                            "tag": ["tag:12"],
                        },
                        {
                            "pid": "735",
                            "action": "allow",
                            "target": "spotify.com",
                            "type": "dns",
                            "direction": "outbound",
                            "disabled": "0",
                            "tag": ["tag:10"],
                        },
                        {
                            "pid": "734",
                            "action": "block",
                            "target": "social",
                            "type": "category",
                            "direction": "bidirection",
                            "disabled": "0",
                            "tag": ["tag:12"],
                            "activatedTime": "1774299013",
                            "expire": 3600,
                            "autoDeleteWhenExpires": "1",
                            "dnsmasq_only": True,
                        },
                    ],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    rules = snapshot.policy_rules
    assert len(rules) == 6
    assert snapshot.appliance_identity == FirewallaApplianceIdentityInput(
        host="192.168.200.1",
        group_name="Firewalla",
        device_name=None,
        model="gold",
        serial_number="serial-123",
        software_version="1.0.0",
    )
    assert snapshot.exception_rule_count == 2
    assert snapshot.appliance_runtime.booting_complete is True
    assert snapshot.appliance_runtime.dist_codename == "bionic"
    assert snapshot.appliance_runtime.cloud_connected is True
    assert snapshot.appliance_runtime.ddns == "box.example.firewalla.org"
    assert snapshot.appliance_runtime.firmware_release_type == "alpha"
    assert snapshot.appliance_runtime.timezone_name == "America/New_York"
    assert snapshot.appliance_runtime.public_ip == "23.245.207.179"
    assert snapshot.appliance_runtime.public_ips == {"eth0": "23.245.207.179"}
    assert snapshot.appliance_runtime.cpu_usage_1m == 42.1
    assert snapshot.appliance_runtime.memory_usage_ratio == 0.7638814708714687
    assert snapshot.appliance_runtime.total_memory_mb == 3861.65625
    assert snapshot.appliance_runtime.uptime_seconds == 22690936
    assert snapshot.appliance_runtime.disk_usages == (
        FirewallaDiskUsageInput(
            mount="/", capacity_ratio=0.29, used_bytes=None, size_bytes=None
        ),
        FirewallaDiskUsageInput(
            mount="/boot", capacity_ratio=0.18, used_bytes=None, size_bytes=None
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
            mount="/log", capacity_ratio=0.8, used_bytes=None, size_bytes=None
        ),
        FirewallaDiskUsageInput(
            mount="/data", capacity_ratio=0.06, used_bytes=None, size_bytes=None
        ),
        FirewallaDiskUsageInput(
            mount="/home", capacity_ratio=0.62, used_bytes=None, size_bytes=None
        ),
    )
    assert snapshot.speed_test_results[1] == FirewallaSpeedTestRecord(
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
        wan_uuid="wan-1",
    )
    assert snapshot.speed_test_results[0].wan_uuid == "wan-2"
    assert rules[0].rule_id == "739"
    assert rules[0].enabled is False
    assert rules[0].target_name == "Kitchen speaker"
    assert rules[1].rule_id == "738"
    assert rules[1].enabled is True
    assert rules[1].scope == ("00:08:9B:FB:01:D9",)
    assert rules[1].target_name == "DAP - 00:08:9B:FB:01:D9"
    assert rules[2].target_name == "VLAN10 CORE"
    assert rules[3].target_name == "Quarantine"
    assert rules[4].applies_to == ("KADEN's Devices (KADEN)",)
    assert rules[5].target_name == "social"
    assert rules[5].tag_refs == ("tag:12",)
    assert rules[5].activated_time == 1774299013.0
    assert rules[5].expire_seconds == 3600
    assert rules[5].expires_at == 1774302613.0
    assert rules[5].auto_delete_when_expires is True
    assert rules[5].dnsmasq_only is True
    assert rules[5].is_temporary is True
    assert snapshot.groups == (
        FirewallaGroupRuntime(group_id="10", name="KADEN's Devices"),
        FirewallaGroupRuntime(group_id="12", name="Quarantine"),
    )


@pytest.mark.asyncio
async def test_get_runtime_snapshot_normalizes_host_inventory() -> None:
    """Test runtime snapshots preserve normalized host inventory.

    This includes standalone VPN peer host records.
    """
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(
                return_value={
                    "groupName": "Firewalla",
                    "model": "gold",
                    "cpuid": "serial-123",
                    "longVersion": "1.0.0",
                    "networkConfig": {
                        "dhcp": {"bond0.10": {"searchDomain": ["int.ccpk.us"]}},
                        "interface": {
                            "bond": {
                                "bond0.10": {
                                    "meta": {
                                        "name": "VLAN10 CORE",
                                        "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
                                    }
                                }
                            }
                        },
                    },
                    "networkProfiles": {
                        "5799d896-5e0f-40a5-a776-38a5d7746204": {"intf": "bond0.10"}
                    },
                    "tags": {
                        "10": {"name": "KADEN's Devices"},
                    },
                    "userTags": {"21": {"name": "KADEN", "affiliatedTag": "10"}},
                    "deviceTags": {
                        "43": {"name": "phone"},
                    },
                    "hosts": [
                        {
                            "mac": "AA:BB:CC:DD:EE:FF",
                            "name": "kaden-phone",
                            "bname": "Kaden Phone",
                            "localDomain": "kaden-phone",
                            "ip": "192.168.200.25",
                            "lastActive": 1774287984.272,
                            "flowsummary": {"inbytes": 1234, "outbytes": 5678},
                            "intf": "5799d896-5e0f-40a5-a776-38a5d7746204",
                            "tags": ["10"],
                            "deviceTags": ["43"],
                            "stale": False,
                            "policy": {
                                "vpnClient": {
                                    "profileId": "profile-1",
                                    "state": True,
                                }
                            },
                        },
                        {
                            "mac": "wg_peer:test-peer",
                            "bname": "WireGuard Kaden",
                            "ip": "10.42.0.2",
                            "lastActive": "1774287000.5",
                            "flowsummary": {"inbytes": "99", "outbytes": "100"},
                            "intf": "5799d896-5e0f-40a5-a776-38a5d7746204",
                            "stale": False,
                        },
                    ],
                    "policyRules": [],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    assert snapshot.hosts == (
        FirewallaHostRuntime(
            mac="AA:BB:CC:DD:EE:FF",
            host_name="Kaden Phone",
            dns_hostname="kaden-phone",
            dns_domain="int.ccpk.us",
            dns_fqdn="kaden-phone.int.ccpk.us",
            dhcp_name=None,
            ip_address="192.168.200.25",
            group_name="KADEN's Devices (KADEN)",
            network_name="VLAN10 CORE",
            connection_type="phone",
            last_active=1774287984.272,
            download_bytes=1234,
            upload_bytes=5678,
            stale=False,
            vpn_client=FirewallaHostVpnClient(profile_id="profile-1", state=True),
            group_ids=("10",),
        ),
        FirewallaHostRuntime(
            mac="wg_peer:test-peer",
            host_name="WireGuard Kaden",
            dns_domain="int.ccpk.us",
            ip_address="10.42.0.2",
            group_name=None,
            network_name="VLAN10 CORE",
            connection_type=None,
            last_active=1774287000.5,
            download_bytes=99,
            upload_bytes=100,
            stale=False,
            vpn_client=None,
        ),
    )


@pytest.mark.asyncio
async def test_get_runtime_snapshot_prefers_customized_dns_hostname() -> None:
    """Test host normalization prefers one explicit DNS override over other names."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(
                return_value={
                    "groupName": "Firewalla",
                    "model": "gold",
                    "cpuid": "serial-123",
                    "longVersion": "1.0.0",
                    "networkConfig": {
                        "dhcp": {"bond0.10": {"searchDomain": ["int.ccpk.us"]}},
                        "interface": {
                            "bond": {
                                "bond0.10": {
                                    "meta": {
                                        "name": "VLAN10 CORE",
                                        "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
                                    },
                                }
                            }
                        },
                    },
                    "networkProfiles": {
                        "5799d896-5e0f-40a5-a776-38a5d7746204": {"intf": "bond0.10"}
                    },
                    "deviceTags": {
                        "43": {"name": "phone"},
                    },
                    "hosts": [
                        {
                            "mac": "EC:0D:51:CC:BA:BC",
                            "name": "Chads-Phone",
                            "bname": "Chads-Phone",
                            "dhcpName": "Chads-Phone",
                            "localDomain": "chads-phone",
                            "userLocalDomain": "chads-phone2",
                            "ip": "192.168.202.101",
                            "lastActive": 1774287984.272,
                            "flowsummary": {"inbytes": 1234, "outbytes": 5678},
                            "intf": "5799d896-5e0f-40a5-a776-38a5d7746204",
                            "deviceTags": ["43"],
                            "stale": False,
                        },
                        {
                            "mac": "00:18:DD:05:5A:37",
                            "name": "HDHR",
                            "bname": "HDHR-1055A37C",
                            "dhcpName": "HDHR-1055A37C",
                            "localDomain": "hdhr",
                            "ip": "192.168.202.50",
                            "lastActive": 1774287000.5,
                            "flowsummary": {"inbytes": "99", "outbytes": "100"},
                            "intf": "5799d896-5e0f-40a5-a776-38a5d7746204",
                            "stale": False,
                        },
                    ],
                    "policyRules": [],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    assert snapshot.hosts == (
        FirewallaHostRuntime(
            mac="EC:0D:51:CC:BA:BC",
            host_name="Chads-Phone",
            dns_hostname="chads-phone2",
            dns_domain="int.ccpk.us",
            dns_fqdn="chads-phone2.int.ccpk.us",
            dhcp_name="Chads-Phone",
            ip_address="192.168.202.101",
            group_name=None,
            network_name="VLAN10 CORE",
            connection_type="phone",
            last_active=1774287984.272,
            download_bytes=1234,
            upload_bytes=5678,
            stale=False,
            vpn_client=None,
        ),
        FirewallaHostRuntime(
            mac="00:18:DD:05:5A:37",
            host_name="HDHR",
            dns_hostname="hdhr",
            dns_domain="int.ccpk.us",
            dns_fqdn="hdhr.int.ccpk.us",
            dhcp_name="HDHR-1055A37C",
            ip_address="192.168.202.50",
            group_name=None,
            network_name="VLAN10 CORE",
            connection_type=None,
            last_active=1774287000.5,
            download_bytes=99,
            upload_bytes=100,
            stale=False,
            vpn_client=None,
        ),
    )


@pytest.mark.asyncio
async def test_get_runtime_snapshot_derives_user_totals_and_group_links() -> None:
    """Test user normalization derives aggregate totals and preserves group links."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(
                return_value={
                    "groupName": "Firewalla",
                    "model": "gold",
                    "cpuid": "serial-123",
                    "longVersion": "1.0.0",
                    "tags": {
                        "11": {"name": "PAYTON's Devices"},
                    },
                    "hosts": [
                        {
                            "mac": "AA:BB:CC:DD:EE:23",
                            "name": "Payton iPad",
                            "tags": ["11"],
                        }
                    ],
                    "userTags": {
                        "23": {
                            "name": "PAYTON",
                            "affiliatedTag": "11",
                            "appTimeUsageToday": {
                                "instagram": {
                                    "category": "social",
                                    "totalMins": 42,
                                    "uniqueMins": 40,
                                },
                                "facebook": {
                                    "category": "social",
                                    "totalMins": 2,
                                    "uniqueMins": 2,
                                },
                            },
                        }
                    },
                    "policyRules": [],
                    "exceptionRules": [],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    assert snapshot.hosts == (
        FirewallaHostRuntime(
            mac="AA:BB:CC:DD:EE:23",
            host_name="Payton iPad",
            dns_hostname="Payton iPad",
            dns_fqdn="Payton iPad",
            ip_address=None,
            group_name="PAYTON's Devices (PAYTON)",
            network_name=None,
            connection_type=None,
            last_active=None,
            download_bytes=None,
            upload_bytes=None,
            stale=None,
            vpn_client=None,
            group_ids=("11",),
        ),
    )
    assert snapshot.users == (
        FirewallaUserRuntime(
            user_id="23",
            name="PAYTON",
            affiliated_group_id="11",
            affiliated_group_name="PAYTON's Devices",
            total_minutes_today=44,
            unique_minutes_today=42,
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
            ),
        ),
    )


@pytest.mark.asyncio
async def test_get_runtime_snapshot_prefers_internet_usage_totals_for_users() -> None:
    """Test user normalization prefers internet-time totals over app totals."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(
                return_value={
                    "groupName": "Firewalla",
                    "model": "gold",
                    "cpuid": "serial-123",
                    "longVersion": "1.0.0",
                    "userTags": {
                        "21": {
                            "name": "KADEN",
                            "affiliatedTag": "10",
                            "internetTimeUsageToday": {
                                "totalMins": 99,
                                "uniqueMins": 99,
                            },
                            "appTimeUsageToday": {
                                "youtube": {
                                    "category": "av",
                                    "totalMins": 56,
                                    "uniqueMins": 56,
                                },
                                "facebook": {
                                    "category": "social",
                                    "totalMins": 2,
                                    "uniqueMins": 2,
                                },
                                "totalMins": 58,
                                "uniqueMins": 58,
                            },
                        }
                    },
                    "policyRules": [],
                    "exceptionRules": [],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    assert snapshot.users == (
        FirewallaUserRuntime(
            user_id="21",
            name="KADEN",
            affiliated_group_id="10",
            affiliated_group_name=None,
            total_minutes_today=99,
            unique_minutes_today=99,
            app_usage_today=(
                FirewallaUserAppUsage(
                    app_id="youtube",
                    category="av",
                    total_minutes=56,
                    unique_minutes=56,
                ),
                FirewallaUserAppUsage(
                    app_id="facebook",
                    category="social",
                    total_minutes=2,
                    unique_minutes=2,
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_get_runtime_snapshot_omits_latest_speed_test_without_success() -> None:
    """Test missing or failed speed tests produce a no-data speed-test state."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(
                return_value={
                    "groupName": "Firewalla",
                    "device": "Firewalla",
                    "bootingComplete": False,
                    "cloudConnected": False,
                    "sysMetrics": {
                        "cpuUsage1": [
                            {"user": 10, "sys": 5, "iowait": 0},
                            {"user": 20, "sys": 10, "iowait": 0},
                        ],
                        "memUsage": 0.25,
                        "totalMem": 1000,
                    },
                    "internetSpeedtestResults": [
                        {
                            "manual": False,
                            "success": False,
                            "timestamp": 1774300000,
                        }
                    ],
                    "policyRules": [],
                    "exceptionRules": [],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    assert snapshot.appliance_runtime.booting_complete is False
    assert snapshot.appliance_runtime.cloud_connected is False
    assert snapshot.appliance_runtime.cpu_usage_1m == 22.5
    assert snapshot.appliance_runtime.memory_usage_ratio == 0.25
    assert snapshot.appliance_runtime.total_memory_mb == 1000
    assert snapshot.appliance_runtime.uptime_seconds is None
    assert snapshot.speed_test_results == (
        FirewallaSpeedTestRecord(
            tested_at_timestamp=1774300000,
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
    )


@pytest.mark.asyncio
async def test_async_wake_host_sends_host_targeted_command() -> None:
    """Test Wake-on-LAN sends the captured host-targeted command shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(return_value={"ok": True}),
        ) as mock_send:
            response = await client.async_wake_host("00:AA:BB:CC:DD:26")

    assert response == {"ok": True}
    assert mock_send.await_args.kwargs == {
        "message_type": "cmd",
        "data": {"item": "wol:wake"},
        "target": "00:AA:BB:CC:DD:26",
    }


@pytest.mark.asyncio
async def test_async_set_host_policy_sends_host_targeted_policy_write() -> None:
    """Test host policy writes use the captured host-targeted set shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(return_value={"ok": True}),
        ) as mock_send:
            response = await client.async_set_host_policy(
                "00:AA:BB:CC:DD:26",
                {"devicePresence": True},
            )

    assert response == {"ok": True}
    assert mock_send.await_args.kwargs == {
        "message_type": "set",
        "data": {
            "item": "policy",
            "value": {"devicePresence": True},
        },
        "target": "00:AA:BB:CC:DD:26",
    }


@pytest.mark.asyncio
async def test_async_set_host_name_sends_host_targeted_write_and_accepts_null_ack() -> (
    None
):
    """Test host rename uses the captured host-targeted item=host write."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value=None),
        ) as mock_send:
            response = await client.async_set_host_name(
                "00:AA:BB:CC:DD:26",
                "Plex Server Renamed",
            )

    assert response == {}
    assert mock_send.await_args.kwargs == {
        "message_type": "set",
        "data": {
            "item": "host",
            "value": {"name": "Plex Server Renamed"},
        },
        "target": "00:AA:BB:CC:DD:26",
    }


@pytest.mark.asyncio
async def test_async_set_host_dns_hostname_sends_hostdomain_write_and_accepts_null_ack() -> (
    None
):
    """Test DNS hostname override uses the captured hostDomain write."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value=None),
        ) as mock_send:
            response = await client.async_set_host_dns_hostname(
                "00:AA:BB:CC:DD:26",
                "plex.server.3",
            )

    assert response == {}
    assert mock_send.await_args.kwargs == {
        "message_type": "set",
        "data": {
            "item": "hostDomain",
            "value": {"customizeDomainName": "plex.server.3"},
        },
        "target": "00:AA:BB:CC:DD:26",
    }


@pytest.mark.asyncio
async def test_async_set_host_device_type_sends_feedback_write_and_accepts_null_ack() -> (
    None
):
    """Test device type override uses the captured feedback write."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value=None),
        ) as mock_send:
            response = await client.async_set_host_device_type(
                "00:AA:BB:CC:DD:26",
                "tablet",
            )

    assert response == {}
    assert mock_send.await_args.kwargs == {
        "message_type": "set",
        "data": {
            "item": "feedback",
            "value": {
                "key": "device.detect",
                "target": "00:AA:BB:CC:DD:26",
                "value": {"type": "tablet"},
            },
        },
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_create_rule_sends_confirmed_persistent_payload() -> None:
    """Test rule creation uses the confirmed persistent mutation shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        template = FirewallaRuleTemplate(
            source_rule_id="744",
            name="block category social for AV_SMART_TV",
            action="block",
            target="social",
            target_type="category",
            tag_refs=("tag:17",),
            dnsmasq_only=True,
        )

        with (
            patch(
                "custom_components.firewalla_local.api.client.time.time",
                return_value=1774303259.8190122,
            ),
            patch.object(
                client, "_async_send_local_message", AsyncMock(return_value={})
            ) as mock_send,
        ):
            await client.async_create_rule(template)

    assert mock_send.await_args.kwargs == {
        "message_type": "cmd",
        "data": {
            "item": "policy:create",
            "value": {
                "action": "block",
                "appTimeUsage": {},
                "disturbLevel": "",
                "disturbMethod": {},
                "dnsmasq_only": True,
                "duration": "",
                "scope": [],
                "tag": ["tag:17"],
                "target": "social",
                "trust": "",
                "type": "category",
                "updatedTime": 1774303259.8190122,
                "useBf": True,
            },
        },
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_delete_rule_sends_confirmed_delete_payload() -> None:
    """Test rule deletion uses the confirmed delete mutation shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )

        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(return_value={}),
        ) as mock_send:
            await client.async_delete_rule("744")

    assert mock_send.await_args.kwargs == {
        "message_type": "cmd",
        "data": {"item": "policy:delete", "value": {"policyID": "744"}},
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_update_rule_sends_live_rule_payload_with_changed_state() -> None:
    """Test rule updates preserve the live payload and only toggle state fields."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        rule = FirewallaPolicyRule(
            rule_id="211",
            action="allow",
            target="spotify.com",
            target_type="dns",
            direction="outbound",
            enabled=False,
            purpose=None,
            scope=(),
            tag_refs=("tag:10",),
            applies_to=("KADEN's Devices (KADEN)",),
            dnsmasq_only=False,
            raw_update_payload={
                "pid": "211",
                "action": "allow",
                "direction": "outbound",
                "disabled": 1,
                "dnsmasq_only": False,
                "idleTs": "1774324800",
                "tag": ["tag:10"],
                "target": "spotify.com",
                "timestamp": "1693953160.462",
                "trust": True,
                "type": "dns",
                "upnp": False,
                "useBf": "",
            },
        )

        with (
            patch(
                "custom_components.firewalla_local.api.client.time.time",
                return_value=1774310993.8565822,
            ),
            patch.object(
                client, "_async_send_local_message", AsyncMock(return_value={})
            ) as mock_send,
        ):
            await client.async_update_rule(rule, enabled=True)

    assert mock_send.await_args.kwargs == {
        "message_type": "cmd",
        "data": {
            "item": "policy:update",
            "value": {
                "pid": "211",
                "action": "allow",
                "direction": "outbound",
                "disabled": 0,
                "dnsmasq_only": False,
                "idleTs": "",
                "tag": ["tag:10"],
                "target": "spotify.com",
                "timestamp": "1693953160.462",
                "trust": True,
                "type": "dns",
                "updatedTime": 1774310993.8565822,
                "upnp": False,
                "useBf": "",
            },
        },
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_update_rule_control_only_resumes_existing_rule() -> None:
    """Test sparse control-only update sends only pause or resume fields."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )

        with (
            patch(
                "custom_components.firewalla_local.api.client.time.time",
                return_value=1774310993.8565822,
            ),
            patch.object(
                client, "_async_send_local_message", AsyncMock(return_value={})
            ) as mock_send,
        ):
            await client.async_update_rule_control_only("211", enabled=True)

    assert mock_send.await_args.kwargs == {
        "message_type": "cmd",
        "data": {
            "item": "policy:update",
            "value": {
                "pid": "211",
                "disabled": 0,
                "idleTs": "",
                "updatedTime": 1774310993.8565822,
            },
        },
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_get_runtime_init_payload_retries_once_on_unauthorized() -> None:
    """Test a single 401 is retried before decoding the local response."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        encrypted_message = aes256_cbc_encrypt_to_base64(
            json.dumps(
                {
                    "code": 200,
                    "data": {
                        "groupName": "Firewalla",
                        "model": "gold",
                        "cpuid": "serial-123",
                        "longVersion": "1.0.0",
                    },
                },
                separators=(",", ":"),
            ),
            TEST_SYMMETRIC_KEY,
        )

        with patch.object(
            client,
            "_async_post_local_payload",
            AsyncMock(
                side_effect=[
                    (401, "unauthorized"),
                    (200, json.dumps({"message": encrypted_message})),
                ]
            ),
        ) as mock_post:
            payload = await client.async_get_runtime_init_payload()

    assert payload["groupName"] == "Firewalla"
    assert mock_post.await_count == 2


@pytest.mark.asyncio
async def test_get_runtime_init_payload_raises_auth_error_after_retry_401s() -> None:
    """Test repeated 401 responses raise a typed auth error."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )

        with (
            patch.object(
                client,
                "_async_post_local_payload",
                AsyncMock(side_effect=[(401, "unauthorized"), (401, "unauthorized")]),
            ) as mock_post,
            pytest.raises(FirewallaAuthError),
        ):
            await client.async_get_runtime_init_payload()

    assert mock_post.await_count == 2


@pytest.mark.asyncio
async def test_get_usage_history_payload_sends_scoped_get_request() -> None:
    """Test usage-history pulls use the confirmed scoped get shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )

        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(return_value={"ok": True}),
        ) as mock_send:
            await client.async_get_usage_history_payload(
                scope_type="tag",
                target="10",
                begin_timestamp=1_774_065_600,
                end_timestamp=1_774_670_400,
                granularity="day",
                app_ids=("internet", "facebook"),
            )

    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {
            "item": "appTimeUsage",
            "type": "tag",
            "begin": 1_774_065_600,
            "end": 1_774_670_400,
            "granularity": "day",
            "apps": ["internet", "facebook"],
        },
        "target": "10",
    }


@pytest.mark.asyncio
async def test_get_wan_events_payload_accepts_list_response() -> None:
    """Test WAN events pulls accept the confirmed list-shaped data payload."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        encrypted_message = aes256_cbc_encrypt_to_base64(
            json.dumps(
                {
                    "code": 200,
                    "data": [
                        {
                            "event_type": "action",
                            "action_type": "ping_RTT",
                            "action_value": 1,
                            "labels": {
                                "rtt": 53.2,
                                "rttLimit": 35.3,
                                "target": "1.1.1.1",
                                "wan_intf_name": "WAN-ONE",
                                "wan_intf_uuid": "wan-1",
                            },
                            "ts": 1774036038371,
                        }
                    ],
                },
                separators=(",", ":"),
            ),
            TEST_SYMMETRIC_KEY,
        )

        with patch.object(
            client,
            "_async_post_local_payload",
            AsyncMock(return_value=(200, json.dumps({"message": encrypted_message}))),
        ):
            payload = await client.async_get_wan_events_payload(
                limit_count=100,
                limit_offset=0,
            )

    assert payload == [
        {
            "event_type": "action",
            "action_type": "ping_RTT",
            "action_value": 1,
            "labels": {
                "rtt": 53.2,
                "rttLimit": 35.3,
                "target": "1.1.1.1",
                "wan_intf_name": "WAN-ONE",
                "wan_intf_uuid": "wan-1",
            },
            "ts": 1774036038371,
        }
    ]


@pytest.mark.asyncio
async def test_get_network_interface_payload_accepts_dict_response() -> None:
    """Test item=intf pulls accept the confirmed dict-shaped data payload."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )
        encrypted_message = aes256_cbc_encrypt_to_base64(
            json.dumps(
                {
                    "code": 200,
                    "data": {
                        "intf": "bond0.10",
                        "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
                        "monitoring": True,
                    },
                },
                separators=(",", ":"),
            ),
            TEST_SYMMETRIC_KEY,
        )

        with patch.object(
            client,
            "_async_post_local_payload",
            AsyncMock(return_value=(200, json.dumps({"message": encrypted_message}))),
        ):
            payload = await client.async_get_network_interface_payload(
                network_uuid="5799d896-5e0f-40a5-a776-38a5d7746204"
            )

    assert payload == {
        "intf": "bond0.10",
        "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
        "monitoring": True,
    }


@pytest.mark.asyncio
async def test_get_wan_events_payload_sends_paged_get_request() -> None:
    """Test WAN events pulls use the confirmed paged get shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )

        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value=[]),
        ) as mock_send:
            await client.async_get_wan_events_payload(limit_count=250, limit_offset=25)

    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {
            "item": "events",
            "value": {
                "limit_count": 250,
                "limit_offset": 25,
                "parse_json": True,
                "reverse": True,
            },
        },
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_get_network_interface_payload_sends_targeted_get_request() -> None:
    """Test item=intf pulls use the confirmed targeted get shape."""
    async with ClientSession() as session:
        client = FirewallaApiClient(
            session=session,
            host="192.168.200.1",
            gid="gid-123",
            eid="eid-123",
            aid="aid-123",
            symmetric_key=TEST_SYMMETRIC_KEY,
            device_name="Home Assistant",
        )

        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value={}),
        ) as mock_send:
            await client.async_get_network_interface_payload(
                network_uuid="5799d896-5e0f-40a5-a776-38a5d7746204"
            )

    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {"item": "intf"},
        "target": "5799d896-5e0f-40a5-a776-38a5d7746204",
    }
