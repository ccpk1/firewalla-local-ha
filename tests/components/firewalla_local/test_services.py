"""Tests for Firewalla Local services."""

from __future__ import annotations

# pylint: disable=too-many-lines
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant, SupportsResponse
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.api import FirewallaApiClient, FirewallaApiError
from custom_components.firewalla_local.api.exceptions import FirewallaProtocolError
from custom_components.firewalla_local.api.models import FlowLogPage
from custom_components.firewalla_local.const import (
    ALARM_STATUS_ACTIVE,
    ALARM_STATUS_ARCHIVED,
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_LLM_TOOL_MODE,
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    CONF_SYMMETRIC_KEY,
    DEFAULT_LLM_TOOL_MODE,
    DOMAIN,
    LLM_TOOL_MODE_READ_AND_CONTROL,
    LLM_TOOL_MODE_READ_ONLY,
    LLM_TOOL_MODE_SUMMARY_ONLY,
    MATCH_TYPE_ALARM_TYPE,
    RULE_PURPOSE_DAP,
    RULE_TARGET_TYPE_MAC,
    SERVICE_ARCHIVE_ALARMS,
    SERVICE_DELETE_ALARMS,
    SERVICE_DELETE_HOST,
    SERVICE_DELETE_RULE,
    SERVICE_FIELD_ALARM_ID,
    SERVICE_FIELD_ALARM_MATCH_TYPE,
    SERVICE_FIELD_ALARM_MATCH_VALUE,
    SERVICE_FIELD_ALARM_STATUS,
    SERVICE_FIELD_APPLIES_TO,
    SERVICE_FIELD_CLEAR,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIG_ENTRY_NAME,
    SERVICE_FIELD_CONFIRM,
    SERVICE_FIELD_CURRENT_PERIODS,
    SERVICE_FIELD_DETAIL,
    SERVICE_FIELD_DNS_HOSTNAME,
    SERVICE_FIELD_DURATION,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_EXCEPTION_ID,
    SERVICE_FIELD_FETCH_ALL_RECORDS,
    SERVICE_FIELD_GROUP_ID,
    SERVICE_FIELD_GROUP_NAME,
    SERVICE_FIELD_HISTORY_COUNT,
    SERVICE_FIELD_HISTORY_PERIOD,
    SERVICE_FIELD_HOST_DEVICE_TYPE,
    SERVICE_FIELD_HOST_ID,
    SERVICE_FIELD_HOST_MAC,
    SERVICE_FIELD_HOST_NAME,
    SERVICE_FIELD_INCLUDE,
    SERVICE_FIELD_INCLUDE_ARCHIVED,
    SERVICE_FIELD_INCLUDE_DNS,
    SERVICE_FIELD_INCLUDE_PURPOSE,
    SERVICE_FIELD_INCLUDE_SYSTEM_MANAGED,
    SERVICE_FIELD_KIND,
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_MODE,
    SERVICE_FIELD_NETWORK_NAME,
    SERVICE_FIELD_NETWORK_UUID,
    SERVICE_FIELD_NEW_NAME,
    SERVICE_FIELD_OFFSET,
    SERVICE_FIELD_RECORD_COUNT,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_RESERVED_IPV4,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_ID,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_SCOPE_KIND,
    SERVICE_FIELD_SECTIONS,
    SERVICE_FIELD_SSID_PROFILE_ID,
    SERVICE_FIELD_TOP_N,
    SERVICE_FIELD_USAGE_HISTORY_APP_IDS,
    SERVICE_FIELD_USAGE_HISTORY_BEGIN,
    SERVICE_FIELD_USAGE_HISTORY_END,
    SERVICE_FIELD_USAGE_HISTORY_GRANULARITY,
    SERVICE_FIELD_USER,
    SERVICE_FIELD_USER_ID,
    SERVICE_FIELD_USER_NAME,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_FIELD_WINDOW,
    SERVICE_FIELD_WINDOW_HOURS,
    SERVICE_GET_ALARMS,
    SERVICE_GET_FLOW_REPORT,
    SERVICE_GET_HOSTS,
    SERVICE_GET_INTERNET_QUALITY_REPORT,
    SERVICE_GET_NETWORK_SEGMENT_REPORT,
    SERVICE_GET_NETWORK_SEGMENT_USAGE,
    SERVICE_GET_RULES,
    SERVICE_GET_SPEED_TEST_RESULTS,
    SERVICE_GET_SYSTEM_OVERVIEW,
    SERVICE_GET_TIME_USAGE_REPORT,
    SERVICE_GET_WAN_DATA_USAGE,
    SERVICE_GET_WAN_EVENTS,
    SERVICE_GET_WIRELESS_STATUS,
    SERVICE_MUTE_ALARM,
    SERVICE_PAUSE_RULE,
    SERVICE_RESUME_RULE,
    SERVICE_RUN_INTERNET_SPEED_TEST,
    SERVICE_SET_HOST_DEVICE_TYPE,
    SERVICE_SET_HOST_DHCP_RESERVATION,
    SERVICE_SET_HOST_DNS_HOSTNAME,
    SERVICE_SET_HOST_MEMBERSHIP,
    SERVICE_SET_HOST_NAME,
    SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_OFFLINE,
    SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_ONLINE,
    SERVICE_SET_SSID_PAUSED,
    SERVICE_SYNC_RUNTIME,
    SERVICE_UNMUTE_ALARM,
    SERVICE_WAKE_HOST,
    TRANS_KEY_EXCEPTION_DELETE_HOST_CONFIRM_REQUIRED,
    TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_NOT_FOUND,
    TRANS_KEY_EXCEPTION_WAKE_HOST_FAILED,
)
from custom_components.firewalla_local.coordinator import FirewallaRuntimeData
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaFlowRecord,
    FirewallaGroupRuntime,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
    FirewallaUserRuntime,
)
from custom_components.firewalla_local.services import (
    _async_register_service,
    _get_loaded_entry,
    async_setup_services,
)


def _box_host() -> FirewallaHostRuntime:
    """Return the Firewalla box's own host record, always present in snapshots."""
    return FirewallaHostRuntime(
        mac="AA:BB:CC:DD:EE:00",
        host_name="Firewalla",
        ip_address="192.168.200.1",
        group_name=None,
        network_name=None,
        connection_type=None,
        last_active=None,
        download_bytes=None,
        upload_bytes=None,
        stale=False,
    )


def _snapshot(
    enabled: bool = True,
    *,
    rule_id: str = "744",
    target: str = "social",
    target_type: str = "category",
    target_name: str | None = "social",
) -> FirewallaRuntimeSnapshot:
    """Return one selected rule snapshot."""
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
            timezone_name="America/New_York"
        ),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id=rule_id,
                action="block",
                target=target,
                target_type=target_type,
                direction="bidirection",
                enabled=enabled,
                purpose=None,
                scope=(),
                tag_refs=("tag:17",),
                target_name=target_name,
                applies_to=("AV_SMART_TV",),
                dnsmasq_only=True,
                raw_update_payload={
                    "pid": rule_id,
                    "action": "block",
                    "target": target,
                    "type": target_type,
                    "tag": ["tag:17"],
                    "dnsmasq_only": True,
                    "disabled": 0 if enabled else 1,
                },
            ),
        ),
        exception_rule_count=0,
        hosts=(_box_host(),),
    )


def _runtime_payload() -> dict[str, object]:
    """Return a minimal raw init payload for coordinator setup tests."""
    return {
        "timezone": "America/New_York",
        "policyRules": [],
        "networkProfiles": {
            "5799d896-5e0f-40a5-a776-38a5d7746204": {
                "intf": "bond0.10",
                "name": "VLAN10 CORE",
            },
            "d7e5a5c4-0b28-4010-b3c6-dad1a868693f": {
                "intf": "br0",
                "name": "Primary LAN",
            },
        },
        "networkConfig": {
            "interface": {
                "bond": {
                    "bond0.10": {
                        "meta": {
                            "name": "VLAN10 CORE",
                            "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
                        }
                    }
                },
                "lan": {
                    "meta": {
                        "name": "Primary LAN",
                        "uuid": "d7e5a5c4-0b28-4010-b3c6-dad1a868693f",
                    }
                },
            }
        },
        "monthlyDataUsageOnWans": {
            "wan-1": {
                "download": [
                    [1_743_480_000, 1024],
                    [1_743_566_400, 2048],
                ],
                "upload": [
                    [1_743_480_000, 512],
                    [1_743_566_400, 768],
                ],
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


def _network_segment_report_runtime_payload() -> dict[str, object]:
    """Return a runtime payload enriched for network segment report tests."""
    payload = deepcopy(_runtime_payload())
    payload["networkConfig"] = {
        **payload["networkConfig"],
        "dhcp": {
            "bond0.10": {
                "gateway": "192.168.10.1",
                "subnetMask": "255.255.255.0",
                "lease": 86400,
                "range": {
                    "from": "192.168.10.110",
                    "to": "192.168.10.126",
                },
                "nameservers": ["192.168.10.1"],
                "searchDomain": ["int.ccpk.us"],
                "extraOptions": {},
            },
            "br0": {
                "gateway": "192.168.200.1",
                "subnetMask": "255.255.255.0",
                "lease": 86400,
                "range": {
                    "from": "192.168.200.100",
                    "to": "192.168.200.199",
                },
                "nameservers": ["192.168.200.1"],
                "searchDomain": ["lan.example"],
                "extraOptions": {},
            },
        },
    }
    payload["deviceTags"] = {
        "43": {"name": "phone"},
    }
    payload["hosts"] = [
        {
            "mac": "00:AA:BB:CC:DD:26",
            "name": "plex-server",
            "dhcpName": "plex-server",
            "ip": "192.168.10.10",
            "intf": "5799d896-5e0f-40a5-a776-38a5d7746204",
            "detect": {
                "feedback": {"type": "tablet"},
                "type": "phone",
            },
            "deviceTags": ["43"],
            "policy": {
                "devicePresence": True,
                "deviceOffline": False,
                "ipAllocation": {
                    "allocations": {
                        "5799d896-5e0f-40a5-a776-38a5d7746204": {
                            "ipv4": "192.168.10.10",
                            "type": "static",
                        }
                    }
                },
            },
        },
        {
            "mac": "0C:85:E1:B0:1D:1C",
            "name": "office-phone",
            "dhcpName": "office-phone",
            "ip": "192.168.10.44",
            "intf": "5799d896-5e0f-40a5-a776-38a5d7746204",
            "deviceTags": ["43"],
            "policy": {
                "ipAllocation": {
                    "allocations": {
                        "5799d896-5e0f-40a5-a776-38a5d7746204": {
                            "type": "dynamic",
                        }
                    }
                },
            },
        },
    ]
    return payload


def _wan_usage_history_payload() -> dict[str, object]:
    """Return one normalized-looking raw last-12-month WAN usage payload."""
    return {
        "wan-1": [
            {
                "ts": 1_748_750_400,
                "stats": {
                    "download": [
                        [1_748_750_400, 1000],
                        [1_748_836_800, 1100],
                        [1_748_923_200, 1200],
                        [1_749_009_600, 1300],
                        [1_749_096_000, 1400],
                        [1_749_182_400, 1500],
                        [1_749_268_800, 1600],
                        [1_749_355_200, 1700],
                    ],
                    "upload": [
                        [1_748_750_400, 500],
                        [1_748_836_800, 550],
                        [1_748_923_200, 600],
                        [1_749_009_600, 650],
                        [1_749_096_000, 700],
                        [1_749_182_400, 750],
                        [1_749_268_800, 800],
                        [1_749_355_200, 850],
                    ],
                    "totalDownload": 10800,
                    "totalUpload": 5400,
                },
            },
            {
                "ts": 1_746_072_000,
                "stats": {
                    "download": [
                        [1_746_072_000, 2000],
                        [1_746_158_400, 2100],
                        [1_746_244_800, 2200],
                    ],
                    "upload": [
                        [1_746_072_000, 900],
                        [1_746_158_400, 1000],
                        [1_746_244_800, 1100],
                    ],
                    "totalDownload": 6300,
                    "totalUpload": 3000,
                },
            },
        ],
        "wan-2": [
            {
                "ts": 1_748_750_400,
                "stats": {
                    "download": [[1_748_750_400, 2048]],
                    "upload": [[1_748_750_400, 1024]],
                    "totalDownload": 2048,
                    "totalUpload": 1024,
                },
            }
        ],
    }


def _wan_events_payload() -> list[dict[str, object]]:
    """Return representative raw WAN events from the direct events timeline."""
    return [
        {
            "action_type": "ping_RTT",
            "action_value": 1,
            "event_type": "action",
            "labels": {
                "rtt": 53.2365,
                "rttLimit": 35.3376,
                "target": "1.1.1.1",
                "wan_intf_name": "WAN-ONE",
                "wan_intf_uuid": "wan-1",
            },
            "ts": 1_774_036_038_371,
        },
        {
            "event_type": "state",
            "labels": {
                "changedInterface": "eth0",
                "failures": [
                    {
                        "target": "1.1.1.1",
                        "type": "ping",
                    }
                ],
                "ok_value": 0,
                "primaryInterface": "eth0",
                "wanStatus": {
                    "eth0": {
                        "active": True,
                        "ip4s": ["23.245.207.179/23"],
                        "ready": True,
                        "seq": 0,
                        "wan_intf_name": "WAN-ONE",
                        "wan_intf_uuid": "wan-1",
                    },
                    "eth1": {
                        "active": False,
                        "ready": False,
                        "seq": 1,
                        "wan_intf_name": "WAN-TWO",
                        "wan_intf_uuid": "wan-2",
                    },
                },
                "wanSwitched": True,
                "wanType": "primary_standby",
            },
            "prev_state_value": 15,
            "state_key": "primary_standby",
            "state_type": "dualwan_state",
            "state_value": 12,
            "ts": 1_774_383_170_915,
            "ts0": 1_774_383_170_915,
        },
        {
            "event_type": "state",
            "labels": {
                "dns_test_domain": "github.com",
                "name_server": "172.64.36.2",
                "ok_value": 0,
                "wan_intf_address": "23.245.207.179",
                "wan_intf_name": "WAN-ONE",
                "wan_intf_uuid": "wan-1",
            },
            "prev_state_value": 0,
            "state_key": "172.64.36.2",
            "state_type": "dns",
            "state_value": 1,
            "ts": 1_774_551_926_895,
            "ts0": 1_774_551_926_895,
        },
    ]


def _speed_test_snapshot(
    *, timezone_name: str | None = None
) -> FirewallaRuntimeSnapshot:
    """Return a runtime snapshot with normalized speed-test records."""
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
            timezone_name=timezone_name,
        ),
        policy_rules=(),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="0C:85:E1:B0:1D:1C",
                host_name="Office Phone",
                ip_address="192.168.10.44",
                group_name=None,
                network_name="VLAN10 CORE",
                connection_type=None,
                last_active=None,
                download_bytes=620781748,
                upload_bytes=133546109,
                stale=False,
            ),
            FirewallaHostRuntime(
                mac="00:AA:BB:CC:DD:26",
                host_name="Plex Server",
                ip_address="192.168.10.10",
                group_name=None,
                network_name="VLAN10 CORE",
                connection_type=None,
                last_active=None,
                download_bytes=1001430063,
                upload_bytes=3730817840,
                stale=False,
            ),
        ),
        speed_test_results=(
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1_774_519_230.541,
                download_mbps=82.65986251831055,
                upload_mbps=50.29832458496094,
                latency_ms=28.195942,
                jitter_ms=1.458138,
                packet_loss_percent=-1,
                download_megabytes=161.26446723937988,
                upload_megabytes=58.01159858703613,
                isp="Atlantic Broadband",
                public_ip="23.245.207.179",
                server_country="United States",
                server_host="speedtest-cmh.dish-wireless.com:8080",
                server_id="53971",
                server_location="Columbus, OH",
                server_sponsor="Boost Mobile",
                manual=False,
                success=True,
                vendor="ookla",
                wan_uuid="wan-1",
            ),
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1_774_200_026.511,
                download_mbps=63.15821075439453,
                upload_mbps=51.20576858520508,
                latency_ms=27.404289,
                jitter_ms=1.714381,
                packet_loss_percent=-1,
                download_megabytes=89.23129463195801,
                upload_megabytes=60.53947830200195,
                isp="Atlantic Broadband",
                public_ip="23.245.207.179",
                server_country="United States",
                server_host="speedtest-cmh.dish-wireless.com:8080",
                server_id="53971",
                server_location="Columbus, OH",
                server_sponsor="Boost Mobile",
                manual=False,
                success=True,
                vendor="ookla",
                wan_uuid="wan-2",
            ),
        ),
    )


def _wake_host_snapshot(
    *,
    duplicate_name: bool = False,
    primary_group_name: str | None = None,
) -> FirewallaRuntimeSnapshot:
    """Return a runtime snapshot with Wake-on-LAN-capable and unsupported hosts."""
    second_name = "Plex Server" if duplicate_name else "WireGuard Kaden"
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
            timezone_name="America/New_York",
        ),
        policy_rules=(),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="00:AA:BB:CC:DD:26",
                host_name="Plex Server",
                ip_address="192.168.10.10",
                group_name=primary_group_name,
                network_name="VLAN10 CORE",
                connection_type=None,
                last_active=None,
                download_bytes=100,
                upload_bytes=50,
                stale=False,
                dns_hostname="plex-server",
                dns_domain="int.ccpk.us",
                dns_fqdn="plex-server.int.ccpk.us",
                dhcp_name="plex-server",
                host_device_type="tablet",
            ),
            FirewallaHostRuntime(
                mac="wg_peer:test-peer",
                host_name=second_name,
                ip_address="10.42.0.2",
                group_name=None,
                network_name="VLAN10 CORE",
                connection_type=None,
                last_active=None,
                download_bytes=1,
                upload_bytes=1,
                stale=False,
                dns_domain="int.ccpk.us",
            ),
        ),
    )


def _network_interface_payload() -> dict[str, object]:
    """Return one representative raw item=intf payload."""
    return {
        "intf": "bond0.10",
        "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
        "type": "lan",
        "monitoring": True,
        "gateway": "192.168.10.1",
        "dns": ["192.168.10.1", "1.1.1.1"],
        "origDns": ["1.1.1.1"],
        "ipv4": "192.168.10.1",
        "ipv4s": ["192.168.10.1"],
        "ipv4Subnet": "192.168.10.0/24",
        "ipv4Subnets": ["192.168.10.0/24"],
        "hosts": {
            "00:AA:BB:CC:DD:26": {
                "conn": 25161,
                "dns": 2753,
                "dnsB": 0,
                "download": 1001430063,
                "ipB": 1,
                "ipD": 0,
                "ntp": 74,
                "upload": 3730817840,
            },
            "0C:85:E1:B0:1D:1C": {
                "conn": 4730,
                "dns": 1018,
                "dnsB": 302,
                "download": 620781748,
                "ipB": 3258,
                "ipD": 0,
                "ntp": 12,
                "upload": 133546109,
            },
        },
        "flows": {
            "download": [
                {
                    "device": "00:AA:BB:CC:DD:26",
                    "host": "pkg-containers.githubusercontent.com",
                    "ip": "185.199.111.154",
                    "count": "406504404",
                }
            ],
            "upload": [
                {
                    "device": "0C:85:E1:B0:1D:1C",
                    "host": "upload.example.net",
                    "ip": "203.0.113.50",
                    "count": "133546109",
                }
            ],
        },
        "newLast24": {
            "conn": [[1_774_558_800, 5696], [1_774_641_600, 650]],
            "dns": [[1_774_558_800, 1855], [1_774_641_600, 120]],
        },
        "last60": {
            "download": [[1_774_641_200, 362233], [1_774_641_260, 243273]],
        },
        "last30": {
            "upload": [[1_772_409_600, 4096], [1_772_496_000, 8192]],
        },
        "last12Months": {
            "download": [[1_740_960_000, 16384], [1_743_638_400, 32768]],
        },
        "policy": {"state": True},
    }


def _zero_host_activity_network_interface_payload() -> dict[str, object]:
    """Return a payload where raw host counters are sparse but flows are rich."""
    payload = deepcopy(_network_interface_payload())
    payload["hosts"] = {
        "00:AA:BB:CC:DD:26": {
            "conn": 0,
            "dns": 0,
            "dnsB": 0,
            "download": 0,
            "ipB": 0,
            "ipD": 0,
            "ntp": 0,
            "upload": 0,
        },
        "0C:85:E1:B0:1D:1C": {
            "conn": 0,
            "dns": 0,
            "dnsB": 0,
            "download": 0,
            "ipB": 0,
            "ipD": 0,
            "ntp": 0,
            "upload": 0,
        },
    }
    payload["flows"] = {
        **cast(dict[str, object], payload["flows"]),
        "download": [
            {
                "device": "00:AA:BB:CC:DD:26",
                "deviceIP": "192.168.10.10",
                "host": "pkg-containers.githubusercontent.com",
                "ip": "185.199.111.154",
                "count": "406504404",
            }
        ],
        "upload": [
            {
                "device": "0C:85:E1:B0:1D:1C",
                "deviceIP": "192.168.10.44",
                "host": "upload.example.net",
                "ip": "203.0.113.50",
                "count": "133546109",
            }
        ],
        "recent": [
            {
                "device": "00:AA:BB:CC:DD:26",
                "deviceIP": "192.168.10.10",
                "count": 4,
                "ts": 1_774_641_600,
            },
            {
                "device": "0C:85:E1:B0:1D:1C",
                "deviceIP": "192.168.10.44",
                "count": 2,
                "ts": 1_774_641_540,
            },
        ],
        "appDetails": {
            "youtube": [
                {
                    "device": "00:AA:BB:CC:DD:26",
                    "download": 300,
                    "upload": 30,
                    "duration": 60.0,
                    "ts": 1_774_641_000,
                },
                {
                    "device": "0C:85:E1:B0:1D:1C",
                    "download": 200,
                    "upload": 20,
                    "duration": 120.0,
                    "ts": 1_774_641_120,
                },
            ],
            "netflix": [
                {
                    "device": "00:AA:BB:CC:DD:26",
                    "download": 100,
                    "upload": 10,
                    "duration": 30.0,
                    "ts": 1_774_641_180,
                }
            ],
        },
        "categoryDetails": {
            "av": [
                {
                    "device": "00:AA:BB:CC:DD:26",
                    "download": 400,
                    "upload": 40,
                    "duration": 90.0,
                    "ts": 1_774_641_180,
                },
                {
                    "device": "0C:85:E1:B0:1D:1C",
                    "download": 200,
                    "upload": 20,
                    "duration": 120.0,
                    "ts": 1_774_641_120,
                },
            ]
        },
    }
    return payload


