"""Tests for the guarded Firewalla admin manager."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.firewalla_local.managers.admin_manager import (
    FirewallaAdminManager,
)


def _manager(*, get_result: object = None) -> tuple[FirewallaAdminManager, AsyncMock]:
    """Return an admin manager with a mocked client and coordinator."""
    client = SimpleNamespace(
        async_get_item=AsyncMock(return_value=get_result),
        async_set_item=AsyncMock(return_value={"ok": True}),
        async_command_item=AsyncMock(return_value={"ok": True}),
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    manager = FirewallaAdminManager(coordinator, SimpleNamespace(), client)
    return manager, client


@pytest.mark.asyncio
async def test_admin_read_redacts_sensitive_fields() -> None:
    """Admin reads keep structure while removing returned credentials."""
    manager, client = _manager(
        get_result={"profileId": "wg0", "password": "secret", "nested": {"token": "x"}}
    )

    response = await manager.async_read("vpnProfiles")

    assert response["result"] == {
        "profileId": "wg0",
        "password": "[redacted]",
        "nested": {"token": "[redacted]"},
    }
    client.async_get_item.assert_awaited_once_with(
        "vpnProfiles", value=None, target="0.0.0.0"
    )


@pytest.mark.asyncio
async def test_admin_execute_defaults_to_dry_run() -> None:
    """A write request does not execute unless dry run is disabled."""
    manager, client = _manager()

    response = await manager.async_execute(
        "tag:create",
        value={"name": "Guests"},
    )

    assert response["executed"] is False
    client.async_command_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_execute_requires_confirmation() -> None:
    """A non-dry write requires explicit confirmation."""
    manager, client = _manager()

    with pytest.raises(ValueError, match="confirm must be true"):
        await manager.async_execute(
            "tag:create",
            value={"name": "Guests"},
            dry_run=False,
        )

    client.async_command_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_execute_routes_confirmed_command_and_refreshes() -> None:
    """A confirmed command reaches the command transport and refreshes."""
    manager, client = _manager()

    response = await manager.async_execute(
        "tag:create",
        value={"name": "Guests"},
        dry_run=False,
        confirm=True,
    )

    assert response["executed"] is True
    assert response["refreshed"] is True
    client.async_command_item.assert_awaited_once_with(
        "tag:create",
        value={"name": "Guests"},
        target="0.0.0.0",
    )


@pytest.mark.asyncio
async def test_network_config_dry_run_runs_impact_check() -> None:
    """Network dry runs read current state and run the native impact check."""
    manager, client = _manager(get_result={"ncid": "current"})
    requested = {"ncid": "next", "interface": {}}

    response = await manager.async_execute("networkConfig", value=requested)

    assert response["executed"] is False
    assert isinstance(response["current_config_hash"], str)
    assert client.async_get_item.await_count == 2
    assert client.async_get_item.await_args_list[1].kwargs == {
        "value": {"config": requested}
    }
    client.async_set_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_network_config_rejects_stale_hash() -> None:
    """Network execution refuses a config changed since the caller read it."""
    manager, client = _manager(get_result={"ncid": "current"})

    with pytest.raises(ValueError, match="changed after it was read"):
        await manager.async_execute(
            "networkConfig",
            value={"ncid": "next"},
            dry_run=False,
            confirm=True,
            expected_current_hash="stale",
        )

    client.async_set_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_network_config_executes_with_matching_hash() -> None:
    """Network execution wraps config only after hash and impact gates pass."""
    current = {"ncid": "current"}
    manager, client = _manager(get_result=current)
    read_response = await manager.async_read("networkConfig")
    client.async_get_item.reset_mock()

    response = await manager.async_execute(
        "networkConfig",
        value={"ncid": "next"},
        dry_run=False,
        confirm=True,
        expected_current_hash=str(read_response["config_hash"]),
        refresh=False,
    )

    assert response["executed"] is True
    client.async_set_item.assert_awaited_once_with(
        "networkConfig",
        value={"config": {"ncid": "next"}},
        target="0.0.0.0",
    )


@pytest.mark.asyncio
async def test_network_config_snapshot_rolls_back_without_exposing_secrets() -> None:
    """A raw snapshot can be restored by hash while its response stays redacted."""
    current = {"ncid": "current", "password": "wifi-secret"}
    manager, client = _manager(get_result=current)
    read_response = await manager.async_read("networkConfig")

    assert read_response["result"] == {
        "ncid": "current",
        "password": "[redacted]",
    }
    client.async_get_item.reset_mock()
    response = await manager.async_rollback_network_config(
        str(read_response["config_hash"])
    )

    assert response["executed"] is False
    assert response["rollback_snapshot_hash"] == read_response["config_hash"]
    client.async_set_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_network_config_rollback_rejects_unknown_snapshot() -> None:
    """Rollback refuses hashes not held by this loaded manager."""
    manager, client = _manager()

    with pytest.raises(ValueError, match="snapshot is unavailable"):
        await manager.async_rollback_network_config("missing")

    client.async_set_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_execute_rejects_non_allowlisted_item() -> None:
    """Credential, shell, and unknown commands stay unreachable."""
    manager, client = _manager()

    with pytest.raises(ValueError, match="Unsupported"):
        await manager.async_execute("cmd", value={"cmd": "id"})

    client.async_command_item.assert_not_awaited()
