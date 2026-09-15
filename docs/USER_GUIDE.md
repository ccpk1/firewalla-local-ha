# Firewalla Local user guide

## Overview

Firewalla Local is a Home Assistant custom integration for connecting to one
Firewalla box over the verified local protocol.

This guide is organized around the main jobs you can do with the integration:

- install and pair the box
- choose which monitoring surfaces you want exposed
- understand the main Firewalla device entities and refresh behavior
- monitor watched devices, watched users, and device trackers
- operate hosts and rules from Home Assistant
- call the local report services added after 1.0.0

## What the integration provides

Firewalla Local can expose these main surface areas:

- Firewalla appliance monitoring on the main router device
- a diagnostic `Sync runtime` button on the main router device
- per-network status binary sensors for every LAN, VLAN, VPN, and WAN
- per-SSID status binary sensors and toggle switches for every wireless network
  when Firewalla AP7 access points are present
- per-AP system-status binary sensors on a dedicated device per access point
  when Firewalla AP7 access points are present
- watched-device binary sensors for selected endpoints
- watched-user usage sensors for selected Firewalla users
- router-based `device_tracker` entities for selected MAC-backed LAN clients
- rule-backed switches for supported persistent Firewalla rules
- operator services for hosts, networks, WANs, and reports

## Service catalog at a glance

Services that already existed in 1.0.0:

- `firewalla_local.pause_rule`
- `firewalla_local.resume_rule`
- `firewalla_local.get_runtime_inventory`

Services added after 1.0.0:

- `firewalla_local.get_host_name_mapping`
- `firewalla_local.get_network_segment_report`
- `firewalla_local.get_network_segment_usage`
- `firewalla_local.run_internet_speed_test`
- `firewalla_local.wake_host`
- `firewalla_local.delete_host`
- `firewalla_local.set_host_name`
- `firewalla_local.set_host_dns_hostname`
- `firewalla_local.set_host_device_type`
- `firewalla_local.set_host_notify_when_next_online`
- `firewalla_local.set_host_notify_when_next_offline`
- `firewalla_local.set_host_dhcp_reservation`
- `firewalla_local.get_speed_test_results`
- `firewalla_local.get_internet_quality_report`
- `firewalla_local.get_time_usage_report`
- `firewalla_local.get_wan_data_usage`
- `firewalla_local.get_wan_events`
- `firewalla_local.get_wireless_status`
- `firewalla_local.set_ssid_paused`
- `firewalla_local.get_admin_capabilities`
- `firewalla_local.admin_read`
- `firewalla_local.admin_execute`
- `firewalla_local.admin_rollback_network_config`

## Installation

### One-click HACS install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=erabti&repository=firewalla-local-ha&category=integration)

### Manual HACS setup

1. Ensure HACS is installed.
2. In Home Assistant, open **HACS -> Integrations -> Custom repositories**.
3. Add `https://github.com/erabti/firewalla-local-ha` as an **Integration** repository.
4. Search for **Firewalla Local**, install it, and restart Home Assistant.

### Add the integration and pair your device

Because this integration communicates entirely locally, it uses the same secure
pairing process as adding a secondary phone to your Firewalla.

> Warning
> Security notice: local credential persistence and unpairing
>
> This integration uses Firewalla's official Additional Pairing flow to
> communicate directly with your Firewalla box over your local network.
>
> Testing indicates Firewalla may return a local credential bundle that is tied
> to the Firewalla box rather than uniquely to one Home Assistant instance.
> This bundle includes the values Home Assistant stores for local access, such
> as `symmetric_key`, `gid`, `aid`, and `eid`.
>
> Removing the Home Assistant paired-device entry in the Firewalla mobile app
> should not be treated as a guaranteed revocation of those already-cached local
> credentials. If the Home Assistant config entry still exists and still holds a
> valid local credential bundle, the integration may continue to read local
> Firewalla data.
>
> To fully remove the integration from Home Assistant, delete the Firewalla
> Local config entry from **Settings -> Devices & Services** so Home Assistant
> removes the stored local credentials. You may also remove the paired-device
> entry from the Firewalla app to keep the paired-device list clean.
>
> Current testing does not prove which Firewalla action rotates or invalidates
> the underlying local credential bundle. Do not assume that simple unpairing in
> the mobile app alone revokes local access.

**Step 1: Start the Home Assistant setup**

1. Open **Settings -> Devices & Services -> Add Integration**.
2. Search for and select **Firewalla Local**.
3. **Local hostname or IP address:** Leave this as the default `fire.walla`
   for most setups. If you have custom DNS routing, replace it with the
   Firewalla's local IP address such as `192.168.1.1`.

