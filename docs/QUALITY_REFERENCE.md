# Firewalla Local quality reference

## Purpose

This document maps repository quality expectations to the source documents and implementation surfaces that enforce them.

It is a compact reference for review and maintenance. It should stay focused on durable contracts, not temporary project status.

## Source documents

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/RULE_MODEL.md`
- `AGENTS.md`
- `custom_components/firewalla_local/quality_scale.yaml`

## Quality mapping

| Quality area | Contract | Evidence surface |
| --- | --- | --- |
| Layer boundaries | Protocol work stays inside `api/`; coordinator routes refreshes and owns config-entry writes; managers own business orchestration | `docs/ARCHITECTURE.md`, `custom_components/firewalla_local/api/`, `custom_components/firewalla_local/coordinator.py`, `custom_components/firewalla_local/managers/` |
| Strict typing | Stable structures use strong typing and mypy remains authoritative | `docs/DEVELOPMENT_STANDARDS.md`, `pyproject.toml`, `custom_components/firewalla_local/` |
| Entry scope safety | Runtime behavior remains scoped to one config entry | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, setup, services, and flow code |
| Entity reliability | Entities have stable identity, defined lifecycle handling, and correct device attachment | `docs/ARCHITECTURE.md`, platform files, entity base logic if introduced |
| Entity quality | Shared entity behavior, explicit concurrency policy, and user-meaningful metadata are standardized across rule, appliance-monitoring, watched-device, watched-user, and per-SSID (AP7) platforms, including watched-user usage totals and association metadata | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, `custom_components/firewalla_local/entity.py`, platform files |
| Mutation discipline | Manager methods are the single write path above the API layer | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, manager and service code |
| Config-entry discipline | Config-entry writes remain coordinator-owned and entry-scoped | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, coordinator and flow code |
| Translation posture | User-facing failures and service surfaces are translation-ready | translations, flows, services, repair surfaces |
| Error handling | API exceptions are typed and Home Assistant exception mapping is specific | `custom_components/firewalla_local/api/`, flows, services, coordinator |
| Diagnostics and supportability | Sensitive data is redacted while diagnostics remain useful | `custom_components/firewalla_local/diagnostics.py` |
| Runtime efficiency | Shared normalization and indexed lookup paths are used instead of repeated payload scans, including watched-user usage shaping and host-association joins | managers, models, helper report modules, platform code |
| Rule interpretation | Durable rule-control semantics, switch eligibility, and metadata grouping stay aligned with live evidence | `docs/RULE_MODEL.md`, manager logic, runtime inventory surfaces, platform attributes |
| Boundary enforcement | Architecture rules are enforced by dedicated lint or validation checks | validation tooling and review gates |
| Documentation quality | Repository guidance reflects durable rules and stays aligned with implementation | `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, `docs/QUALITY_REFERENCE.md` |

## Architecture quality contracts

### Terminology contract

- Firewalla runtime records are rules, templates, snapshots, and registry entries
- Home Assistant platform objects are entities

### Layer contract

- `api/` is framework-independent
- coordinator routes refreshes and owns config-entry writes
- manager layer owns rule resolution, mutation orchestration, optimistic updates, and lifecycle reconciliation
- entities and services remain presentation and interaction surfaces

### Multi-instance contract

- entity unique IDs include entry scope plus immutable object identity plus stable suffix
- device identity remains license-anchored
- cleanup and signaling remain entry-scoped

### Mutation contract

- rule mutations above the API layer must flow through manager methods
- optimistic updates remain in memory only
- coordinator refresh remains the source of truth

### Translation contract

- user-facing failures and operational surfaces use translation-backed messaging
- English source files remain the source of truth for translation keys

### Lifecycle contract

- dynamic entity behavior follows a shared reconciliation policy
- options changes, missing backing rules, and reload behavior remain explicit and entry-scoped

## Validation model

### Automated gates

Run:

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/firewalla_local`
- `python -m pytest tests/ -v`

### Review gates

Review changes for:

- boundary violations
- duplicated business logic outside the manager layer
- config-entry writes outside coordinator-owned paths
- non-specific exception handling
- missing translation readiness
- identity instability
- orphan-prone lifecycle behavior
- ad hoc payload parsing paths that bypass the shared registry
- unowned specialized root modules that should live under `managers/`, `helpers/`, or `utils/`

## Non-goals for this document

Do not store here:

- temporary plan status
- historical milestones
- dated certification claims
- issue tracking notes
- detailed implementation plans

## Maintenance rule

Update this document only when:

- a quality contract changes
- a source-of-truth document moves or is replaced
- the repository adds a new required validation or review gate