# Support note: Phase 4 validation and handoff

## Purpose

Convert Phase 4 from broad closure intent into an execution-ready validation and handoff plan.

This file exists to keep the active initiative plan directional while still giving Firewalla Builder a concrete backlog shape for the next runtime slice.

## Scope

Phase 4 covers:

- validation-lane definition
- test-matrix ownership
- file-by-file builder handoff for the next mutation and service slice
- explicit protocol risks and stop conditions
- quality-scale closure planning
- Phase 4 exit criteria

This file does not reopen the architecture. It applies the already accepted rules from the repository guidance documents to the next execution slice.

## Source of truth and guardrails

Builder must follow these documents in this order:

1. `docs/ARCHITECTURE.md`
2. `docs/DEVELOPMENT_STANDARDS.md`
3. `docs/QUALITY_REFERENCE.md`
4. `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_IN-PROCESS.md`
5. this support file

Guardrails:

- do not reopen Phase 3b architectural decisions during Phase 4 handoff work
- do not infer new platform types from the current switch-first runtime surface
- do not generalize one confirmed mutation family into a blanket contract for all rule families
- do not treat documentation of the handoff as permission to guess missing protocol behavior

## Phase 4A: Validation lanes and initial test matrix

### Goal

Define a named fast lane and slow lane so validation work stays targeted and cheap during iteration.

### Deliverables

- a fast-lane matrix for pure `api/` and utility coverage
- a slow-lane matrix for Home Assistant integration coverage
- a per-behavior ownership map to the test module that should hold or expand coverage
- a gap list marking each area as `present`, `partial`, or `missing`

### Current runnable lane commands

Use these commands as the current repository baseline for Phase 4A.

Fast lane current baseline:

```bash
python -m pytest \
  tests/components/firewalla_local/test_client.py \
  tests/components/firewalla_local/test_models.py \
  tests/components/firewalla_local/test_runtime_inventory.py \
  tests/components/firewalla_local/test_boundaries.py \
  tests/components/firewalla_local/test_auth.py \
  tests/components/firewalla_local/test_diagnostics.py \
  tests/components/firewalla_local/test_rule_manager.py \
  -v
```

Slow lane current baseline:

```bash
python -m pytest \
  tests/components/firewalla_local/test_config_flow.py \
  tests/components/firewalla_local/test_init.py \
  tests/components/firewalla_local/test_services.py \
  tests/components/firewalla_local/test_switch.py \
  -v
```

Full repo gate:

```bash
python -m pytest tests/ -v
```

Lane rule:

- run the fast lane first for protocol, model, helper, and boundary regressions
- run the slow lane when a change touches setup, services, entities, flows, or config-entry lifecycle
- run the full repo gate before marking a builder slice complete

### Fast lane: pure API and utility tests

Use the fast lane for pure runtime logic that should validate cheaply before Home Assistant setup tests run.

| Runtime surface | Target behavior | Current owner | Coverage state | Notes |
| --- | --- | --- | --- | --- |
| `api/client.py` | runtime snapshot normalization | `tests/components/firewalla_local/test_client.py` | present | extend when new mutation families add normalization branches |
| `api/client.py` | create, delete, and update payload shape | `tests/components/firewalla_local/test_client.py` | present | currently strongest evidence for the first supported mutation family |
| `api/client.py` | one-retry `401` auth handling | `tests/components/firewalla_local/test_client.py` | present | keep as fast-lane regression guard |
| `api/auth.py` | QR parsing, cloud login parsing, group extraction, and provisioning polling behavior | `tests/components/firewalla_local/test_auth.py` | present | keep fully mocked and internal-only; do not hit live cloud endpoints in tests |
| `api/models.py` | typed QR and cloud payload coercion | future `tests/components/firewalla_local/test_api_models.py` | missing | add if protocol model surface expands further |
| `models.py` | rule naming, switch eligibility, template serialization | `tests/components/firewalla_local/test_models.py` | present | extend alongside new rule-family eligibility rules |
| `utils/duration.py` | duration parsing and invalid input handling | `tests/components/firewalla_local/test_services.py` or future `test_duration.py` | partial | split into a dedicated utility test file if parsing rules expand |
| `managers/rule_manager.py` | candidate filtering, optimistic mutation updates, target resolution | `tests/components/firewalla_local/test_rule_manager.py` | present | use this as the fast-lane guard for manager-owned mutation behavior |

