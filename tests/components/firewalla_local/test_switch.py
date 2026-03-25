"""Tests for the Firewalla Local rule-backed switch platform."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import (
    ATTR_RULE_ID,
    ATTR_RULE_IS_PAUSED,
    ATTR_RULE_NOTES,
    ATTR_RULE_PAUSE_UNTIL,
    ATTR_RULE_PURPOSE,
    ATTR_RULE_TAG_REFS,
    ATTR_RULE_TARGET_TYPE,
    ATTR_RULE_TEMPLATE_TARGET,
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    CONF_SYMMETRIC_KEY,
    DOMAIN,
    TRANS_KEY_PURPOSE_RULE_SWITCH,
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


def _runtime_payload() -> dict[str, object]:
    """Return a minimal raw init payload for coordinator setup tests."""
    return {"policyRules": []}


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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(
                side_effect=[
                    _runtime_payload(),
                    _runtime_payload(),
                    _runtime_payload(),
                ]
            ),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=[
                _snapshot_with_rule("744"),
                _snapshot_with_rule("744", enabled=False),
                _snapshot_with_rule("744", enabled=True),
            ],
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_update_rule",
            new=AsyncMock(),
        ) as mock_update,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = next(iter(hass.states.async_entity_ids("switch")))
        state = hass.states.get(entity_id)
        registry = er.async_get(hass)
        entity_entry = registry.async_get(entity_id)

        assert entity_id.endswith("block_category_social_for_av_smart_tv")
        assert state is not None
        assert state.name == "Firewalla block category social for AV_SMART_TV"
        assert entity_entry is not None
        assert entity_entry.unique_id.endswith("_744_switch")
        assert state.state == "on"
        attributes = state.attributes
        assert attributes[ATTR_RULE_PURPOSE] == TRANS_KEY_PURPOSE_RULE_SWITCH
        assert attributes[ATTR_RULE_ID] == "744"
        assert next(iter(attributes)) == ATTR_RULE_PURPOSE
        assert "source_rule_id" not in attributes
        assert "backing_rule_present" not in attributes
        assert attributes[ATTR_RULE_TEMPLATE_TARGET] == "social"
        assert attributes[ATTR_RULE_TARGET_TYPE] == "category"
        assert attributes[ATTR_RULE_TAG_REFS] == ["tag:17"]
        assert attributes[ATTR_RULE_NOTES] == []
        assert attributes[ATTR_RULE_IS_PAUSED] is False
        assert attributes[ATTR_RULE_PAUSE_UNTIL] is None

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

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_rule(None),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = next(iter(hass.states.async_entity_ids("switch")))
    assert hass.states.get(entity_id).state == "unavailable"


async def test_selected_rule_switch_does_not_guess_replacement_rule(
    hass: HomeAssistant,
) -> None:
    """Test the switch stays unavailable when only a new equivalent rule exists."""
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

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_rule("999"),
        ),
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
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_rule(
                "744",
                enabled=False,
                idle_ts=str(pause_until),
                notes="Pause for maintenance",
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
    assert attributes[ATTR_RULE_PURPOSE] == TRANS_KEY_PURPOSE_RULE_SWITCH
    assert attributes[ATTR_RULE_ID] == "744"
    assert attributes[ATTR_RULE_NOTES] == ["Pause for maintenance"]
    assert attributes[ATTR_RULE_IS_PAUSED] is True
    assert attributes[ATTR_RULE_PAUSE_UNTIL] == "2026-03-25T12:00:00+00:00"


async def test_deselecting_all_rules_removes_switch_entities(
    hass: HomeAssistant,
) -> None:
    """Test deselected rule switches are removed from state and registry."""
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
            return_value=_snapshot_with_rule("744"),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = next(iter(hass.states.async_entity_ids("switch")))
        entity_registry = er.async_get(hass)
        assert entity_registry.async_get(entity_id) is not None

        hass.config_entries.async_update_entry(
            entry,
            options={
                CONF_SELECTED_RULE_IDS: [],
                CONF_SELECTED_RULE_TEMPLATES: [],
            },
        )
        await hass.async_block_till_done()

    assert not list(hass.states.async_entity_ids("switch"))
    assert entity_registry.async_get(entity_id) is None
