"""Tests for Firewalla Local setup."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.const import DOMAIN


async def test_setup_entry(hass: HomeAssistant) -> None:
    """Test setting up the scaffold entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla Local firewalla.local",
        data={CONF_HOST: "firewalla.local"},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime_data = entry.runtime_data
    assert runtime_data.client.host == "firewalla.local"
    assert runtime_data.coordinator.data is not None
    assert runtime_data.coordinator.data.host == "firewalla.local"
