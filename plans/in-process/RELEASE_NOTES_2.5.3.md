# Firewalla Local 2.5.3

2.5.3 closes the redaction gaps left in the diagnostics added by 2.5.2.
Upgrading needs no config entry change and no repairing.

## Diagnostics

Three kinds of value still reached a report unredacted.

- **Alarm messages are redacted.** `alarms[].message` was published verbatim
  beside the redacted `device_name` on the same record, and it names the watched
  device and what it went to.
- **Values inside identifying mappings are redacted.** The redaction checked a
  key after recursing into it, so a mapping whose name is itself identifying —
  `public_ips` — was walked first and its entries came back intact. The key check
  now runs before the recursion.
- **IPv6 addresses are covered.** The scalar scrub matched dotted-quad addresses
  only, so `2001:db8::1`, `fe80::…` and `::ffff:203.0.113.7` were published as
  they were. Mapped-IPv4 forms are matched first so their tail is consumed with
  them, and the pattern stops at an address boundary, so a `12:34:56`, a
  `host:8833` and a `bond0.10` are left alone.

User and group ids stay as they are. They are opaque box ids like `rule_id`, and
they are what makes an alarm diagnosable.

## Tests

A test now walks every string field reachable from the runtime snapshot model and
fails unless that field is redacted or declared published on purpose. The
declared list is checked against the model in both directions, so it cannot go
stale, and a field added later fails there instead of in an issue thread. The
fixture carries an alarm message and a dual-stack `public_ips` value.

## Documentation

The reverse-engineering notes quoted decompiled app source in Finding 44. They
describe the behaviour now, with the facts unchanged.

The `get_live_throughput` documentation claimed the single-host scope does not
wait for an averaging window. It does: a burst looks the same whether you are
watching one device or sixty. The service description, the assistant tool
description and the user guide say so.
