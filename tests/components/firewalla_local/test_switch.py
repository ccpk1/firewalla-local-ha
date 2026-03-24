"""Tests for the Firewalla Local rule-backed switch platform."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
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
)
from custom_components.firewalla_local.models import (
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    FirewallaRuntimeSnapshot,
    FirewallaSystemInfo,
)


def _snapshot_with_rule(
    rule_id: str | None,
    *,
    enabled: bool = True,
    idle_ts: str = "",
    notes: str = "",
) -> FirewallaRuntimeSnapshot:
    """Return a runtime snapshot with an optional AV_SMART_TV social rule."""
    policy_rules: tuple[FirewallaPolicyRule, ...]
    if rule_id is None:
        policy_rules = ()
    else:
        policy_rules = (
            FirewallaPolicyRule(
                rule_id=rule_id,
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
                    "pid": rule_id,
                    "action": "block",
                    "target": "social",
                    "type": "category",
                    "tag": ["tag:17"],
                    "dnsmasq_only": True,
                    "disabled": 0 if enabled else 1,
                    "idleTs": idle_ts,
                    "notes": notes,
                },
            ),
        )

    return FirewallaRuntimeSnapshot(
        system_info=FirewallaSystemInfo(
            host="192.168.200.1",
            name="Firewalla",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        policy_rules=policy_rules,
        exception_rule_count=0,
    )


async def test_selected_rule_switch_turns_rule_off_and_on(hass: HomeAssistant) -> None:
    """Test the switch disables and re-enables the matched persistent rule."""
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
            new=AsyncMock(
                side_effect=[
                    _snapshot_with_rule("744"),
                    _snapshot_with_rule("744", enabled=False),
                    _snapshot_with_rule("744", enabled=True),
                ]
            ),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule",
            new=AsyncMock(),
        ) as mock_update,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = next(iter(hass.states.async_entity_ids("switch")))
        assert entity_id.endswith("_744")
        assert hass.states.get(entity_id).state == "on"
        attributes = hass.states.get(entity_id).attributes
        assert attributes["rule_id"] == "744"
        assert attributes["matching_rule_count"] == 1
        assert attributes["backing_rule_present"] is True
        assert attributes["target"] == "social"
        assert attributes["target_type"] == "category"
        assert attributes["tag_refs"] == ["tag:17"]
        assert attributes["notes"] == []
        assert attributes["is_paused"] is False
        assert attributes["paused_rule_ids"] == []
        assert attributes["matched_rules"] == [
            {
                "rule_id": "744",
                "enabled": True,
                "notes": None,
                "is_paused": False,
                "pause_until": None,
                "pause_remaining_seconds": None,
            }
        ]
        assert attributes["icon"] == "mdi:shield-lock"

        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()

        mock_update.assert_awaited_once()
        updated_rule = mock_update.await_args.args[0]
        assert updated_rule.rule_id == "744"
        assert mock_update.await_args.kwargs == {"enabled": False}
        assert hass.states.get(entity_id).state == "off"

        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert mock_update.await_count == 2
        updated_rule = mock_update.await_args.args[0]
        assert updated_rule.rule_id == "744"
        assert mock_update.await_args.kwargs == {"enabled": True}
        assert hass.states.get(entity_id).state == "on"


async def test_selected_rule_switch_is_unavailable_when_rule_is_missing(
    hass: HomeAssistant,
) -> None:
    """Test the switch becomes unavailable when its backing rule is removed."""
    template = FirewallaRuleTemplate(
        source_rule_id="744",
        name="block category social for AV_SMART_TV",
        action="block",
        target="social",
        target_type="category",
        tag_refs=("tag:17",),
        dnsmasq_only=True,
    )
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
            CONF_SELECTED_RULE_TEMPLATES: [template.to_dict()],
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
        new=AsyncMock(return_value=_snapshot_with_rule(None)),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = next(iter(hass.states.async_entity_ids("switch")))
    assert hass.states.get(entity_id).state == "unavailable"


async def test_selected_rule_switch_exposes_pause_and_notes_attributes(
    hass: HomeAssistant,
) -> None:
    """Test switch attributes include notes and timed pause details."""
    template = FirewallaRuleTemplate(
        source_rule_id="744",
        name="block category social for AV_SMART_TV",
        action="block",
        target="social",
        target_type="category",
        tag_refs=("tag:17",),
        dnsmasq_only=True,
    )
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
            CONF_SELECTED_RULE_TEMPLATES: [template.to_dict()],
        },
    )
    entry.add_to_hass(hass)

    pause_until = datetime(2026, 3, 25, 12, 0, tzinfo=UTC).timestamp()
    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_snapshot",
            new=AsyncMock(
                return_value=_snapshot_with_rule(
                    "744",
                    enabled=False,
                    idle_ts=str(pause_until),
                    notes="Pause for maintenance",
                )
            ),
        ),
        patch(
            "custom_components.firewalla_local.models.time.time",
            return_value=pause_until - 600,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = next(iter(hass.states.async_entity_ids("switch")))
    attributes = hass.states.get(entity_id).attributes
    assert attributes["rule_id"] == "744"
    assert attributes["matching_rule_count"] == 1
    assert attributes["notes"] == ["Pause for maintenance"]
    assert attributes["is_paused"] is True
    assert attributes["paused_rule_ids"] == ["744"]
    assert attributes["matched_rules"] == [
        {
            "rule_id": "744",
            "enabled": False,
            "notes": "Pause for maintenance",
            "is_paused": True,
            "pause_until": pause_until,
            "pause_remaining_seconds": 600,
        }
    ]
