"""Typed protocol models for Firewalla Local pairing and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .exceptions import FirewallaValidationError

REQUIRED_QR_FIELDS = ("gid", "seed", "license", "ek", "ipaddress")


@dataclass(slots=True, frozen=True)
class PairingQrData:
    """Validated QR fields needed for the pairing flow."""

    gid: str
    seed: str
    license: str
    ek: str
    ipaddress: str
    device_name: str | None
    raw_payload: dict[str, Any]

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> PairingQrData:
        """Build validated QR data from a mapping."""
        missing_fields = [field for field in REQUIRED_QR_FIELDS if field not in payload]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise FirewallaValidationError(
                f"QR JSON is missing required fields: {missing}"
            )

        normalized: dict[str, str] = {}
        for field in REQUIRED_QR_FIELDS:
            value = payload[field]
            if not isinstance(value, str) or not value.strip():
                raise FirewallaValidationError(
                    f"QR field {field!r} must be a non-empty string"
                )
            normalized[field] = value.strip()

        device_name = payload.get("deviceName")
        if not isinstance(device_name, str) or not device_name.strip():
            device_name = None

        return cls(
            gid=normalized["gid"],
            seed=normalized["seed"],
            license=normalized["license"],
            ek=normalized["ek"],
            ipaddress=normalized["ipaddress"],
            device_name=device_name,
            raw_payload=dict(payload),
        )


@dataclass(slots=True, frozen=True)
class GeneratedKeys:
    """PEM-encoded key material for Firewalla ETP."""

    private_pem: str
    public_pem: str


@dataclass(slots=True, frozen=True)
class PairingCode:
    """Decrypted QR pairing object used for cloud rendezvous."""

    rendezvous_id: str
    evalue: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ETPIdentity:
    """Authenticated ETP identity returned by login/eptoken."""

    access_token: str
    eid: str
    aid: str
    groups: list[dict[str, Any]]


@dataclass(slots=True, frozen=True)
class GroupFetchResult:
    """Outcome of one cloud group fetch attempt."""

    source: str
    status: int
    groups: list[dict[str, Any]]


@dataclass(slots=True, frozen=True)
class FirewallaProvisionedCredentials:
    """Durable credentials recovered from cloud provisioning."""

    license: str
    host: str
    gid: str
    eid: str
    aid: str
    symmetric_key: str
    box_name: str | None
