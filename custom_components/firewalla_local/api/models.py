"""Typed protocol models for Firewalla Local pairing and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, TypedDict

from .exceptions import FirewallaValidationError

_QR_FIELD_GID: Final = "gid"
_QR_FIELD_SEED: Final = "seed"
_QR_FIELD_LICENSE: Final = "license"
_QR_FIELD_EK: Final = "ek"
_QR_FIELD_IPADDRESS: Final = "ipaddress"
_QR_FIELD_DEVICE_NAME: Final = "deviceName"

REQUIRED_QR_FIELDS: Final = (
    _QR_FIELD_GID,
    _QR_FIELD_SEED,
    _QR_FIELD_LICENSE,
    _QR_FIELD_EK,
    _QR_FIELD_IPADDRESS,
)


class PairingQrPayload(TypedDict, total=False):
    """Validated QR payload fields used during provisioning."""

    gid: str
    seed: str
    license: str
    ek: str
    ipaddress: str
    deviceName: str


class SymmetricKeyRecord(TypedDict, total=False):
    """Encrypted symmetric key entry returned by the cloud API."""

    key: str


class CloudGroupRecord(TypedDict, total=False):
    """Linked cloud group record used to recover local credentials."""

    _id: str
    eid: str
    aid: str
    symmetricKeys: list[SymmetricKeyRecord]


class LoginIdentityPayload(TypedDict, total=False):
    """Decoded login/eptoken response payload."""

    access_token: str
    eid: str
    aid: str
    groups: list[CloudGroupRecord]


@dataclass(slots=True, frozen=True)
class PairingQrData:
    """Validated QR fields needed for the pairing flow."""

    gid: str
    seed: str
    license: str
    ek: str
    ipaddress: str
    device_name: str | None
    raw_payload: PairingQrPayload

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> PairingQrData:
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

        device_name = payload.get(_QR_FIELD_DEVICE_NAME)
        if not isinstance(device_name, str) or not device_name.strip():
            device_name = None

        return cls(
            gid=normalized[_QR_FIELD_GID],
            seed=normalized[_QR_FIELD_SEED],
            license=normalized[_QR_FIELD_LICENSE],
            ek=normalized[_QR_FIELD_EK],
            ipaddress=normalized[_QR_FIELD_IPADDRESS],
            device_name=device_name,
            raw_payload={
                _QR_FIELD_GID: normalized[_QR_FIELD_GID],
                _QR_FIELD_SEED: normalized[_QR_FIELD_SEED],
                _QR_FIELD_LICENSE: normalized[_QR_FIELD_LICENSE],
                _QR_FIELD_EK: normalized[_QR_FIELD_EK],
                _QR_FIELD_IPADDRESS: normalized[_QR_FIELD_IPADDRESS],
                **(
                    {_QR_FIELD_DEVICE_NAME: device_name}
                    if device_name is not None
                    else {}
                ),
            },
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
    evalue: dict[str, object]


@dataclass(slots=True, frozen=True)
class ETPIdentity:
    """Authenticated ETP identity returned by login/eptoken."""

    access_token: str
    eid: str
    aid: str
    groups: list[CloudGroupRecord]


@dataclass(slots=True, frozen=True)
class GroupFetchResult:
    """Outcome of one cloud group fetch attempt."""

    source: str
    status: int
    groups: list[CloudGroupRecord]


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
