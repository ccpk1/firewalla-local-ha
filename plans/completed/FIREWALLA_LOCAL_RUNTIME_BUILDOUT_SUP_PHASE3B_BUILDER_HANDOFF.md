# Builder handoff: Phase 3b platinum hygiene and orchestration hardening

## Purpose

Provide an implementation-ready handoff for all of Phase 3b.

This handoff is intentionally specific. It exists to remove ambiguity for Firewalla Builder, prevent accidental architecture drift, and define completion in a way that can be verified instead of inferred.

## Scope

This handoff covers all of Phase 3b in the active runtime buildout plan:

- minimum manager architecture
- coordinator routing and config-entry ownership
- shared entity base and lifecycle reconciliation
- manager-owned registry pipeline
- runtime inventory ownership cleanup
- optimistic updates
- services, translation, and exception mapping
- boundary enforcement and quality-scale alignment

This handoff does not authorize architecture redesign beyond the already accepted repository documents.

## Source of truth

Builder must follow these documents in this order:

1. `docs/ARCHITECTURE.md`
2. `docs/DEVELOPMENT_STANDARDS.md`
3. `docs/QUALITY_REFERENCE.md`
4. `plans/completed/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_COMPLETE.md`
5. this handoff file

If this handoff appears to conflict with the architecture or standards docs, the docs win.

## Non-negotiable guardrails

### No redesign without permission

Builder must not:

- move config-entry writes out of the coordinator
- remove or weaken the minimum `IntegrationManager`, `HostManager`, and `RuleManager` architecture
- move business logic back into entities, services, platform files, or helpers
- change UID-first naming into generated human-readable defaults
- remove entry-scoped unique-ID requirements
- reintroduce unowned specialized root modules such as a root-level runtime inventory module
- introduce compatibility wrappers, duplicate runtime paths, or convenience fallback identity rules
- invent cross-manager write paths or implicit multi-entry behavior

If implementation reveals a real conflict with these decisions, stop and request direction instead of redesigning on the fly.

### Completion means full Phase 3b completion

Builder must not treat partial architectural movement as completion.

Phase 3b is complete only when:

- all accepted ownership moves are implemented
- duplicated rule-resolution logic has been removed from the entity edge
- config-entry write ownership is enforced in code paths
- runtime inventory ownership is explicit and root drift is removed
- entity lifecycle and unique-ID behavior are consistent with the docs
- boundary enforcement checks exist and are run
- the quality-scale file reflects the actual repository state honestly

## Required implementation order

Builder should execute Phase 3b in this order:

1. Manager and entity foundation
2. Coordinator routing and config-entry ownership cleanup
3. Lifecycle reconciliation and multi-instance identity cleanup
4. Registry pipeline and runtime inventory ownership move
5. Mutation, services, translation, and boundary enforcement
6. Quality-scale truthing and final validation

Do not start broader platform expansion before steps 1 through 5 are complete.

## Work package A: Minimum manager and shared entity foundation

### Required file outcomes

Create or update:

- `custom_components/firewalla_local/managers/__init__.py`
- `custom_components/firewalla_local/managers/base_manager.py`
- `custom_components/firewalla_local/managers/integration_manager.py`
- `custom_components/firewalla_local/managers/host_manager.py`
- `custom_components/firewalla_local/managers/rule_manager.py`
- `custom_components/firewalla_local/entity.py`
- `custom_components/firewalla_local/__init__.py`
- `custom_components/firewalla_local/coordinator.py`
- any platform files currently holding manager-owned logic

### Checklist

- [ ] add `managers/` package
- [ ] add `BaseManager` with the minimum shared runtime contract needed by `IntegrationManager`, `HostManager`, and `RuleManager`
- [ ] instantiate `IntegrationManager`, `HostManager`, and `RuleManager` during setup and place them in `entry.runtime_data`
- [ ] create `entity.py` as the shared base entity module
- [ ] move common availability handling, typed coordinator access, typed manager access, shared `DeviceInfo`, and common metadata behavior into `entity.py`
- [ ] remove duplicated matching or orchestration logic from `switch.py` and any other platform files touched in this phase

### Guardrails

