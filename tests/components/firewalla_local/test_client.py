"""Tests for Firewalla Local client normalization."""

from __future__ import annotations

import json
import logging
from unittest.mock import ANY, AsyncMock, patch

import pytest
from aiohttp import ClientSession

from custom_components.firewalla_local.api.client import FirewallaApiClient
from custom_components.firewalla_local.api.crypto import aes256_cbc_encrypt_to_base64
from custom_components.firewalla_local.api.exceptions import (
    FirewallaAuthError,
    FirewallaLocalRuntimeNotReadyError,
    FirewallaProtocolError,
    FirewallaValidationError,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaDiskUsageInput,
    FirewallaGroupRuntime,
    FirewallaHostRuntime,
    FirewallaHostVpnClient,
    FirewallaInternetQualitySample,
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
async def test_runtime_init_payload_requests_inactive_hosts() -> None:
    """Test the runtime init request includes inactive hosts like the app."""
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
            await client.async_get_runtime_init_payload()

    assert mock_send.await_count == 1
    assert mock_send.await_args_list[0].kwargs == {
        "message_type": "init",
        "data": {"get": "0.0.0.0", "includeInactiveHosts": True},
        "target": "0.0.0.0",
        "log_level": logging.DEBUG,
    }


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
            AsyncMock(return_value=(200, json.dumps({"message": encrypted_response}))),
        ):
            await client.async_get_pairing_runtime_init_payload(log_as_info=True)

    assert (
        "Requesting Firewalla pairing init sequence from host 192.168.200.1"
        in caplog.text
    )
    assert (
        "Firewalla pairing init request metadata for host 192.168.200.1: "
        "aid present=True, device name=Home Assistant, timezone=UTC" in caplog.text
    )


