# Support note: Phase 3b standards adoption

## Purpose

Record which external best practices were adopted into the Firewalla Local guidance documents during the Phase 3b documentation gate and which patterns were intentionally not copied.

This note is not a source-of-truth architecture document. It exists to explain the standards adoption outcome behind the durable repository guidance.

## Source references reviewed

- `https://github.com/ccpk1/ChoreOps/blob/main/docs/QUALITY_REFERENCE.md`
- `https://github.com/ccpk1/ChoreOps/blob/main/docs/ARCHITECTURE.md`
- `https://github.com/ccpk1/ChoreOps/blob/main/docs/DEVELOPMENT_STANDARDS.md`

## Adopted patterns

### 1. Lexicon and terminology contracts

Apply the same discipline of using precise repository terminology so architectural discussions stay stable as the integration grows.

Adopted Firewalla rule:

- use `rule`, `rule template`, `runtime snapshot`, and `registry record` for normalized Firewalla data structures
- use `entity` only for Home Assistant platform objects
- use `unique ID` for registry identity and `entity_id` only for the Home Assistant registry string
- use `device identity` for the license-anchored Firewalla box relationship
- use `scope metadata` for networks, devices, tags, and targets when they inform a rule but are not standalone entity types

Adoption result:

- avoids mixing Firewalla rule records with Home Assistant entities
- keeps future services, repairs, and diagnostics aligned with the architecture

### 2. Quality-reference style documentation

ChoreOps keeps a compact quality reference that maps durable contracts to evidence locations.

Adopted Firewalla rule:

- add a repository-local quality reference document after the architecture and standards refresh so Platinum expectations are tracked through contracts and evidence, not memory or plan prose

Adoption result:

- prevents `quality_scale.yaml` from drifting away from actual implementation evidence
- gives reviewers a stable document for architecture and standards conformance

### 3. Strong layer boundaries

The ChoreOps materials are clear that pure logic, HA-aware helpers, orchestration, and infrastructure each have separate ownership.

Adopted Firewalla rule:

- `api/` remains protocol-only and never imports `homeassistant.*`
- coordinator is the router and refresh orchestrator and owns config-entry writes
- manager layer owns rule matching, mutation orchestration, optimistic state updates, lifecycle reconciliation, and manager-owned registry indexing
- entities remain presentation surfaces over manager-owned resolved state
- helper and utility modules now have explicit directory ownership boundaries

Adoption result:

- directly addresses the current switch implementation carrying too much business logic at the entity edge

### 4. Single write and mutation ownership

ChoreOps uses manager-owned write paths rather than allowing UI or service layers to mutate storage directly.

Adopted Firewalla rule:

- all Firewalla mutations must flow through manager methods
- `services.py`, platform files, and flows must not build ad hoc mutation payloads independently once manager APIs exist
- the manager becomes the single source of truth for update, delete, create, pause, and optimistic local-state mutation behavior

Adoption result:

- avoids duplicated command logic across switch entities, services, and future platforms

### 5. Signal-first or event-first orchestration where decoupling is needed

ChoreOps uses dispatcher signals to avoid tight manager coupling.

Adopted Firewalla rule:

- do not adopt an event system just to mimic ChoreOps complexity
- do adopt the underlying rule that cross-manager orchestration must be explicit and loosely coupled when more than one runtime component reacts to the same state transition
- direct cross-manager writes are forbidden
- any signaling or central routing used for cross-manager reactions must remain entry-scoped

Adoption result:

- preserves simplicity while still preventing direct, implicit coupling across future manager, service, repair, and entity layers

### 6. Entry-scoped lifecycle discipline

The ChoreOps docs strongly reinforce instance scoping and cleanup behavior.

Adopted Firewalla rule:

- every mutation, reconciliation pass, service call, and dynamic entity decision must be scoped to a single config entry
- options changes and reload paths must use one explicit lifecycle contract for add, update, remove, and orphan cleanup behavior
- missing backing rules need a defined policy instead of indefinite orphaning

Adoption result:

- aligns with Home Assistant multi-entry expectations and prevents hidden global assumptions

### 7. Honest type-system rules

ChoreOps is explicit that `TypedDict` is appropriate for stable shapes while dynamic maps should remain honest dynamic dictionaries.

Adopted Firewalla rule:

