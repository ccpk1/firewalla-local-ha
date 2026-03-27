# Support note: GitHub operations and release-notes inventory

## Purpose

Capture the GitHub management, release-note, workflow, and lint-validation practices used in `ccpk1/ChoreOps`, then translate them into a concrete Firewalla Local release-prep inventory.

This note is intentionally repository-specific. It does not assume Firewalla Local should copy ChoreOps wholesale. It separates portable best practices from ChoreOps-only complexity.

## External source surfaces reviewed

ChoreOps evidence was reviewed from these repository surfaces:

- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/TRIAGE.md`
- `CONTRIBUTING.md`
- `SUPPORT.md`
- `AGENTS.md`
- plan and completion notes referencing:
  - `.github/workflows/validate.yaml`
  - `.github/workflows/lint-validation.yaml`
  - `.github/workflows/translation-sync-manual.yaml`
  - `.github/release.yml`
  - `.github/ISSUE_TEMPLATE/*`

Current Firewalla Local comparison surfaces reviewed:

- `.github/`
- `README.md`
- `CONTRIBUTING.md`
- `SUPPORT.md`
- `SECURITY.md`
- `hacs.json`
- `pyproject.toml`
- `custom_components/firewalla_local/manifest.json`
- `custom_components/firewalla_local/quality_scale.yaml`

## Portable best-practice inventory from ChoreOps

### 1. Pull-request-first merge and release-note contract

ChoreOps treats PR metadata as part of release infrastructure, not as optional maintainer etiquette.

Portable practices:

- require PRs to `main` for release-bound work
- require `Closes #...` when a change resolves an issue
- require release-note category labels on PRs
- require release-note-friendly PR titles because generated notes surface titles directly
- require validation evidence to be recorded in the PR

Why it matters for Firewalla Local:

- it keeps release notes classifiable without hand reconstruction
- it ties issue closure to shipped work instead of informal branch state
- it reduces ambiguity when multiple small changes land between releases

### 2. Explicit issue workflow labels versus shipped-release labels

ChoreOps cleanly separates open-issue workflow state from shipped-release state.

Portable practices:

- use `status:*` labels only for open issue workflow state
- use `release: pending` after merge but before a public release ships
- use `release: shipped` only after release publication
- keep release-note category labels separate from issue delivery labels

Why it matters for Firewalla Local:

- it prevents label overload and ambiguous issue state
- it makes post-release cleanup and support easier to reason about

### 3. Dedicated release checklist document

ChoreOps keeps release discipline in a durable checklist instead of burying it in plan prose.

Portable practices:

- maintain a single release checklist document
- include version readiness and schema or migration readiness
- include quality gates, translation checks, and architecture checks
- include post-release verification and rollback readiness
- include release-notes wording expectations for user-visible changes

Why it matters for Firewalla Local:

- it gives maintainers a repeatable release gate
- it makes first release and patch release behavior consistent

### 4. Workflow-backed lint and validation gates

ChoreOps treats linting and validation as repository operations, not just developer habits.

Portable practices:

- provide a dedicated lint or validation workflow in `.github/workflows/`
- make workflow output guide contributors toward prerequisites instead of failing silently
- keep lint commands centralized in a reusable script or at least a well-known command set
- use CI for regression checks that are easy to forget locally, such as repo-brand or path-contract guardrails

Why it matters for Firewalla Local:

- this repo currently has no `.github/workflows/` directory
- release confidence is still dependent on local, manually reported command runs
- lint and type-check expectations are documented, but not repository-enforced on GitHub

### 5. Contributor and support surfaces aligned to actual repo operations

ChoreOps keeps `CONTRIBUTING.md`, `SUPPORT.md`, and maintainer instructions aligned with GitHub automation and release-note policy.

Portable practices:

- keep contributor docs consistent with real validation commands
- document discussions vs issues clearly
- document support routing and pre-bug expectations
- align agent or maintainer guidance with the same merge and release-note rules

Why it matters for Firewalla Local:

- `CONTRIBUTING.md` is still ChoreOps-branded
- contributor guidance references release-note labels, but this repo does not yet expose the matching GitHub management files

### 6. Release-note source of truth is defined

ChoreOps explicitly defines where release-note categorization comes from.

Portable practices:

- define whether release notes are generated from `.github/release.yml`, PR labels, handwritten changelogs, or a hybrid process
- keep user-visible wording in plain language
- require migration or upgrade notes when applicable

Why it matters for Firewalla Local:

- the current repo presents release badges and a public version story, but it does not yet define how release notes are categorized or generated

### 7. Repository-governance files are part of release readiness

ChoreOps treats GitHub management files as release-facing assets.

Portable practices:

- maintain `CODEOWNERS`
- maintain issue-template configuration
- maintain release configuration such as `.github/release.yml`
- maintain CI guards for naming or brand regressions when repository drift is a real risk

Why it matters for Firewalla Local:

- `.github/` currently contains only `FUNDING.yml` and `agents/`
- there are no issue templates, no release config, and no workflows

## Firewalla Local current coverage snapshot

### Already covered reasonably well

- HACS metadata exists in `hacs.json`
- install and removal guidance exist in `README.md` and `docs/USER_GUIDE.md`
- support routing exists in `SUPPORT.md`
- security reporting exists in `SECURITY.md`
- release-prep planning now exists in `plans/in-process/FIREWALLA_LOCAL_RELEASE_PREP_IN-PROCESS.md`
- local validation command expectations are documented in `AGENTS.md`

### Not yet covered or only partially covered

- no `.github/workflows/` validation or lint automation
- no `.github/release.yml` or equivalent release-note category contract
- no issue-template configuration under `.github/ISSUE_TEMPLATE/`
- no documented label taxonomy equivalent to ChoreOps `docs/TRIAGE.md`
- no durable `docs/RELEASE_CHECKLIST.md`
- contributor docs still contain ChoreOps branding drift
- no explicit CI-backed repo guardrails for naming or documentation drift

## Recommended adoption order for Firewalla Local

### Tier 1: High-value, low-controversy adoption

Adopt these first because they directly improve release readiness without requiring complex multi-repo governance.

1. Add a Firewalla Local release checklist document
2. Add at least one GitHub validation workflow covering Ruff, MyPy, and pytest
3. Define PR merge and release-note rules in contributor docs and align them with actual GitHub files
4. Fix branding and repo-name drift in `CONTRIBUTING.md` and `CODEOWNERS`

### Tier 2: GitHub workflow and issue hygiene

Adopt these once the base release contract is defined.

1. Add `.github/release.yml` or a clearly documented alternative for changelog grouping
2. Add issue templates and config under `.github/ISSUE_TEMPLATE/`
3. Add a simple triage and label policy document for maintainers

### Tier 3: Nice-to-have or only if maintenance burden justifies it

These are useful, but they should not block a first release unless the owner explicitly wants the stronger governance model.

1. CI checks for naming or brand-regression drift
2. automation for label transitions such as `release: pending` to `release: shipped`
3. more advanced release automation beyond tag-and-validate basics

## Firewalla Local gap list to carry into release prep

- define one source of truth for release-note categorization
- define whether release notes are generated or maintained manually
- add workflow-backed lint and validation gates
- add a release checklist document
- align `CONTRIBUTING.md` with Firewalla Local branding and actual commands
- decide whether label taxonomy and issue templates are required before first release

## Suggested integration into the release-prep initiative

Use this support note as the source material for these release-prep tasks:

- Phase 1: version and governance audit
- Phase 2: public repository and contributor-surface cleanup
- Phase 3: distribution and automation definition
- Phase 4: launch checklist and release-candidate gate

The main recommendation from this inventory is simple:

- Firewalla Local does not need all of ChoreOps governance complexity
- Firewalla Local does need the minimum durable GitHub operations layer: workflows, release-note policy, checklist discipline, and contributor-doc consistency