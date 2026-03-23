"""Config flow for Firewalla."""

from __future__ import annotations

from typing import Any, Self

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST

from .const import DOMAIN


def _normalize_host(host: str) -> str:
    """Normalize host input for storage and duplicate detection."""
    return host.strip().lower()


class FirewallaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Firewalla."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.host: str | None = None

    def is_matching(self, other_flow: Self) -> bool:
        """Return True if another flow targets the same host."""
        return other_flow.host == self.host

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            self.host = host
            self._async_abort_entries_match({CONF_HOST: host})
            return self.async_create_entry(
                title=f"Firewalla {host}",
                data={CONF_HOST: host},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            self.host = host
            entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(
                entry,
                data_updates={CONF_HOST: host},
            )

        entry = self._get_reconfigure_entry()
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str}
            ),
        )
