# Initiative Plan: Firewalla Local runtime buildout

## Initiative snapshot

- Initiative: Firewalla Local runtime buildout
- Status: In process
- Owner: Firewalla Strategist
- Primary outcome: Define the executable implementation plan that turns the documented Firewalla Local architecture into the first real runtime integration under the `firewalla_local` package layout.
- Why now: The foundation docs are complete, and implementation should now follow a concrete runtime plan instead of growing from the legacy scaffold ad hoc.

## Current execution state

Implemented and verified in the repository:

- clean domain and package cutover to `firewalla_local`
- pure local API boundary under `custom_components/firewalla_local/api/`
- cloud bootstrap plus local runtime proof carried into the real integration codepath
- config flow pairing against the live protocol, including local runtime validation before entry creation
- reauthentication with fresh QR input and reconfigure support for host updates
- options flow for persisted rule selection using readable normalized rule labels
- coordinator-backed typed runtime snapshots with normalized system and policy-rule state
- log-once unavailability and recovery behavior in the coordinator
- runtime inventory reporting and a response-returning Home Assistant service for live inspection
- typed timing fields on normalized policy rules, including temporary-rule derivation based on current evidence
- first rule-backed switch platform wired into config entry setup
- persisted rule-template matching so selected switches survive live rule-ID churn and missing-rule cleanup
- update-in-place rule toggling for the first supported switchable rule families
- switch attributes for rule ID, match count, pause state, pause duration, and notes
- license-anchored switch and device identity with UID-based default naming rather than generated entity names
- focused tests covering client normalization, config flow behavior, runtime service behavior, and inventory reporting
- focused tests covering switch setup, availability, toggle behavior, and pause metadata

Phase 3b status:

- Phase 3b is complete in the repository and has now passed the full repo validation gates: `python -m ruff check .`, `python -m mypy custom_components/firewalla_local`, and `python -m pytest tests/ -v`

Still open and driving the next implementation slice:

- define the explicit Phase 4 validation matrix as fast-lane pure API coverage plus slower Home Assistant integration coverage
- write the remaining builder handoff scope file-by-file for the next mutation and platform slices so implementation work starts from a concrete backlog
- record the remaining local mutation protocol unknowns for additional rule families as explicit risks instead of implicit assumptions
- add the planned quality-scale closure matrix that ties each rule to concrete evidence, exemptions, or blockers
- expand the validation matrix around broader mutation behavior, entity registry stability, and future service and platform surfaces

## Critical execution note

This initiative assumes a pristine buildout path.

Rules:

- do not carry forward compatibility code, wrapper modules, or legacy fallback behavior unless a concrete implementation blocker forces an exception
- do not preserve old package names, duplicate imports, or dual-domain runtime paths for convenience
- do not introduce fallback identity, storage, transport, or crypto strategies
- treat the existing `firewalla` scaffold as source material to replace cleanly, not baggage to preserve

## Scope and non-goals

### In scope

- Plan the migration from the current `firewalla` scaffold to the target `firewalla_local` package layout.
- Plan the pure `custom_components/firewalla_local/api/` submodule structure.
- Plan initial pairing, key generation, signed REST transport, options flow, and reauthentication behavior.
- Plan the first coordinator-backed rule entity architecture, including both direct on or off controls and time-bounded disable actions where the protocol supports them.
- Plan the first implementation-stage test strategy for setup, auth failure, diagnostics, and registry stability.

### Non-goals

- Implement the runtime code.
- Add speculative cloud or MSP fallback behavior.
- Expand the MVP beyond the documented local-only scope.
- Redesign the already accepted architecture and development standards unless implementation evidence forces a change.

## Open questions or external dependencies

1. Which local rule endpoints and payload shapes are the first-class MVP contract for polling and mutation?
2. Which rule types should be exposed first as Home Assistant entities, and which support both binary enablement and time-bounded disable behavior in the MVP?
3. What exact config flow UX should collect QR JSON, validate pairing, and persist connection material without exposing secrets?
4. Which fields belong in `ConfigEntry.data` versus `ConfigEntry.options` at first implementation?
5. What implementation evidence, if any, would justify an exception to the accepted three-tier storage contract?

## Phase summary table

