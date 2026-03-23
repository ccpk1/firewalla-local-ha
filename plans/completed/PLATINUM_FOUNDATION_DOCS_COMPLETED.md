# Initiative Plan: platinum foundation docs

## Initiative snapshot

- Initiative: Platinum foundation docs
- Status: _COMPLETED
- Owner: Firewalla Strategist
- Primary outcome: Create durable `docs/ARCHITECTURE.md` and `docs/DEVELOPMENT_STANDARDS.md` documents that define a minimal, typed, constants-first, localization-ready foundation for this repository.
- Why now: The scaffold is intentionally small, but implementation work should not proceed without a documented architecture boundary and coding standards baseline.
- Strategic context confirmed during research:
  - the GitHub repository name is `firewalla-ha`
  - the Home Assistant UI name is `Firewalla Local`
  - the target internal domain is `firewalla_local`
  - first-time pairing uses QR data to negotiate a local-only ETP token exchange over LAN
  - local box communication uses standard signed HTTP REST requests on port `8833`
  - local rule polling endpoints are verified enough to plan coordinator-backed rule synchronization
  - the future API layer should live as a pure internal submodule under the integration package, with no `homeassistant.*` imports inside that boundary
  - the immutable Home Assistant device identity is the QR `license` value, while `gid` remains a required connection parameter only
  - the integration must depend on the `cryptography` package for RSA key generation and PKCS#8/SPKI signing
  - two consecutive `401 Unauthorized` responses define auth failure: one immediate retry, then `FirewallaAuthError`, then Home Assistant reauth

## Scope and non-goals

### In scope

- Create a repo-local documentation foundation under `docs/`.
- Define the first durable architecture contract for this integration.
- Define the first prescriptive development standards for constants, typing, localization, logging, exceptions, and validation.
- Align contributor guidance so future plans and implementation work reference the new documents.
- Capture the follow-on planning inputs required for the later runtime architecture plan.
- Record the verified transport/authentication realities that the future runtime plan must respect.

### Non-goals

- Implement the runtime architecture itself.
- Choose or document an invented Firewalla API contract.
- Introduce complex multi-layer runtime abstractions before protocol and feature scope justify them.
- Create a broad contributor handbook beyond the minimum standards needed to guide current work.
- Lock the repository into a package split or domain rename before we decide whether the existing `custom_components/firewalla/` scaffold remains the correct public shape.

## Open questions or external dependencies

1. What secure credential storage rules must be documented in Home Assistant for QR payloads, generated PEM material, and long-lived local tokens?
2. Which local rule endpoints and mutation semantics should the MVP treat as first-class, and which adjacent capabilities should remain explicitly deferred?
3. Will the integration remain config-entry-only at first, or will it require local storage, migrations, or cached snapshots that need explicit architecture coverage?
4. Do we want a separate quality reference document later, or should quality expectations live only in `quality_scale.yaml`, `ARCHITECTURE.md`, and `DEVELOPMENT_STANDARDS.md` for now?

## Phase summary table

| Phase | Focus | Deliverable | Notes |
| --- | --- | --- | --- |
| 1 | Foundation decisions | Documentation scope, terminology, naming, and boundary decisions | Prevent overbuilding before protocol is fully mapped |
| 2 | Architecture document | First `docs/ARCHITECTURE.md` | Describes structure, transport boundaries, and evolution rules |
| 3 | Standards document | First `docs/DEVELOPMENT_STANDARDS.md` | Prescriptive rules for daily coding work |
| 4 | Workflow alignment | References updated and next-plan inputs captured | Makes the docs operational, not just informational |

## Per-phase details with checkboxes

### Phase 1: Foundation decisions

Goal: Define what the first architecture and standards docs must cover, what the repo should call things, and which verified local transport rules versus deferred feature details must be recorded clearly.

- [x] Create the `docs/` directory and reserve the initial durable files:
  - `docs/ARCHITECTURE.md`
  - `docs/DEVELOPMENT_STANDARDS.md`
- [x] Document a terminology contract for this repo so future docs clearly distinguish Home Assistant entities from integration data, runtime objects, and configuration data.
- [x] Resolve the naming decision that affects future documentation and architecture language:
  - GitHub repo: `firewalla-ha`
  - Home Assistant UI name: `Firewalla Local`
  - target internal domain and package path: `firewalla_local`
  - pure internal API boundary lives under `custom_components/firewalla_local/api/`
- [x] Decide the initial architecture posture in `docs/ARCHITECTURE.md`: coordinator-centered Home Assistant wiring, backed by a mandatory pure `api/` submodule inside the integration package for crypto, signing, and HTTP session logic.
- [x] Capture the verified protocol baseline in the architecture notes:
  - first-time pairing uses QR data to negotiate a local-only ETP token exchange
  - local box control uses standard signed HTTP REST requests on port `8833`
  - local rule polling endpoints are accepted architecture inputs for the MVP
