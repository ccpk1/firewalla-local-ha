"""Redaction for the normalized runtime snapshot published in diagnostics.

Diagnostics are pasted into public issues, and the normalized snapshot carries
the same personal data as the raw init payload in a friendlier shape: who lives
in the house (user, group and host names), what their devices are called, their
MAC and IP addresses, the appliance serial number and DDNS name, and the public
IP and ISP from the last speed tests. ``async_redact_data`` cannot do this on its
own, because it matches the config-entry keys it is given rather than the shape
of this payload.

Two passes run over every value:

- key names are matched against the sets below, so a field keeps being redacted
  if it moves within the snapshot
- scalars are scrubbed for MAC addresses, IPv4 addresses, emails, JWTs and known
  domain suffixes, so a field nobody listed still loses its identifying content

Counts, identifiers of the box's own objects (``rule_id``, ``alarm_id``) and
network UUIDs are kept on purpose: they are what makes a report diagnosable, and
they name nothing on their own. Treat the result as reduced sensitivity rather
than as a guarantee -- the payload shape is not a published contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .init_payload_redaction import (
    redact_runtime_init_payload,
    redact_scalar,
)

_REDACTED: Final = "**REDACTED**"

# Keys that name a person, a device, or an address wherever they appear.
_IDENTIFYING_KEYS: Final = frozenset(
    {
        "affiliated_group_name",
        "associated_host_macs",
        "associated_host_names",
        "ddns",
        "dhcp_name",
        "device_ip",
        "device_name",
        "dns_domain",
        "dns_fqdn",
        "dns_hostname",
        "group_name",
        "host",
        "host_id",
        "host_ip",
        "host_name",
        "ip_address",
        "isp",
        "mac",
        "name",
        "network_name",
        "peer_id",
        "public_ip",
        "public_ips",
        "remote_host",
        "remote_ip",
        "remote_latitude",
        "remote_longitude",
        "serial_number",
        "server_host",
        "server_id",
        "server_location",
        "server_sponsor",
        "target",
        "target_name",
        "wan_ip",
        "wan_ips",
    }
)

# Keys holding a list of identifiers rather than a name: redacted as a whole so
# the count survives without publishing the values.
_IDENTIFIER_LIST_KEYS: Final = frozenset(
    {
        "applies_to",
        "scope",
        "tag_refs",
        "user_ids",
        "group_ids",
    }
)

# Raw protocol records keep their original key spelling, so they go through the
# init-payload walker, which knows `p.device.mac` and its neighbours.
_RAW_RECORD_KEYS: Final = frozenset(
    {
        "raw_payload",
        "raw_update_payload",
    }
)


def _redact_value(key: str, value: Any, *, in_raw_record: bool = False) -> Any:
    """Redact one key/value pair, recursing into containers."""
    key_lower = key.lower()

    if not in_raw_record and key_lower in _RAW_RECORD_KEYS:
        if isinstance(value, Mapping):
            return _redact_raw_record(value)
        return value

    if isinstance(value, Mapping):
        return {
            nested_key: _redact_value(nested_key, nested_value, in_raw_record=True)
            if in_raw_record
            else _redact_value(nested_key, nested_value)
            for nested_key, nested_value in value.items()
        }

    if isinstance(value, list | tuple):
        if key_lower in _IDENTIFIER_LIST_KEYS:
            return [_REDACTED for _ in value]
        return [
            _redact_value(key, item, in_raw_record=True)
            if in_raw_record
            else _redact_value(key, item)
            for item in value
        ]

    if key_lower in _IDENTIFYING_KEYS or key_lower in _IDENTIFIER_LIST_KEYS:
        return _REDACTED if value is not None else value

    return redact_scalar(value)


def _redact_raw_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Redact one raw protocol record for inclusion in diagnostics.

    Two passes, because the two name the same things differently: the init-payload
    walker knows the wire spellings (``p.device.mac``, ``p.dest.domain``) and the
    snapshot pass knows the normalized ones (``target``, ``host_name``). A rule's
    blocked domain arrived in ``raw_update_payload`` under the wire spelling and
    survived the first pass alone.
    """
    return {
        key: _redact_value(key, value, in_raw_record=True)
        for key, value in redact_runtime_init_payload(dict(record)).items()
    }


def redact_runtime_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a redacted copy of the normalized runtime snapshot."""
    return {key: _redact_value(key, value) for key, value in snapshot.items()}
