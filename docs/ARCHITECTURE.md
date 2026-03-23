# Firewalla Local architecture

## Purpose

This document defines the durable architecture contract for the Firewalla Local Home Assistant integration.

It exists to keep the repository minimal, typed, and maintainable while the runtime implementation grows from the current scaffold into a real local-only integration.

## Project status and disclaimer

This repository is an independent Home Assistant integration project.

It is not affiliated with, endorsed by, or supported by Firewalla.

The security and architecture guidance in this document reflects the
maintainer's current technical view of the protocol behavior, operational
trade-offs, and deployment risks. It should not be read as official vendor
documentation or as a vendor security statement.

Use this project at your own risk.

## Product naming

- GitHub repository name: `firewalla-local-ha`
- Home Assistant UI name: `Firewalla Local`
- Home Assistant integration domain: `firewalla_local`
- Home Assistant package path target: `custom_components/firewalla_local/`

## Mission

The integration provides local runtime access to a Firewalla box from Home Assistant.

The MVP architecture is responsible for:

- cloud-provisioned QR-based pairing
- durable local credential establishment
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

- first-time pairing starts from the Firewalla QR JSON payload but uses a split architecture:
	- cloud provisioning through `login/eptoken` and `ept/rendezvous/me`
	- local runtime over `http://{local_ip}:8833/v1/encipher/message/{gid}`
- the QR payload includes fields such as `gid`, `seed`, `license`, `ek`, and `ipaddress`
- local box communication uses encrypted HTTP POST requests on port `8833`
- local runtime credentials are `gid`, `eid`, `aid`, and the decrypted symmetric key
- cryptographic signing and key generation require SPKI public PEM and PKCS#8 private PEM handling

The architecture treats unresolved mutation details as feature-level questions, not transport-level questions.

## Security posture

This section explains the high-level security approach behind the integration
and the trade-offs that come with it.

### Split architecture: cloud provisioning and local runtime

The current architecture is intentionally split into two stages.

- Provisioning is cloud-brokered. Initial pairing uses the Firewalla QR payload
	plus Firewalla cloud endpoints to establish local trust material and recover
	the durable symmetric key required for local messaging.
- Runtime is local-first. Day-to-day communication is designed around LAN
	access to the box on port `8833` once local credentials have been
	established.
- The integration architecture does not depend on storing a Firewalla account
	password in Home Assistant.
- If the paired local credentials remain valid, the architecture expects normal
	runtime polling and control to continue without depending on a permanent
	cloud control path after provisioning.

This split is a pragmatic compromise between Firewalla's pairing model and Home
Assistant's preference for durable local runtime control.

### Local HTTP and encrypted payloads

The local runtime uses HTTP on port `8833`, not HTTPS.

That matters because transport security and payload security are not the same
thing.

- The current protocol evidence in this repository, including `poc.py` and the
	local API client implementation, shows application-layer encryption of the
	request and response payloads before they cross the network.
- The current implementation path uses AES-256-CBC encrypted payloads wrapped
	in JSON and sent to the Encipher message endpoint.
- This design reduces exposure of raw firewall state and control payloads on
	the LAN, but it is not a substitute for a trusted network or for good local
	segmentation practices.

Observed message envelopes also include timestamps and unique message
identifiers. The integration preserves that shape, but this document does not
treat those fields alone as a complete replay-protection guarantee.

### Stored credentials and host security

Home Assistant persists config entries on disk through its own storage system.

For this integration, the architecture currently expects the durable local
connection material to include values such as:

- `license`
- `local_ip`
- `gid`
- `eid`
- `aid`
- the decrypted symmetric key used for local runtime access

Those values are materially sensitive.

They are still narrower in scope than a Firewalla account password, but a host
compromise could expose enough credential material to control or observe the
paired box through the local runtime path.

If you no longer trust the Home Assistant host that was paired to the box, the
maintainer's recommended response is to revoke that pairing from the Firewalla
mobile app and create a new pairing. Exact menu labels can vary by app
version, so this document does not treat any specific UI path as a stable API
contract.

### Diagnostics and log exposure

The current repository already treats diagnostics and logs as sensitive output
surfaces.

- `custom_components/firewalla_local/diagnostics.py` redacts `aid`, `eid`,
	`gid`, `license`, `local_ip`, and `symmetric_key` from exported diagnostics.
- `docs/DEVELOPMENT_STANDARDS.md` forbids logging QR payloads, PEM material,
	tokens, signatures, or decrypted sensitive payload data.
- The architecture expects troubleshooting output to focus on failure class,
	HTTP status, and protocol behavior rather than secret values.

This is an area where host security still matters: safe logging reduces casual
exposure, but it does not make a compromised Home Assistant host safe.

### Recommended deployment posture

The maintainer's recommendation is to treat this integration as trusted-network
software.

- Keep the Home Assistant host on your trusted management or core LAN.
- Isolate untrusted IoT devices onto a separate VLAN or equivalent network
	segment.
- Use Firewalla rules to prevent untrusted device segments from initiating
	traffic toward the Home Assistant host when your deployment allows it.
- Do not expose Home Assistant directly to the public internet without a secure
	remote-access design.

This guidance is opinionated and conservative by design. It reflects the
maintainer's view that local encrypted payloads are useful, but they do not
eliminate the need for standard LAN hardening and host security.

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
- `eid`
- `aid`
- Firewalla local IP address
- decrypted symmetric key

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
