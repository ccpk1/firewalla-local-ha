"""Tests for the Firewalla Local rule-backed switch platform."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import (
    ATTR_INTEGRATION,
    ATTR_RULE_ACTION,
    ATTR_RULE_APPLIES_TO,
    ATTR_RULE_APPLIES_TO_KIND,
    ATTR_RULE_CATEGORY,
    ATTR_RULE_CURRENT_STATE_REASON,
    ATTR_RULE_CUSTOM_NAME,
    ATTR_RULE_ID,
    ATTR_RULE_IS_PAUSED,
    ATTR_RULE_NAME,
    ATTR_RULE_NOTES,
    ATTR_RULE_PAUSE_REMAINING_SECONDS,
    ATTR_RULE_PAUSE_UNTIL,
    ATTR_RULE_PURPOSE,
    ATTR_RULE_SCHEDULE_DAYS,
    ATTR_RULE_SCHEDULE_DURATION,
    ATTR_RULE_SCHEDULE_NEXT_END,
    ATTR_RULE_SCHEDULE_NEXT_START,
    ATTR_RULE_SCHEDULE_START_CRON,
    ATTR_RULE_TIME_LIMIT_PERIOD_CRON,
    ATTR_RULE_TIME_LIMIT_QUOTA,
    ATTR_RULE_TIME_LIMIT_USED,
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    CONF_SYMMETRIC_KEY,
    DOMAIN,
    RULE_STATE_REASON_ENABLED,
    RULE_STATE_REASON_ON_SCHEDULE,
    RULE_STATE_REASON_PAUSED,
    TRANS_KEY_PURPOSE_RULE_SWITCH,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    FirewallaRuntimeSnapshot,
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


def _visible_attribute_keys(attributes: dict[str, object]) -> list[str]:
    """Return switch attribute keys without Home Assistant's friendly name."""
    return [key for key in attributes if key != "friendly_name"]


def _snapshot_with_rule(
    rule_id: str | None,
    *,
    enabled: bool = True,
    idle_ts: str = "",
    notes: str = "",
    target: str = "social",
    target_type: str = "category",
    target_name: str | None = "social",
    applies_to: tuple[str, ...] = ("AV_SMART_TV",),
    applies_to_kind: tuple[str, ...] = ("device",),
    tag_refs: tuple[str, ...] = ("tag:17",),
    dnsmasq_only: bool | None = True,
    auto_delete_when_expires: bool | None = None,
    raw_update_overrides: dict[str, object] | None = None,
) -> FirewallaRuntimeSnapshot:
    """Return a runtime snapshot with an optional AV_SMART_TV social rule."""
    policy_rules: tuple[FirewallaPolicyRule, ...]
    if rule_id is None:
        policy_rules = ()
    else:
        raw_update_payload = {
            "pid": rule_id,
            "action": "block",
            "target": target,
            "type": target_type,
            "tag": list(tag_refs),
            "dnsmasq_only": dnsmasq_only,
            "disabled": 0 if enabled else 1,
            "idleTs": idle_ts,
            "notes": notes,
        }
        if raw_update_overrides:
            raw_update_payload.update(raw_update_overrides)
        policy_rules = (
            FirewallaPolicyRule(
                rule_id=rule_id,
                action="block",
                target=target,
                target_type=target_type,
                direction="bidirection",
                enabled=enabled,
                purpose=None,
                scope=(),
                tag_refs=tag_refs,
                target_name=target_name,
                applies_to=applies_to,
                applies_to_kind=applies_to_kind,
                auto_delete_when_expires=auto_delete_when_expires,
                dnsmasq_only=dnsmasq_only,
                raw_update_payload=raw_update_payload,
            ),
        )

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
        policy_rules=policy_rules,
        exception_rule_count=0,
        hosts=(_box_host(),),
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

        assert state is not None
        assert state.name == "Firewalla block category social for AV_SMART_TV"
        assert entity_entry is not None
        assert entity_entry.unique_id.endswith("_744_switch")
        assert state.state == "on"
        attributes = state.attributes
        assert attributes[ATTR_RULE_PURPOSE] == TRANS_KEY_PURPOSE_RULE_SWITCH
        assert attributes[ATTR_INTEGRATION] == DOMAIN
        assert attributes[ATTR_RULE_ID] == "744"
        assert attributes[ATTR_RULE_NAME] == "block category social for AV_SMART_TV"
        assert attributes[ATTR_RULE_APPLIES_TO] == ["AV_SMART_TV"]
        assert attributes[ATTR_RULE_APPLIES_TO_KIND] == ["device"]
        assert next(iter(attributes)) == ATTR_RULE_PURPOSE
        assert _visible_attribute_keys(attributes) == [
            ATTR_RULE_PURPOSE,
            ATTR_INTEGRATION,
            ATTR_RULE_ID,
            ATTR_RULE_NAME,
            ATTR_RULE_APPLIES_TO,
            ATTR_RULE_APPLIES_TO_KIND,
            ATTR_RULE_ACTION,
            ATTR_RULE_IS_PAUSED,
            ATTR_RULE_CURRENT_STATE_REASON,
        ]
        assert "source_rule_id" not in attributes
        assert "backing_rule_present" not in attributes
        assert attributes[ATTR_RULE_ACTION] == "block"
        assert attributes[ATTR_RULE_IS_PAUSED] is False
        assert attributes[ATTR_RULE_CURRENT_STATE_REASON] == RULE_STATE_REASON_ENABLED

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


