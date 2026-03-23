"""Standalone proof-of-concept for the Firewalla ETP local pairing handshake.

This script intentionally stays outside the Home Assistant integration code.
It is meant to prove the local pairing path before any config-flow work starts.

The RSA key serialization formats in this file are verified against the public
Node tooling and the external builder brief:

- private key: PEM PKCS#8, unencrypted
- public key: PEM SPKI

This proof is for the local Additional Pairing flow only. It does not use the
MSP or web API.

The default request target in this proof uses the external builder brief
endpoint: `https://<firewalla_ip>:8833/v1/auth/app/verify`.

Some firmware may route the same pairing flow through `/v1/encipher/auth`, so
the endpoint path is configurable from the CLI.

The current public history of `lesleyxyz/firewalla-tools` does not expose this
local request body, so the default payload here is limited to the QR fields and
generated public key that are already accepted inputs for this repo. If your
box requires additional fields, provide them with `--extra-field`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

DEFAULT_VERIFY_PATH = "/v1/auth/app/verify"
DEFAULT_TIMEOUT = 15.0
REQUIRED_QR_FIELDS = ("gid", "seed", "license", "ek", "ipaddress")


@dataclass(slots=True, frozen=True)
class PairingQrData:
    """Validated QR fields needed for the pairing proof."""

    gid: str
    seed: str
    license: str
    ek: str
    ipaddress: str

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> PairingQrData:
        """Build validated QR data from a mapping."""
        missing_fields = [field for field in REQUIRED_QR_FIELDS if field not in payload]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"QR JSON is missing required fields: {missing}")

        normalized: dict[str, str] = {}
        for field in REQUIRED_QR_FIELDS:
            value = payload[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"QR field {field!r} must be a non-empty string")
            normalized[field] = value.strip()

        return cls(
            gid=normalized["gid"],
            seed=normalized["seed"],
            license=normalized["license"],
            ek=normalized["ek"],
            ipaddress=normalized["ipaddress"],
        )


@dataclass(slots=True, frozen=True)
class GeneratedKeys:
    """PEM-encoded key material for Firewalla ETP."""

    private_pem: str
    public_pem: str


def generate_firewalla_keys() -> GeneratedKeys:
    """Generate the RSA keypair formatted exactly for Firewalla ETP."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return GeneratedKeys(private_pem=private_pem, public_pem=public_pem)


def load_qr_json(raw_json: str) -> PairingQrData:
    """Parse and validate the Firewalla QR JSON."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as err:
        raise ValueError("QR JSON is not valid JSON") from err

    if not isinstance(payload, dict):
        raise ValueError("QR JSON root must be an object")

    return PairingQrData.from_mapping(payload)


def parse_extra_fields(values: list[str]) -> dict[str, str]:
    """Parse repeated KEY=VALUE overrides for the request body."""
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid extra field {value!r}; expected KEY=VALUE")
        key, field_value = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid extra field {value!r}; empty key")
        parsed[key] = field_value
    return parsed


def build_verify_payload(
    qr_data: PairingQrData,
    public_key: str,
    extra_fields: dict[str, str],
) -> dict[str, Any]:
    """Build the default verify payload for the local pairing proof."""
    payload: dict[str, Any] = {
        "gid": qr_data.gid,
        "seed": qr_data.seed,
        "license": qr_data.license,
        "ek": qr_data.ek,
        "ipaddress": qr_data.ipaddress,
        "publicKey": public_key,
    }
    payload.update(extra_fields)
    return payload


def write_key_file(path: Path, content: str, *, force: bool) -> None:
    """Persist a PEM file to disk."""
    if path.exists() and not force:
        raise FileExistsError(
            f"Refusing to overwrite existing file {path}; rerun with --force"
        )
    path.write_text(content, encoding="utf-8")


async def post_verify(
    firewalla_ip: str,
    endpoint_path: str,
    payload: dict[str, Any],
    *,
    request_timeout: float,
    verify_tls: bool,
) -> tuple[int, str]:
    """Send the pairing proof request to the local Firewalla box."""
    url = f"https://{firewalla_ip}:8833{endpoint_path}"
    client_timeout = aiohttp.ClientTimeout(total=request_timeout)

    async with (
        aiohttp.ClientSession(timeout=client_timeout) as session,
        session.post(url, json=payload, ssl=verify_tls) as response,
    ):
        return response.status, await response.text()


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Proof-of-concept Firewalla ETP verify handshake",
    )
    qr_group = parser.add_mutually_exclusive_group(required=True)
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
        "--firewalla-ip",
        help="Override the IP address used for the verify request",
    )
    parser.add_argument(
        "--endpoint-path",
        default=DEFAULT_VERIFY_PATH,
        help=(
            "Local pairing endpoint path "
            f"(default: {DEFAULT_VERIFY_PATH})"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--verify-tls",
        action="store_true",
        help="Enable TLS certificate verification for the local HTTPS request",
    )
    parser.add_argument(
        "--extra-field",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Add a raw string field to the verify payload; repeat as needed",
    )
    parser.add_argument(
        "--print-payload",
        action="store_true",
        help="Print the JSON payload before sending the request",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate keys and payload without making the HTTPS request",
    )
    parser.add_argument(
        "--public-key-out",
        type=Path,
        default=Path("etp.public.pem"),
        help="Path to write the authorized public key on success",
    )
    parser.add_argument(
        "--private-key-out",
        type=Path,
        default=Path("etp.private.pem"),
        help="Path to write the authorized private key on success",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting existing output files",
    )
    return parser


async def async_main() -> int:
    """Run the standalone pairing proof."""
    parser = build_parser()
    args = parser.parse_args()

    raw_qr_json = args.qr_json
    if args.qr_file is not None:
        raw_qr_json = args.qr_file.read_text(encoding="utf-8")

    assert raw_qr_json is not None
    qr_data = load_qr_json(raw_qr_json)
    keys = generate_firewalla_keys()
    extra_fields = parse_extra_fields(args.extra_field)
    payload = build_verify_payload(qr_data, keys.public_pem, extra_fields)
    firewalla_ip = args.firewalla_ip or qr_data.ipaddress
    endpoint_path = args.endpoint_path
    if not endpoint_path.startswith("/"):
        raise ValueError("--endpoint-path must start with '/'")

    if args.print_payload or args.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))

    if args.dry_run:
        print("Dry run complete; no HTTPS request was sent")
        return 0

    print(f"POST https://{firewalla_ip}:8833{endpoint_path}")
    status, response_text = await post_verify(
        firewalla_ip,
        endpoint_path,
        payload,
        request_timeout=args.timeout,
        verify_tls=args.verify_tls,
    )

    print(f"HTTP {status}")
    print(response_text)

    if status != 200:
        return 1

    write_key_file(args.public_key_out, keys.public_pem, force=args.force)
    write_key_file(args.private_key_out, keys.private_pem, force=args.force)
    print(f"Saved public key to {args.public_key_out}")
    print(f"Saved private key to {args.private_key_out}")
    return 0


def main() -> int:
    """Run the async CLI entry point."""
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except (
        aiohttp.ClientError,
        TimeoutError,
        FileExistsError,
        OSError,
        ValueError,
    ) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())