# Firewalla Local 2.5.0

## Summary

Firewalla Local **2.5.0** turns the integration into an operator surface. Your data is now
readable by AI assistants through Home Assistant's Model Context Protocol server, and the
local data plane answers questions it could not before: *what did this device or group
actually do, and what was blocked?*

It also adds **device membership control** — assign a device to a group or a user, or
release it — reports each rule's **hit count and last matched flow**, and makes every
published moment readable as a date and every derived value reproducible from its inputs.

**One thing to check before you upgrade.** This release renames attributes, service
response keys, and services so one concept keeps one name everywhere. The renames are
replacements, not additions: the old names are gone. If you have automations, templates,
scripts, or AI prompts that read those keys, read **Breaking changes** below first.

Everything else is additive. No config entry changes, and no re-pairing.

## Ask your network questions

Home Assistant's `mcp_server` integration serves any registered LLM API automatically. This
integration now registers its own, so an MCP client — ChatGPT, Claude Desktop, VS Code and
other editors, a custom agent, or Assist — can answer questions like *"how many devices are
online?"*, *"did my internet drop this week?"*, or *"which devices on my guest network used
the most bandwidth in the last hour?"* from real local data. No sidecar, no cloud
subscription.

- **39 tools** — 14 read, 16 control, and 9 destructive.
- **Five access levels**, defaulting to the most conservative: **Off**, **Summary only**,
  **Read only**, **Read and control**, and **Full**. The level is the control that governs
  what leaves your network.
- **Structural, not cosmetic.** In *Summary only* the other tools are not registered at all,
  so there is no sensitive field to filter out — there is nothing to leak. That tier answers
  general questions from counts, network names, and performance metrics, with no device
  addresses, hardware identifiers, group or user names, or public IP.
- **Graduated, and honest about the trade.** *Read only* adds device names and addresses.
  *Read and control* adds reversible actions. *Full* adds the irreversible ones —
  `delete_host`, `delete_rule`, `delete_alarms`, and the membership clears — each requiring
  an explicit `confirm: true`.
- **Every control action is admin-gated.** A non-admin user cannot change your network
  through an assistant, whatever the access level.
- **Each box is its own tool set.** Point a client at one box or several; when APIs are
  merged, Home Assistant namespaces each box's tools by the name you gave that entry, so the
  assistant always knows which box it is acting on.
- **Credentials never leave.** Pairing keys, symmetric keys, and the account token cannot
  appear in tool output at all.
