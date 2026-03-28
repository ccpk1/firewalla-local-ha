# Firewalla Local user guide

## Overview

Firewalla Local is a Home Assistant custom integration for connecting to one
Firewalla box over the verified local protocol.

- pairing and reauthentication
- runtime polling
- appliance monitoring
- watched-device monitoring
- watched-user monitoring
- selected rule-backed switches
- runtime inventory reporting
- pause and resume services

## Installation

### One-click HACS install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ccpk1&repository=firewalla-local-ha&category=integration)

### Manual HACS setup

1. Ensure HACS is installed.
2. In Home Assistant, open **HACS -> Integrations -> Custom repositories**.
3. Add `https://github.com/ccpk1/firewalla-local-ha` as an **Integration** repository.
4. Search for **Firewalla Local**, install it, and restart Home Assistant.

### Add the integration and pair your device

Because this integration communicates entirely locally, it uses the exact same secure pairing process as adding a secondary phone to your Firewalla.

**Step 1: Start the Home Assistant setup**
1. Open **Settings -> Devices & Services -> Add Integration**.
2. Search for and select **Firewalla Local**.
3. **Local hostname or IP address:** Leave this as the default `fire.walla` (this works for 99% of setups where Firewalla is handling your DNS). If you have a custom DNS routing setup, replace this with your Firewalla's local IP address (e.g., `192.168.1.1`).

**Step 2: Generate the pairing code (Firewalla App)**
1. Open the Firewalla app on your phone.
2. Tap the gear icon to open **Settings -> Advanced**, then find and tap **Allow Additional Pairing**.
3. Toggle the switch to **On**. A QR code will appear on your screen.

**Step 3: Extract the raw QR JSON**
Because Home Assistant cannot scan the screen directly, you need to copy the raw text hidden inside that QR code.
1. **Take a screenshot** of the QR code in the Firewalla app.
2. Open your phone's default **Photos** app (Apple Photos or Google Photos).
3. Open the screenshot you just took. Modern smartphones can read QR codes directly from photos.
   * **iOS:** Tap the "Live Text" icon in the bottom right, or simply press and hold directly on the QR code until a menu pops up.
   * **Android:** Tap "Google Lens" or press and hold the QR code.
4. Select **Copy Link** or **Copy Text**. You should now have a long string of JSON text saved to your clipboard.

**Step 4: Complete the connection**
1. Send that copied text to the device where you have Home Assistant open (via text, email, Apple Notes, etc., or just paste it directly if you are setting this up on your phone).
2. Paste the exact string into the **Raw QR JSON** field in Home Assistant.
3. Click **Submit**.

Let the integration validate the local runtime. Once successful, your Firewalla Local entities will be created!

> **🛡️ A note on pairing security:** Treating QR codes and authentication strings with caution is always good practice. However, copying this raw JSON does not expose a permanent "master key" to your network. This payload is protected by Firewalla's modern security techniques: it is strictly time-bound (valid for only 10 minutes), requires local network access to execute, and uses an encrypted token exchange.

## Removal

### Remove the Home Assistant integration entry

1. Open **Settings -> Devices & Services**.
2. Open the **Firewalla Local** integration.
3. Choose **Delete** to remove the config entry.

This removes the integration-managed entities for that entry from Home Assistant.

### Remove the custom repository

If you installed through HACS and no longer want the integration available:

1. Remove the Firewalla Local integration entry from Home Assistant.
2. Remove the repository from HACS custom repositories if you added it manually.
3. Remove the installed integration from HACS.
4. Restart Home Assistant.

## Data updates and refresh behavior

Firewalla Local uses local polling.

- the integration refreshes the runtime snapshot every 3 minutes
- you can change the polling interval in the options flow between 1 and 10 minutes
- Home Assistant entities reflect the latest successful refresh
- successful rule actions may update the in-memory state immediately for responsive UI behavior
- later coordinator refreshes remain the source of truth
- the integration does not create its own custom persistent cache of live Firewalla runtime state between restarts

If the Firewalla box is temporarily unavailable, the integration marks data as
unavailable and resumes normal state updates after a successful refresh.

## Options flow

Use the integration options flow to manage the runtime surfaces you want in Home
Assistant.

- **Manage rule selection:** Choose which supported Firewalla rules should be
   exposed as Home Assistant switches.
- **Manage watched devices:** Choose which endpoints should appear as
   watched-device connectivity binary sensors.
- **Manage watched users:** Choose which Firewalla users should appear as
  watched-user daily-usage sensors.
- **General options:** Adjust the local polling interval without re-pairing the
   box.

## Appliance monitoring

Firewalla Local exposes the box itself through always-on monitoring entities.

- a system-status binary sensor attached to the Firewalla device
- a latest-speed-test sensor attached to the same device

The system-status entity exposes stable attributes such as:

- uptime and `uptime_seconds`
- boot-complete and cloud-connected state
- firmware release type and DDNS
- WAN IP summary
- total, online, and offline device counts
- CPU, memory, and disk summary values

The latest-speed-test entity exposes the latest successful result from the
local payload, including download speed as the primary state and the remaining
test details as attributes.

## Watched-device monitoring

Watched devices are opt-in. After selecting devices in the options flow, the
integration creates one watched-device binary sensor per selected MAC address.

- each watched-device entity exposes a connectivity-style online or offline
  state
- attributes include local IP address, device group, network name, connection
  type when available, upload and download totals, and last activity time
- if a selected device disappears from the current Firewalla payload, the
  entity remains in Home Assistant and becomes unavailable instead of being
  silently removed

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
   totals, and a manager-derived last-active value based on associated hosts