- [x] Record the Home Assistant-specific architecture constraints that must be settled in the docs:
  - the API boundary is an internal pure submodule, not a single `api.py` monolith
  - the device registry identity must use the immutable QR `license` value, never the current IP address or `gid`
  - persistent `401 Unauthorized` responses follow the one-retry rule before entering reauthentication
  - cryptographic operations require the `cryptography` dependency declared in `manifest.json`
- [x] Decide which quality topics must be first-class from day one:
  - strict typing
  - constants-first design
  - translation-ready user-facing strings
  - async-safe I/O boundaries
  - explicit validation commands
- [x] Capture explicit deferrals for items that cannot be finalized yet, including rule mutation mechanics, entity platform strategy, storage strategy beyond config entries, and any event-driven coordination patterns.

### Phase 2: Author `docs/ARCHITECTURE.md`

Goal: Create a durable architecture reference that describes what the repo is, how runtime pieces fit together, and how the structure should evolve without premature complexity or guessed feature scope.

- [x] Add an overview section describing the integration mission, target quality level, and the purpose of the architecture document.
- [x] Add a component map covering the existing scaffold and target near-term modules:
  - `__init__.py`
  - `config_flow.py`
  - `coordinator.py`
  - `const.py`
  - `models.py`
  - `diagnostics.py`
  - `api/` pure submodule for client, crypto, auth, signing, and transport code
  - platform files as they are added
- [x] Define runtime boundary rules for configuration data, runtime data, coordinator responsibilities, API submodule responsibilities, platform responsibilities, and diagnostics responsibilities.
- [x] Add a transport and authentication section that records the currently verified contract:
  - QR JSON contains pairing fields such as `gid`, `seed`, `license`, `ek`, and `ipaddress`
  - key generation uses RSA key pairs in SPKI public PEM and PKCS#8 private PEM format
  - first-time pairing is a local-only handshake that produces the credentials needed for authenticated box access
  - established local communication uses standard HTTP GET and POST requests on port `8833`, signed by the generated ETP PEM material
- [x] Add an MVP architecture section that separates the concerns of:
  - pairing and credential material
  - signed REST transport/session handling
  - rule discovery and selection state
  - Home Assistant config/options flow UX
  - coordinator-backed entity synchronization
- [x] Add a device identity section that defines the immutable QR `license` value as the Home Assistant device and config-entry identity anchor, explicitly forbids IP address based unique IDs, and treats `gid` as a connection parameter rather than a registry identifier.
- [x] Add a reauthentication lifecycle section that defines the one-retry rule for `401 Unauthorized`: one immediate retry, then `FirewallaAuthError`, then `ConfigEntryAuthFailed` in the Home Assistant layer.
- [x] Add a dependency section that states the cryptographic requirements exceed the Python standard library alone and therefore require the `cryptography` library declared and maintained in `manifest.json`.
- [x] Define structural evolution rules for when to introduce `helpers/`, `utils/`, shared entity base classes, or additional modules, including the rule that pure modules inside `api/` must not import `homeassistant.*`.
- [x] Add localization architecture guidance that treats `custom_components/firewalla/translations/en.json` as the source of truth for integration-facing copy and requires translation-ready patterns from the first feature.
- [x] Add an architecture decisions section that explicitly records current deferrals and points the next planning effort toward runtime architecture buildout once the rule control contract and package naming decision are accepted.

### Phase 3: Author `docs/DEVELOPMENT_STANDARDS.md`

Goal: Create the first prescriptive coding standards document that future implementation work can follow without guesswork.

- [x] Add a constants taxonomy section defining the approved prefixes and usage boundaries for this repo, including at minimum:
  - `CONF_*`
  - `DEFAULT_*`
  - `ATTR_*`
  - `SERVICE_*` and `SERVICE_FIELD_*` when services exist
  - `TRANS_KEY_*` for stable translation identifiers where applicable
  - flow-step constants when flows grow beyond the current minimal scaffold