- A full **MCP tool reference** is published as the spec the surface is built and tested
  against: [`docs/MCP_TOOL_REFERENCE.md`](https://github.com/ccpk1/firewalla-local-ha/blob/main/docs/MCP_TOOL_REFERENCE.md).

> **Requires Home Assistant Core 2026.10 or newer.** On older Core the integration works
> exactly as before and the AI settings are hidden rather than shown and broken.

## Trace what a device or group actually did

The Firewalla app's flow report is served entirely from your box, and the integration could
not surface any of it. It now can.

- **New `get_flow_report` service and tool.** Ask what a host or a group did in a window,
  and what was blocked. It returns a summarized view by default and raw records on request.
- **One service, not three.** The rollup, the flow log, and the block log are filters and
  resolution levels over the same data, so a group report and a device report are the same
  code path with a different target.
- **Honest about the window.** Firewalla silently serves a narrower window than you ask for
  instead of rejecting it. The window actually served is read back from the response and
  reported, so you can see what you really got.
- **Identity is gated, and off by default.** Flow records carry user identity, so that
  resolution is opt-in rather than on by name.
- A record distinguishes a **destination port** (`port`) from a **port on the host**
  (`host_port`), and `destination_kind` is `domain` / `host` / `ip` / `peer`, where `peer`
  is a LAN peer named by its id.

## Assign devices to groups and users

Group membership turned out to be writable locally, and a user assignment is the same write
with a different tag — so one contract covers both.

- **New `set_host_membership` service**, plus four tools (`set_host_group`, `clear_host_group`,
  `set_host_user`, `clear_host_user`).
- **The collection model was wrong and is now fixed.** The group list was built from Firewalla's
  raw tag map, so it contained user backing tags as well as real groups — 10 of 28 entries on
  the development box. Every entry now carries a `group` / `user` kind, and group and user
  counts are reported from that one classification so they can never disagree.
- **Backing tag names are not shown.** Most are bare UUIDs and two are stale human labels, so
  rendering them would leak UUIDs or a misleading name. The user's display name is used
  instead.
- **Membership changes delete the device's rules.** Firewalla does this, so the service does
  too, and it says so rather than letting you discover it.

## Rules report their activity

A rule switch could go stale with no way to see why. Rules now carry their hits and their
last match.

- **`hit_count` and the last matched flow** are published on the rule switch and in
  `get_rules`, so you can see whether a rule is doing anything.
- **`hit_count` is always numeric**, so a template comparing it never has to guard against a
  missing value.
- **New `get_rules` service** — a non-admin, scoped rule listing, for target discovery and for
  finding what an alarm's block created.
- **New `create_rule` service** (admin-gated) with an optional alarm reference and auto-archive,
  so blocking an alarm target is ordinary rule creation rather than a parallel rule store.
- **Blocks stay rules.** There is deliberately no separate block/unblock service — one place
  to manage enforcement, not two.

## Every moment is readable, and every derived value is reproducible

Two defects, which are the same defect: a published value the reader cannot reproduce.

- **Instants are readable.** A timestamp of `1791258075.36` tells you nothing. Every published
  moment now appears twice: a date as `<name>_at`, and epoch seconds as
  `<name>_at_timestamp`. If you were parsing a date string to compare two times, read the
  `_timestamp` twin instead.
- **Derived values carry their inputs.** `online` is not a fact about a host — it is
  `reference - last_active <= window`. Measured on a live box, the old surface contradicted
  itself: the overview reported a VPN peer online while the host list reported all five peers
  offline, seconds apart, because the reference was derived from the peer's own subset. The
  reference instant and the window are now published beside the value:

  ```jinja
  {{ (state_attr('binary_sensor.my_device','activity_reference_at_timestamp')
      - state_attr('binary_sensor.my_device','last_active_at_timestamp'))
     <= state_attr('binary_sensor.my_device','online_window_seconds') }}
  ```

  `stale` participates too: a host the box has not seen in about a week is offline however
  recent its activity stamp looks.
- **A pause now says whether it will resume on its own**, instead of reporting only that it is
  paused.

## Breaking changes

**Read this section if you have automations, templates, or scripts that read entity attributes
or service-response keys.** The renames below are renames, not additions: the old names are
gone rather than aliased, so anything reading them stops working. Each row names the old value
and its replacement.

**There is no compatibility layer, deliberately.** An alias would leave two names meaning one
thing, which is the defect this work exists to remove. The tables below are the migration.

### Renamed attributes and keys

`host` is the word this integration uses for a Firewalla endpoint, on every surface, so the
keys and the labels shown in the UI now both say it. Nothing about the data changed — only the
names. If you used the attribute **name** shown in the UI, it changed too, from *"Devices
online"* to *"Hosts online"* and so on.

| Entity / service | Was | Now |
| --- | --- | --- |
| `binary_sensor` system status | `devices_online` / `devices_offline` / `devices_total` | `hosts_online` / `hosts_offline` / `hosts_total` |
| `binary_sensor` system status | `vpn_devices_online` / `_offline` / `_total` | `vpn_hosts_online` / `_offline` / `_total` |
| `binary_sensor` network | `device_count` | `host_count` |
| `binary_sensor` watched host | `device_group` | `host_group` |
| `device_tracker` presence | `device_group` | `host_group` |
| `sensor` watched user usage | `associated_devices` / `associated_device_count` / `associated_device_group` | `associated_hosts` / `associated_host_count` / `associated_host_group` |
| `binary_sensor` alarm | `device_name` | `host_name` |
| `binary_sensor` network top talkers | `device_name` | `host_name` |

`device_tracker` is a Home Assistant platform name, not this integration's vocabulary, so it
keeps its name and its behaviour.

The same rename applies where those values are returned by a service: `get_runtime_inventory`
reports `hosts_online` / `hosts_offline` / `hosts_total`, and the network list in
`get_system_overview` reports `host_count`.

**Rule matches, membership, and flow rows were renamed too.** These keys appear inside service
responses and tool results:

| Service / tool | Was | Now |
| --- | --- | --- |
| `get_rules` (`last_hit`) | `device_id` / `device_ip` / `device_port` | `host_id` / `host_ip` / `host_port` |
| `get_time_usage` | `device_id` / `device_name` | `host_id` / `host_name` |
| `get_network_config` host rows | `device_type` | `host_device_type` |
| `get_network_config` summary | `device_host_count` | *(removed — it duplicated `host_count`)* |
| `get_flow_report` member and record rows | `device_id` / `device_name` / `device_ip` / `device_ids` | `host_id` / `host_name` / `host_ip` / `host_ids` |
| `get_flow_report` `destination_kind` | `"device"` (a LAN peer) | `"peer"` |
| `get_system_overview` sections | `devices` / `vpn_devices` | `hosts` / `vpn_hosts` |
| `get_network_usage` section and provenance | `devices` | `hosts` |
| `get_network_usage` summary | `active_device_count` | `active_host_count` |
| `get_time_usage` app and category rows | `devices` | `hosts` |
| `get_time_usage` provenance | `apps.devices.intervals` | `apps.hosts.intervals` |
| `get_network_usage` host rows | `conn` / `dns` / `dns_blocked` / `ip_blocked` / `ip_denied` / `ntp` | `connection_count` / `dns_count` / `blocked_dns_count` / `blocked_ip_count` / `denied_ip_count` / `ntp_count` |
| host records in `get_hosts`, the network `hosts` include, `get_network_usage`, and `get_time_usage` | `ip_address` | `host_ip` |
| `get_network_config` `sections.configuration` | `kind` | `network_kind` |
| `get_network_config` `sections.configuration` | `type` | `interface_type` |
| `get_rules` (tag-scoped rules only) | `target: "TAG"` | `target: null` — read `applies_to` / `applies_to_kind` / `tag_refs` instead |
| `get_rules` | *(absent)* | `applies_to_kind` added — names what each `applies_to` entry is (`group` / `user` / `network`) |
| `set_host_group` / `set_host_user` and the group/journal variant | `device_rules.removed` | `host_rules.removed` |

**Every response dropped its `config_entry_id` echo.** The integration instance is already
bound to one Firewalla setup, and the value was only ever the id the caller passed in, so it
carried nothing. Nothing replaces it, because nothing can vary: a tool call reaches exactly
one setup.

Firewalla's own payloads call these `device` (`deviceIP`, `devicePort`, `deviceTags`). That
word is not echoed here, because in Home Assistant a *device* is a device-registry entry — a
different concept.

### Renamed time attributes and keys

Three things changed, and they can be adopted independently:

- **Renames**, where a name did not say what the value measured.
- **Pairs**, where a date or a number was published without the other form.
- **A basis**, where a derived value is now published alongside the reference instant and
  window it was measured in. This one is additive: the old keys still work.

| Entity / service | Was | Now |
| --- | --- | --- |
| `binary_sensor` watched host, `device_tracker` presence, `sensor` watched user | `last_active` | `last_active_at`, with `last_active_at_timestamp` for the epoch form |
| `binary_sensor` alarm `fired_at` | epoch number | `fired_at` is now the date; read `fired_at_timestamp` for the number |
| `binary_sensor` alarm | *(absent)* | `fired_at_timestamp` added |
| `switch` rule, `get_rules` | `pause_until` | unchanged form; `pause_until_timestamp` added |
| `get_rules` `last_hit` | `at` / `timestamp` | `matched_at` / `matched_at_timestamp` |
| `get_flow_report` records | `timestamp` | `occurred_at` (date) with `occurred_at_timestamp` |
| `get_wan_events` | `timestamp` / `timestamp_iso` | `occurred_at_timestamp` / `occurred_at` |
| `get_network_usage` metric samples | `timestamp` / `timestamp_iso` | `sampled_at_timestamp` / `sampled_at` |
| `get_internet_quality` | `sampled_at` | unchanged form; `sampled_at_timestamp` added |
| `binary_sensor` system status | `runtime_data_updated_at` | unchanged form; `runtime_data_updated_at_timestamp` added |
| `sensor` speed test | `tested_at` | unchanged form; `tested_at_timestamp` added |
| `get_runtime_inventory` rule records | `activated_time` / `updated_time` / `last_activated_time` | `activated_at` / `updated_at` / `last_activated_at`, each with an `_at_timestamp` twin |
| `get_runtime_inventory` rule records | `expires_at` (epoch) / `pause_until` (epoch) | both are dates now, matching the rule service; read `expires_at_timestamp` / `pause_until_timestamp` for the numbers |
| `get_time_usage`, `get_wan_usage`, `get_network_config`, `get_network_usage` | `begin_timestamp_iso` / `end_timestamp_iso` / `anchor_timestamp_iso` | `begin` / `end` / `anchor`, beside the existing `_timestamp` forms |
| `get_hosts`, `get_system_overview`, `get_runtime_inventory` | *(absent)* | `activity_reference_at` / `activity_reference_at_timestamp` / `online_window_seconds` added |

Timezone is unchanged. Times stay UTC unless a value is explicitly a local-time report
boundary, where the offset is part of the string and `time_zone` names the zone.

### Renamed services and MCP tools

One operation now has one name, whether a model asks for it or an automation calls it.
Fourteen reads and eight controls named the same operation differently depending on the layer.

| Was | Now |
| --- | --- |
| `get_network_segment_report` | `get_network_config` |
| `get_network_segment_usage` | `get_network_usage` |
| `get_wan_data_usage` | `get_wan_usage` |
| `get_time_usage_report` | `get_time_usage` |
| `get_internet_quality_report` | `get_internet_quality` |
| `get_speed_test_results` | `get_speed_tests` |
| `get_host_name_mapping` | `get_hosts` |
| tool `list_hosts` | tool `get_hosts` |
| tool `list_rules` | tool `get_rules` |
| tool `get_user_usage` | tool `get_time_usage` |
| tool `set_alarm_muted` | tool `mute_alarm` |

Ten tools are deliberately narrower than the service they call — the four membership tools
share one `set_host_membership` service, the single-object and bulk alarm tools share
`archive_alarms` / `delete_alarms`, and `block_alarm_target` / `unblock_alarm_target` use the
generic rule services. Those keep their own names.

### Reads now report their source and freshness

`get_alarms` reads the cached snapshot by default, with `refresh: true` to poll the box. It
previously polled on every call, which meant it could not see an archive made moments earlier
in the same session. Because the snapshot holds only the active set, `include_archived` now
**requires** `refresh: true` and is refused otherwise, rather than polling behind a read that
reports itself as cached.

Every control result also carries a new `runtime` field: `updated` when the call already
changed the local snapshot, so an immediate read agrees with it, and `pending` when it did
not. Read it instead of assuming a write is visible.

## Other

- **Service access is now 20 admin-gated, 14 open.** The write surface is protected; every
  read service stays open, so dashboards, wall displays, and reporting keep working for every
  user. Automations and scripts are unaffected — Home Assistant only enforces the admin check
  when a call carries a signed-in user.
- **New `get_system_overview` service** — one call for box, network, host, and rule counts.
- **New `sync_runtime` service** and its diagnostic button, to force an immediate local refresh.
- **`get_hosts` is the renamed `get_host_name_mapping`**, and it now reports each host's network.
- **Internet quality faults surface.** Latency and packet-loss quality events are now requested,
  so they appear instead of being silently absent.
- **Top talkers are real.** The usage ranking families are now requested, so the ranking is
  built from what the box actually returns.
- **One numeric policy.** Seven duplicated numeric coercers were consolidated, and every boolean
  encoding the box sends is read — including the ones that are not `true`/`false`.
- **A boundary guard.** `utils/` and `api/` can no longer import Home Assistant, enforced by a
  test rather than by convention.
- **`get_alarms` is bounded**, and each alarm reports the host's network.

### ❤️ **Support the Project**

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/ccpk1)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/ccpk1)

## Upgrading

Go to HACS → Integrations → Firewalla Local and install version **2.5.0**, then restart Home
Assistant. No config entry changes are needed — an existing setup continues to work, and no
re-pairing is required.

**Before upgrading, check your automations and templates against Breaking changes.** The
renames are the only part of this release that can break an existing setup, and they fail
loudly (a key is missing) rather than silently.

If you use the AI assistant tools, they need Home Assistant Core 2026.10 or newer; on older
Core the integration works exactly as before and the setting is hidden.
