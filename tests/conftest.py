"""Pytest configuration for Firewalla custom integration tests."""

# pylint: disable=invalid-name

from __future__ import annotations

from typing import Any

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable custom integrations for all tests."""
    del enable_custom_integrations
    return None
