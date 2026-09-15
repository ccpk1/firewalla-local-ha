"""Architecture boundary tests for Firewalla Local."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[3] / "custom_components" / "firewalla_local"
)


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys instead of silently keeping the last one."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    """Construct one mapping while checking each key exactly once."""
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _python_files() -> list[Path]:
    """Return integration Python files excluding tests and caches."""
    return [
        path for path in PACKAGE_ROOT.rglob("*.py") if "__pycache__" not in path.parts
    ]


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


def test_service_descriptions_have_unique_mapping_keys() -> None:
    """Test Home Assistant service metadata has no ambiguous duplicate keys."""
    with (PACKAGE_ROOT / "services.yaml").open(encoding="utf-8") as service_file:
        assert yaml.load(service_file, Loader=_UniqueKeyLoader)