@pytest.mark.asyncio
async def test_get_pairing_runtime_init_payload_uses_phone_like_sequence() -> None:
    """Test pairing-time init mirrors the observed phone request sequence."""
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
            AsyncMock(side_effect=[{"step": 1}, {"step": 2}, {"step": 3}]),
        ) as mock_send:
            payload = await client.async_get_pairing_runtime_init_payload()

    assert payload == {"step": 3}
    assert mock_send.await_count == 3
    assert mock_send.await_args_list[0].kwargs == {
        "message_type": "init",
        "data": {"COMMAND_TIMEOUT": 15, "get": "0.0.0.0"},
        "force_close": True,
        "target": "0.0.0.0",
        "log_level": logging.DEBUG,
    }
    expected_detail_data = {
        "dapOps": [{"body": {}, "key": "dapInfo", "method": "GET", "path": "/info"}],
        "fwapcOps": [
            {
                "body": {},
                "key": "stationControls",
                "method": "GET",
                "path": "/config/stations",
            },
            {
                "body": {},
                "key": "switchTopology",
                "method": "GET",
                "path": "/status/wired_station",
            },
            {
                "body": {},
                "key": "switchInfo",
                "method": "GET",
                "path": "/status/switch",
            },
            {
                "body": {},
                "key": "fwapcCountry",
                "method": "GET",
                "path": "/config/country",
            },
        ],
        "embeddedOps": [
            {
                "item": "events",
                "key": "latest24MainNetworkEvents",
                "target": "0.0.0.0",
                "value": {
                    "min": ANY,
                    "reverse": True,
                    "parse_json": True,
                    "filters": [
                        {
                            "event_type": "action",
                            "sub_type": "system_reboot",
                        },
                        {
                            "event_type": "state",
                            "sub_type": "dualwan_state",
                        },
                        {
                            "event_type": "state",
                            "sub_type": "wan_state",
                        },
                    ],
                },
            }
        ],
        "get": "0.0.0.0",
        "value": {},
    }
    assert mock_send.await_args_list[1].kwargs == {
        "message_type": "init",
        "data": expected_detail_data,
        "force_close": True,
        "target": "0.0.0.0",
        "log_level": logging.DEBUG,
    }
    assert mock_send.await_args_list[2].kwargs == {
        "message_type": "init",
        "data": expected_detail_data,
        "force_close": True,
        "target": "0.0.0.0",
        "log_level": logging.DEBUG,
    }


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
                    "userTags": {
                        "21": {
                            "name": "KADEN",
                            "affiliatedTag": "10",
                            "appTimeUsageToday": {
                                "instagram": {
                                    "category": "social",
                                    "totalMins": 12,
                                    "uniqueMins": 12,
                                }
                            },
                        }
                    },
                    "exceptionRules": [
                        {
                            "eid": "mute-1",
                            "aid": "alarm-1",
                            "alarm_type": "ALARM_VIDEO",
                        },
                        {"aid": "2"},
                    ],
                    "activeAlarmCount": 1,
                    "archivedAlarmCount": 2,
                    "pendingAlarmCount": 3,
                    "newAlarms": [
                        {
                            "aid": "alarm-1",
                            "alarmTimestamp": "1789047961.229",
                            "timestamp": "1789047799.2",
                            "device": "phone",
                            "message": "phone is watching video",
                            "state": "active",
                            "type": "ALARM_VIDEO",
                            "p.dest.category": "av",
                            "p.dest.domain": "example.com",
                            "p.dest.ip": "203.0.113.1",
                            "p.dest.app": "video-app",
                            "p.dest.country": "US",
                            "p.dest.latitude": "40.1",
                            "p.dest.longitude": "-73.9",
                            "p.intf.name": "Home",
                            "p.protocol": "tcp",
                            "p.severity": "high",
                        },
                        {"device": "malformed-without-id"},
                    ],
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
    assert len(snapshot.alarm_exceptions) == 1
    assert snapshot.alarm_exceptions[0].exception_id == "mute-1"
    assert snapshot.alarm_exceptions[0].alarm_id == "alarm-1"
    assert snapshot.active_alarm_count == 1
    assert snapshot.archived_alarm_count == 2
    assert snapshot.pending_alarm_count == 3
    assert len(snapshot.alarms) == 1
    alarm = snapshot.alarms[0]
    assert alarm.alarm_id == "alarm-1"
    assert alarm.alarm_type == "ALARM_VIDEO"
    assert alarm.fired_at == 1789047961.229
    assert alarm.remote_category == "av"
    assert alarm.remote_host == "example.com"
    assert alarm.remote_ip == "203.0.113.1"
    assert alarm.raw_payload["p.dest.latitude"] == "40.1"
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
        # The box sends -1 for "not measured", so the model holds absent rather
        # than an impossible negative loss.
        packet_loss_percent=None,
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
    assert rules[4].applies_to == ("KADEN",)
    assert rules[5].target_name == "social"
    assert rules[5].tag_refs == ("tag:12",)
    assert rules[5].activated_time == 1774299013.0
    assert rules[5].expire_seconds == 3600
    assert rules[5].expires_at == 1774302613.0
    assert rules[5].auto_delete_when_expires is True
    assert rules[5].dnsmasq_only is True
    assert rules[5].is_temporary is True
    assert snapshot.groups == (
        FirewallaGroupRuntime(
            group_id="10",
            name="KADEN",
            kind="user",
            user_id="21",
        ),
        FirewallaGroupRuntime(group_id="12", name="Quarantine", kind="group"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_flow", "expected_destination", "expected_kind"),
    [
        pytest.param(
            {
                "ts": 1790990234.243,
                "device": "74:A7:EA:24:44:44",
                "deviceIP": "192.168.202.43",
                "domain": "www.youtube.com",
                "port": 53,
                "protocol": "dns",
                "app": "youtube",
                "category": "av",
            },
            "www.youtube.com",
            "domain",
            id="dns_match_uses_the_domain",
        ),
        pytest.param(
            {
                "ts": 1791032490.245,
                "device": "C0:56:E3:AB:DB:DC",
                "deviceIP": "192.168.200.213",
                "host": "dev.us.ezviz7.com",
                "ip": "32.196.236.79",
                "port": 8555,
                "protocol": "tcp",
            },
            "dev.us.ezviz7.com",
            "host",
            id="host_wins_over_ip",
        ),
        pytest.param(
            {
                "ts": 1791032458.199,
                "device": "02:42:0B:3C:52:52",
                "ip": "148.59.129.29",
                "port": 48116,
                "protocol": "tcp",
            },
            "148.59.129.29",
            "ip",
            id="ip_only_match",
        ),
    ],
)
@pytest.mark.asyncio
async def test_rule_hits_are_normalized_with_one_destination(
    raw_flow: dict[str, object],
    expected_destination: str,
    expected_kind: str,
) -> None:
    """A rule's last matched flow resolves to one destination plus its kind.

    Firewalla reports the destination under `host`, `domain` or `ip` depending on
    how the rule matched, so the raw fields are collapsed into one destination so
    a caller does not have to know which family produced it.
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
                    "policyRules": [
                        {
                            "pid": "516",
                            "action": "block",
                            "target": "TLX-fw-youtube",
                            "type": "category",
                            "disabled": "0",
                            "hitCount": "26617",
                            "lastHitFlow": raw_flow,
                        }
                    ],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    rule = snapshot.policy_rules[0]
    assert rule.hit_count == 26617
    assert rule.last_hit is not None
    assert rule.last_hit.destination == expected_destination
    assert rule.last_hit.destination_kind == expected_kind
    assert rule.last_hit.device_id == raw_flow["device"]
    assert rule.last_hit.timestamp == raw_flow["ts"]


@pytest.mark.asyncio
async def test_a_rule_without_hits_reports_a_zero_count() -> None:
    """A rule the box reports no count for reads as 0, not null.

    The box writes an explicit `"0"` for some rules and omits the field for
    others, so omission is not a distinct "unknown" state as far as a tally is
    concerned. `hit_count` is therefore always a number, which keeps "never
    fired" readable as a comparison instead of a null check.

    `last_hit` stays null, because it describes one specific match rather than a
    count and there is no match to describe.
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
                    "policyRules": [
                        {
                            "pid": "672",
                            "action": "block",
                            "target": "66.132.172.137",
                            "type": "ip",
                            "disabled": "0",
                        }
                    ],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    rule = snapshot.policy_rules[0]
    assert rule.hit_count == 0
    assert rule.last_hit is None


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
                    "userTags": {
                        "21": {
                            "name": "KADEN",
                            "affiliatedTag": "10",
                            "appTimeUsageToday": {
                                "instagram": {
                                    "category": "social",
                                    "totalMins": 12,
                                    "uniqueMins": 12,
                                }
                            },
                        }
                    },
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
            host_name="kaden-phone",
            dns_hostname="kaden-phone",
            dns_domain="int.ccpk.us",
            dns_fqdn="kaden-phone.int.ccpk.us",
            dhcp_name=None,
            ip_address="192.168.200.25",
            group_name="KADEN",
            membership_kind="user",
            network_name="VLAN10 CORE",
            network_uuid="5799d896-5e0f-40a5-a776-38a5d7746204",
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
            network_uuid="5799d896-5e0f-40a5-a776-38a5d7746204",
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
            network_uuid="5799d896-5e0f-40a5-a776-38a5d7746204",
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
            network_uuid="5799d896-5e0f-40a5-a776-38a5d7746204",
            connection_type=None,
            last_active=1774287000.5,
            download_bytes=99,
            upload_bytes=100,
            stale=False,
            vpn_client=None,
        ),
    )


