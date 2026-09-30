"""Probe Firewalla alarm control syntax against the live local runtime.

This is a reverse-engineering helper, not part of the integration. It sends real
commands to the box, so it defaults to a dry run and requires ``--confirm`` to
actually write.

Control syntax confirmed from the decompiled Android app
(``ku7.m14063c`` / ``ku7.m14064d``):

- archive a single alarm:  ``item="alarm:ignore"`` with ``{"alarmID": <aid>}``
- delete a single alarm:   ``item="alarm:delete"`` with ``{"alarmID": <aid>}``
- remove a mute/exception: ``item="alarm:unallow"`` with ``{"alarmID": <aid>}``
- create a mute/exception: ``item="alarm:allow"``  with ``{"alarmID", "matchAll",
  "info": {"type", "target", "device", "expireTs"}}``
- block:                   ``item="alarm:block"`` with the same envelope; adds
  ``dnsmasq_only`` for ``dns``/``category`` (``cd0.m2349a``)
- remove a block:          ``item="alarm:unblock"`` with ``{"alarmID": <aid>}``

``alarmID`` is the ``aid`` field of an alarm record, and the mute/block command's
``device`` field is the device MAC (``p.device.mac``).

Mute durations, taken verbatim from ``AlarmMuteScheduleDialog``:

- ``1 hour``  -> ``(System.currentTimeMillis() / 1000) + 3600``
- ``today``   -> start of tomorrow in the **box's** timezone:
  ``ZonedDateTime.now(boxTz).plusDays(1).truncatedTo(DAYS).toEpochSecond()``
- ``always``  -> ``expireTs`` is ``-1`` and therefore omitted from the payload
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, ClientTimeout

from custom_components.firewalla_local.api.client import FirewallaApiClient
from custom_components.firewalla_local.const import DEFAULT_PAIRING_DEVICE_NAME
from custom_components.firewalla_local.utils.duration import parse_duration_to_seconds

CONFIG_PATH = Path("/workspaces/core/config/.storage/core.config_entries")

_ARGS_ALARM_ID = "alarmID"
_ARGS_ALARM_TYPE = "alarm_type"
_ARGS_DEVICE = "device"
_ARGS_EXPIRE_TS = "expire_ts"
_ARGS_MATCH_ALL = "match_all"
_ARGS_TARGET = "target"

_BULK_ACTIONS = {
    "archive-all": "alarm:ignoreAll",
    "delete-archived-all": "alarm:deleteArchivedAll",
    "delete-active-all": "alarm:deleteActiveAll",
}

_MUTABLE_TYPES = ("dns", "ip", "domain", "category", "country", "devicePort", "mac")

_MUTE_SECONDS_ONE_HOUR = parse_duration_to_seconds("1h")
_RAW_TIMEZONE_KEY = "timezone"


def resolve_expire_ts(duration: str, payload: dict[str, Any]) -> int | None:
    """Return the expireTs for a mute duration, or None for 'always'.

    Mirrors ``AlarmMuteScheduleDialog``: 'hour' is the same relative-offset form
    used by ``pause_rule``, and 'today' is the start of tomorrow in the **box's**
    timezone, not the client's.

    Uses stdlib time only. Root-level tools in this repository do not import
    ``homeassistant.*``, since they run outside the Home Assistant process; the
    integration's own ``dt_util`` convention applies to ``services.py``, not here.

    Deliberately does not invent a duration vocabulary: the app exposes three
    fixed options, so this does too rather than accepting arbitrary durations.
    """
    if duration == "always":
        return None
    if duration == "hour":
        return int(datetime.now(tz=UTC).timestamp()) + _MUTE_SECONDS_ONE_HOUR
    tz_name = payload.get(_RAW_TIMEZONE_KEY)
    try:
        tzinfo = ZoneInfo(tz_name) if isinstance(tz_name, str) else UTC
    except Exception:
        tzinfo = UTC
    start_of_tomorrow = datetime.now(tz=tzinfo) + timedelta(days=1)
    return int(
        start_of_tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    )


def load_entry() -> dict[str, object]:
    """Return the first configured Firewalla Local config entry."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for entry in config["data"]["entries"]:
        if entry.get("domain") == "firewalla_local":
            return entry
    raise RuntimeError("No firewalla_local config entry found")


def _build_client(
    session: ClientSession, entry: dict[str, object]
) -> FirewallaApiClient:
    """Create a client from a stored config entry."""
    data = entry["data"]
    return FirewallaApiClient(
        session=session,
        host=data["host"],
        gid=data["gid"],
        eid=data["eid"],
        aid=data["aid"],
        symmetric_key=data["symmetric_key"],
        device_name=DEFAULT_PAIRING_DEVICE_NAME,
    )


