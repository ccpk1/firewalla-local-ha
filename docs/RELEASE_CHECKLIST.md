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
- [ ] The HACS workflow passes **every** check, with no `ignore` key. Brand assets live in `custom_components/firewalla_local/brand/`, which is what satisfies the brands check: the `custom_integrations` folder in `home-assistant/brands` is closed to new entries, and local brand images have been the supported replacement since Home Assistant 2026.3.

## 4) Documentation and public surfaces

- [ ] `README.md` still matches the shipped feature set and support posture.
- [ ] `docs/USER_GUIDE.md` still matches the actual setup, removal, and runtime behavior.
- [ ] `CONTRIBUTING.md`, `SUPPORT.md`, and `SECURITY.md` still reflect the real repository process.
- [ ] Any user-visible change has a short release summary prepared for the GitHub release body.
- [ ] **Any breaking change is called out in the release body**, naming the old and new
      value so an upgrading user can find it. `plans/in-process/RELEASE_NOTES_2.5.0.md` is the
      source, and is itself the release body.

### Known breaking change pending release

Renamed the entity attribute keys, service-response keys and labels from `device` to
`host`, because `host` is this integration's word for a Firewalla endpoint on every
surface. Firewalla's own payloads say `device` (`deviceIP`, `devicePort`, `deviceTags`)
but that word is not echoed, because in Home Assistant a *device* is a device-registry
entry. `device_tracker` is unaffected — it is a Home Assistant platform. Full
old-to-new tables are in the *Breaking changes* section of
`plans/in-process/RELEASE_NOTES_2.5.0.md`.

| What | Detail |
| --- | --- |
| Breaks | A template or automation reading `devices_online`, `devices_offline`, `devices_total`, `vpn_devices_*`, `device_count`, `device_group`, `associated_devices`, `associated_device_count`, `associated_device_group` or `device_name` from an entity attribute or a service response. Also `device_id` / `device_ip` / `device_port` in `get_rules` `last_hit`, `device_id` / `device_name` in `get_time_usage`, `device_type` / `device_host_count` / the `devices` section in `get_network_config`, `active_device_count` in `get_network_usage`, the `device_*` keys and `destination_kind: "device"` on `get_flow_report`, the `devices` and `vpn_devices` sections of `get_system_overview`, the `devices` rows in `get_time_usage`, and `device_rules.removed` in the membership responses. Two further renames: the abbreviated `conn` / `dns` / `dns_blocked` / `ip_blocked` / `ip_denied` / `ntp` counters in `get_network_usage` host rows, and `config_entry_id`, which every response no longer echoes. Also `ip_address` is now `host_ip` wherever a host record or the watched-device attribute publishes it, the network configuration section's `kind` / `type` are now `network_kind` / `interface_type`, and a tag-scoped rule reports `target: null` instead of the box's `TAG` sentinel, with the new `applies_to_kind` naming each `applies_to` entry |
| Fix | Read the `hosts_*` / `host_*` / `associated_hosts*` name instead. `device_host_count` was a duplicate of `host_count` in the same response — read `host_count` |
| Not affected | `device_tracker` entities and their platform; entity ids; entity names |
| Migration | One-to-one rename; no value, type or availability changed |

### Known breaking change pending release — time and derived state

Every published moment now names what it is an instant of, and appears twice: a date
(`<name>_at`) and epoch seconds (`<name>_at_timestamp`). Derived windowed values such as
`online` are published alongside the reference instant and window they were measured in,
so they can be checked from the payload. Full old-to-new tables are in the *Breaking
changes* section of `plans/in-process/RELEASE_NOTES_2.5.0.md`.

| What | Detail |
| --- | --- |
| Breaks | A template, automation or agent read of `last_active` on the watched-host, device-tracker and watched-user surfaces (`last_active_at` + `last_active_at_timestamp` now); `fired_at` on the alarm sensor, which was an epoch number and is now a date; `get_rules`' `last_hit.at` / `.timestamp` (`matched_at` / `matched_at_timestamp`); `timestamp` in `get_flow_report` records (`occurred_at` + `occurred_at_timestamp`), in `get_wan_events` (`occurred_at_timestamp` + `occurred_at`) and in `get_network_usage` metric samples (`sampled_at_timestamp` + `sampled_at`); `begin_timestamp_iso` / `end_timestamp_iso` / `anchor_timestamp_iso` in the report `time_basis` blocks (`begin` / `end` / `anchor`); and `activated_time` / `updated_time` / `last_activated_time` in `get_runtime_inventory` rule records (`activated_at` / `updated_at` / `last_activated_at`). `get_runtime_inventory` also changed `expires_at` and `pause_until` from epoch numbers to dates, matching the rule service surface. Bare `timestamp` is gone from every response |
| Fix | Read the `_at` form for a date and the `_at_timestamp` twin for arithmetic. Where a value was already correct but unpaired (`tested_at`, `sampled_at`, `pause_until`, `runtime_data_updated_at`, `expires_at`, `begin` / `end` / `anchor`), the key is unchanged and the twin is new, so nothing breaks. `online` is unchanged and now carries `activity_reference_at` / `activity_reference_at_timestamp` / `online_window_seconds` beside it |
| Not affected | Entity ids, entity names, device registry entries, all attribute *values* other than `fired_at`, `expires_at` and `pause_until` in the runtime inventory, and the local-time report boundaries, which keep their `time_zone` and offset |
| Migration | Rename and pair only; no value, type or availability changed except the three epoch-to-date corrections above, each of which keeps its number under the new `_timestamp` twin |