def _membership_snapshot() -> FirewallaRuntimeSnapshot:
    """Return a snapshot with a classified group and user collection.

    The collection deliberately holds a group and a user that share the name
    "KADEN", and two groups that share the name "IOT_LIGHTS". Both are realistic
    on a real box, and both are the reason a membership selector is split by kind
    and why an ambiguous name has to fail rather than pick one.
    """
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
            timezone_name="America/New_York"
        ),
        policy_rules=(),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="00:AA:BB:CC:DD:26",
                host_name="Plex Server",
                ip_address="192.168.10.10",
                group_name=None,
                network_name="VLAN10 CORE",
                connection_type=None,
                last_active=None,
                download_bytes=100,
                upload_bytes=50,
                stale=False,
            ),
            FirewallaHostRuntime(
                mac="0C:85:E1:B0:1D:1C",
                host_name="Kaden Phone",
                ip_address="192.168.200.25",
                group_name="KADEN",
                network_name="VLAN10 CORE",
                connection_type="phone",
                last_active=None,
                download_bytes=200,
                upload_bytes=20,
                stale=False,
                group_ids=("10",),
                user_ids=("21",),
            ),
        ),
        groups=(
            FirewallaGroupRuntime(group_id="12", name="Quarantine", kind="group"),
            FirewallaGroupRuntime(group_id="53", name="IOT_LIGHTS", kind="group"),
            FirewallaGroupRuntime(group_id="66", name="IOT_LIGHTS", kind="group"),
            FirewallaGroupRuntime(group_id="99", name="KADEN", kind="group"),
            FirewallaGroupRuntime(
                group_id="10",
                name="KADEN",
                kind="user",
                user_id="21",
            ),
            FirewallaGroupRuntime(
                group_id="11",
                name="PAYTON",
                kind="user",
                user_id="22",
            ),
            FirewallaGroupRuntime(
                group_id="13",
                name="PAYTON",
                kind="user",
                user_id="23",
            ),
        ),
        users=(
            FirewallaUserRuntime(
                user_id="21",
                name="KADEN",
                affiliated_group_id="10",
                affiliated_group_name="KADEN",
                total_minutes_today=None,
                unique_minutes_today=None,
            ),
            FirewallaUserRuntime(
                user_id="22",
                name="PAYTON",
                affiliated_group_id="11",
                affiliated_group_name="PAYTON",
                total_minutes_today=None,
                unique_minutes_today=None,
            ),
            FirewallaUserRuntime(
                user_id="23",
                name="PAYTON",
                affiliated_group_id="13",
                affiliated_group_name="PAYTON",
                total_minutes_today=None,
                unique_minutes_today=None,
            ),
        ),
    )


def _membership_entry() -> MockConfigEntry:
    """Return a config entry for the membership service tests."""
    return MockConfigEntry(
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


@contextmanager
def _membership_patches(
    write_mock: AsyncMock,
    *,
    snapshot: FirewallaRuntimeSnapshot | None = None,
    delete_mock: AsyncMock | None = None,
) -> Iterator[None]:
    """Patch the runtime payload, snapshot, host-policy writer, and rule deleter."""
    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=snapshot if snapshot is not None else _membership_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_delete_rule",
            new=delete_mock if delete_mock is not None else AsyncMock(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_policy",
            new=write_mock,
        ),
    ):
        yield


def _user_filter_snapshot() -> FirewallaRuntimeSnapshot:
    """Return a snapshot whose device-to-user link exists only via the tag.

    `user_ids` is empty on both hosts, matching a real box: the host-level
    `userTags` array that would populate it is always empty, so an assignment is
    visible only as the user's affiliated backing tag in `group_ids`.
    """
    return replace(
        _membership_snapshot(),
        hosts=(
            FirewallaHostRuntime(
                mac="0C:85:E1:B0:1D:1C",
                host_name="Kaden Phone",
                ip_address="192.168.200.25",
                group_name="KADEN",
                network_name="VLAN10 CORE",
                connection_type="phone",
                last_active=None,
                download_bytes=200,
                upload_bytes=20,
                stale=False,
                group_ids=("10",),
                user_ids=(),
            ),
            FirewallaHostRuntime(
                mac="00:AA:BB:CC:DD:26",
                host_name="Plex Server",
                ip_address="192.168.10.10",
                group_name=None,
                network_name="VLAN10 CORE",
                connection_type=None,
                last_active=None,
                download_bytes=100,
                upload_bytes=50,
                stale=False,
                group_ids=(),
                user_ids=(),
            ),
        ),
    )


def _membership_snapshot_with_rules() -> FirewallaRuntimeSnapshot:
    """Return a membership snapshot carrying the device's own rules.

    Modelled on the real captured device: a disabled `dap` pair belonging to this
    device (575 and 576), plus 578 and 579 which are scoped to it (578 is a live
    rule the owner created and 579 is an enabled `dap` rule). 577 belongs to a
    different device and must never be attributed to this one.
    """
    return replace(
        _membership_snapshot(),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="575",
                action="allow",
                target="dap_0c85e1b01d1c",
                target_type="category",
                direction="outbound",
                enabled=False,
                purpose=RULE_PURPOSE_DAP,
                scope=("0C:85:E1:B0:1D:1C",),
                target_name=None,
            ),
            FirewallaPolicyRule(
                rule_id="576",
                action="block",
                target="0C:85:E1:B0:1D:1C",
                target_type=RULE_TARGET_TYPE_MAC,
                direction="bidirection",
                enabled=False,
                purpose=RULE_PURPOSE_DAP,
                scope=(),
                target_name=None,
            ),
            FirewallaPolicyRule(
                rule_id="577",
                action="block",
                target="AA:BB:CC:DD:EE:FF",
                target_type=RULE_TARGET_TYPE_MAC,
                direction="bidirection",
                enabled=False,
                purpose=RULE_PURPOSE_DAP,
                scope=(),
                target_name=None,
            ),
            FirewallaPolicyRule(
                rule_id="578",
                action="allow",
                target="192.168.254.8",
                target_type="ip",
                direction="outbound",
                enabled=True,
                purpose=None,
                scope=("0C:85:E1:B0:1D:1C",),
                target_name=None,
            ),
            FirewallaPolicyRule(
                rule_id="579",
                action="block",
                target="0C:85:E1:B0:1D:1C",
                target_type=RULE_TARGET_TYPE_MAC,
                direction="bidirection",
                enabled=True,
                purpose=RULE_PURPOSE_DAP,
                scope=(),
                target_name=None,
            ),
        ),
    )


def _usage_history_snapshot() -> FirewallaRuntimeSnapshot:
    """Return a runtime snapshot with host, group, and user scope targets."""
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
            timezone_name="America/New_York"
        ),
        policy_rules=(),
        exception_rule_count=0,
        hosts=(
            FirewallaHostRuntime(
                mac="EC:0D:51:CC:BA:BC",
                host_name="Kaden Phone",
                ip_address="192.168.200.25",
                group_name="KADEN's Devices (KADEN)",
                network_name="VLAN10 CORE",
                connection_type="phone",
                last_active=1_774_287_984.272,
                download_bytes=1234,
                upload_bytes=5678,
                stale=False,
                group_ids=("10",),
                user_ids=("21",),
            ),
        ),
        groups=(
            FirewallaGroupRuntime(group_id="12", name="Quarantine", kind="group"),
            FirewallaGroupRuntime(
                group_id="10",
                name="KADEN",
                kind="user",
                user_id="21",
            ),
        ),
        users=(
            FirewallaUserRuntime(
                user_id="21",
                name="KADEN",
                affiliated_group_id="10",
                affiliated_group_name="KADEN",
                total_minutes_today=410,
                unique_minutes_today=381,
            ),
        ),
    )


def _usage_history_payload() -> dict[str, object]:
    """Return one representative raw usage-history payload."""
    return {
        "internetTimeUsage": {
            "category": "none",
            "totalMins": 596,
            "uniqueMins": 580,
            "slots": {
                "1774065600": {"totalMins": 120, "uniqueMins": 118},
                "1774152000": {"totalMins": 90, "uniqueMins": 88},
            },
            "devices": {
                "EC:0D:51:CC:BA:BC": {
                    "totalMins": 30,
                    "uniqueMins": 30,
                    "intervals": [
                        {"begin": 1774065600, "end": 1774065900},
                        {"begin": 1774066200, "end": 1774066500},
                    ],
                }
            },
        },
        "appTimeUsageTotal": {
            "totalMins": 121,
            "uniqueMins": 120,
            "slots": {
                "1774065600": {"totalMins": 60, "uniqueMins": 60},
                "1774152000": {"totalMins": 61, "uniqueMins": 60},
            },
        },
        "appTimeUsage": {
            "facebook": {
                "category": "social",
                "totalMins": 121,
                "uniqueMins": 120,
                "slots": {
                    "1774065600": {"totalMins": 60, "uniqueMins": 60},
                    "1774152000": {"totalMins": 61, "uniqueMins": 60},
                },
                "devices": {
                    "EC:0D:51:CC:BA:BC": {
                        "totalMins": 15,
                        "uniqueMins": 15,
                        "intervals": [
                            {"begin": 1774065660, "end": 1774065900},
                        ],
                    }
                },
            }
        },
        "categoryTimeUsage": {
            "social": {
                "totalMins": 121,
                "uniqueMins": 120,
                "slots": {
                    "1774065600": {"totalMins": 60, "uniqueMins": 60},
                    "1774152000": {"totalMins": 61, "uniqueMins": 60},
                },
            }
        },
    }


def _usage_history_payload_with_sparse_apps() -> dict[str, object]:
    """Return a usage-history payload with ranked and zero-only app rows."""
    payload = deepcopy(_usage_history_payload())
    payload["appTimeUsage"] = {
        "facebook": cast(dict[str, object], payload["appTimeUsage"])["facebook"],
        "slack": {
            "category": "productivity",
            "totalMins": 45,
            "uniqueMins": 40,
            "slots": {
                "1774065600": {"totalMins": 20, "uniqueMins": 18},
                "1774152000": {"totalMins": 25, "uniqueMins": 22},
            },
        },
        "youtube": {
            "category": "video",
            "totalMins": 0,
            "uniqueMins": 0,
            "slots": {
                "1774065600": {"totalMins": 0, "uniqueMins": 0},
                "1774152000": {"totalMins": 0, "uniqueMins": 0},
            },
        },
    }
    payload["categoryTimeUsage"] = {
        "social": cast(dict[str, object], payload["categoryTimeUsage"])["social"],
        "productivity": {
            "totalMins": 45,
            "uniqueMins": 40,
            "slots": {
                "1774065600": {"totalMins": 20, "uniqueMins": 18},
                "1774152000": {"totalMins": 25, "uniqueMins": 22},
            },
        },
        "video": {
            "totalMins": 0,
            "uniqueMins": 0,
            "slots": {
                "1774065600": {"totalMins": 0, "uniqueMins": 0},
                "1774152000": {"totalMins": 0, "uniqueMins": 0},
            },
        },
    }
    return payload


async def test_pause_rule_service_updates_matching_rule_optimistically(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule disables the live rule and updates entity state in memory."""
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
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
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
            return_value=_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule_control_only",
            new=AsyncMock(),
        ) as mock_update_rule,
        patch(
            "custom_components.firewalla_local.services.dt_util.utcnow",
            return_value=datetime.fromtimestamp(1_700_000_000, UTC),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = next(iter(hass.states.async_entity_ids("switch")))
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "on"

        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "744",
                SERVICE_FIELD_RULE_DURATION: "30m",
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_update_rule.await_args is not None
    assert mock_update_rule.await_count == 1
    assert mock_update_rule.await_args.kwargs == {
        "enabled": False,
        "idle_ts": 1_700_001_800,
    }
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "off"


async def test_pause_rule_service_refreshes_runtime_before_target_lookup(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule sees a rule that only appears after the forced refresh."""
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
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
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
            side_effect=(
                _snapshot(),
                _snapshot(
                    rule_id="999",
                    target="TAG",
                    target_type="mac",
                    target_name="AV_SMART_TV",
                ),
            ),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule_control_only",
            new=AsyncMock(),
        ) as mock_update_rule,
        patch(
            "custom_components.firewalla_local.services.dt_util.utcnow",
            return_value=datetime.fromtimestamp(1_700_000_000, UTC),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "999",
                SERVICE_FIELD_RULE_DURATION: "30m",
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_update_rule.await_args is not None
    assert mock_update_rule.await_args.args == ("999",)
    assert mock_update_rule.await_args.kwargs == {
        "enabled": False,
        "idle_ts": 1_700_001_800,
    }


async def test_pause_rule_service_rejects_invalid_duration(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule validates duration strings."""
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
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
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
            return_value=_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError, match=r'duration ".*" is invalid'):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "744",
                SERVICE_FIELD_RULE_DURATION: "later",
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )


async def test_pause_rule_service_supports_indefinite_pause(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule can pause indefinitely with no duration or resume_at."""
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
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
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
            return_value=_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule_control_only",
            new=AsyncMock(),
        ) as mock_update_rule,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "744",
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_update_rule.await_args is not None
    assert mock_update_rule.await_count == 1
    assert mock_update_rule.await_args.kwargs == {"enabled": False, "idle_ts": None}


async def test_pause_rule_service_supports_resume_at(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule can pause until an explicit resume time."""
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
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
        },
    )
    entry.add_to_hass(hass)
    resume_at = datetime(2099, 1, 1, 12, 0, tzinfo=UTC)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule_control_only",
            new=AsyncMock(),
        ) as mock_update_rule,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "744",
                SERVICE_FIELD_RULE_RESUME_AT: resume_at,
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_update_rule.await_args is not None
    assert mock_update_rule.await_count == 1
    assert mock_update_rule.await_args.kwargs == {
        "enabled": False,
        "idle_ts": int(resume_at.timestamp()),
    }


async def test_pause_rule_service_rejects_duration_and_resume_at(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule rejects conflicting timing inputs."""
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
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
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
            return_value=_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match="Provide either a duration or a resume time",
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "744",
                SERVICE_FIELD_RULE_DURATION: "30m",
                SERVICE_FIELD_RULE_RESUME_AT: datetime(2099, 1, 1, 12, 0, tzinfo=UTC),
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )


def test_get_loaded_entry_rejects_ambiguous_config_entry_name(
    hass: HomeAssistant,
) -> None:
    """Test ambiguous entry names require callers to use config_entry_id."""
    first_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla",
        data={CONF_LICENSE: "license-123"},
    )
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-456",
        title="Firewalla",
        data={CONF_LICENSE: "license-456"},
    )
    first_entry.runtime_data = object()
    second_entry.runtime_data = object()
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)

    with pytest.raises(ServiceValidationError, match="ambiguous"):
        _get_loaded_entry(hass, entry_id=None, entry_name="Firewalla")