### Slow lane: Home Assistant integration tests

Use the slow lane for full integration setup, service handling, coordinator behavior, and registry-facing surfaces.

| Runtime surface | Target behavior | Current owner | Coverage state | Notes |
| --- | --- | --- | --- | --- |
| config flow | setup, duplicate prevention, invalid host or QR handling, reauth, options | `tests/components/firewalla_local/test_config_flow.py` | present | expand for any new mutation-selection UX |
| setup and coordinator | setup success, auth failure, unavailability and recovery, host migration | `tests/components/firewalla_local/test_init.py` | present | keep entry lifecycle coverage here |
| services | runtime inventory, pause, resume, validation failures | `tests/components/firewalla_local/test_services.py` and `tests/components/firewalla_local/test_init.py` | present | extend with additional rule-family targets |
| switch platform | availability, optimistic toggles, pause attributes, cleanup on deselect | `tests/components/firewalla_local/test_switch.py` | present | follow-on entity coverage should extend here first |
| diagnostics | redaction behavior and payload shape | `tests/components/firewalla_local/test_diagnostics.py` | present | keep diagnostics coverage fully local and based on synthetic runtime data |
| entity and device registry stability | stable unique IDs, cleanup, device attachment | `tests/components/firewalla_local/test_switch.py` and `tests/components/firewalla_local/test_init.py` | partial | add explicit registry assertions when broader coverage starts |
| boundary enforcement | layer purity and ownership checks | `tests/components/firewalla_local/test_boundaries.py` | present | extend if new manager or helper surfaces are added |
| runtime inventory reporting | report shape and helper ownership | `tests/components/firewalla_local/test_runtime_inventory.py` | present | keep read-only ownership distinct from manager mutation tests |

### Coverage gaps to close next

- add explicit registry-stability assertions when follow-on entity coverage broadens beyond the current switch slice
- add dedicated auth-model coverage for `api/models.py` if the protocol model surface grows beyond the current auth-helper coverage

### Target lane expansion

Add these tests to the fast lane when they exist:

- `tests/components/firewalla_local/test_auth.py`
- `tests/components/firewalla_local/test_api_models.py`
- `tests/components/firewalla_local/test_duration.py`

Add these tests to the slow lane when they exist:

- any future registry-focused integration test module if registry assertions outgrow `test_switch.py` and `test_init.py`

### Completion criteria

- every validation target belongs to either fast lane or slow lane
- every row names an owning test file or a missing target file
- current coverage is labeled explicitly as `present`, `partial`, or `missing`
- diagnostics and registry stability are named rows instead of implied concerns
- the support file provides executable commands for the current repo layout so Builder does not need to infer how to run each lane

## Phase 4B: Builder handoff by file surface

### Goal

Provide a file-by-file backlog for the next runtime slice so Builder works from bounded surfaces instead of a feature paragraph.

### Execution order

Builder should execute Phase 4B in this order:

1. mutation-surface proof
2. service-surface hardening
3. switch-first follow-on coverage

Do not start the later packages first. The current service and switch layers already depend on the manager-owned mutation contract, so the next slice must prove those boundaries in that order.

### Work package 4B-1: Mutation-surface proof

Purpose:

- extend beyond the first supported mutation family only where local protocol evidence exists
- keep mutation semantics manager-owned rather than drifting into platform or service files

Touch-first files and exact role:

- `custom_components/firewalla_local/api/client.py`
  - prove whether additional rule families still use the current `async_update_rule` payload discipline
  - keep family-specific payload branching local to the API boundary if the wire contract diverges
  - treat `async_create_rule`, `async_delete_rule`, and `async_update_rule` as the only supported mutation entry points unless protocol evidence proves otherwise
