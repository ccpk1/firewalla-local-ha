# Firewalla Local release checklist

## Purpose

Use this checklist for **every** release. Work through the steps in order before
publishing a tagged release or promoting the next release candidate.

This file is the list of steps to complete each time, not a record of what went
into a given version. Release notes for a specific version belong in the GitHub
release body, and the reasoning behind a version lives in its plan under
`plans/`.

## 1) Version and metadata consistency

- [ ] `custom_components/firewalla_local/manifest.json` has the intended release version.
- [ ] `pyproject.toml` matches the same version.
- [ ] `hacs.json` still matches the supported Home Assistant and HACS contract.
- [ ] `manifest.json` still includes the correct documentation and issue tracker URLs.
- [ ] `manifest.json` does **not** list a dependency that Home Assistant already ships in `requirements`. hassfest rejects those (`cryptography` is one).

## 2) Quality gates

Run and pass:

```bash
bash ./utils/quick_lint.sh
python -m mypy custom_components/firewalla_local
python -m pytest tests/ -v
```

Checklist:

- [ ] No unresolved lint or formatting drift remains.
- [ ] No unresolved type errors remain in `custom_components/firewalla_local`.
- [ ] No failing tests remain in `tests/`.
- [ ] No debug-only artifacts or temporary development changes remain.

## 3) GitHub validation surfaces

- [ ] `.github/workflows/lint-validation.yaml` still reflects the repository-standard Python validation commands.
- [ ] `.github/workflows/validate.yaml` still runs HACS validation and hassfest, and both pass on the release commit.
- [ ] The HACS workflow still ignores `brands` intentionally, because Home Assistant 2026.3 no longer accepts custom integration branding, while this repository still keeps the brand assets staged correctly for repository and HACS guidance.

## 4) Documentation and public surfaces

- [ ] `README.md` still matches the shipped feature set and support posture.
- [ ] `docs/USER_GUIDE.md` still matches the actual setup, removal, and runtime behavior.
- [ ] `CONTRIBUTING.md`, `SUPPORT.md`, and `SECURITY.md` still reflect the real repository process.
- [ ] Any user-visible change has a short release summary prepared for the GitHub release body.
- [ ] **Any breaking change is called out in the release body**, naming the old and new
      value so an upgrading user can find it. `USER_GUIDE.md`'s *Upgrading* section is
      the source; the release body summarises it.

### Known breaking change pending release

Renamed the entity attribute keys, service-response keys and labels from `device` to
`host`, because `host` is this integration's word for a Firewalla endpoint on every
surface. Firewalla's own payloads say `device` (`deviceIP`, `devicePort`, `deviceTags`)
but that word is not echoed, because in Home Assistant a *device* is a device-registry
entry. `device_tracker` is unaffected — it is a Home Assistant platform. Full
old-to-new table in `docs/USER_GUIDE.md` under *Upgrading: renamed attributes and keys*.

| What | Detail |
| --- | --- |
| Breaks | A template or automation reading `devices_online`, `devices_offline`, `devices_total`, `vpn_devices_*`, `device_count`, `device_group`, `associated_devices`, `associated_device_count`, `associated_device_group` or `device_name` from an entity attribute or a service response. Also `device_id` / `device_ip` / `device_port` in `get_rules` `last_hit`, `device_id` / `device_name` in `get_time_usage_report`, `device_type` / `device_host_count` / the `devices` section in `get_network_segment_report`, `active_device_count` in `get_network_segment_usage`, the `device_*` keys and `destination_kind: "device"` on `get_flow_report`, the `devices` and `vpn_devices` sections of `get_system_overview`, the `devices` rows in `get_time_usage_report`, and `device_rules.removed` in the membership responses |
| Fix | Read the `hosts_*` / `host_*` / `associated_hosts*` name instead. `device_host_count` was a duplicate of `host_count` in the same response — read `host_count` |
| Not affected | `device_tracker` entities and their platform; entity ids; entity names |
| Migration | One-to-one rename; no value, type or availability changed |

## 5) HACS and Home Assistant posture

- [ ] The repository still contains only one integration under `custom_components/`.
- [ ] The integration package still includes the files HACS expects.
- [ ] The repository still passes HACS structure expectations apart from the intentional `brands` bypass.
- [ ] The release posture remains compatible with the Home Assistant versions advertised in `hacs.json`.

## 6) Runtime smoke

- [ ] Install or upgrade through the documented HACS path.
- [ ] Confirm the config flow still completes successfully against a real Firewalla box.
- [ ] Confirm at least one runtime refresh succeeds after setup.
- [ ] Confirm at least one representative service action still works.

## 7) Release publication

- [ ] Use a plain SemVer Git tag matching `manifest.json`, such as `2.1.0`.
- [ ] Publish a short release summary in the GitHub release body.
- [ ] Do not rely on a separate generated changelog system; use a concise manual summary and release-note-friendly PR titles.

## 8) Rollback readiness

- [ ] Known risks and any deferred issues are documented before publishing.
- [ ] If the release exposes a blocking setup or packaging failure, prepare a patch release instead of silently rewriting the tag.

## 9) Confirm release-specific blockers and defers

Review this step at every release rather than carrying a fixed list forward. A
release is publishable when nothing below is outstanding for the version being
tagged.

- [ ] The worktree is clean and free of generated artifacts at release cut time.
- [ ] The repository validation workflows are green on the commit being tagged.
- [ ] The metadata and public docs still describe the version being released.
- [ ] Any live runtime smoke checks are completed against a real Firewalla box.
- [ ] The release summary and known-risk notes are prepared before publication.

Known long-term defers, so they are not mistaken for release blockers:

- discovery support remains deferred until Firewalla exposes a durable contract.
- broader rule-family expansion remains deferred until the protocol contract is proven.
- broader DHCP admin surfaces remain deferred pending protocol evidence.
- advanced release automation remains deferred beyond the current hybrid workflow.
- custom-integration branding acceptance remains deferred because the HACS workflow intentionally bypasses the obsolete `brands` check.

## 10) Release exit criteria

The release is ready to publish only when all of the following are true:

- [ ] local quality gates pass on the tagged commit.
- [ ] GitHub workflow validation passes on the tagged commit.
- [ ] documentation, support, and contributor surfaces still match the shipped behavior.
- [ ] the HACS install or upgrade path and the live config-flow smoke path both succeed.
- [ ] a representative runtime refresh and one representative service action both succeed.
- [ ] any known risks, defers, and rollback expectations are documented in the release notes or this checklist.