async def test_pause_rule_service_accepts_config_entry_name(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule can target a loaded entry by config_entry_name."""
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
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
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
            return_value=_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule_control_only",
            new=AsyncMock(),
        ) as mock_update_rule,
        patch(
            "custom_components.firewalla_local.services.dt_util.utcnow",
            return_value=datetime.fromtimestamp(1_700_000_000, UTC),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "744",
                SERVICE_FIELD_RULE_DURATION: "30m",
                SERVICE_FIELD_CONFIG_ENTRY_NAME: entry.title,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_update_rule.await_args is not None
    assert mock_update_rule.await_count == 1
    assert mock_update_rule.await_args.kwargs == {
        "enabled": False,
        "idle_ts": 1_700_001_800,
    }


async def test_pause_rule_service_routes_to_requested_config_entry_id(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule uses the requested config entry when multiple are loaded."""
    first_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="First Firewalla",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
        },
    )
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-456",
        title="Second Firewalla",
        data={
            CONF_LICENSE: "license-456",
            CONF_HOST: "192.168.200.2",
            CONF_GID: "gid-456",
            CONF_EID: "eid-456",
            CONF_AID: "aid-456",
            CONF_SYMMETRIC_KEY: "symmetric-key-2",
        },
        options={
            CONF_SELECTED_RULE_IDS: ["888"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "888",
                    "name": "block category games for Upstairs TV",
                    "action": "block",
                    "target": "games",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
        },
    )
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=(
                _snapshot(),
                _snapshot(
                    rule_id="888",
                    target="games",
                    target_name="games",
                ),
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(first_entry.entry_id)
        if second_entry.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(second_entry.entry_id)
        await hass.async_block_till_done()

    first_pause_rule = AsyncMock()
    second_pause_rule = AsyncMock()
    assert isinstance(first_entry.runtime_data, FirewallaRuntimeData)
    assert isinstance(second_entry.runtime_data, FirewallaRuntimeData)
    first_runtime = first_entry.runtime_data
    second_runtime = second_entry.runtime_data

    # Pylint does not follow the runtime_data narrowing through patch.object.
    # pylint: disable=no-member
    with (
        patch.object(
            first_runtime.coordinator,
            "async_request_refresh",
            new=AsyncMock(side_effect=AssertionError("wrong entry refreshed")),
        ),
        patch.object(
            second_runtime.coordinator,
            "async_request_refresh",
            new=AsyncMock(),
        ) as second_refresh,
        patch.object(
            first_runtime.rule_manager,
            "has_rule_target",
            side_effect=AssertionError("wrong rule manager used"),
        ),
        patch.object(
            second_runtime.rule_manager,
            "has_rule_target",
            return_value=True,
        ) as second_has_rule_target,
        patch.object(
            first_runtime.rule_manager,
            "async_pause_rule",
            new=first_pause_rule,
        ),
        patch.object(
            second_runtime.rule_manager,
            "async_pause_rule",
            new=second_pause_rule,
        ),
        patch(
            "custom_components.firewalla_local.services.dt_util.utcnow",
            return_value=datetime.fromtimestamp(1_700_000_000, UTC),
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "888",
                SERVICE_FIELD_RULE_DURATION: "30m",
                SERVICE_FIELD_CONFIG_ENTRY_ID: second_entry.entry_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()
    # pylint: enable=no-member

    second_refresh.assert_awaited_once()
    second_has_rule_target.assert_called_once_with("888")
    first_pause_rule.assert_not_awaited()
    second_pause_rule.assert_awaited_once_with("888", 1_700_001_800)


async def test_pause_rule_service_requires_selector_with_multiple_entries(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule requires explicit entry selection when two entries load."""
    first_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="First Firewalla",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
        },
    )
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-456",
        title="Second Firewalla",
        data={
            CONF_LICENSE: "license-456",
            CONF_HOST: "192.168.200.2",
            CONF_GID: "gid-456",
            CONF_EID: "eid-456",
            CONF_AID: "aid-456",
            CONF_SYMMETRIC_KEY: "symmetric-key-2",
        },
        options={
            CONF_SELECTED_RULE_IDS: ["888"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "888",
                    "name": "block category games for Upstairs TV",
                    "action": "block",
                    "target": "games",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
        },
    )
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=(
                _snapshot(),
                _snapshot(
                    rule_id="888",
                    target="games",
                    target_name="games",
                ),
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(first_entry.entry_id)
        if second_entry.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(second_entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match=("Multiple Firewalla entries are loaded"),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "888",
                SERVICE_FIELD_RULE_DURATION: "30m",
            },
            blocking=True,
        )


async def test_pause_rule_service_rejects_unknown_rule_target(
    hass: HomeAssistant,
) -> None:
    """Test pause_rule rejects targets that are not present in manager state."""
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
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
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
            return_value=_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match=r'No live Firewalla rule matched ".*"',
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_ID: "999",
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )


async def test_resume_rule_service_reenables_matching_rule(
    hass: HomeAssistant,
) -> None:
    """Test resume_rule enables a paused live rule and clears its pause boundary."""
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
        options={
            CONF_SELECTED_RULE_IDS: ["744"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "744",
                    "name": "block category social for AV_SMART_TV",
                    "action": "block",
                    "target": "social",
                    "target_type": "category",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": True,
                    "use_bf": True,
                }
            ],
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
            return_value=_snapshot(enabled=False),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule_control_only",
            new=AsyncMock(),
        ) as mock_update_rule,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_RESUME_RULE,
            {
                SERVICE_FIELD_RULE_ID: "744",
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_update_rule.await_args is not None
    assert mock_update_rule.await_count == 1
    assert mock_update_rule.await_args.kwargs == {"enabled": True}


async def test_run_internet_speed_test_service_returns_acknowledgement(
    hass: HomeAssistant,
) -> None:
    """Test the speed-test trigger service resolves one WAN and returns an ack."""
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
            side_effect=(_speed_test_snapshot(), _speed_test_snapshot()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_run_internet_speed_test",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_run_speed_test,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_RUN_INTERNET_SPEED_TEST,
            {
                SERVICE_FIELD_WAN_NAME: "WAN-ONE",
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_run_speed_test.await_args is not None
    assert mock_run_speed_test.await_args.args == ("wan-1",)
    assert response == {
        "config_entry_id": entry.entry_id,
        "wan": {"uuid": "wan-1", "name": "WAN-ONE"},
        "command": {
            "item": "runInternetSpeedtest",
            "value": {"wan_uuid": "wan-1"},
        },
        "command_response": {"ok": True},
    }


async def test_get_speed_test_results_service_defaults_to_latest_result(
    hass: HomeAssistant,
) -> None:
    """Test the speed-test results service returns the latest result by default."""
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
            side_effect=(_speed_test_snapshot(), _speed_test_snapshot()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_SPEED_TEST_RESULTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["refreshed"] is True
    assert response["count"] == 1
    assert response["wan"] is None
    assert "latest" not in response
    assert response["results"][0]["wan_uuid"] == "wan-1"
    assert response["results"][0]["wan_name"] == "WAN-ONE"


async def test_get_speed_test_results_service_filters_one_wan_without_refresh(
    hass: HomeAssistant,
) -> None:
    """Test the speed-test results service can filter one WAN from cached data."""
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
        ) as mock_get_runtime,
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_speed_test_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_SPEED_TEST_RESULTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_WAN_UUID: "wan-2",
                SERVICE_FIELD_LIMIT: 2,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_runtime.await_count == 1
    assert response is not None
    assert response["refreshed"] is False
    assert response["wan"] == {"uuid": "wan-2", "name": "WAN-TWO"}
    assert response["count"] == 1
    assert response["results"][0]["wan_uuid"] == "wan-2"


async def test_get_internet_quality_report_service_returns_latest_sample(
    hass: HomeAssistant,
) -> None:
    """Test the internet-quality report service returns the latest sample."""
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
            side_effect=(_speed_test_snapshot(), _speed_test_snapshot()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_internet_quality_payload",
            new=AsyncMock(
                return_value={
                    "metric:monitor:raw:ping:1.1.1.1:wan-1": {
                        "1774293094": {
                            "stat": {
                                "lossrate": 0.0017,
                                "max": 73.7,
                                "mean": 22.2,
                                "median": 21,
                                "min": 19.2,
                            }
                        }
                    }
                }
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_INTERNET_QUALITY_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["refreshed"] is True
    assert response["count"] == 1
    assert response["wan"] is None
    assert "latest" not in response
    assert response["samples"][0]["wan_uuid"] == "wan-1"
    assert response["samples"][0]["wan_name"] == "WAN-ONE"
    assert response["samples"][0]["ping_target"] == "1.1.1.1"
    assert response["samples"][0]["ping_latency_ms"] == 22.2
    assert response["samples"][0]["ping_latency_max_ms"] == 73.7
    assert response["samples"][0]["ping_latency_median_ms"] == 21
    assert response["samples"][0]["ping_latency_min_ms"] == 19.2
    assert response["samples"][0]["ping_packet_loss_percent"] == 0.17


async def test_get_internet_quality_report_service_filters_one_wan(
    hass: HomeAssistant,
) -> None:
    """Test the internet-quality report service can filter one WAN."""
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
            return_value=_speed_test_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_internet_quality_payload",
            new=AsyncMock(
                return_value={
                    "metric:monitor:raw:ping:1.1.1.1:wan-1": {
                        "1774293094": {
                            "stat": {
                                "lossrate": 0.0017,
                                "max": 73.7,
                                "mean": 22.2,
                                "median": 21,
                                "min": 19.2,
                            }
                        }
                    },
                    "metric:monitor:raw:ping:1.1.1.1:wan-2": {
                        "1774293000": {
                            "stat": {
                                "lossrate": 0,
                                "max": 45,
                                "mean": 18.75,
                                "median": 18,
                                "min": 15,
                            }
                        }
                    },
                }
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_INTERNET_QUALITY_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_WAN_UUID: "wan-2",
                SERVICE_FIELD_LIMIT: 2,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["refreshed"] is False
    assert response["wan"] == {"uuid": "wan-2", "name": "WAN-TWO"}
    assert response["count"] == 1
    assert response["samples"][0]["wan_uuid"] == "wan-2"


async def test_run_internet_speed_test_service_requires_selector_for_multiple_wans(
    hass: HomeAssistant,
) -> None:
    """Test the speed-test trigger requires a selector when multiple WANs exist."""
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
            side_effect=(_speed_test_snapshot(), _speed_test_snapshot()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_RUN_INTERNET_SPEED_TEST,
                {
                    SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                },
                blocking=True,
                return_response=True,
            )


async def test_wake_host_service_returns_acknowledgement_for_host_mac(
    hass: HomeAssistant,
) -> None:
    """Test the Wake-on-LAN service returns an acknowledgement for one host."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_wake_host",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_wake_host,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_WAKE_HOST,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_MAC: "00:aa:bb:cc:dd:26",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_wake_host.await_args is not None
    assert mock_wake_host.await_args.args == ("00:AA:BB:CC:DD:26",)
    assert response is not None
    assert response == {
        "config_entry_id": entry.entry_id,
        "refreshed": False,
        "target": {
            "kind": "host",
            "id": "00:AA:BB:CC:DD:26",
            "name": "Plex Server",
            "network_kind": None,
        },
        "query": {
            "host_id": None,
            "host_mac": "00:aa:bb:cc:dd:26",
            "host_name": None,
            "refresh": False,
        },
        "command": {
            "item": "wol:wake",
            "target": "00:AA:BB:CC:DD:26",
        },
        "command_response": {"ok": True},
    }


async def test_wake_host_service_resolves_unique_host_name(
    hass: HomeAssistant,
) -> None:
    """Test the Wake-on-LAN service can resolve one host by display name."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_wake_host",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_wake_host,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_WAKE_HOST,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_NAME: "Plex Server",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_wake_host.await_args is not None
    assert mock_wake_host.await_args.args == ("00:AA:BB:CC:DD:26",)


async def test_wake_host_service_resolves_full_host_label(
    hass: HomeAssistant,
) -> None:
    """Test the Wake-on-LAN service can resolve one host by full label."""
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
            return_value=_wake_host_snapshot(duplicate_name=True),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_wake_host",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_wake_host,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_WAKE_HOST,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_NAME: "Plex Server (192.168.10.10)",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_wake_host.await_args is not None
    assert mock_wake_host.await_args.args == ("00:AA:BB:CC:DD:26",)


async def test_wake_host_service_rejects_ambiguous_host_name(
    hass: HomeAssistant,
) -> None:
    """Test the Wake-on-LAN service rejects ambiguous host names."""
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
            return_value=_wake_host_snapshot(duplicate_name=True),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match=(
            r'More than one Firewalla host matches the name "Plex Server"'
            r".*Matching hosts: "
            r".*wg_peer:test-peer.*00:AA:BB:CC:DD:26"
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_WAKE_HOST,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_NAME: "Plex Server",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )


async def test_wake_host_service_rejects_non_wol_host(
    hass: HomeAssistant,
) -> None:
    """Test the Wake-on-LAN service rejects non-MAC pseudo-hosts."""
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(primary_group_name="Media Devices"),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match="does not appear to support Wake-on-LAN",
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_WAKE_HOST,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_ID: "wg_peer:test-peer",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )


async def test_wake_host_service_raises_translated_runtime_error(
    hass: HomeAssistant,
) -> None:
    """Test the Wake-on-LAN service raises a translation-backed runtime error."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_wake_host",
            new=AsyncMock(side_effect=FirewallaApiError("boom")),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(HomeAssistantError) as exc_info:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_WAKE_HOST,
                {
                    SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                    SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                    SERVICE_FIELD_REFRESH: False,
                },
                blocking=True,
                return_response=True,
            )

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == TRANS_KEY_EXCEPTION_WAKE_HOST_FAILED


async def test_delete_host_service_requires_confirmation_toggle(
    hass: HomeAssistant,
) -> None:
    """Test delete_host raises a validation error without confirm: true."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_delete_host",
            new=AsyncMock(return_value={"deleted": "00:AA:BB:CC:DD:26"}),
        ) as mock_delete_host,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(HomeAssistantError) as exc_info:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_DELETE_HOST,
                {
                    SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                    SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                    SERVICE_FIELD_CONFIRM: False,
                    SERVICE_FIELD_REFRESH: False,
                },
                blocking=True,
                return_response=True,
            )

    assert (
        exc_info.value.translation_key
        == TRANS_KEY_EXCEPTION_DELETE_HOST_CONFIRM_REQUIRED
    )
    mock_delete_host.assert_not_awaited()


async def test_delete_host_service_deletes_single_host_and_returns_success(
    hass: HomeAssistant,
) -> None:
    """Test delete_host deletes one resolved host and returns a success result."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_delete_host",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_delete_host,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_DELETE_HOST,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_MAC: "00:aa:bb:cc:dd:26",
                SERVICE_FIELD_CONFIRM: True,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_delete_host.await_args is not None
    assert mock_delete_host.await_args.args == ("00:AA:BB:CC:DD:26",)
    assert response is not None
    assert response == {
        "config_entry_id": entry.entry_id,
        "refreshed": False,
        "command": {"item": "host:delete"},
        "results": [{"host_mac": "00:aa:bb:cc:dd:26", "status": "success"}],
    }


async def test_delete_host_service_handles_multi_host_and_skips_unmatched(
    hass: HomeAssistant,
) -> None:
    """Test delete_host processes multiple MACs and skips unmatched ones."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_delete_host",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_delete_host,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_DELETE_HOST,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_MAC: "00:aa:bb:cc:dd:26, 1E:2F:3A:4B:5C:6D",
                SERVICE_FIELD_CONFIRM: True,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_delete_host.await_count == 1
    assert mock_delete_host.await_args.args == ("00:AA:BB:CC:DD:26",)
    assert response is not None
    assert response == {
        "config_entry_id": entry.entry_id,
        "refreshed": False,
        "command": {"item": "host:delete"},
        "results": [
            {"host_mac": "00:aa:bb:cc:dd:26", "status": "success"},
            {
                "host_mac": "1E:2F:3A:4B:5C:6D",
                "status": "skipped",
                "reason": "not_found",
            },
        ],
    }


async def test_set_host_notify_when_next_online_returns_acknowledgement(
    hass: HomeAssistant,
) -> None:
    """Test the online notification toggle returns an acknowledgement."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_policy",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_set_host_policy,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_ONLINE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_ENABLED: True,
                SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_set_host_policy.await_args is not None
    assert mock_set_host_policy.await_args.args == (
        "00:AA:BB:CC:DD:26",
        {"devicePresence": True},
    )
    assert response is not None
    assert response == {
        "config_entry_id": entry.entry_id,
        "refreshed": False,
        "target": {
            "kind": "host",
            "id": "00:AA:BB:CC:DD:26",
            "name": "Plex Server",
            "network_kind": None,
        },
        "query": {
            "enabled": True,
            "host_id": None,
            "host_mac": "00:AA:BB:CC:DD:26",
            "host_name": None,
            "refresh": False,
        },
        "notification": {
            "enabled": True,
            "name": "notify_when_next_online",
            "policy_key": "devicePresence",
        },
        "command": {
            "item": "policy",
            "target": "00:AA:BB:CC:DD:26",
            "value": {"devicePresence": True},
        },
        "command_response": {"ok": True},
    }


async def test_set_host_notify_when_next_offline_resolves_host_name(
    hass: HomeAssistant,
) -> None:
    """Test the offline notification toggle resolves one host by name."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_policy",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_set_host_policy,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_OFFLINE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_ENABLED: False,
                SERVICE_FIELD_HOST_NAME: "Plex Server",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_set_host_policy.await_args is not None
    assert mock_set_host_policy.await_args.args == (
        "00:AA:BB:CC:DD:26",
        {"deviceOffline": False},
    )
    assert response is not None
    assert response["notification"] == {
        "enabled": False,
        "name": "notify_when_next_offline",
        "policy_key": "deviceOffline",
    }


async def test_set_host_name_returns_acknowledgement_for_host_mac(
    hass: HomeAssistant,
) -> None:
    """Test the host rename service returns an acknowledgement."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_name",
            new=AsyncMock(return_value={}),
        ) as mock_set_host_name,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_NAME,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                SERVICE_FIELD_NEW_NAME: "Plex Server Renamed",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_set_host_name.await_args is not None
    assert mock_set_host_name.await_args.args == (
        "00:AA:BB:CC:DD:26",
        "Plex Server Renamed",
    )
    assert response is not None
    assert response == {
        "config_entry_id": entry.entry_id,
        "refreshed": False,
        "target": {
            "kind": "host",
            "id": "00:AA:BB:CC:DD:26",
            "name": "Plex Server",
            "network_kind": None,
        },
        "query": {
            "new_name": "Plex Server Renamed",
            "host_id": None,
            "host_mac": "00:AA:BB:CC:DD:26",
            "host_name": None,
            "refresh": False,
        },
        "host_name": {
            "new_name": "Plex Server Renamed",
        },
        "command": {
            "item": "host",
            "target": "00:AA:BB:CC:DD:26",
            "value": {"name": "Plex Server Renamed"},
        },
        "command_response": {},
    }


async def test_set_host_name_resolves_unique_host_name(
    hass: HomeAssistant,
) -> None:
    """Test the host rename service can resolve one host by display name."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_name",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_set_host_name,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_NAME,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_NAME: "Plex Server",
                SERVICE_FIELD_NEW_NAME: "Plex Server Name 2",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_set_host_name.await_args is not None
    assert mock_set_host_name.await_args.args == (
        "00:AA:BB:CC:DD:26",
        "Plex Server Name 2",
    )


async def test_set_host_dns_hostname_returns_acknowledgement_for_host_mac(
    hass: HomeAssistant,
) -> None:
    """Test the host DNS hostname service returns an acknowledgement."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_dns_hostname",
            new=AsyncMock(return_value={}),
        ) as mock_set_host_dns_hostname,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_DNS_HOSTNAME,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                SERVICE_FIELD_DNS_HOSTNAME: "plex.server.3",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_set_host_dns_hostname.await_args is not None
    assert mock_set_host_dns_hostname.await_args.args == (
        "00:AA:BB:CC:DD:26",
        "plex.server.3",
    )
    assert response is not None
    assert response == {
        "config_entry_id": entry.entry_id,
        "refreshed": False,
        "target": {
            "kind": "host",
            "id": "00:AA:BB:CC:DD:26",
            "name": "Plex Server",
            "network_kind": None,
        },
        "query": {
            "dns_hostname": "plex.server.3",
            "host_id": None,
            "host_mac": "00:AA:BB:CC:DD:26",
            "host_name": None,
            "refresh": False,
        },
        "dns_hostname": {
            "dns_hostname": "plex.server.3",
        },
        "command": {
            "item": "hostDomain",
            "target": "00:AA:BB:CC:DD:26",
            "value": {"customizeDomainName": "plex.server.3"},
        },
        "command_response": {},
    }


async def test_set_host_device_type_returns_acknowledgement_for_host_mac(
    hass: HomeAssistant,
) -> None:
    """Test the host device type service returns an acknowledgement."""
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
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_device_type",
            new=AsyncMock(return_value={}),
        ) as mock_set_host_device_type,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_DEVICE_TYPE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                SERVICE_FIELD_HOST_DEVICE_TYPE: "tablet",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_set_host_device_type.await_args is not None
    assert mock_set_host_device_type.await_args.args == (
        "00:AA:BB:CC:DD:26",
        "tablet",
    )
    assert response is not None
    assert response == {
        "config_entry_id": entry.entry_id,
        "refreshed": False,
        "target": {
            "kind": "host",
            "id": "00:AA:BB:CC:DD:26",
            "name": "Plex Server",
            "network_kind": None,
        },
        "query": {
            "host_device_type": "tablet",
            "host_id": None,
            "host_mac": "00:AA:BB:CC:DD:26",
            "host_name": None,
            "refresh": False,
        },
        "host_device_type": {
            "host_device_type": "tablet",
        },
        "command": {
            "item": "feedback",
            "target": "0.0.0.0",
            "value": {
                "key": "device.detect",
                "target": "00:AA:BB:CC:DD:26",
                "value": {"type": "tablet"},
            },
        },
        "command_response": {},
    }


async def test_sync_runtime_reports_snapshot_time(hass: HomeAssistant) -> None:
    """Test the sync runtime service polls the box and reports the snapshot time."""
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
            return_value=_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.coordinator."
            "FirewallaDataUpdateCoordinator.async_request_refresh",
            new=AsyncMock(),
        ) as mock_refresh,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SYNC_RUNTIME,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )

    assert mock_refresh.await_count == 1
    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["synced"] is True
    assert set(response) == {
        "config_entry_id",
        "synced",
        "synced_at",
        "synced_at_timestamp",
    }


async def test_get_rules_returns_attachment_and_purpose_fields(
    hass: HomeAssistant,
) -> None:
    """Test rule summaries expose group/network attachments and purpose.

    Without `applies_to` and `tag_refs` a group- or network-scoped rule is
    indistinguishable from an unattached one, because `scope` only covers
    device-scoped rules.
    """
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
            return_value=_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RULES,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )

    assert response is not None
    rule = response["rules"][0]
    assert rule["applies_to"] == ["AV_SMART_TV"]
    assert rule["tag_refs"] == ["tag:17"]
    assert rule["purpose"] is None


async def test_get_rules_exposes_hit_count_and_last_hit(
    hass: HomeAssistant,
) -> None:
    """A rule reports whether it fires, and what it last matched.

    This is what makes the rule list answer two questions it could not before:
    "why is this device blocked?", from the device and destination on the last
    hit, and "what can I clean up?", from rules that have never fired.
    """
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

    snapshot = replace(
        _snapshot(),
        policy_rules=(
            replace(
                _snapshot().policy_rules[0],
                hit_count=26617,
                last_hit=FirewallaFlowRecord(
                    timestamp=1790990234.243,
                    device_id="74:A7:EA:24:44:44",
                    device_ip="192.168.202.43",
                    destination="www.youtube.com",
                    destination_kind="domain",
                    destination_ip=None,
                    port=53,
                    protocol="dns",
                    app="youtube",
                    category="av",
                ),
            ),
            replace(_snapshot(rule_id="672").policy_rules[0], hit_count=0),
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

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RULES,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )

    assert response is not None
    by_id = {rule["rule_id"]: rule for rule in response["rules"]}
    fired, never = by_id["744"], by_id["672"]

    assert fired["hit_count"] == 26617
    # `last_hit` projects the shared flow record. `download_bytes` /
    # `upload_bytes` are present here because this fixture models a *regular*
    # flow: a blocked one has no bytes at all and would read None rather than 0.
    assert fired["last_hit"] == {
        "timestamp": 1790990234.243,
        "at": "2026-10-03T01:17:14.243000+00:00",
        "is_blocked": None,
        "block_type": None,
        "blocked_by_rule_id": None,
        "device_id": "74:A7:EA:24:44:44",
        "device_ip": "192.168.202.43",
        "destination": "www.youtube.com",
        "destination_kind": "domain",
        "destination_ip": None,
        "destination_mac": None,
        "port": 53,
        "device_port": None,
        "protocol": "dns",
        "download_bytes": None,
        "upload_bytes": None,
        "duration_seconds": None,
        "event_count": None,
        "network_id": None,
        "app": "youtube",
        "category": "av",
        "region": None,
    }
    # A rule with no recorded matches reads as 0, not null, so "never fired" is a
    # comparison rather than a null check. `last_hit` has nothing to describe and
    # stays null.
    assert never["hit_count"] == 0
    assert never["last_hit"] is None


async def test_get_rules_excludes_product_owned_purposes_by_default(
    hass: HomeAssistant,
) -> None:
    """Test DAP and family rules are hidden unless explicitly requested."""
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

    snapshot = _snapshot()
    dap_rule = replace(
        snapshot.policy_rules[0],
        rule_id="900",
        purpose="dap",
        target_name="dap_bc2411a6aef9",
    )
    snapshot = replace(snapshot, policy_rules=(*snapshot.policy_rules, dap_rule))

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

        default = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RULES,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )
        included = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RULES,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_INCLUDE_PURPOSE: ["dap"],
            },
            blocking=True,
            return_response=True,
        )

    assert default is not None
    assert [rule["rule_id"] for rule in default["rules"]] == ["744"]
    assert included is not None
    assert sorted(rule["rule_id"] for rule in included["rules"]) == ["744", "900"]


async def test_get_rules_excludes_system_managed_rules_by_default(
    hass: HomeAssistant,
) -> None:
    """Test subsystem-owned rules are hidden unless explicitly requested."""
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

    snapshot = _snapshot()
    auto_block = replace(
        snapshot.policy_rules[0],
        rule_id="651",
        target="66.132.195.91",
        target_type="ip",
        target_name=None,
        applies_to=(),
        tag_refs=(),
        raw_update_payload={"pid": "651", "method": "auto", "action": "block"},
    )
    snapshot = replace(snapshot, policy_rules=(*snapshot.policy_rules, auto_block))

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

        default = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RULES,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )
        included = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RULES,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_INCLUDE_SYSTEM_MANAGED: True,
            },
            blocking=True,
            return_response=True,
        )

    assert default is not None
    assert [rule["rule_id"] for rule in default["rules"]] == ["744"]
    assert included is not None
    assert sorted(rule["rule_id"] for rule in included["rules"]) == ["651", "744"]


async def test_get_rules_supports_filters(hass: HomeAssistant) -> None:
    """Test the rule filters narrow the result server-side."""
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
            return_value=_snapshot(enabled=False),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        matches = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RULES,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_APPLIES_TO: "AV_SMART_TV",
                SERVICE_FIELD_ENABLED: False,
            },
            blocking=True,
            return_response=True,
        )
        no_match = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_RULES,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_ENABLED: True,
            },
            blocking=True,
            return_response=True,
        )

    assert matches is not None
    assert [rule["rule_id"] for rule in matches["rules"]] == ["744"]
    assert no_match is not None
    assert no_match["rules"] == []


_TRANSLATIONS_PATH: Final = (
    Path(__file__).parents[3]
    / "custom_components"
    / "firewalla_local"
    / "translations"
    / "en.json"
)
_SERVICES_YAML_PATH: Final = (
    Path(__file__).parents[3]
    / "custom_components"
    / "firewalla_local"
    / "services.yaml"
)
_USER_GUIDE_PATH: Final = Path(__file__).parents[3] / "docs" / "USER_GUIDE.md"


