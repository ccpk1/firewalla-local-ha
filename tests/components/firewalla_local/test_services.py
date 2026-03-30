"""Tests for Firewalla Local services."""

from __future__ import annotations

# pylint: disable=too-many-lines
from datetime import UTC, datetime
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
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_NETWORK_UUID,
    SERVICE_FIELD_OFFSET,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_FIELD_USAGE_HISTORY_APP_IDS,
    SERVICE_FIELD_USAGE_HISTORY_BEGIN,
    SERVICE_FIELD_USAGE_HISTORY_END,
    SERVICE_FIELD_USAGE_HISTORY_GRANULARITY,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND,
    SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_GET_NETWORK_INTERFACES,
    SERVICE_GET_SPEED_TEST_RESULTS,
    SERVICE_GET_USAGE_HISTORY,
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
        appliance_runtime=FirewallaApplianceRuntimeInput(),
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
        appliance_runtime=FirewallaApplianceRuntimeInput(),
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


async def test_get_usage_history_service_resolves_device_label_and_serializes_data(
    hass: HomeAssistant,
) -> None:
    """Test the usage history service resolves one device label."""
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
            SERVICE_GET_USAGE_HISTORY,
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
    assert response["scope"] == {
        "scope_kind": "device",
        "target_id": "EC:0D:51:CC:BA:BC",
        "target_name": "Kaden Phone",
        "request_scope_type": "host",
    }
    assert response["query"]["time_zone"] == "America/Los_Angeles"
    assert response["query"]["begin_local"] == "2026-03-20T21:00:00-07:00"
    assert response["query"]["end_local"] == "2026-03-27T21:00:00-07:00"
    assert response["query"]["app_ids"] is None
    assert response["internet"]["slots"][0] == {
        "timestamp": 1_774_065_600,
        "timestamp_iso": "2026-03-21T04:00:00+00:00",
        "total_minutes": 120,
        "unique_minutes": 118,
    }
    assert response["internet"]["intervals"] == []
    assert response["apps"][0]["key"] == "facebook"
    assert response["apps"][0]["metric"]["devices"][0] == {
        "device_id": "EC:0D:51:CC:BA:BC",
        "device_name": "Kaden Phone",
        "total_minutes": 15,
        "unique_minutes": 15,
        "intervals": [],
    }


async def test_get_usage_history_service_hour_granularity_keeps_intervals(
    hass: HomeAssistant,
) -> None:
    """Test hour granularity preserves interval detail."""
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
            SERVICE_GET_USAGE_HISTORY,
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
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["internet"]["intervals"] == []
    assert response["apps"][0]["metric"]["devices"][0]["intervals"] == [
        {
            "begin_timestamp": 1_774_065_660,
            "begin_timestamp_iso": "2026-03-21T04:01:00+00:00",
            "end_timestamp": 1_774_065_900,
            "end_timestamp_iso": "2026-03-21T04:05:00+00:00",
            "duration_seconds": 240,
            "duration_minutes": 5,
        }
    ]


async def test_get_usage_history_service_resolves_user_name_to_tag_scope(
    hass: HomeAssistant,
) -> None:
    """Test the usage history service resolves user names through tag scope."""
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
            SERVICE_GET_USAGE_HISTORY,
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
    assert response["scope"]["target_id"] == "21"
    assert response["scope"]["target_name"] == "KADEN"


