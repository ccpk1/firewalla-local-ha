"""Best-effort redaction for the raw Firewalla runtime init payload.

The raw init payload is a large, unnormalized blob that contains far more
sensitive data than the normalized runtime snapshot. The generic
``async_redact_data`` helper only redacts exact config-entry keys, which do not
match the raw payload's field names. This module walks the raw payload and
redacts known sensitive keys plus common sensitive value patterns (JWTs, MAC
addresses, IPv4 addresses, and the embedded license/JWT material).

This is a best-effort pass: the payload shape is not a published contract, so
new fields may appear that are not covered here. Treat the output as
"reduced sensitivity", not a guarantee of full sanitization.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

_REDACTED: Final = "**REDACTED**"

# Keys whose values are always sensitive regardless of location.
_SENSITIVE_KEYS: Final = frozenset(
    {
        "jwt",
        "ddnstoken",
        "btmac",
        "cpuid",
        "publicip",
        "publicips",
        "ddns",
        "firstbinding",
        "sshts",
        "localdomainsuffix",
        "license",
        "serial",
        "serialnumber",
        "mac",
        "mac_address",
        "gatewaymac",
        "publickey",
        "privatekey",
        "psk",
        "key",
        "secret",
        "password",
        "token",
        "stamp",
        "email",
        "uuid",
        "eid",
        "gid",
        "aid",
        "devid",
        "ssid",
        "url",
    }
)

# Keys that are sensitive only when they appear under a host record.
_HOST_SENSITIVE_KEYS: Final = frozenset(
    {
        "ip",
        "ipv6",
        "name",
        "bname",
        "dhcpname",
        "bonjourname",
        "localdomain",
        "userlocaldomain",
        "macvendor",
        "recentactivity",
        "openports",
        "names",
        "detect",
    }
)

# Keys that are sensitive only when they appear under a WireGuard peer record.
_WG_PEER_SENSITIVE_KEYS: Final = frozenset(
    {
        "name",
        "allowedips",
        "publickey",
        "uid",
        "devid",
    }
)

# Keys that are sensitive only when they appear under a speed-test record.
_SPEEDTEST_SENSITIVE_KEYS: Final = frozenset(
    {
        "publicip",
        "host",
        "ip",
        "name",
    }
)

# Top-level sections that are not relevant to the wireless/AP7 investigation
# and carry a large amount of sensitive data (personal names, traffic flows,
# usage history, metrics). These are dropped entirely from the export rather
# than redacted, which preserves traceability in the retained sections while
# removing the bulk of the sensitive data.
_EXCLUDED_TOP_LEVEL_KEYS: Final = frozenset(
    {
        "usertags",
        "internetspeedtestresults",
        "systemflows",
        "last60",
        "last30",
        "newlast24",
        "last12months",
        "latestallstateevents",
        "lateststateeventserror",
        "networkmonitorevents",
        "customizedcategories",
        "devicetags",
        "tags",
        "sysmetrics",
        "monthlydatausage",
        "monthlydatausageonwans",
        "networkmetrics",
        "newalarms",
    }
)

_MAC_RE: Final = re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")
_IPV4_RE: Final = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")
_JWT_RE: Final = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_EMAIL_RE: Final = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# Matches a private/internal domain suffix (e.g. "int.ccpk.us", "ha.ccpk.us")
# and any subdomains of it (e.g. "www.googleapis.com.int.ccpk.us").
_DOMAIN_SUFFIX_RE: Final = re.compile(
    r"(?i)(?:[a-z0-9-]+\.)*[a-z0-9-]+\.(?:ccpk\.us|local|lan|internal|home)"
)


def _redact_scalar(value: Any) -> Any:
    """Redact sensitive value patterns from a scalar string."""
    if not isinstance(value, str):
        return value
    redacted = _JWT_RE.sub(_REDACTED, value)
    redacted = _MAC_RE.sub(_REDACTED, redacted)
    redacted = _IPV4_RE.sub(_REDACTED, redacted)
    redacted = _EMAIL_RE.sub(_REDACTED, redacted)
    redacted = _DOMAIN_SUFFIX_RE.sub(_REDACTED, redacted)
    return redacted


def _redact_host(host: Mapping[str, Any]) -> dict[str, Any]:
    """Redact one host record."""
    return {
        key: (
            _REDACTED
            if key.lower() in _SENSITIVE_KEYS or key.lower() in _HOST_SENSITIVE_KEYS
            else _redact_payload(value, _is_host=key.lower() == "policy")
        )
        for key, value in host.items()
    }


def _redact_wg_peer(peer: Mapping[str, Any]) -> dict[str, Any]:
    """Redact one WireGuard peer record."""
    return {
        key: (
            _REDACTED
            if key.lower() in _WG_PEER_SENSITIVE_KEYS
            else _redact_payload(value, _is_wg_peer=True)
        )
        for key, value in peer.items()
    }


def _redact_speedtest(record: Mapping[str, Any]) -> dict[str, Any]:
    """Redact one speed-test record."""
    return {
        key: (
            _REDACTED
            if key.lower() in _SPEEDTEST_SENSITIVE_KEYS
            else _redact_payload(value, _is_speedtest=True)
        )
        for key, value in record.items()
    }


def _redact_payload(
    value: Any,
    *,
    _is_host: bool = False,
    _is_wg_peer: bool = False,
    _is_speedtest: bool = False,
) -> Any:
    """Recursively redact a portion of the init payload."""
    if isinstance(value, Mapping):
        return {
            _redact_key(key): _redact_value(
                key,
                value,
                _is_host=_is_host,
                _is_wg_peer=_is_wg_peer,
                _is_speedtest=_is_speedtest,
            )
            for key, value in value.items()
        }
    if isinstance(value, list):
        return [
            _redact_payload(
                item,
                _is_host=_is_host,
                _is_wg_peer=_is_wg_peer,
                _is_speedtest=_is_speedtest,
            )
            for item in value
        ]
    return _redact_scalar(value)


def _redact_key(key: str) -> str:
    """Redact sensitive value patterns from a dict key."""
    if not isinstance(key, str):
        return key
    redacted = _JWT_RE.sub(_REDACTED, key)
    redacted = _MAC_RE.sub(_REDACTED, redacted)
    redacted = _IPV4_RE.sub(_REDACTED, redacted)
    redacted = _EMAIL_RE.sub(_REDACTED, redacted)
    redacted = _DOMAIN_SUFFIX_RE.sub(_REDACTED, redacted)
    return redacted


def _redact_value(
    key: str,
    value: Any,
    *,
    _is_host: bool,
    _is_wg_peer: bool,
    _is_speedtest: bool,
) -> Any:
    """Redact one key/value pair based on its context."""
    key_lower = key.lower()

    if key_lower in _SENSITIVE_KEYS:
        return _REDACTED

    if _is_host and key_lower in _HOST_SENSITIVE_KEYS:
        return _REDACTED
    if _is_wg_peer and key_lower in _WG_PEER_SENSITIVE_KEYS:
        return _REDACTED
    if _is_speedtest and key_lower in _SPEEDTEST_SENSITIVE_KEYS:
        return _REDACTED

    # Recurse into nested structures, propagating context.
    if isinstance(value, Mapping):
        return {
            _redact_key(nested_key): _redact_value(
                nested_key,
                nested_value,
                _is_host=_is_host,
                _is_wg_peer=_is_wg_peer,
                _is_speedtest=_is_speedtest,
            )
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [
            _redact_payload(
                item,
                _is_host=_is_host,
                _is_wg_peer=_is_wg_peer,
                _is_speedtest=_is_speedtest,
            )
            for item in value
        ]
    return _redact_scalar(value)


def redact_runtime_init_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a best-effort redacted copy of the raw runtime init payload."""
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        key_lower = key.lower()

        if key_lower in _EXCLUDED_TOP_LEVEL_KEYS:
            continue

        if key_lower == "hosts":
            redacted[key] = [
                _redact_host(host) if isinstance(host, Mapping) else host
                for host in value
            ]
            continue
        if key_lower == "wgpeers":
            redacted[key] = [
                _redact_wg_peer(peer) if isinstance(peer, Mapping) else peer
                for peer in value
            ]
            continue
        if key_lower == "internetspeedtestresults":
            redacted[key] = [
                _redact_speedtest(record) if isinstance(record, Mapping) else record
                for record in value
            ]
            continue

        redacted[key] = _redact_value(
            key,
            value,
            _is_host=False,
            _is_wg_peer=False,
            _is_speedtest=False,
        )
    return redacted
