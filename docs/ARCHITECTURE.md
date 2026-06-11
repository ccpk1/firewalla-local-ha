# Firewalla Local architecture

## Purpose

This document defines the durable architecture contract for the Firewalla Local Home Assistant integration.

It describes how the repository is built, where responsibilities belong, and which constraints must remain true as the integration grows.

## Product naming

- GitHub repository name: `firewalla-local-ha`
- Home Assistant UI name: `Firewalla Local`
- Home Assistant integration domain: `firewalla_local`
- Home Assistant package path: `custom_components/firewalla_local/`

## Mission

The integration provides local runtime access to a Firewalla box from Home Assistant.

The architecture supports:

- QR-based pairing and credential establishment
- signed local REST communication over port `8833`
- coordinator-backed runtime polling
- rule-backed switches, appliance-monitoring entities, watched-device monitoring, watched-user daily-usage monitoring, and supporting services
- a future opt-in `device_tracker` surface for MAC-backed LAN hosts only
- diagnostics, reauthentication, and repair-ready user flows

The architecture does not support speculative fallback paths, duplicate runtime layers, or convenience abstractions that blur ownership boundaries.

It also does not support VPN, pseudo-host, or tunnel-only presence tracking for
Home Assistant `device_tracker` entities. Those records do not map cleanly to
Home Assistant home or away semantics and must not be forced into that model.

Watched-device binary sensors and `device_tracker` entities also use separate
configurable activity windows. Watched-device connectivity uses a shorter
online window, while `device_tracker` presence uses a separate away window in
general options.

## Quality references

Use these documents together:

- `docs/ARCHITECTURE.md`: structural contracts and ownership boundaries
- `docs/DEVELOPMENT_STANDARDS.md`: coding, typing, translation, and lifecycle rules
- `docs/QUALITY_REFERENCE.md`: compact mapping from quality expectations to repository evidence
- `docs/RULE_MODEL.md`: durable policy-rule interpretation, switch eligibility,
  and metadata contracts

## Lexicon standards

Use terms consistently across code, documentation, diagnostics, and review.

| Term | Meaning |
| --- | --- |
| Device | The physical Firewalla box represented in the Home Assistant device registry |
| Config entry | The Home Assistant configuration record for one paired Firewalla box |
| Domain | The Home Assistant integration domain `firewalla_local` only |
| Rule | A normalized Firewalla policy rule from runtime data |
| Item type / record type | A Firewalla data category such as a rule, tag, host, or network profile |
| Host | One Firewalla endpoint or client record from runtime data; never a Home Assistant device registry record |
| Host name | The primary user-facing Firewalla host label exposed by the integration as `host_name` |
| DNS hostname | The per-host DNS label exposed by Firewalla runtime data and normalized as `dns_hostname` |
| DNS domain | The segment-level search domain derived from DHCP configuration and normalized as `dns_domain` |
| DNS FQDN | The fully qualified local-domain value exposed by runtime data and normalized as `dns_fqdn` |
| DHCP name | The DHCP-origin hostname value exposed by runtime data and normalized as `dhcp_name` |
| User-facing identity | The app-visible person or device label the integration should prefer for entity names and attributes when Firewalla also exposes an internal backing group or tag |
| Host device type | The Firewalla host classification exposed by detect or feedback data and normalized as `host_device_type` |
| Rule template | The persisted matching contract used to find the intended live rule even if the live rule ID changes |
| Runtime snapshot | The coordinator-owned normalized in-memory view of the current Firewalla state |
| Registry | The manager-owned indexed runtime structure derived from the raw Firewalla payload |
| Scope metadata | Networks, devices, tags, targets, and related applicability data that describe a rule but are not standalone entities |
| Entity | A Home Assistant platform object only |
| Device tracker | A Home Assistant `device_tracker` entity surface for one selected MAC-backed LAN host; never shorthand for the Firewalla box device or generic host inventory |
| Unique ID | The stable Home Assistant registry identifier supplied by the integration |
| Entity ID | The Home Assistant registry string generated and owned by Home Assistant |
| Identity anchor | The immutable value used to tie the config entry and device to the physical box |