- `custom_components/firewalla_local/api/models.py`
  - add or tighten typed protocol payload shapes only after the local contract is observed more than once
  - keep unconfirmed fields out of the typed model surface
- `custom_components/firewalla_local/models.py`
  - extend normalized rule-template and rule-eligibility typing only when those fields are stable enough to survive persistence and matching
- `custom_components/firewalla_local/managers/rule_manager.py`
  - keep `async_set_template_enabled`, `async_pause_rule`, `async_resume_rule`, `_resolve_rules_for_target`, and `_apply_optimistic_rule_update` as the owning mutation orchestration surface
  - extend rule-target resolution here if selected-template targets or live-rule targets broaden

Regression and verify-only files:

- `custom_components/firewalla_local/coordinator.py`
  - verify no config-entry writes or family-specific mutation branching drift back into the coordinator
- `custom_components/firewalla_local/entity.py`
  - verify entity behavior still consumes manager-owned rule views instead of calling client mutations directly
- `custom_components/firewalla_local/managers/integration_manager.py`
  - verify no mutation ownership leaks into the integration manager

Expected test ownership:

- extend `tests/components/firewalla_local/test_client.py` for protocol payload shape and retry behavior
- extend `tests/components/firewalla_local/test_rule_manager.py` when mutation behavior grows beyond the current optimistic-update and target-resolution coverage
- keep auth-related mutation setup fully mocked and internal-only

Stop conditions:

- stop if a newly observed rule family cannot be represented honestly by the current `async_update_rule` contract
- stop if optimistic updates require rule-family-specific state that cannot be encoded without lying in the normalized model

### Work package 4B-2: Service-surface hardening

Purpose:

- keep custom services as a thin validation and dispatch layer over manager-owned behavior
- make the next service slice explicit in schemas, translations, and tests rather than hidden in implementation code

Touch-first files and exact role:

- `custom_components/firewalla_local/services.py`
  - keep `_get_loaded_entry` as the only config-entry resolution path for Firewalla services
  - extend `_async_handle_pause_rule` and `_async_handle_resume_rule` only for confirmed target families and confirmed timing semantics
  - keep `get_runtime_inventory` read-only and separate from mutation dispatch
- `custom_components/firewalla_local/services.yaml`
  - update service descriptions only after the capability exists in code
  - keep the user-facing target description aligned with the current rule-target model
- `custom_components/firewalla_local/utils/duration.py`
  - expand parsing only if the service contract adds new supported duration syntax
- `custom_components/firewalla_local/const.py`
  - add constants only for actual new service fields, placeholders, or translation keys
- `custom_components/firewalla_local/translations/en.json`
  - add translation-backed exception or placeholder entries for new service failures instead of hardcoded strings

Regression-test files:

- extend `tests/components/firewalla_local/test_services.py` for entry selection, target validation, timing conflict, indefinite pause, and any broader target-family dispatch
- keep `tests/components/firewalla_local/test_init.py` as the setup and lifecycle guard when service registration or unload behavior changes

Stop conditions:

- stop if a proposed service target cannot be resolved cleanly as either one live rule ID or one selected-template source ID
- stop if a new timing mode cannot be expressed truthfully as duration-based, explicit `resume_at`, or indefinite pause

### Work package 4B-3: Switch-first follow-on coverage

Purpose:

- broaden runtime coverage without prematurely inventing new platform types
- keep the next slice anchored to the persisted-template plus live-match model that already exists

Scope rule:

- keep the next coverage slice switch-first
- treat additional platform types as contingent, not assumed

Touch-first files and exact role:

- `custom_components/firewalla_local/switch.py`
  - extend eligibility or presentation only when the broader rule-family support still behaves like a binary on or off switch
  - keep rule metadata exposure stable and translation-backed
- `custom_components/firewalla_local/managers/rule_manager.py`
  - own expanded candidate filtering, selected-template matching, and multi-match handling
  - keep live-rule disappearance and optimistic mutation reconciliation in the manager layer