@pytest.mark.asyncio
async def test_get_runtime_snapshot_prefers_name_over_bname() -> None:
    """Test host normalization ignores backup names for primary host names."""
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
                    "hosts": [
                        {
                            "mac": "00:71:47:4D:A4:8B",
                            "name": "FTV-Veranda",
                            "bname": "Fire TV Veranda",
                            "dhcpName": "amazon-21315c414",
                            "localDomain": "ftv-veranda",
                            "ip": "192.168.202.47",
                            "lastActive": 1774287000.5,
                            "intf": "5799d896-5e0f-40a5-a776-38a5d7746204",
                            "stale": False,
                        }
                    ],
                    "policyRules": [],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    assert snapshot.hosts == (
        FirewallaHostRuntime(
            mac="00:71:47:4D:A4:8B",
            host_name="FTV-Veranda",
            dns_hostname="ftv-veranda",
            dns_domain="int.ccpk.us",
            dns_fqdn="ftv-veranda.int.ccpk.us",
            dhcp_name="amazon-21315c414",
            ip_address="192.168.202.47",
            group_name=None,
            network_name="VLAN10 CORE",
            network_uuid="5799d896-5e0f-40a5-a776-38a5d7746204",
            connection_type=None,
            last_active=1774287000.5,
            download_bytes=None,
            upload_bytes=None,
            stale=False,
            vpn_client=None,
        ),
    )


@pytest.mark.asyncio
async def test_get_runtime_snapshot_normalizes_wg_peers_into_host_inventory() -> None:
    """Test WireGuard peers outside hosts[] become watched-device host records."""
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
                        "interface": {
                            "wireguard": {
                                "wg0": {
                                    "meta": {
                                        "name": "WireGuard",
                                        "uuid": "2c30793a-f9ce-43c0-9e9e-c30115366b76",
                                    }
                                }
                            }
                        }
                    },
                    "tags": {
                        "60": {"name": "CHADS_PHONE"},
                    },
                    "hosts": [],
                    "wgPeers": [
                        {
                            "allowedIPs": ["192.168.250.199/32"],
                            "flowsummary": {
                                "inbytes": 41981924,
                                "outbytes": 5574375,
                            },
                            "intf": "wg0",
                            "lastActiveTimestamp": 1778687590,
                            "name": "chads-phone-wgvpn",
                            "policy": {"tags": ["60"]},
                            "uid": "peer-123",
                        }
                    ],
                    "policyRules": [],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    assert snapshot.hosts == (
        FirewallaHostRuntime(
            mac="wg_peer:peer-123",
            host_name="chads-phone-wgvpn",
            ip_address="192.168.250.199",
            group_name="CHADS_PHONE",
            membership_kind="group",
            network_name="WireGuard",
            network_uuid="wg0",
            connection_type="vpn",
            last_active=1778687590.0,
            download_bytes=41981924,
            upload_bytes=5574375,
            stale=None,
            group_ids=("60",),
        ),
    )