Critical rule:

- never use `entity` to refer to a Firewalla rule, target, network, tag, or other normalized runtime record
- never use `domain` to describe a Firewalla item type, record type, or rule-specific behavior
- never use `device` for Firewalla endpoint inventory, naming fields, or selector behavior unless the code is explicitly referring to a Home Assistant device registry concept

Identity presentation rule:

- when Firewalla exposes both an app-visible user identity and a backing group or tag used only to model assignment, Home Assistant-facing surfaces must prefer the user-facing identity
- backing group names are implementation details unless the surface is explicitly diagnostic or inventory-oriented
- this rule applies to normalized rule applicability, watched-user associations, and host-backed entity attributes derived from group membership
- when normalized rule applicability uses an affiliated user identity in place of a backing group name, the accompanying applicability kind must also be `user` so label and kind stay aligned on Home Assistant-facing surfaces

## Protocol baseline

The repository assumes the following protocol facts:

- first-time pairing begins from the Firewalla QR JSON payload
- provisioning uses the required cloud-assisted bootstrap sequence

  *(The full pairing protocol from QR through cloud login, rendezvous, group
  polling, and symmetric key decryption is documented in
  `docs/REVERSE_ENGINEERING_WORKFLOW.md#pairing-protocol-full-sequence`.)*

- local runtime communication uses encrypted HTTP POST requests to
  `http://{local_ip}:8833/v1/encipher/message/{gid}`
- local runtime credentials include `gid`, `eid`, `aid`, and the decrypted
  symmetric key
- key generation and signing require SPKI public PEM and PKCS#8 private PEM
  handling

Transport questions and mutation-surface questions are separate concerns. Unverified mutation details do not justify weakening the protocol boundary.

## Identity contract

The immutable Home Assistant identity anchor is the QR `license` value.

Rules:

- `license` is the primary device registry identity anchor
- `license` is the config-entry identity anchor
- `gid` is a connection parameter, not a device identifier
- IP addresses and hostnames must never be used as unique identifiers
- entity unique IDs must remain stable across IP changes, host changes, and re-pairing that preserves the same box identity

This rule keeps registry identity independent from mutable connection details.

## Layered architecture

The integration is built as a small layered system with explicit ownership and concrete module homes.

### Directory layout

The runtime should converge on named directories with clear ownership:

- `custom_components/firewalla_local/api/`
	- `client.py`
	- `auth.py`
	- `crypto.py`
	- `exceptions.py`
	- `models.py` when protocol-only structures justify it
- `custom_components/firewalla_local/managers/`
	- `__init__.py`
	- `base_manager.py`
	- `integration_manager.py`
	- `host_manager.py`
	- `rule_manager.py`
	- additional manager files only when a separate orchestration boundary is justified
- `custom_components/firewalla_local/helpers/`
	- `entity_helpers.py`
	- `service_helpers.py`
	- `runtime_inventory.py` if inventory reporting remains a read-only helper over manager-owned registry data
	- additional Home Assistant-aware helper modules only when shared runtime glue clearly belongs outside a manager or platform file
- `custom_components/firewalla_local/utils/`
	- pure utility modules such as duration parsing or other framework-independent helpers
- `custom_components/firewalla_local/`
	- `coordinator.py`
	- `entity.py`
	- `models.py`
	- platform files
	- flow files
	- diagnostics and service entry points

### Layer responsibilities

| Layer | Home Assistant imports | Owns state mutation | Owns protocol work | Responsibility |
| --- | --- | --- | --- | --- |
| `api/` | No | No | Yes | Crypto, auth, transport, request and response handling |
| coordinator | Yes | Config-entry writes only | No | Routing, refresh orchestration, availability handling, config-entry updates, and raw payload handoff |
| `managers/` | Yes | Yes | No | Rule matching, registry indexing, lifecycle reconciliation, command orchestration, optimistic updates |
| `helpers/` | Yes | No | No | Shared Home Assistant-aware lookup, registry, entity, and service helper functions |
| `utils/` | No | No | No | Pure framework-independent helper functions |
| entities and services | Yes | No | No | Presentation surfaces and user interaction entry points |
| models | No, unless explicitly HA-specific | No | No | Typed structures and normalized data models |

