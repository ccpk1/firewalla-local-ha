"""Tests for Firewalla Local services."""

from __future__ import annotations

# pylint: disable=too-many-lines
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

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
    SERVICE_FIELD_LIMIT,
    SERVICE_FIELD_REFRESH,
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_FIELD_WAN_NAME,
    SERVICE_FIELD_WAN_UUID,
    SERVICE_GET_SPEED_TEST_RESULTS,
    SERVICE_GET_WAN_USAGE,
    SERVICE_GET_WAN_USAGE_HISTORY,
    SERVICE_PAUSE_RULE,
    SERVICE_RESUME_RULE,
    SERVICE_RUN_INTERNET_SPEED_TEST,
)
from custom_components.firewalla_local.coordinator import FirewallaRuntimeData
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
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
        "policyRules": [],
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
                "ts": 1_740_996_000,
                "stats": {
                    "download": [[1_740_996_000, 8192]],
                    "upload": [[1_740_996_000, 4096]],
                    "totalDownload": 8192,
                    "totalUpload": 4096,
                },
            },
            {
                "ts": 1_743_675_200,
                "stats": {
                    "download": [[1_743_675_200, 16384]],
                    "upload": [[1_743_675_200, 6144]],
                    "totalDownload": 16384,
                    "totalUpload": 6144,
                },
            },
        ],
        "wan-2": [
            {
                "ts": 1_743_675_200,
                "stats": {
                    "download": [[1_743_675_200, 2048]],
                    "upload": [[1_743_675_200, 1024]],
                    "totalDownload": 2048,
                    "totalUpload": 1024,
                },
            }
        ],
    }


def _speed_test_snapshot() -> FirewallaRuntimeSnapshot:
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
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(),
        exception_rule_count=0,
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


async def test_get_wan_usage_service_returns_current_month_view(
    hass: HomeAssistant,
) -> None:
    """Test the current WAN usage service returns the coordinator-backed view."""
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
            SERVICE_GET_WAN_USAGE,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
            return_response=True,
        )

    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["refreshed"] is True
    assert response["wan"] is None
    assert response["count"] == 2
    first_view = response["results"][0]
    assert first_view["wan_uuid"] == "wan-1"
    assert first_view["wan_name"] == "WAN-ONE"
    assert first_view["periods"][0]["total_download_bytes"] == 3072
    assert (
        first_view["periods"][0]["begin_timestamp_iso"] == "2025-03-30T00:00:00+00:00"
    )
    assert first_view["periods"][0]["end_timestamp_iso"] == "2025-04-29T23:59:59+00:00"
    assert first_view["periods"][0]["download_samples"][0] == {
        "timestamp": 1_743_480_000,
        "timestamp_iso": "2025-04-01T04:00:00+00:00",
        "value": 1024,
    }


async def test_get_wan_usage_history_service_filters_one_wan_without_refresh(
    hass: HomeAssistant,
) -> None:
    """Test the WAN history service returns the direct-read view for one WAN."""
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
            SERVICE_GET_WAN_USAGE_HISTORY,
            {
                SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id,
                SERVICE_FIELD_WAN_UUID: "wan-1",
            },
            blocking=True,
            return_response=True,
        )

    assert mock_get_history.await_count == 1
    assert response is not None
    assert response["config_entry_id"] == entry.entry_id
    assert response["wan"] == {"uuid": "wan-1", "name": "WAN-ONE"}
    assert response["count"] == 1
    first_period = response["results"][0]["periods"][0]
    assert first_period["bucket_timestamp"] == 1_740_996_000
    assert first_period["bucket_timestamp_iso"] == "2025-03-03T10:00:00+00:00"
    assert first_period["begin_timestamp"] == 1_740_996_000
    assert first_period["begin_timestamp_iso"] == "2025-03-03T10:00:00+00:00"
    assert first_period["end_timestamp"] == 1_740_996_000
    assert first_period["end_timestamp_iso"] == "2025-03-03T10:00:00+00:00"
    assert first_period["total_download_bytes"] == 8192
    assert first_period["upload_samples"][0] == {
        "timestamp": 1_740_996_000,
        "timestamp_iso": "2025-03-03T10:00:00+00:00",
        "value": 4096,
    }