def _parse_services_yaml() -> dict[str, Any]:
    """Return services.yaml parsed, so an invalid file fails loudly here."""
    import yaml

    parsed = yaml.safe_load(_SERVICES_YAML_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_user_guide_catalog_lists_every_service() -> None:
    """The user guide's service catalog names every registered service.

    The catalog is the list a user scans to find out what exists, and nothing
    kept it in step with the registrations, so `get_rules` and `create_rule`
    shipped without appearing in it at all. Both directions are checked: a
    missing service is undiscoverable, and a catalog entry for a service that no
    longer exists sends the reader after something that cannot be called.
    """
    guide = _USER_GUIDE_PATH.read_text(encoding="utf-8")
    catalog = {
        match.group(1)
        for match in re.finditer(r"^- `firewalla_local\.([a-z_]+)`$", guide, re.M)
    }
    registered = {
        match.group(1)
        for match in re.finditer(
            r"^([a-z_]+):$", _SERVICES_YAML_PATH.read_text(encoding="utf-8"), re.M
        )
    }

    assert registered - catalog == set(), "services absent from the user guide"
    assert catalog - registered == set(), "catalog entries with no service"


def test_every_service_has_a_translation_and_no_orphans() -> None:
    """Every service is translated, and no translation describes a missing service.

    A service with no translation shows an empty title/description to users, and
    an orphaned entry is dead weight that hides which services still exist. Both
    directions are checked so the surface cannot drift from its documentation.
    """
    translations = json.loads(_TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    translated = set(translations["services"])
    declared = {
        match.group(1)
        for match in re.finditer(
            r"^([a-z_]+):$", _SERVICES_YAML_PATH.read_text(encoding="utf-8"), re.M
        )
    }

    assert declared - translated == set(), "services missing a translation"
    assert translated - declared == set(), "translation entries with no service"


def test_every_service_field_is_documented() -> None:
    """Every service field accepted by a schema is named in both doc surfaces.

    The mirror of the LLM reference check, for the human-facing surface. It
    caught `get_hosts` growing eight server-side filters for the AI
    tools while the docs still described only `refresh` and the entry selectors,
    and the same pattern in `get_rules` (six), `get_wan_events` (two), and
    `get_network_segment_report` (one). Automations could not discover
    capabilities the services already had. Schemas are the source of truth.
    """
    from custom_components.firewalla_local.services import _SERVICE_REGISTRATIONS

    translations = json.loads(_TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    yaml_services = _parse_services_yaml()
    gaps: list[str] = []

    for name, _handler, schema, _response, _admin in _SERVICE_REGISTRATIONS:
        fields = {marker.schema for marker in schema.schema}
        in_json = set((translations["services"].get(name) or {}).get("fields") or {})
        in_yaml = set((yaml_services.get(name) or {}).get("fields") or {})
        for field in sorted(fields - in_json):
            gaps.append(f"{name}: {field} missing from translations")
        for field in sorted(fields - in_yaml):
            gaps.append(f"{name}: {field} missing from services.yaml")

    assert gaps == [], f"undocumented service fields: {gaps}"


def test_services_yaml_is_valid_and_matches_translations() -> None:
    """services.yaml parses, and both surfaces document the same fields.

    An unquoted colon inside a description silently makes the file invalid YAML.
    One shipped that way in `get_rules` ("Defaults to user-visible rules: ..."),
    which no test covered, because nothing parsed the file.
    """
    yaml_services = _parse_services_yaml()
    translations = json.loads(_TRANSLATIONS_PATH.read_text(encoding="utf-8"))

    yaml_fields = {
        name: set(entry.get("fields") or {}) for name, entry in yaml_services.items()
    }
    json_fields = {
        name: set(entry.get("fields") or {})
        for name, entry in translations["services"].items()
    }

    mismatched = {
        name: {
            "yaml": sorted(yaml_fields.get(name, set())),
            "json": sorted(json_fields.get(name, set())),
        }
        for name in set(yaml_fields) | set(json_fields)
        if yaml_fields.get(name, set()) != json_fields.get(name, set())
    }

    assert mismatched == {}, f"services.yaml and translations disagree: {mismatched}"


async def test_get_system_overview_reports_counts_without_identities(
    hass: HomeAssistant,
) -> None:
    """The default summary carries counts and network names, never identities."""
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "build_runtime_snapshot",
            return_value=_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        overview = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_SYSTEM_OVERVIEW,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )

    assert overview is not None
    assert overview["devices"]["total"] == 1
    assert overview["vpn_devices"] == {"total": 0, "online": 0, "offline": 0}
    assert overview["rules"]["total"] == 1
    assert overview["alarms"] == {"active": 0, "archived": 0}
    assert overview["networks"]["count"] == len(overview["networks"]["items"])
    assert overview["networks"]["count"] >= 1
    for network in overview["networks"]["items"]:
        assert set(network) == {
            "uuid",
            "name",
            "kind",
            "ipv4_subnets",
            "device_count",
            "online",
            "offline",
        }
    # No identity collections unless asked for.
    assert "items" not in overview["groups"]
    assert "items" not in overview["users"]
    assert overview["llm_access"]["mode"] == DEFAULT_LLM_TOOL_MODE
    # The note must describe this tier, not claim detail is unavailable.
    assert "Read only" in overview["llm_access"]["note"]


async def test_llm_access_note_describes_the_active_tier(
    hass: HomeAssistant,
) -> None:
    """The access note tracks the mode instead of always asking for more.

    A fixed "raise access for rules and alarms" line is false above the summary
    tier — the assistant would tell a user to unlock what they already have, and
    could not answer "what else could you do?". Each tier's note now states what
    it reaches and what the next step would add.
    """
    notes: dict[str, str] = {}
    for mode in (
        LLM_TOOL_MODE_SUMMARY_ONLY,
        LLM_TOOL_MODE_READ_ONLY,
        LLM_TOOL_MODE_READ_AND_CONTROL,
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=f"license-{mode}",
            title="Firewalla (192.168.200.1)",
            data={
                CONF_LICENSE: "license-123",
                CONF_HOST: "192.168.200.1",
                CONF_GID: "gid-123",
                CONF_EID: "eid-123",
                CONF_AID: "aid-123",
                CONF_SYMMETRIC_KEY: "symmetric-key",
            },
            options={CONF_LLM_TOOL_MODE: mode},
        )
        entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.firewalla_local.api.client.FirewallaApiClient."
                "async_get_runtime_init_payload",
                new=AsyncMock(return_value=_runtime_payload()),
            ),
            patch(
                "custom_components.firewalla_local.api.client.FirewallaApiClient."
                "build_runtime_snapshot",
                return_value=_snapshot(),
            ),
        ):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            overview = await hass.services.async_call(
                DOMAIN,
                SERVICE_GET_SYSTEM_OVERVIEW,
                {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
                blocking=True,
                return_response=True,
            )

        assert overview is not None
        assert overview["llm_access"]["mode"] == mode
        notes[mode] = overview["llm_access"]["note"]

    assert len(set(notes.values())) == 3, "each tier must describe itself"
    # The summary tier points upward; the higher tiers do not pretend to be short.
    assert "Read only" in notes[LLM_TOOL_MODE_SUMMARY_ONLY]
    assert "Read only" not in notes[LLM_TOOL_MODE_READ_ONLY]
    assert "Full" in notes[LLM_TOOL_MODE_READ_AND_CONTROL]


async def test_get_system_overview_includes_identifiers_on_request(
    hass: HomeAssistant,
) -> None:
    """Identifiers are opt-in, so they never ride along by default."""
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "build_runtime_snapshot",
            return_value=_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        overview = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_SYSTEM_OVERVIEW,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_INCLUDE: ["identifiers"],
            },
            blocking=True,
            return_response=True,
        )

    assert overview is not None
    assert overview["groups"]["items"] == []
    assert overview["users"]["items"] == []
    assert "items" in overview["groups"]


async def test_get_system_overview_identifiers_separate_groups_from_users(
    hass: HomeAssistant,
) -> None:
    """The `groups` section reports plain groups and the `users` section users.

    The tag collection holds both together, so a user entry used to be counted
    and listed as a group. Each identifier now carries `kind` as well, so a
    consumer separates the two by that field rather than by name.
    """
    entry = _membership_entry()
    entry.add_to_hass(hass)

    write = AsyncMock(return_value={"ok": True})
    with _membership_patches(write):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        overview = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_SYSTEM_OVERVIEW,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_INCLUDE: ["identifiers"],
            },
            blocking=True,
            return_response=True,
        )

    assert overview is not None
    # The snapshot holds four plain groups and three users.
    assert overview["groups"]["count"] == 4
    assert overview["users"]["count"] == 3
    assert overview["groups"]["items"] == [
        {"id": "12", "name": "Quarantine", "kind": "group"},
        {"id": "53", "name": "IOT_LIGHTS", "kind": "group"},
        {"id": "66", "name": "IOT_LIGHTS", "kind": "group"},
        {"id": "99", "name": "KADEN", "kind": "group"},
    ]
    assert [item["kind"] for item in overview["users"]["items"]] == ["user"] * 3
    # A user entry never appears in the groups section, even though it lives in
    # the same collection and its name collides with a real group's.
    assert "10" not in [item["id"] for item in overview["groups"]["items"]]
    assert "11" not in [item["id"] for item in overview["groups"]["items"]]


async def test_connectivity_is_one_definition_across_every_surface(
    hass: HomeAssistant,
) -> None:
    """The list, the counts and the watched-device sensor agree on `online`.

    The three surfaces previously kept separate windows, so the same device
    could be online for one and offline for another. They now share the single
    connectivity window, so this asserts the list, the overview counts and the
    same host's watched-device sensor all agree.

    The windows are intentionally shorter than the device tracker's presence
    window: `idle-but-fresh` carries `stale: false` (the box's seven-day signal)
    and is still not connected, which is exactly the distinction `online` has to
    make.
    """
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

    base = _snapshot()
    template = base.hosts[0]
    # Reference host sets the freshness baseline.
    reference = replace(template, mac="AA:BB:CC:DD:EE:01", last_active=1_000_000.0)
    # Idle 2 min: inside the 5-minute connectivity window, and not stale.
    recent = replace(
        template,
        mac="AA:BB:CC:DD:EE:02",
        host_name="just-connected",
        last_active=1_000_000.0 - 120.0,
        stale=False,
    )
    # Idle 6 min: not stale, but past the connectivity tolerance, so this must
    # read as not connected.
    quiet = replace(
        template,
        mac="AA:BB:CC:DD:EE:03",
        host_name="quiet-but-not-stale",
        last_active=1_000_000.0 - 360.0,
        stale=False,
    )
    # Idle 63.8 min: well past every window, and still not stale.
    idle = replace(
        template,
        mac="AA:BB:CC:DD:EE:04",
        host_name="idle-but-fresh",
        last_active=1_000_000.0 - 3828.0,
        stale=False,
    )
    snapshot = replace(base, hosts=(reference, recent, quiet, idle))

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "build_runtime_snapshot",
            return_value=snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        overview = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_SYSTEM_OVERVIEW,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )
        hosts = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_HOSTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    # `quiet-but-not-stale` and `idle-but-fresh` both carry `stale: false` — the
    # box's seven-day signal — yet neither is connected, which is exactly the
    # distinction `online` has to make.
    assert hosts is not None
    online = {h["host_name"]: h["online"] for h in hosts["hosts"]}
    assert online == {
        "Firewalla": True,
        "just-connected": True,
        "quiet-but-not-stale": False,
        "idle-but-fresh": False,
    }

    # And the summary counts agree with the list.
    assert overview is not None
    assert overview["devices"]["total"] == 4
    assert overview["devices"]["online"] == sum(1 for v in online.values() if v)

    # The watched-device sensor reads the same state, because it now shares the
    # one online window rather than keeping its own.
    host_manager = entry.runtime_data.host_manager
    for host in host_manager.get_hosts():
        assert host_manager.is_watched_device_online(host) == online[host.host_name]


async def test_get_system_overview_counts_vpn_peers_separately(
    hass: HomeAssistant,
) -> None:
    """VPN peers are counted as a breakdown of the device total.

    Peers reuse the shared online definition, so a recent peer counts online
    and a stale one does not — the same 1-online/1-offline shape seen live.
    """
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

    base = _snapshot()
    template = base.hosts[0]
    recent_peer = replace(
        template,
        mac="wg_peer:chads-phone",
        host_name="chads-phone-wgvpn",
        connection_type="vpn",
        last_active=1_700_000_000.0,
    )
    stale_peer = replace(
        template,
        mac="awg_peer:chads-laptop",
        host_name="chads-laptop-awgvpn",
        connection_type="vpn",
        last_active=1_600_000_000.0,
    )
    snapshot = replace(base, hosts=(*base.hosts, recent_peer, stale_peer))

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "build_runtime_snapshot",
            return_value=snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        overview = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_SYSTEM_OVERVIEW,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )
        peers = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_HOSTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_KIND: "pseudo_host",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert overview is not None
    assert overview["devices"]["total"] == 3
    assert overview["vpn_devices"] == {"total": 2, "online": 1, "offline": 1}

    # The list agrees with the summary. Answering "how many are connected?"
    # from the length of this list is the bug the smoke test found: both peers
    # are returned, but only one is online.
    assert peers is not None
    assert len(peers["hosts"]) == 2
    assert [host["online"] for host in peers["hosts"]] == [False, True]
    assert sum(1 for host in peers["hosts"] if host["online"]) == 1


async def test_get_hosts_defaults_to_summary_detail(
    hass: HomeAssistant,
) -> None:
    """Test the host-name mapping service defaults to the compact summary shape.

    Summary omits `dns_fqdn` (derivable), `dhcp_name` (unreliable) and the
    nested `ip_assignment`, flattening the assignment's useful parts instead.
    """
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(primary_group_name="Media Devices"),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_HOSTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response == {
        "hosts": [
            {
                "host_id": "00:AA:BB:CC:DD:26",
                "mac": "00:AA:BB:CC:DD:26",
                "ip_address": "192.168.10.10",
                "host_name": "Plex Server",
                "dns_hostname": "plex-server",
                "dns_domain": "int.ccpk.us",
                "group_name": "Media Devices",
                "host_device_type": "tablet",
                "kind": "mac_host",
                "network_uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
                "network_name": "VLAN10 CORE",
                "online": True,
                "last_active": None,
                "vpn_client": None,
                "ip_assignment_mode": "static",
                "reserved_ipv4": "192.168.10.10",
            },
            {
                "host_id": "wg_peer:test-peer",
                "mac": None,
                "ip_address": "10.42.0.2",
                "host_name": "WireGuard Kaden",
                "dns_hostname": None,
                "dns_domain": "int.ccpk.us",
                "group_name": None,
                "host_device_type": None,
                "kind": "pseudo_host",
                "network_uuid": None,
                "network_name": "VLAN10 CORE",
                "online": True,
                "last_active": None,
                "vpn_client": None,
                "ip_assignment_mode": None,
                "reserved_ipv4": None,
            },
        ],
    }


async def test_get_hosts_full_detail_includes_derived_fields(
    hass: HomeAssistant,
) -> None:
    """Test the full detail shape keeps the derivable and nested fields."""
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(primary_group_name="Media Devices"),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_HOSTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_DETAIL: "full",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    first = response["hosts"][0]
    assert first["dns_fqdn"] == "plex-server.int.ccpk.us"
    assert first["dhcp_name"] == "plex-server"
    assert first["ip_assignment"] == {
        "mode": "static",
        "network_uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
        "reserved_ipv4": "192.168.10.10",
    }
    assert "ip_assignment_mode" not in first


async def test_get_hosts_supports_filters(
    hass: HomeAssistant,
) -> None:
    """Test the host filters narrow the result server-side."""
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(primary_group_name="Media Devices"),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        by_name = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_HOSTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_NAME: "plex",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )
        vpn_only = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_HOSTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_KIND: "pseudo_host",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert by_name is not None
    assert [host["host_name"] for host in by_name["hosts"]] == ["Plex Server"]
    assert vpn_only is not None
    assert [host["host_name"] for host in vpn_only["hosts"]] == ["WireGuard Kaden"]


@pytest.mark.parametrize(
    "user_selector",
    [
        pytest.param("KADEN", id="by_user_name"),
        pytest.param("21", id="by_user_id"),
    ],
)
async def test_get_hosts_user_filter_matches_through_the_backing_tag(
    hass: HomeAssistant,
    user_selector: str,
) -> None:
    """The `user` filter finds devices assigned to a user.

    A device assigned to a user carries the user's affiliated backing tag in
    `group_ids`. The host-level `userTags` array that feeds `host.user_ids` is
    always empty on a real box (Finding 42 — 0 of 211 hosts on the dev box), so
    matching on `user_ids` alone could never match anything and the filter
    returned no hosts for every selector. It now resolves the user to their
    backing tag and matches that against `group_ids`.
    """
    entry = _membership_entry()
    entry.add_to_hass(hass)

    write = AsyncMock(return_value={"ok": True})
    with _membership_patches(write, snapshot=_user_filter_snapshot()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_HOSTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_USER: user_selector,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert [host["host_name"] for host in response["hosts"]] == ["Kaden Phone"]


async def test_get_hosts_user_filter_returns_nothing_for_an_unknown_user(
    hass: HomeAssistant,
) -> None:
    """An unknown user selector yields no hosts rather than raising."""
    entry = _membership_entry()
    entry.add_to_hass(hass)

    write = AsyncMock(return_value={"ok": True})
    with _membership_patches(write, snapshot=_user_filter_snapshot()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_HOSTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_USER: "NOSUCHUSER",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["hosts"] == []


async def _call_set_host_membership(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    data: dict[str, object],
) -> dict[str, Any]:
    """Call the membership service and return its response."""
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_HOST_MEMBERSHIP,
        {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id, **data},
        blocking=True,
        return_response=True,
    )
    assert response is not None
    return response


@pytest.mark.parametrize(
    ("data", "expected_tag_id", "expected_kind", "expected_name", "expected_changed"),
    [
        pytest.param(
            {SERVICE_FIELD_GROUP_NAME: "Quarantine"},
            "12",
            "group",
            "Quarantine",
            True,
            id="group_by_name",
        ),
        pytest.param(
            {SERVICE_FIELD_GROUP_ID: "66"},
            "66",
            "group",
            "IOT_LIGHTS",
            True,
            id="group_by_id_resolves_an_ambiguous_name",
        ),
        pytest.param(
            {SERVICE_FIELD_USER_NAME: "KADEN"},
            "10",
            "user",
            "KADEN",
            False,
            id="user_by_name_writes_the_backing_tag",
        ),
    ],
)
async def test_set_host_membership_writes_the_resolved_tag(
    hass: HomeAssistant,
    data: dict[str, object],
    expected_tag_id: str,
    expected_kind: str,
    expected_name: str,
    expected_changed: bool,
) -> None:
    """Assign a device to a group or a user by writing the resolved backing tag.

    A user assignment is expressed on the wire as the user's affiliated backing
    tag, not the user id, so the user case asserts the tag and not `user_id`.
    """
    entry = _membership_entry()
    entry.add_to_hass(hass)
    write = AsyncMock(return_value={"ok": True})

    with _membership_patches(write):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await _call_set_host_membership(
            hass,
            entry,
            {
                SERVICE_FIELD_HOST_MAC: "0C:85:E1:B0:1D:1C",
                SERVICE_FIELD_REFRESH: False,
                **data,
            },
        )

    assert write.await_args is not None
    assert write.await_args.args == (
        "0C:85:E1:B0:1D:1C",
        {"tags": [int(expected_tag_id)]},
    )
    assert response["membership"] == {
        "before": {"kind": "user", "id": "10", "name": "KADEN"},
        "after": {
            "kind": expected_kind,
            "id": expected_tag_id,
            "name": expected_name,
        },
        "changed": expected_changed,
    }


async def test_set_host_membership_clears_the_current_assignment(
    hass: HomeAssistant,
) -> None:
    """Clearing sends an explicit empty tag list and reports what was removed."""
    entry = _membership_entry()
    entry.add_to_hass(hass)
    write = AsyncMock(return_value={"ok": True})

    with _membership_patches(write):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await _call_set_host_membership(
            hass,
            entry,
            {
                SERVICE_FIELD_HOST_MAC: "0C:85:E1:B0:1D:1C",
                SERVICE_FIELD_CLEAR: True,
                SERVICE_FIELD_REFRESH: False,
            },
        )

    assert write.await_args is not None
    assert write.await_args.args == ("0C:85:E1:B0:1D:1C", {"tags": []})
    assert response["membership"] == {
        "before": {"kind": "user", "id": "10", "name": "KADEN"},
        "after": None,
        "changed": True,
    }


@pytest.mark.parametrize(
    ("data", "expected_slug"),
    [
        pytest.param(
            {SERVICE_FIELD_GROUP_NAME: "IOT_LIGHTS"},
            "ambiguous",
            id="ambiguous_group_name",
        ),
        pytest.param(
            {SERVICE_FIELD_USER_NAME: "PAYTON"},
            "ambiguous",
            id="ambiguous_user_name",
        ),
        pytest.param(
            {SERVICE_FIELD_GROUP_NAME: "No Such Group"},
            "not_found",
            id="unknown_group_name",
        ),
        pytest.param(
            {SERVICE_FIELD_GROUP_ID: "10"},
            "not_found",
            id="user_tag_id_rejected_as_a_group",
        ),
        pytest.param(
            {SERVICE_FIELD_USER_NAME: "NOSUCHUSER"},
            "not_found",
            id="unknown_user_name",
        ),
        pytest.param(
            {SERVICE_FIELD_USER_ID: "99"},
            "not_found",
            id="group_tag_id_rejected_as_a_user",
        ),
    ],
)
async def test_set_host_membership_rejects_bad_targets(
    hass: HomeAssistant,
    data: dict[str, object],
    expected_slug: str,
) -> None:
    """Reject unknown targets, and keep group and user selectors apart.

    Tag `10` is the user's backing tag and tag `99` is a plain group, so each
    cross-kind case here would resolve if the selector were not scoped by kind.
    """
    entry = _membership_entry()
    entry.add_to_hass(hass)
    write = AsyncMock(return_value={"ok": True})

    with _membership_patches(write):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError) as err:
            await _call_set_host_membership(
                hass,
                entry,
                {
                    SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                    SERVICE_FIELD_REFRESH: False,
                    **data,
                },
            )

    assert write.await_count == 0
    assert err.value.translation_key is not None
    assert err.value.translation_key.endswith(expected_slug)


