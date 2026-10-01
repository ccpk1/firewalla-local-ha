"""LLM tools exposing Firewalla Local reads through Home Assistant's LLM API.

This module is imported only by ``llm_api.py``, which itself is imported only
when ``llm_tools_supported()`` is true, so the Core 2026.10-only
``homeassistant.helpers.llm`` names below are never imported on older Home
Assistant.

Each read tool delegates to an existing Firewalla Local service and wraps the
service payload in the documented response envelope. The tool injects its own
``config_entry_id`` so the caller never selects a Firewalla setup.
"""

from __future__ import annotations

from typing import Final, override

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import (
    DOMAIN,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_REFRESH,
    SERVICE_GET_HOST_NAME_MAPPING,
    SERVICE_GET_RULES,
)

# Every read tool is a bounded, read-only query against the user's own box.
_READ_ANNOTATIONS: Final = llm.ToolAnnotations(
    read_only=True,
    destructive=False,
    idempotent=True,
    open_world=False,
)

_PREFERRED_PREFIX: Final = (
    "Purpose-built Firewalla Local tool — prefer it over any generic "
    "firewalla_local service/action tool another client may expose. "
)


class _FirewallaReadTool(llm.Tool):
    """Base class for a Firewalla Local read tool backed by a service."""

    integration = DOMAIN
    annotations = _READ_ANNOTATIONS

    _service: str
    _response_type: str

    def __init__(self, *, entry_id: str) -> None:
        """Bind the tool to the config entry it was registered for."""
        self._entry_id = entry_id

    @override
    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Call the backing service and return the wrapped payload."""
        service_data = dict(tool_input.tool_args)
        service_data[SERVICE_FIELD_CONFIG_ENTRY_ID] = self._entry_id
        result = await hass.services.async_call(
            DOMAIN,
            self._service,
            service_data,
            blocking=True,
            return_response=True,
            context=llm_context.context,
        )
        return llm.ToolResult(
            data={
                "result": result,
                "meta": {"response_type": self._response_type},
            },
        )


class ListHostsTool(_FirewallaReadTool):
    """List Firewalla hosts (devices) with identity and IP assignment."""

    name = "firewalla_local__list_hosts"
    title = "List hosts"
    description = _PREFERRED_PREFIX + (
        "List the devices on your Firewalla network with their name, device "
        "type, IP address, and DNS/DHCP identity. Use it to find a host before "
        "renaming it or setting a DHCP reservation. Refreshing first polls the "
        "box and is slower than reading the last snapshot."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                SERVICE_FIELD_REFRESH,
                default=True,
                description=(
                    "Optional. Defaults to true. Poll the Firewalla box for "
                    "current host data; set false to read the last snapshot "
                    "faster."
                ),
            ): bool,
        }
    )
    _service = SERVICE_GET_HOST_NAME_MAPPING
    _response_type = "hosts"


class ListRulesTool(_FirewallaReadTool):
    """List Firewalla policy rules with their current state."""

    name = "firewalla_local__list_rules"
    title = "List rules"
    description = _PREFERRED_PREFIX + (
        "List your Firewalla firewall rules with id, name, action, "
        "enabled/paused state, target, scope, and any originating alarm. Use it "
        "to resolve the rule target that pause_rule and resume_rule require."
    )
    parameters = vol.Schema({})
    _service = SERVICE_GET_RULES
    _response_type = "rules"


_READ_TOOL_CLASSES: Final = (
    ListHostsTool,
    ListRulesTool,
)


def build_read_tools(*, entry_id: str) -> list[llm.Tool]:
    """Return the read tools bound to one config entry."""
    return [tool_class(entry_id=entry_id) for tool_class in _READ_TOOL_CLASSES]