**Step 2: Generate the pairing code in the Firewalla app**

1. Open the Firewalla app on your phone.
2. Open **Settings -> Advanced -> Allow Additional Pairing**.
3. Turn it on. A QR code appears on screen.

**Step 3: Extract the raw QR JSON**

1. Take a screenshot of the QR code in the Firewalla app.
2. Open the screenshot in your phone's photo app.
3. Use your phone's QR or text recognition tools to copy the raw QR content.
4. Copy the full JSON payload.

**Step 4: Complete the connection**

1. Paste the exact raw JSON into the **Raw QR JSON** field in Home Assistant.
2. Submit the form.
3. Let the integration validate the local runtime and create the entities.

> **A note on pairing security:** The QR JSON is not a permanent master key.
> It is time-limited, requires local network access, and is used in an
> encrypted token exchange.

## Removal

### Remove the Home Assistant integration entry

1. Open **Settings -> Devices & Services**.
2. Open the **Firewalla Local** integration.
3. Choose **Delete** to remove the config entry.

This removes the integration-managed entities for that entry from Home
Assistant.

### Remove the custom repository

If you installed through HACS and no longer want the integration available:

1. Remove the Firewalla Local integration entry from Home Assistant.
2. Remove the repository from HACS custom repositories if you added it
   manually.
3. Remove the installed integration from HACS.
4. Restart Home Assistant.

## Data updates and refresh behavior

Firewalla Local uses local polling.

- the integration refreshes the runtime snapshot every 3 minutes by default
- you can change the polling interval in the options flow between 1 and 10
  minutes
- Home Assistant entities reflect the latest successful refresh
- the main Firewalla device also exposes a `Sync runtime` button so you can
  request an immediate refresh on demand
- successful rule actions may update the in-memory state immediately for a more
  responsive UI
- later coordinator refreshes remain the source of truth
- the integration does not create its own custom persistent cache of live
  Firewalla runtime state between restarts

If the Firewalla box is temporarily unavailable, the integration marks data as
unavailable and resumes normal state updates after a successful refresh.

If you want to confirm how fresh the current runtime is, check the
system-status attribute `runtime_data_updated_at` on the main Firewalla device.

## Options flow

Use the integration options flow to manage which runtime surfaces you want in
Home Assistant.

- **Manage rule selection:** Choose which supported Firewalla rules should be
  exposed as Home Assistant switches.
- **Manage watched devices:** Choose which endpoints should appear as
  watched-device connectivity binary sensors.
- **Manage watched users:** Choose which Firewalla users should appear as
  watched-user daily-usage sensors.
- **Manage device trackers:** Choose which MAC-backed LAN clients should appear
  as Home Assistant router-based device trackers.
- **Manage network entities:** Toggle per-network status binary sensors for
  every LAN, VLAN, VPN, and WAN.
- **Manage SSID entities:** Toggle per-SSID status binary sensors and toggle
  switches for every wireless network when Firewalla AP7 access points are
  present.
- **General options:** Adjust the local polling interval and timing settings
  without re-pairing the box.

## Main Firewalla device

The main Firewalla router device is the anchor device for appliance monitoring
and management surfaces.

It currently exposes:

- a system-status binary sensor
- WAN-scoped speed-test download, upload, and latency sensors
- WAN-scoped internet-quality ping latency and packet-loss sensors
- a diagnostic `Sync runtime` button
- per-network status binary sensors (LAN, VLAN, VPN, WAN)
- per-SSID status binary sensors and toggle switches when AP7 access points
  are present

### System-status binary sensor

The system-status entity exposes stable attributes such as:

- uptime and `uptime_seconds`
- boot-complete and cloud-connected state
- firmware release type and DDNS
- WAN IP summary
- current WAN usage summary
- total, online, and offline device counts
- CPU, memory, and disk summary values
- `ports` with per-port link state, speed (Mbps), and MAC address
- `bluetooth_mac` for the box's Bluetooth radio
- `timezone` for the box's configured time zone
- `runtime_data_updated_at` showing when the current runtime snapshot was last
  refreshed successfully

Use this entity when you want a quick appliance-health view plus a stable set
of status attributes for automations or dashboards.

### WAN-scoped speed-test sensors

Each discovered WAN gets three speed-test sensors: download, upload, and
latency. Each sensor exposes the latest successful speed test result from the
local payload for that WAN.

The sensor state is the metric named by the entity, and every speed-test sensor
also includes the full speed-test metadata in its attributes, including upload
speed, latency, jitter, packet loss, server details, timestamp, WAN name, and
WAN UUID.

### WAN-scoped internet-quality sensors