@pytest.mark.parametrize(
    ("data", "expected_key"),
    [
        pytest.param(
            {SERVICE_FIELD_REFRESH: False},
            "membership_target_required",
            id="no_target",
        ),
        pytest.param(
            {
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_CLEAR: True,
                SERVICE_FIELD_REFRESH: False,
            },
            "membership_target_conflict",
            id="clear_with_a_target",
        ),
        pytest.param(
            {
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_USER_NAME: "KADEN",
                SERVICE_FIELD_REFRESH: False,
            },
            "membership_target_required",
            id="group_and_user_together",
        ),
        pytest.param(
            {
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_GROUP_ID: "12",
                SERVICE_FIELD_REFRESH: False,
            },
            "membership_target_required",
            id="two_group_selectors",
        ),
    ],
)
async def test_set_host_membership_requires_exactly_one_target(
    hass: HomeAssistant,
    data: dict[str, object],
    expected_key: str,
) -> None:
    """Require exactly one of a group, a user, or clear."""
    entry = _membership_entry()
    entry.add_to_hass(hass)
    write = AsyncMock(return_value={"ok": True})

    with _membership_patches(write):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError) as err:
            await _call_set_host_membership(
                hass,
                entry,
                {SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26", **data},
            )

    assert write.await_count == 0
    assert err.value.translation_key == expected_key


async def test_set_host_membership_removes_the_device_own_rules(
    hass: HomeAssistant,
) -> None:
    """A membership change deletes every rule the device owns.

    Confirmed by capture on 2026-10-02: assigning an unassigned device to a group
    sent `policy:delete` for all four of its rules -- two enabled user rules and
    two disabled Active Protect rules -- before the tags write, in one batch. The
    device then follows only its group's rules, which is what the app warns about
    when you assign one.

    The selector is "the device's MAC is the target or appears in scope". It is
    deliberately not keyed on `purpose == "dap"`: an earlier version was, which
    would have left the two enabled user rules behind.
    """
    entry = _membership_entry()
    entry.add_to_hass(hass)
    write = AsyncMock(return_value={"ok": True})
    delete = AsyncMock(return_value=None)

    with _membership_patches(
        write,
        snapshot=_membership_snapshot_with_rules(),
        delete_mock=delete,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await _call_set_host_membership(
            hass,
            entry,
            {
                SERVICE_FIELD_HOST_MAC: "0C:85:E1:B0:1D:1C",
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_REFRESH: False,
            },
        )

    # Every rule scoped to this device goes, including the enabled user rule.
    # Rule 577 belongs to another device and must never be touched.
    deleted = [call.args[0] for call in delete.await_args_list]
    assert deleted == ["575", "576", "578", "579"]
    assert response["device_rules"] == {
        "removed": ["575", "576", "578", "579"],
    }
    assert response["membership"]["after"] == {
        "kind": "group",
        "id": "12",
        "name": "Quarantine",
    }


async def test_set_host_membership_removes_nothing_when_the_device_has_no_rules(
    hass: HomeAssistant,
) -> None:
    """A device carrying no rules of its own reports an empty removal list."""
    entry = _membership_entry()
    entry.add_to_hass(hass)
    write = AsyncMock(return_value={"ok": True})
    delete = AsyncMock(return_value=None)

    with _membership_patches(write, delete_mock=delete):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await _call_set_host_membership(
            hass,
            entry,
            {
                SERVICE_FIELD_HOST_MAC: "0C:85:E1:B0:1D:1C",
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_REFRESH: False,
            },
        )

    assert delete.await_count == 0
    assert response["device_rules"] == {"removed": []}


def test_set_host_membership_is_registered_as_an_admin_action() -> None:
    """The membership service is admin-gated and returns a response.

    The gate itself is exercised by the generic admin-service tests; this pins the
    registration so a future edit cannot quietly drop either property.
    """
    from custom_components.firewalla_local.services import _SERVICE_REGISTRATIONS

    registrations = {
        name: (response, admin)
        for name, _handler, _schema, response, admin in _SERVICE_REGISTRATIONS
    }

    assert registrations[SERVICE_SET_HOST_MEMBERSHIP] == (
        SupportsResponse.ONLY,
        True,
    )


async def test_set_host_dhcp_reservation_returns_acknowledgement_for_static_mode(
    hass: HomeAssistant,
) -> None:
    """Test the DHCP reservation service returns an acknowledgement."""
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
    runtime_payload = _network_segment_report_runtime_payload()
    cast(list[dict[str, object]], runtime_payload["hosts"])[0]["policy"] = {
        "ipAllocation": {
            "allocations": {
                "5799d896-5e0f-40a5-a776-38a5d7746204": {
                    "ipv4": "192.168.10.10",
                    "type": "static",
                },
                "d7e5a5c4-0b28-4010-b3c6-dad1a868693f": {
                    "ipv4": "192.168.200.25",
                    "type": "static",
                },
            }
        }
    }

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=runtime_payload),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_policy",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_set_host_policy,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_DHCP_RESERVATION,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_MODE: "static",
                SERVICE_FIELD_RESERVED_IPV4: "192.168.200.250",
                SERVICE_FIELD_HOST_MAC: "00:aa:bb:cc:dd:26",
                SERVICE_FIELD_NETWORK_UUID: "d7e5a5c4-0b28-4010-b3c6-dad1a868693f",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_set_host_policy.await_args is not None
    assert mock_set_host_policy.await_args.args == (
        "00:AA:BB:CC:DD:26",
        {
            "ipAllocation": {
                "allocations": {
                    "5799d896-5e0f-40a5-a776-38a5d7746204": {
                        "ipv4": "192.168.10.10",
                        "type": "static",
                    },
                    "d7e5a5c4-0b28-4010-b3c6-dad1a868693f": {
                        "ipv4": "192.168.200.250",
                        "type": "static",
                    },
                }
            }
        },
    )
    assert response is not None
    assert response == {
        "config_entry_id": entry.entry_id,
        "refreshed": False,
        "target": {
            "kind": "host",
            "id": "00:AA:BB:CC:DD:26",
            "name": "Plex Server",
            "network_kind": None,
        },
        "network": {
            "uuid": "d7e5a5c4-0b28-4010-b3c6-dad1a868693f",
            "name": "Primary LAN",
        },
        "query": {
            "mode": "static",
            "reserved_ipv4": "192.168.200.250",
            "host_id": None,
            "host_mac": "00:aa:bb:cc:dd:26",
            "host_name": None,
            "network_uuid": "d7e5a5c4-0b28-4010-b3c6-dad1a868693f",
            "network_name": None,
            "refresh": False,
        },
        "ip_assignment": {
            "mode": "static",
            "network_uuid": "d7e5a5c4-0b28-4010-b3c6-dad1a868693f",
            "reserved_ipv4": "192.168.200.250",
        },
        "command": {
            "item": "policy",
            "target": "00:AA:BB:CC:DD:26",
            "value": {
                "ipAllocation": {
                    "allocations": {
                        "5799d896-5e0f-40a5-a776-38a5d7746204": {
                            "ipv4": "192.168.10.10",
                            "type": "static",
                        },
                        "d7e5a5c4-0b28-4010-b3c6-dad1a868693f": {
                            "ipv4": "192.168.200.250",
                            "type": "static",
                        },
                    }
                }
            },
        },
        "command_response": {"ok": True},
    }


async def test_set_host_dhcp_reservation_resolves_names_for_dynamic_mode(
    hass: HomeAssistant,
) -> None:
    """Test the DHCP reservation service resolves host and network by name."""
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
    runtime_payload = _network_segment_report_runtime_payload()
    cast(list[dict[str, object]], runtime_payload["hosts"])[0]["policy"] = {
        "ipAllocation": {
            "allocations": {
                "5799d896-5e0f-40a5-a776-38a5d7746204": {
                    "ipv4": "192.168.10.10",
                    "type": "static",
                },
                "d7e5a5c4-0b28-4010-b3c6-dad1a868693f": {
                    "ipv4": "192.168.200.25",
                    "type": "static",
                },
            }
        }
    }

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=runtime_payload),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_policy",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_set_host_policy,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_DHCP_RESERVATION,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_MODE: "dynamic",
                SERVICE_FIELD_HOST_NAME: "Plex Server",
                SERVICE_FIELD_NETWORK_NAME: "Primary LAN",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_set_host_policy.await_args is not None
    assert mock_set_host_policy.await_args.args == (
        "00:AA:BB:CC:DD:26",
        {
            "ipAllocation": {
                "allocations": {
                    "5799d896-5e0f-40a5-a776-38a5d7746204": {
                        "ipv4": "192.168.10.10",
                        "type": "static",
                    },
                    "d7e5a5c4-0b28-4010-b3c6-dad1a868693f": {
                        "type": "dynamic",
                    },
                }
            }
        },
    )
    assert response is not None
    assert response["network"] == {
        "uuid": "d7e5a5c4-0b28-4010-b3c6-dad1a868693f",
        "name": "Primary LAN",
    }
    assert response["ip_assignment"] == {
        "mode": "dynamic",
        "network_uuid": "d7e5a5c4-0b28-4010-b3c6-dad1a868693f",
        "reserved_ipv4": None,
    }


async def test_set_host_dhcp_reservation_requires_ipv4_for_static_mode(
    hass: HomeAssistant,
) -> None:
    """Test static DHCP reservations require one IPv4 address."""
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match="Provide reserved IPv4 when the reservation mode is static",
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_DHCP_RESERVATION,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_MODE: "static",
                SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )


async def test_set_host_dhcp_reservation_infers_network_from_ipv4(
    hass: HomeAssistant,
) -> None:
    """Test static reservations can infer the target network by subnet."""
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.managers.integration_manager.FirewallaIntegrationManager.async_set_host_policy",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_set_host_policy,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_DHCP_RESERVATION,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_MODE: "static",
                SERVICE_FIELD_RESERVED_IPV4: "192.168.200.250",
                SERVICE_FIELD_HOST_NAME: "Plex Server",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_set_host_policy.await_args is not None
    assert mock_set_host_policy.await_args.args == (
        "00:AA:BB:CC:DD:26",
        {
            "ipAllocation": {
                "allocations": {
                    "5799d896-5e0f-40a5-a776-38a5d7746204": {
                        "ipv4": "192.168.10.10",
                        "type": "static",
                    },
                    "d7e5a5c4-0b28-4010-b3c6-dad1a868693f": {
                        "ipv4": "192.168.200.250",
                        "type": "static",
                    },
                }
            }
        },
    )
    assert response is not None
    assert response["network"] == {
        "uuid": "d7e5a5c4-0b28-4010-b3c6-dad1a868693f",
        "name": "Primary LAN",
    }


async def test_set_host_dhcp_reservation_rejects_ipv4_outside_network_range(
    hass: HomeAssistant,
) -> None:
    """Test static reservations reject IPv4 values outside the network subnet."""
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match="outside the IPv4 subnet",
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_DHCP_RESERVATION,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_MODE: "static",
                SERVICE_FIELD_RESERVED_IPV4: "192.168.200.150",
                SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )


async def test_set_host_dhcp_reservation_rejects_duplicate_ipv4_on_same_network(
    hass: HomeAssistant,
) -> None:
    """Test static reservations reject duplicate IPv4 ownership on one network."""
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
    runtime_payload = _network_segment_report_runtime_payload()
    cast(list[dict[str, object]], runtime_payload["hosts"])[1]["policy"] = {
        "ipAllocation": {
            "allocations": {
                "d7e5a5c4-0b28-4010-b3c6-dad1a868693f": {
                    "ipv4": "192.168.200.150",
                    "type": "static",
                }
            }
        }
    }

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=runtime_payload),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_wake_host_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match="already assigned to",
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOST_DHCP_RESERVATION,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_MODE: "static",
                SERVICE_FIELD_RESERVED_IPV4: "192.168.200.150",
                SERVICE_FIELD_HOST_MAC: "00:AA:BB:CC:DD:26",
                SERVICE_FIELD_NETWORK_UUID: "d7e5a5c4-0b28-4010-b3c6-dad1a868693f",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )


