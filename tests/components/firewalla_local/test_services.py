"""Tests for Firewalla Local services."""

from __future__ import annotations

# pylint: disable=too-many-lines
from copy import deepcopy
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    CONF_SYMMETRIC_KEY,
    DOMAIN,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIG_ENTRY_NAME,
    SERVICE_FIELD_CURRENT_PERIODS,
    SERVICE_FIELD_DETAIL,
    SERVICE_FIELD_HISTORY_COUNT,
    SERVICE_FIELD_HISTORY_PERIOD,
    SERVICE_FIELD_INCLUDE,
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_NETWORK_UUID,
    SERVICE_FIELD_OFFSET,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_FIELD_SECTIONS,
    SERVICE_FIELD_TOP_N,
    SERVICE_FIELD_USAGE_HISTORY_APP_IDS,
    SERVICE_FIELD_USAGE_HISTORY_BEGIN,
    SERVICE_FIELD_USAGE_HISTORY_END,
    SERVICE_FIELD_USAGE_HISTORY_GRANULARITY,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_FIELD_WINDOW,
    SERVICE_GET_NETWORK_SEGMENT_REPORT,
    SERVICE_GET_NETWORK_SEGMENT_USAGE,
    SERVICE_GET_SPEED_TEST_RESULTS,
    SERVICE_GET_TIME_USAGE_REPORT,
    SERVICE_GET_WAN_DATA_USAGE,
    SERVICE_GET_WAN_EVENTS,
    SERVICE_PAUSE_RULE,
    SERVICE_RESUME_RULE,
    SERVICE_RUN_INTERNET_SPEED_TEST,
)
from custom_components.firewalla_local.coordinator import FirewallaRuntimeData
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaGroupRuntime,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
    FirewallaUserRuntime,
)
from custom_components.firewalla_local.services import _get_loaded_entry


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
            }
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
                display_name="Office Phone",
                fallback_name=None,
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
                display_name="Plex Server",
                fallback_name=None,
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
                display_name="Kaden Phone",
                fallback_name=None,
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
        groups=(FirewallaGroupRuntime(group_id="10", name="KADEN's Devices"),),
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
                SERVICE_FIELD_RULE_TARGET: "744",
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
                SERVICE_FIELD_RULE_TARGET: "999",
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

    with pytest.raises(ServiceValidationError, match="Invalid duration"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_TARGET: "744",
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
                SERVICE_FIELD_RULE_TARGET: "744",
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
                SERVICE_FIELD_RULE_TARGET: "744",
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

    with pytest.raises(ServiceValidationError, match="Provide either duration"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_TARGET: "744",
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
                SERVICE_FIELD_RULE_TARGET: "744",
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
                SERVICE_FIELD_RULE_TARGET: "888",
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
        match=(
            "Multiple Firewalla entries are loaded; "
            "use config_entry_id or config_entry_name"
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_TARGET: "888",
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

    with pytest.raises(ServiceValidationError, match="Rule target not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_RULE,
            {
                SERVICE_FIELD_RULE_TARGET: "999",
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
                SERVICE_FIELD_RULE_TARGET: "744",
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
    assert response["latest"] is not None
    assert response["latest"]["wan_uuid"] == "wan-1"
    assert response["latest"]["wan_name"] == "WAN-ONE"
    assert response["results"] == [response["latest"]]


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
    assert response["latest"]["wan_uuid"] == "wan-2"


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
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND: "device",
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET: (
                    "Kaden Phone (192.168.200.25)"
                ),
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
        "kind": "device",
        "id": "EC:0D:51:CC:BA:BC",
        "name": "Kaden Phone",
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
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND: "device",
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET: (
                    "Kaden Phone (192.168.200.25)"
                ),
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
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND: "user",
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET: "KADEN",
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
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND: "group",
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET: "KADEN's Devices",
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
    assert mock_get_usage_history.await_args.kwargs["target"] == "10"
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
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND: "device",
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET: "EC:0D:51:CC:BA:BC",
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
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND: "device",
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET: "EC:0D:51:CC:BA:BC",
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
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND: "device",
                SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET: "EC:0D:51:CC:BA:BC",
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


async def test_get_wan_data_usage_service_returns_current_month_summary_by_default(
    hass: HomeAssistant,
) -> None:
    """Test the WAN data usage service returns current-month summary by default."""
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
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_monthly.await_count == 1
    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["refreshed"] is True
    assert response["target"] == {
        "kind": "wan_collection",
        "id": None,
        "name": None,
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
    assert first_report["target"] == {"kind": "wan", "id": "wan-1", "name": "WAN-ONE"}
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
    assert response["target"] == {"kind": "wan", "id": "wan-1", "name": "WAN-ONE"}
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
        "kind": "network_segment",
        "id": "5799d896-5e0f-40a5-a776-38a5d7746204",
        "name": "VLAN10 CORE",
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
        "has_dhcp_config": True,
        "has_ipv4_addressing": True,
        "has_ipv6_addressing": False,
    }
    assert response["sections"]["configuration"] == {
        "interface_name": "bond0.10",
        "type": "lan",
        "monitoring": True,
        "active": None,
        "ready": None,
        "pending_test": None,
        "policy": {"state": True},
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
        "applied": {"refresh": False},
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
        },
    }


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
        match="Provide network_uuid or network_name",
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
        "kind": "network_segment",
        "id": "5799d896-5e0f-40a5-a776-38a5d7746204",
        "name": "VLAN10 CORE",
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


async def test_get_network_segment_usage_service_requires_window(
    hass: HomeAssistant,
) -> None:
    """Test the network segment usage service requires one window."""
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

    with pytest.raises(ServiceValidationError, match="Provide window"):
        await hass.services.async_call(
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
        match="Provide network_uuid or network_name",
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
            new=AsyncMock(return_value=_wan_events_payload()),
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
    assert mock_get_events.await_args.kwargs == {
        "limit_count": 100,
        "limit_offset": 10,
    }
    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["wan"] == {"uuid": "wan-1", "name": "WAN-ONE"}
    assert response["query"] == {"limit": 100, "offset": 10}
    assert response["count"] == 3
    assert response["results"][0] == {
        "family": "ping_RTT",
        "event_type": "action",
        "timestamp": 1_774_036_038.371,
        "timestamp_iso": "2026-03-20T19:47:18.371000+00:00",
        "value": 1,
        "previous_value": None,
        "ok_value": None,
        "state_key": None,
        "wan_uuid": "wan-1",
        "wan_name": "WAN-ONE",
        "active": None,
        "ready": None,
        "changed_interface": None,
        "primary_interface": None,
        "wan_type": None,
        "wan_switched": None,
        "target": "1.1.1.1",
        "name_server": None,
        "dns_test_domain": None,
        "wan_interface_address": None,
        "measurement_kind": "rtt",
        "measurement_value": 53.2365,
        "threshold_value": 35.3376,
        "failures": [],
        "wan_statuses": [],
    }
    assert response["results"][1]["family"] == "dualwan_state"
    assert response["results"][1]["wan_uuid"] == "wan-1"
    assert response["results"][1]["changed_interface"] == "eth0"
    assert response["results"][1]["wan_statuses"] == [
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
    assert response["results"][2]["family"] == "dns"
    assert response["results"][2]["name_server"] == "172.64.36.2"
    assert response["results"][2]["wan_interface_address"] == "23.245.207.179"