- [x] Add a localization section that forbids hardcoded user-facing strings in production code and defines English source files as the only manually edited translation source.
- [x] Add a type system section requiring complete type hints, modern Python syntax, narrow exception handling, and explicit guidance for when `TypedDict`, dataclasses, enums, or plain dictionaries are appropriate.
- [x] Add a module-boundary section defining coordinator, pure `api/` submodule, helper, utility, model, and platform responsibilities, including the no-`homeassistant.*` purity rule for the `api/` tree.
- [x] Add coding rules for logging, exceptions, config flows, entity naming, unique IDs, availability, diagnostics redaction, and Home Assistant-friendly async patterns.
  - require device registry mapping to use the immutable `license` as the primary device identity anchor so entities never float across re-pairing or IP changes
  - require the API layer to translate transport and auth failures into custom integration exceptions instead of leaking raw `aiohttp` tracebacks upward
  - require `diagnostics.py` to use Home Assistant redaction helpers to scrub PII, secrets, and sensitive Firewalla payload fields before exposure
- [x] Add security and secret-handling rules covering:
  - QR payload handling in config flow
  - in-memory key generation versus file output during Home Assistant operation
  - storage of private key material and long-lived tokens
  - prohibition on logging secrets, PEM content, QR payloads, or decrypted transport bodies
- [x] Add a dependency-management section that requires external cryptography dependencies to be explicitly justified, declared in `manifest.json`, and reflected in tests and typing expectations.
- [x] Add a development workflow section with the repo validation commands from `pyproject.toml` and the expectation that documentation and translation updates accompany behavior changes when relevant.

### Phase 4: Workflow alignment and next-plan setup

Goal: Make the new docs part of the repo’s working contract and leave a clean handoff into the next architecture-planning effort.

- [x] Update `AGENTS.md` so the new `docs/ARCHITECTURE.md` and `docs/DEVELOPMENT_STANDARDS.md` are part of the default reading order for planning and implementation tasks.
- [x] Update `README.md` only if needed so contributors know the repo has durable architecture and standards documents.
- [x] Review `custom_components/firewalla/quality_scale.yaml` against the new docs and adjust wording only where the docs clarify expectations without claiming unimplemented behavior.
- [x] Add a short “next planning inputs” section to the plan docs listing the unresolved runtime questions that the follow-on architecture-buildout plan must answer.
- [x] Prepare the next strategist handoff scope: runtime architecture buildout plan for the real Firewalla integration once the documentation foundation is accepted and the naming/package posture is confirmed.

## Runtime buildout handoff

The next strategist initiative should create the runtime architecture buildout plan for the Firewalla Local integration.

That plan should cover:

- migration from `firewalla` scaffold paths to the target `firewalla_local` package layout
- design of the pure `custom_components/firewalla_local/api/` submodule
- config flow, options flow, and reauthentication flow behavior
- local pairing and key-generation execution boundaries
- coordinator data model and entity exposure rules for rule-backed entities
- testing strategy for setup, auth failure, diagnostics redaction, and entity/device registry stability

## Next planning inputs

- Which local rule endpoints and mutation contracts are first-class in the MVP
- Which rule types should be exposed first as Home Assistant entities
- Which config-entry fields are required at setup time versus options time
- Whether any storage beyond `ConfigEntry.data`, `ConfigEntry.options`, and the coordinator cache is justified

## Validation strategy

- Documentation review must confirm that `docs/ARCHITECTURE.md` and `docs/DEVELOPMENT_STANDARDS.md` are durable guidance documents, not implementation notebooks.
- The documents must treat the local signed REST transport and rule polling endpoints as verified architecture inputs.
- The documents must explicitly flag only unresolved feature details, such as mutation semantics or future capability expansion, as provisional.
- The documents must require a pure internal `api/` submodule boundary rather than normalizing a single `api.py` monolith.
- The documents must define an immutable non-IP device identity rule and a persistent-401-to-reauth lifecycle.
- The documents must explicitly acknowledge the mandatory `cryptography` dependency and its `manifest.json` impact.
- The development standards must require `license`-anchored device registry mapping, custom API exception translation, diagnostics redaction through Home Assistant utilities, and the one-retry `401` auth contract.
- The documents must not commit the repo to complex abstractions before real complexity appears.
- References between `AGENTS.md`, `README.md`, and the new docs must be internally consistent.
- If any code-adjacent guidance files are updated, confirm the referenced repo validation commands remain accurate:
  - `python -m ruff check .`
  - `python -m ruff format .`
  - `python -m mypy custom_components/firewalla_local`
  - `python -m pytest tests/ -v`

## References

- `AGENTS.md`
- `README.md`
- `pyproject.toml`
- `custom_components/firewalla/manifest.json`
- `custom_components/firewalla/config_flow.py`
- `custom_components/firewalla/coordinator.py`
- `custom_components/firewalla/api.py`
- `custom_components/firewalla/quality_scale.yaml`
- `tests/conftest.py`
- lesleyxyz/firewalla-tools
- lesleyxyz/node-firewalla
- Home Assistant Integration Quality Scale
- Home Assistant developer documentation for config flows, translations, diagnostics, and entity development