Each discovered WAN gets two internet-quality sensors: **ping latency** and
**ping packet loss**. These reflect the Firewalla box's continuous per-WAN
Internet Quality monitoring, sampled every 15 minutes against a ping target
(Cloudflare `1.1.1.1` by default).

- the latency sensor state is the latest sample's **mean** latency in
  milliseconds
- the packet-loss sensor state is the latest sample's loss as a percentage
- every internet-quality sensor also exposes the full sample in its attributes:
  `ping_target`, `sampled_at`, `ping_latency`, `ping_latency_max`,
  `ping_latency_median`, `ping_latency_min`, `ping_packet_loss`, `wan_name`,
  and `wan_uuid`

These sensors are always created per WAN (like the speed-test sensors) and can
be disabled per-entity in Home Assistant if you do not want them.

### Sync runtime button

The main Firewalla device also includes a diagnostic `Sync runtime` button.
Use it when you want to trigger an immediate refresh instead of waiting for the
next polling interval. After a successful refresh, the system-status entity's
`runtime_data_updated_at` attribute updates to the latest runtime snapshot
time.

## Per-network monitoring

When enabled, the integration creates one status binary sensor per Firewalla
network, mirroring the network list in the Firewalla app. This covers LAN,
VLAN, VPN, and WAN surfaces.

- enable or disable this surface in the options flow with **Enable network
  status entities**
- each entity's state reflects whether the network is currently configured and
  enabled
- each entity exposes a stable set of attributes describing the network

The per-network attributes include:

- network kind (LAN, VLAN, VPN, or WAN)
- VLAN ID and ethernet ports when applicable
- IPv4/IPv6 addresses and subnets, gateway, and DNS servers
- DHCP configuration
- device count
- advanced options such as mDNS/SSDP Relay and Block ICMP
- a compact usage summary, including current-month WAN usage where available

Use these entities for a live, per-network health and usage view on your
dashboards. For a deeper configuration or usage drill-down, use the
`get_network_segment_report` and `get_network_segment_usage` services instead.

## Per-SSID wireless monitoring and control (AP7)

When Firewalla AP7 access points are present, the integration creates one
status binary sensor and one toggle switch per wireless network (SSID),
mirroring the wireless network list in the Firewalla app. Both entities attach
to the main Firewalla box device, which is the controller of the SSIDs.

**Control: turn a full SSID network on or off**

- each toggle switch **turns the entire wireless network (SSID) on or off** —
  switch **on** enables (unpauses) the network, switch **off** pauses it
- the pause/resume is a **global SSID-level control across all AP7 access
  points** — toggling one SSID affects that network everywhere in the house
- the switch state reflects the current paused state and updates immediately
  on toggle (optimistic), then reconciles with the next coordinator refresh
- you can also drive the same control in automations with the
  `set_ssid_paused` service

- enable or disable this surface in the options flow with **Enable SSID status
  entities**
- each binary sensor's state reflects whether the wireless network is currently
  enabled (not paused)
- each entity exposes a stable set of attributes describing the wireless
  network

The per-SSID attributes include:

- SSID name
- band (e.g. 2.4g+5g+6g)
- encryption and WPA3 state
- VLAN ID and interface when applicable
- paused state

Use these entities for a live, per-wireless-network status and control view on
your dashboards. For a structured read of the full wireless configuration, use
the `get_wireless_status` service; to pause or resume one SSID from an
automation, use the `set_ssid_paused` service.

## Per-AP device monitoring (AP7)

When Firewalla AP7 access points are present, the integration creates one Home
Assistant device per access point, linked to the main Firewalla box device as
its parent. Each AP device carries a system-status binary sensor that reflects
whether the access point is currently present in the runtime payload.

The per-AP status attributes include:

- AP name and model
- 5 GHz and 2.4 GHz channel
- LED state
- TX power, country, mesh mode, and timezone
- pause-WiFi and disable-ACL state
- live client count (from the switch topology)

Use these entities for a per-access-point health and coverage view on your
dashboards. The AP device name follows the Firewalla app (the source of record);
entity IDs stay stable until you regenerate them from the Home Assistant device
management screen.

> Note: per-AP `pauseWifi` is surfaced as a read-only attribute today. It is
> not yet exposed as a toggle switch; per-AP wireless control remains a
> separate, deferred surface. The per-SSID toggle switches (documented in the
> previous section) provide global wireless control across all APs.

## Watched-device monitoring

Watched devices are opt-in. After selecting devices in the options flow, the
integration creates one watched-device binary sensor per selected Firewalla
host identity.

- watched-device selection can include MAC-backed hosts and standalone VPN peer
  identities such as `wg_peer:*` when the local runtime exposes them as host
  records

