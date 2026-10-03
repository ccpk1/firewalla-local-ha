"""Version support checks for the LLM/MCP tool surface."""

from __future__ import annotations

from homeassistant.const import MAJOR_VERSION, MINOR_VERSION

from ..const import MIN_LLM_TOOLS_HA_VERSION


def llm_tools_supported() -> bool:
    """Return whether this Home Assistant version supports LLM tools.

    LLM tool registration needs the Core 2026.10 contract (``llm.ToolResult``,
    ``llm.ToolAnnotations``, ``Tool.integration``). On older Core nothing is
    registered and the integration loads normally.
    """
    return (MAJOR_VERSION, MINOR_VERSION) >= MIN_LLM_TOOLS_HA_VERSION
