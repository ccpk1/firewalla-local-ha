# Firewalla Local development standards

## Purpose

This document defines the prescriptive coding standards for the Firewalla Local integration.

It explains how code should be written, reviewed, and extended so the repository stays aligned with the architecture contract.

## Naming baseline

- Product name: `Firewalla Local`
- Integration domain: `firewalla_local`
- Package path: `custom_components/firewalla_local/`
- Pure protocol boundary: `custom_components/firewalla_local/api/`

## General rules

- prefer the smallest coherent change that solves the real problem
- keep typing explicit and complete
- keep user-facing behavior translation-ready from day one
- preserve layer boundaries even when a shortcut looks faster
- avoid convenience fallbacks for identity, transport, or mutation behavior

## Lexicon standards

Use repository terminology consistently.

- use `domain` only for the Home Assistant integration domain `firewalla_local`
- use `rule`, `rule template`, `runtime snapshot`, and `registry` for Firewalla data concepts
- use `item type` or `record type` for Firewalla-specific categories such as `rule`
- use `host` for Firewalla endpoint or client inventory records
- use `host_name` for the primary user-facing Firewalla host label
- use `dns_hostname`, `dns_domain`, and `dns_fqdn` for DNS-oriented host identity fields
- use `dhcp_name` only for the DHCP-origin hostname field
- use `host_device_type` for the Firewalla host classification field
- use `entity` only for Home Assistant platform objects
- use `device tracker` only for Home Assistant `device_tracker` entities and never as shorthand for generic host inventory or the Firewalla box device
- use `unique ID` for the stable registry identifier and `entity_id` for the Home Assistant registry string
- use `scope metadata` for applicability data such as networks, devices, tags, and targets

Critical rule:

- never call a Firewalla rule or normalized runtime record an entity
- never call a Firewalla host record a device unless the code is explicitly modeling a Home Assistant device registry object
- never use `tracked device` as a synonym for the Home Assistant `device_tracker` surface
- never use `domain` to describe a Firewalla item type, record type, or rule-specific behavior

Normalized host identity rule:

- keep the primary Firewalla host label separate from DNS and DHCP-derived naming fields
- do not collapse `host_name`, `dns_hostname`, `dns_domain`, `dns_fqdn`, and `dhcp_name` into one convenience field
- do not add compatibility aliases such as duplicate `display_name` or `fallback_name` fields once a normalized host contract exists

User-facing identity rule:

- when local payloads expose both a user-facing identity and an affiliated backing group or tag, prefer the user-facing identity for Home Assistant names and attributes
- treat backing group names as implementation detail unless the current surface is explicitly diagnostic, inventory-oriented, or otherwise intended to expose raw Firewalla structure
- do not concatenate backing group names into entity or attribute labels just because the raw payload links the user through that group
- when a rule `applies_to` label is intentionally rewritten from a backing group to the affiliated user identity, `applies_to_kind` must also be rewritten to `user` rather than preserving the raw backing-group kind

## Constants taxonomy

Use explicit constants instead of scattered literals.

Approved constant families:

- `DOMAIN`
- `CONF_*`
- `DEFAULT_*`
- `ATTR_*`
- `SERVICE_*`
- `SERVICE_FIELD_*`
- `TRANS_KEY_*`
- `TRANS_PLACEHOLDER_*`
- `RULE_*`
- flow-step constants once flow complexity justifies them

The constant system should stay disciplined but compact. Do not introduce a large taxonomy unless the repository complexity actually requires it.

Constant naming rule:

- prefix by contract surface first, then by item type or purpose only when needed

Usage matrix:

- `CONF_*`: config-entry data or options keys only
- `DEFAULT_*`: default values only
- `RULE_*`: normalized Firewalla rule record values and fixed rule-item literals
- `ATTR_*`: Home Assistant entity state attributes only
- `SERVICE_*`: service names only
- `SERVICE_FIELD_*`: service schema keys and `call.data` access only
- `TRANS_KEY_*`: translation identifiers only
- `TRANS_PLACEHOLDER_*`: translation placeholder names only

Rules:

- do not use `ATTR_*` constants in service schemas or `call.data`
- do not use `CONF_*` constants for service selector fields
- do not use `domain` in constant names to describe Firewalla item types such as rules
- prefer compact, honest families over large framework-style taxonomies that the repository does not need

