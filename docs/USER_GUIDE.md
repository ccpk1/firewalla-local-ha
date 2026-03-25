# Firewalla Local user guide

## Overview

Firewalla Local is a Home Assistant custom integration for connecting to one
Firewalla box over the verified local protocol.

The current release is intentionally small. It focuses on the first proven
runtime slice:

- pairing and reauthentication
- runtime polling
- selected rule-backed switches
- runtime inventory reporting
- pause and resume services

## Installation

### HACS installation

1. Ensure HACS is installed in Home Assistant.
2. Open **HACS -> Integrations -> Custom repositories**.
3. Add `https://github.com/ccpk1/firewalla-local-ha` as an **Integration** repository.
4. Install **Firewalla Local** from HACS.
5. Restart Home Assistant.

### Add the integration

1. Open **Settings -> Devices & Services -> Add Integration**.
2. Select **Firewalla Local**.
3. Paste the Firewalla QR JSON payload when prompted.
4. Let the integration validate the local runtime before the entry is created.

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
- Home Assistant entities reflect the latest successful refresh
- successful rule actions may update the in-memory state immediately for responsive UI behavior
- later coordinator refreshes remain the source of truth
- the integration does not create its own custom persistent cache of live Firewalla runtime state between restarts

If the Firewalla box is temporarily unavailable, the integration marks data as
unavailable and resumes normal state updates after a successful refresh.

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

## Services

### Get runtime inventory

Use `firewalla_local.get_runtime_inventory` to inspect the current runtime data.

This is useful when you want to:

- see the current normalized runtime objects
- inspect rule IDs before using pause or resume services
- compare what is live on the box with what is currently exposed in Home Assistant

### Pause rule

Use `firewalla_local.pause_rule` to pause a managed rule.

You can provide:

- a `rule_target`
- a `duration`
- or a `resume_at` time

If you provide neither duration nor resume time, the rule remains paused until
you resume it.

### Resume rule

Use `firewalla_local.resume_rule` to resume a paused managed rule immediately.

## Reauthentication and host changes

- if credentials stop working, Home Assistant can trigger reauthentication using a fresh QR payload
- if the local host changes, use the integration reconfigure flow instead of deleting and re-adding the device

## Known limitations

- discovery is not implemented
- only the currently supported rule subset is exposed as switches
- broader mutation surfaces are still intentionally out of scope until they are proven by protocol evidence
- this is a community integration and not an official Firewalla support channel