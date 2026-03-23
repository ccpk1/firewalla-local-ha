# Firewalla Local architecture

## Purpose

This document defines the durable architecture contract for the Firewalla Local Home Assistant integration.

It exists to keep the repository minimal, typed, and maintainable while the runtime implementation grows from the current scaffold into a real local-only integration.

## Product naming

- GitHub repository name: `firewalla-ha`
- Home Assistant UI name: `Firewalla Local`
- Home Assistant integration domain: `firewalla_local`
- Home Assistant package path target: `custom_components/firewalla_local/`

## Mission

The integration provides local-only access to a Firewalla box from Home Assistant.

The MVP architecture is responsible for:

- local QR-based pairing
- local credential establishment
- signed local REST communication over port `8833`
- coordinator-backed rule discovery and synchronization
- Home Assistant configuration, reauthentication, diagnostics, and entity wiring

The architecture is not responsible for introducing unnecessary layers, external repositories, or speculative protocol abstractions.

## Terminology

- Device: The physical Firewalla hardware represented in the Home Assistant device registry
- Config entry: The Home Assistant configuration record for one paired Firewalla box
- API submodule: The pure internal module tree under `custom_components/firewalla_local/api/` that handles protocol work without importing `homeassistant.*`
- Coordinator: The Home Assistant update coordinator that converts API results into integration state
- Entity: A Home Assistant entity derived from coordinated Firewalla state
- Connection parameters: Values required to communicate with the box, such as host details and `gid`
- Identity anchor: The immutable value used to tie the Home Assistant device and config entry to the physical hardware

## Verified protocol baseline

The architecture assumes the following are settled inputs:

- first-time pairing is local-only and starts from the Firewalla QR JSON payload
- the QR payload includes fields such as `gid`, `seed`, `license`, `ek`, and `ipaddress`
- local box communication uses signed HTTP GET and POST requests on port `8833`
- local rule polling endpoints are valid MVP inputs for coordinator-backed synchronization
- cryptographic signing and key generation require SPKI public PEM and PKCS#8 private PEM handling

The architecture treats unresolved mutation details as feature-level questions, not transport-level questions.

## Identity contract

The immutable Home Assistant device identity is the QR `license` value.

Rules:

- `license` is the primary device registry identity anchor
- `license` is the config-entry identity anchor unless a later Home Assistant constraint forces a more specific split
- `gid` is not a device identity and must never be used as the Home Assistant device registry identifier
- IP addresses and hostnames must never be used as unique identifiers
- `gid` remains a required connection parameter for API communication

This rule exists so entity and device identity survive re-pairing, IP changes, and local recovery scenarios.

## Architecture posture

The integration uses coordinator-centered Home Assistant wiring backed by a mandatory pure internal API submodule.

Target structure:

- `custom_components/firewalla_local/__init__.py`
- `custom_components/firewalla_local/config_flow.py`
- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/const.py`
- `custom_components/firewalla_local/models.py`
- `custom_components/firewalla_local/diagnostics.py`
- `custom_components/firewalla_local/api/`
- platform modules as needed

The `api/` tree is the only place where crypto, signing, low-level auth, and HTTP transport logic should live.

## Runtime boundaries

### Home Assistant layer

Files in the integration root handle:

- config entry lifecycle
- config flow and reauth flow
- coordinator state management
- platform entity creation
- diagnostics exports
- Home Assistant exceptions and translations

### Pure API submodule

Files under `custom_components/firewalla_local/api/` handle:

- key generation
- PEM serialization and signing
- request construction
- HTTP session interactions with the Firewalla box
- protocol response parsing
- custom API exception definitions

Files under `api/` must not import `homeassistant.*`.

## Storage and state contract

To ensure Home Assistant performance and prevent disk I/O bottlenecks, data must be strictly isolated into three tiers.

### Tier 1: Config entry

The config entry is persisted to disk through Home Assistant storage and must store only the data required to reconnect to the device or render the user's preferred entities.

It is strictly divided into two mappings.

#### `ConfigEntry.data`

`ConfigEntry.data` contains immutable connection material populated during initial setup.

Permitted data:

- `license`
- `gid`
- Firewalla IP address
- generated `private.pem`
- generated `public.pem`

#### `ConfigEntry.options`

`ConfigEntry.options` contains mutable user preferences populated through the Home Assistant options flow.

Permitted data:

- the list of Firewalla rule UUIDs selected for exposure as Home Assistant switch entities
- future user-controlled sensor or entity enablement preferences

Rules:

- `ConfigEntry.data` must mutate rarely
- `ConfigEntry.options` must contain preferences only
- dynamic API responses must never be written to either config entry mapping
- live device state must never be written to either config entry mapping
- the full discovered rule list must never be written to either config entry mapping

### Tier 2: Runtime data

Runtime data is in-memory state created during `async_setup_entry` and does not survive a reboot.

Permitted data:

- the instantiated `FirewallaApiClient`
- the `DataUpdateCoordinator` instance

Rules:

- runtime data holds live objects only
- runtime data is recreated on setup
- runtime data is not a persistence layer

### Tier 3: Coordinator cache

The live Firewalla state exists only in the in-memory coordinator cache.

Examples:

- active rules
- blocked IPs
- alarms
- other large API payloads

Rules:

- Firewalla state must be fetched fresh from the local API
- the integration must not create custom storage files to cache Firewalla state between reboots
- if Home Assistant restarts, the coordinator simply performs a fresh poll
- entities consume normalized coordinator data and never perform protocol work directly

## Dependency contract

The integration must depend on the `cryptography` package.

Rules:

- `cryptography` is the required library for RSA key generation and PKCS#8/SPKI serialization
- no fallback crypto library should be designed into the architecture
- the dependency must be declared in `manifest.json`
- tests and typing expectations must reflect the presence of this dependency

## Reauthentication contract

Authentication failure follows the one-retry rule.

Rules:

- the API client may retry once immediately after a `401 Unauthorized`
- if the immediate retry also returns `401 Unauthorized`, the API layer must raise `FirewallaAuthError`
- the Home Assistant layer must convert `FirewallaAuthError` into `ConfigEntryAuthFailed`
- `401 Unauthorized` must not enter long retry windows or indefinite coordinator retry loops
- network timeouts and `5xx` responses are operational failures, not auth failures

## Supported capabilities

This architecture is designed to support:

- initial key pairing and local credential establishment
- signed REST client behavior
- rule discovery and polling
- user selection of rule-backed entities
- coordinator-backed state updates
- reauthentication when local credentials are no longer accepted

This architecture explicitly does not include:

- exact mutation semantics for every rule class
- non-rule capabilities beyond the MVP
- storage beyond config-entry needs unless implementation proves it necessary
- cloud-mediated access paths or MSP fallback behavior

## Localization contract

User-facing text belongs in translation files, with English as the source of truth.

Architecture implications:

- flow labels and errors must be translation-ready
- repair and reauth messaging must be translation-ready
- diagnostics and log text must avoid secret leakage while remaining clear

## Structural evolution rules

- Start with the root integration files plus the pure `api/` submodule
- Add shared entity base files only when at least two platforms need the abstraction
- Add `helpers/` or `utils/` only when a clear responsibility cannot live cleanly in `models.py`, `const.py`, or `api/`
- Keep pure protocol code under `api/` and Home Assistant orchestration outside it
- Do not reintroduce a monolithic `api.py` once the `api/` boundary exists
