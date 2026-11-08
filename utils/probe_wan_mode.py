"""Fingerprint a Firewalla box's multi-WAN state for mode comparison.

Pulls the runtime init payload from the dev box and reduces it to the fields
that change when the box's WAN mode changes, so two captures taken in different
modes can be diffed without reading two 60k-line payloads.

The point is to answer, for a mode we have never seen: what does the box call
it, which interfaces does it name, what per-WAN state does it publish, and does
anything report a traffic split.

Usage:
    python utils/probe_wan_mode.py --label failover --out .artifacts/wan-mode
    python utils/probe_wan_mode.py --label load_balance --out .artifacts/wan-mode

Two captures are written per run: ``<label>.json`` is the reduced fingerprint
and ``<label>-raw.json`` is the full payload, which is what to reach for when a
field in the fingerprint turns out to matter.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from custom_components.firewalla_local.api.client import FirewallaApiClient
from custom_components.firewalla_local.const import DEFAULT_PAIRING_DEVICE_NAME

CONFIG_PATH = Path("/workspaces/core/config/.storage/core.config_entries")

# Per-WAN health flags the box publishes in ``wanTestResult``. Each is a plain
# boolean on a real payload, so they are reduced to a flat mapping.
_WAN_TEST_FLAGS = ("active", "carrier", "dns", "ping")


def load_entry() -> dict[str, object]:
    """Return the first configured Firewalla Local config entry."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for entry in config["data"]["entries"]:
        if entry.get("domain") == "firewalla_local":
            return entry["data"]
    raise RuntimeError("No firewalla_local config entry found")


def _raw_routing(payload: dict[str, Any]) -> Any:
    """Return the routing block verbatim, whatever mode it describes."""
    network_config = payload.get("networkConfig")
    if not isinstance(network_config, dict):
        return None
    return network_config.get("routing")


def _wan_profiles(payload: dict[str, Any]) -> dict[str, Any]:
    """Return every ``networkProfiles`` entry the box typed as a WAN."""
    profiles = payload.get("networkProfiles")
    if not isinstance(profiles, dict):
        return {}
    return {
        uuid: {
            "intf": profile.get("intf"),
            "type": profile.get("type"),
            "active": profile.get("active"),
            "ready": profile.get("ready"),
            "pendingTest": profile.get("pendingTest"),
            "monitoring": profile.get("monitoring"),
            "rtid": profile.get("rtid"),
            "extra_keys": sorted(
                set(profile)
                - {
                    "intf",
                    "type",
                    "active",
                    "ready",
                    "pendingTest",
                    "monitoring",
                    "rtid",
                    "uuid",
                    "dns",
                    "dns6",
                    "gateway",
                    "gateway6",
                    "ipv4",
                    "ipv4Subnet",
                    "ipv4Subnets",
                    "ipv4s",
                    "ipv6",
                    "ipv6Subnets",
                    "origDns",
                    "origDns6",
                    "pds",
                    "policy",
                    "rt4Subnets",
                    "rt6Subnets",
                }
            ),
        }
        for uuid, profile in profiles.items()
        if isinstance(profile, dict) and profile.get("type") == "wan"
    }


def _wan_test_results(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the per-interface ``wanTestResult`` block, health flags flattened."""
    test_result = payload.get("wanTestResult")
    if not isinstance(test_result, dict):
        return {}
    wans = test_result.get("wans")
    if not isinstance(wans, dict):
        return {}

    reduced: dict[str, Any] = {}
    for interface, entry in wans.items():
        if not isinstance(entry, dict):
            continue
        reduced[interface] = {
            **{flag: entry.get(flag) for flag in _WAN_TEST_FLAGS},
            "wanConnState": entry.get("wanConnState"),
            "failures": entry.get("failures"),
            "extra_keys": sorted(
                set(entry)
                - {
                    *_WAN_TEST_FLAGS,
                    "wanConnState",
                    "failures",
                    "http",
                    "recentDownTime",
                    "ts",
                }
            ),
        }
    return reduced


def _dual_wan_events(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the ``dualwan_state`` event labels, which carry the mode name."""
    found: dict[str, Any] = {}
    for block_key in ("latestAllStateEvents", "latestStateEventsError"):
        block = payload.get(block_key)
        if not isinstance(block, dict):
            continue
        for event_key, event in block.items():
            if not isinstance(event, dict):
                continue
            labels = event.get("labels")
            if not isinstance(labels, dict) or "wanType" not in labels:
                continue
            found[f"{block_key}:{event_key}"] = {
                "wanType": labels.get("wanType"),
                "primaryInterface": labels.get("primaryInterface"),
                "changedInterface": labels.get("changedInterface"),
                "wanSwitched": labels.get("wanSwitched"),
                "wanStatus": labels.get("wanStatus"),
                "state_key": event.get("state_key"),
                "state_value": event.get("state_value"),
            }
    return found


def _top_level_network(payload: dict[str, Any]) -> Any:
    """Return the top-level ``network`` block, reduced to identity and state."""
    network = payload.get("network")
    if not isinstance(network, dict):
        return None
    return {
        key: network.get(key)
        for key in (
            "uuid",
            "name",
            "desc",
            "type",
            "active",
            "ready",
            "pendingTest",
            "rtid",
            "conn_type",
        )
    }


def _counters(payload: dict[str, Any]) -> dict[str, Any]:
    """Return per-interface rx/tx counters, the only per-WAN traffic signal."""
    metrics = payload.get("networkMetrics")
    if not isinstance(metrics, dict):
        return {}
    return {
        interface: {key: entry.get(key) for key in ("rx", "tx")}
        for interface, entry in metrics.items()
        if isinstance(entry, dict)
    }


def build_fingerprint(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce one init payload to the fields a WAN-mode change can move."""
    return {
        "routing": _raw_routing(payload),
        "network": _top_level_network(payload),
        "wan_profiles": _wan_profiles(payload),
        "wan_test_result": _wan_test_results(payload),
        "dual_wan_events": _dual_wan_events(payload),
        "counters": _counters(payload),
        # Absence of a key in a mode is itself a finding, so the payload's
        # top-level shape is recorded rather than assumed.
        "top_level_keys": sorted(payload),
    }


async def async_main(label: str, out_dir: Path) -> int:
    """Capture the live payload and write the reduced and raw captures."""
    entry = load_entry()

    timeout = ClientTimeout(total=30.0)
    async with ClientSession(timeout=timeout) as session:
        client = FirewallaApiClient(
            session=session,
            host=str(entry["host"]),
            gid=str(entry["gid"]),
            eid=str(entry["eid"]),
            aid=str(entry["aid"]),
            symmetric_key=str(entry["symmetric_key"]),
            device_name=DEFAULT_PAIRING_DEVICE_NAME,
        )
        payload = await client.async_get_runtime_init_payload()

    await asyncio.to_thread(out_dir.mkdir, parents=True, exist_ok=True)
    fingerprint = build_fingerprint(payload)
    await asyncio.to_thread(
        (out_dir / f"{label}.json").write_text,
        json.dumps(fingerprint, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    await asyncio.to_thread(
        (out_dir / f"{label}-raw.json").write_text,
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(fingerprint, indent=2, sort_keys=True))
    return 0


def main() -> int:
    """Parse the CLI and run one capture."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="Capture label, e.g. failover")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".artifacts/wan-mode"),
        help="Directory to write the captures into",
    )
    args = parser.parse_args()
    return asyncio.run(async_main(args.label, args.out))


if __name__ == "__main__":
    raise SystemExit(main())