@pytest.mark.asyncio
async def test_get_runtime_snapshot_normalizes_awg_peers_into_host_inventory() -> None:
    """Test Amnezia WG peers outside hosts[] become watched-device host records."""
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
                        "interface": {
                            "amneziawg": {
                                "awg0": {
                                    "meta": {
                                        "name": "AmneziaWG",
                                        "uuid": "2c30793a-f9ce-43c0-9e9e-c30115366b76",
                                    }
                                }
                            }
                        }
                    },
                    "tags": {
                        "60": {"name": "CHADS_PHONE"},
                    },
                    "hosts": [],
                    "awgPeers": [
                        {
                            "allowedIPs": ["10.190.68.226/32"],
                            "flowsummary": {
                                "inbytes": 2276685,
                                "outbytes": 1243658,
                            },
                            "intf": "awg0",
                            "lastActiveTimestamp": 1786738739,
                            "name": "chads-phone-amvpn",
                            "policy": {"tags": ["60"]},
                            "uid": "peer-123",
                        }
                    ],
                    "policyRules": [],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    assert snapshot.hosts == (
        FirewallaHostRuntime(
            mac="awg_peer:peer-123",
            host_name="chads-phone-amvpn",
            ip_address="10.190.68.226",
            group_name="CHADS_PHONE",
            membership_kind="group",
            network_name="AmneziaWG",
            network_uuid="awg0",
            connection_type="vpn",
            last_active=1786738739.0,
            download_bytes=2276685,
            upload_bytes=1243658,
            stale=None,
            group_ids=("60",),
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
            group_name="PAYTON",
            membership_kind="user",
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
            affiliated_group_name="PAYTON",
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
            affiliated_group_name="KADEN",
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
async def test_get_runtime_snapshot_uses_user_names_and_app_names() -> None:
    """Test rule normalization prefers affiliated user names and app names."""
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
                        "10": {"name": "KADEN's Devices"},
                    },
                    "userTags": {
                        "21": {
                            "name": "KADEN",
                            "affiliatedTag": "10",
                            "appTimeUsageToday": {
                                "instagram": {
                                    "category": "social",
                                    "totalMins": 12,
                                    "uniqueMins": 12,
                                }
                            },
                        }
                    },
                    "policyRules": [
                        {
                            "pid": "741",
                            "action": "block",
                            "target": "TLX-fw-instagram",
                            "type": "category",
                            "direction": "outbound",
                            "disabled": "0",
                            "tag": ["tag:10"],
                            "app_name": "instagram",
                        }
                    ],
                    "exceptionRules": [],
                }
            ),
        ):
            snapshot = await client.async_get_runtime_snapshot()

    assert snapshot.policy_rules == (
        FirewallaPolicyRule(
            rule_id="741",
            action="block",
            target="TLX-fw-instagram",
            target_type="category",
            direction="outbound",
            enabled=True,
            purpose=None,
            scope=(),
            applies_to=("KADEN",),
            applies_to_kind=("user",),
            tag_refs=("tag:10",),
            target_name="Instagram",
            category="social",
            raw_update_payload={
                "pid": "741",
                "action": "block",
                "target": "TLX-fw-instagram",
                "type": "category",
                "direction": "outbound",
                "disabled": "0",
                "tag": ["tag:10"],
                "app_name": "instagram",
            },
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
async def test_async_delete_host_sends_box_targeted_delete_command() -> None:
    """Test host delete sends the captured box-targeted host:delete shape."""
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
            response = await client.async_delete_host("12:A9:78:EB:EA:02")

    assert response == {"ok": True}
    assert mock_send.await_args.kwargs == {
        "message_type": "cmd",
        "data": {"item": "host:delete", "value": {"mac": "12:A9:78:EB:EA:02"}},
        "target": "0.0.0.0",
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
async def test_async_set_ssid_paused_sends_full_network_config_write() -> None:
    """Test SSID pause uses the confirmed full-networkConfig set contract."""
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
        network_config_payload = {
            "apc": {"profile": {"uuid-1": {"ssid": "Guest", "paused": True}}},
            "ts": 1788412692554,
        }
        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(return_value={"ncid": "abc123"}),
        ) as mock_send:
            response = await client.async_set_ssid_paused(
                network_config_payload=network_config_payload,
            )

    assert response == {"ncid": "abc123"}
    assert mock_send.await_args.kwargs == {
        "message_type": "set",
        "data": {
            "COMMAND_TIMEOUT": 90,
            "LAN_ONLY": 1,
            "item": "networkConfig",
            "value": {"config": network_config_payload},
        },
        "target": "0.0.0.0",
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
async def test_async_set_host_dns_hostname_uses_hostdomain_write() -> None:
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
async def test_async_set_host_device_type_uses_feedback_write() -> None:
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
async def test_create_rule_returns_new_rule_id() -> None:
    """Test rule creation returns the box-reported rule id for undo."""
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
            source_rule_id="1728",
            name="vimeo.com",
            action="block",
            target="vimeo.com",
            target_type="dns",
            scope=("0C:85:E1:B0:1D:1C",),
            dnsmasq_only=True,
            alarm_id="1728",
        )

        with patch.object(
            client,
            "_async_send_local_message",
            AsyncMock(return_value={"policy": {"pid": "652"}}),
        ) as mock_send:
            new_rule_id = await client.async_create_rule(template)

    assert new_rule_id == "652"
    assert mock_send.await_args.kwargs["data"]["value"]["aid"] == "1728"


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
async def test_get_alarms_sends_both_page_size_keys() -> None:
    """The active alarm item reads count while tolerating other page keys."""
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
            AsyncMock(return_value={"alarms": [{"aid": "alarm-1"}, "invalid"]}),
        ) as mock_send:
            alarms = await client.async_get_alarms(limit=17, offset=4)

    assert alarms == ({"aid": "alarm-1"},)
    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {
            "item": "alarms",
            "value": {"count": 17, "limit": 17, "offset": 4},
        },
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_get_archived_alarms_uses_archived_item_and_offset() -> None:
    """The archived alarm item accepts limit and offset on the local runtime."""
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
            AsyncMock(return_value={"alarms": [{"aid": "archived-1"}]}),
        ) as mock_send:
            alarms = await client.async_get_archived_alarms(limit=23, offset=46)

    assert alarms == ({"aid": "archived-1"},)
    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {
            "item": "archivedAlarms",
            "value": {"count": 23, "limit": 23, "offset": 46},
        },
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_get_alarm_detail_uses_alarm_id() -> None:
    """The per-alarm enrichment item is queried by the aid field."""
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
            AsyncMock(return_value={"aid": "alarm-1", "p.severity": "high"}),
        ) as mock_send:
            detail = await client.async_get_alarm_detail("alarm-1")

    assert detail["p.severity"] == "high"
    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {"item": "alarmDetail", "value": {"alarmID": "alarm-1"}},
        "target": "0.0.0.0",
    }