- each watched-device entity exposes a connectivity-style online or offline
  state
- attributes include local IP address, device group, network name, connection
  type when available, upload and download totals, and last activity time
- when the current switch topology places the device on an AP7 access point,
  the entity also exposes conditional WiFi attributes:
  - `topology_connection_type` — `wired` or `wireless`
  - for wireless connections only: `wifi_ssid`, `wifi_band`, `wifi_rssi`, and
    `wifi_ap` (the access-point name it is attached to)
- if a selected device disappears from the current Firewalla payload, the
  entity remains in Home Assistant and becomes unavailable instead of being
  silently removed

The integration always requests the full host inventory, including devices the
Firewalla app would only show with its "Show past devices" setting enabled
(devices that have not been online in the past 7 days). A watched device that
is present but inactive is therefore reported as offline rather than removed
from the inventory, so it stays associated with its configured entity and
name.

## Watched-user monitoring

Watched users are opt-in. After selecting users in the options flow, the
integration creates one watched-user sensor per selected Firewalla user.

- each watched-user entity exposes today's total usage minutes as the primary
  state
- today's primary total prefers the proven
  `internetTimeUsageToday.totalMins` field when the local payload exposes it
- if the payload omits a total counter, the integration falls back to the
  available per-app totals instead of inventing a separate value
- attributes include associated device group when present, associated device
  names, associated device count, unique usage minutes today, per-app usage
  totals, and a manager-derived `last_active` value based on associated hosts
- `unique_usage_today` remains separate because Firewalla exposes it as a
  distinct raw field and it is not guaranteed to equal the primary total
- `app_usage_by_app` is sourced from the proven `appTimeUsageToday` payload and
  only includes apps with positive usage
- if a selected user disappears from the current Firewalla payload, the entity
  remains in Home Assistant and becomes unavailable instead of being silently
  removed

## Device-tracker monitoring

Device trackers are opt-in. After selecting eligible devices in the options
flow, the integration creates one Home Assistant `device_tracker` entity per
selected MAC-backed LAN client.

- each selected device tracker creates a distinct tracked-client device in Home
  Assistant and links it back to the primary Firewalla router device
- the tracker entity is attached to that tracked-client device and uses the
  standard router-tracker states `home`, `not_home`, or unavailable
- the tracker friendly name follows Home Assistant's translated sub-entity
  pattern as `<device name> Presence`
- entity IDs are stable at creation and are not auto-regenerated when the
  device is renamed; if you want an entity ID to reflect a new device name,
  regenerate it manually from the Home Assistant device management screen
- attributes include IP address, device group, network name, connection type,
  and last-active time when those values are available in the current runtime
  snapshot
- only MAC-backed LAN clients are eligible for device trackers
- pseudo-hosts and non-LAN identities such as `wg_peer:*`, VPN, tunnel, and
  overlay-style records are intentionally excluded
- if a selected tracked client disappears from the current Firewalla payload,
  the tracker remains in Home Assistant and becomes unavailable instead of
  being silently removed

### Device-tracker timing behavior

- device trackers use their own away window setting in the options flow
- this away window is separate from the watched-device online window
- the integration does not invent richer presence states beyond `home`,
  `not_home`, and unavailable

The integration always requests the full host inventory, including devices the
Firewalla app would only show with its "Show past devices" setting enabled
(devices that have not been online in the past 7 days). A tracked client that is
present but inactive is still classified by the away window, so it reports
`not_home` rather than unavailable. Because the host remains in the inventory,
its tracker stays associated with the client device and keeps its name.

### Device-tracker lifecycle behavior

- deselecting a device tracker removes the integration-managed tracker entity
  and tracked-client device for that config entry
- reloading or temporarily unloading the config entry preserves the registry
  identity so the tracker and tracked-client device come back with the same
  entity and device identity on setup

## Rule-backed switches

Only a supported subset of Firewalla rules can be exposed as Home Assistant
switches.

At a high level, the integration only exposes rules that fit the proven
persistent user-managed switch model. It does not try to turn every Firewalla
rule into a switch.

In practice:

- user-managed persistent rules from the supported rule families (allow, block, disturb, QoS, and **route**) may appear in the options flow
- Firewalla-managed or automatically generated rules are excluded
- temporary or auto-expiring rule shapes are excluded from switch selection
- if a previously selected rule later disappears, Home Assistant can still show
  enough context for you to remove the stale selection cleanly

### Persistent rules versus temporary rules

Persistent rules:

- stay installed in Firewalla until you explicitly change or delete them
- can be paused and resumed in place
- are the rule family that the integration can expose as Home Assistant
  switches when they match the supported rule model

Temporary rules:

