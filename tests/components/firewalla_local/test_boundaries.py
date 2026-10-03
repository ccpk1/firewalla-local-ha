"""Architecture boundary tests for Firewalla Local."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[3] / "custom_components" / "firewalla_local"
)


def _python_files() -> list[Path]:
    """Return integration Python files excluding tests and caches."""
    return [
        path for path in PACKAGE_ROOT.rglob("*.py") if "__pycache__" not in path.parts
    ]


def _imported_modules(path: Path) -> set[str]:
    """Return every module name imported by one file.

    Parsed rather than matched textually so a module mentioned in a docstring or
    a comment is not mistaken for a real import.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _offenders_with_homeassistant_import(layer: str) -> list[str]:
    """Return files in one layer that import Home Assistant."""
    return [
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in (PACKAGE_ROOT / layer).rglob("*.py")
        if "__pycache__" not in path.parts
        and any(
            module == "homeassistant" or module.startswith("homeassistant.")
            for module in _imported_modules(path)
        )
    ]


def test_utils_layer_does_not_import_home_assistant() -> None:
    """Test utils/ stays pure so it can be reused anywhere."""
    assert _offenders_with_homeassistant_import("utils") == []


def test_api_layer_does_not_import_home_assistant() -> None:
    """Test the protocol boundary stays independent of Home Assistant."""
    assert _offenders_with_homeassistant_import("api") == []


def test_runtime_inventory_root_module_is_removed() -> None:
    """Test runtime inventory lives under an owned helper path."""
    assert not (PACKAGE_ROOT / "runtime_inventory.py").exists()
    assert (PACKAGE_ROOT / "helpers" / "runtime_inventory.py").exists()


def test_config_entry_writes_remain_in_coordinator_module() -> None:
    """Test config-entry mutation does not drift outside coordinator-owned paths."""
    offenders = [
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in _python_files()
        if "async_update_entry(" in path.read_text() and path.name != "coordinator.py"
    ]
    assert offenders == []


def test_platforms_do_not_call_protocol_mutations_directly() -> None:
    """Test platform files delegate mutation orchestration to managers."""
    platform_files = [
        path for path in _python_files() if path.name in {"sensor.py", "switch.py"}
    ]
    offenders = [
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in platform_files
        if "async_update_rule(" in path.read_text()
        or "async_create_rule(" in path.read_text()
        or "async_delete_rule(" in path.read_text()
    ]
    assert offenders == []