### Architectural rules

- `custom_components/firewalla_local/api/` is the only protocol boundary
- nothing in `api/` may import `homeassistant.*`
- the coordinator is primarily a router and refresh orchestrator, not a business-logic owner
- the coordinator may schedule refreshes, track availability, own config-entry writes, and hand raw or normalized refresh inputs to the manager layer
- config-entry writes belong to the coordinator because the coordinator owns the integration instance lifecycle and reload semantics
- `managers/` is the single source of truth for rule resolution and command orchestration
- at minimum the runtime should have:
	- `IntegrationManager` for config-entry-scoped lifecycle, Firewalla appliance device lifecycle, entity lifecycle, and shared orchestration concerns
	- `HostManager` for normalized endpoint-host inventory plus watched-device and MAC-backed device-tracker orchestration
	- `RuleManager` for rule resolution, registry indexing, command handling, optimistic updates, and read-model generation for rule-backed surfaces
	- `UserManager` for watched-user identity, usage shaping, total and unique fallback handling, and host-association joins
- `helpers/` contains Home Assistant-aware shared helper code only and must not become a second manager layer
- `utils/` contains pure functions only and must not import `homeassistant.*`
- entities must consume manager-owned resolved state and must not re-implement matching, filtering, or mutation payload construction
- services must delegate to manager methods and must not become a second business-logic path
- models should stay typed and lightweight rather than accumulating orchestration logic
- shared report code such as runtime inventory must not live as an unowned root module; it must belong either to the owning manager or to a clearly named helper module built around manager-owned data
- multi-instance behavior must be designed in from the start rather than retrofitted later

## Runtime boundary details

### API boundary

Files under `custom_components/firewalla_local/api/` own:

- key generation
- PEM serialization and signing
- HTTP transport
- request envelope construction
- protocol response parsing
- API exception taxonomy

The API layer returns typed integration-facing results and raises typed integration exceptions.

### Coordinator boundary

The coordinator owns:

- routing refresh outputs into the runtime layer
- runtime polling cadence
- refresh timing and availability transitions
- config-entry data and options updates
- update-listener and reload routing for entry-scoped configuration changes
- conversion of raw client responses into the current runtime snapshot input
- log-once unavailable and log-once recovery behavior

The coordinator does not own:

- rule-template matching
- entity selection logic
- service dispatch
- dynamic entity reconciliation
- optimistic command behavior

The coordinator is the runtime router between the API boundary and the manager-owned orchestration layer.

The coordinator is also the owner of config-entry writes because config-entry mutation is part of integration instance lifecycle management rather than rule-specific business logic.

### Manager boundary

Manager modules under `custom_components/firewalla_local/managers/` own:

- rule-template matching
- normalized registry construction and indexing
- lookup helpers for rule-backed surfaces
- write-path orchestration for enable, disable, pause, create, update, and delete operations
- optimistic in-memory state updates after successful commands
- reconciliation when options change or backing rules disappear
- shared lifecycle policy for add, update, remove, and orphan handling

At minimum:

- `IntegrationManager` owns shared integration concerns that cut across platforms or rule actions, including Firewalla appliance device lifecycle, entity lifecycle, startup or reload coordination, and other entry-scoped orchestration that should not live in the coordinator
- `HostManager` owns normalized endpoint-host inventory, watched-device lookup state, device-tracker lookup state, and host-scoped orchestration for watched-device, device-tracker, and host-derived summary surfaces
- `RuleManager` owns rule-specific behavior, including registry indexing, rule-template matching, runtime inventory inputs, and rule-command orchestration
- `UserManager` owns watched-user identity, usage shaping, selection lookups, host association joins, total and unique fallback handling, and user-scoped orchestration for the proven user-usage surface
- normalization owned by `api/` and manager-owned view shaping must preserve the distinction between raw backing group identity and the app-facing identity actually shown to Home Assistant users