- `custom_components/firewalla_local/models.py`
  - encode broadened switch eligibility only after the broader rule-family semantics are confirmed and stable enough for persisted template matching

Regression-test files:

- extend `tests/components/firewalla_local/test_switch.py` for registry stability, multi-match behavior, and any broader switch-eligible rule families
- extend `tests/components/firewalla_local/test_config_flow.py` only if options-flow selection behavior changes with the broader candidate pool

Stop conditions:

- stop if the broader rule family no longer behaves like a binary switch and instead needs a distinct entity contract
- stop if persisted template matching becomes ambiguous enough that one source rule can no longer identify the intended live rule family reliably

### Phase 4B completion evidence

Phase 4B is complete when all of the following are true:

- Builder can identify the touch-first file for mutation, service, schema, translation, and entity work without reopening architecture questions
- the test owner for each surface is named before implementation starts
- stop conditions are written for mutation, service targeting, and switch-surface expansion
- verify-only files are explicitly named so coordinator or entity regressions do not get rewritten casually

### Completion criteria

- every next-slice surface is assigned to named files
- the service surface is explicit, not buried inside mutation work
- follow-on entity coverage is scoped as a switch-first extension of the current model unless protocol evidence forces a change
- Builder can start the next slice without re-deciding where code, schemas, translations, and tests belong

## Phase 4C: Remaining protocol unknowns and implementation risks

### Goal

Prevent the next builder slice from over-generalizing the currently proven mutation path.

### Phase 4C starting point

Phase 4C starts from the current code, not from hypothetical future protocol work.

The present repository surfaces that anchor this risk register are:

- `custom_components/firewalla_local/api/client.py`
  - current confirmed mutation entry points are `async_create_rule`, `async_delete_rule`, and `async_update_rule`
  - current in-place update semantics are limited to toggling `disabled`, stamping `updatedTime`, and managing `idleTs`
- `custom_components/firewalla_local/managers/rule_manager.py`
  - current manager-owned mutation routing is `async_set_template_enabled`, `async_pause_rule`, and `async_resume_rule`
  - current optimistic state model mutates only enablement and pause boundary state in memory
- `custom_components/firewalla_local/services.py`
  - current service targeting assumes one target resolves either to one live rule ID or one selected-template source ID
  - current timing model supports only indefinite pause, duration-derived pause, and explicit `resume_at`
- `custom_components/firewalla_local/models.py`
  - current persisted-template model assumes a stable match can be identified from the existing normalized rule fields

### Confirmed protocol contracts

- the first switch-backed rule family supports update-in-place mutation through the current local message path
- the current service surface supports pause and resume through manager-owned mutation routing
- the current template-matching model is sufficient for the already implemented switch slice

### Allowed builder assumptions

Builder may assume only the following without reopening 4C:

- the existing local message envelope remains the transport wrapper for the already confirmed mutation entry points
- the current switch-backed slice may continue to use manager-owned optimistic enablement and pause-boundary updates
- service targeting may continue to rely on one live rule ID or one selected-template source ID for the currently implemented slice
- persisted template matching may continue to rely on the current `FirewallaRuleTemplate` shape for the already proven switch-backed family

Everything else is unproven unless new protocol evidence is captured.

### Prohibited builder assumptions

Builder must not assume any of the following without fresh evidence:

- that every user-visible rule family supports `async_update_rule` with only the currently known field set
- that all pause-like behavior is represented solely by `idleTs`
- that create payloads for broader rule families fit the current `FirewallaRuleCreatePayload` shape unchanged
- that broader rule-family matching can be done safely with the current persisted-template fields
- that any broader family still belongs on the existing switch surface

### Risk register

