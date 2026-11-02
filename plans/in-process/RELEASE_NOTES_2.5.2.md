# Firewalla Local 2.5.2

## Summary

2.5.2 adds one service and its assistant tool, and closes the review findings on
the HACS submission. Upgrading needs no config entry change and no repairing.

- **New `firewalla_local.get_live_throughput`** and the
  `firewalla_local__get_live_throughput` assistant tool: per-host and
  per-interface bandwidth as it is right now, which no existing report could
  answer.
- **Diagnostics are redacted by shape**, so a report can be pasted into a public
  issue without publishing the household's names, devices or addresses.
- **Home Assistant 2025.10 is now genuinely supported.** The declared floor was
  eight releases short of what the code needed.
- **Reports no longer resolve a time zone on the event loop.**

Contributed by [@ferritercb](https://github.com/ferritercb), whose
`get_live_throughput` service and protocol work this release builds on.

## Live throughput

Every other usage report answers over a window: `get_network_usage` returns byte
totals for at least the last 60 minutes, `get_wan_usage` returns daily totals.
None of them can answer "what is using the bandwidth right now", because the box
keeps no per-host rate history to look back at.

`get_live_throughput` reads the box's own live sampler — the data behind the
Firewalla app's live view — and averages repeated readings across a short window.
It has to sample repeatedly: the box reports a 2-second average, and a stream
sends its next few seconds of video in a burst and is then idle, so a single
reading lands in a gap often enough to matter. Measured on a streaming 1080p
Apple TV, one reading came back zero three times in five.

### Three scopes, because they are three questions

- **one device** — `host_mac` or `host_name`. That device alone, from the box's
  own single-host query: one request, no waiting for a window, and an idle device
  answering zero rather than being left out. This is the only scope that measures
  a device, including traffic it exchanged with another device on its own segment
- **one network** — `network_uuid` or `network_name`, which accepts a WAN. A WAN
  is how to ask what the internet link is doing, and it is what the app's own
  dashboard chart shows: one cell per WAN, with download, upload and total
- **everything** — neither. Every device on every network, busiest first

The response says which it used in `scope`. Host and network selectors are
mutually exclusive.

### Reading the numbers

- **Device and network figures are not comparable, and neither is a slice of the
  other.** Network rows are interface counters; device rows are the box's
  best-effort attribution. Measured on one network they differed by 1.1× to 85×,
  and adding them together counts the same traffic twice. If an aggregate
  interface (a `bond0` trunk above its VLANs) is present, a warning names it.
- **A network figure is routed traffic only.** Two devices on the same segment
  talk through the switch, never through the box, so that traffic appears in the
  devices' own figures and not in the segment's.
- **Direction is resolved for you.** Rows carry `download_bytes_per_second`,
  `upload_bytes_per_second` and `total_bytes_per_second` rather than the box's
  raw `rx`/`tx`, which mean opposite things at each edge: on a WAN `rx` is the
  download, on a LAN it is what the LAN sent toward the box.

### Sampling

- **A short window is noisy.** Two readings miss a busy stream about a third of
  the time. The assistant tool defaults to 6 seconds, and every window up to 30
  is accepted for when the answer has to be trusted.
- **The window is reported as served, not as requested.** The sampler averages
  every 2 seconds, so an odd request is rounded up to the next even second and
  never down — a 5-second request is served 6 seconds of coverage, and the
  response says so with `sample_seconds` (served), `sample_seconds_requested`
  (the request) and a `live_throughput_window_rounded` warning.
- **A call after a quiet spell no longer halves the answer.** The box stops its
  sampler when idle, and the first reading back carries real interface traffic
  with no device attached to it yet. That used to be averaged in, scaling every
  device down; it is now retried and never counted, and the answer says
  `warming_up` if the sampler still had nothing to attribute.

`hosts.available` reports how many devices there were, beside `hosts.count` for
how many were returned.

## Diagnostics

Diagnostics exported the normalized runtime snapshot unredacted, while redacting
the raw payload beside it. The snapshot carries the same personal data in a
friendlier shape: the names of the people set up as Firewalla users, their
groups, every host name and MAC and IP address, the appliance serial number and
DDNS name, and the public IP and ISP of the last speed tests. Diagnostics get
pasted into public issues.

The snapshot is now redacted by shape rather than removed, because the counts and
the box's own object ids are what make a report diagnosable. Raw protocol records
are the exception: they are omitted, not redacted. They duplicate the normalized
fields beside them — a 193-rule capture carried 57.7 KB of rule records whose
action, target, type, scope and counters were all already published in normalized
form — so publishing them added noise without adding an answer. The report says
where one was withheld, so a reader is not misled into thinking it was empty.

A test asserts over the whole serialized payload, so a field added later that
carries a name or an address fails there instead of in an issue thread.

## Home Assistant 2025.10

`hacs.json` has declared 2025.10 since the first release, and the code needed
2026.8. Three `except A, B:` clauses — Python 3.14 syntax — do not parse on 3.13,
which is what 2025.10 runs, and two device-registry APIs differ: the call that
links a child device to its parent changed keyword, and the lookup by identifier
did not exist.

On 2026.3 to 2026.7 that was worse than a missing feature: configuring a device
tracker made setup raise. Both are now chosen by inspecting the running Home
Assistant rather than by comparing version numbers, so the next rename needs no
release. CI runs the suite against 2025.10 as well, so the declaration is enforced
instead of assumed.

The assistant tool surface still needs 2026.10 — it depends on names Core only
added there. It is absent, not broken, on older releases.

## Event loop

Report shaping resolved the time zone the box reports with the synchronous
`get_time_zone`, which reads tzdata from disk the first time a zone is resolved.
The box's zone is never the one Home Assistant loaded at startup, so that was
always a first resolution, from six async service handlers. It is now awaited.
Two more sites had the same pattern: the alarm manager's `today` expiry, and the
rule switch's state attributes, which cannot await and now use the configured
zone that was resolved at startup.

## Documentation

The reverse-engineering notes quoted thirteen excerpts of decompiled app source.
They are now descriptions of the behaviour, with the facts unchanged.

`get_network_usage` now says it returns totals over a window of at least an hour
and points at the live tool. Asked "what is using my bandwidth now", a model
landed there first and answered from hour-old totals.