- are created for a short-lived timed action
- expire or disappear automatically instead of remaining installed as a normal
  paused rule
- are not treated as switch candidates by this integration

The guarded admin service can also create, update, or delete rules through the
confirmed local protocol. Use `get_admin_capabilities` to discover the current
command list and run `admin_execute` in its default dry-run mode before writing.

## Services

The service surface is now broad enough that it helps to think about it in
three groups:

- inspection and report services
- host and network operator actions
- rule control services
- guarded expert administration services

The report-style services in this section were built primarily to help model,
correlate, and validate Firewalla data during reverse engineering.

- treat them as operator tools first, not as a fully refined long-term public
  reporting API
- they should be directionally correct and useful for automations, debugging,
  and ongoing protocol work
- the shared report envelope and major section names are more stable than the
  fine-grained field selection and presentation details

### Service groups

Inspection and report services:

- `firewalla_local.get_runtime_inventory`
- `firewalla_local.get_host_name_mapping`
- `firewalla_local.get_network_segment_report`
- `firewalla_local.get_network_segment_usage`
- `firewalla_local.get_speed_test_results`
- `firewalla_local.get_internet_quality_report`
- `firewalla_local.get_time_usage_report`
- `firewalla_local.get_wan_data_usage`
- `firewalla_local.get_wan_events`
- `firewalla_local.get_wireless_status`

Host and network operator actions:

- `firewalla_local.run_internet_speed_test`
- `firewalla_local.wake_host`
- `firewalla_local.delete_host`
- `firewalla_local.set_host_name`
- `firewalla_local.set_host_dns_hostname`
- `firewalla_local.set_host_device_type`
- `firewalla_local.set_host_notify_when_next_online`
- `firewalla_local.set_host_notify_when_next_offline`
- `firewalla_local.set_host_dhcp_reservation`

Wireless control services:

- `firewalla_local.set_ssid_paused`

Rule control services:

- `firewalla_local.pause_rule`
- `firewalla_local.resume_rule`

Guarded expert administration services:

- `firewalla_local.get_admin_capabilities`
- `firewalla_local.admin_read`
- `firewalla_local.admin_execute`
- `firewalla_local.admin_rollback_network_config`

### Guarded local administration

The expert administration surface covers the confirmed local catalog for device
and group policies, tag or group lifecycle, rule CRUD, WAN/VLAN/LAN/Wi-Fi
configuration, network-interface changes, VPN client profiles, virtual WAN
groups, data-plan settings, DNS settings, categories, and exceptions. It does
not expose the excluded shell, credential, migration, power, or firmware
commands listed below.

Start with `firewalla_local.get_admin_capabilities`. It returns:

- `read_items`: safe local configuration and status reads
- `set_items`: configuration values written with Firewalla's `set` message
- `command_items`: actions written with Firewalla's `cmd` message
- `excluded_items`: shell, credential, migration, power, and firmware commands
  intentionally unavailable through this generic service
- `safeguards`: the write gates enforced by the manager

Use `firewalla_local.admin_read` with an item from `read_items`. For example,
read the complete router configuration:

```yaml
action: firewalla_local.admin_read
data:
  item: networkConfig
```

The response includes `config_hash`. The manager also keeps the raw configuration
in a bounded in-memory snapshot cache so rollback does not require exposing
secrets. Sensitive response fields such as passwords, tokens, private keys, and
certificates are replaced with `[redacted]`.

Use `firewalla_local.admin_execute` first without changing its defaults. It
returns the exact planned message and does not write:

```yaml
action: firewalla_local.admin_execute
data:
  item: tag:create
  value:
    name: Guests
```

To execute, set both write gates:

```yaml
action: firewalla_local.admin_execute
data:
  item: tag:create
  value:
    name: Guests
  dry_run: false
  confirm: true
```

Common management payloads:

| Task | Item | Target and value |
| --- | --- | --- |
| Create a device group | `tag:create` | `value: {name: Guests}` |
| Rename a device group | `tag` | target is the tag UID; value contains `name` |
| Delete a device group | `tag:remove` | value contains `uid` or `name` |
| Assign device policy or group | `policy` | target is the host MAC; value is the host policy patch |
| Create a rule | `policy:create` | value is the Firewalla rule object |
| Update a rule | `policy:update` | value includes `pid` and changed rule fields |
| Delete a rule | `policy:delete` | value contains `policyID` |
| Save a VPN profile | `saveVpnProfile` | value contains `type`, `profileId`, profile data, and settings |
| Start or stop VPN | `startVpnClient` / `stopVpnClient` | value contains `type` and `profileId` |
| Delete a VPN profile | `deleteVpnProfile` | value contains `type` and `profileId` |
| Manage virtual WAN groups | `createOrUpdateVirtWanGroup` / `removeVirtWanGroup` | value follows the live Firewalla object |