| Risk area | What is currently proven | What is still unproven | Current enforcement | Next proof path |
| --- | --- | --- | --- | --- |
| additional rule-family update payloads | the current local runtime accepts the existing `async_update_rule` envelope for the first supported switch-backed rule family | whether other rule families can be updated with the same payload discipline and only the current field set | Phase 4B stop condition blocks broadening the contract without evidence | extend `test_client.py` only after a new family is observed and captured honestly |
| pause or resume boundary semantics | `idleTs` works for the currently implemented pause and resume service flow | whether future rule families use `idleTs` identically, require companion fields, or encode pause differently | `services.py` only exposes indefinite pause, duration pause, and explicit `resume_at` | confirm any broader family against the wire contract before changing service schemas or manager behavior |
| create payload variance | `FirewallaRuleTemplate.build_create_value()` and `async_create_rule()` cover the currently confirmed persistent rule shape | whether broader rule families require family-specific create fields that do not fit the current typed payload shape | no new create branches have been added to the API client yet | add a typed payload extension only after repeated evidence from a broader family |
| optimistic update fidelity | manager optimistic updates currently track enablement and pause boundary changes | whether future mutations need additional local state reconciliation to avoid lying until the next poll | `rule_manager.py` limits optimistic updates to fields already proven in the current slice | add direct manager tests before widening optimistic behavior to new rule state |
| service target clarity | current services can target one live rule ID or one selected-template source ID | whether broader coverage introduces targets that are ambiguous, many-to-one, or no longer human-clear | `_get_loaded_entry()` and `has_rule_target()` enforce the current narrow service contract | reject new target forms until they can be resolved deterministically in manager code and tests |
| template matching stability | the current normalized fields are sufficient to preserve the first switch slice across live rule-ID churn | whether additional optional or family-specific fields make current persisted templates too weak or ambiguous | switch and manager code currently rely on the existing `FirewallaRuleTemplate` shape | add model and manager coverage before widening template selection to new families |

### Decision table for the next builder slice

| Observation during implementation | Builder action |
| --- | --- |
| a broader rule family works with the current update payload and only known fields | add the narrowest possible test coverage and extend support without widening unrelated model assumptions |
| a broader rule family requires additional fixed fields but still fits the current entity model | stop, document the new fields, then extend `api/models.py`, `models.py`, and tests together |
| a broader rule family requires materially different pause semantics | stop and treat it as a protocol-contract change before touching services or manager optimistic state |
| a broader rule family cannot be expressed as a binary switch | stop and require an explicit entity-surface decision |
| template matching for a broader family is ambiguous | stop and redesign the persisted matching contract before extending options flow or switch coverage |

### Unconfirmed mutation contracts

- whether additional rule families accept the same update payload discipline already proven for the first supported rule family
- whether `idleTs` remains the correct and complete pause or resume boundary for all future rule-family targets
- whether create and update payloads for broader rule shapes require family-specific fields beyond the currently proven slice
- whether template matching remains stable when additional rule families introduce more optional or family-specific fields
- whether service targeting by rule target remains clear once broader rule-family coverage is exposed

### Stop conditions for Builder

Builder must stop and ask for direction if any of the following occur:

- an additional rule family rejects the current mutation payload shape
- a new rule-family mutation requires fields that cannot be represented honestly by the current typed payload model
- pause or resume semantics differ materially from the currently proven enabled plus `idleTs` contract
- a broader rule-family slice forces a new entity surface rather than a switch-first extension
- template matching becomes ambiguous enough that the current persisted template contract no longer identifies one intended live rule class reliably

Additional stop conditions tied to the current code:

- stop if `services.py` needs to accept a target form that cannot be resolved as a deterministic manager-owned rule target
- stop if `rule_manager.py` would need to fake optimistic state beyond enablement or pause-boundary changes to keep the UI coherent
- stop if `models.py` needs family-specific persisted template fields before a stable matching rule for that family is understood

### Proof requirements before expanding support

Before Builder expands beyond the currently proven rule family, all of the following should exist for that new slice:

- one captured example of the local rule payload shape that is specific enough to justify model or payload changes
- one test in `tests/components/firewalla_local/test_client.py` or a new adjacent fast-lane test that proves the mutation envelope honestly
- one manager or service test, when relevant, that proves the routing or optimistic behavior does not drift beyond the confirmed contract
- one explicit note in this Phase 4C section if the new slice changes any currently unproven assumption into a confirmed contract