async def test_selected_rule_switch_uses_live_custom_name(
    hass: HomeAssistant,
) -> None:
    """Test the switch name adopts the live custom rule name."""
    live_rule = FirewallaPolicyRule(
        rule_id="772",
        action="allow",
        target="choreops.com",
        target_type="dns",
        direction="bidirection",
        enabled=True,
        purpose=None,
        scope=(),
        tag_refs=("tag:17",),
        applies_to=("AV_SMART_TV",),
        applies_to_kind=("device",),
        category="social",
        raw_update_payload={
            "pid": "772",
            "action": "allow",
            "target": "choreops.com",
            "type": "dns",
            "tag": ["tag:17"],
            "disabled": 0,
            "_name": "ChoreOps Custom Allow",
        },
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
            CONF_SELECTED_RULE_IDS: ["772"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "772",
                    "name": "allow dns choreops.com for AV_SMART_TV",
                    "action": "allow",
                    "target": "choreops.com",
                    "target_type": "dns",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": False,
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
            return_value=FirewallaRuntimeSnapshot(
                appliance_identity=FirewallaApplianceIdentityInput(
                    host="192.168.200.1",
                    group_name="Firewalla",
                    device_name=None,
                    model="gold",
                    serial_number="serial-123",
                    software_version="1.0.0",
                ),
                appliance_runtime=FirewallaApplianceRuntimeInput(),
                policy_rules=(live_rule,),
                exception_rule_count=0,
                hosts=(_box_host(),),
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = next(iter(hass.states.async_entity_ids("switch")))
    state = hass.states.get(entity_id)

    assert state is not None
    assert state.name == "Firewalla ChoreOps Custom Allow"
    assert state.attributes[ATTR_INTEGRATION] == DOMAIN
    assert state.attributes[ATTR_RULE_APPLIES_TO] == ["AV_SMART_TV"]
    assert state.attributes[ATTR_RULE_APPLIES_TO_KIND] == ["device"]
    assert state.attributes[ATTR_RULE_CATEGORY] == "social"
    assert ATTR_RULE_CUSTOM_NAME not in state.attributes


async def test_selected_rule_switch_name_updates_after_rule_rename(
    hass: HomeAssistant,
) -> None:
    """Test selected-rule friendly names track live rule renames after refresh."""
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
            CONF_SELECTED_RULE_IDS: ["772"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "772",
                    "name": "allow dns choreops.com for AV_SMART_TV",
                    "action": "allow",
                    "target": "choreops.com",
                    "target_type": "dns",
                    "scope": [],
                    "tag_refs": ["tag:17"],
                    "dnsmasq_only": False,
                    "use_bf": True,
                }
            ],
        },
    )
    entry.add_to_hass(hass)

    initial_rule = FirewallaPolicyRule(
        rule_id="772",
        action="allow",
        target="choreops.com",
        target_type="dns",
        direction="bidirection",
        enabled=True,
        purpose=None,
        scope=(),
        tag_refs=("tag:17",),
        applies_to=("AV_SMART_TV",),
        raw_update_payload={
            "pid": "772",
            "action": "allow",
            "target": "choreops.com",
            "type": "dns",
            "tag": ["tag:17"],
            "disabled": 0,
            "_name": "ChoreOps Custom Allow",
        },
    )
    renamed_rule = FirewallaPolicyRule(
        rule_id="772",
        action="allow",
        target="choreops.com",
        target_type="dns",
        direction="bidirection",
        enabled=True,
        purpose=None,
        scope=(),
        tag_refs=("tag:17",),
        applies_to=("AV_SMART_TV",),
        raw_update_payload={
            "pid": "772",
            "action": "allow",
            "target": "choreops.com",
            "type": "dns",
            "tag": ["tag:17"],
            "disabled": 0,
            "_name": "ChoreOps Family Allow",
        },
    )

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            side_effect=[
                FirewallaRuntimeSnapshot(
                    appliance_identity=FirewallaApplianceIdentityInput(
                        host="192.168.200.1",
                        group_name="Firewalla",
                        device_name=None,
                        model="gold",
                        serial_number="serial-123",
                        software_version="1.0.0",
                    ),
                    appliance_runtime=FirewallaApplianceRuntimeInput(),
                    policy_rules=(initial_rule,),
                    exception_rule_count=0,
                    hosts=(_box_host(),),
                ),
                FirewallaRuntimeSnapshot(
                    appliance_identity=FirewallaApplianceIdentityInput(
                        host="192.168.200.1",
                        group_name="Firewalla",
                        device_name=None,
                        model="gold",
                        serial_number="serial-123",
                        software_version="1.0.0",
                    ),
                    appliance_runtime=FirewallaApplianceRuntimeInput(),
                    policy_rules=(renamed_rule,),
                    exception_rule_count=0,
                    hosts=(_box_host(),),
                ),
            ],
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = next(iter(hass.states.async_entity_ids("switch")))
        initial_state = hass.states.get(entity_id)
        assert initial_state is not None
        assert initial_state.name == "Firewalla ChoreOps Custom Allow"

        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()

    renamed_state = hass.states.get(entity_id)
    assert renamed_state is not None
    assert renamed_state.name == "Firewalla ChoreOps Family Allow"


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
    assert attributes[ATTR_INTEGRATION] == DOMAIN
    assert attributes[ATTR_RULE_ID] == "744"
    assert attributes[ATTR_RULE_APPLIES_TO] == ["AV_SMART_TV"]
    assert attributes[ATTR_RULE_APPLIES_TO_KIND] == ["device"]
    assert attributes[ATTR_RULE_ACTION] == "block"
    assert attributes[ATTR_RULE_NOTES] == "Pause for maintenance"
    assert attributes[ATTR_RULE_IS_PAUSED] is True
    assert attributes[ATTR_RULE_PAUSE_UNTIL] == "2026-03-25T12:00:00+00:00"
    assert attributes[ATTR_RULE_PAUSE_REMAINING_SECONDS] == 600
    assert attributes[ATTR_RULE_CURRENT_STATE_REASON] == RULE_STATE_REASON_PAUSED


