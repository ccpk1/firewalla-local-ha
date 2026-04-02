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
- [x] No debug-only artifacts or temporary development changes remain.

## 3) GitHub validation surfaces

- [x] `.github/workflows/lint-validation.yaml` still reflects the repository-standard Python validation commands.
- [x] `.github/workflows/validate.yaml` still runs HACS validation and hassfest.
- [x] The HACS workflow still ignores `brands` intentionally because Home Assistant 2026.3 no longer accepts custom integration branding, while this repository still keeps the brand assets staged correctly for repository and HACS guidance.

## 4) Documentation and public surfaces

- [x] `README.md` still matches the shipped feature set and support posture.
- [x] `docs/USER_GUIDE.md` still matches the actual setup, removal, and runtime behavior.
- [x] `CONTRIBUTING.md`, `SUPPORT.md`, and `SECURITY.md` still reflect the real repository process.
- [x] Any user-visible change has a short release summary prepared.

## 5) HACS and Home Assistant posture

- [x] The repository still contains only one integration under `custom_components/`.
- [x] The integration package still includes the files HACS expects.
- [ ] The repository still passes HACS structure expectations apart from the intentional `brands` bypass.
- [x] The current release posture remains compatible with Home Assistant 2026.3 or newer.

## 6) Runtime smoke

- [x] Install or upgrade through the documented HACS path.
- [x] Confirm the config flow still completes successfully against a real Firewalla box.
- [x] Confirm at least one runtime refresh succeeds after setup.
- [x] Confirm at least one representative service action still works.

## 7) Release publication

- [ ] Use a plain SemVer Git tag matching `manifest.json`, such as `1.1.0`.
- [ ] Publish a short release summary in the GitHub release body.
- [ ] Do not rely on a separate generated changelog system; use a concise manual summary and release-note-friendly PR titles.

## 8) Rollback readiness

- [x] Known risks and any deferred issues are documented before publishing.
- [ ] If the release exposes a blocking setup or packaging failure, prepare a patch release instead of silently rewriting the tag.

## 9) Launch blockers and defers

Treat these as launch blockers for `1.1.0` unless the release decision is reopened
explicitly:

- [x] The worktree is clean and free of generated artifacts.
- [x] The repository validation workflows are green on the commit being tagged.
- [x] The metadata and public docs still describe the version being released.
- [x] The live runtime smoke checks are completed against a real Firewalla box.
- [x] The release summary and known-risk notes are prepared before publication.

These items are allowed defers for the first public line if they do not regress
the shipped behavior:

- [ ] discovery support remains deferred until Firewalla exposes a durable contract.
- [ ] broader rule-family expansion remains deferred until the protocol contract is proven.
- [ ] advanced release automation remains deferred beyond the current hybrid workflow.
- [ ] custom-integration branding acceptance remains deferred because the HACS workflow intentionally bypasses the obsolete `brands` check.

## Draft release summary

- Expanded local host controls with `wake_host`, `set_host_name`, `set_host_notify_when_next_online`, `set_host_notify_when_next_offline`, and `set_host_dhcp_reservation`.
- Added broader local report surfaces for host identity records, network segment configuration, network segment usage, scoped time usage, WAN data usage, WAN events, and speed test history.
- Unified newer report services around a more consistent response envelope so automations and debugging workflows can reason about targets, queries, time basis, summaries, sections, and metadata more predictably.
- Added host DHCP reservation management with network-aware validation for the selected network range and duplicate reservation conflicts.
- Added watched-user monitoring, router-based device trackers for selected MAC-backed LAN clients, and a manual `Sync runtime` button with a runtime refresh timestamp on the main Firewalla device.

## Known risks and defers

- `get_wan_events` remains a low-level WAN health timeline surface and is not yet aligned to Firewalla's MSP alarm model.
- Broader DHCP admin surfaces remain deferred pending protocol evidence for segment-level DHCP enable or disable changes and any future delete semantics beyond the current host reservation path.
- Discovery support remains deferred until Firewalla exposes a durable local contract.
- HACS structure posture beyond the intentional `brands` bypass still depends on the repository validation workflow at release time.

## Execution snapshot (2026-04-02)

Local release-candidate checks completed in this repository:

- `bash ./utils/quick_lint.sh` passed
- `python -m mypy custom_components/firewalla_local` passed
- `python -m pytest tests/ -v` passed (`189 passed`)
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

- [x] local quality gates pass on the tagged commit.
- [x] GitHub workflow validation passes on the tagged commit.
- [x] documentation, support, and contributor surfaces still match the shipped behavior.
- [x] the HACS install or upgrade path and the live config-flow smoke path both succeed.
- [x] a representative runtime refresh and one representative service action both succeed.
- [x] any known risks, defers, and rollback expectations are documented in the release notes or release checklist.