- `entity.py` is a shared entity module only, not a manager or helper surrogate
- `BaseManager` must not become a storage layer or protocol layer
- `IntegrationManager`, `HostManager`, and `RuleManager` must have clear boundaries; do not blur them into one generic catch-all manager

### Done criteria

- manager objects exist in runtime data
- `entity.py` exists and is used by the existing switch platform where appropriate
- platform files no longer own logic that the docs assign to managers

## Work package B: Coordinator routing and config-entry ownership cleanup

### Required file outcomes

Create or update:

- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/__init__.py`
- `custom_components/firewalla_local/config_flow.py`
- any service or helper modules that currently mutate config-entry data directly

### Checklist

- [ ] ensure coordinator remains the router between `api/` and manager-owned orchestration
- [ ] move or keep all config-entry writes in coordinator-owned paths only
- [ ] make update-listener and reload-routing behavior explicit and entry-scoped
- [ ] confirm managers, helpers, services, and platform files do not write config-entry data or options directly

### Guardrails

- do not move config-entry writes into managers for convenience
- do not let helpers become a back door for config-entry mutation

### Done criteria

- config-entry writes are coordinator-owned in code and easy to audit
- options updates route through the documented listener and reload path

## Work package C: Lifecycle reconciliation and multi-instance identity

### Required file outcomes

Create or update:

- `custom_components/firewalla_local/managers/integration_manager.py`
- `custom_components/firewalla_local/entity.py`
- relevant platform files such as `switch.py`
- helper modules only if needed for read-only registry or entity-registry glue
- tests covering cleanup and unique-ID behavior

### Checklist

- [ ] define and implement one shared lifecycle reconciliation policy for add, update, remove, orphan handling, and startup safety-net cleanup
- [ ] implement missing-backing-rule handling according to an explicit policy
- [ ] update entity unique IDs to include entry scope, immutable object identifier, and stable suffix
- [ ] preserve license-anchored device identity while using entry-scoped entity unique IDs
- [ ] ensure no cleanup path, service path, or helper path relies on first-loaded-entry behavior
- [ ] use `entity.py` to centralize shared lifecycle-related entity behavior where appropriate
- [ ] define and apply purpose-metadata conventions where that improves clarity
- [ ] define and apply explicit `PARALLEL_UPDATES` policy in coordinator-based platforms

### Guardrails

- do not weaken UID-first naming
- do not switch to generated human-readable defaults
- do not use device identity as a substitute for per-entry unique-ID scope

### Done criteria

- unique IDs follow the documented multi-instance-safe structure
- cleanup logic is explicit and tested
- shared entity behavior is not duplicated unnecessarily across platforms

## Work package D: Manager-owned registry pipeline and runtime inventory ownership

### Required file outcomes

Create or update:

- `custom_components/firewalla_local/managers/rule_manager.py`
- `custom_components/firewalla_local/models.py`
- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/helpers/runtime_inventory.py` or a manager-owned equivalent
- remove or relocate `custom_components/firewalla_local/runtime_inventory.py`
- any consumers of runtime inventory or raw payload scans

### Checklist

- [ ] define a manager-owned registry object or equivalent indexed runtime structure
- [ ] centralize rule, network, tag, device, and scope lookups
- [ ] add shared indexed lookups such as `rule_index`
- [ ] remove repeated full payload scans from platform or reporting code where the shared registry should be used instead
- [ ] relocate runtime inventory reporting into an owned helper or manager module
- [ ] ensure runtime inventory consumes manager-owned data rather than re-parsing raw payloads independently
- [ ] define and implement stale-template tolerance rules
- [ ] evaluate and implement the chosen eager, lazy, or cached lookup strategy without creating a second source of truth

### Guardrails

- runtime inventory must not remain an unowned specialized root module
- registry indexing belongs to `RuleManager`, not to platform files
- caching must not bypass the refresh cycle as the source of truth

### Done criteria

- one shared registry pipeline exists
- runtime inventory ownership is explicit
- repeated ad hoc scans are materially reduced or removed

## Work package E: Mutation, services, translation, and boundary enforcement

### Required file outcomes

Create or update:

- `custom_components/firewalla_local/managers/rule_manager.py`
- `custom_components/firewalla_local/services.py`
- `custom_components/firewalla_local/services.yaml`
- `custom_components/firewalla_local/config_flow.py`
- `custom_components/firewalla_local/translations/en.json`
- `custom_components/firewalla_local/quality_scale.yaml`
- validation tooling for boundary enforcement under `utils/` if needed
- tests for services, errors, and boundary-sensitive behavior

### Checklist

- [ ] implement optimistic manager-side in-memory updates for successful commands
- [ ] define rollback or reconciliation behavior when later polling disagrees
- [ ] add `services.py` as the central Home Assistant service layer
- [ ] implement `pause_rule` and any supporting service schema or duration-handling path required for the current scope
- [ ] ensure services delegate to manager methods instead of constructing payloads independently
- [ ] make config-flow, reauth, and service errors translation-specific by failure class
- [ ] move icon behavior out of Python where the Home Assistant translation or icon system provides the correct durable surface
- [ ] tighten internal typing in API and manager-facing payloads where shapes are stable enough to encode
- [ ] add or update boundary-enforcement checks for:
  - purity boundaries
  - coordinator-owned config-entry writes
  - manager-owned mutation paths
  - unowned specialized root modules
- [ ] update `quality_scale.yaml` so each state is truthful and implementation-backed

### Guardrails

- services must not become a parallel business-logic layer
- translation work must not collapse distinct failures into one generic message
- boundary checks must enforce architecture rather than merely document it

### Done criteria

- service layer is centralized
- optimistic updates exist and are reconciled correctly
- translation mapping is specific
- boundary enforcement exists and is run
- quality-scale truthfulness is restored

## File placement rules for Builder

Use these placement rules without exception unless the user explicitly approves a change:

- protocol-only code: `custom_components/firewalla_local/api/`
- business orchestration and indexed runtime ownership: `custom_components/firewalla_local/managers/`
- shared Home Assistant-aware support code: `custom_components/firewalla_local/helpers/`
- pure helper functions: `custom_components/firewalla_local/utils/`
- shared entity behavior: `custom_components/firewalla_local/entity.py`
- coordinator routing and config-entry writes: `custom_components/firewalla_local/coordinator.py`

If a new file does not clearly belong to one of those categories, stop and ask before introducing it.

## Testing and validation checklist

Builder must run and report at minimum:

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/firewalla_local`
- `python -m pytest tests/ -v`

Focused tests should also be added or updated for:

- manager setup and runtime-data wiring
- coordinator-owned config-entry write paths
- entity unique-ID and cleanup behavior
- missing-rule reconciliation behavior
- manager-owned registry lookups and runtime inventory outputs
- service dispatch and `pause_rule`
- translation-specific failure mapping
- boundary-enforcement checks if they are implemented as executable validation

## Review checklist for Builder before claiming completion

Builder must verify all of the following are true:

- [ ] no business-logic drift remains in entity or service code that the managers should own
- [ ] no config-entry writes remain outside coordinator-owned paths
- [ ] no unowned specialized root modules remain where ownership belongs in `managers/`, `helpers/`, or `utils/`
- [ ] `entity.py` is present and used for shared entity behavior
- [ ] `IntegrationManager`, `HostManager`, and `RuleManager` all exist and have non-overlapping responsibilities
- [ ] unique IDs are entry-scoped and suffix-stable
- [ ] device identity remains license-anchored
- [ ] runtime inventory ownership is explicit and manager-backed
- [ ] platform modules declare explicit `PARALLEL_UPDATES` policy where applicable
- [ ] quality-scale states are honest
- [ ] all required validation commands pass

## Stop conditions

Builder must stop and ask for direction if any of the following become necessary:

- changing UID-first naming into human-readable defaults
- moving config-entry write ownership away from the coordinator
- introducing more than the minimum manager set for reasons that change the accepted architecture rather than clarify it
- keeping a specialized root-level module because there is no agreed owner
- weakening entry-scoped unique-ID or cleanup guarantees
- introducing compatibility layers not already approved in the plan

## Definition of done

Phase 3b is complete only when all work packages in this handoff are complete, validated, and aligned with:

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/QUALITY_REFERENCE.md`
- `plans/completed/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_COMPLETE.md`

Partial architectural progress does not count as completion.

Defined handoff: Firewalla Builder
