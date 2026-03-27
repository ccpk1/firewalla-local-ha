"""Pull the current Firewalla local runtime using stored HA credentials.

This helper is the preferred comparison workflow when you want to inspect what
the integration can read from the box right now without re-pairing, testing the
cloud auth flow, or capturing packets.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout

from custom_components.firewalla_local.api.client import FirewallaApiClient
from custom_components.firewalla_local.const import DEFAULT_PAIRING_DEVICE_NAME

CONFIG_PATH = Path("/workspaces/core/config/.storage/core.config_entries")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Pull the current Firewalla local runtime using the working "
            "Home Assistant config entry credentials"
        )
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path(".artifacts/runtime-pull"),
        help="Artifact root where one timestamped runtime pull should be written",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds",
    )
    return parser


def load_entry() -> dict[str, object]:
    """Return the first configured Firewalla Local config entry."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for entry in config["data"]["entries"]:
        if entry.get("domain") == "firewalla_local":
            return entry
    raise RuntimeError("No firewalla_local config entry found")


def build_output_dir(root: Path) -> Path:
    """Create and return one timestamped artifact directory."""
    run_dir = root / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


async def async_main() -> int:
    """Pull and write the current raw runtime and compact user summary."""
    args = build_parser().parse_args()
    entry = load_entry()
    data = entry["data"]
    out_dir = build_output_dir(args.artifact_dir)

    timeout = ClientTimeout(total=args.timeout)
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
        payload = await client.async_get_runtime_init_payload()
        snapshot = client.build_runtime_snapshot(payload)

    (out_dir / "runtime_init.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "user_usage_summary.json").write_text(
        json.dumps(
            [
                {
                    "user_id": user.user_id,
                    "name": user.name,
                    "affiliated_group_id": user.affiliated_group_id,
                    "affiliated_group_name": user.affiliated_group_name,
                    "total_minutes_today": user.total_minutes_today,
                    "unique_minutes_today": user.unique_minutes_today,
                    "app_usage_today": [
                        {
                            "app_id": usage.app_id,
                            "category": usage.category,
                            "total_minutes": usage.total_minutes,
                            "unique_minutes": usage.unique_minutes,
                        }
                        for usage in user.app_usage_today
                    ],
                }
                for user in snapshot.users
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "config_entry_id": entry["entry_id"],
                "host": data["host"],
                "aid": data["aid"],
                "eid": data["eid"],
                "gid": data["gid"],
                "license": data.get("license"),
                "host_count": len(snapshot.hosts),
                "rule_count": len(snapshot.policy_rules),
                "user_count": len(snapshot.users),
                "artifact_dir": str(out_dir),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print(out_dir)
    print(
        json.dumps(
            {
                "host_count": len(snapshot.hosts),
                "rule_count": len(snapshot.policy_rules),
                "user_count": len(snapshot.users),
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    """Run the runtime pull helper."""
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