Manager methods are the single write and mutation path for runtime behavior above the API layer.

Cross-manager rules:

- direct cross-manager writes are forbidden
- cross-manager orchestration must use explicit entry-scoped signaling or clearly defined coordinator-managed routing contracts when more than one manager reacts to the same transition
- direct read-only calls between managers are acceptable only when they do not create hidden mutation coupling
- managers must not reach into each other's private state or bypass the owning manager's public contract

### Helper boundary

Helper modules under `custom_components/firewalla_local/helpers/` own shared Home Assistant-aware support code such as:

- entity lookup helpers
- service-input normalization helpers
- shared `DeviceInfo` and registry helper logic when that logic does not belong in a manager
- read-only report helpers such as runtime inventory rendering, but only when the underlying data contract is owned by a manager

Helpers may depend on Home Assistant, but they must not become business-logic owners or alternate write paths.

### Utility boundary

Utility modules under `custom_components/firewalla_local/utils/` own pure framework-independent helpers such as:

- duration parsing
- value normalization helpers
- other reusable pure functions

Utilities must not import `homeassistant.*`.

### Entity and service boundary

Entities and services own:

- exposing manager-backed state to Home Assistant
- validating Home Assistant-facing inputs
- mapping failures into translation-ready Home Assistant exceptions
- attaching all surfaces to the correct device and config-entry scope

They do not own command construction, direct protocol calls, or duplicated rule-resolution logic.

## Presence and device-tracker contract

Device-tracker presence is a separate surface from watched-device monitoring.

Rules:

- watched-device connectivity remains a `binary_sensor` concern and continues to
	model bounded online or offline monitoring for selected hosts
- device-tracker presence must use a separate opt-in `device_tracker` platform
	rather than overloading watched-device binary sensors
- device-tracker selection must be stored independently from watched-device
	selection in config-entry options
- device-tracker entities must be limited to MAC-backed LAN hosts only
- pseudo-hosts such as `wg_peer:*` and VPN-related identities must never become
	`device_tracker` entities
- this exclusion is intentional design policy, not a deferred implementation
	phase, because those identities do not map honestly to Home Assistant home or
	away state
- device-tracker state should resolve to `home`, `not_home`, or unavailable
	only
- device-tracker entities must reuse the existing manager-owned host inventory
	and online-state contract rather than introducing a new polling path or a new
	transport read
- device-tracker entities must remain entry-scoped, opt-in, and stable under
	multi-instance loading just like watched-device entities
- each selected tracked client must create its own Home Assistant device
	record keyed to the tracked client's MAC address
- each tracked-client device must set `via_device` to the primary Firewalla
	router device for the owning config entry so the Home Assistant UI keeps the
	client devices grouped under the Firewalla integration
- the `device_tracker` entity must attach to the tracked-client device rather
	than remaining standalone or attempting to attach directly to the router
	device
- tracked-client device lifecycle must be manager-owned and explicit: create on
	selection, preserve while selected but temporarily missing, and remove device
	registry linkage when the client is no longer managed by the config entry

Implementation guidance:

- the first device-tracker slice should use `DeviceTrackerEntity` with
	`source_type=router`
- selection UX should mirror the watched-device options-flow pattern while
	remaining a separate options bucket
- missing device trackers should remain selectable as unavailable placeholders
	rather than being silently dropped from saved options
- client-device registry creation should be driven from one integration-owned
	helper or manager path so `identifiers`, `connections`, `via_device`, and
	removal behavior stay consistent across setup, reload, and deselection
- tracker metadata may expose bounded host facts such as IP, network name,
	connection type, and last active time, but must not invent zone or GPS-like
	semantics

## Storage and state contract

Firewalla state is split into three tiers.

### Tier 1: Config entry

The config entry stores only durable connection material and user preferences.

#### `ConfigEntry.data`

Permitted durable connection material:

- `license`
- `gid`
- `eid`
- `aid`
- Firewalla local IP address
- decrypted symmetric key

#### `ConfigEntry.options`

Permitted user preferences:

- selected rule templates or equivalent durable selection inputs
- future user-controlled feature enablement and presentation preferences

Rules:

- `ConfigEntry.data` contains connection material only
- `ConfigEntry.options` contains user preferences only
- the integration must not persist live runtime payloads into the config entry
- the integration must not persist the full discovered rule list into the config entry

### Tier 2: Runtime data

`entry.runtime_data` contains live objects only.

Permitted runtime objects:

- API client
- coordinator
- manager and related runtime collaborators

Rules:

- runtime data is rebuilt during setup
- runtime data is never treated as durable storage

### Tier 3: In-memory runtime snapshot and registry

Live Firewalla state exists only in memory.

Rules:

- the coordinator owns the current runtime snapshot
- the manager owns the indexed registry derived from the current raw payload or normalized snapshot input
- the repository must not create custom storage files to cache live Firewalla state between reboots
- restart behavior is always fresh poll plus reconstruction of runtime objects

## Normalized registry pipeline

The integration must normalize the Firewalla init payload once per refresh path and expose a shared indexed registry for consumers.

Rules:

- repeated per-platform parsing of the raw init payload is forbidden once a shared registry exists
- shared indexed lookups such as `rule_index` and resolved applicability metadata must be built centrally
- `runtime_inventory.py`, entities, services, and future platforms must consume shared normalized outputs instead of each performing their own ad hoc scans
- caching or lazy lookup is allowed only when it preserves correctness and remains subordinate to the current refresh cycle
- persisted rule-template matching must tolerate optional upstream field evolution without silently changing the intended user-selected rule identity

## Mutation ownership and optimistic updates

All rule mutations flow through the manager layer.

Rules:

- the manager is the only integration layer above `api/` that may orchestrate create, update, delete, enable, disable, or pause operations
- successful commands may update in-memory runtime state optimistically for immediate UI correctness
- the coordinator refresh remains the later source of truth
- optimistic state must remain in memory only
- if later polling disagrees with the optimistic state, the refreshed state wins and the discrepancy is treated as a runtime reconciliation concern

## Config-entry scope contract

All runtime behavior is scoped to one config entry.

Rules:

- service calls must resolve one explicit target entry
- lifecycle reconciliation must mutate only the owning entry scope
- no service, manager, or helper may rely on first-loaded-entry behavior
- diagnostics, reload, unload, reauth, and repair paths must remain entry-scoped

Instance isolation rules:

- manager signaling, helper lookups, and cleanup paths must remain scoped to one config entry
- entity unique IDs must encode entry scope so future multi-instance cleanup remains deterministic
- config-entry lifecycle operations must never mutate another entry's device, entities, or runtime data

## Entity architecture

Entities are derived views over manager-owned state.

Rules:

- all entities must attach to the license-anchored device
- entities must remain stable under live rule-ID churn when the same selected logical rule can be matched through the stored template contract
- groups, users, networks, tags, and targets may inform entity behavior but are not automatically entity types themselves
- rule-backed pause actions are service-driven unless a later architecture decision explicitly introduces a native entity control for them

Rule control model:

- persistent user-managed rules that support pause or resume must be treated as
	one shared control family unless evidence proves otherwise
- switch eligibility must be derived from shared control semantics rather than
	target type alone
- family-specific fields such as schedule, quota, disturb, QoS, app identity,
	and port-forward details are metadata surfaces layered on top of the shared
	control model, not separate control systems
- temporary rules remain a separate family defined by true expiry behavior, not
	by descriptive metadata alone
- the durable interpretation details live in `docs/RULE_MODEL.md`

Switch-enabled rule policy:

- switch eligibility must be defined through one manager-owned logic path
- the same switch-candidate policy must drive live manager behavior, options-flow fallback behavior, and runtime inventory reporting
- only a subset of Firewalla rules should be switch-enabled because the
	integration is intentionally limited to rule shapes that behave like stable
	user-managed on or off controls
