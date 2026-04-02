# Firewalla Local MAC-only device tracker

## Initiative snapshot

- Initiative: Firewalla Local MAC-only device tracker
- Status: Completed
- Objective: Add an opt-in `device_tracker` platform for selected MAC-backed LAN
  hosts so Home Assistant users can use Firewalla presence as a router-based
  input for `person` tracking.
- Current status: Runtime implementation is complete and validated. Remaining
  work is limited to release-surface and user-facing documentation alignment.
- Validation status:
  - `python -m ruff check .` passed
  - `python -m mypy custom_components/firewalla_local` passed
  - `python -m pytest tests/ -v` passed with `185 passed`

## Scope and non-goals

Scope:

- add a separate opt-in device-tracker selection flow alongside watched-device
  selection
- add one `device_tracker` entity per selected MAC-backed host
- add one distinct Home Assistant client device per selected tracked MAC and
  attach the device-tracker entity to that client device
- reuse the existing normalized host inventory and manager-owned presence
  contract while keeping watched-device and device-tracker windows separate
- preserve missing device-tracker selections as unavailable placeholders until
  the user removes them
- keep the feature safe under multiple loaded Firewalla config entries

Non-goals:

- do not merge this with watched-device binary sensors
- do not auto-create trackers for all discovered hosts
- do not create trackers for pseudo-hosts such as `wg_peer:*`
- do not create trackers for VPN, tunnel, overlay, or other non-MAC identities
- do not invent richer presence semantics beyond `home`, `not_home`, and
  unavailable

## Locked decisions

- use a separate opt-in device-tracker selection set; do not reuse or infer from
  `CONF_WATCHED_DEVICES`
- restrict device-tracker entities to MAC-backed LAN hosts only
- exclude pseudo-hosts such as `wg_peer:*` and all VPN, tunnel, or overlay
  identities by design, not as a deferred phase
- keep watched-device connectivity and device-tracker presence as separate
  manager-owned evaluations with separate configurable windows in general
  options
- expose device trackers through `DeviceTrackerEntity` with
  `source_type=router`
- create one tracked-client device registry record per selected MAC-backed host
  and set its `via_device` link to the primary Firewalla router device
- use a separate options-flow menu entry labeled `Manage device trackers`
- allow only bounded extra attributes such as IP, network name, connection
  type, group name, and last active

## External dependencies

- no blocking external dependency is currently known
- the feature must be built only from the existing proven host inventory and
  manager-owned presence contract

## Phase summary table

| Phase | Goal | Exit gate |
| --- | --- | --- |
| 1 | Establish device-tracker contracts | Architecture, options, and identity rules are fixed and MAC-only |
| 2 | Add runtime and device-registry surfaces | Selected MAC-backed hosts appear as entry-scoped router trackers on client devices |
| 3 | Validate lifecycle and multi-instance behavior | Tests prove stable IDs, missing-host handling, device lifecycle, and entry isolation |
| 4 | Align documentation and release surfaces | User docs and architecture reflect the shipped contract |

## Per-phase details with checkboxes

### Phase 1: Establish device-tracker contracts

- [x] Add `CONF_DEVICE_TRACKERS` to
  `custom_components/firewalla_local/const.py` as a config-entry options list
  storing selected MAC-backed device trackers.
- [x] Extend the architecture and standards references so the repository clearly
  states that `device_tracker` is MAC-only and intentionally excludes VPN or
  pseudo-host identities.
- [x] Define a helper-level or manager-level MAC-backed eligibility rule so the
  same contract is used consistently by options flow and platform setup.
- [x] Confirm the device-tracker surface is a distinct opt-in selection set from
  `CONF_WATCHED_DEVICES` rather than an alias or implicit reuse.

### Phase 2: Add runtime and platform surfaces

- [x] Add a new `device_tracker.py` platform under
  `custom_components/firewalla_local/` using `DeviceTrackerEntity` with
  `source_type=router`.
- [x] Reuse `HostManager` in
  `custom_components/firewalla_local/managers/host_manager.py` for device-tracker
  lookups instead of duplicating inventory or online-state logic in the
  platform.