| Phase | Focus | Deliverable | Notes |
| --- | --- | --- | --- |
| 1 | Package migration and module map | Runtime file map and migration plan | Aligns the codebase with `firewalla_local` and the pure `api/` boundary |
| 2 | Pairing, transport, and auth plan | API-layer execution plan | Covers crypto, local pairing, signing, HTTP transport, and reauth handoff |
| 3 | Home Assistant runtime plan | Flow, coordinator, entity, and diagnostics plan | Defines how the HA layer consumes the API boundary |
| 3b | Platinum hygiene and orchestration hardening | Domain-manager and lifecycle plan | Closes the architecture gap between raw protocol transport and HA entities |
| 4 | Validation and implementation handoff | Test plan and builder-ready scope | Makes the runtime plan executable for implementation |

## Per-phase details with checkboxes

### Phase 1: Package migration and module map

Goal: Define the concrete target runtime file layout and how the repo moves from the current scaffold to the accepted `firewalla_local` architecture.

Gate note: Phase 1 must produce a clean cutover plan. No compatibility wrappers or dual-runtime package paths should survive this gate unless they are explicitly justified as short-lived implementation scaffolding with a removal step.

- [x] Map the current scaffold files under `custom_components/firewalla/` to their target locations under `custom_components/firewalla_local/`.
- [x] Define the initial `api/` submodule layout, including at minimum:
  - `api/client.py`
  - `api/auth.py`
  - `api/crypto.py`
  - `api/exceptions.py`
  - `api/models.py` if protocol-only structures justify it
- [x] Add `custom_components/firewalla_local/services.yaml` to the required file map so Home Assistant can expose custom services for timed rule actions.
- [x] Decide the package migration strategy as a clean rename and replacement plan, not a compatibility-wrapper plan.
- [x] Define the migration impact on tests under `tests/components/firewalla/` and the target test package layout for `firewalla_local`.
- [x] Record manifest and translation path impacts of the domain migration so builder work starts from the full rename surface.
- [x] Define deletion criteria for every legacy `firewalla` path so the builder can remove old scaffold files decisively during implementation.

Phase 1 note: Executed by renaming the scaffold and test package to `firewalla_local`, updating workspace and repo references, creating the initial `api/` submodule skeleton, adding `services.yaml`, and leaving no runtime compatibility layer behind. Validation completed with `ruff check`, `ruff format`, `mypy custom_components/firewalla_local`, and `pytest tests/ -v`.

### Phase 2: Pairing, transport, and auth plan

Goal: Define the implementation sequence and module responsibilities for local pairing, key generation, signed REST transport, and reauthentication.

Gate note: Phase 2 must prove the protocol path in the pure `api/` boundary first. Home Assistant orchestration should not be used to compensate for unclear protocol behavior.

Support note: See `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE2_PAIRING_SEQUENCE.md` for the pairing sequence, async or executor boundaries, and explicit protocol assumptions.

- [x] Define the pairing sequence from QR JSON input through local credential establishment, including which steps run in async code versus the executor.
- [x] Define the `cryptography` usage boundaries for RSA generation, PKCS#8 private PEM serialization, and SPKI public PEM serialization.
- [x] Define the request-signing and HTTP client responsibilities inside `api/client.py` and related modules.
- [x] Define the duration parsing contract for time-bounded rule actions:
  - accept user-facing duration strings such as `30m`, `4h`, or `2d 4h 30m`
  - parse the duration string into a total offset from the current system time
  - convert the result into the exact `resumeTs` Unix epoch integer required by the Firewalla payload
  - place the parser either in a pure utility module or within the `api/` boundary, not in Home Assistant orchestration code
- [x] Define the one-retry auth contract in executable terms:
  - first `401` triggers one immediate retry
  - second `401` raises `FirewallaAuthError`
  - Home Assistant layer converts that to `ConfigEntryAuthFailed`
- [x] Define the API exception taxonomy so transport, auth, validation, and protocol failures are distinct and typed.
- [x] Define a fast protocol-first validation harness for the pure `api/` layer so pairing, signing, and auth behavior can be proven before Home Assistant flow and coordinator work begins.

Phase 2 execution note: The repository now has a working protocol-first implementation and proof path. The cloud bootstrap and local `8833` runtime flow were validated against a physical box, then carried into `config_flow.py`, `api/auth.py`, and `api/client.py`. The repo also includes `auth_smoke.py` as a bounded live validation harness built on the real integration modules. The remaining Phase 2 blocker is not pairing or auth; it is the still-unverified local mutation message contract for creating, updating, pausing, and expiring rules.