@pytest.mark.asyncio
async def test_alarm_commands_use_verified_command_items() -> None:
    """Alarm writes use the confirmed command item names and payloads."""
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
            await client.async_archive_alarm("alarm-1")
            await client.async_delete_all_alarms(archived=True)
            await client.async_create_alarm_exception({"type": "ALARM_GAME"})
            await client.async_delete_alarm_exception("exception-1")

    assert [call.kwargs for call in mock_send.await_args_list] == [
        {
            "message_type": "cmd",
            "data": {"item": "alarm:ignore", "value": {"alarmID": "alarm-1"}},
            "target": "0.0.0.0",
        },
        {
            "message_type": "cmd",
            "data": {"item": "alarm:deleteArchivedAll", "value": {}},
            "target": "0.0.0.0",
        },
        {
            "message_type": "cmd",
            "data": {"item": "exception:create", "value": {"type": "ALARM_GAME"}},
            "target": "0.0.0.0",
        },
        {
            "message_type": "cmd",
            "data": {
                "item": "exception:delete",
                "value": {"exceptionID": "exception-1"},
            },
            "target": "0.0.0.0",
        },
    ]


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
    """Test item=intf pulls use the confirmed targeted get shapes.

    Two requests, because the box returns two disjoint family sets: a bare read
    carries the app and category families, and adding `apiVer: 2` plus `local`
    swaps them for the eleven traffic families. Asserting only the first request
    is what let the ranking families go unrequested -- an empty top-talker list
    looked like a quiet network rather than a missing call.
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
            "_async_send_local_message_data",
            AsyncMock(return_value={}),
        ) as mock_send:
            await client.async_get_network_interface_payload(
                network_uuid="5799d896-5e0f-40a5-a776-38a5d7746204"
            )

    assert mock_send.await_count == 2
    first, second = (call.kwargs for call in mock_send.await_args_list)
    assert first == {
        "message_type": "get",
        "data": {"item": "intf"},
        "target": "5799d896-5e0f-40a5-a776-38a5d7746204",
    }
    assert second == {
        "message_type": "get",
        "data": {"item": "intf", "apiVer": 2, "local": True},
        "target": "5799d896-5e0f-40a5-a776-38a5d7746204",
    }
    # The window is deliberately absent: measured, sending start/end on this call
    # reduces the response from 11 families to 3.
    assert "start" not in second["data"]
    assert "end" not in second["data"]


@pytest.mark.asyncio
async def test_network_interface_payload_merges_both_family_sets() -> None:
    """Test the two intf responses are merged rather than one chosen.

    The v1 and v2 payloads are complementary, not alternatives: merging them is
    what gives one view both the app/category families and the traffic rankings.
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

        app_payload = {
            "uuid": "net-1",
            "flows": {"appDetails": {"youtube": []}, "recent": []},
            "hosts": {"AA:BB": {"download": 0}},
        }
        traffic_payload = {
            "uuid": "net-1",
            "flows": {"download": [{"device": "AA:BB", "count": "10"}], "upload": []},
        }

        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(side_effect=[app_payload, traffic_payload]),
        ):
            merged = await client.async_get_network_interface_payload(
                network_uuid="net-1"
            )

    assert sorted(merged["flows"]) == ["appDetails", "download", "recent", "upload"]
    # Non-family keys come from the primary payload untouched.
    assert merged["hosts"] == {"AA:BB": {"download": 0}}


