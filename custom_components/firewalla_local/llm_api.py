"""LLM API exposing Firewalla Local data and controls to assistants.

This module is imported only when ``llm_tools_supported()`` is true, so the
Core 2026.10-only ``homeassistant.helpers.llm`` names below are never imported
on older Home Assistant. Do not rename this module to ``llm.py`` — that is
Home Assistant's LLM integration-platform filename and is auto-imported by the
``llm`` integration outside this integration's version guard.
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import (
    DOMAIN,
    LLM_TOOL_MODE_FULL,
    LLM_TOOL_MODE_READ_AND_CONTROL,
    LLM_TOOL_MODE_SUMMARY_ONLY,
)
from .coordinator import get_llm_tool_mode
from .llm_tools_common import PROMPT
from .llm_tools_control import build_control_tools
from .llm_tools_read import build_anonymous_tools, build_read_tools


class FirewallaLocalAPI(llm.API):
    """LLM API owned by the Firewalla Local integration.

    Registered once per config entry. Read tools are exposed by default; control
    tools are added in a later phase and gated by the options toggle.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        api_id: str,
        name: str,
        entry_id: str,
        mode: str,
    ) -> None:
        """Initialize the API."""
        super().__init__(hass=hass, id=api_id, name=name)
        self._entry_id = entry_id
        self._mode = mode

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return the API instance for one LLM request."""
        if self._mode == LLM_TOOL_MODE_SUMMARY_ONLY:
            # Capability removal, not filtering: the other tools are not
            # registered at all in this tier, so there is nothing to redact.
            tools = build_anonymous_tools(entry_id=self._entry_id)
        else:
            tools = build_read_tools(entry_id=self._entry_id)
            if self._mode in (LLM_TOOL_MODE_READ_AND_CONTROL, LLM_TOOL_MODE_FULL):
                tools.extend(
                    build_control_tools(
                        entry_id=self._entry_id,
                        include_destructive=self._mode == LLM_TOOL_MODE_FULL,
                    )
                )
        return llm.APIInstance(
            api=self,
            api_prompt=PROMPT,
            llm_context=llm_context,
            tools=tools,
        )


def _resolve_api_name(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Return a display name unique among this integration's entries.

    Home Assistant derives a merged tool's namespace from the API *name*
    (`MergedAPI` prefixes tools with the slugified name), and it only enforces
    uniqueness of ids, not names. Two entries the user has titled identically
    would therefore produce two identically-named tools, leaving the model no
    way to tell which box it is acting on.

    The discriminator is decided from the config entries themselves rather than
    from what is currently registered, so every entry reaches the same verdict
    regardless of registration order and the names do not move on reload.
    """
    title = entry.title
    others = [
        other
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ]
    if not any(other.title == title for other in others):
        return title
    return f"{title} [{entry.entry_id[:6]}]"


def async_register_firewalla_api(
    hass: HomeAssistant, entry: ConfigEntry
) -> Callable[[], None]:
    """Register the Firewalla Local LLM API for one config entry."""
    api = FirewallaLocalAPI(
        hass,
        # The config entry id is the box's stable identity: assigned by Home
        # Assistant, never reissued, and unaffected by a rename or by another
        # entry appearing. This id is both the MCP URL and the value
        # `mcp_server` stores to select an API, so it must not move.
        api_id=f"{DOMAIN}-{entry.entry_id}",
        # The title is the display name only, so renaming changes what users
        # see without moving the id.
        name=_resolve_api_name(hass, entry),
        entry_id=entry.entry_id,
        mode=get_llm_tool_mode(entry.options),
    )
    return llm.async_register_api(hass, api)
