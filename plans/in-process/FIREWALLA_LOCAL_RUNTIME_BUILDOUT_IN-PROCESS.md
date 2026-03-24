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

Still open and driving the next implementation slice:

- complete write-path confirmation for the remaining local v1 mutation families
- duration parsing and `resumeTs` payload generation for time-bounded actions
- real mutation services, including `pause_rule`
- platinum-alignment cleanup for translation posture, exception translations, and quality-scale truthfulness
- final test-matrix expansion around mutation behavior, entity registry stability, and service surfaces

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
- [ ] Define the duration parsing contract for time-bounded rule actions:
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
- [ ] Define the entity and service contract for rule control:
 - [x] Define the entity and service contract for the first rule-backed switch slice:
  - entities are strictly binary switch entities for on or off behavior
  - the first implemented switches toggle existing live rules in place rather than recreating them
  - switch identity is anchored to the license-backed config entry plus immutable source rule ID
  - Home Assistant owns the final entity ID; the integration supplies UID-based default naming rather than generated human names
  - switch attributes expose the primary backing `rule_id` and matching-rule metadata for future service targeting
- [ ] Define the remaining service contract for rule control:
  - entities are strictly binary switch entities for on or off behavior
  - switch entities are rule-backed, not group-backed
  - groups, users, and networks act as rule scope or applicability metadata, not as switch entities on their own
  - time-bounded pause actions are not native entity controls
  - time-bounded pause actions are exposed exclusively through a custom Home Assistant service such as `firewalla_local.pause_rule`
  - the custom service accepts the rule target and a duration string, then resolves that duration into the `resumeTs` payload field
- [x] Define and implement the first entity plan, including which rule-backed switch entities are created, how unique IDs are derived, and how all entities attach to the license-anchored device entry.
- [ ] Define the follow-on entity plan for broader rule-family coverage and how the switch surface coordinates with the time-bounded pause service.
- [x] Define the diagnostics plan, including which config entry fields and runtime payloads are exposed and how Home Assistant redaction helpers are applied.

Phase 3 execution note: The current implementation now provisions real local credentials during config flow, validates the local runtime before creating the entry, supports reauth with a fresh QR payload, supports host reconfigure, and ships an options flow that persists selected rule IDs and rule templates from the live coordinator snapshot. The coordinator populates typed `FirewallaRuntimeSnapshot` data containing normalized `system_info`, `policy_rules`, and `exception_rule_count`, and it now logs local-runtime outages once and recovery once when polling succeeds again. Runtime inventory reporting is available both as structured data and markdown through the `get_runtime_inventory` response service. The first rule-backed switch platform is implemented and validated, including license-anchored identity, UID-based default naming, availability handling when backing rules disappear, update-in-place toggles, and pause or notes metadata. The remaining Phase 3 work is service-layer mutation beyond plain enable or disable, broader rule-family coverage, and translation or quality-scale alignment for the implemented entity model.

### Phase 4: Validation and implementation handoff

Goal: Produce the implementation-ready validation plan and builder handoff so runtime work can proceed without reopening the architecture decisions.

Gate note: Phase 4 must optimize for fast iteration. Pure `api/` unit tests should validate protocol rules cheaply before slower Home Assistant integration tests become the main feedback loop.

- [ ] Define the initial test matrix for:
  - pure `api/` pairing and signing behavior
  - successful setup and pairing
  - repeated `401` to reauth behavior
  - reconfigure behavior for mutable connection data
  - options flow persistence
  - entity availability and recovery behavior
  - diagnostics redaction
  - device and entity registry stability
- [x] Define the minimum code-quality gates for the first implementation pass:
  - `python -m ruff check .`
  - `python -m ruff format .`
  - `python -m mypy custom_components/firewalla_local`
  - `python -m pytest tests/ -v`
- [ ] Define the builder handoff scope file-by-file so implementation begins from a concrete task breakdown instead of a broad feature brief.
- [ ] Include the custom service implementation surface in the builder handoff, including `services.yaml`, service schema, duration parsing, and service tests.
- [ ] Record any remaining protocol unknowns as explicit implementation risks, not as hidden assumptions.
- [ ] Split the validation plan into a fast lane for pure `api/` unit tests and a slower lane for Home Assistant integration tests.

Phase 4 execution note: Focused validation is now in place for the implemented runtime slices. Recent work has passed Ruff, MyPy, and targeted pytest coverage for client normalization, config flow, setup and service behavior, and runtime inventory reporting. The remaining handoff work is centered on the first write-path slice: mutation payload confirmation, duration parsing, service schema finalization, and entity platform scope.
Phase 4 execution note: Focused validation is now in place for the implemented runtime slices. Recent work has passed Ruff, MyPy, and targeted pytest coverage for client normalization, config flow, setup and service behavior, runtime inventory reporting, and the first switch platform. The remaining handoff work is centered on the next write-path slice: mutation payload confirmation for additional rule families, duration parsing, service schema finalization, broader entity coverage, and reconciling the quality-scale file with the repo's actual platinum target and current implementation state.

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
- `AGENTS.md`
- `README.md`
- `custom_components/firewalla_local/manifest.json`
- `custom_components/firewalla_local/config_flow.py`
- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/api/`
- `custom_components/firewalla_local/quality_scale.yaml`
- `tests/conftest.py`
- `tests/components/firewalla_local/`