@pytest.mark.asyncio
async def test_network_interface_payload_survives_a_failed_traffic_read() -> None:
    """Test a failing ranking read degrades instead of failing the refresh.

    The app and category families are still useful on their own, so a network
    whose v2 read fails must keep its v1 data rather than losing the whole view.
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

        app_payload = {"uuid": "net-1", "flows": {"appDetails": {}}}
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(
                side_effect=[app_payload, FirewallaProtocolError("no traffic data")]
            ),
        ):
            payload = await client.async_get_network_interface_payload(
                network_uuid="net-1"
            )

    assert payload == app_payload


@pytest.mark.asyncio
async def test_get_internet_quality_payload_sends_get_request() -> None:
    """Test networkMonitorData pulls use the confirmed get shape."""
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
            await client.async_get_internet_quality_payload()

    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {"item": "networkMonitorData", "value": {}},
        "target": "0.0.0.0",
    }


def test_extract_internet_quality_samples_parses_buckets() -> None:
    """Test extraction parses the metric key and stat buckets."""
    client = FirewallaApiClient(
        session=None,  # type: ignore[arg-type]
        host="192.168.200.1",
        gid="gid-123",
        eid="eid-123",
        aid="aid-123",
        symmetric_key=TEST_SYMMETRIC_KEY,
        device_name="Home Assistant",
    )
    samples = client._extract_internet_quality_samples(
        {
            "metric:monitor:raw:ping:1.1.1.1:8d5a7f20-2923-49a3-8e2b-338f9428a632": {
                "1788961500": {
                    "stat": {
                        "lossrate": 0,
                        "max": 73.7,
                        "mean": 22.2,
                        "median": 21,
                        "min": 19.2,
                    }
                },
                "1788962400": {
                    "stat": {
                        "lossrate": 0.0017,
                        "max": 45,
                        "mean": 21.4,
                        "median": 20.4,
                        "min": 19.2,
                    }
                },
            }
        }
    )

    assert samples == (
        FirewallaInternetQualitySample(
            timestamp=1788961500.0,
            target="1.1.1.1",
            ping_latency_ms=22.2,
            ping_latency_max_ms=73.7,
            ping_latency_median_ms=21,
            ping_latency_min_ms=19.2,
            ping_packet_loss_percent=0.0,
            wan_uuid="8d5a7f20-2923-49a3-8e2b-338f9428a632",
        ),
        FirewallaInternetQualitySample(
            timestamp=1788962400.0,
            target="1.1.1.1",
            ping_latency_ms=21.4,
            ping_latency_max_ms=45,
            ping_latency_median_ms=20.4,
            ping_latency_min_ms=19.2,
            ping_packet_loss_percent=0.17,
            wan_uuid="8d5a7f20-2923-49a3-8e2b-338f9428a632",
        ),
    )


def test_extract_internet_quality_samples_skips_invalid_keys() -> None:
    """Test extraction ignores non-metric keys and malformed buckets."""
    client = FirewallaApiClient(
        session=None,  # type: ignore[arg-type]
        host="192.168.200.1",
        gid="gid-123",
        eid="eid-123",
        aid="aid-123",
        symmetric_key=TEST_SYMMETRIC_KEY,
        device_name="Home Assistant",
    )
    samples = client._extract_internet_quality_samples(
        {
            "unrelated": {"1788961500": {"stat": {"mean": 1}}},
            "metric:monitor:raw:ping:1.1.1.1:wan-1": {
                "1788961500": {"stat": {"mean": 22.2, "lossrate": 0}},
                "not-a-number": {"stat": {"mean": 1, "lossrate": 0}},
                "1788962400": "not-a-dict",
            },
        }
    )

    assert samples == (
        FirewallaInternetQualitySample(
            timestamp=1788961500.0,
            target="1.1.1.1",
            ping_latency_ms=22.2,
            ping_packet_loss_percent=0.0,
            wan_uuid="wan-1",
        ),
    )


def _flow_client(session: ClientSession) -> FirewallaApiClient:
    """Return a client for flow-reporting request-shape tests."""
    return FirewallaApiClient(
        session=session,
        host="192.168.200.1",
        gid="gid-123",
        eid="eid-123",
        aid="aid-123",
        symmetric_key=TEST_SYMMETRIC_KEY,
        device_name="Home Assistant",
    )


@pytest.mark.asyncio
async def test_flow_rollup_request_matches_the_app_shape() -> None:
    """Test the rollup sends `local` and not `audit`.

    `local: true` is what the app sends and what enables the four LAN-to-LAN
    families (11 families with it, 7 without, measured live). `audit` has no
    effect on the rollup at all, so it is not sent.
    """
    async with ClientSession() as session:
        client = _flow_client(session)
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value={}),
        ) as mock_send:
            await client.async_get_flow_rollup_payload(
                target_type="tag",
                target="31",
                start_timestamp=1_790_949_600,
                end_timestamp=1_791_036_000,
                hourblock=24,
            )

    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {
            "item": "tag",
            "apiVer": 2,
            "local": True,
            "start": 1_790_949_600,
            "end": 1_791_036_000,
            "hourblock": 24,
        },
        "target": "31",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hourblock",
    [
        pytest.param(0, id="zero"),
        pytest.param(1, id="one"),
        pytest.param(-5, id="negative"),
    ],
)
async def test_flow_rollup_clamps_hourblock_so_the_response_is_not_empty(
    hourblock: int,
) -> None:
    """Test hourblock is raised to at least 2.

    Measured live: `hourblock` 0 and 1 both return an **empty** response with no
    error, and every value from 2 to 168 returns identical full data. So passing
    0 or 1 yields silence, which is why it is clamped rather than forwarded.
    """
    async with ClientSession() as session:
        client = _flow_client(session)
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value={}),
        ) as mock_send:
            await client.async_get_flow_rollup_payload(
                target_type="host",
                target="CC:28:AA:11:06:B7",
                start_timestamp=1,
                end_timestamp=2,
                hourblock=hourblock,
            )

    assert mock_send.await_args.kwargs["data"]["hourblock"] == 2


@pytest.mark.asyncio
async def test_flow_log_request_sends_the_audit_flag_and_a_count() -> None:
    """Test the flow log matches the app's captured request shape."""
    async with ClientSession() as session:
        client = _flow_client(session)
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value={"flows": [], "count": 0, "nextTs": None}),
        ) as mock_send:
            await client.async_get_flow_log_payload(
                target_type="tag",
                target="31",
                count=300,
                since_timestamp=1_791_035_214.683,
                include_blocked=True,
            )

    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {
            "item": "flows",
            "type": "tag",
            "audit": True,
            "count": 300,
            "exclude": [],
            "ts": 1_791_035_214.683,
        },
        "target": "31",
    }


