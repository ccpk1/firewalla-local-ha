# Initiative Plan: Firewalla Local release prep

## Initiative snapshot

- Initiative: Firewalla Local release prep
- Status: In process
- Owner: Firewalla Strategist
- Primary outcome: Convert the current runtime-complete repository into a release-ready custom integration with consistent public metadata, clear operator guidance, durable distribution mechanics, and an explicit launch checklist.
- Why now: The runtime buildout plan is complete and archived, but the repository still has release-facing gaps and inconsistencies that should be closed deliberately rather than absorbed piecemeal into feature work.

## Scope and non-goals

### In scope

- Define the release authority for versioning across repository metadata, Home Assistant manifest metadata, HACS metadata, and GitHub releases.
- Define the repository-facing cleanup required before public release, including contributor, support, and ownership surfaces.
- Define the minimum automation and validation contract required for repeatable release candidates.
- Define the launch checklist for the first public release or the next formal tagged release.

### Non-goals

- Implement new runtime features unrelated to release readiness.
- Re-open the completed runtime buildout architecture unless a release blocker exposes a real mismatch.
- Promise discovery, new rule families, or additional monitoring surfaces as part of this release-prep plan.
- Treat speculative automation or project-management preferences as mandatory unless they directly reduce release risk.

## Open questions or external dependencies

1. Is GitHub Actions required before release, or is a documented manual release process acceptable for the first shipped version?
2. Are issue templates, discussion categories, and PR templates required before release, or can support continue with the current lightweight repository surfaces?
3. Should release-prep also normalize repository branding drift where `CONTRIBUTING.md` and `CODEOWNERS` still refer to ChoreOps?

Support note: See `plans/in-process/FIREWALLA_LOCAL_RELEASE_PREP_SUP_GITHUB_OPERATIONS_AND_RELEASE_NOTES.md` for the ChoreOps-derived GitHub management and release-note inventory that should guide workflow, linting, and release-governance decisions in this initiative.

## Phase summary table

| Phase | Focus | Deliverable | Notes |
| --- | --- | --- | --- |
| 1 | Release audit and version contract | Repository-wide release readiness inventory | Resolves metadata authority, naming drift, and launch blockers before automation work starts |
| 2 | Public repository and operator surfaces | External-facing docs and support cleanup plan | Keeps the first public release coherent for end users and contributors |
| 3 | Distribution and automation | Repeatable release mechanics plan | Covers HACS, tags, changelog or release notes flow, and CI expectations |
| 4 | Release candidate and launch gate | Final checklist and exit criteria | Defines what must be true before cutting a release |

## Per-phase details with checkboxes

### Phase 1: Release audit and version contract

Goal: Establish one authoritative release contract and inventory the concrete gaps between the current repo state and a publishable release.

- [x] Audit release-facing metadata across:
  - `custom_components/firewalla_local/manifest.json`
  - `pyproject.toml`
  - `hacs.json`
  - GitHub release expectations documented in `README.md`
- [x] Decide and document the single source of truth for release versioning, including how the integration version, package version, and Git tag version relate.
- [x] Resolve the current version mismatch between `manifest.json` and `pyproject.toml` as an explicit release-prep task rather than leaving it implicit.
- [x] Review repository ownership and naming drift in:
  - `CODEOWNERS`
  - `CONTRIBUTING.md`
  - `SUPPORT.md`
  - `SECURITY.md`
  and classify each item as release-blocking, release-recommended, or post-release cleanup.
- [x] Record whether the first release requires any remaining quality-scale evidence updates in `custom_components/firewalla_local/quality_scale.yaml` or whether the current file is already sufficient for release.

Phase 1 execution note: Phase 1 is complete.

- Release contract locked for the 1.0.0 line.
- Authoritative integration release version: `custom_components/firewalla_local/manifest.json`.
- GitHub release tags should match the manifest version exactly using plain SemVer for release publication: `1.0.0`, `1.0.1`, and so on.
- `pyproject.toml` is not the runtime authority for Home Assistant, but it must remain aligned with the manifest release version so repository metadata, packaging metadata, and public release communication do not drift.
- `hacs.json` remains compatibility metadata, not the release-version source of truth.
- `README.md` already presents the repository as publicly releasable and does not currently conflict with a 1.0.0 launch posture.
- `quality_scale.yaml` is already sufficient for Phase 1 release audit purposes and does not require immediate edits in this phase.