### Phase 3: Home Assistant runtime plan

Goal: Define how Home Assistant flows, runtime data, coordinator state, diagnostics, and entities use the API layer without violating the architecture contract.

Gate note: Phase 3 must preserve the accepted Home Assistant contracts for device identity, no-floating-entities behavior, no-cache restart behavior, and reauthentication. The HA layer is orchestration only, not a fallback mechanism for protocol uncertainty.

- [x] Define the config flow plan for QR ingestion, connection testing, identity assignment from `license`, and config entry creation.
- [x] Define the reconfigure flow plan so mutable connection details such as host or IP can be updated without re-pairing or identity churn.
  - updating `ConfigEntry.data["ipaddress"]` must not automatically regenerate keys or trigger re-pairing unless the box actively rejects the existing credentials
- [x] Define the options flow plan for mutable user preferences, including selected rule UUIDs, timed-control preferences if needed, and future feature toggles.
- [x] Define the `runtime_data` shape created during `async_setup_entry`, including the API client and coordinator objects.
- [x] Define the coordinator data contract for normalized rule data, polling cadence, availability transitions, log-once unavailable behavior, recovery behavior, and no-cache restart behavior.
- [x] Define the entity contract for the first rule-backed switch slice:
  - entities are strictly binary switch entities for on or off behavior
  - the first implemented switches toggle existing live rules in place rather than recreating them
  - switch identity is anchored to the license-backed config entry plus immutable source rule ID
  - Home Assistant owns the final entity ID; the integration supplies UID-based default naming rather than generated human names
  - switch attributes expose the primary backing `rule_id` and matching-rule metadata for future service targeting
- [x] Define the remaining entity and service contract for rule control:
  - switch entities are rule-backed, not group-backed
  - groups, users, and networks act as rule scope or applicability metadata, not as switch entities on their own
  - time-bounded pause actions are not native entity controls
  - time-bounded pause actions are exposed exclusively through a custom Home Assistant service such as `firewalla_local.pause_rule`
  - the custom service accepts the rule target and a duration string, then resolves that duration into the `resumeTs` payload field
- [x] Define and implement the first entity plan, including which rule-backed switch entities are created, how unique IDs are derived, and how all entities attach to the license-anchored device entry.
- [x] Define the follow-on entity plan for broader rule-family coverage and how the switch surface coordinates with the time-bounded pause service.
  - re-homed into Phase 4 builder handoff planning so the next coverage slice is executed as a file-scoped implementation backlog rather than as a lingering architecture question
- [x] Define the diagnostics plan, including which config entry fields and runtime payloads are exposed and how Home Assistant redaction helpers are applied.

Phase 3 execution note: The current implementation now provisions real local credentials during config flow, validates the local runtime before creating the entry, supports reauth with a fresh QR payload, supports host reconfigure, and ships an options flow that persists selected rule IDs and rule templates from the live coordinator snapshot. The coordinator populates typed `FirewallaRuntimeSnapshot` data containing normalized `system_info`, `policy_rules`, and `exception_rule_count`, and it now logs local-runtime outages once and recovery once when polling succeeds again. Runtime inventory reporting is available both as structured data and markdown through the `get_runtime_inventory` response service. The first rule-backed switch platform is implemented and validated, including license-anchored identity, UID-based default naming, availability handling when backing rules disappear, update-in-place toggles, and pause or notes metadata. The remaining Phase 3 work is service-layer mutation beyond plain enable or disable, broader rule-family coverage, and translation or quality-scale alignment for the implemented entity model.

### Phase 3b: Platinum hygiene and orchestration hardening

Goal: Add the missing middle-management layer and lifecycle discipline required to make the integration production-grade, scalable across more platforms, and honestly alignable to Platinum expectations.

Gate note: Phase 3b is the required pause-and-harden phase. No additional platform expansion should bypass this gate by adding more entity-specific logic directly into platform files.

