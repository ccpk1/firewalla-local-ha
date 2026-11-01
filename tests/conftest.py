"""Pytest configuration for Firewalla custom integration tests."""

# pylint: disable=invalid-name

from __future__ import annotations

from typing import Any

import pytest

from custom_components.firewalla_local.helpers.llm_support import (
    llm_tools_supported,
)

pytest_plugins = "pytest_homeassistant_custom_component"

# The tool surface only exists on Core 2026.10 and newer: it needs
# `llm.ToolResult`, `llm.ToolAnnotations` and `Tool.integration`, and probatio,
# which replaced voluptuous in the same release. These modules import those names
# at module level, so on older Core they cannot even be imported, and a skip
# marker would be too late — `collect_ignore` keeps them out of collection.
_LLM_TEST_MODULES = (
    "test_llm_contract.py",
    "test_llm_control.py",
    "test_llm_errors.py",
    "test_llm_support.py",
    "test_llm_tools.py",
)

collect_ignore = [
    f"components/firewalla_local/{module}"
    for module in _LLM_TEST_MODULES
    if not llm_tools_supported()
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable custom integrations for all tests."""
    del enable_custom_integrations
    return None


def pytest_report_collectionfinish(
    config: pytest.Config, start_path: Any, items: list[pytest.Item]
) -> str | None:
    """Say why the tool-surface tests are missing, rather than just omitting them."""
    del config, start_path, items
    if llm_tools_supported():
        return None
    return (
        f"{len(_LLM_TEST_MODULES)} LLM/MCP test modules not collected: the tool "
        "surface requires Home Assistant 2026.10 or newer"
    )