### Completion criteria

- each remaining unknown is written as a risk instead of hidden in prose
- confirmed versus unconfirmed protocol surfaces are separated clearly
- the support file names concrete stop conditions instead of assuming Builder will infer them
- allowed versus prohibited assumptions are written explicitly so Builder knows what can proceed without escalation
- a next-slice decision table exists so broader support does not slip from observation into assumption

## Phase 4D: Quality-scale closure matrix and exit criteria

### Goal

Tie the quality-scale file to evidence and blockers so Phase 4 can close truthfully.

### Quality-scale closure matrix

| Rule area | Current state | Evidence surface | Blocker or defer reason | Next action |
| --- | --- | --- | --- | --- |
| config-flow | done | `config_flow.py`, `test_config_flow.py` | none | keep regression coverage aligned with flow changes |
| config-flow-test-coverage | partial | `test_config_flow.py` | missing reconfigure edge cases, reauth failure-path coverage, and broader options-flow drift cases | keep rule as `todo` in `quality_scale.yaml` until those scenarios are named and implemented |
| action-setup and action-exceptions | done | `services.py`, `services.yaml`, `translations/en.json`, `test_services.py`, `test_init.py` | none | extend only if service surface grows |
| diagnostics | done | `diagnostics.py`, `test_diagnostics.py` | none | keep diagnostics payload shape aligned with runtime-data changes |
| entity-translations | done | `translations/en.json`, `switch.py` | none | keep aligned with any broader switch-family coverage |
| exception-translations | done | `translations/en.json`, `config_flow.py`, `services.py` | none | extend with any new failure class |
| icon-translations | done | `icons.json`, `switch.py` | none | keep Python-side icon drift out of future platform work |
| devices | done | `entity.py`, `managers/integration_manager.py`, `test_init.py`, `test_switch.py` | none | keep device attachment aligned with license-anchored identity |
| entity registry stability | partial | `switch.py`, `entity.py`, `test_switch.py` | current tests prove unique IDs and entity registration for the first switch slice but not broader cleanup or future registry drift | add explicit registry assertions when broader switch-family coverage starts |
| docs-high-level-description | done | `README.md`, `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md` | none | keep README scope summary aligned with implemented surfaces |
| docs-data-update | todo | `quality_scale.yaml`, architecture docs, coordinator behavior | current runtime snapshot and polling behavior are described in architecture notes, not in user-facing docs | add concise user-facing data update documentation before closing this rule |
| docs-installation-instructions | todo | `README.md` | release-facing install guidance is still missing | add installation steps once the integration is ready for external users |
| docs-removal-instructions | todo | `README.md` | removal guidance is not yet written | add removal steps alongside installation documentation |
| brands | todo | repository metadata and branding assets | external asset work has not been prepared yet | defer until release-prep or branding work is prioritized |
| discovery | todo | `manifest.json`, protocol knowledge | no reliable discovery mechanism has been confirmed for this integration | keep deferred unless Firewalla exposes a dependable discovery path |

### Runtime-slice closable items

- diagnostics evidence is now closable and backed by explicit diagnostics tests
- config-flow test coverage becomes closable when the missing scenarios are named and implemented
- entity registry stability becomes closable when broader switch-family coverage adds explicit registry assertions

### Deferred non-runtime items

- branding-related work
- release-facing documentation tasks that do not block runtime correctness
- discovery support unless a dependable protocol path is confirmed

### Phase 4 exit criteria

Phase 4 is complete only when:

- the validation lanes and test matrix are documented and owned
- the file-by-file builder handoff exists for mutation, service, and follow-on entity work
- the remaining protocol unknowns are recorded with explicit stop conditions
- the quality-scale closure matrix ties each relevant rule to evidence, blocker, or deliberate defer
- the next builder slice can begin without reopening the settled architecture or guessing where work belongs

## Defined handoff

Defined handoff: Firewalla Builder