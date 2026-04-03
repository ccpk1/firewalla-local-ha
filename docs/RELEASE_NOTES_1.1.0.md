# Firewalla Local 1.1.0

## Summary

Firewalla Local 1.1.0 is the first feature release after 1.0.0.

Version 1.0.0 established the core integration baseline:

- pairing and reauthentication
- appliance monitoring
- supported rule-backed switches
- three services: `pause_rule`, `resume_rule`, and `get_runtime_inventory`

Version 1.1.0 expands that baseline into a broader local operator toolkit with
new host actions, much richer report services, watched-user monitoring,
router-based device trackers, and better runtime refresh visibility on the main
Firewalla device.

## Highlights

- Added 13 new Home Assistant services beyond the 1.0.0 baseline.
- Added host operator actions for Wake-on-LAN, host rename, host notification
	toggles, DHCP reservation management, and WAN speed-test triggering.
- Added richer local reporting for host identity, network segments, time usage,
	speed test history, WAN usage, and WAN events.
- Added watched-user monitoring for selected Firewalla users.
- Added opt-in router-based device trackers for selected MAC-backed LAN
	clients, with tracked-client devices linked back to the main Firewalla
	device.
- Added a manual `Sync runtime` button on the main Firewalla device and a
	`runtime_data_updated_at` system-status attribute showing when the current
	runtime snapshot was last refreshed.
- Added clearer pairing support tooling with enhanced debug logging breadcrumbs
	for QR validation, cloud provisioning, and local runtime validation, plus
	troubleshooting guidance in the user guide.

## New services since 1.0.0

Firewalla Local 1.0.0 exposed only these services:

- `firewalla_local.pause_rule`
- `firewalla_local.resume_rule`
- `firewalla_local.get_runtime_inventory`

Firewalla Local 1.1.0 adds these services:

- `firewalla_local.get_host_name_mapping`
- `firewalla_local.get_network_segment_report`
- `firewalla_local.get_network_segment_usage`
- `firewalla_local.run_internet_speed_test`
- `firewalla_local.wake_host`
- `firewalla_local.set_host_name`
- `firewalla_local.set_host_notify_when_next_online`
- `firewalla_local.set_host_notify_when_next_offline`
- `firewalla_local.set_host_dhcp_reservation`
- `firewalla_local.get_speed_test_results`
- `firewalla_local.get_time_usage_report`
- `firewalla_local.get_wan_data_usage`
- `firewalla_local.get_wan_events`

## What is new

### Host actions from Home Assistant

You can now use Home Assistant to operate on individual Firewalla hosts more
directly.

- wake a compatible host with Wake-on-LAN
- rename a host through the same local protocol used by the Firewalla app
- toggle `notify when next online` and `notify when next offline`
- set or clear host DHCP reservations with network-aware validation
- run an internet speed test on a selected WAN

### Richer local reporting

The integration now exposes much more of Firewalla's locally available data
through Home Assistant service calls.

That includes:

- host identity lookup
- network segment configuration reports
- network segment usage reports
- time usage reports for devices, groups, and users
- speed test result history
- WAN data usage reports
- WAN event timelines

The newer report surfaces are also more consistent for automation consumers.
They follow a shared report-style structure around:

- target resolution
- query echoing
- time basis
- summary fields
- detailed sections
- metadata and provenance

### Watched-user monitoring

You can now select Firewalla users in the options flow and expose one
watched-user sensor per selected user.

- each watched-user sensor reports today's usage as its primary state
- attributes include unique usage, associated devices, associated device
	count, per-app usage, and a derived `last_active` value based on current host
	joins

### Router-based device trackers

You can now select eligible MAC-backed LAN clients in the options flow and
expose them as Home Assistant router-based `device_tracker` entities.

- each selected client gets its own tracked-client device in Home Assistant
- the tracked-client device links back to the main Firewalla router device with
	`via_device`
- tracker names follow the standard Home Assistant composed form such as
	`Chad's Phone Presence`
- pseudo-host, VPN, tunnel, and other non-MAC identities remain excluded by
	design

### Better runtime refresh visibility

The main Firewalla device now includes a diagnostic `Sync runtime` button so
you can request an immediate refresh without opening the options flow.

- pressing the button triggers an immediate coordinator refresh against the
	local Firewalla runtime
- the main system-status entity now exposes `runtime_data_updated_at` so you
	can see when the current runtime snapshot was last refreshed
- this makes it easier to confirm that Home Assistant is showing fresh
	Firewalla data when you are debugging or checking the box manually

## Upgrade notes

- No migration step is expected for existing 1.0.0 users.
- Existing entities and paired config entries should continue to work normally
	after upgrade.
- The original 1.0.0 rule services and runtime inventory service continue to
	work as before.
- The new services are additive and can be adopted incrementally.
- Device trackers are opt-in and only appear after you select eligible clients
	in the options flow.
- The main Firewalla device now exposes a manual runtime sync button and a
	runtime refresh timestamp attribute.

## Known defers

- `get_wan_events` is still a low-level WAN-health surface and is not yet
	aligned to Firewalla's MSP alarm model.
- Discovery remains deferred until Firewalla exposes a durable local discovery
	contract.
- Broader DHCP administration beyond the shipped host reservation path remains
	deferred pending more protocol evidence.

## Suggested GitHub release body

Firewalla Local 1.1.0 expands the integration from the 1.0.0 baseline of
pairing, monitoring, rule control, and three core services into a broader local
operator toolkit.

Highlights in this release:

- Added 13 new services beyond the original `pause_rule`, `resume_rule`, and
	`get_runtime_inventory` set.
- Added Wake-on-LAN, host rename, host notification toggles, DHCP reservation
	management, and WAN speed-test triggering.
- Added new local report services for host identity records, network segments,
	time usage, speed test history, WAN usage, and WAN events.
- Added watched-user monitoring and opt-in router-based device trackers for
	selected MAC-backed LAN clients.
- Added a manual `Sync runtime` button on the Firewalla device and a
	system-status attribute showing when the runtime snapshot was last refreshed.
- Added enhanced pairing debug logging and troubleshooting guidance to make
	first-time setup failures easier to diagnose.

No migration is expected for existing 1.0.0 users.