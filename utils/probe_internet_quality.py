"""Probe the Firewalla internet-quality data from the dev box.

Fetches `item=networkMonitorData` and the `events` ping_RTT/ping_lossrate feed
using the stored HA config-entry credentials, and writes the raw responses to
.tmp so we can confirm the exact schema before implementing.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout

from custom_components.firewalla_local.api.client import FirewallaApiClient
from custom_components.firewalla_local.const import DEFAULT_PAIRING_DEVICE_NAME

CONFIG_PATH = Path("/workspaces/core/config/.storage/core.config_entries")


def load_entry() -> dict[str, object]:
    """Return the first configured Firewalla Local config entry."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for entry in config["data"]["entries"]:
        if entry.get("domain") == "firewalla_local":
            return entry
    raise RuntimeError("No firewalla_local config entry found")


async def async_main() -> int:
    """Fetch and dump the internet-quality payloads."""
    entry = load_entry()
    data = entry["data"]

    timeout = ClientTimeout(total=20.0)
    async with ClientSession(timeout=timeout) as session:
        client = FirewallaApiClient(
            session=session,
            host=data["host"],
            gid=data["gid"],
            eid=data["eid"],
            aid=data["aid"],
            symmetric_key=data["symmetric_key"],
            device_name=DEFAULT_PAIRING_DEVICE_NAME,
        )

        # 1. networkMonitorData (latency/loss measurements)
        try:
            nmd = await client._async_send_local_message_data(
                message_type="get",
                data={"item": "networkMonitorData", "value": {}},
            )
            Path(".tmp/quality_networkMonitorData.json").write_text(
                json.dumps(nmd, indent=2, sort_keys=True), encoding="utf-8"
            )
            print(
                "networkMonitorData keys:",
                list(nmd) if isinstance(nmd, dict) else type(nmd),
            )
        except Exception as err:
            print("networkMonitorData ERROR:", type(err).__name__, err)

        # 2. events feed filtered to ping_RTT / ping_lossrate
        try:
            events = await client._async_send_local_message_data(
                message_type="get",
                data={
                    "item": "events",
                    "value": {
                        "filters": [
                            {"event_type": "action", "sub_type": "ping_RTT"},
                            {"event_type": "action", "sub_type": "ping_lossrate"},
                        ],
                        "limit_count": 50,
                        "limit_offset": 0,
                        "parse_json": True,
                        "reverse": True,
                    },
                },
            )
            Path(".tmp/quality_events.json").write_text(
                json.dumps(events, indent=2, sort_keys=True), encoding="utf-8"
            )
            print("events type:", type(events).__name__)
            if isinstance(events, list):
                print("events count:", len(events))
                if events:
                    print("first event:", json.dumps(events[0], indent=2)[:800])
        except Exception as err:
            print("events ERROR:", type(err).__name__, err)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
