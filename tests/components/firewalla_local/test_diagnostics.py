"""Tests for Firewalla Local diagnostics."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from homeassistant.core import HomeAssistant

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
from custom_components.firewalla_local.coordinator import FirewallaConfigEntry
from custom_components.firewalla_local.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.firewalla_local.models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
)


def _snapshot() -> FirewallaRuntimeSnapshot:
    """Return a representative runtime snapshot for diagnostics tests."""
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
                rule_id="744",
                action="block",
                target="social",
                target_type="category",
                direction="bidirection",
                enabled=True,
                purpose=None,
                scope=(),
                tag_refs=("tag:17",),
                target_name="social",
            ),
        ),
        exception_rule_count=1,
    )


async def test_get_config_entry_diagnostics_redacts_entry_data(
    hass: HomeAssistant,
) -> None:
    """Test diagnostics redact sensitive config entry values."""
    entry = cast(
        FirewallaConfigEntry,
        SimpleNamespace(
            domain=DOMAIN,
            title="Firewalla",
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
                        "name": "block social",
                        "action": "block",
                        "target": "social",
                        "target_type": "category",
                        "scope": [],
                        "tag_refs": ["tag:17"],
                        "dnsmasq_only": None,
                        "use_bf": False,
                    }
                ],
            },
            runtime_data=SimpleNamespace(coordinator=SimpleNamespace(data=_snapshot())),
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    entry_data = cast(dict[str, str], diagnostics["entry_data"])

    assert entry_data == {
        CONF_LICENSE: "**REDACTED**",
        CONF_HOST: "**REDACTED**",
        CONF_GID: "**REDACTED**",
        CONF_EID: "**REDACTED**",
        CONF_AID: "**REDACTED**",
        CONF_SYMMETRIC_KEY: "**REDACTED**",
    }
    assert diagnostics["entry_options"] == {
        CONF_SELECTED_RULE_IDS: ["744"],
        CONF_SELECTED_RULE_TEMPLATES: [
            {
                "source_rule_id": "744",
                "name": "block social",
                "action": "block",
                "target": "social",
                "target_type": "category",
                "scope": [],
                "tag_refs": ["tag:17"],
                "dnsmasq_only": None,
                "use_bf": False,
            }
        ],
    }
    assert diagnostics["runtime_snapshot"] is not None


async def test_get_config_entry_diagnostics_handles_missing_snapshot(
    hass: HomeAssistant,
) -> None:
    """Test diagnostics return a null runtime snapshot when unavailable."""
    entry = cast(
        FirewallaConfigEntry,
        SimpleNamespace(
            domain=DOMAIN,
            title="Firewalla",
            data={CONF_LICENSE: "license-123"},
            options={},
            runtime_data=SimpleNamespace(coordinator=SimpleNamespace(data=None)),
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    entry_data = cast(dict[str, str], diagnostics["entry_data"])

    assert entry_data[CONF_LICENSE] == "**REDACTED**"
    assert diagnostics["entry_options"] == {}
    assert diagnostics["runtime_snapshot"] is None