async def test_selected_rule_switch_exposes_schedule_and_time_limit_attributes(
    hass: HomeAssistant,
) -> None:
    """Test switch attributes expose the user-facing schedule and time limit view."""
    await hass.config.async_set_time_zone("America/New_York")

    template = FirewallaRuleTemplate(
        source_rule_id="765",
        name="block internet for KADEN's Devices (KADEN)",
        action="block",
        target="TAG",
        target_type="mac",
        tag_refs=("tag:10",),
        dnsmasq_only=False,
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
            CONF_SELECTED_RULE_IDS: ["765"],
            CONF_SELECTED_RULE_TEMPLATES: [template.to_dict()],
        },
    )
    entry.add_to_hass(hass)

    reference_now = datetime(2026, 3, 26, 4, 14, 30, tzinfo=UTC).timestamp()

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient.build_runtime_snapshot",
            return_value=_snapshot_with_rule(
                "765",
                target="TAG",
                target_type="mac",
                target_name="KADEN's Devices (KADEN)",
                applies_to=("KADEN's Devices (KADEN)",),
                tag_refs=("tag:10",),
                dnsmasq_only=False,
                auto_delete_when_expires=True,
                raw_update_overrides={
                    "cronTime": "0 21 * * *",
                    "duration": "36000",
                    "appTimeUsage": {
                        "app": "internet",
                        "quota": 225,
                        "apps": ["internet"],
                        "period": "0 0 * * *",
                        "uniqueMinute": True,
                    },
                    "appTimeUsed": 62,
                    "autoDeleteWhenExpires": "1",
                },
            ),
        ),
        patch(
            "custom_components.firewalla_local.models.time.time",
            return_value=reference_now,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = next(iter(hass.states.async_entity_ids("switch")))
    attributes = hass.states.get(entity_id).attributes
    assert attributes[ATTR_RULE_ID] == "765"
    assert attributes[ATTR_RULE_ACTION] == "block"
    assert attributes[ATTR_RULE_SCHEDULE_START_CRON] == "0 21 * * *"
    assert attributes[ATTR_RULE_SCHEDULE_DURATION] == 36000
    assert attributes[ATTR_RULE_SCHEDULE_DAYS] == [
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
    ]
    assert attributes[ATTR_RULE_SCHEDULE_NEXT_START] == "2026-03-26T21:00:00-04:00"
    assert attributes[ATTR_RULE_SCHEDULE_NEXT_END] == "2026-03-26T07:00:00-04:00"
    assert attributes[ATTR_RULE_TIME_LIMIT_PERIOD_CRON] == "0 0 * * *"
    assert attributes[ATTR_RULE_TIME_LIMIT_QUOTA] == 225
    assert attributes[ATTR_RULE_TIME_LIMIT_USED] == 62
    assert attributes[ATTR_RULE_CURRENT_STATE_REASON] == RULE_STATE_REASON_ON_SCHEDULE


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
