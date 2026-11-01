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

Raw protocol records are the one exception to "redact, do not drop": they are
omitted, because they duplicate the normalized fields beside them and are large.
See ``_OMITTED_RECORD_KEYS``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .init_payload_redaction import redact_scalar

_REDACTED: Final = "**REDACTED**"
_OMITTED: Final = "**OMITTED**"

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

# Raw protocol records are omitted rather than redacted. They duplicate the
# normalized fields beside them -- a 193-rule capture carried 57.7 KB of rule
# records whose `action`, `target`, `type`, `scope` and counters are all already
# published in normalized form -- so publishing them adds noise to a report
# without adding an answer. They were added to investigate fields the model does
# not surface yet, which is a local task, not a public-issue one.
#
# The marker keeps the fact that they existed, because a reader triaging a report
# needs to know something was withheld rather than absent.
_OMITTED_RECORD_KEYS: Final = frozenset(
    {
        "raw_payload",
        "raw_update_payload",
    }
)


def _redact_value(key: str, value: Any) -> Any:
    """Redact one key/value pair, recursing into containers."""
    key_lower = key.lower()

    if key_lower in _OMITTED_RECORD_KEYS:
        if isinstance(value, Mapping):
            return f"{_OMITTED} ({len(value)} raw protocol keys)"
        return _OMITTED

    if isinstance(value, Mapping):
        return redact_runtime_snapshot(value)

    if isinstance(value, list | tuple):
        if key_lower in _IDENTIFIER_LIST_KEYS:
            return [_REDACTED for _ in value]
        return [_redact_value(key, item) for item in value]

    if key_lower in _IDENTIFYING_KEYS or key_lower in _IDENTIFIER_LIST_KEYS:
        return _REDACTED if value is not None else value

    return redact_scalar(value)


def redact_runtime_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a redacted copy of the normalized runtime snapshot."""
    return {key: _redact_value(key, value) for key, value in snapshot.items()}
