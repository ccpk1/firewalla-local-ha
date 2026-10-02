"""Probe device membership writes against the live local runtime.

This is a reverse-engineering helper, not part of the integration. It sends real
commands to the box, so it defaults to a dry run and requires ``--apply`` to
write.

The contract this probe keeps honest is documented in
``docs/REVERSE_ENGINEERING_WORKFLOW.md`` Findings 41, 42 and 43:

- membership is a host-scoped ``set`` on ``item: "policy"`` writing ``value.tags``
- a plain group and a user assignment are the same wire shape; a user assignment
  is the user's affiliated backing tag, so the tag id is what gets written and
  never the user id
- tag ids are integers in the write and strings in the read payload
- the payload may be minimal (``{"tags": [...]}``). Finding 43 confirmed the box
  keeps every other policy key, so no other key is sent, and this probe asserts
  that by diffing the host policy before and after

Usage:

    python utils/probe_membership.py --list
    python utils/probe_membership.py <mac>                      # inspect only
    python utils/probe_membership.py <mac> --tag 12             # dry run
    python utils/probe_membership.py <mac> --clear --apply
    python utils/probe_membership.py <mac> --tag 12 --apply --restore
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
from pathlib import Path
from typing import Any

from aiohttp import ClientSession

from custom_components.firewalla_local.api.client import FirewallaApiClient
from custom_components.firewalla_local.const import DEFAULT_PAIRING_DEVICE_NAME

CONFIG_PATH = Path("/workspaces/core/config/.storage/core.config_entries")


def load_entry() -> dict[str, Any]:
    """Return the first Firewalla config entry's data."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for entry in config["data"]["entries"]:
        if entry.get("domain") == "firewalla_local":
            data = entry["data"]
            assert isinstance(data, dict)
            return data
    raise RuntimeError("no firewalla_local config entry found")


def _raw_host(payload: dict[str, Any], mac: str) -> dict[str, Any]:
    for host in payload.get("hosts", []):
        if str(host.get("mac", "")).upper() == mac.upper():
            return host
    raise RuntimeError(f"host {mac} not found")


def _tag_ids(payload: dict[str, Any], raw_host: dict[str, Any]) -> list[str]:
    return [str(tag) for tag in (raw_host.get("tags") or [])]


def _describe_tag(payload: dict[str, Any], tag_id: str) -> str:
    """Describe one tag as a group or a user affiliation by linkage."""
    tags = payload.get("tags", {})
    users = payload.get("userTags", {})
    tag = tags.get(tag_id) or {}
    policy = tag.get("policy")
    linked = policy.get("userTags") if isinstance(policy, dict) else None
    if linked:
        name = (users.get(str(linked[0])) or {}).get("name")
        return f"{tag_id}:USER({name})"
    return f"{tag_id}:GROUP({tag.get('name')})"


def _membership_label(payload: dict[str, Any], raw_host: dict[str, Any]) -> str:
    tag_ids = _tag_ids(payload, raw_host)
    return ", ".join(_describe_tag(payload, tag) for tag in tag_ids) or "<none>"


def _build_payload(tag_ids: list[int]) -> dict[str, object]:
    """Build the minimal membership payload."""
    return {"tags": tag_ids}


async def _run(args: argparse.Namespace) -> None:
    data = load_entry()
    async with ClientSession() as session:
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

        if args.list:
            for raw_host in payload.get("hosts", []):
                print(
                    f"{raw_host.get('mac')!s:>20}  "
                    f"{raw_host.get('name')!s:28.28}  "
                    f"{_membership_label(payload, raw_host)}"
                )
            return

        mac = args.mac
        raw_host = _raw_host(payload, mac)
        original_tags = _tag_ids(payload, raw_host)
        original_policy = copy.deepcopy(raw_host.get("policy") or {})

        print(f"host          : {raw_host.get('name')} ({mac})")
        print(f"policy keys   : {len(original_policy)}")
        print(f"BEFORE        : {_membership_label(payload, raw_host)}")

        if args.clear:
            target_tag_ids: list[int] = []
            print("\ntarget        : clear (explicit empty list)")
        else:
            if args.tag is None:
                print("\n(no --tag or --clear supplied; inspection only)")
                return
            tag_id = str(args.tag)
            if tag_id not in payload.get("tags", {}):
                print(f"\ntag {args.tag} does not exist on this box")
                return
            target_tag_ids = [int(args.tag)]
            print(f"\ntarget        : {_describe_tag(payload, tag_id)}")

        print(f"payload       : {json.dumps(_build_payload(target_tag_ids))}")

        if not args.apply:
            print("\nDRY RUN - nothing sent. Re-run with --apply to write.")
            return

        response = await client.async_set_host_policy(
            mac, _build_payload(target_tag_ids)
        )
        print(f"write response: {json.dumps(response, sort_keys=True)[:160]}")

        after_payload = await client.async_get_runtime_init_payload()
        after_host = _raw_host(after_payload, mac)
        after_policy = after_host.get("policy") or {}

        print(f"AFTER         : {_membership_label(after_payload, after_host)}")
        print(f"policy keys   : {len(after_policy)}")
        lost = sorted(set(original_policy) - set(after_policy))
        changed = sorted(
            key
            for key in set(original_policy) & set(after_policy)
            if key != "tags" and original_policy[key] != after_policy[key]
        )
        print(f"policy lost   : {lost or 'none'}")
        print(f"policy changed: {changed or 'none'}")

        if args.restore:
            print(f"\nrestoring {original_tags}")
            await client.async_set_host_policy(
                mac, _build_payload([int(tag) for tag in original_tags])
            )
            restored_payload = await client.async_get_runtime_init_payload()
            restored_host = _raw_host(restored_payload, mac)
            print(
                f"restored      : {_membership_label(restored_payload, restored_host)}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mac", nargs="?", help="Target host MAC")
    parser.add_argument("--tag", type=int, help="Tag id to write")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Write an explicit empty tags list (mutually exclusive with --tag)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually send the write (default is dry-run)",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore the original tags after the write",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List hosts and their current membership",
    )
    args = parser.parse_args()
    if args.clear and args.tag is not None:
        parser.error("--clear and --tag are mutually exclusive")
    if not args.list and not args.mac:
        parser.error("provide a host MAC, or --list")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