async def test_get_usage_history_service_preserves_explicit_empty_app_list(
    hass: HomeAssistant,
) -> None:
    """Test the usage history service preserves explicit empty app filters."""
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
            SERVICE_GET_USAGE_HISTORY,
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
    assert response["wan"] is None
    assert response["query"] == {
        "current_periods": ["month"],
        "history_period": None,
        "history_count": 0,
        "detail": "summary",
        "time_zone": "America/New_York",
        "detail_applied_to": [],
        "detail_unavailable_for": [],
    }
    assert response["count"] == 2
    first_report = response["results"][0]
    assert first_report["wan"] == {"uuid": "wan-1", "name": "WAN-ONE"}
    assert first_report["current_month"]["usage"] == {
        "download_bytes": 3072,
        "upload_bytes": 1280,
        "total_bytes": 4352,
    }
    assert first_report["current_month"]["detail"] == "summary"
    assert first_report["current_month"]["days"] == []
    assert first_report["history_months"] == []


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
            return_value=_speed_test_snapshot(),
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
                SERVICE_FIELD_DETAIL: "daily",
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    first_report = response["results"][0]
    assert response["query"]["detail_applied_to"] == ["current_month"]
    assert first_report["current_month"]["detail"] == "daily"
    assert first_report["current_month"]["days"][0]["usage"] == {
        "download_bytes": 2048,
        "upload_bytes": 768,
        "total_bytes": 2816,
    }
    assert first_report["current_month"]["days"][0]["time_period"]["kind"] == "day"


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
            return_value=_speed_test_snapshot(),
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
    assert response["wan"] == {"uuid": "wan-1", "name": "WAN-ONE"}
    assert response["refreshed"] is False
    assert response["query"]["current_periods"] == []
    assert response["query"]["history_period"] == "month"
    assert response["query"]["history_count"] == 1
    first_report = response["results"][0]
    assert first_report["current_month"] is None
    assert len(first_report["history_months"]) == 1
    assert first_report["history_months"][0]["usage"] == {
        "download_bytes": 10800,
        "upload_bytes": 5400,
        "total_bytes": 16200,
    }
    assert first_report["history_months"][0]["detail"] == "summary"


async def test_get_network_interfaces_service_returns_normalized_segment_view(
    hass: HomeAssistant,
) -> None:
    """Test the network interfaces service returns normalized item=intf data."""
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=_network_interface_payload()),
        ) as mock_get_network_interface,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_INTERFACES,
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
    assert response["network"] == {
        "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
        "name": "VLAN10 CORE",
    }
    assert response["count"] == 1
    first_view = response["results"][0]
    assert first_view["network"] == {
        "uuid": "5799d896-5e0f-40a5-a776-38a5d7746204",
        "name": "VLAN10 CORE",
    }
    assert first_view["interface_name"] == "bond0.10"
    assert first_view["type"] == "lan"
    assert first_view["monitoring"] is True
    assert first_view["gateway"] == "192.168.10.1"
    assert first_view["dns_servers"] == ["192.168.10.1", "1.1.1.1"]
    assert first_view["host_count"] == 2
    assert first_view["hosts"][0] == {
        "host_id": "00:AA:BB:CC:DD:26",
        "host_name": "Plex Server",
        "ip_address": "192.168.10.10",
        "conn": 25161,
        "dns": 2753,
        "dns_blocked": 0,
        "ip_blocked": 1,
        "ip_denied": 0,
        "ntp": 74,
        "download_bytes": 1001430063,
        "upload_bytes": 3730817840,
    }
    assert first_view["top_download_hosts"][0] == {
        "host_id": "00:AA:BB:CC:DD:26",
        "host_name": "Plex Server",
        "ip_address": "192.168.10.10",
        "remote_host": "pkg-containers.githubusercontent.com",
        "remote_ip": "185.199.111.154",
        "value": 406504404,
    }
    assert first_view["top_upload_hosts"][0] == {
        "host_id": "0C:85:E1:B0:1D:1C",
        "host_name": "Office Phone",
        "ip_address": "192.168.10.44",
        "remote_host": "upload.example.net",
        "remote_ip": "203.0.113.50",
        "value": 133546109,
    }
    assert first_view["newLast24"][0]["metric"] == "conn"
    assert first_view["newLast24"][0]["samples"][0] == {
        "timestamp": 1_774_558_800,
        "timestamp_iso": "2026-03-26T21:00:00+00:00",
        "value": 5696,
    }
    assert first_view["last12Months"][0]["metric"] == "download"


