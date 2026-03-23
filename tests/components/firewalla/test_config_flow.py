"""Tests for the Firewalla config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla.const import DOMAIN


async def test_user_flow_creates_entry(hass) -> None:
    """Test the user flow creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "firewalla.local"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Firewalla firewalla.local"
    assert result["data"] == {CONF_HOST: "firewalla.local"}


async def test_duplicate_host_aborts(hass) -> None:
    """Test duplicate hosts are rejected."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla firewalla.local",
        data={CONF_HOST: "firewalla.local"},
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_HOST: "firewalla.local"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