## Type system

- all public and internal functions must be type hinted
- use modern Python typing syntax
- use dataclasses, enums, or `TypedDict` for stable structures with fixed keys
- use dynamic mappings only where keys are genuinely variable at runtime
- avoid `dict[str, object]` for stable protocol, config, manager, or service payload shapes when a stronger type is available
- avoid type suppressions unless no honest type expression can represent the pattern cleanly

Type selection rule:

- stable protocol payloads, normalized models, manager command payloads, and service inputs should be strongly typed
- ad hoc dynamic lookup maps may remain dynamic when that is the honest representation

## Module and layer boundaries

### `api/`

Files in `custom_components/firewalla_local/api/` own:

- cryptography
- signing
- HTTP transport
- protocol parsing
- API-specific exception types

Rules:

- nothing inside `api/` may import `homeassistant.*`
- `api/` must not become a single-file monolith
- transport, auth, crypto, and response handling should remain separated when they justify separate files

### Coordinator

The coordinator owns:

- routing refresh outputs into the runtime layer
- polling cadence
- refresh orchestration
- availability transitions
- config-entry writes and reload-triggering config updates
- normalized snapshot refresh inputs

Rules:

- the coordinator is primarily a router and refresh orchestrator, not a business-logic owner
- the coordinator must not own rule-template matching, service dispatch, or entity reconciliation policy
- config-entry writes belong to the coordinator, not to managers, helpers, services, or platform files

### Manager layer

Manager modules under `custom_components/firewalla_local/managers/` own:

- rule-template matching
- rule resolution
- lifecycle reconciliation
- mutation orchestration
- optimistic updates
- shared indexed runtime lookups

Rules:

- all rule mutations above the API layer must flow through manager methods
- entities, flows, and services must not duplicate command logic or payload construction once manager methods exist
- the minimum manager set should include `integration_manager.py`, `host_manager.py`, and `rule_manager.py`
- `IntegrationManager` owns shared lifecycle concerns such as Firewalla appliance device lifecycle and entity lifecycle
- `HostManager` owns endpoint-host inventory, watched-device orchestration, device-tracker eligibility, device-tracker selection lookups, and host-derived appliance summary lookups
- watched-device online evaluation and device-tracker away evaluation must remain separate manager-owned contracts, each backed by its own general-options setting
- tracked-client device-registry lifecycle for selected device trackers must be
	explicitly owned by integration code, including create, refresh, deselect,
	config-entry unload, and stale-device removal behavior
- `RuleManager` owns rule-specific orchestration, indexed lookup state, runtime inventory inputs, and rule-command behavior
- `UserManager` is the owner for watched-user joins, usage shaping, and fallback handling over the proven local user payload
- direct cross-manager writes are forbidden
- managers may use explicit entry-scoped signals or other centralized orchestration contracts for cross-manager reactions
- direct read-only manager calls are acceptable only when they do not create hidden mutation coupling

### Helpers

Helper modules under `custom_components/firewalla_local/helpers/` own shared Home Assistant-aware support code.

Rules:

- helpers may import Home Assistant APIs
- helpers must not own business orchestration or write paths
- helpers should contain reusable integration glue such as entity lookup or shared registry helper functions
- report helpers such as runtime inventory belong in `helpers/` only if they are read-only views over manager-owned data; otherwise they belong in the owning manager module

### Utils

Utility modules under `custom_components/firewalla_local/utils/` own pure reusable functions.

Rules:

- utils must not import `homeassistant.*`
- utils are the correct home for pure parsing, formatting, and value-normalization helpers
- utils must not accumulate orchestration logic that belongs in managers

### Entities and services

Rules:

- entities and services are presentation and interaction surfaces only
- they must delegate business logic to manager methods
- they must not perform protocol calls directly
- they must map failures into specific Home Assistant exception types and translation keys
- services that target hosts must resolve against the normalized host contract and keep `host_name` as the primary human-facing selector surface
- watched-user entity attributes must distinguish raw payload facts from
	integration-derived joins, especially for totals, per-app usage, and
	host-derived `last_active` metadata
- watched-user, watched-device, and device-tracker attributes must not expose backing group names when an app-facing user identity is available for the same relationship
- `device_tracker` is reserved for MAC-backed LAN hosts only; VPN, tunnel,
	overlay, and pseudo-host identities such as `wg_peer:*` are excluded by
	design and must not be surfaced as presence trackers
