# Firewalla Local 2.5.0 — release notes draft

> **Draft.** This is the working source for the GitHub release body for 2.5.0.
> The migration tables in §2 are the authoritative list of breaking changes and
> were moved here out of `docs/USER_GUIDE.md`, because they describe one upgrade
> step rather than how the integration works.
>
> **This branch ships as `2.5.0-beta.2`**, a prerelease of these notes. It is the
> second beta: `2.5.0-beta.1` was tagged before the flow-reporting, time-state and
> vocabulary work below, so everything in §1 is new since that tag. Publish these
> notes for the prerelease, then reuse them for the final 2.5.0 — the beta is a
> name for the same content, not a separate set of notes.
>
> Before publishing, confirm every item still matches the code — the same
> discipline the user guide is held to.

## Summary

2.5.0 makes the local data plane readable by AI assistants through Home
Assistant's Model Context Protocol server, and extends the integration well
beyond monitoring into a local operator toolkit: host actions, alarm triage,
flow and time reporting, and per-network and per-SSID control.

The read surface was also renamed so one operation has one name, and reads now
report where their data came from and how fresh it is.

## Breaking changes

**Read this section if you have automations, templates, or scripts that read entity
attributes or service-response keys.** The renames below are renames, not additions:
the old names are gone rather than aliased, so anything reading them stops working.
Each row names the old value and its replacement.

### Renamed attributes and keys

**If you read these attributes or service-response keys in an automation or template,
they were renamed.** `host` is the word this integration uses for a Firewalla endpoint,
on every surface, so the keys and the labels shown in the UI now both say it. Nothing
about the data changed — only the names.

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

The same rename applies where those values are returned by a service, so
`get_runtime_inventory` reports `hosts_online` / `hosts_offline` / `hosts_total`, and
the network list in `get_system_overview` reports `host_count`.

**Rule matches, membership and flow rows were renamed too.** These keys appear inside
service responses and tool results:

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
| host records in `get_hosts`, the network `hosts` include, `get_network_usage` and `get_time_usage` | `ip_address` | `host_ip` |
| `get_network_config` `sections.configuration` | `kind` | `network_kind` |
| `get_network_config` `sections.configuration` | `type` | `interface_type` |
| `get_rules` (tag-scoped rules only) | `target: "TAG"` | `target: null` — read `applies_to` / `applies_to_kind` / `tag_refs` instead |
| `get_rules` | *(absent)* | `applies_to_kind` added — names what each `applies_to` entry is (`group` / `user` / `network`) |
| `set_host_group` / `set_host_user` and the group/journal variant | `device_rules.removed` | `host_rules.removed` |

**The watched-device `ip_address` attribute is now `host_ip`** on the entity as well
as in service responses, so one concept keeps one name everywhere it is published.

**Every response dropped its `config_entry_id` echo.** The integration instance is
already bound to one Firewalla setup, and the value was only ever the id the caller
passed in, so it carried nothing. Nothing replaces it, because nothing can vary: a
tool call reaches exactly one setup.

In a flow record, `port` is the destination's port and `host_port` is the port on the
host. `host_id` is not always a MAC: a VPN peer's id is not one. `destination_kind`
is `domain` / `host` / `ip` / `peer`, where `peer` is a LAN peer named by its id
rather than by a name or an address.

Firewalla's own payloads call these `device` (`deviceIP`, `devicePort`, `deviceTags`).
That word is not echoed here, because in Home Assistant a *device* is a device-registry
entry — a different concept.

### Renamed time attributes and keys

**Every published moment now appears twice and names what it is an instant of.** A date
is the readable form (`<name>_at`); epoch seconds are the arithmetic form
(`<name>_at_timestamp`). If you read or parse a time value in an automation or template,
the key may have changed and the form you were reading may now be on its twin.

Three things changed, and they can be adopted independently:

- **Renames**, where a name did not say what the value measured.
- **Pairs**, where a date or a number was published without the other form. If you were
  parsing `"2026-03-26T21:00:00+00:00"` to compare two times, read the `_timestamp` twin
  instead — no parsing needed.
- **A basis**, where a derived value such as `online` is now published alongside the
  reference instant and window it was measured in. This is additive: the old keys still
  work, and the new ones let you reproduce the value.

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

**`online` is derived, and now reproducible.** It is
`activity_reference_at_timestamp - last_active_at_timestamp <= online_window_seconds`,
and all three inputs are published beside it. To check one host in a template:

```jinja
{{ (state_attr('binary_sensor.my_device','activity_reference_at_timestamp')
    - state_attr('binary_sensor.my_device','last_active_at_timestamp'))
   <= state_attr('binary_sensor.my_device','online_window_seconds') }}
```

`stale` also participates: a host the box has not seen in about a week is offline
however recent its activity stamp looks.

**There is no compatibility layer.** These are renames, not additions, so the old names
are gone rather than aliased — an alias would leave two names meaning one thing, which is
the problem this set of changes exists to remove. The tables above are the migration.

**Timezone is unchanged.** Times stay UTC unless a value is explicitly a local-time
report boundary, where the offset is part of the string and `time_zone` names the zone.

If you used the attribute **name** shown in the UI, it changed too, from *"Devices
online"* to *"Hosts online"* and so on — the labels and the keys now agree.

**What did not change:** `device_tracker` entities. That is a Home Assistant platform,
not this integration's vocabulary, and it keeps its name and its behavior.

### Renamed services and MCP tools

One operation now has one name, whether the model asks for it or an automation calls
it. Fourteen reads and eight controls named the same operation differently depending
on the layer. Internal identifiers that embedded the old service names were renamed
with them, except `_RAW_*`, which mirrors the box's own field names.

| Was | Now |
| --- | --- |
| `get_network_segment_report` | `get_network_config` |
| `get_network_segment_usage` | `get_network_usage` |
| `get_wan_data_usage` | `get_wan_usage` |
| `get_time_usage_report` | `get_time_usage` |
| `get_internet_quality_report` | `get_internet_quality` |
| `get_speed_test_results` | `get_speed_tests` |
| tool `list_hosts` | tool `get_hosts` |
| tool `list_rules` | tool `get_rules` |
| tool `get_user_usage` | tool `get_time_usage` |
| tool `set_alarm_muted` | tool `mute_alarm` |

Ten tools are deliberately narrower than the service they call — the four
membership tools share one `set_host_membership` service, the single-object and bulk
alarm tools share `archive_alarms` / `delete_alarms`, and `block_alarm_target` /
`unblock_alarm_target` use the generic rule services. Those keep their own names.

### Reads now report their source and freshness

`get_alarms` reads the cached snapshot by default, with `refresh: true` to poll the
box. It previously polled on every call, which meant it could not see an archive made
moments earlier in the same session. Because the snapshot holds only the active set,
`include_archived` now **requires** `refresh: true` and is refused otherwise rather
than polling behind a read that reports itself as cached.

Every control result also carries a new `runtime` field: `updated` when the call
already changed the local snapshot, so an immediate read agrees with it, and
`pending` when it did not. Read it instead of assuming a write is visible.

## Upgrading

Go to HACS → Integrations → Firewalla Local and install version **2.5.0-beta.2** (or
2.5.0 once it is out), then restart Home Assistant. No config entry changes are needed —
an existing setup continues to work, and no re-pairing is required.

**Before upgrading, check your automations and templates against §2.** The renames are
the only part of this release that can break an existing setup, and they fail loudly
(a key is missing) rather than silently.

If you use the AI assistant tools, note that they need Home Assistant Core 2026.10 or
newer; on older Core the integration works exactly as before and the setting is hidden.

## Support the project

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/ccpk1)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/ccpk1)