`networkConfig` is the complete FireRouter configuration and therefore covers
WAN, LAN, VLAN, routes, DHCP, DNS, wireless, and Smart Queue references present
in that object. Callers provide only an RFC 7396-style merge patch: omitted and
redacted values are preserved, while `null` removes a key. The integration
applies that patch to a fresh raw read before sending Firewalla's required full
object. It has two extra gates:

1. `admin_execute` always calls Firewalla's native `networkConfigImpact` check.
2. Execution requires `expected_current_hash` copied from a fresh
   `admin_read` response. A stale hash is rejected.

Example network dry run:

```yaml
action: firewalla_local.admin_execute
data:
  item: networkConfig
  value: {}  # Safe no-op merge patch for checking the impact path
```

After reviewing `impact`, execute with `dry_run: false`, `confirm: true`, and
the fresh `expected_current_hash`. Set `refresh: false` when the network change
may briefly interrupt Home Assistant's path to the router.

To roll back, call `admin_rollback_network_config` with the original
`config_hash`. Dry run is still the default. Execution requires a fresh current
hash, `dry_run: false`, and `confirm: true`. Raw snapshots live only in memory
and are lost when the integration reloads or Home Assistant restarts; Firewalla's
own `networkConfigHistory` remains available through `admin_read` for recovery.

This is an expert protocol surface. `get_admin_capabilities` states what the
installed integration permits; the exact fields inside each value are defined
by the Firewalla firmware running on the box and can change with firmware.
The complete static catalog and payload examples are in
[`ADMIN_CONTROL.md`](ADMIN_CONTROL.md).

### Get rule and runtime inventory

Use `firewalla_local.get_runtime_inventory` to inspect the current runtime data.

- useful for rule discovery, group and user correlation, and debugging the
  normalized runtime model
- returns structured `inventory` data plus a rendered `markdown` summary
- unlike the newer report services, it predates the shared report envelope

### Get host name mapping

Use `firewalla_local.get_host_name_mapping` to read the current normalized host
identity records.

- lightweight lookup for host IDs, MACs, IPs, names, and host kind
- `refresh` defaults to `true`
- MAC-backed hosts appear as `kind=mac_host`
- non-MAC pseudo-hosts can still appear as `kind=pseudo_host`

### Get network segment report

Use `firewalla_local.get_network_segment_report` to read one configuration-
oriented report for a single network segment.

- use `network_uuid` for deterministic automations or `network_name` for
  interactive use
- returns the full network detail in one call: kind, VLAN ID, ethernet ports,
  IPv4/IPv6 + DHCP, DNS, advanced options (mDNS/SSDP Relay, Block ICMP), device
  count, per-host configuration, and a compact windowed usage summary
- uses the shared report envelope with `target`, `query`, `time_basis`,
  `summary`, `sections`, and `metadata`
- for a deep per-device/app/series drill-down use
  `firewalla_local.get_network_segment_usage` instead

### Get network segment usage

Use `firewalla_local.get_network_segment_usage` to read one usage-oriented
report for a single network segment.

- choose one required `window`
- use `top_n` to limit ranking rows
- use `include=series` only when you need raw metric samples
- public windows are `last_60_minutes`, `last_24_hours`, `last_30_days`, and
  `last_12_months`

### Run internet speed test

Use `firewalla_local.run_internet_speed_test` to start a speed test on one WAN.

- choose the WAN with `wan_uuid` or `wan_name`
- if only one WAN is available, you can omit the WAN selector
- the service returns an acknowledgement and does not wait for the completed
  measurement
- if you want completed results, use `firewalla_local.get_speed_test_results`
  or the WAN-scoped speed-test sensors

### Wake host

Use `firewalla_local.wake_host` to send a Wake-on-LAN command to one host.

- choose one host with `host_mac`, `host_name`, or `host_id`
- `host_mac` is best for deterministic automations
- `refresh` defaults to `true`
- the service returns an acknowledgement with the resolved host and command
  details

### Delete host

Use `firewalla_local.delete_host` to permanently remove one or more host
devices from the Firewalla box. It is a destructive action and requires
explicit acknowledgement.

- **destructive confirmation:** you must set `confirm: true`; without it the
  service aborts. There is no undo — the device is permanently removed and
  re-adding requires it coming back online
- **one or many hosts:** provide `host_mac` as a comma-separated list of MAC
  addresses
- **skip on unmatched:** a MAC that does not resolve to a current host is
  skipped (reported as `skipped`/`not_found`), not treated as a fatal error —
  the remaining hosts are still processed