- [x] Phase 3b prerequisite: Refine the durable architecture and development standards first
  - harvest portable best practices from `ChoreOps` reference materials before revising local docs:
    - `docs/QUALITY_REFERENCE.md`
    - `docs/ARCHITECTURE.md`
    - `docs/DEVELOPMENT_STANDARDS.md`
  - use `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE3B_STANDARDS_HARVEST.md` to separate portable patterns from ChoreOps-specific complexity that should not be copied into this simpler repository
  - update `docs/ARCHITECTURE.md` so the domain-manager layer, registry pipeline, lifecycle reconciliation, service orchestration, UID-first naming contract, and optimistic-update boundaries are explicit architectural rules rather than one-off implementation notes
  - update `docs/DEVELOPMENT_STANDARDS.md` so the manager, coordinator, entity, service, translation, typing, and error-mapping expectations are defined as build rules for all future work, not just this switch initiative
  - create a compact Firewalla-specific quality reference document after the architecture and standards refresh so repository-specific Platinum expectations, quality contracts, and evidence locations live in a durable review surface rather than only in `quality_scale.yaml` or plan prose
  - record any changed quality-scale interpretation or repository-specific Platinum expectations in a durable form before implementation resumes
  - treat the refreshed docs as the reference baseline for all remaining Phase 3b and Phase 4 tasks so future contributors can build against stable rules instead of plan prose alone
  - re-evaluate the remaining Phase 3b workstreams immediately after the documentation refresh and adjust scope where the new durable standards reveal missing lifecycle, typing, service, review, or quality-reference work

- [x] Workstream A: Establish the minimum manager architecture
  - add `custom_components/firewalla_local/managers/` with at minimum:
    - `base_manager.py`
    - `system_manager.py`
    - `rule_manager.py`
  - add `custom_components/firewalla_local/entity.py` as a required shared base entity module before the first sensor platform expansion so common availability, typed coordinator and manager access, shared `DeviceInfo`, and shared metadata behavior do not fragment across platforms
  - store manager instances in `entry.runtime_data` alongside the API client and coordinator
  - make `SystemManager` the owner of shared entry-scoped orchestration such as device lifecycle, entity lifecycle, startup coordination, and reload-time reconciliation routing that should not live in the coordinator
  - make `RuleManager` the owner of rule-template matching, rule resolution, indexed registry lookups, rule-command orchestration, and read-model generation for rule-backed surfaces
  - move `_load_selected_templates` and similar configuration-derived business logic out of `switch.py` into the owning manager layer
  - ensure entities consume manager-owned resolved objects instead of re-implementing matching and filtering logic in platform files

- [x] Workstream B: Clarify coordinator routing and config-entry ownership
  - keep the coordinator as the router between `api/` and the manager layer, not a business-logic owner
  - make coordinator-owned config-entry writes explicit in implementation paths so `ConfigEntry.data` and `ConfigEntry.options` updates do not leak into managers, helpers, services, or platform files
  - formalize the `update_listener` and reload-routing contract so options changes trigger runtime reconciliation through the proper entry-scoped path
  - keep availability transitions, refresh cadence, and refresh-input handoff in the coordinator while moving rule-domain decisions out of it

- [x] Workstream C: Centralize lifecycle reconciliation and multi-instance identity
  - define a shared entity lifecycle policy owned by `SystemManager` for add, update, remove, orphan handling, and startup safety-net cleanup
  - define cleanup behavior for missing backing rules so entities do not remain indefinitely orphaned without a deliberate policy
  - define the base entity contract in `entity.py`, including shared `DeviceInfo`, common availability behavior, typed coordinator and manager access, purpose metadata conventions, and cleanup assumptions used across platforms
  - update entity unique-ID rules in implementation to include the integration instance identifier, the immutable object identifier, and a stable suffix
  - preserve license-anchored device identity while using entry-scoped entity unique IDs for future multi-instance isolation and deterministic cleanup
  - ensure no service, manager, helper, or cleanup path relies on first-loaded-entry behavior

