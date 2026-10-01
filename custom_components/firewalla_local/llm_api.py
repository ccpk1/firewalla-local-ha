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
from homeassistant.util import slugify

from .const import DOMAIN, LLM_TOOL_MODE_FULL, LLM_TOOL_MODE_READ_AND_CONTROL
from .coordinator import get_llm_tool_mode
from .llm_prompt import PROMPT
from .llm_tools_control import build_control_tools
from .llm_tools_read import build_read_tools


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


def _resolve_api_id(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Return a unique LLM API id for one config entry.

    The common case is a single Firewalla setup, which gets the bare domain as a
    clean, pasteable MCP URL. Beyond that the slugified entry title disambiguates,
    with the entry id as a collision fallback. Ids are decided from the entries
    present at registration time and are not reshuffled live.
    """
    registered = {api.id for api in llm.async_get_apis(hass)}
    if len(hass.config_entries.async_entries(DOMAIN)) <= 1:
        return DOMAIN if DOMAIN not in registered else f"{DOMAIN}-{entry.entry_id[:8]}"

    candidate = f"{DOMAIN}-{slugify(entry.title) or entry.entry_id[:8]}"
    if candidate not in registered:
        return candidate
    return f"{DOMAIN}-{entry.entry_id[:8]}"


def async_register_firewalla_api(
    hass: HomeAssistant, entry: ConfigEntry
) -> Callable[[], None]:
    """Register the Firewalla Local LLM API for one config entry."""
    api = FirewallaLocalAPI(
        hass,
        api_id=_resolve_api_id(hass, entry),
        name=entry.title,
        entry_id=entry.entry_id,
        mode=get_llm_tool_mode(entry.options),
    )
    return llm.async_register_api(hass, api)
