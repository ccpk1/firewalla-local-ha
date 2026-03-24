"""Bounded live smoke check for the integration's cloud auth helpers."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout

from custom_components.firewalla_local.api import (
    FirewallaApiClient,
    async_provision_firewalla_credentials,
    generate_firewalla_keys,
    load_qr_json,
)
from custom_components.firewalla_local.api.auth import fetch_groups, login_eptoken
from custom_components.firewalla_local.const import (
    DEFAULT_FIREWALLA_HOST,
    DEFAULT_PAIRING_DEVICE_NAME,
)
from custom_components.firewalla_local.runtime_inventory import (
    build_runtime_inventory_report,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-check the final Firewalla Local integration setup path using "
            "the real integration API modules"
        )
    )
    qr_group = parser.add_mutually_exclusive_group(required=False)
    qr_group.add_argument(
        "--qr-json",
        help="Raw QR JSON string from the Firewalla app",
    )
    qr_group.add_argument(
        "--qr-file",
        type=Path,
        help="Path to a file containing the raw QR JSON",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email or label to bind to the ETP token during login",
    )
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help=(
            "Only validate login/eptoken plus one authenticated group fetch; "
            "skip QR provisioning and local runtime verification"
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_FIREWALLA_HOST,
        help=(
            "Local Firewalla hostname or IP override used for post-link runtime "
            f"verification (default: {DEFAULT_FIREWALLA_HOST})"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path(".artifacts/auth-smoke"),
        help="Directory where auth smoke outputs should be written",
    )
    return parser


def prompt_for_raw_qr_json() -> str:
    """Prompt for QR JSON without shell-escaping issues."""
    print("Scan the Firewalla Additional Pairing QR code with a generic QR reader")
    return input("Paste the raw QR JSON and press Enter: ")


async def async_main() -> int:
    """Run the bounded auth smoke check against the real integration code."""
    args = build_parser().parse_args()

    if args.auth_only and (args.qr_json is not None or args.qr_file is not None):
        raise SystemExit("--auth-only cannot be combined with QR input")

    artifact_dir = args.artifact_dir / "latest"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    timeout = ClientTimeout(total=args.timeout)

    if args.auth_only:
        keys = generate_firewalla_keys()
        async with ClientSession(timeout=timeout) as session:
            identity = await login_eptoken(
                session,
                assertion_name=args.email,
                public_pem=keys.public_pem,
            )
            group_fetch_result, _ = await fetch_groups(
                session,
                identity=identity,
                assertion_name=args.email,
                public_pem=keys.public_pem,
            )

        (artifact_dir / "identity.json").write_text(
            json.dumps(
                {
                    "aid": identity.aid,
                    "eid": identity.eid,
                    "group_count": len(identity.groups),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (artifact_dir / "group_fetch.json").write_text(
            json.dumps(
                {
                    "group_count": len(group_fetch_result.groups),
                    "source": group_fetch_result.source,
                    "status": group_fetch_result.status,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (artifact_dir / "summary.json").write_text(
            json.dumps(
                {
                    "auth_only": True,
                    "group_count": len(group_fetch_result.groups),
                    "group_fetch_source": group_fetch_result.source,
                    "group_fetch_status": group_fetch_result.status,
                    "login_status": 200,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        print("Cloud auth HTTP 200")
        print(
            json.dumps(
                {
                    "aid": identity.aid,
                    "eid": identity.eid,
                    "group_count": len(identity.groups),
                },
                indent=2,
                sort_keys=True,
            )
        )
        print(f"Cloud group fetch HTTP {group_fetch_result.status}")
        print(f"Artifacts written under {artifact_dir}")
        return 0

    raw_qr_json = args.qr_json
    if raw_qr_json is None and args.qr_file is None:
        raw_qr_json = prompt_for_raw_qr_json()
    elif args.qr_file is not None:
        raw_qr_json = args.qr_file.read_text(encoding="utf-8")

    assert raw_qr_json is not None
    qr_data = load_qr_json(raw_qr_json)
    keys = generate_firewalla_keys()

    async with ClientSession(timeout=timeout) as session:
        credentials = await async_provision_firewalla_credentials(
            session,
            qr_data=qr_data,
            host=args.host,
            keys=keys,
            assertion_name=args.email,
        )
        client = FirewallaApiClient(
            session=session,
            host=credentials.host,
            gid=credentials.gid,
            eid=credentials.eid,
            aid=credentials.aid,
            symmetric_key=credentials.symmetric_key,
            device_name=DEFAULT_PAIRING_DEVICE_NAME,
        )
        runtime_payload = await client.async_get_runtime_init_payload()
        runtime_snapshot = client.build_runtime_snapshot(runtime_payload)
        system_info = runtime_snapshot.system_info

    (artifact_dir / "qr.json").write_text(
        json.dumps(qr_data.raw_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (artifact_dir / "provisioned_credentials.json").write_text(
        json.dumps(
            {
                "aid": credentials.aid,
                "eid": credentials.eid,
                "gid": credentials.gid,
                "host": credentials.host,
                "license": credentials.license,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (artifact_dir / "system_info.json").write_text(
        json.dumps(
            {
                "host": system_info.host,
                "model": system_info.model,
                "name": system_info.name,
                "serial_number": system_info.serial_number,
                "software_version": system_info.software_version,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (artifact_dir / "runtime_init.json").write_text(
        json.dumps(runtime_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (artifact_dir / "runtime_snapshot.json").write_text(
        json.dumps(
            {
                "system_info": {
                    "host": runtime_snapshot.system_info.host,
                    "model": runtime_snapshot.system_info.model,
                    "name": runtime_snapshot.system_info.name,
                    "serial_number": runtime_snapshot.system_info.serial_number,
                    "software_version": runtime_snapshot.system_info.software_version,
                },
                "policy_rules": [
                    {
                        "rule_id": rule.rule_id,
                        "action": rule.action,
                        "target": rule.target,
                        "target_name": rule.target_name,
                        "target_type": rule.target_type,
                        "direction": rule.direction,
                        "enabled": rule.enabled,
                        "purpose": rule.purpose,
                        "scope": list(rule.scope),
                        "applies_to": list(rule.applies_to),
                    }
                    for rule in runtime_snapshot.policy_rules
                ],
                "exception_rule_count": runtime_snapshot.exception_rule_count,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (artifact_dir / "runtime_inventory.json").write_text(
        json.dumps(
            build_runtime_inventory_report(
                runtime_payload,
                runtime_snapshot.policy_rules,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "auth_only": False,
                "gid": credentials.gid,
                "host": credentials.host,
                "license": credentials.license,
                "system_name": system_info.name,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print("Cloud provisioning succeeded")
    print(
        json.dumps(
            {
                "aid": credentials.aid,
                "eid": credentials.eid,
                "gid": credentials.gid,
                "host": credentials.host,
                "license": credentials.license,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print("Local runtime verification succeeded")
    print(
        json.dumps(
            {
                "host": system_info.host,
                "model": system_info.model,
                "name": system_info.name,
                "serial_number": system_info.serial_number,
                "software_version": system_info.software_version,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"Artifacts written under {artifact_dir}")
    return 0


def main() -> int:
    """Run the async entry point."""
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