- [x] Extend the options flow in
  `custom_components/firewalla_local/config_flow.py` with a separate device-
  tracker menu and selection step that mirrors watched-device selection
  behavior.
- [x] Ensure selected device trackers use entry-scoped unique IDs and attach to
  one distinct tracked-client device keyed by the client's MAC address.
- [x] Create or update the tracked-client device registry record with the
  client's MAC connection data, a stable identifier contract, and
  `via_device` pointing to the primary Firewalla router device for the owning
  config entry.
- [x] Keep the tracker entity attached to the tracked-client device rather than
  the router device so the scanner-tracker contract remains satisfied without
  leaving standalone entities in the UI.
- [x] Keep platform code presentation-only: it should consume manager-owned host
  lookups and state, not rebuild matching or visibility rules.
- [x] Align tracker naming with the Home Assistant translated sub-entity
  pattern so the friendly name resolves as `<device name> Presence` and the
  auto-generated entity ID normalizes to the `..._presence` form.

### Phase 3: Validate lifecycle and multi-instance behavior

- [x] Add config-flow tests in
  `tests/components/firewalla_local/test_config_flow.py` covering device-tracker
  choice generation, stale device-tracker preservation, and options updates.
- [x] Add platform tests in a new
  `tests/components/firewalla_local/test_device_tracker.py` or equivalent
  focused module covering entity creation, `home` and `not_home` state, and
  unavailability when a selected host disappears.
- [x] Add device-registry tests proving selected trackers create one client
  device per MAC, attach the tracker entity to that device, and set
  `via_device` to the router device.
- [x] Add setup or reload coverage proving device-tracker option changes cause
  the correct reload behavior without disturbing unrelated watched-device,
  watched-user, or rule-selection surfaces.
- [ ] Add lifecycle coverage for deselection, config-entry unload, and stale
- [x] Add lifecycle coverage for deselection, config-entry unload, and stale
  tracked-client device cleanup so unused client devices do not remain attached
  to the config entry indefinitely.
- [x] Add multi-instance coverage proving two Firewalla config entries can track
  the same MAC independently without unique-ID or lifecycle collisions.
- [x] Add multi-instance device-registry coverage proving two Firewalla config
  entries can create separate tracked-client devices for the same MAC without
  `via_device`, identifier, or cleanup collisions.

Phase 3 implementation notes:

- deselection coverage is implemented and passing
- stale tracked-client device cleanup during runtime reconciliation is
  implemented and passing
- explicit config-entry unload coverage for tracked-client device detachment or
  removal still needs a focused test before this phase can be called complete

### Phase 4: Align documentation and release surfaces

- [ ] Update `docs/USER_GUIDE.md` to document device-tracker setup, state
- [x] Update `docs/USER_GUIDE.md` to document device-tracker setup, state
  meaning, and the deliberate exclusion of pseudo-host or VPN presence.
- [x] Update `README.md` only at the capability-summary level once the feature
  exists; do not describe speculative tracker behavior before implementation.
- [x] Keep `docs/ARCHITECTURE.md` aligned with the final ownership boundaries,
  especially that `HostManager` owns both watched-device and device-tracker host
  orchestration.
- [x] Add focused release-summary language only if the feature lands before the
  next release cut.

## Validation strategy

- validate with the repository-standard commands:
  - `python -m ruff check .`
  - `python -m mypy custom_components/firewalla_local`
  - `python -m pytest tests/ -v`
- during iteration, focused coverage should include at minimum:
  - `tests/components/firewalla_local/test_config_flow.py`
  - device-tracker platform tests
  - setup and reload behavior tests
- no live protocol experimentation should be hidden inside this feature pass;
  the tracker must be built from already-proven host inventory and current
  manager-owned online-state behavior

## Builder guardrails

- do not widen scope beyond MAC-backed LAN hosts without explicit approval
- do not implement VPN, pseudo-host, `wg_peer:*`, tunnel, or overlay presence
  in any form
- do not reuse watched-device binary sensors as tracker entities or treat one
  surface as an alias for the other
- do not add a new polling path, background task, or protocol read for device
  trackers
- do not move host-selection or online-state business logic into platform files
  when it belongs in `HostManager`