- `unique_usage_today` is kept as a separate attribute because Firewalla
   exposes it as a distinct raw field and it is not guaranteed to always equal
   the primary total
- `app_usage_by_app` is sourced from the proven `appTimeUsageToday` payload and
   only includes apps with positive usage to keep the attribute surface compact
- `last_active` is an integration-derived join over associated hosts rather
   than a direct user field from the local payload
- if a selected user disappears from the current Firewalla payload, the entity
   remains in Home Assistant and becomes unavailable instead of being silently
   removed
- the current watched-user slice only exposes values that are explicitly proven
   in the local payload or are clearly integration-derived joins over that
   payload

## Rule-backed switches

Only a supported subset of Firewalla rules can be exposed as Home Assistant
switches.

At a high level, the integration only exposes rules that fit the proven
persistent user-managed switch model. That means the integration does not try to
turn every Firewalla rule into a switch.

In practice:

- user-managed persistent rules from the supported rule families may appear in the options flow
- Firewalla-managed or automatically generated rules are excluded
- temporary or auto-expiring rule shapes are excluded from switch selection
- if a previously selected rule later disappears, Home Assistant can still show enough context for you to remove the stale selection cleanly

### Persistent rules versus temporary rules

This distinction matters because the integration is built primarily around
pausing and resuming existing persistent rules, not around creating and deleting
rules for you.

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

The easiest way to make sure a rule is persistent is to create it manually in
the Firewalla app as a normal ongoing rule.

For example:

- if you are using one of the simple internet-block flows, choose **Block
   always** instead of a timed block  (You can then resume the rule or pause the rule as necessary and it will remain persistent)
- if you want another durable rule type, create it normally in the app first
   and then let the integration discover it as an existing rule

Once a persistent rule exists, the integration can interact with it mainly by:

- exposing it as a switch when it matches the supported rule families
- pausing it
- resuming it

The integration should not be thought of as the primary place to create or
delete rules. The Firewalla app remains the normal place to set up the rule in
the first place.

If you later decide you no longer want that persistent rule at all, delete it
from the Firewalla app. After the rule is removed on the box:

- the corresponding Home Assistant switch will become unavailable
- you can then remove the stale selection from the integration options flow if
   you no longer want it tracked

## Services

### Get runtime inventory

Use `firewalla_local.get_runtime_inventory` to inspect the current runtime data.

This is useful when you want to:

- see the current normalized runtime objects
- inspect rule IDs before using pause or resume services
- compare what is live on the box with what is currently exposed in Home Assistant

### Run internet speed test

Use `firewalla_local.run_internet_speed_test` to start a speed test on one WAN.

- choose the WAN with `wan_uuid` for deterministic automations or `wan_name`
   for interactive use
- if only one WAN is available, you can omit the WAN selector
- the service returns an acknowledgement with the resolved WAN and command
   payload
- the service does not wait for the completed measurement because the test may
   take around 30 seconds

### Get speed test results

Use `firewalla_local.get_speed_test_results` to read normalized speed test
results.

- by default it refreshes once and returns only the most recent result
- use `limit` to request more than one record
- use `wan_uuid` or `wan_name` to filter to one WAN when needed
- the response includes `latest` for the common case and `results` for the full
   returned list

### Get WAN usage

Use `firewalla_local.get_wan_usage` to read the current-month data-usage view
for each WAN.

- by default it returns every discovered WAN in one response
- use `wan_uuid` or `wan_name` to filter to one WAN when needed
- each WAN entry includes total upload and download bytes plus the current-month
   sample series
- timestamps are returned both as raw epoch values and readable UTC ISO fields

### Get WAN usage history

Use `firewalla_local.get_wan_usage_history` to read the last 12 monthly WAN
usage buckets.

- by default it returns every discovered WAN in one response
- use `wan_uuid` or `wan_name` to filter to one WAN when needed
- each month bucket includes total upload and download bytes plus the normalized
   sample series
- when Firewalla omits explicit month bounds, the integration derives begin and
   end timestamps from the available sample coverage

### Pause rule

Use `firewalla_local.pause_rule` to pause a managed rule.

This is intended for an existing persistent rule that already exists on the
Firewalla box.

You can provide:

- a `rule_target`
- a `duration`
- or a `resume_at` time

If you provide neither duration nor resume time, the rule remains paused until
you resume it.

### Resume rule

Use `firewalla_local.resume_rule` to resume a paused managed rule immediately.

Like `pause_rule`, this operates on an existing persistent rule rather than
creating a new rule for you.

## Reauthentication and host changes

- if credentials stop working, Home Assistant can trigger reauthentication using a fresh QR payload
- if the local host changes, use the integration reconfigure flow instead of deleting and re-adding the device

## Known limitations

- discovery is not implemented
- only the currently supported rule subset is exposed as switches
- watched-device VPN state is intentionally deferred until the host-to-VPN mapping is proven
- system-level online and offline device counts may use integration-derived aggregation when the raw payload does not expose a trustworthy aggregate online flag
- watched-user totals currently rely on the proven `internetTimeUsageToday` and
   `appTimeUsageToday` user payloads; fields not present there remain out of
   scope until they are directly verified
- watched-user entities do not expose a last-app-used field because that value is not yet proven in the local contract
- current WAN usage is exposed as a status-sensor attribute for summary and
   automation use, not as separate per-WAN entities
- broader mutation surfaces are still intentionally out of scope until they are proven by protocol evidence
- this is a community integration and not an official Firewalla support channel