- [x] Workstream D: Move normalization to a manager-owned registry pipeline
  - define a manager-owned registry object that consumes the raw init payload once and indexes rules, networks, tags, devices, and lookups by stable keys
  - eliminate repeated parsing and repeated full-list scans by platform code and reporting helpers where the same data is being normalized multiple times
  - define the target runtime shape for efficient lookup, including `rule_index` keyed by rule ID and resolved applicability metadata precomputed once per poll
  - relocate `runtime_inventory.py` out of the integration root into the owning manager or a clearly named helper module so inventory reporting has explicit ownership
  - ensure runtime inventory and future platforms consume shared normalized outputs instead of separately picking through the raw payload
  - evaluate whether large init-payload lookups should be eagerly normalized once per poll, lazily resolved, or cached behind payload-version or timestamp checks so polling does not rebuild every name map unnecessarily
  - define stale-template tolerance rules so persisted `FirewallaRuleTemplate` data remains forward-compatible when optional Firewalla fields evolve

- [x] Workstream E: Enforce mutation, service, translation, and boundary rules
  - define the manager contract for applying successful enable, disable, and future pause mutations to in-memory rule state immediately
  - preserve the coordinator poll as the later source of truth while avoiding an immediate full refresh solely to flip one bit in the UI
  - define rollback or recovery behavior when a command succeeds locally but later polling disagrees
  - introduce a dedicated `services.py` layer that maps Home Assistant service calls to manager methods rather than growing `__init__.py` into a service dispatcher
  - define `pause_rule` and future action services so they can target managed rules even when no switch entity exists for that rule
  - replace hardcoded user-facing operational strings with translation-ready exception, repair, and service messaging where appropriate
  - define specific user-facing exception mapping in `config_flow.py` so auth, cloud bootstrap, QR validation, and local-box rejection failures each land on distinct translation keys rather than a single generic API failure bucket
  - move platform icon decisions out of Python where the Home Assistant translation or icon system supports it, and track the exact deliverable needed to satisfy the quality-scale icon-translation expectation truthfully
  - tighten internal typing in the API and manager layers so unstructured `dict[str, object]` payloads shrink behind `TypedDict` or model boundaries where protocol shape is now stable enough to encode
  - require the first multi-platform buildout to declare explicit `PARALLEL_UPDATES` policy in platform modules and to consume shared `entity.py` behavior instead of duplicating availability or metadata patterns
  - add boundary-enforcement validation for purity rules, coordinator-owned config-entry writes, manager-owned mutation paths, and unowned specialized root modules
  - review the quality scale file item by item and convert scaffold-era comments or exemptions into truthful `done`, `todo`, or `exempt` states with implementation-backed rationale

- [x] Cross-cutting architecture decision: Preserve UID-first entity naming unless deliberately re-opened
  - maintain the current contract that the integration must not generate descriptive entity names from mutable rule text solely to satisfy default UI polish
  - keep unique IDs and default object IDs anchored to immutable identifiers while allowing user renames through normal Home Assistant registry behavior
  - include entry scope and a stable suffix in entity unique IDs so future multi-instance cleanup remains deterministic
  - if a later design wants human-readable defaults again, require an explicit architecture decision because it conflicts with the current UID-first rule already accepted for this repository

Phase 3b execution note: This phase now has working code behind the accepted contracts. The repository has a minimum `SystemManager` plus `RuleManager` architecture stored in `entry.runtime_data`, a shared `entity.py` base, coordinator-owned reload and config-entry migration paths, entry-scoped unique IDs, manager-owned optimistic rule mutation, a dedicated `services.py` layer with `pause_rule`, duration parsing under `utils/`, owned runtime inventory helpers under `helpers/`, boundary-enforcement tests, and a trued-up `quality_scale.yaml`. The current switch platform now consumes manager-owned rule views instead of directly owning matching and mutation logic, which means future platforms can build on the same manager and entity foundation rather than duplicating orchestration at the entity edge.

### Phase 4: Validation and implementation handoff

Goal: Produce the implementation-ready validation plan and builder handoff so runtime work can proceed without reopening the architecture decisions.

Gate note: Phase 4 must optimize for fast iteration. Pure `api/` unit tests should validate protocol rules cheaply before slower Home Assistant integration tests become the main feedback loop.

- [x] Phase 4A: Validation lanes and initial test matrix
  - define the fast-lane validation matrix for pure `api/` and utility behavior, including owning test modules and current coverage state
  - define the slow-lane validation matrix for Home Assistant integration behavior, including setup, reauth, reconfigure, services, entity availability, diagnostics redaction, and registry stability
  - record current coverage as `present`, `partial`, or `missing` so the next builder slice adds tests to named files instead of broad areas
  - completed in `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE4_VALIDATION_AND_HANDOFF.md`, including executable lane commands for the current repo test layout