- do not scatter tracked-client device-registry writes across platform files;
  use one integration-owned lifecycle path so create, update, deselect, unload,
  and cleanup behavior stays coherent
- do not change the approved `home`, `not_home`, or unavailable state contract
  without approval
- do not update release-facing docs as if the feature exists until the feature
  is actually implemented

## Stop and ask conditions

- stop if the current watched-device online heuristic appears unsuitable for the
  device-tracker `home` or `not_home` contract
- stop if the builder concludes that MAC-backed eligibility cannot be enforced
  cleanly from the current normalized host inventory
- stop if the platform would require new protocol work, new raw payload fields,
  or a second runtime fetch path
- stop if the implementation would require pseudo-host or VPN identities to be
  treated as valid presence trackers
- stop if multi-instance unique-ID safety cannot be preserved under the planned
  entity model
- stop if tracked-client device creation cannot satisfy Home Assistant's
  scanner-tracker enablement rules while still preserving `via_device`
  linkage to the router device

## Expected file touch list

- `custom_components/firewalla_local/const.py`
- `custom_components/firewalla_local/config_flow.py`
- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/entity.py` if shared tracker helpers are
  justified
- `custom_components/firewalla_local/device_tracker.py`
- `custom_components/firewalla_local/helpers/` if shared device-registry helper
  logic is introduced for tracked clients
- `custom_components/firewalla_local/managers/integration_manager.py`
- `custom_components/firewalla_local/managers/host_manager.py`
- `custom_components/firewalla_local/translations/en.json`
- `docs/USER_GUIDE.md`
- `README.md` only if the feature lands in the same implementation pass
- `tests/components/firewalla_local/test_config_flow.py`
- `tests/components/firewalla_local/test_init.py`
- `tests/components/firewalla_local/test_device_tracker.py`

## Definition of done

- `CONF_DEVICE_TRACKERS` exists as a separate options bucket from
  `CONF_WATCHED_DEVICES`
- the options flow exposes `Manage device trackers` and only offers eligible
  MAC-backed LAN hosts
- each selected device tracker creates one entry-scoped `device_tracker` entity
  with `source_type=router`
- each selected tracked MAC creates one client device in the device registry
  and the tracker entity is attached to that client device
- each tracked-client device sets `via_device` to the primary Firewalla router
  device for the owning config entry
- tracker naming follows the Home Assistant translated sub-entity pattern so
  the friendly name resolves as `<device name> Presence` and auto-generated
  entity IDs normalize from the tracked-client device name instead of using a
  manually constructed slug
- tracker state resolves to `home`, `not_home`, or unavailable only
- pseudo-hosts and VPN-related identities are excluded from both device-tracker
  selection and tracker creation
- missing device trackers remain as unavailable entities until the user removes
  them from device-tracker options
- deselection, config-entry unload, and stale-device cleanup remove or detach
  tracked-client devices cleanly so the integration does not leak orphaned
  device-registry state
- unique IDs remain stable and collision-safe across multiple loaded Firewalla
  entries
- focused tests for config flow, platform behavior, device-registry behavior,
  reload behavior, lifecycle cleanup, and multi-instance safety are added and
  passing
- repository-standard validation passes:
  - `python -m ruff check .`
  - `python -m mypy custom_components/firewalla_local`
  - `python -m pytest tests/ -v`

## Handoff package

Builder implementation should begin with these authoritative inputs:

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- this plan file
- `custom_components/firewalla_local/binary_sensor.py` as the closest existing
  opt-in host-surface pattern
- `custom_components/firewalla_local/config_flow.py` as the existing selection
  UX pattern
- `custom_components/firewalla_local/managers/host_manager.py` as the owning
  runtime boundary for host inventory and online-state behavior

## References

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `custom_components/firewalla_local/binary_sensor.py`

## Current remainder

- no functional or documentation remainder is currently required for the
  shipped MAC-only device-tracker initiative
- any future work should be treated as follow-on enhancement scope rather than
  completion work for this plan
- `custom_components/firewalla_local/config_flow.py`
- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/entity.py`
- `custom_components/firewalla_local/managers/host_manager.py`
- `plans/completed/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_COMPLETED.md`