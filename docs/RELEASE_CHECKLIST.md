# Firewalla Local release checklist

## Purpose

Use this checklist before publishing a tagged release or promoting the next
release candidate.

## 1) Version and metadata consistency

- [x] `custom_components/firewalla_local/manifest.json` has the intended release version.
- [x] `pyproject.toml` matches the same version.
- [x] `hacs.json` still matches the supported Home Assistant and HACS contract.
- [x] `manifest.json` still includes the correct documentation and issue tracker URLs.

## 2) Quality gates

Run and pass:

```bash
bash ./utils/quick_lint.sh
python -m mypy custom_components/firewalla_local
python -m pytest tests/ -v
```

Checklist:

- [x] No unresolved lint or formatting drift remains.
- [x] No unresolved type errors remain in `custom_components/firewalla_local`.
- [x] No failing tests remain in `tests/`.
- [ ] No debug-only artifacts or temporary development changes remain.

## 3) GitHub validation surfaces

- [x] `.github/workflows/lint-validation.yaml` still reflects the repository-standard Python validation commands.
- [x] `.github/workflows/validate.yaml` still runs HACS validation and hassfest.
- [x] The HACS workflow still ignores `brands` intentionally because Home Assistant 2026.3 no longer accepts custom integration branding, while this repository still keeps the brand assets staged correctly for repository and HACS guidance.

## 4) Documentation and public surfaces

- [x] `README.md` still matches the shipped feature set and support posture.
- [x] `docs/USER_GUIDE.md` still matches the actual setup, removal, and runtime behavior.
- [x] `CONTRIBUTING.md`, `SUPPORT.md`, and `SECURITY.md` still reflect the real repository process.
- [ ] Any user-visible change has a short release summary prepared.

## 5) HACS and Home Assistant posture

- [x] The repository still contains only one integration under `custom_components/`.
- [ ] The integration package still includes the files HACS expects.
- [ ] The repository still passes HACS structure expectations apart from the intentional `brands` bypass.
- [x] The current release posture remains compatible with Home Assistant 2026.3 or newer.

## 6) Runtime smoke

- [x] Install or upgrade through the documented HACS path.
- [x] Confirm the config flow still completes successfully against a real Firewalla box.
- [x] Confirm at least one runtime refresh succeeds after setup.
- [x] Confirm at least one representative service action still works.

## 7) Release publication

- [ ] Use a plain SemVer Git tag matching `manifest.json`, such as `1.0.0`.
- [ ] Publish a short release summary in the GitHub release body.
- [ ] Do not rely on a separate generated changelog system for the first release line.

## 8) Rollback readiness

- [ ] Known risks and any deferred issues are documented before publishing.
- [ ] If the release exposes a blocking setup or packaging failure, prepare a patch release instead of silently rewriting the tag.

## 9) Launch blockers and defers

Treat these as launch blockers for `1.0.0` unless the release decision is reopened
explicitly:

- [ ] The worktree is clean and free of generated artifacts.
- [x] The repository validation workflows are green on the commit being tagged.
- [x] The metadata and public docs still describe the version being released.
- [x] The live runtime smoke checks are completed against a real Firewalla box.
- [ ] The release summary and known-risk notes are prepared before publication.

These items are allowed defers for the first public line if they do not regress
the shipped behavior:

- [ ] discovery support remains deferred until Firewalla exposes a durable contract.
- [ ] broader rule-family expansion remains deferred until the protocol contract is proven.
- [ ] advanced release automation remains deferred beyond the current hybrid workflow.
- [ ] custom-integration branding acceptance remains deferred because the HACS workflow intentionally bypasses the obsolete `brands` check.

## Execution snapshot (2026-03-27)

Local release-candidate checks completed in this repository:

- `bash ./utils/quick_lint.sh` passed
- `python -m mypy custom_components/firewalla_local` passed
- `python -m pytest tests/ -v` passed (`124 passed`)
- metadata alignment confirmed for `manifest.json`, `pyproject.toml`, and `hacs.json`
- workflow contract confirmed in `.github/workflows/lint-validation.yaml` and `.github/workflows/validate.yaml`

Remaining pre-publish items require release-operator execution, GitHub workflow run status,
or live hardware verification:

- clean worktree verification at release cut time
- HACS install or upgrade smoke path
- config-flow and runtime smoke checks against a real Firewalla box
- representative service-action smoke verification
- final release summary and known-risk notes in the GitHub release

## 10) Release exit criteria

The release candidate is ready to publish only when all of the following are
true:

- [ ] local quality gates pass on the tagged commit.
- [x] GitHub workflow validation passes on the tagged commit.
- [ ] documentation, support, and contributor surfaces still match the shipped behavior.
- [x] the HACS install or upgrade path and the live config-flow smoke path both succeed.
- [x] a representative runtime refresh and one representative service action both succeed.
- [ ] any known risks, defers, and rollback expectations are documented in the release notes or release checklist.