**No shim, alias or deprecation period accompanies this break.** An alias would leave two
names for one value, which is the defect this change removes. The tables in the *Breaking
changes* section of `plans/in-process/RELEASE_NOTES_2.5.0.md` are the migration, and a
reviewer should not ask for a compatibility layer.

## 5) HACS and Home Assistant posture

- [ ] The repository still contains only one integration under `custom_components/`.
- [ ] The integration package still includes the files HACS expects.
- [ ] The repository still passes every HACS structure expectation, including the brands check, with no checks ignored.
- [ ] The release posture remains compatible with the Home Assistant versions advertised in `hacs.json`.

### Release asset

`hacs.json` sets `zip_release: true` with `filename: firewalla_local.zip`, so HACS
downloads the named asset from the release instead of the tag's source archive.
That choice is what makes the download counter meaningful — HACS reports the
GitHub asset's `download_count`, which only moves when an asset is fetched — and
it is also a hard requirement: if the asset is missing or misnamed, every install
and upgrade fails with `Download of firewalla_local.zip was not completed`.

`.github/workflows/release.yaml` builds and attaches it on `release: published`,
and fails the run if:

- the tag does not match `manifest.json`'s `version` (HACS would otherwise
  advertise one version and install another);
- the archive is missing `manifest.json`, `__init__.py` or `translations/en.json`
  at its root;
- the archive contains a `custom_components/` wrapper directory.

The archive is built from inside `custom_components/firewalla_local`, because
HACS extracts it straight into `custom_components/` and a wrapping directory
would nest the integration one level too deep. That failure is silent at build
time and only breaks installs, which is why the workflow asserts the layout.

- [ ] `hacs.json` still declares `zip_release` and a `filename` that matches the
      asset the workflow uploads.
- [ ] The published release has `firewalla_local.zip` attached, and its size is
      plausible (a few hundred KB, not a few KB).
- [ ] The tag equals `manifest.json`'s `version`.

## 6) Runtime smoke

- [ ] Install or upgrade through the documented HACS path.
- [ ] Confirm the config flow still completes successfully against a real Firewalla box.
- [ ] Confirm at least one runtime refresh succeeds after setup.
- [ ] Confirm at least one representative service action still works.

## 7) Release publication

- [ ] Use a plain SemVer Git tag matching `manifest.json`, such as `2.1.0`.
- [ ] Publish a short release summary in the GitHub release body.
- [ ] Do not rely on a separate generated changelog system; use a concise manual summary and release-note-friendly PR titles.

Order matters, because the asset is produced by a workflow that reacts to the
release:

1. Push the tag.
2. Save the release **without** `firewalla_local.zip` attached; the publish step
   runs `release.yaml`, which builds the archive, checks its layout and attaches
   it. Drafting a release does not trigger it — only `published` does.
3. Confirm the `Release` workflow run went green, which also confirms the tag and
   `manifest.json` agree.
4. Confirm the asset is on the release.
5. Only then treat the version as live, because HACS fetches that asset.

The workflow file has to be on the **default branch** before the release is
published. A workflow added on the release branch alone will not be picked up for
a `release` event, and the release would publish with no asset.

## 8) Rollback readiness

- [ ] Known risks and any deferred issues are documented before publishing.
- [ ] If the release exposes a blocking setup or packaging failure, prepare a patch release instead of silently rewriting the tag.
- [ ] If the asset is missing or malformed, re-run the `Release` workflow for that
      release rather than re-tagging; re-running replaces the asset and leaves the
      tag history intact.

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
- a stable release still needs to be cut for 2.5.0: `2.5.0-beta.2` is published as a
  prerelease, and HACS serves the latest **non**-prerelease to default users, so the store
  still offers 2.1.0.

## 10) Release exit criteria

The release is ready to publish only when all of the following are true:

- [ ] local quality gates pass on the tagged commit.
- [ ] GitHub workflow validation passes on the tagged commit.
- [ ] documentation, support, and contributor surfaces still match the shipped behavior.
- [ ] the HACS install or upgrade path and the live config-flow smoke path both succeed.
- [ ] a representative runtime refresh and one representative service action both succeed.
- [ ] any known risks, defers, and rollback expectations are documented in the release notes or this checklist.