- selected device trackers must attach to a distinct tracked-client device
	record keyed by the client's MAC address, and that device must use
	`via_device` to point at the primary Firewalla router device for the config
	entry

## Async and event loop rules

- all network requests in `custom_components/firewalla_local/api/` must use `aiohttp`
- the `requests` library is forbidden
- do not perform blocking I/O in the Home Assistant event loop
- CPU-bound cryptographic work must be offloaded with `hass.async_add_executor_job()` when called from async Home Assistant code
- keep executor usage tightly scoped to the actual blocking work

## Time and timezone standards

- time-bucketed Firewalla data such as day, week, and month reports must use the Firewalla appliance timezone as the canonical timezone when the box exposes a valid timezone name
- Home Assistant timezone is a fallback only when the Firewalla runtime does not expose a usable timezone
- do not derive canonical period boundaries from Home Assistant timezone when Firewalla has already provided its own timezone context
- if a feature separates canonical bucket timezone from display timezone, that distinction must be explicit in the code and surfaced clearly in the response contract
- time-bucketed service responses should identify the timezone used for period derivation when that context materially affects interpretation

## Identity and device registry rules

- the Home Assistant device registry identity must use the immutable `license` value from the QR payload
- `gid` must never be used as the device registry identifier
- IP addresses and hostnames must never be used as unique IDs
- entity unique IDs must remain stable under re-pairing and network changes
- all entities must attach to the correct license-anchored device

## Entity standards

### Entity naming

- prefer `_attr_has_entity_name = True` for entity surfaces attached to the shared Firewalla device
- user-facing names must be owned by translation keys
- do not hardcode `_attr_name` for production entity names
- do not force entity-ID shaping with `_attr_suggested_object_id` for presentation reasons
- mutable labels such as rule names, watched users, and watched devices must use `_attr_translation_placeholders`
- when mutable placeholders can change at runtime, refresh `_attr_translation_placeholders` in `_handle_coordinator_update()` and invalidate the cached `name` before calling the base implementation
- entity names must not embed the device name
- the repository follows a translation-owned naming contract
- unique IDs must remain anchored to immutable identifiers and must not depend on the current friendly name

### Entity identity

- unique IDs must be based on immutable identifiers
- unique IDs must include the config-entry instance identifier, the immutable object identifier, and a stable suffix
- Home Assistant owns the final `entity_id`
- entity identity must survive live rule-ID churn when the stored rule template still resolves to the intended logical rule
- device identity remains license-anchored even when entity unique IDs include entry scope for multi-instance isolation

### Entity lifecycle

- dynamic entity add, update, remove, and orphan handling must follow one shared lifecycle policy
- options changes must trigger explicit reconciliation behavior
- missing backing rules must have a defined handling policy and must not drift into indefinite orphaning by accident
- shared entity base classes are allowed only when at least two platforms need the same abstraction

### Shared entity base

- `custom_components/firewalla_local/entity.py` is part of the expected core runtime layout for the first multi-platform buildout
- use `entity.py` as the shared base for common availability, typed coordinator access, typed manager access, `DeviceInfo`, identity behavior, and shared metadata patterns
- the shared base entity should centralize coordinator-availability handling and any common typed accessors instead of repeating those patterns across platform files
- entity base helpers must stay focused on shared entity behavior and must not become a business-logic layer

### Entity scope

- groups, users, networks, devices, and tags may be scope metadata without becoming entity types
- rule-backed pause behavior belongs in services unless a later architecture decision explicitly changes that contract

### Entity metadata

- add concise purpose-oriented metadata when it materially helps users understand what an entity is for
- keep purpose metadata stable, readable, and manager-derived
- primary control and monitoring entities should remain uncategorized unless their semantics are truly diagnostic
- do not expose internal debugging structures or sensitive payloads just to make an entity feel richer

### Platform concurrency

- coordinator-based platforms should set `PARALLEL_UPDATES = 0` explicitly when entities do not poll independently
- any non-zero or non-default parallel update limit must be justified by platform behavior and protocol constraints
- platform concurrency policy should be declared in the platform module rather than left implicit

## Service standards

- service handlers must resolve one explicit config-entry scope
- service handlers must validate Home Assistant-facing input and then delegate to manager methods
- services must not construct Firewalla mutation payloads independently from the manager layer
- services must remain useful even when no entity exists for the targeted rule, if the service contract is rule-based rather than entity-based