async def test_get_network_interfaces_service_accepts_alternate_ranking_keys(
    hass: HomeAssistant,
) -> None:
    """Test network rankings tolerate alternate live payload field names."""
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
    payload = _network_interface_payload()
    payload["flows"] = {
        "download": [
            {
                "mac": "00:AA:BB:CC:DD:26",
                "deviceIP": "192.168.10.10",
                "domain": "pkg-containers.githubusercontent.com",
                "ip": "185.199.111.154",
                "download": 406504404,
            }
        ]
    }

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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=payload),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_INTERFACES,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["results"][0]["top_download_hosts"][0] == {
        "host_id": "00:AA:BB:CC:DD:26",
        "host_name": "Plex Server",
        "ip_address": "192.168.10.10",
        "remote_host": "pkg-containers.githubusercontent.com",
        "remote_ip": "185.199.111.154",
        "value": 406504404,
    }


async def test_get_network_interfaces_service_accepts_wrapped_ranking_lists(
    hass: HomeAssistant,
) -> None:
    """Test network rankings tolerate wrapper objects around ranking rows."""
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
    payload = _network_interface_payload()
    payload["flows"] = {
        "download": {
            "count": 1,
            "flows": [
                {
                    "device": "00:AA:BB:CC:DD:26",
                    "deviceIP": "192.168.10.10",
                    "host": "pkg-containers.githubusercontent.com",
                    "ip": "185.199.111.154",
                    "download": 406504404,
                    "count": 1,
                }
            ],
            "nextTs": 1_774_641_200,
        },
        "upload": {
            "count": 1,
            "flows": [
                {
                    "device": "0C:85:E1:B0:1D:1C",
                    "deviceIP": "192.168.10.44",
                    "host": "upload.example.net",
                    "ip": "203.0.113.50",
                    "upload": 133546109,
                    "count": 1,
                }
            ],
            "nextTs": 1_774_641_200,
        },
    }

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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_network_interface_payload",
            new=AsyncMock(return_value=payload),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NETWORK_INTERFACES,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_NETWORK_UUID: "5799d896-5e0f-40a5-a776-38a5d7746204",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    first_view = response["results"][0]
    assert first_view["top_download_hosts"][0] == {
        "host_id": "00:AA:BB:CC:DD:26",
        "host_name": "Plex Server",
        "ip_address": "192.168.10.10",
        "remote_host": "pkg-containers.githubusercontent.com",
        "remote_ip": "185.199.111.154",
        "value": 406504404,
    }
    assert first_view["top_upload_hosts"][0] == {
        "host_id": "0C:85:E1:B0:1D:1C",
        "host_name": "Office Phone",
        "ip_address": "192.168.10.44",
        "remote_host": "upload.example.net",
        "remote_ip": "203.0.113.50",
        "value": 133546109,
    }


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
    first_history_day = response["results"][0]["history_days"][0]
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
                SERVICE_FIELD_DETAIL: "daily",
                SERVICE_FIELD_WAN_UUID: "wan-1",
                SERVICE_FIELD_REFRESH: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["query"]["detail_applied_to"] == ["current_week", "history_weeks"]
    current_week = response["results"][0]["current_week"]
    assert current_week["time_period"]["begin_timestamp_iso"] == (
        "2025-06-09T00:00:00-04:00"
    )
    assert current_week["time_period"]["end_timestamp_iso"] == (
        "2025-06-16T00:00:00-04:00"
    )
    assert current_week["detail"] == "daily"
    assert len(current_week["days"]) == 2
    current_day = response["results"][0]["current_day"]
    assert current_day["time_period"]["begin_timestamp_iso"] == (
        "2025-06-10T00:00:00-04:00"
    )
    assert current_day["time_period"]["is_partial"] is True
    history_week = response["results"][0]["history_weeks"][0]
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