- the service returns a per-host result envelope showing each MAC's status
  (`success`, `failed`, or `skipped`/`not_found`)
- `refresh` defaults to `true`
- deleting a host that is also in your watched-device or device-tracker lists
  simply stops appearing in those choices after the next refresh; the saved
  option lists are not modified

### Host rename

Use `firewalla_local.set_host_name` to send one host-scoped rename command.

- choose one host with `host_mac`, `host_name`, or `host_id`
- provide the exact `new_name` string you want Firewalla to store
- this writes the Firewalla custom host name, not the DNS hostname override
- `refresh` defaults to `true`

### Host DNS hostname override

Use `firewalla_local.set_host_dns_hostname` to send one host-scoped DNS
hostname override through the captured `hostDomain` path.

- choose one host with `host_mac`, `host_name`, or `host_id`
- provide the exact `dns_hostname` string you want Firewalla to store
- this is separate from `set_host_name` and targets DNS naming rather than the
  Firewalla display or custom host name
- `refresh` defaults to `true`

### Host device type

Use `firewalla_local.set_host_device_type` to set one Firewalla host device
type through the captured `feedback.device.detect` path.

- choose one host with `host_mac`, `host_name`, or `host_id`
- provide one supported `host_device_type` value from the current runtime
  category set
- `refresh` defaults to `true`
- supported values are `desktop`, `phone`, `tablet`, `wearable`,
  `personal_default`, `console`, `smart speaker`, `tv`, `projector`,
  `entertainment_default`, `switch`, `automation`, `iot_default`,
  `peripheral`, `router`, `camera`, `network_default`, `nas`, `printer`,
  `security`, `sensor`, `car browser`, `business`, `medical`, and `ap`

### Host notification toggles

Use `firewalla_local.set_host_notify_when_next_online` and
`firewalla_local.set_host_notify_when_next_offline` to control host-scoped
notification toggles.

- both services reuse the same host selectors as `wake_host`
- set `enabled` to `true` or `false`
- `refresh` defaults to `true`

### Host DHCP reservation

Use `firewalla_local.set_host_dhcp_reservation` to set or clear one
host-scoped DHCP reservation on one Firewalla network.

- choose one host with `host_mac`, `host_name`, or `host_id`
- choose one network with `network_uuid` or `network_name`
- for `mode=static`, provide `reserved_ipv4`
- for `mode=dynamic`, omit `reserved_ipv4` to clear the reservation
- static reservations are validated against the resolved network range and
  existing reservations
- `refresh` defaults to `true`

### Get speed test results

Use `firewalla_local.get_speed_test_results` to read normalized speed test
results.

- by default it refreshes once and returns only the most recent result
- use `limit` to request more than one record
- use `wan_uuid` or `wan_name` to filter to one WAN when needed

### Get internet quality report

Use `firewalla_local.get_internet_quality_report` to read normalized
internet-quality samples (ping latency and packet loss) for one or all WANs.

- by default it refreshes once and returns only the most recent sample
- use `limit` to request more than one sample (the runtime keeps ~24 hours of
  15-minute buckets)
- use `wan_uuid` or `wan_name` to filter to one WAN when needed
- each sample includes `sampled_at`, `ping_target`, `ping_latency_ms`,
  `ping_latency_max_ms`, `ping_latency_median_ms`, `ping_latency_min_ms`,
  `ping_packet_loss_percent`, `wan_uuid`, and `wan_name`

### Get time usage report

Use `firewalla_local.get_time_usage_report` to read scoped historical usage for
one device, group, or user.

- set `scope_kind` to `device`, `group`, or `user`
- set `scope_target` to a stable id or current display label
- provide explicit `begin`, `end`, and `granularity`
- uses the shared report envelope
- supports `sections`, `include=intervals`, `detail=summary`, and
  `detail=standard`

### Get WAN data usage

Use `firewalla_local.get_wan_data_usage` to read one normalized WAN data-usage
report for each WAN.

- by default it returns one current-month report row for every discovered WAN
- use `wan_uuid` or `wan_name` to filter to one WAN when needed
- use `current_periods`, `history_period`, `history_count`, `detail`, and
  `include=subperiods` to shape the report
- uses the shared report envelope

### Get WAN events

Use `firewalla_local.get_wan_events` to read normalized WAN health timeline
events.

- by default it returns the most recent events across all WANs
- use `wan_uuid` or `wan_name` to filter to one WAN when needed
- use `limit` and `offset` to page through older events

### Pause rule

Use `firewalla_local.pause_rule` to pause a managed rule.

- intended for an existing persistent rule that already exists on the box
- provide `rule_target`
- optionally provide `duration` or `resume_at`
- if you provide neither, the rule remains paused until resumed