- [x] Phase 4B: Builder handoff by file surface
  - convert the next runtime slice into ordered work packages for mutation proof, service hardening, and switch-first follow-on coverage
  - assign touch-first files, verify-only files, test owners, and explicit stop conditions for each package
  - completed in `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE4_VALIDATION_AND_HANDOFF.md` as a concrete file-scoped execution map grounded in the current `api/client.py`, `services.py`, `switch.py`, and `managers/rule_manager.py` surfaces
  - execution started and validated with direct manager mutation tests in `tests/components/firewalla_local/test_rule_manager.py` and additional service-resolution coverage in `tests/components/firewalla_local/test_services.py`
- [x] Define the minimum code-quality gates for the first implementation pass:
  - `python -m ruff check .`
  - `python -m ruff format .`
  - `python -m mypy custom_components/firewalla_local`
  - `python -m pytest tests/ -v`
- [x] Phase 4C: Remaining protocol unknowns and implementation risks
  - separate confirmed mutation contracts from unconfirmed rule-family behavior so Builder does not generalize from the currently proven slice
  - record explicit stop conditions for additional mutation families, pause or resume semantics, create or update payload variance, and rule-template stability under broader coverage
  - completed in `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE4_VALIDATION_AND_HANDOFF.md` as a concrete risk register tied to the current `api/client.py`, `services.py`, `models.py`, `switch.py`, and `managers/rule_manager.py` surfaces, including explicit allowed assumptions, prohibited assumptions, proof requirements, and stop/go decision rules
- [x] Phase 4D: Quality-scale closure matrix and exit criteria
  - map relevant quality-scale rules to concrete evidence, explicit blockers, or deliberate defer decisions
  - distinguish runtime-slice blockers from later documentation or release-prep work so Phase 4 can close honestly
  - define exit criteria for Phase 4 completion in terms that are testable and reviewable
  - completed in `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE4_VALIDATION_AND_HANDOFF.md` with a trued-up closure matrix tied to `quality_scale.yaml`, the current implementation surfaces, and explicit defer reasons for release-prep items

Phase 4 execution note: Phase 4 planning and handoff are now complete. The repository has a documented fast-lane versus slow-lane validation matrix, a file-scoped builder handoff, a concrete protocol risk register with stop/go rules, and a quality-scale closure matrix tied to current evidence and explicit defers. Remaining open items in `quality_scale.yaml` are now clearly separated into runtime blockers versus release-prep or future-protocol work rather than being mixed into architecture planning. Detailed execution scaffolding for that work lives in `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE4_VALIDATION_AND_HANDOFF.md`.

## Validation strategy

Document-only updates to plans and support notes do not require repo lint, type-check, or test runs.

- The plan must stay consistent with `docs/ARCHITECTURE.md` and `docs/DEVELOPMENT_STANDARDS.md`.
- The plan must preserve the accepted contracts for:
  - `license` as immutable device identity
  - `gid` as connection-only parameter
  - pure `api/` submodule boundary
  - mandatory `cryptography` dependency
  - one-retry `401` auth handling
  - no custom storage cache for Firewalla state
- The plan must enforce the no-compatibility, no-legacy-baggage execution rule unless an exception is explicitly justified and time-bounded.
- The plan must not introduce speculative cloud fallback behavior.
- The plan should prefer a clean rename and replacement path over wrapper-based migration.
- The plan must identify unresolved protocol items explicitly before implementation starts.

## References

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE4_VALIDATION_AND_HANDOFF.md`
- `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE3B_STANDARDS_HARVEST.md`
- `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE3B_BUILDER_HANDOFF.md`
- `AGENTS.md`
- `README.md`
- `custom_components/firewalla_local/manifest.json`
- `custom_components/firewalla_local/config_flow.py`
- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/api/`
- `custom_components/firewalla_local/quality_scale.yaml`
- `tests/conftest.py`
- `tests/components/firewalla_local/`
- `https://github.com/ccpk1/ChoreOps/blob/main/docs/QUALITY_REFERENCE.md`
- `https://github.com/ccpk1/ChoreOps/blob/main/docs/ARCHITECTURE.md`
- `https://github.com/ccpk1/ChoreOps/blob/main/docs/DEVELOPMENT_STANDARDS.md`