Repository governance drift classification from Phase 1 audit:

- `CONTRIBUTING.md`: release-recommended cleanup because it is still ChoreOps-branded and references workflow conventions that are not yet fully implemented in this repo.
- `CODEOWNERS`: release-recommended cleanup because the ownership header still says ChoreOps even though the path ownership is otherwise usable.
- `SUPPORT.md`: acceptable for release in its current minimal form, with optional expansion in a later phase.
- `SECURITY.md`: acceptable for release in its current form.

Phase 1 outcome summary:

- the repository is now aligned to a 1.0.0 release contract at the manifest and `pyproject.toml` level
- version-authority ambiguity is resolved
- remaining release-prep work is now concentrated in contributor-surface cleanup, GitHub operations, release-note policy, and launch checklist definition rather than basic metadata alignment

### Phase 2: Public repository and operator surfaces

Goal: Make the repository readable and trustworthy for external users, maintainers, and contributors.

- [x] Review `README.md` and `docs/USER_GUIDE.md` together and define the canonical split between:
  - quick-start install flow
  - operational usage guidance
  - removal and support guidance
  - security caveats and scope disclaimers
- [x] Add a release-prep cleanup task for any contributor-facing drift, especially the current ChoreOps references in `CONTRIBUTING.md` and `CODEOWNERS`.
- [x] Define the minimum support posture for release across:
  - `SUPPORT.md`
  - `SECURITY.md`
  - GitHub Issues and Discussions expectations
- [x] Review whether the current README claims around Platinum quality, supported hardware, and release availability match the actual shipped state and identify any wording that must soften before release.
- [x] Confirm that brand assets under `custom_components/firewalla_local/brand/` are sufficient for release and identify any remaining branding tasks outside the integration package, such as repository social preview or release artwork, only if they materially affect launch quality.
- [x] Normalize GitHub-facing contributor and governance files so Firewalla Local naming, contributor instructions, and support routing all match the real repository rather than inherited ChoreOps wording.

Phase 2 execution note: Phase 2 is complete.

- `README.md` and `docs/USER_GUIDE.md` now have an explicit, acceptable split for a 1.0.0 release posture: README owns the public quick-start, scope, support routing, and release-facing framing, while the user guide owns operational setup, pairing, removal, refresh behavior, and runtime-surface details.
- The README was reviewed as mostly release-ready. The only concrete automation mismatch was the existing workflow badge, so this phase kept the badge and aligned the repository to it instead of softening public release language.
- Contributor and governance drift has been normalized in `CONTRIBUTING.md` and `CODEOWNERS` so Firewalla Local naming and contributor guidance now match the real repository.
- `SUPPORT.md` now reflects the actual current support posture instead of assuming issue templates that do not yet exist.
- Existing brand assets under `custom_components/firewalla_local/brand/` are sufficient for release-package purposes in this phase.
- The repository now includes a first GitHub validation workflow at `.github/workflows/lint-validation.yaml` plus a checked-in `utils/quick_lint.sh` entrypoint so the public README badge is backed by a real repository surface.

Phase 2 outcome summary:

- end-user docs required only minor review, not a rewrite
- the main public-surface cleanup work was governance and contributor-surface accuracy
- the repository now has a truthful path from README badge to workflow file to checked-in lint command

### Phase 3: Distribution and automation

Goal: Define how releases are produced, validated, and published in a way that can be repeated without guesswork.

- [x] Decide whether the first release will use documented manual steps, GitHub Actions, or a hybrid flow, and record the minimum acceptable release process.
- [x] Inventory the current GitHub automation surface under `.github/` and explicitly capture the absence of `.github/workflows/` as a release-prep decision point rather than an accidental omission.
- [x] Define the minimum GitHub management layer to adopt from ChoreOps, with special attention to:
  - validation workflows
  - lint or quality-gate workflow structure
  - release-note categorization source of truth
  - issue-template and triage expectations
