"""Tests for Firewalla Local services."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
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
    SERVICE_FIELD_RULE_DURATION,
    SERVICE_FIELD_RULE_RESUME_AT,
    SERVICE_FIELD_RULE_TARGET,
    SERVICE_PAUSE_RULE,
    SERVICE_RESUME_RULE,
)
from custom_components.firewalla_local.models import (
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
    FirewallaSystemInfo,
)
from custom_components.firewalla_local.services import _get_loaded_entry


def _snapshot(enabled: bool = True) -> FirewallaRuntimeSnapshot:
    """Return one selected social-category rule snapshot."""
    return FirewallaRuntimeSnapshot(
        system_info=FirewallaSystemInfo(
            host="192.168.200.1",
            name="Firewalla",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="744",
                action="block",
                target="social",
                target_type="category",
                direction="bidirection",
                enabled=enabled,
                purpose=None,
                scope=(),
                tag_refs=("tag:17",),
                target_name="social",
                applies_to=("AV_SMART_TV",),
                dnsmasq_only=True,
                raw_update_payload={
                    "pid": "744",
                    "action": "block",
                    "target": "social",
                    "type": "category",
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
    return {"policyRules": []}


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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule",
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule",
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule",
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule",
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule",
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