async def test_get_time_usage_report_service_resolves_device_label_and_serializes_data(
    hass: HomeAssistant,
) -> None:
    """Test the time usage report service resolves one device label."""
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
    begin = datetime(2026, 3, 20, 21, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    end = datetime(2026, 3, 27, 21, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_usage_history_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_usage_history_payload",
            new=AsyncMock(return_value=_usage_history_payload()),
        ) as mock_get_usage_history,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_TIME_USAGE_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_NAME: "Kaden Phone (192.168.200.25)",
                SERVICE_FIELD_USAGE_HISTORY_BEGIN: begin,
                SERVICE_FIELD_USAGE_HISTORY_END: end,
                SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: "day",
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_usage_history.await_args is not None
    assert mock_get_usage_history.await_args.kwargs == {
        "scope_type": "host",
        "target": "EC:0D:51:CC:BA:BC",
        "begin_timestamp": 1_774_065_600,
        "end_timestamp": 1_774_670_400,
        "granularity": "day",
        "app_ids": None,
    }
    assert response is not None
    assert response["target"] == {
        "kind": "host",
        "id": "EC:0D:51:CC:BA:BC",
        "name": "Kaden Phone",
        "network_kind": None,
    }
    assert response["query"] == {
        "detail": "standard",
        "sections": [],
        "include": [],
        "time_zone": "America/New_York",
        "begin_timestamp": 1_774_065_600,
        "begin": "2026-03-21T00:00:00-04:00",
        "end_timestamp": 1_774_670_400,
        "end": "2026-03-28T00:00:00-04:00",
        "granularity": "day",
        "app_ids": None,
    }
    assert response["time_basis"] == {
        "kind": "custom_range",
        "label": "Requested day usage range",
        "begin_timestamp": 1_774_065_600,
        "end_timestamp": 1_774_670_400,
        "anchor_timestamp": 1_774_670_400,
        "is_partial": False,
        "boundary_source": "query_window",
        "time_zone": "America/New_York",
        "begin_timestamp_iso": "2026-03-21T00:00:00-04:00",
        "end_timestamp_iso": "2026-03-28T00:00:00-04:00",
        "anchor_timestamp_iso": "2026-03-28T00:00:00-04:00",
    }
    assert response["summary"] == {
        "total_minutes": 596,
        "unique_minutes": 580,
        "app_total_minutes": 121,
        "app_count": 1,
        "category_count": 1,
        "period_count": 2,
    }
    assert response["metadata"]["applied"] == {
        "detail": "standard",
        "sections": ["internet", "app_totals", "apps", "categories"],
        "include": [],
        "request_scope_type": "host",
    }
    assert response["metadata"]["provenance"]["apps"] == {
        "source": "direct",
        "source_field": "appTimeUsage",
        "note": "Per-app usage sections are ranked by returned usage totals",
    }
    assert response["metadata"]["provenance"]["categories"] == {
        "source": "direct",
        "source_field": "categoryTimeUsage",
        "note": "Per-category usage sections are ranked by returned usage totals",
    }
    assert "apps.devices.intervals" not in response["metadata"]["provenance"]
    assert response["query"]["app_ids"] is None
    assert response["sections"]["internet"]["summary"] == {
        "total_minutes": 596,
        "unique_minutes": 580,
    }
    assert response["sections"]["internet"]["periods"][0] == {
        "time_period": {
            "kind": "day",
            "label": "2026-03-21",
            "start_timestamp": 1_774_065_600,
            "start": "2026-03-21T00:00:00-04:00",
            "end_timestamp": 1_774_152_000,
            "end": "2026-03-22T00:00:00-04:00",
            "is_partial": False,
            "boundary_source": "firewalla_slot",
        },
        "usage": {
            "total_minutes": 120,
            "unique_minutes": 118,
        },
    }
    assert response["sections"]["apps"][0]["key"] == "facebook"
    assert response["sections"]["apps"][0]["summary"] == {
        "total_minutes": 121,
        "unique_minutes": 120,
    }
    assert response["sections"]["apps"][0]["devices"][0] == {
        "device_id": "EC:0D:51:CC:BA:BC",
        "device_name": "Kaden Phone",
        "summary": {
            "total_minutes": 15,
            "unique_minutes": 15,
        },
    }


async def test_get_time_usage_report_service_detail_intervals_keeps_intervals(
    hass: HomeAssistant,
) -> None:
    """Test include=intervals preserves per-device interval detail."""
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
            return_value=_usage_history_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_usage_history_payload",
            new=AsyncMock(return_value=_usage_history_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_TIME_USAGE_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_NAME: "Kaden Phone (192.168.200.25)",
                SERVICE_FIELD_USAGE_HISTORY_BEGIN: datetime.fromtimestamp(
                    1_774_065_600,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_END: datetime.fromtimestamp(
                    1_774_670_400,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: "hour",
                SERVICE_FIELD_INCLUDE: ["intervals"],
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["query"]["detail"] == "standard"
    assert response["query"]["sections"] == []
    assert response["query"]["include"] == ["intervals"]
    assert response["metadata"]["applied"] == {
        "detail": "standard",
        "sections": ["internet", "app_totals", "apps", "categories"],
        "include": ["intervals"],
        "request_scope_type": "host",
    }
    assert response["metadata"]["provenance"]["apps.devices.intervals"] == {
        "source": "direct",
        "source_field": "appTimeUsage.*.devices.*.intervals",
        "note": (
            "Interval detail appears only when requested and when Firewalla "
            "returns device intervals"
        ),
    }
    assert response["sections"]["apps"][0]["devices"][0]["intervals"] == [
        {
            "time_period": {
                "kind": "interval",
                "start_timestamp": 1_774_065_660,
                "start": "2026-03-21T00:01:00-04:00",
                "end_timestamp": 1_774_065_900,
                "end": "2026-03-21T00:05:00-04:00",
            },
            "duration_seconds": 240,
            "duration_minutes": 5,
        }
    ]


async def test_get_time_usage_report_service_resolves_user_name_to_tag_scope(
    hass: HomeAssistant,
) -> None:
    """Test the time usage report service resolves user names through tag scope."""
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
            return_value=_usage_history_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_usage_history_payload",
            new=AsyncMock(return_value=_usage_history_payload()),
        ) as mock_get_usage_history,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_TIME_USAGE_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_USER_NAME: "KADEN",
                SERVICE_FIELD_USAGE_HISTORY_BEGIN: datetime.fromtimestamp(
                    1_774_065_600,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_END: datetime.fromtimestamp(
                    1_774_670_400,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: "day",
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_usage_history.await_args is not None
    assert mock_get_usage_history.await_args.kwargs["scope_type"] == "tag"
    assert mock_get_usage_history.await_args.kwargs["target"] == "21"
    assert response is not None
    assert response["target"]["id"] == "21"
    assert response["target"]["name"] == "KADEN"


@pytest.mark.parametrize(
    "scope_target",
    [
        pytest.param("KADEN", id="user_name"),
        pytest.param("10", id="user_backing_tag_id"),
    ],
)
async def test_get_time_usage_report_group_scope_rejects_a_user_entry(
    hass: HomeAssistant,
    scope_target: str,
) -> None:
    """A group-scoped request must not resolve to a user's backing tag.

    The tag collection holds plain groups and user affiliations together, and a
    user entry carries the user's own name. Without a kind filter, a
    group-scoped request for that name -- or for the user's backing tag id --
    resolved to the user's tag and returned that user's usage labelled as a
    group. Users resolve through the user scope instead.
    """
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
            return_value=_usage_history_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_usage_history_payload",
            new=AsyncMock(return_value=_usage_history_payload()),
        ) as mock_get_usage_history,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GET_TIME_USAGE_REPORT,
                {
                    SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                    SERVICE_FIELD_GROUP_NAME: scope_target,
                    SERVICE_FIELD_USAGE_HISTORY_BEGIN: datetime.fromtimestamp(
                        1_774_065_600,
                        UTC,
                    ),
                    SERVICE_FIELD_USAGE_HISTORY_END: datetime.fromtimestamp(
                        1_774_670_400,
                        UTC,
                    ),
                    SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: "day",
                },
                blocking=True,
                return_response=True,
            )

    assert (
        err.value.translation_key
        == TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_NOT_FOUND
    )
    assert mock_get_usage_history.await_count == 0


@pytest.mark.parametrize(
    ("data", "expected_key"),
    [
        pytest.param(
            {
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_USER_NAME: "KADEN",
            },
            "selector_conflict",
            id="two-selectors",
        ),
        pytest.param({}, "selector_required", id="no-selector"),
    ],
)
@pytest.mark.asyncio
async def test_get_time_usage_report_accepts_exactly_one_scope_selector(
    hass: HomeAssistant,
    data: dict[str, object],
    expected_key: str,
) -> None:
    """Test the usage report enforces the same exactly-one scope rule.

    One rule, one message, whichever report a caller meets it on. The entry is
    fully set up so the failure is provably the selector rule and not a missing
    fixture.
    """
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
            return_value=_usage_history_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_usage_history_payload",
            new=AsyncMock(return_value=_usage_history_payload()),
        ) as mock_get_usage_history,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GET_TIME_USAGE_REPORT,
                {
                    SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                    SERVICE_FIELD_USAGE_HISTORY_BEGIN: datetime.fromtimestamp(
                        1_774_065_600,
                        UTC,
                    ),
                    SERVICE_FIELD_USAGE_HISTORY_END: datetime.fromtimestamp(
                        1_774_670_400,
                        UTC,
                    ),
                    SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: "day",
                    **data,
                },
                blocking=True,
                return_response=True,
            )

    assert err.value.translation_key == expected_key
    assert mock_get_usage_history.await_count == 0


async def test_get_time_usage_report_service_preserves_explicit_empty_app_list(
    hass: HomeAssistant,
) -> None:
    """Test the time usage report service preserves explicit empty app filters."""
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
            return_value=_usage_history_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_usage_history_payload",
            new=AsyncMock(return_value=_usage_history_payload()),
        ) as mock_get_usage_history,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_TIME_USAGE_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_USAGE_HISTORY_BEGIN: datetime.fromtimestamp(
                    1_774_065_600,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_END: datetime.fromtimestamp(
                    1_774_670_400,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: "day",
                SERVICE_FIELD_USAGE_HISTORY_APP_IDS: [],
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_usage_history.await_args is not None
    assert mock_get_usage_history.await_args.kwargs["scope_type"] == "tag"
    assert mock_get_usage_history.await_args.kwargs["target"] == "12"
    assert mock_get_usage_history.await_args.kwargs["app_ids"] == ()
    assert response is not None
    assert response["query"]["app_ids"] == []


async def test_get_time_usage_report_service_honors_requested_sections(
    hass: HomeAssistant,
) -> None:
    """Test the time usage report includes only explicitly requested sections."""
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
            return_value=_usage_history_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_usage_history_payload",
            new=AsyncMock(return_value=_usage_history_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_TIME_USAGE_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_MAC: "EC:0D:51:CC:BA:BC",
                SERVICE_FIELD_USAGE_HISTORY_BEGIN: datetime.fromtimestamp(
                    1_774_065_600,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_END: datetime.fromtimestamp(
                    1_774_670_400,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: "day",
                SERVICE_FIELD_DETAIL: "summary",
                SERVICE_FIELD_SECTIONS: ["apps"],
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["query"]["sections"] == ["apps"]
    assert response["metadata"]["applied"] == {
        "detail": "summary",
        "sections": ["apps"],
        "include": [],
        "request_scope_type": "host",
    }
    assert set(response["sections"]) == {"apps"}
    assert response["sections"]["apps"][0]["key"] == "facebook"
    assert response["metadata"]["unavailable_sections"] == []


async def test_get_time_usage_report_service_non_empty_app_filter_adds_apps_section(
    hass: HomeAssistant,
) -> None:
    """Test a non-empty app filter still returns app usage in summary mode."""
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
            return_value=_usage_history_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_usage_history_payload",
            new=AsyncMock(return_value=_usage_history_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_TIME_USAGE_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_MAC: "EC:0D:51:CC:BA:BC",
                SERVICE_FIELD_USAGE_HISTORY_BEGIN: datetime.fromtimestamp(
                    1_774_065_600,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_END: datetime.fromtimestamp(
                    1_774_670_400,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: "day",
                SERVICE_FIELD_DETAIL: "summary",
                SERVICE_FIELD_USAGE_HISTORY_APP_IDS: ["facebook"],
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["metadata"]["applied"]["sections"] == [
        "internet",
        "app_totals",
        "apps",
    ]
    assert set(response["sections"]) == {"internet", "app_totals", "apps"}
    assert response["sections"]["apps"][0]["key"] == "facebook"


async def test_get_time_usage_report_service_ranks_apps_and_filters_zero_only_rows(
    hass: HomeAssistant,
) -> None:
    """Test the time usage report surfaces meaningful app usage first."""
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
            return_value=_usage_history_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_usage_history_payload",
            new=AsyncMock(return_value=_usage_history_payload_with_sparse_apps()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_TIME_USAGE_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_HOST_MAC: "EC:0D:51:CC:BA:BC",
                SERVICE_FIELD_USAGE_HISTORY_BEGIN: datetime.fromtimestamp(
                    1_774_065_600,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_END: datetime.fromtimestamp(
                    1_774_670_400,
                    UTC,
                ),
                SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: "day",
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["summary"]["app_count"] == 2
    assert response["summary"]["category_count"] == 2
    assert [item["key"] for item in response["sections"]["apps"]] == [
        "facebook",
        "slack",
    ]
    assert [item["key"] for item in response["sections"]["categories"]] == [
        "social",
        "productivity",
    ]


async def test_get_wan_data_usage_service_returns_current_month_summary_when_requested(
    hass: HomeAssistant,
) -> None:
    """Test the WAN data usage service returns the requested current month."""
    await hass.config.async_set_time_zone("America/Los_Angeles")

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
            side_effect=(
                _speed_test_snapshot(timezone_name="America/New_York"),
                _speed_test_snapshot(timezone_name="America/New_York"),
            ),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_monthly_wan_usage_payload",
            new=AsyncMock(return_value=_runtime_payload()["monthlyDataUsageOnWans"]),
        ) as mock_get_monthly,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_DATA_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_CURRENT_PERIODS: ["month"],
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_monthly.await_count == 1
    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["refreshed"] is True
    assert response["target"] == {
        "kind": "network",
        "id": None,
        "name": None,
        "network_kind": "wan",
    }
    assert response["query"] == {
        "detail": "summary",
        "include": [],
        "time_zone": "America/New_York",
        "refresh": True,
        "current_periods": ["month"],
        "history_period": None,
        "history_count": 0,
    }
    assert response["summary"] == {
        "wan_count": 2,
        "current_periods": ["month"],
        "history_period": None,
        "history_count": 0,
        "includes_history": False,
        "includes_subperiods": False,
    }
    assert response["metadata"] == {
        "applied": {
            "detail": "summary",
            "include": [],
        },
        "warnings": [],
        "unavailable_sections": [],
        "provenance": {
            "reports": {
                "source": "direct",
                "source_field": "monthlyDataUsageOnWans",
                "note": "Current and history rows come from direct WAN usage payloads",
            },
        },
    }
    assert response["time_basis"]["kind"] == "period_bundle"
    assert response["time_basis"]["time_zone"] == "America/New_York"
    first_report = response["sections"]["reports"][0]
    assert first_report["target"] == {
        "kind": "network",
        "id": "wan-1",
        "name": "WAN-ONE",
        "network_kind": "wan",
    }
    assert first_report["current"]["month"]["usage"] == {
        "download_bytes": 3072,
        "upload_bytes": 1280,
        "total_bytes": 4352,
    }
    assert first_report["current"]["month"]["detail"] == "summary"
    assert first_report["current"]["month"]["days"] == []
    assert first_report["history"]["months"] == []


async def test_get_wan_data_usage_service_adds_daily_detail_to_current_month(
    hass: HomeAssistant,
) -> None:
    """Test daily detail is nested under current month when requested."""
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
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_monthly_wan_usage_payload",
            new=AsyncMock(return_value=_runtime_payload()["monthlyDataUsageOnWans"]),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_DATA_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_CURRENT_PERIODS: ["month"],
                SERVICE_FIELD_DETAIL: "full",
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    first_report = response["sections"]["reports"][0]
    assert response["metadata"]["applied"] == {
        "detail": "full",
        "include": ["subperiods"],
    }
    assert response["metadata"]["provenance"]["reports.current.subperiods"] == {
        "source": "derived",
        "source_field": "monthlyDataUsageOnWans",
        "note": (
            "Nested week and day breakdowns are derived from current WAN usage samples"
        ),
    }
    assert first_report["current"]["month"]["detail"] == "daily"
    assert first_report["current"]["month"]["days"][0]["usage"] == {
        "download_bytes": 2048,
        "upload_bytes": 768,
        "total_bytes": 2816,
    }
    assert first_report["current"]["month"]["days"][0]["time_period"]["kind"] == "day"


async def test_get_wan_data_usage_service_defaults_to_day_and_week(
    hass: HomeAssistant,
) -> None:
    """Test the WAN data usage service defaults to the day and week periods.

    The month-only default answered the least common form of the question and
    omitted the day and week totals callers usually want.
    """
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
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_monthly_wan_usage_payload",
            new=AsyncMock(return_value=_runtime_payload()["monthlyDataUsageOnWans"]),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_DATA_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["query"]["current_periods"] == ["day", "week"]
    assert response["summary"]["current_periods"] == ["day", "week"]
    assert response["summary"]["includes_history"] is False


async def test_get_wan_data_usage_service_returns_history_months_only(
    hass: HomeAssistant,
) -> None:
    """Test historical monthly usage can be returned without current periods."""
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
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_last12_monthly_wan_usage_payload",
            new=AsyncMock(return_value=_wan_usage_history_payload()),
        ) as mock_get_history,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_DATA_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_CURRENT_PERIODS: [],
                SERVICE_FIELD_HISTORY_PERIOD: "month",
                SERVICE_FIELD_HISTORY_COUNT: 1,
                SERVICE_FIELD_WAN_UUID: "wan-1",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_history.await_count == 1
    assert response is not None
    assert response["target"] == {
        "kind": "network",
        "id": "wan-1",
        "name": "WAN-ONE",
        "network_kind": "wan",
    }
    assert response["refreshed"] is False
    assert response["query"] == {
        "detail": "summary",
        "include": [],
        "time_zone": "America/New_York",
        "refresh": False,
        "current_periods": [],
        "history_period": "month",
        "history_count": 1,
    }
    assert response["summary"]["includes_history"] is True
    first_report = response["sections"]["reports"][0]
    assert first_report["current"]["month"] is None
    assert len(first_report["history"]["months"]) == 1
    assert first_report["history"]["months"][0]["usage"] == {
        "download_bytes": 10800,
        "upload_bytes": 5400,
        "total_bytes": 16200,
    }
    assert first_report["history"]["months"][0]["detail"] == "summary"


async def test_get_wan_data_usage_service_reports_unavailable_history_include(
    hass: HomeAssistant,
) -> None:
    """Test include=history warns when no history rows were requested."""
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
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_monthly_wan_usage_payload",
            new=AsyncMock(return_value=_runtime_payload()["monthlyDataUsageOnWans"]),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_DATA_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_INCLUDE: ["history"],
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["metadata"]["unavailable_sections"] == ["history"]
    assert response["metadata"]["warnings"] == [
        {
            "code": "history_not_available",
            "message": "History was requested but history_count is 0",
        }
    ]


async def test_get_network_segment_report_service_returns_configuration_report(
    hass: HomeAssistant,
) -> None:
    """Test the network segment report returns DHCP and host detail data."""
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_speed_test_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=_network_interface_payload()),
        ) as mock_get_network_interface,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_INCLUDE: ["hosts"],
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_network_interface.await_args is not None
    assert mock_get_network_interface.await_args.kwargs == {
        "network_uuid": "5799d896-5e0f-40a5-a776-38a5d7746204"
    }
    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["refreshed"] is False
    assert response["target"] == {
        "kind": "network",
        "id": "5799d896-5e0f-40a5-a776-38a5d7746204",
        "name": "VLAN10 CORE",
        "network_kind": "lan",
    }
    assert response["query"] == {"refresh": False}
    assert response["time_basis"] == {
        "kind": "snapshot",
        "label": "Current network segment configuration snapshot",
        "begin_timestamp": None,
        "end_timestamp": None,
        "anchor_timestamp": None,
        "is_partial": None,
        "boundary_source": "runtime_snapshot",
        "time_zone": None,
    }
    assert response["summary"] == {
        "host_count": 2,
        "returned_host_count": 2,
        "device_host_count": 2,
        "has_dhcp_config": True,
        "has_ipv4_addressing": True,
        "has_ipv6_addressing": False,
    }
    assert response["sections"]["configuration"] == {
        "kind": "lan",
        "interface_name": "bond0.10",
        "vlan_id": None,
        "ports": [],
        "enabled": None,
        "mdns_relay": None,
        "ssdp_relay": False,
        "block_icmp": None,
        "type": "lan",
        "monitoring": True,
        "active": None,
        "ready": None,
        "pending_test": None,
        "policy": {"state": True},
    }
    assert response["sections"]["usage"] == {
        "last_24h": {"download_bytes": None, "upload_bytes": None},
        "last_60m": {"download_bytes": None, "upload_bytes": None},
        "last_30d": {"download_bytes": None, "upload_bytes": None},
        "last_12m": {"download_bytes": None, "upload_bytes": None},
        "monthly": {"download_bytes": None, "upload_bytes": None},
    }
    assert response["sections"]["dhcp"] == {
        "gateway": "192.168.10.1",
        "subnet_mask": "255.255.255.0",
        "lease_seconds": 86400,
        "range": {
            "start": "192.168.10.110",
            "end": "192.168.10.126",
        },
        "name_servers": ["192.168.10.1"],
        "search_domains": ["int.ccpk.us"],
        "extra_options": None,
    }
    assert response["sections"]["hosts"]["count"] == 2
    assert response["sections"]["hosts"]["items"][0] == {
        "host_id": "00:AA:BB:CC:DD:26",
        "host_name": "Plex Server",
        "ip_address": "192.168.10.10",
        "dhcp_name": "plex-server",
        "device_type": "tablet",
        "ip_assignment": {
            "mode": "static",
            "network_uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
            "reserved_ipv4": "192.168.10.10",
        },
        "notifications": {
            "notify_when_next_online": True,
            "notify_when_next_offline": False,
        },
        "actions": {"wake_on_lan_supported": True},
    }
    assert response["sections"]["hosts"]["items"][1] == {
        "host_id": "0C:85:E1:B0:1D:1C",
        "host_name": "Office Phone",
        "ip_address": "192.168.10.44",
        "dhcp_name": "office-phone",
        "device_type": "phone",
        "ip_assignment": {
            "mode": "dynamic",
            "network_uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
            "reserved_ipv4": None,
        },
        "notifications": {
            "notify_when_next_online": False,
            "notify_when_next_offline": False,
        },
        "actions": {"wake_on_lan_supported": True},
    }
    assert response["metadata"] == {
        "applied": {"refresh": False, "include": ["hosts"]},
        "warnings": [],
        "unavailable_sections": [],
        "provenance": {
            "configuration": {
                "source": "direct",
                "source_field": "networkInterface",
                "note": "Interface state comes from the direct network view",
            },
            "addressing": {
                "source": "direct",
                "source_field": "networkInterface",
                "note": "Addressing fields come from the direct network view",
            },
            "dns": {
                "source": "direct",
                "source_field": "networkInterface",
                "note": "DNS fields come from the direct network view",
            },
            "dhcp": {
                "source": "derived",
                "source_field": "logic.dhcpRange",
                "note": (
                    "DHCP settings are derived from the runtime snapshot for "
                    "the matching interface"
                ),
            },
            "hosts": {
                "source": "derived",
                "source_field": "hostManager",
                "note": "Host rows are derived from runtime host inventory",
            },
            "usage": {
                "source": "manager",
                "source_field": "item=intf",
                "note": (
                    "Windowed usage comes from the cached per-network "
                    "usage summary; WAN windowed usage is not available"
                ),
            },
        },
    }


async def test_get_network_segment_report_service_omits_hosts_by_default(
    hass: HomeAssistant,
) -> None:
    """Test host rows are omitted unless explicitly included.

    Host rows carry MAC, hostname, IP and reservation, so they must not be part
    of the default configuration report. The section must be absent rather than
    present-and-empty so its absence is unambiguous.
    """
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_speed_test_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=_network_interface_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert "hosts" not in response["sections"]
    assert set(response["sections"]) == {
        "configuration",
        "usage",
        "addressing",
        "dns",
        "dhcp",
    }
    # The device count is reported whether or not the rows are asked for; only
    # `returned_host_count` tracks the optional row set.
    assert response["summary"]["host_count"] == 2
    assert response["summary"]["returned_host_count"] is None
    assert response["metadata"]["applied"] == {"refresh": False, "include": []}
    assert "hosts" not in response["metadata"]["provenance"]


async def test_get_network_segment_report_service_requires_network_selector(
    hass: HomeAssistant,
) -> None:
    """Test the network segment report requires one network selector."""
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_speed_test_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match="Provide a network UUID or network name",
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )


async def test_get_network_segment_usage_service_returns_summary_report(
    hass: HomeAssistant,
) -> None:
    """Test the network segment usage service returns one selected window."""
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
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=_network_interface_payload()),
        ) as mock_get_network_interface,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_WINDOW: "last_24_hours",
                SERVICE_FIELD_TOP_N: 1,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_network_interface.await_args is not None
    assert mock_get_network_interface.await_args.kwargs == {
        "network_uuid": "5799d896-5e0f-40a5-a776-38a5d7746204"
    }
    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["refreshed"] is False
    assert response["target"] == {
        "kind": "network",
        "id": "5799d896-5e0f-40a5-a776-38a5d7746204",
        "name": "VLAN10 CORE",
        "network_kind": "lan",
    }
    assert response["query"] == {
        "refresh": False,
        "window": "last_24_hours",
        "top_n": 1,
        "include": [],
        "time_zone": "America/New_York",
    }
    assert response["time_basis"] == {
        "kind": "window",
        "label": "Last 24 hours",
        "begin_timestamp": 1_774_558_800,
        "end_timestamp": 1_774_641_600,
        "anchor_timestamp": 1_774_641_600,
        "is_partial": None,
        "boundary_source": "newLast24",
        "time_zone": "America/New_York",
        "begin_timestamp_iso": "2026-03-26T17:00:00-04:00",
        "end_timestamp_iso": "2026-03-27T16:00:00-04:00",
        "anchor_timestamp_iso": "2026-03-27T16:00:00-04:00",
    }
    assert response["summary"] == {
        "host_count": 2,
        "known_host_count": 2,
        "active_device_count": 2,
        "metric_count": 2,
        "sample_count": 4,
        "top_download_count": 1,
        "top_upload_count": 1,
        "app_count": 0,
        "category_count": 0,
        "total_download_bytes": 406504404,
        "total_upload_bytes": 133546109,
        "includes_series": False,
        "flow_families": ["download", "upload"],
    }
    assert response["sections"]["devices"] == {
        "count": 2,
        "items": [
            {
                "host_id": "00:AA:BB:CC:DD:26",
                "host_name": "Plex Server",
                "ip_address": "192.168.10.10",
                "conn": 0,
                "dns": None,
                "dns_blocked": None,
                "ip_blocked": None,
                "ip_denied": None,
                "ntp": None,
                "download_bytes": 406504404,
                "upload_bytes": 0,
            },
            {
                "host_id": "0C:85:E1:B0:1D:1C",
                "host_name": "Office Phone",
                "ip_address": "192.168.10.44",
                "conn": 0,
                "dns": None,
                "dns_blocked": None,
                "ip_blocked": None,
                "ip_denied": None,
                "ntp": None,
                "download_bytes": 0,
                "upload_bytes": 133546109,
            },
        ],
    }
    assert response["sections"]["rankings"] == {
        "top_download_hosts": [
            {
                "host_id": "00:AA:BB:CC:DD:26",
                "host_name": "Plex Server",
                "ip_address": "192.168.10.10",
                "remote_host": "pkg-containers.githubusercontent.com",
                "remote_ip": "185.199.111.154",
                "value": 406504404,
            }
        ],
        "top_upload_hosts": [
            {
                "host_id": "0C:85:E1:B0:1D:1C",
                "host_name": "Office Phone",
                "ip_address": "192.168.10.44",
                "remote_host": "upload.example.net",
                "remote_ip": "203.0.113.50",
                "value": 133546109,
            }
        ],
    }
    assert response["sections"]["activity"] == {
        "source": "newLast24",
        "label": "Last 24 hours",
        "metrics": [
            {
                "metric": "conn",
                "summary": {
                    "sample_count": 2,
                    "total_value": 6346,
                    "max_value": 5696,
                    "latest_timestamp": 1_774_641_600,
                    "latest": "2026-03-27T16:00:00-04:00",
                },
            },
            {
                "metric": "dns",
                "summary": {
                    "sample_count": 2,
                    "total_value": 1975,
                    "max_value": 1855,
                    "latest_timestamp": 1_774_641_600,
                    "latest": "2026-03-27T16:00:00-04:00",
                },
            },
        ],
    }
    assert "series" not in response["sections"]
    assert response["metadata"] == {
        "applied": {
            "window": "last_24_hours",
            "top_n": 1,
            "include": [],
            "time_zone": "America/New_York",
        },
        "warnings": [],
        "unavailable_sections": [],
        "provenance": {
            "devices": {
                "source": "derived",
                "source_field": (
                    "flows.appDetails|flows.recent|flows.download|flows.upload"
                ),
                "note": (
                    "Per-device activity is derived from richer flow families "
                    "when raw host counters are sparse"
                ),
            },
            "rankings": {
                "source": "direct",
                "source_field": "flows",
                "note": (
                    "Top upload and download rankings come from the direct "
                    "flow ranking payload"
                ),
            },
            "activity": {
                "source": "direct",
                "source_field": "newLast24",
                "note": (
                    "Selected activity window metrics come from the direct "
                    "network interface payload"
                ),
            },
        },
    }


async def test_get_network_segment_usage_service_derives_activity_from_flows(
    hass: HomeAssistant,
) -> None:
    """Test usage falls back to richer flow families when raw host counters are zero."""
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
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=_zero_host_activity_network_interface_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_WINDOW: "last_24_hours",
                SERVICE_FIELD_TOP_N: 1,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["summary"] == {
        "host_count": 2,
        "known_host_count": 2,
        "active_device_count": 2,
        "metric_count": 2,
        "sample_count": 4,
        "top_download_count": 1,
        "top_upload_count": 1,
        "app_count": 2,
        "category_count": 1,
        "total_download_bytes": 406504604,
        "total_upload_bytes": 133546149,
        "includes_series": False,
        "flow_families": [
            "appDetails",
            "categoryDetails",
            "download",
            "recent",
            "upload",
        ],
    }
    assert response["sections"]["devices"] == {
        "count": 2,
        "items": [
            {
                "host_id": "00:AA:BB:CC:DD:26",
                "host_name": "Plex Server",
                "ip_address": "192.168.10.10",
                "conn": 4,
                "dns": None,
                "dns_blocked": None,
                "ip_blocked": None,
                "ip_denied": None,
                "ntp": None,
                "download_bytes": 406504404,
                "upload_bytes": 40,
            },
            {
                "host_id": "0C:85:E1:B0:1D:1C",
                "host_name": "Office Phone",
                "ip_address": "192.168.10.44",
                "conn": 2,
                "dns": None,
                "dns_blocked": None,
                "ip_blocked": None,
                "ip_denied": None,
                "ntp": None,
                "download_bytes": 200,
                "upload_bytes": 133546109,
            },
        ],
    }
    assert response["sections"]["apps"] == {
        "count": 1,
        "items": [
            {
                "key": "youtube",
                "download_bytes": 500,
                "upload_bytes": 50,
                "total_bytes": 550,
                "duration_seconds": 180.0,
                "session_count": 2,
                "active_device_count": 2,
                "latest_timestamp": 1_774_641_120,
                "latest": "2026-03-27T15:52:00-04:00",
            }
        ],
    }
    assert response["sections"]["categories"] == {
        "count": 1,
        "items": [
            {
                "key": "av",
                "download_bytes": 600,
                "upload_bytes": 60,
                "total_bytes": 660,
                "duration_seconds": 210.0,
                "session_count": 2,
                "active_device_count": 2,
                "latest_timestamp": 1_774_641_180,
                "latest": "2026-03-27T15:53:00-04:00",
            }
        ],
    }
    assert response["metadata"]["provenance"]["devices"] == {
        "source": "derived",
        "source_field": "flows.appDetails|flows.recent|flows.download|flows.upload",
        "note": (
            "Per-device activity is derived from richer flow families when raw "
            "host counters are sparse"
        ),
    }
    assert response["metadata"]["provenance"]["apps"] == {
        "source": "derived",
        "source_field": "flows.appDetails",
        "note": "Top apps are aggregated from classified flow activity",
    }
    assert response["metadata"]["provenance"]["categories"] == {
        "source": "derived",
        "source_field": "flows.categoryDetails",
        "note": "Top categories are aggregated from classified flow activity",
    }


async def test_get_network_segment_usage_service_returns_series_when_requested(
    hass: HomeAssistant,
) -> None:
    """Test the network segment usage service adds raw samples when requested."""
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
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=_network_interface_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_WINDOW: "last_24_hours",
                SERVICE_FIELD_INCLUDE: ["series"],
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["query"]["include"] == ["series"]
    assert response["summary"]["includes_series"] is True
    assert response["sections"]["activity"]["metrics"][0] == {
        "metric": "conn",
        "summary": {
            "sample_count": 2,
            "total_value": 6346,
            "max_value": 5696,
            "latest_timestamp": 1_774_641_600,
            "latest": "2026-03-27T16:00:00-04:00",
        },
    }
    metric = response["sections"]["series"]["metrics"][0]
    assert metric["metric"] == "conn"
    assert metric["summary"] == {
        "sample_count": 2,
        "total_value": 6346,
        "max_value": 5696,
        "latest_timestamp": 1_774_641_600,
        "latest": "2026-03-27T16:00:00-04:00",
    }
    assert metric["samples"] == [
        {
            "timestamp": 1_774_558_800,
            "timestamp_iso": "2026-03-26T21:00:00+00:00",
            "value": 5696,
        },
        {
            "timestamp": 1_774_641_600,
            "timestamp_iso": "2026-03-27T20:00:00+00:00",
            "value": 650,
        },
    ]
    assert response["metadata"]["provenance"]["series"] == {
        "source": "direct",
        "source_field": "newLast24",
        "note": "Series samples expose the raw points for the selected activity window",
    }


async def test_get_network_segment_usage_service_defaults_window(
    hass: HomeAssistant,
) -> None:
    """Test the network segment usage service works without a window.

    An omitted window previously raised a validation error while the tool
    advertised a default, making a compliant call impossible.
    """
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
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=_network_interface_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["query"]["window"] == "last_60_minutes"


async def test_get_network_segment_usage_service_requires_network_selector(
    hass: HomeAssistant,
) -> None:
    """Test the network segment usage service requires one network selector."""
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
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(
        ServiceValidationError,
        match="Provide a network UUID or network name",
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_WINDOW: "last_24_hours",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )


async def test_get_wan_data_usage_service_returns_history_days_in_local_time(
    hass: HomeAssistant,
) -> None:
    """Test history-day output uses local-time ISO period boundaries."""
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

    await hass.config.async_set_time_zone("America/Los_Angeles")

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_last12_monthly_wan_usage_payload",
            new=AsyncMock(return_value=_wan_usage_history_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_DATA_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_CURRENT_PERIODS: [],
                SERVICE_FIELD_HISTORY_PERIOD: "day",
                SERVICE_FIELD_HISTORY_COUNT: 2,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["query"]["time_zone"] == "America/New_York"
    first_history_day = response["sections"]["reports"][0]["history"]["days"][0]
    assert first_history_day["time_period"]["begin_timestamp_iso"] == (
        "2025-06-08T00:00:00-04:00"
    )
    assert first_history_day["time_period"]["end_timestamp_iso"] == (
        "2025-06-09T00:00:00-04:00"
    )


async def test_get_wan_data_usage_service_returns_current_and_history_weeks(
    hass: HomeAssistant,
) -> None:
    """Test derived week rows use Monday-start local calendar windows."""
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

    await hass.config.async_set_time_zone("America/Los_Angeles")

    current_month_payload = {
        "wan-1": {
            "download": [
                [1_748_750_400, 100],
                [1_748_836_800, 110],
                [1_748_923_200, 120],
                [1_749_009_600, 130],
                [1_749_096_000, 140],
                [1_749_182_400, 150],
                [1_749_268_800, 160],
                [1_749_355_200, 170],
                [1_749_441_600, 180],
                [1_749_528_000, 190],
            ],
            "upload": [
                [1_748_750_400, 10],
                [1_748_836_800, 11],
                [1_748_923_200, 12],
                [1_749_009_600, 13],
                [1_749_096_000, 14],
                [1_749_182_400, 15],
                [1_749_268_800, 16],
                [1_749_355_200, 17],
                [1_749_441_600, 18],
                [1_749_528_000, 19],
            ],
            "totalDownload": 1450,
            "totalUpload": 145,
            "monthlyBeginTs": 1_748_750_400,
            "monthlyEndTs": 1_751_342_400,
        }
    }

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_speed_test_snapshot(timezone_name="America/New_York"),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_monthly_wan_usage_payload",
            new=AsyncMock(return_value=current_month_payload),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_last12_monthly_wan_usage_payload",
            new=AsyncMock(return_value=_wan_usage_history_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_DATA_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_CURRENT_PERIODS: ["week", "day"],
                SERVICE_FIELD_HISTORY_PERIOD: "week",
                SERVICE_FIELD_HISTORY_COUNT: 1,
                SERVICE_FIELD_DETAIL: "full",
                SERVICE_FIELD_WAN_UUID: "wan-1",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["metadata"]["applied"] == {
        "detail": "full",
        "include": ["history", "subperiods"],
    }
    assert response["metadata"]["provenance"]["reports.history"] == {
        "source": "direct",
        "source_field": "last12MonthlyDataUsageOnWans",
        "note": "History rows appear only when history_count is greater than zero",
    }
    current_week = response["sections"]["reports"][0]["current"]["week"]
    assert current_week["time_period"]["begin_timestamp_iso"] == (
        "2025-06-09T00:00:00-04:00"
    )
    assert current_week["time_period"]["end_timestamp_iso"] == (
        "2025-06-16T00:00:00-04:00"
    )
    assert current_week["detail"] == "daily"
    assert len(current_week["days"]) == 2
    current_day = response["sections"]["reports"][0]["current"]["day"]
    assert current_day["time_period"]["begin_timestamp_iso"] == (
        "2025-06-10T00:00:00-04:00"
    )
    assert current_day["time_period"]["is_partial"] is True
    history_week = response["sections"]["reports"][0]["history"]["weeks"][0]
    assert history_week["time_period"]["begin_timestamp_iso"] == (
        "2025-06-02T00:00:00-04:00"
    )
    assert history_week["time_period"]["end_timestamp_iso"] == (
        "2025-06-09T00:00:00-04:00"
    )
    assert len(history_week["days"]) == 7


async def test_get_wan_events_service_returns_normalized_timeline(
    hass: HomeAssistant,
) -> None:
    """Test the WAN events service returns normalized state and action records."""
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
            return_value=_speed_test_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_wan_events_payload",
            new=AsyncMock(side_effect=_wan_events_service_payload),
        ) as mock_get_events,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_EVENTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_WAN_UUID: "wan-1",
                SERVICE_FIELD_LIMIT: 100,
                SERVICE_FIELD_OFFSET: 10,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_events.await_args is not None
    call_kwargs = mock_get_events.await_args.kwargs
    assert call_kwargs["limit_count"] == 100
    assert call_kwargs["limit_offset"] == 10
    # Transcribed from the app's own decoded request. A three-entry link-state
    # set was here before and excluded every quality event -- the latency and
    # packet-loss faults that "why did my internet drop" mostly means -- which is
    # why a real 2026-09-30 ping_RTT event was invisible.
    assert call_kwargs["filters"] == [
        {"event_type": "action", "sub_type": "system_reboot"},
        {"event_type": "state", "sub_type": "dualwan_state"},
        {"event_type": "state", "sub_type": "ethernet_state"},
        {"event_type": "state", "sub_type": "wan_state"},
        {"event_type": "state", "sub_type": "overall_wan_state"},
        {"event_type": "state", "sub_type": "ap_ethernet_state"},
        {"event_type": "state", "sub_type": "ap_ethernet_speed_change"},
        {"event_type": "action", "sub_type": "wpa_connection"},
        {"event_type": "action", "sub_type": "ping_RTT"},
        {"event_type": "action", "sub_type": "ping_lossrate"},
        {"event_type": "action", "sub_type": "dns_RTT"},
        {"event_type": "action", "sub_type": "dns_lossrate"},
        {"event_type": "action", "sub_type": "http_RTT"},
        {"event_type": "action", "sub_type": "http_lossrate"},
    ]
    # The box's own DNS health probe fires every ~3 minutes and stays opt-in; the
    # quality families above are a different thing that merely share the word.
    assert "dns" not in {entry["sub_type"] for entry in call_kwargs["filters"]}
    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["wan"] == {"uuid": "wan-1", "name": "WAN-ONE"}
    assert response["query"] == {
        "limit": 100,
        "offset": 10,
        "window_days": 7,
        "include_dns": False,
    }
    assert response["count"] == 2
    families = {item["family"] for item in response["results"]}
    # Both are WAN events and both are needed. This assertion previously required
    # `ping_RTT` to be *excluded*, on the reasoning that latency lives in
    # get_internet_quality -- which conflated two different things. That service
    # reports latency *samples* (the link's current state); this one reports
    # discrete events, and a threshold breach is an event: it has a time, a
    # measurement, and the limit it crossed. The app treats it as one, and without
    # it "why did my internet drop" cannot be answered at all.
    assert families == {"dualwan_state", "ping_RTT"}
    # The DNS health probe is a different thing that merely shares the word.
    assert "dns" not in families

    threshold_event = next(
        item for item in response["results"] if item["family"] == "ping_RTT"
    )
    # A quality event is only meaningful with its measurement *and* its limit.
    assert threshold_event["measurement_kind"] == "rtt"
    assert threshold_event["measurement_value"] is not None
    assert threshold_event["threshold_value"] is not None
    assert threshold_event["target"] is not None

    link_event = next(
        item for item in response["results"] if item["family"] == "dualwan_state"
    )
    assert link_event["wan_uuid"] == "wan-1"
    # Empty results explain themselves rather than reading as a failure.
    assert response["metadata"]["warnings"] == []
    assert response["time_basis"]["kind"] == "event_window"
    assert response["time_basis"]["boundary_source"] == "query_window"
    assert link_event["changed_interface"] == "eth0"
    assert link_event["wan_statuses"] == [
        {
            "interface_key": "eth0",
            "wan_uuid": "wan-1",
            "wan_name": "WAN-ONE",
            "active": True,
            "ready": True,
            "ip4_addresses": ["23.245.207.179/23"],
            "seq": 0,
        },
        {
            "interface_key": "eth1",
            "wan_uuid": "wan-2",
            "wan_name": "WAN-TWO",
            "active": False,
            "ready": False,
            "ip4_addresses": [],
            "seq": 1,
        },
    ]


async def test_get_wan_events_service_includes_dns_when_requested(
    hass: HomeAssistant,
) -> None:
    """Test DNS health probes are returned only when explicitly requested."""
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
            return_value=_speed_test_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_wan_events_payload",
            new=AsyncMock(side_effect=_wan_events_service_payload),
        ) as mock_get_events,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_EVENTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_INCLUDE_DNS: True,
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_events.await_args is not None
    filters = mock_get_events.await_args.kwargs["filters"]
    assert {"event_type": "state", "sub_type": "dns"} in filters
    assert response is not None
    # The fixture carries dualwan_state, ping_RTT and dns. The default read
    # returns the first two and never the dns probe; opting in adds only the
    # probe, which is why the count grows by exactly one.
    assert response["count"] == 3
    assert any(item["family"] == "dns" for item in response["results"])
    assert {"dualwan_state", "ping_RTT"} <= {
        item["family"] for item in response["results"]
    }


def _wan_events_service_payload(
    *,
    filters: list[dict[str, str]] | None = None,
    **kwargs: object,
) -> list[dict[str, object]]:
    """Return the WAN events fixture filtered the way the box filters it.

    The service relies on the box applying `filters`; the mock must honour them
    too, or the default DNS exclusion cannot be tested.
    """
    del kwargs
    payload = _wan_events_payload()
    if not filters:
        return payload

    allowed = {(item["event_type"], item["sub_type"]) for item in filters}
    return [
        event
        for event in payload
        if (
            event.get("event_type"),
            event.get("state_type") or event.get("action_type"),
        )
        in allowed
    ]


def _wireless_runtime_payload() -> dict[str, object]:
    """Return a raw init payload with an AP7 wireless config."""
    return {
        "timezone": "America/New_York",
        "policyRules": [],
        "networkConfig": {
            "apc": {
                "assets": {
                    "ap-1": {
                        "sysConfig": {
                            "name": "Upstairs",
                            "channel": {"5g": "36", "2g": "11"},
                            "led": "off",
                        },
                        "model": "fwap-D",
                    }
                },
                "assets_template": {
                    "ap_default": {
                        "wifiNetworks": [
                            {
                                "intf": "br0",
                                "ssidProfiles": [
                                    "cca57d09-34dd-41b0-a128-320c8ed7f126"
                                ],
                            },
                            {
                                "intf": "br1",
                                "vlan": 100,
                                "ssidProfiles": [
                                    "f185dc47-2730-48a8-844c-b57aa31af4ba"
                                ],
                            },
                        ]
                    }
                },
                "profile": {
                    "cca57d09-34dd-41b0-a128-320c8ed7f126": {
                        "ssid": "Castle",
                        "band": "2.4g+5g+6g",
                        "encryption": "psk2+ccmp",
                        "wpa3": False,
                    },
                    "f185dc47-2730-48a8-844c-b57aa31af4ba": {
                        "ssid": "Castle Guest",
                        "band": "2.4g+5g+6g",
                        "encryption": "psk2+ccmp",
                        "wpa3": False,
                    },
                },
            }
        },
    }


@pytest.mark.parametrize(
    ("profile_selector", "expected_uuid"),
    [
        pytest.param(
            "f185dc47-2730-48a8-844c-b57aa31af4ba",
            "f185dc47-2730-48a8-844c-b57aa31af4ba",
            id="by_uuid",
        ),
        pytest.param(
            "Castle Guest", "f185dc47-2730-48a8-844c-b57aa31af4ba", id="by_ssid"
        ),
    ],
)
async def test_set_ssid_paused_service_toggles_profile(
    hass: HomeAssistant,
    profile_selector: str,
    expected_uuid: str,
) -> None:
    """Test set_ssid_paused sends the full networkConfig write for a profile."""
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
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_wireless_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_set_ssid_paused",
            new=AsyncMock(return_value={}),
        ) as mock_set_paused,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SSID_PAUSED,
            {
                SERVICE_FIELD_SSID_PROFILE_ID: profile_selector,
                SERVICE_FIELD_ENABLED: False,
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_set_paused.await_args is not None
    assert mock_set_paused.await_count == 1
    network_config_payload = mock_set_paused.await_args.kwargs["network_config_payload"]
    assert "ts" in network_config_payload
    profile = network_config_payload["apc"]["profile"][expected_uuid]
    assert profile["paused"] is True


async def test_set_ssid_paused_service_resumes_profile(
    hass: HomeAssistant,
) -> None:
    """Test set_ssid_paused clears paused when resuming."""
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
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_wireless_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_set_ssid_paused",
            new=AsyncMock(return_value={}),
        ) as mock_set_paused,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SSID_PAUSED,
            {
                SERVICE_FIELD_SSID_PROFILE_ID: "f185dc47-2730-48a8-844c-b57aa31af4ba",
                SERVICE_FIELD_ENABLED: True,
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_set_paused.await_args is not None
    network_config_payload = mock_set_paused.await_args.kwargs["network_config_payload"]
    assert (
        network_config_payload["apc"]["profile"][
            "f185dc47-2730-48a8-844c-b57aa31af4ba"
        ].get("paused")
        is None
    )


async def test_set_ssid_paused_service_rejects_unknown_profile(
    hass: HomeAssistant,
) -> None:
    """Test set_ssid_paused raises for an unknown SSID profile."""
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
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_wireless_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_SSID_PAUSED,
                {
                    SERVICE_FIELD_SSID_PROFILE_ID: "unknown-profile",
                    SERVICE_FIELD_ENABLED: False,
                    SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                },
                blocking=True,
            )
        await hass.async_block_till_done()


async def test_get_wireless_status_service_returns_profiles(
    hass: HomeAssistant,
) -> None:
    """Test get_wireless_status returns the SSID profiles and access points."""
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
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_wireless_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WIRELESS_STATUS,
            {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
            blocking=True,
            return_response=True,
        )
        await hass.async_block_till_done()

    assert response is not None
    profiles = response["ssid_profiles"]
    assert len(profiles) == 2
    by_uuid = {profile["profile_uuid"]: profile for profile in profiles}
    assert by_uuid["cca57d09-34dd-41b0-a128-320c8ed7f126"]["ssid"] == "Castle"
    guest = by_uuid["f185dc47-2730-48a8-844c-b57aa31af4ba"]
    assert guest["ssid"] == "Castle Guest"
    assert guest["vlan"] == 100
    assert guest["interface"] == "br1"
    assert response["access_points"][0]["name"] == "Upstairs"
    assert response["access_points"][0]["model"] == "fwap-D"


async def test_admin_service_allows_admin_user(hass: HomeAssistant) -> None:
    """Admin services allow calls from administrator users."""
    handler = AsyncMock()
    service = "permission_admin"
    _async_register_service(
        hass,
        service=service,
        handler=handler,
        schema={},
        supports_response=SupportsResponse.NONE,
        admin=True,
    )
    user = await hass.auth.async_create_user("Admin")

    await hass.services.async_call(
        DOMAIN,
        service,
        context=Context(user_id=user.id),
        blocking=True,
    )

    handler.assert_awaited_once()


async def test_admin_service_rejects_non_admin_user(hass: HomeAssistant) -> None:
    """Admin services reject calls from non-administrator users."""
    handler = AsyncMock()
    service = "permission_non_admin"
    _async_register_service(
        hass,
        service=service,
        handler=handler,
        schema={},
        supports_response=SupportsResponse.NONE,
        admin=True,
    )
    await hass.auth.async_create_user("Owner")
    user = await hass.auth.async_create_user("User")

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            context=Context(user_id=user.id),
            blocking=True,
        )

    handler.assert_not_awaited()


async def test_admin_service_allows_automation_call(hass: HomeAssistant) -> None:
    """Admin services allow calls without a signed-in user."""
    handler = AsyncMock()
    service = "permission_automation"
    _async_register_service(
        hass,
        service=service,
        handler=handler,
        schema={},
        supports_response=SupportsResponse.NONE,
        admin=True,
    )

    await hass.services.async_call(DOMAIN, service, blocking=True)

    handler.assert_awaited_once()


@pytest.mark.parametrize(
    ("service", "service_data"),
    (
        pytest.param(
            SERVICE_ARCHIVE_ALARMS,
            {SERVICE_FIELD_ALARM_STATUS: ALARM_STATUS_ACTIVE},
            id="archive-alarms",
        ),
        pytest.param(
            SERVICE_DELETE_ALARMS,
            {
                SERVICE_FIELD_ALARM_STATUS: ALARM_STATUS_ACTIVE,
                SERVICE_FIELD_CONFIRM: True,
            },
            id="delete-alarms",
        ),
        pytest.param(
            SERVICE_MUTE_ALARM,
            {
                SERVICE_FIELD_DURATION: "always",
                SERVICE_FIELD_SCOPE_KIND: "all",
                SERVICE_FIELD_ALARM_MATCH_TYPE: MATCH_TYPE_ALARM_TYPE,
                SERVICE_FIELD_ALARM_MATCH_VALUE: "ALARM_GAME",
            },
            id="mute-alarm",
        ),
        pytest.param(
            SERVICE_UNMUTE_ALARM,
            {SERVICE_FIELD_EXCEPTION_ID: "exception-1"},
            id="unmute-alarm",
        ),
        pytest.param(
            SERVICE_DELETE_RULE,
            {SERVICE_FIELD_RULE_ID: "rule-1", SERVICE_FIELD_CONFIRM: True},
            id="delete-rule",
        ),
    ),
)
async def test_phase_two_write_services_reject_non_admin_users(
    hass: HomeAssistant,
    service: str,
    service_data: dict[str, object],
) -> None:
    """New alarm and rule write services enforce the Phase 1 admin gate."""
    await async_setup_services(hass)
    await hass.auth.async_create_user("Owner")
    user = await hass.auth.async_create_user("User")

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            service_data,
            context=Context(user_id=user.id),
            blocking=True,
        )