### Resume rule

Use `firewalla_local.resume_rule` to resume a paused managed rule immediately.

Like `pause_rule`, this operates on an existing persistent rule rather than
creating a new rule for you.

### Get wireless status

Use `firewalla_local.get_wireless_status` to read the current Firewalla
wireless configuration as structured data.

- returns the SSID profiles (SSID, band, encryption, WPA3, paused state, VLAN,
  interface) and the access points (name, model, channels, LED, TX power,
  country, mesh mode, timezone, pause-WiFi/ACL state, and client count)
- for Firewalla boxes without AP7 access points, the returned sections are
  empty

### Set SSID paused

Use `firewalla_local.set_ssid_paused` to pause or resume one wireless network
(SSID profile).

- provide `ssid_profile_id` — either the profile UUID or the SSID name (e.g.
  "Universe Guest")
- provide `enabled` — `true` to enable (unpause) the network, `false` to pause
  it
- the pause applies to the SSID across all AP7 access points (a global
  SSID-level control, not per-AP)
- the per-SSID toggle switches expose the same control as native entities

## Reauthentication and host changes

- if credentials stop working, Home Assistant can trigger reauthentication with
  a fresh QR payload
- if the local host changes, use the integration reconfigure flow instead of
  deleting and re-adding the device

## Known limitations

- discovery is not implemented
- only the currently supported rule subset is exposed as switches
- watched-device VPN state is intentionally deferred until the host-to-VPN
  mapping is proven
- system-level online and offline device counts may use integration-derived
  aggregation when the raw payload does not expose a trustworthy aggregate
  online flag
- watched-user totals currently rely on the proven `internetTimeUsageToday` and
  `appTimeUsageToday` user payloads
- watched-user entities do not expose a last-app-used field because that value
  is not yet proven in the local contract
- current WAN usage is exposed as a status-sensor attribute for summary and
  automation use, not as separate per-WAN entities
- broader mutation surfaces remain intentionally out of scope until they are
  proven by protocol evidence
- this is a community integration and not an official Firewalla support
  channel

## Troubleshooting pairing

If pairing fails, start with the simplest checks first.

Before collecting any packet capture, update to the latest Firewalla Local
build and try pairing again. The pairing process was reworked to match the
native Firewalla app flow more closely, so the first retry after updating may
already succeed without any additional troubleshooting.

### Basic checks

1. Confirm Home Assistant can reach the Firewalla local address you entered.
  If `fire.walla` does not resolve correctly on your network, retry with the
  Firewalla LAN IP instead. For reference, communication occurs over port 8833.
2. Generate a fresh QR code in the Firewalla app and copy the raw JSON again.
  The QR payload is time-limited, so stale content can fail even when the
  rest of the setup is correct.
3. Make sure Home Assistant has outbound internet access during pairing.
  The long-term data path is local, but the initial pairing flow includes a
  cloud-brokered credential exchange.
4. Make sure your Home Assistant instance is not isolated from the Firewalla
  management IP by VLAN or firewall policy.

### Enable debug logging before first pairing

If the integration has not been configured successfully yet, use manual Home
Assistant logger configuration before retrying.

Add this to your Home Assistant configuration:

```yaml
logger:
  default: warning
  logs:
    custom_components.firewalla_local: debug
```

Then restart Home Assistant and retry pairing.

This is the most reliable way to capture first-pair failures because there may
not be a config entry yet, which means entry-scoped diagnostics are not always
available.

### If an entry already exists

If Firewalla Local already appears in **Settings -> Devices & Services**, you
can usually enable debug logging from the Home Assistant UI for the integration
and then retry the failing action.

If the entry loads successfully, you can also download integration diagnostics.
Diagnostics are useful for existing entries, but they do not replace the log
capture for a first-time pairing failure.

### What to capture for support

If pairing still fails after updating and retrying, the next step is a paired
comparison capture. The current support workflow is designed to stay simple and
usually takes around 10 minutes.

When asking for help, try to include:

1. Whether you used `fire.walla` or a direct IP address
2. Whether this is a first-time pairing or a reauthentication attempt
3. One successful phone pairing capture from the same environment
4. One Home Assistant pairing-attempt capture from the updated integration
5. The Home Assistant log output from the failed attempt after debug logging
   was enabled
6. Diagnostics from the integration UI if the config entry already exists

The Windows capture helper generates a local safe report zip from cleartext
packet metadata so you can usually share the comparison output without sending
the raw `.pcap` publicly.

The pairing logs now distinguish QR validation, cloud provisioning, and local
runtime validation failures, which makes support triage much more direct.