- use dataclasses or `TypedDict` for stable protocol, config, manager, and event payloads
- use dynamic mappings only where Firewalla payload structure is genuinely variable or user-driven
- document the boundary so the codebase does not oscillate between over-modeled and under-typed structures

Adoption result:

- improves mypy value without introducing a wave of suppressions for dynamic lookup paths

### 8. Entity and lifecycle standards

ChoreOps documents entity cleanup, dynamic creation rules, and lifecycle synchronization explicitly.

Adopted Firewalla rule:

- document a single entity lifecycle model covering setup, options changes, reconciliation, orphan handling, and registry stability
- require `entity.py` as a core shared base file for the first multi-platform buildout
- define which responsibilities belong in the shared base entity: typed coordinator access, typed manager access, common availability behavior, shared `DeviceInfo`, and common metadata conventions
- keep the UID-first naming contract explicit unless deliberately reopened
- require explicit `PARALLEL_UPDATES` policy for coordinator-based platforms
- allow concise purpose-oriented entity metadata when it materially improves user clarity

Adoption result:

- prevents each new platform from inventing its own cleanup and identity behavior

### 9. Error mapping and translation posture

ChoreOps makes translation-backed exceptions and specific exception classes non-negotiable.

Adopted Firewalla rule:

- define translation-backed config-flow, service, and repair errors by failure class
- preserve a clear exception taxonomy from API boundary through Home Assistant mapping
- require exception chaining and forbid broad hardcoded user-facing errors in runtime code

Adoption result:

- closes one of the current Platinum-readiness gaps without needing ChoreOps-scale translation machinery

### 10. Validation and review as architecture enforcement

The quality reference ties architectural rules to validation and review gates.

Adopted Firewalla rule:

- future quality reference should map each durable contract to evidence locations and validation expectations
- documentation must explain what reviewers should reject, not just what builders should prefer
- boundary enforcement is now a required Phase 3b implementation concern rather than a soft review preference

Adoption result:

- makes Phase 3b outcomes durable across future contributors and reviews

## Patterns to adapt carefully, not copy directly

These ChoreOps practices are valuable but must be simplified for Firewalla Local:

- large constant taxonomies: keep naming disciplined, but avoid importing ChoreOps-scale prefix systems unless Firewalla complexity truly grows to require them
- dispatcher-heavy event choreography: use only where multiple runtime components need clean decoupling; do not introduce a signal mesh prematurely
- dual human-readable and machine-readable entity-ID strategy: keep the Firewalla UID-first identity contract already accepted for this repository
- storage-heavy CRUD and migration architecture: Firewalla Local does not currently need ChoreOps-style custom storage ownership because runtime state is coordinator-driven and config-entry bounded
- dashboard and translation-sensor patterns: informative but not relevant to Firewalla Local's current scope

## Adopted repository outcomes

The standards refresh produced these durable Firewalla-specific outcomes:

- coordinator owns config-entry writes and runtime routing
- minimum manager architecture is explicit: `IntegrationManager`, `HostManager`, and `RuleManager`
- `managers/`, `helpers/`, `utils/`, and `entity.py` now have named ownership boundaries
- `runtime_inventory.py` is no longer acceptable as an unowned root-level specialized module
- entity unique IDs must include entry scope, immutable object identity, and stable suffix
- device identity remains license-anchored
- shared base entity behavior is part of the core runtime layout for the first multi-platform expansion
- coordinator-based platforms are expected to declare `PARALLEL_UPDATES = 0` explicitly unless a different limit is justified
- quality reference and review-gate expectations are documented as durable repository rules

## Patterns intentionally not copied

These ChoreOps practices remain intentionally out of scope unless future repository complexity justifies them:

- large constant taxonomies beyond what Firewalla Local actually needs
- dispatcher-heavy event meshes used only for parity with a larger integration
- dual human-readable and machine-readable default entity-ID strategies that conflict with the current UID-first rule
- storage-heavy CRUD and migration architecture that does not fit a coordinator-driven Firewalla runtime
- dashboard, translation-sensor, and other frontend-specific patterns outside the current repository scope

## Current role of this note

Use this note as context for why the repository standards now look the way they do.

Do not treat it as a substitute for:

1. `docs/ARCHITECTURE.md`
2. `docs/DEVELOPMENT_STANDARDS.md`
3. `docs/QUALITY_REFERENCE.md`
4. `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_IN-PROCESS.md`