@pytest.mark.asyncio
async def test_block_log_request_sends_no_audit_flag() -> None:
    """Test the block log omits `audit` and reads the `logs` record key.

    `auditLogs` is the blocked-only query. The app sends no `audit` with it, and
    the records come back under `logs` rather than `flows`.
    """
    async with ClientSession() as session:
        client = _flow_client(session)
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value={"logs": [{"ltype": "audit"}], "count": 1}),
        ) as mock_send:
            page = await client.async_get_block_log_payload(
                target_type="tag",
                target="31",
                count=300,
                since_timestamp=1_791_036_000,
                category="games",
                end_timestamp=1_791_032_400,
            )

    assert mock_send.await_args.kwargs == {
        "message_type": "get",
        "data": {
            "item": "auditLogs",
            "type": "tag",
            "count": 300,
            "exclude": [],
            "ts": 1_791_036_000,
            "category": "games",
            "ets": 1_791_032_400,
        },
        "target": "31",
    }
    assert page.records == ({"ltype": "audit"},)
    assert page.reported_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        pytest.param(-1, 50, id="negative_would_return_everything"),
        pytest.param(0, 50, id="zero_is_undefined"),
        pytest.param(1, 50, id="one_returns_zero_rows"),
        pytest.param(50, 50, id="at_the_floor"),
        pytest.param(300, 300, id="honoured"),
        pytest.param(5000, 5000, id="at_the_ceiling"),
        pytest.param(9999, 5000, id="clamped_at_the_ceiling"),
    ],
)
async def test_flow_log_count_is_clamped_into_the_answered_range(
    requested: int,
    expected: int,
) -> None:
    """Test a caller-supplied count is never forwarded unvalidated.

    A non-positive count is the dangerous case: the box returns the ENTIRE
    retained window (~6,956 rows measured) rather than nothing, which is the
    opposite of the intuitive reading. Above 5,000 it silently caps.
    """
    async with ClientSession() as session:
        client = _flow_client(session)
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(return_value={"flows": [], "count": 0}),
        ) as mock_send:
            await client.async_get_flow_log_payload(
                target_type="tag",
                target="31",
                count=requested,
            )

    assert mock_send.await_args.kwargs["data"]["count"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_type",
    [
        pytest.param("device", id="device_is_a_scope_not_a_flow_target"),
        pytest.param("user", id="user_is_a_scope_not_a_flow_target"),
        pytest.param("", id="empty"),
    ],
)
async def test_flow_queries_reject_a_target_type_the_box_does_not_accept(
    target_type: str,
) -> None:
    """Test only `tag` and `host` reach the wire.

    The flow queries take a tag id or a host MAC. A `device` or `user` selector
    belongs to the service layer's scope resolution, which maps it to one of
    these before the client is called.
    """
    async with ClientSession() as session:
        client = _flow_client(session)
        with pytest.raises(FirewallaValidationError):
            await client.async_get_flow_log_payload(
                target_type=target_type,
                target="31",
                count=300,
            )


