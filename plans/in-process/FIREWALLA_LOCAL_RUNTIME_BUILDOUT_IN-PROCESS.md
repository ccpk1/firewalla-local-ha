# Initiative Plan: Firewalla Local runtime buildout

## Initiative snapshot

- Initiative: Firewalla Local runtime buildout
- Status: In process
- Owner: Firewalla Strategist
- Primary outcome: Define the executable implementation plan that turns the documented Firewalla Local architecture into the first real runtime integration under the `firewalla_local` package layout.
- Why now: The foundation docs are complete, and implementation should now follow a concrete runtime plan instead of growing from the legacy scaffold ad hoc.

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

- [ ] Define the pairing sequence from QR JSON input through local credential establishment, including which steps run in async code versus the executor.
- [ ] Define the `cryptography` usage boundaries for RSA generation, PKCS#8 private PEM serialization, and SPKI public PEM serialization.
- [ ] Define the request-signing and HTTP client responsibilities inside `api/client.py` and related modules.
- [ ] Define the duration parsing contract for time-bounded rule actions:
  - accept user-facing duration strings such as `30m`, `4h`, or `2d 4h 30m`
  - parse the duration string into a total offset from the current system time
  - convert the result into the exact `resumeTs` Unix epoch integer required by the Firewalla payload
  - place the parser either in a pure utility module or within the `api/` boundary, not in Home Assistant orchestration code
- [ ] Define the one-retry auth contract in executable terms:
  - first `401` triggers one immediate retry
  - second `401` raises `FirewallaAuthError`
  - Home Assistant layer converts that to `ConfigEntryAuthFailed`
- [ ] Define the API exception taxonomy so transport, auth, validation, and protocol failures are distinct and typed.
- [ ] Define a fast protocol-first validation harness for the pure `api/` layer so pairing, signing, and auth behavior can be proven before Home Assistant flow and coordinator work begins.

### Phase 3: Home Assistant runtime plan

Goal: Define how Home Assistant flows, runtime data, coordinator state, diagnostics, and entities use the API layer without violating the architecture contract.

Gate note: Phase 3 must preserve the accepted Home Assistant contracts for device identity, no-floating-entities behavior, no-cache restart behavior, and reauthentication. The HA layer is orchestration only, not a fallback mechanism for protocol uncertainty.

- [ ] Define the config flow plan for QR ingestion, connection testing, identity assignment from `license`, and config entry creation.
- [ ] Define the reconfigure flow plan so mutable connection details such as host or IP can be updated without re-pairing or identity churn.
  - updating `ConfigEntry.data["ipaddress"]` must not automatically regenerate keys or trigger re-pairing unless the box actively rejects the existing credentials
- [ ] Define the options flow plan for mutable user preferences, including selected rule UUIDs, timed-control preferences if needed, and future feature toggles.
- [ ] Define the `runtime_data` shape created during `async_setup_entry`, including the API client and coordinator objects.
- [ ] Define the coordinator data contract for normalized rule data, polling cadence, availability transitions, log-once unavailable behavior, recovery behavior, and no-cache restart behavior.
- [ ] Define the entity and service contract for rule control:
  - entities are strictly binary switch entities for on or off behavior
  - time-bounded pause actions are not native entity controls
  - time-bounded pause actions are exposed exclusively through a custom Home Assistant service such as `firewalla_local.pause_rule`
  - the custom service accepts the rule target and a duration string, then resolves that duration into the `resumeTs` payload field
- [ ] Define the first entity plan, including which rule-backed switch entities are created, how unique IDs are derived, how all entities attach to the license-anchored device entry, and how the switch surface coordinates with the time-bounded pause service.
- [ ] Define the diagnostics plan, including which config entry fields and runtime payloads are exposed and how Home Assistant redaction helpers are applied.

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
- [ ] Define the minimum code-quality gates for the first implementation pass:
  - `python -m ruff check .`
  - `python -m ruff format .`
  - `python -m mypy custom_components/firewalla_local`
  - `python -m pytest tests/ -v`
- [ ] Define the builder handoff scope file-by-file so implementation begins from a concrete task breakdown instead of a broad feature brief.
- [ ] Include the custom service implementation surface in the builder handoff, including `services.yaml`, service schema, duration parsing, and service tests.
- [ ] Record any remaining protocol unknowns as explicit implementation risks, not as hidden assumptions.
- [ ] Split the validation plan into a fast lane for pure `api/` unit tests and a slower lane for Home Assistant integration tests.

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