- [x] Define the release-note and changelog contract, including where user-facing release notes live and how they reference breaking changes, migration notes, and validation evidence.
- [x] Define the HACS-facing release contract, including version tags, branch expectations, and any repository metadata checks required before publishing.
- [x] Define the pre-release validation command set for release candidates, using the repository-standard commands and identifying which commands are mandatory versus situational:
  - `python -m ruff check .`
  - `python -m ruff format .`
  - `python -m mypy custom_components/firewalla_local`
  - `python -m pytest tests/ -v`

Phase 3 execution note: Phase 3 is complete.

- The release process for the 1.0.0 line is now defined as a hybrid model: GitHub Actions enforces repository validation continuously, while final release publication still depends on a documented manual release pass and a short GitHub release summary.
- The repository automation surface now includes two distinct workflows:
  - `.github/workflows/lint-validation.yaml` for Ruff, MyPy, and pytest
  - `.github/workflows/validate.yaml` for HACS validation and hassfest
- The HACS workflow intentionally ignores the `brands` check because Home Assistant 2026.3 no longer accepts branding from custom integrations. This repository still keeps the brand assets staged correctly for repository guidance, but release validation should not fail on that obsolete acceptance path.
- The release-note contract is intentionally simple for the first release line: user-visible pull requests should carry a short release summary in the PR, and published GitHub releases should use a concise manual summary instead of a separate generated changelog system.
- The repository now has a minimum GitHub intake layer through simplified issue templates, issue-config routing to Discussions, and a pull request template that captures validation plus release-summary text.
- The repository now has a durable release checklist in `docs/RELEASE_CHECKLIST.md` covering version alignment, GitHub validation surfaces, HACS posture, runtime smoke checks, and rollback readiness.
- The HACS-facing contract is now explicit: one integration per repository, plain SemVer tags matching `manifest.json`, and repository validation that accepts the current Home Assistant branding limitation by bypassing the obsolete HACS `brands` check.

Phase 3 outcome summary:

- release automation is now defined and minimally implemented
- GitHub contributor intake is present and simpler than ChoreOps by design
- release notes remain summary-driven rather than automation-heavy for the first public line

### Phase 4: Release candidate and launch gate

Goal: Turn the release-prep work into a concrete launch checklist with explicit stop conditions.

- [ ] Define the release-candidate checklist covering metadata consistency, docs readiness, support posture, validation success, and known-risk disclosure.
- [ ] Record launch blockers versus launch defers so unresolved future work does not silently block release if it is not truly required.
- [ ] Define the first-release smoke checks after tagging or publishing, including HACS install verification, config-flow setup verification, and at least one end-to-end local runtime validation against a real box.
- [ ] Define the rollback or hotfix expectations if the first public release exposes a packaging, setup, or migration problem.
- [ ] Record the final release exit criteria in a form that a builder can execute without re-opening strategic questions.

## Validation strategy

- Planning validation in this initiative means verifying that each release-prep task maps to a concrete repository surface and a concrete outcome, not merely to a general aspiration.
- Implementation validation for the eventual release-prep work should include, at minimum:
  - metadata consistency checks across `manifest.json`, `pyproject.toml`, and `hacs.json`
  - repository-standard lint, type-check, and test commands
  - manual review of `README.md`, `docs/USER_GUIDE.md`, `CONTRIBUTING.md`, `SUPPORT.md`, and `SECURITY.md`
  - at least one real install or upgrade verification path through HACS or the documented manual process
- Any automation added in this initiative must be validated against the current repo layout rather than copied from unrelated repositories.

## References

- `README.md`
- `docs/USER_GUIDE.md`
- `SECURITY.md`
- `SUPPORT.md`
- `CONTRIBUTING.md`
- `CODEOWNERS`
- `hacs.json`
- `pyproject.toml`
- `custom_components/firewalla_local/manifest.json`
- `custom_components/firewalla_local/quality_scale.yaml`
- `plans/completed/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_COMPLETE.md`