- the switch policy should be action and purpose driven, not target-type driven
- Firewalla-managed, temporary, auto-expiring, or otherwise non-persistent rule shapes must remain outside the switch surface
- review reasons and missing readable names are presentation hints and must not
	be used as the sole reason to treat a rule as non-controllable
- explicit purpose exclusions may narrow the exposed subset further even when a
	rule is technically controllable
- user-facing documentation may describe this as a supported subset, but the exact filtering logic remains an internal manager contract

Shared entity rules:

- `custom_components/firewalla_local/entity.py` is a required core file for the first multi-platform runtime buildout
- the shared base entity should provide typed coordinator and manager access, common `DeviceInfo`, and common availability behavior
- shared entity behavior should be centralized rather than repeated across platform files when the same availability or identity logic appears more than once

Unique ID structure rules:

- entity unique IDs must include the integration instance identifier, the immutable object identifier, and a suffix describing the entity surface
- the device identity remains license-anchored even when entity unique IDs include `config_entry.entry_id` for multi-instance isolation
- the suffix must remain stable so registry cleanup and targeted removal logic can classify owned entities reliably

Entity metadata rules:

- entity attributes should expose a concise `purpose` or equivalent metadata field when it materially helps users understand what the entity controls or represents
- purpose metadata must clarify the intended scope of the entity without leaking internal implementation detail or sensitive payload fields
- metadata should be manager-derived and consistent across platforms rather than improvised independently by each entity class
- metadata should be exposed as optional grouped rule details such as schedule,
  expiry, quota, app identity, disturb shaping, QoS, and port-forward context
  when those fields exist on the normalized or raw rule surface

Parallel update rules:

- coordinator-based platforms should explicitly declare `PARALLEL_UPDATES = 0` when entities do not poll independently
- platform concurrency policy must be explicit rather than left to defaults
- if a future platform performs direct device operations outside the coordinator model, its parallel update limit must be justified by the protocol or device behavior

## Naming contract

The repository uses translation-owned naming.

Rules:

- the integration supplies stable unique IDs anchored to immutable identifiers
- Home Assistant owns the final `entity_id`
- user-facing names must come from translation keys, not Python-side `_attr_name` strings or forced suggested object IDs
- mutable labels such as rule names, watched users, and watched devices must flow through `_attr_translation_placeholders`
- entities with mutable labels must refresh `_attr_translation_placeholders` during coordinator updates and invalidate the cached `name` before writing state
- unique IDs must remain stable and name-independent so app-side renames never create duplicate entities or replace entity identity
- normalized host identity must keep human-facing naming separate from DNS-facing naming
- the normalized host contract is `host_name`, `dns_hostname`, `dns_domain`, `dns_fqdn`, `dhcp_name`, and `host_device_type`
- compatibility aliases such as duplicate `display_name` or `fallback_name` fields must not be reintroduced once a normalized host contract exists

## Translation and error contract

User-facing runtime behavior must be translation-ready.

Rules:

- config-flow, reauth, repair, and service failures must map to specific translation keys by failure class
- diagnostics and logs must remain useful without exposing secrets
- exception taxonomy must remain structured from the API layer through the Home Assistant layer

## Security and diagnostics contract

Rules:

- QR payloads and durable connection material are sensitive inputs
- diagnostics must redact secrets, tokens, identifiers, and host-sensitive values
- logs must never expose decrypted payloads, PEM material, signatures, or symmetric-key material
- troubleshooting output should focus on failure class, endpoint behavior, and status shape rather than sensitive values

## Structural evolution rules

- add a shared base entity only when at least two platforms need the same abstraction
- introduce `managers/` as the durable home for orchestration logic rather than keeping that logic in entities, services, or the coordinator
- introduce `helpers/` for shared Home Assistant-aware support code, not for business orchestration
- introduce `utils/` for pure reusable functions, not Home Assistant glue
- keep root-level modules limited to true integration entry points and shared core modules; move specialized reporting or orchestration support under the owning manager or helper directory
- do not collapse the `api/` package back into a monolith
- do not introduce compatibility wrappers or duplicate runtime paths for convenience
- keep the repository minimal by default, but never at the expense of clear ownership boundaries