## Mutation and write-path standards

- manager methods are the single write path above the API layer
- successful commands may update in-memory runtime state optimistically
- optimistic changes must remain in memory only
- the next coordinator refresh remains the source of truth
- if refreshed state disagrees with optimistic state, the refreshed state wins and the discrepancy must be handled as reconciliation, not hidden silently

## Runtime registry standards

- normalize the Firewalla init payload once per refresh path when practical
- shared indexed lookups such as `rule_index` must be built centrally
- future platforms, inventory tools, and services must consume shared normalized outputs instead of repeating full payload scans
- lazy lookup or caching is acceptable only when it preserves correctness and does not create a second source of truth

## Config-entry scope rules

- all runtime behavior must operate within one explicit config-entry scope
- do not rely on first-loaded-entry behavior
- services, repairs, reloads, unloads, diagnostics, and reauth flows must target the owning entry only
- signal names, cleanup logic, and unique-ID construction must preserve per-entry isolation for future multi-instance support

## Exception handling rules

- the API layer must translate transport, auth, timeout, and protocol failures into custom integration exceptions
- raw `aiohttp` tracebacks must not escape the API boundary as user-facing failures
- use specific exception classes for auth, validation, timeout, and protocol failures
- always chain exceptions with `from err` when re-raising
- broad hardcoded user-facing errors are forbidden in runtime code

Home Assistant mapping rules:

- `ConfigEntryAuthFailed` for persistent credential rejection
- `ConfigEntryNotReady` for temporary setup and connectivity failures where appropriate
- `ServiceValidationError` for invalid user input
- `HomeAssistantError` for runtime failures that are not user-input mistakes

## Authentication and retry rules

- a persistent auth failure is two consecutive `401 Unauthorized` responses
- the client may perform one immediate retry after the first `401`
- if the second response is also `401`, raise `FirewallaAuthError`
- do not place `401` failures into long retry loops
- treat timeouts and `5xx` responses as operational failures, not auth failures

## Logging rules

- use lazy structured logging
- do not use f-strings in log calls
- never log QR payloads, PEM material, tokens, signatures, decrypted payloads, or symmetric-key material
- keep logs useful for debugging without exposing secrets or personal data
- avoid repetitive coordinator error spam when auth failure should hand off to reauth handling

## Localization and translation rules

- do not hardcode user-facing production strings in Python when translation keys are appropriate
- English translation files are the only manually edited source for translated integration text
- config-flow, reauth, service, and repair messages must be translation-ready
- exception mapping should be specific by failure class rather than collapsing multiple failures into a generic error bucket
- icon behavior should use Home Assistant translation or icon infrastructure where supported instead of Python-side presentation rules when that yields a cleaner durable contract

## Diagnostics and security rules

- `diagnostics.py` must use Home Assistant redaction helpers such as `async_redact_data`
- diagnostics must scrub secrets, tokens, identifiers, sensitive host details, and sensitive payload fields
- entity attributes must not expose secrets or durable credential material
- QR payloads and local credentials must be handled as sensitive input throughout the codebase

## Review rules

Review changes against these questions:

- does this change preserve the `api/` boundary?
- does business logic remain in manager methods instead of entities, flows, or services?
- do config-entry writes stay in coordinator-owned paths?
- do specialized shared modules live under `managers/`, `helpers/`, or `utils/` instead of becoming unowned root files?
- does the change preserve entry-scoped behavior?
- are user-facing failures translation-ready and specifically typed?
- does the change keep entity identity stable?
- does the change reuse the shared registry pipeline instead of introducing another ad hoc lookup path?
- does the change introduce orphan-prone lifecycle behavior without an explicit reconciliation policy?

## Boundary enforcement

- maintain architecture lint checks that enforce purity boundaries, write ownership, and layer placement rules
- boundary checks should reject Home Assistant imports in `utils/`
- boundary checks should reject duplicated business logic or write paths in services, flows, and platform files
- boundary checks should reject unowned specialized root modules when the code clearly belongs under `managers/`, `helpers/`, or `utils/`

## Validation workflow

Run these commands for relevant changes:

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/firewalla_local`
- `python -m pytest tests/ -v`

Documentation and translations must be updated when behavior changes require them.