async def test_get_alarms_is_not_admin_gated(hass: HomeAssistant) -> None:
    """The read-only alarm service is available to non-admin users."""
    await async_setup_services(hass)
    await hass.auth.async_create_user("Owner")
    user = await hass.auth.async_create_user("User")

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_ALARMS,
            {SERVICE_FIELD_INCLUDE_ARCHIVED: False},
            context=Context(user_id=user.id),
            blocking=True,
            return_response=True,
        )

    assert err.value.translation_key == "multiple_entries_loaded"


async def test_get_alarms_returns_normalized_data_and_report_metadata(
    hass: HomeAssistant,
) -> None:
    """The alarm service combines both sets and uses the shared report envelope."""
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
    snapshot = replace(_snapshot(), active_alarm_count=1, archived_alarm_count=1)

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=snapshot,
        ),
        patch.object(
            FirewallaApiClient,
            "async_get_alarms",
            new=AsyncMock(
                return_value=(
                    {
                        "aid": "active-1",
                        "type": "ALARM_VIDEO",
                        "alarmTimestamp": "1789047961.2",
                        "p.dest.category": "av",
                    },
                )
            ),
        ),
        patch.object(
            FirewallaApiClient,
            "async_get_archived_alarms",
            new=AsyncMock(
                return_value=(
                    {
                        "aid": "archived-1",
                        "type": "ALARM_GAME",
                        "alarmTimestamp": "1789047962.2",
                        "p.dest.category": "games",
                    },
                )
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_ALARMS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_INCLUDE_ARCHIVED: True,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert [alarm["alarm_id"] for alarm in response["alarms"]] == [
        "archived-1",
        "active-1",
    ]
    assert response["alarms"][0]["is_archived"] is True
    # fired_at is an ISO 8601 string; fired_at_timestamp is the epoch form.
    fired_at = response["alarms"][0]["fired_at"]
    fired_at_timestamp = response["alarms"][0]["fired_at_timestamp"]
    assert isinstance(fired_at, str)
    assert "T" in fired_at
    assert isinstance(fired_at_timestamp, float)
    assert response["active_count"] == 1
    assert response["archived_count"] == 1
    assert response["metadata"]["warnings"] == []
    assert response["metadata"]["provenance"]["alarms"]["source_field"] == (
        "alarms / archivedAlarms"
    )
    assert response["time_basis"]["kind"] == "box_retained_history"


@pytest.mark.parametrize(
    ("service", "service_data", "translation_key"),
    (
        pytest.param(
            SERVICE_DELETE_ALARMS,
            {
                SERVICE_FIELD_ALARM_STATUS: ALARM_STATUS_ACTIVE,
                SERVICE_FIELD_CONFIRM: False,
            },
            "delete_alarms_confirm_required",
            id="alarm-delete",
        ),
        pytest.param(
            SERVICE_DELETE_RULE,
            {SERVICE_FIELD_RULE_ID: "rule-1", SERVICE_FIELD_CONFIRM: False},
            "delete_rule_confirm_required",
            id="rule-delete",
        ),
    ),
)
async def test_destructive_delete_services_require_confirmation(
    hass: HomeAssistant,
    service: str,
    service_data: dict[str, object],
    translation_key: str,
) -> None:
    """Alarm and rule deletion fail closed unless confirm is true."""
    await async_setup_services(hass)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, service, service_data, blocking=True)

    assert err.value.translation_key == translation_key


@pytest.mark.parametrize(
    ("service", "service_data", "expected_key"),
    (
        pytest.param(
            SERVICE_ARCHIVE_ALARMS,
            {},
            "selector_required",
            id="archive-nothing-selected",
        ),
        pytest.param(
            SERVICE_ARCHIVE_ALARMS,
            {
                SERVICE_FIELD_ALARM_ID: "1728",
                SERVICE_FIELD_ALARM_STATUS: ALARM_STATUS_ACTIVE,
            },
            "selector_conflict",
            id="archive-both-selected",
        ),
        pytest.param(
            SERVICE_DELETE_ALARMS,
            {SERVICE_FIELD_CONFIRM: True},
            "selector_required",
            id="delete-nothing-selected",
        ),
        pytest.param(
            SERVICE_DELETE_ALARMS,
            {
                SERVICE_FIELD_ALARM_ID: "1728",
                SERVICE_FIELD_ALARM_STATUS: ALARM_STATUS_ARCHIVED,
                SERVICE_FIELD_CONFIRM: True,
            },
            "selector_conflict",
            id="delete-both-selected",
        ),
    ),
)
async def test_alarm_services_require_exactly_one_selector(
    hass: HomeAssistant,
    service: str,
    service_data: dict[str, object],
    expected_key: str,
) -> None:
    """Test a bulk alarm operation cannot be wide by accident or by ambiguity.

    This is what the explicit selector buys. The old contract took a required `mode`
    whose `this` value needed a separate `alarm_id`, so `mode: this` with no alarm
    was a runtime error and `mode` also had to be kept in step with `alarm_id` by
    the caller. Now the wide case is stated by naming a set, and the narrow case by
    naming an alarm, so neither can be reached by forgetting a field.
    """
    await async_setup_services(hass)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, service, service_data, blocking=True)

    assert err.value.translation_key == expected_key


_FLOW_WINDOW_BEGIN = 1_790_948_400
_FLOW_WINDOW_END = 1_791_034_800
_FLOW_HOST_MAC = "EC:0D:51:CC:BA:BC"
_FLOW_GROUP_ID = "12"
_FLOW_AFFILIATED_TAG_ID = "10"
_FLOW_USER_ID = "21"


def _flow_report_rollup_payload() -> dict[str, object]:
    """Return a rollup shaped like the box's, with every section populated.

    The blocks mirror the live measurements: `count` is bytes on the byte
    families and a block count on the blocked ones, a `local:` family carries
    `dstMac` instead of a hostname, and the per-member block is only populated on
    a tag request.
    """

    def _row(**fields: object) -> dict[str, object]:
        return {"begin": _FLOW_WINDOW_BEGIN, "end": _FLOW_WINDOW_END, **fields}

    return {
        "flows": {
            "download": [
                _row(host="a.example", count="1000", device=_FLOW_HOST_MAC),
                _row(host="b.example", count="250"),
            ],
            "upload": [_row(host="a.example", count="400", device=_FLOW_HOST_MAC)],
            "dnsB": [_row(host="ads.example", count="7")],
            "local:in": [_row(dstMac="AA:BB:CC:DD:EE:FF", count="5")],
        },
        "hosts": {
            _FLOW_HOST_MAC: {"download": 1000, "upload": 400, "conn": 5},
            "AA:BB:CC:DD:EE:99": {"download": 10, "upload": 1},
        },
    }