@pytest.mark.asyncio
async def test_a_flow_page_surfaces_the_box_count_and_cursor_separately() -> None:
    """Test the page keeps the reported count apart from the rows returned.

    The box caps a requested page silently, so rows returned can be fewer than
    the count it reports, and a caller needs both to tell a truncated page from a
    quiet target. The cursor stays a float: rounding it could skip records.
    """
    async with ClientSession() as session:
        client = _flow_client(session)
        with patch.object(
            client,
            "_async_send_local_message_data",
            AsyncMock(
                return_value={
                    "flows": [{"ltype": "flow"}, "not-a-dict", {"ltype": "audit"}],
                    "count": 9001,
                    "nextTs": 1_791_017_277.18,
                }
            ),
        ):
            page = await client.async_get_flow_log_payload(
                target_type="tag",
                target="31",
                count=300,
            )

    assert page.records == ({"ltype": "flow"}, {"ltype": "audit"})
    assert page.reported_count == 9001
    assert page.next_cursor == 1_791_017_277.18


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not-a-dict", id="not_an_object"),
        pytest.param({"count": 1}, id="no_records_list"),
        pytest.param({"flows": {"not": "a list"}}, id="records_not_a_list"),
    ],
)
async def test_a_malformed_flow_page_raises_rather_than_returning_nothing(
    payload: object,
) -> None:
    """Test a shape change raises, so the caller can report it as unavailable.

    The client does not swallow this: every other method raises
    `FirewallaProtocolError` on an unexpected shape, and fail-soft is the
    manager's decision so it can report what it could not read.
    """
    async with ClientSession() as session:
        client = _flow_client(session)
        with (
            patch.object(
                client,
                "_async_send_local_message_data",
                AsyncMock(return_value=payload),
            ),
            pytest.raises(FirewallaProtocolError),
        ):
            await client.async_get_flow_log_payload(
                target_type="tag",
                target="31",
                count=300,
            )