def _summarize(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the alarm-relevant summary of one init payload."""
    alarms = payload.get("newAlarms") or []
    exceptions = payload.get("exceptionRules") or []
    return {
        "activeAlarmCount": payload.get("activeAlarmCount"),
        "newAlarms_count": len(alarms),
        "exceptionRules_count": len(exceptions),
        "newest_aids": [a.get("aid") for a in alarms[:5]],
        "exception_aids": [e.get("aid") for e in exceptions[:8]],
    }


def _find_alarm(payload: dict[str, Any], aid: str) -> dict[str, Any] | None:
    """Return one alarm record by aid."""
    for alarm in payload.get("newAlarms") or []:
        if alarm.get("aid") == aid:
            return alarm
    return None


def _build_ignore_value(aid: str) -> dict[str, object]:
    """Build the ``alarm:ignore`` (archive) value payload."""
    return {_ARGS_ALARM_ID: aid}


def _build_delete_value(aid: str) -> dict[str, object]:
    """Build the ``alarm:delete`` value payload."""
    return {_ARGS_ALARM_ID: aid}


def _build_unallow_value(aid: str) -> dict[str, object]:
    """Build the ``alarm:unallow`` value payload."""
    return {_ARGS_ALARM_ID: aid}


def _build_allow_value(
    aid: str,
    *,
    match_type: str,
    target: str | None,
    device: str | None,
    expire_ts: int | None,
    match_all: bool,
) -> dict[str, object]:
    """Build the ``alarm:allow`` (mute) value payload.

    Mirrors ``ku7.m14064d``: the alarm id at the top level, ``matchAll`` always
    set, and the scope details nested under ``info``.
    """
    info: dict[str, object] = {}
    if match_type:
        info["type"] = match_type
    if target:
        info["target"] = target
    if device:
        info["device"] = device
    if expire_ts is not None:
        info["expireTs"] = expire_ts
    value: dict[str, object] = {_ARGS_ALARM_ID: aid, "matchAll": 1 if match_all else 0}
    if match_type == "category":
        # The app scopes category mutes with a target-list style tag.
        info["customizedKeys"] = {
            "app_uid": aid,
            "app_name": target or "",
        }
    value["info"] = info
    return value


def _build_block_value(
    aid: str,
    *,
    match_type: str,
    target: str | None,
    device: str | None,
    match_all: bool,
) -> dict[str, object]:
    """Build the ``alarm:block`` value payload.

    Same envelope as ``alarm:allow``; ``dns``/``category`` additionally carry
    ``dnsmasq_only`` (``cd0.m2349a``). Blocks carry no ``expireTs``.
    """
    info: dict[str, object] = {}
    if match_type:
        info["type"] = match_type
    if target:
        info["target"] = target
    if device:
        info["device"] = device
    if match_type in ("dns", "category"):
        info["dnsmasq_only"] = True
    return {
        _ARGS_ALARM_ID: aid,
        "matchAll": 1 if match_all else 0,
        "info": info,
    }


async def _send(
    client: FirewallaApiClient, item: str, value: dict[str, object]
) -> object:
    """Send one alarm command and return the raw data payload."""
    return await client._async_send_local_message(
        message_type="cmd",
        data={"item": item, "value": value},
        target="0.0.0.0",
    )


async def _fetch_alarms(
    client: FirewallaApiClient,
    *,
    archived: bool = False,
    page_size: int = 1000,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Fetch the active or archived alarm list.

    The two items accept **different** page-size keys, which is easy to get
    wrong: measured on 2026-09-30, ``archivedAlarms`` honours ``limit`` (+
    ``offset``) while ``alarms`` honoured ``count``. Rather than depend on that
    asymmetry, both keys are sent with the same value so either handler reads
    the one it understands; unknown keys are ignored. The default page is 50,
    so a large value is needed to get the full set.
    """
    item = "archivedAlarms" if archived else "alarms"
    payload = await client._async_send_local_message(
        message_type="get",
        data={
            "item": item,
            "value": {"count": page_size, "limit": page_size, "offset": offset},
        },
        target="0.0.0.0",
    )
    if not isinstance(payload, dict):
        return []
    alarms = payload.get("alarms")
    return (
        [a for a in alarms if isinstance(a, dict)] if isinstance(alarms, list) else []
    )


async def _fetch_archived(client: FirewallaApiClient) -> list[dict[str, Any]]:
    """Fetch the archived alarm list."""
    return await _fetch_alarms(client, archived=True)


async def _fetch_alarm_detail(
    client: FirewallaApiClient, aid: str
) -> dict[str, Any] | None:
    """Fetch one alarm's full detail, which carries extra enrichment."""
    payload = await client._async_send_local_message(
        message_type="get",
        data={"item": "alarmDetail", "value": {"alarmID": aid}},
        target="0.0.0.0",
    )
    return payload if isinstance(payload, dict) else None


async def async_main() -> int:
    """Run the requested alarm control probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action",
        required=True,
        choices=(
            "archive",
            "delete",
            "mute",
            "unallow",
            "block",
            "unblock",
            *_BULK_ACTIONS,
        ),
    )
    parser.add_argument("--aid", help="Target alarm id (the alarm's `aid` field).")
    parser.add_argument(
        "--index",
        type=int,
        default=0,
        help="Select the Nth newest alarm when --aid is omitted.",
    )
    parser.add_argument(
        "--match-type",
        default="dns",
        choices=_MUTABLE_TYPES,
        help="Scope selector for a mute/block; mirrors the app's `info.type`.",
    )
    parser.add_argument("--target", help="Scope target, e.g. a domain.")
    parser.add_argument("--device", help="Device MAC scope.")
    parser.add_argument(
        "--duration",
        default="always",
        choices=("hour", "today", "always"),
        help=(
            "Mute lifetime, matching the app's three options. 'always' omits expireTs."
        ),
    )
    parser.add_argument("--expire-ts", type=int, help="Override the computed expiry.")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually send the command. Without this the run is a dry run.",
    )
    args = parser.parse_args()

    entry = load_entry()
    timeout = ClientTimeout(total=args.timeout)
    async with ClientSession(timeout=timeout) as session:
        client = _build_client(session, entry)

        before = await client.async_get_runtime_init_payload()
        print("=== BEFORE ===")
        print(json.dumps(_summarize(before), indent=2))

        if args.action in _BULK_ACTIONS:
            # Bulk commands carry an empty value and act on the whole set, so no
            # alarm id is resolved. `deleteActiveAll` is irreversible.
            item = _BULK_ACTIONS[args.action]
            print(f"\n=== BULK COMMAND === {item} (empty value)")
            if not args.confirm:
                print("\nDry run. Re-run with --confirm to send.")
                return 0
            result = await _send(client, item, {})
            print("\n=== RESPONSE ===")
            print(json.dumps(result, indent=2, default=str))
            await asyncio.sleep(2)
            after = await client.async_get_runtime_init_payload()
            print("\n=== AFTER ===")
            print(json.dumps(_summarize(after), indent=2))
            return 0

        alarms = before.get("newAlarms") or []
        if not alarms:
            print("No active alarms to target.")
            return 1

        aid = args.aid
        if aid is None:
            if args.index >= len(alarms):
                print(f"--index {args.index} out of range ({len(alarms)} alarms).")
                return 1
            aid = alarms[args.index]["aid"]
        alarm = _find_alarm(before, aid)
        if alarm is None:
            # A muted alarm leaves `newAlarms` and appears on an exception rule;
            # a blocked alarm leaves it and appears on a *policy* rule; an
            # archived alarm leaves it entirely and only appears in the
            # `archivedAlarms` fetch. All three must be resolvable so the
            # reverse commands can be issued.
            for source in ("exceptionRules", "policyRules"):
                alarm = next(
                    (
                        record
                        for record in (before.get(source) or [])
                        if record.get("aid") == aid
                    ),
                    None,
                )
                if alarm is not None:
                    print(f"(resolved aid {aid} from {source})")
                    break
        if alarm is None:
            archived = await _fetch_archived(client)
            alarm = next(
                (record for record in archived if record.get("aid") == aid), None
            )
            if alarm is not None:
                print(f"(resolved aid {aid} from archivedAlarms)")
        if alarm is None:
            print(
                f"aid {aid} not found in newAlarms, exceptionRules, "
                "policyRules or archivedAlarms."
            )
            return 1

        if args.action == "archive":
            item, value = "alarm:ignore", _build_ignore_value(aid)
        elif args.action == "delete":
            item, value = "alarm:delete", _build_delete_value(aid)
        elif args.action == "unallow":
            item, value = "alarm:unallow", _build_unallow_value(aid)
        elif args.action == "unblock":
            item, value = "alarm:unblock", _build_unallow_value(aid)
        elif args.action == "block":
            item, value = (
                "alarm:block",
                _build_block_value(
                    aid,
                    match_type=args.match_type,
                    target=args.target or alarm.get("p.dest.domain"),
                    device=args.device or alarm.get("p.device.mac"),
                    match_all=True,
                ),
            )
        else:
            expire_ts = (
                args.expire_ts
                if args.expire_ts is not None
                else resolve_expire_ts(args.duration, before)
            )
            item, value = (
                "alarm:allow",
                _build_allow_value(
                    aid,
                    match_type=args.match_type,
                    target=args.target or alarm.get("p.dest.domain"),
                    device=args.device or alarm.get("p.device.mac"),
                    expire_ts=expire_ts,
                    match_all=True,
                ),
            )
            print(
                f"\nMute duration: {args.duration}"
                + (f" (expireTs={expire_ts})" if expire_ts is not None else "")
            )

        print("\n=== TARGET ALARM ===")
        print(
            json.dumps(
                {
                    "aid": aid,
                    "type": alarm.get("type"),
                    "state": alarm.get("state"),
                    "device": alarm.get("device"),
                    "p.dest.domain": alarm.get("p.dest.domain"),
                    "p.device.mac": alarm.get("p.device.mac"),
                },
                indent=2,
            )
        )

        print("\n=== COMMAND ===")
        print(json.dumps({"item": item, "value": value}, indent=2))

        if not args.confirm:
            print("\nDry run. Re-run with --confirm to send.")
            return 0

        result = await _send(client, item, value)
        print("\n=== RESPONSE ===")
        print(json.dumps(result, indent=2, default=str))

        await asyncio.sleep(2)
        after = await client.async_get_runtime_init_payload()
        print("\n=== AFTER ===")
        print(json.dumps(_summarize(after), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