def _flow_report_block_page() -> FlowLogPage:
    """Return one blocked page naming a rule the box still has."""
    return FlowLogPage(
        records=(
            {
                "ts": 1_791_000_000.5,
                "ltype": "audit",
                "device": _FLOW_HOST_MAC,
                "deviceIP": "192.168.200.25",
                "domain": "ads.example",
                "pid": 7,
                "type": "dns",
                "tags": [_FLOW_GROUP_ID],
            },
        ),
        reported_count=1,
        next_cursor=None,
    )


def _flow_report_regular_page() -> FlowLogPage:
    """Return one regular page carrying byte and duration detail."""
    return FlowLogPage(
        records=(
            {
                "ts": 1_791_000_100.25,
                "ltype": "flow",
                "device": _FLOW_HOST_MAC,
                "deviceIP": "192.168.200.25",
                "host": "a.example",
                "ip": "203.0.113.9",
                "download": 2048,
                "upload": 512,
                "duration": 12.5,
            },
        ),
        reported_count=1,
        next_cursor=None,
    )


_FLOW_REPORT_CLIENT_PREFIX = (
    "custom_components.firewalla_local.api.client.FirewallaApiClient."
)


@contextmanager
def _flow_report_client(
    *,
    rollup: dict[str, object] | None = None,
) -> Iterator[dict[str, AsyncMock]]:
    """Patch the client calls one flow-report service test needs.

    Yields the three flow mocks so a test can assert which were called and can
    make one fail.
    """
    with (
        patch(
            f"{_FLOW_REPORT_CLIENT_PREFIX}async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            f"{_FLOW_REPORT_CLIENT_PREFIX}build_runtime_snapshot",
            return_value=_usage_history_snapshot(),
        ),
        patch(
            f"{_FLOW_REPORT_CLIENT_PREFIX}async_get_flow_rollup_payload",
            new=AsyncMock(
                return_value=_flow_report_rollup_payload() if rollup is None else rollup
            ),
        ) as mock_rollup,
        patch(
            f"{_FLOW_REPORT_CLIENT_PREFIX}async_get_block_log_payload",
            new=AsyncMock(return_value=_flow_report_block_page()),
        ) as mock_block_log,
        patch(
            f"{_FLOW_REPORT_CLIENT_PREFIX}async_get_flow_log_payload",
            new=AsyncMock(return_value=_flow_report_regular_page()),
        ) as mock_flow_log,
    ):
        yield {
            "rollup": mock_rollup,
            "block_log": mock_block_log,
            "flow_log": mock_flow_log,
        }


def _flow_report_entry() -> MockConfigEntry:
    """Return one Firewalla config entry for flow-report service tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )


async def _flow_report_response(
    hass: HomeAssistant,
    *,
    scope: dict[str, object] | None = None,
    extra: dict[str, object] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, AsyncMock], MockConfigEntry]:
    """Set up an entry and call the flow-report service once.

    ``scope`` replaces the default group and ``extra`` adds to it. They are separate
    because the service accepts exactly one selector field, so a test that changes
    only the detail level must not also have to restate the scope -- and a test that
    changes the scope must not leave the default group behind to conflict with it.
    """
    entry = _flow_report_entry()
    entry.add_to_hass(hass)

    with _flow_report_client() as client:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        data: dict[str, object] = {
            SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            SERVICE_FIELD_REFRESH: False,
            **(
                scope if scope is not None else {SERVICE_FIELD_GROUP_NAME: "Quarantine"}
            ),
            **(extra or {}),
        }
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_FLOW_REPORT,
            data,
            blocking=True,
            return_response=True,
        )

    return cast("dict[str, Any] | None", response), client, entry


@pytest.mark.asyncio
async def test_flow_report_summarises_a_group_without_reading_records(
    hass: HomeAssistant,
) -> None:
    """Test a summary is one rollup and makes no record read at all."""
    response, client, _entry = await _flow_report_response(hass)

    assert client["block_log"].await_count == 0
    assert client["flow_log"].await_count == 0
    assert response is not None
    assert response["target"] == {
        "kind": "group",
        "id": _FLOW_GROUP_ID,
        "name": "Quarantine",
        "network_kind": None,
    }
    # A group's identity and its protocol target are the same id, so the resolution
    # is reported but does not remap anything.
    assert response["query"]["resolved_type"] == "tag"
    assert response["query"]["resolved_target"] == _FLOW_GROUP_ID
    assert response["query"]["identity_remapped"] is False
    assert response["summary"]["totals"]["download_bytes"] == 1250
    assert response["summary"]["totals"]["upload_bytes"] == 400
    assert response["summary"]["totals"]["blocked_total"] == 7
    assert response["summary"]["includes_records"] is False
    assert response["summary"]["window"] == {
        "requested_hours": 24,
        "begin_timestamp": _FLOW_WINDOW_BEGIN,
        "end_timestamp": _FLOW_WINDOW_END,
        "served_hours": 24.0,
        "is_clamped": False,
    }
    assert "blocked_records" not in response["sections"]
    assert "flow_records" not in response["sections"]
    assert response["time_basis"]["kind"] == "window"
    assert response["time_basis"]["is_partial"] is False
    assert response["sections"]["blocked"][0]["block_count"] == 7
    assert response["sections"]["local_peers"][0]["peer_id"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.asyncio
async def test_flow_report_records_detail_reads_both_record_families(
    hass: HomeAssistant,
) -> None:
    """Test records detail reads the block log and the flow log separately.

    Both families carry their own time basis, because a record read is a reverse
    walk from an instant rather than the windowed aggregate the rollup is.
    """
    response, client, _entry = await _flow_report_response(
        hass, extra={SERVICE_FIELD_DETAIL: "records"}
    )

    assert client["block_log"].await_count == 1
    assert client["flow_log"].await_count == 1
    assert response is not None
    blocked = response["sections"]["blocked_records"]
    regular = response["sections"]["flow_records"]
    assert blocked["time_basis"]["kind"] == "flow_log"
    assert regular["time_basis"]["kind"] == "flow_log"
    assert blocked["rows_returned"] == 1
    assert blocked["blocked_count"] == 1
    # The block names a rule the live registry no longer has. It is kept rather
    # than dropped, and counted, because an unattributable block is exactly the
    # signal worth surfacing.
    assert blocked["records"][0]["blocked_by_rule_id"] == 7
    assert blocked["records"][0]["rule_name"] is None
    assert blocked["unattributed_blocks"] == 1
    assert regular["records"][0]["download_bytes"] == 2048
    assert regular["records"][0]["duration_seconds"] == 12.5
    assert regular["blocked_count"] == 0


@pytest.mark.asyncio
async def test_flow_report_withholds_host_detail_by_default_on_a_group(
    hass: HomeAssistant,
) -> None:
    """Test a group report names no device the caller did not itself name.

    The member ranking, each destination's device ids, and each record's device
    id and address are absent, and the withheld ranking is **not** reported as
    unavailable -- it can still be retrieved, so calling it unavailable would be a
    false statement about the box.
    """
    response, _client, _entry = await _flow_report_response(
        hass, extra={SERVICE_FIELD_DETAIL: "records"}
    )

    assert response is not None
    assert "member_ranking" not in response["sections"]
    assert response["summary"]["member_count"] is None
    assert "device_ids" not in response["sections"]["top_download"][0]
    assert "device_ids" not in response["sections"]["blocked"][0]
    record = response["sections"]["blocked_records"]["records"][0]
    assert "device_id" not in record
    assert "device_ip" not in record
    assert response["metadata"]["applied"]["host_detail"] is False
    assert "member_ranking" not in response["metadata"]["unavailable_sections"]


@pytest.mark.asyncio
async def test_flow_report_returns_host_detail_when_it_is_asked_for(
    hass: HomeAssistant,
) -> None:
    """Test the include widens the same report rather than unlocking it."""
    response, _client, _entry = await _flow_report_response(
        hass,
        extra={
            SERVICE_FIELD_DETAIL: "records",
            SERVICE_FIELD_INCLUDE: ["host_detail"],
        },
    )

    assert response is not None
    assert response["metadata"]["applied"]["host_detail"] is True
    assert response["summary"]["member_count"] == 2
    assert response["sections"]["member_ranking"][0]["device_id"] == _FLOW_HOST_MAC
    assert response["sections"]["top_download"][0]["device_ids"] == [_FLOW_HOST_MAC]
    record = response["sections"]["blocked_records"]["records"][0]
    assert record["device_id"] == _FLOW_HOST_MAC
    assert record["device_ip"] == "192.168.200.25"


@pytest.mark.asyncio
async def test_flow_report_needs_no_flag_to_name_the_device_it_was_asked_about(
    hass: HomeAssistant,
) -> None:
    """Test a device target is never returned stripped of its own identity.

    A device report names nothing beyond the device that was asked for, so the
    include has nothing to withhold. Gating it anyway would answer "what did this
    device do" with records that decline to say which device.
    """
    response, _client, _entry = await _flow_report_response(
        hass,
        scope={
            SERVICE_FIELD_HOST_NAME: "Kaden Phone",
        },
        extra={SERVICE_FIELD_DETAIL: "records"},
    )

    assert response is not None
    assert response["target"]["kind"] == "host"
    assert response["target"]["id"] == _FLOW_HOST_MAC
    assert response["query"]["resolved_target"] == _FLOW_HOST_MAC
    assert response["metadata"]["applied"]["host_detail"] is True
    assert (
        response["sections"]["blocked_records"]["records"][0]["device_id"]
        == _FLOW_HOST_MAC
    )


@pytest.mark.asyncio
async def test_flow_report_resolves_a_user_to_its_affiliated_tag(
    hass: HomeAssistant,
) -> None:
    """Test a user scopes to the tag the flow queries accept, not to the user id.

    Measured on the dev box: the flow queries returned hundreds of rows for a
    user's affiliated tag and **zero** for the user id, while the app-time-usage
    query returned byte-identical payloads for both. Scoping to the user id would
    therefore return an empty report for most users while claiming success.
    """
    response, _client, _entry = await _flow_report_response(
        hass,
        scope={SERVICE_FIELD_USER_NAME: "KADEN"},
    )

    assert response is not None
    # The published identity is the user id, matching the watched-user entities and
    # `get_time_usage_report`. The affiliated tag is the *protocol* target, so it is
    # reported as the resolution rather than as the target.
    assert response["target"]["kind"] == "user"
    assert response["target"]["id"] == _FLOW_USER_ID
    assert response["query"]["resolved_type"] == "tag"
    assert response["query"]["resolved_target"] == _FLOW_AFFILIATED_TAG_ID
    assert response["query"]["identity_remapped"] is True
    assert response["query"]["resolved_field"] == SERVICE_FIELD_USER_NAME


@pytest.mark.asyncio
async def test_flow_report_stops_a_record_walk_that_cannot_advance(
    hass: HomeAssistant,
) -> None:
    """Test an all-records walk halts on a cursor that does not move.

    The walk's stop conditions are the deadline and a non-advancing cursor, never
    a row count, so a cursor that repeats itself must end the walk and say so
    rather than looping. The page size the caller asked for is what reaches the
    client, because the schema admits exactly the range the transport supports.
    """
    entry = _flow_report_entry()
    entry.add_to_hass(hass)

    repeating = FlowLogPage(
        records=_flow_report_block_page().records,
        reported_count=1,
        next_cursor=1_791_000_000.5,
    )

    with _flow_report_client() as client:
        client["block_log"].return_value = repeating
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_FLOW_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_DETAIL: "records",
                SERVICE_FIELD_RECORD_COUNT: 500,
                SERVICE_FIELD_FETCH_ALL_RECORDS: True,
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert client["block_log"].await_args is not None
    assert client["block_log"].await_args.kwargs["count"] == 500
    assert client["block_log"].await_count == 2
    assert response is not None
    blocked = response["sections"]["blocked_records"]
    assert blocked["truncated"] is True
    assert blocked["time_basis"]["is_partial"] is True
    assert blocked["pages_fetched"] == 2
    assert blocked["records_dropped_as_duplicates"] == 1


@pytest.mark.asyncio
async def test_flow_report_rejects_a_group_that_does_not_exist(
    hass: HomeAssistant,
) -> None:
    """Test an unmatched selector fails with its own translation key."""
    entry = _flow_report_entry()
    entry.add_to_hass(hass)

    with _flow_report_client():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GET_FLOW_REPORT,
                {
                    SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                    SERVICE_FIELD_GROUP_NAME: "no-such-group",
                    SERVICE_FIELD_REFRESH: False,
                },
                blocking=True,
                return_response=True,
            )

    assert err.value.translation_key == "flow_report_scope_not_found"


@pytest.mark.parametrize(
    ("data", "expected_key"),
    [
        pytest.param(
            {
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_USER_NAME: "KADEN",
            },
            "selector_conflict",
            id="two-selectors",
        ),
        pytest.param(
            {SERVICE_FIELD_GROUP_NAME: "Quarantine", SERVICE_FIELD_GROUP_ID: "12"},
            "selector_conflict",
            id="both-fields-of-one-pair",
        ),
        pytest.param({}, "selector_required", id="no-selector"),
    ],
)
@pytest.mark.asyncio
async def test_flow_report_accepts_exactly_one_scope_selector(
    hass: HomeAssistant,
    data: dict[str, object],
    expected_key: str,
) -> None:
    """Test the exactly-one rule: two selectors and none are both errors.

    Two fields of the *same* pair is included deliberately. A caller writing both
    `group_name` and `group_id` has made an ambiguous request rather than stated a
    preference, and silently preferring one would hide a typo in the other.
    """
    entry = _flow_report_entry()
    entry.add_to_hass(hass)

    with _flow_report_client():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GET_FLOW_REPORT,
                {
                    SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                    SERVICE_FIELD_REFRESH: False,
                    **data,
                },
                blocking=True,
                return_response=True,
            )

    assert err.value.translation_key == expected_key


@pytest.mark.asyncio
async def test_flow_report_name_field_does_not_match_an_id(
    hass: HomeAssistant,
) -> None:
    """Test a name selector matches names only, never another group's id.

    This is what the typed pair buys over the free-text field it replaced. That one
    tried identifiers and names in the same lookup, so a value that happened to be a
    group's id could satisfy a selector the caller meant as a name -- and the caller
    would get a different scope's data with no way to notice.
    """
    entry = _flow_report_entry()
    entry.add_to_hass(hass)

    with _flow_report_client():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GET_FLOW_REPORT,
                {
                    SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                    # `12` is the group's id, not its name.
                    SERVICE_FIELD_GROUP_NAME: _FLOW_GROUP_ID,
                    SERVICE_FIELD_REFRESH: False,
                },
                blocking=True,
                return_response=True,
            )

    assert err.value.translation_key == "flow_report_scope_not_found"


@pytest.mark.asyncio
async def test_flow_report_marks_a_section_the_box_did_not_return(
    hass: HomeAssistant,
) -> None:
    """Test an unreadable rollup is reported rather than failing the whole call.

    A section that could not be read is unavailable. That is a different statement
    from a section withheld by the identity gate, and the two must not be
    conflated -- so this also pins that the withheld ranking is not listed here.
    """
    entry = _flow_report_entry()
    entry.add_to_hass(hass)

    with _flow_report_client() as client:
        client["rollup"].side_effect = FirewallaProtocolError("unexpected shape")
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_FLOW_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["summary"]["totals"] is None
    assert response["sections"] == {}
    # The whole summary is missing, so naming the member ranking separately would
    # only repeat that. `unavailable_sections` answers "what could not be read",
    # and a section inside an unreadable summary was not read either.
    assert response["metadata"]["unavailable_sections"] == ["summary"]
    assert [warning["code"] for warning in response["metadata"]["warnings"]] == [
        "flow_summary_unavailable"
    ]


@pytest.mark.asyncio
async def test_flow_report_reports_a_clamped_window_it_was_not_asked_for(
    hass: HomeAssistant,
) -> None:
    """Test a window the box quietly shortened is reported as served, not asked.

    The box serves 24 hours for anything wider and says nothing, so reporting the
    requested window would describe data the caller does not have.
    """
    response, _client, _entry = await _flow_report_response(
        hass, extra={SERVICE_FIELD_WINDOW_HOURS: 168}
    )

    assert response is not None
    assert response["query"]["window_hours"] == 168
    assert response["summary"]["window"]["requested_hours"] == 168
    assert response["summary"]["window"]["served_hours"] == 24.0
    assert response["summary"]["window"]["is_clamped"] is True
    assert response["time_basis"]["is_partial"] is True


@pytest.mark.asyncio
async def test_flow_report_accepts_exactly_the_fields_the_llm_tool_passes(
    hass: HomeAssistant,
) -> None:
    """Test a call carrying only the tool's parameters produces a full report.

    The tool deliberately omits `refresh`, `detail`, `record_count` and
    `fetch_all_records`, so this is what proves those omissions are safe: the
    schema defaults have to fill them in. A tool that omitted a field the service
    left unset would pass its unit tests and fail in a session.
    """
    entry = _flow_report_entry()
    entry.add_to_hass(hass)

    with _flow_report_client() as client:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_FLOW_REPORT,
            {
                SERVICE_FIELD_GROUP_NAME: "Quarantine",
            },
            blocking=True,
            return_response=True,
        )

    # The omitted `refresh` defaulted to true, so the runtime was refreshed.
    assert client["rollup"].await_count == 1
    assert response is not None
    assert response["query"]["refresh"] is True
    # The omitted `detail` defaulted to summary, so no records were read.
    assert response["query"]["detail"] == "summary"
    assert response["query"]["record_count"] == 300
    assert response["query"]["fetch_all_records"] is False
    assert response["summary"]["totals"] is not None
    assert response["metadata"]["applied"]["host_detail"] is False


@pytest.mark.parametrize(
    ("field", "selector"),
    [
        pytest.param(SERVICE_FIELD_USER_NAME, "KADEN", id="by-name"),
        pytest.param(SERVICE_FIELD_USER_ID, _FLOW_USER_ID, id="by-user-id"),
        pytest.param(
            SERVICE_FIELD_USER_ID, _FLOW_AFFILIATED_TAG_ID, id="by-affiliated-tag"
        ),
    ],
)
@pytest.mark.asyncio
async def test_flow_report_accepts_every_user_selector_it_can_report(
    hass: HomeAssistant,
    field: str,
    selector: str,
) -> None:
    """Test a user resolves the same way by name, user id, or affiliated tag.

    All three forms matter. The name is what a person types; the user id is what
    this service publishes as the identity and what `get_time_usage_report`
    accepts; and the affiliated tag is what the response reports as the resolved
    protocol target. Before this, echoing the resolved target back produced
    `flow_report_scope_not_found` -- the report handed out an id it would not
    accept, which no other service in this integration does.

    The affiliated tag is passed through `user_id` rather than `user_name` because
    it is an identifier the service handed out, not a label anyone types.
    """
    response, _client, _entry = await _flow_report_response(
        hass,
        scope={field: selector},
    )

    assert response is not None
    assert response["target"] == {
        "kind": "user",
        "id": _FLOW_USER_ID,
        "name": "KADEN",
        "network_kind": None,
    }
    assert response["query"]["resolved_target"] == _FLOW_AFFILIATED_TAG_ID


@pytest.mark.asyncio
async def test_flow_report_publishes_the_same_user_id_as_the_usage_service(
    hass: HomeAssistant,
) -> None:
    """Test both report services name the same user by the same id.

    They reach the box differently -- `item=appTimeUsage` accepts a user id or the
    affiliated tag interchangeably, while the flow queries accept only the tag --
    but a consumer correlating the two reports for one person must not have to know
    that. Both publish the user id.
    """
    entry = _flow_report_entry()
    entry.add_to_hass(hass)

    with _flow_report_client():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        flow_response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_FLOW_REPORT,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_USER_NAME: "KADEN",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert flow_response is not None
    # The usage service reports `target_id` = the user id for the same user; see
    # `_usage_history_snapshot`, where the user is user_id "21" in tag "10".
    assert flow_response["target"]["id"] == _FLOW_USER_ID


@pytest.mark.asyncio
async def test_network_segment_usage_warns_when_rankings_were_not_returned(
    hass: HomeAssistant,
) -> None:
    """Test an empty ranking says *why* it is empty.

    An empty `top_download_hosts` has two causes that look identical: nothing
    transferred, or the box never returned the ranking families. A bare
    `item=intf` produced the second and reported it as the first, so a caller was
    told "nothing is using bandwidth" by a payload that had not measured it. The
    warning names the families that *were* returned so the distinction is visible.
    """
    # A bare v1 read: the app families only, with no ranking families at all.
    base = _network_interface_payload()
    payload = {
        **base,
        "flows": {
            "appDetails": {"youtube": [{"device": "00:AA:BB:CC:DD:26"}]},
            "categoryDetails": {"av": [{"device": "00:AA:BB:CC:DD:26"}]},
            "recent": [],
        },
    }

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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_speed_test_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=payload),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["sections"]["rankings"]["top_download_hosts"] == []
    assert [w["code"] for w in response["metadata"]["warnings"]] == [
        "ranking_families_unavailable"
    ]
    assert response["summary"]["flow_families"] == [
        "appDetails",
        "categoryDetails",
        "recent",
    ]


@pytest.mark.asyncio
async def test_network_segment_usage_stays_silent_when_rankings_are_present(
    hass: HomeAssistant,
) -> None:
    """Test a network with real rankings raises no warning."""
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
            new=AsyncMock(return_value=_network_segment_report_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_speed_test_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=_network_interface_payload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_SEGMENT_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["summary"]["top_download_count"] > 0
    assert response["metadata"]["warnings"] == []


@pytest.mark.asyncio
async def test_wan_events_empty_result_explains_itself(
    hass: HomeAssistant,
) -> None:
    """Test no events is reported as a quiet period, not a failed read.

    This service can legitimately return nothing, and it was the only report
    without a `time_basis` or `metadata`, so an empty result was indistinguishable
    from a bounded or failed one. A caller must be able to tell "we searched and
    found nothing" from "we could not search".
    """
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
            return_value=_speed_test_snapshot(),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_wan_events_payload",
            new=AsyncMock(return_value=[]),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_WAN_EVENTS,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["count"] == 0
    assert response["results"] == []
    assert response["time_basis"]["kind"] == "event_window"
    assert response["time_basis"]["time_zone"]
    assert [w["code"] for w in response["metadata"]["warnings"]] == ["no_wan_events"]
    assert "quiet period" in response["metadata"]["warnings"][0]["message"]
    assert response["metadata"]["provenance"]["events"]["source_field"] == "item=events"
