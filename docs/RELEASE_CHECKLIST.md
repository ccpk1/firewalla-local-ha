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

Treat these as launch blockers for `2.0.0` unless the release decision is reopened
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

- Added per-SSID wireless control (AP7): every wireless network (SSID) is exposed as a pause/resume toggle switch plus a status binary sensor carrying band, encryption, WPA3, VLAN, and interface details, with optimistic pause state updates.
- Added per-AP device monitoring (AP7): each Firewalla AP7 access point becomes its own Home Assistant device with a system-status binary sensor exposing channel, LED, TX power, country, mesh mode, timezone, pause-WiFi/ACL state, and live client count.
- Added a unified LAN network model with per-network status entities (LAN, VLAN, VPN, WAN) carrying kind, VLAN ID, ports, IPv4/IPv6 + DHCP, device count, advanced options, and usage — including current-month WAN usage.
- Added per-WAN internet quality monitoring with ping latency and packet-loss sensors plus a `get_internet_quality_report` service.
- Expanded appliance monitoring with per-port link/speed/MAC, Bluetooth MAC, box time zone, and derived box WAN IP.
- Fixed device trackers so integration-disabled tracker entities can be re-enabled and use the non-deprecated device registry lookup.

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

## Patch release 2.0.1

Patch release on top of `2.0.0` for two narrow log-noise and deprecation fixes.
There is no user-facing behavior change.

### Version and metadata

- [x] `custom_components/firewalla_local/manifest.json` set to `2.0.1`.
- [x] `pyproject.toml` set to `2.0.1`.
- [ ] Git tag `2.0.1` created on the release commit after merge into `main`.
- [ ] GitHub release published with the summary below.

### Fixes in this patch

- Removed duplicate `name` and `description` keys in `services.yaml` under
  `get_internet_quality_report`. The duplicate keys made Home Assistant log
  `annotatedyaml` duplicate-key warnings on every startup.
- Replaced the deprecated `via_device` device-registry argument with
  `via_device_id` in `async_reconcile_tracked_client_devices` and
  `async_reconcile_ap_devices`. This removes the
  `homeassistant.helpers.frame` deprecation warning and keeps device grouping
  working after Home Assistant 2027.8.0.

### Patch quality gates

- [ ] `bash ./utils/quick_lint.sh`
- [ ] `python -m mypy custom_components/firewalla_local`
- [ ] `python -m pytest tests/ -v`
- [ ] Startup log verified free of both warnings against a real Firewalla box

### Draft release summary

Firewalla Local 2.0.1 is a small patch release that removes two startup log
warnings introduced in 2.0.0:

- Fixed duplicate YAML keys in the service definition for
  `get_internet_quality_report`, which caused `services.yaml` duplicate-key
  warnings at startup.
- Updated tracked-client and AP device registration to use the current
  `via_device_id` device-registry parameter instead of the deprecated
  `via_device` identifier, ahead of Home Assistant 2027.8.0.

No configuration changes and no user action required.

### Patch risk notes

- Device grouping is unchanged: existing devices already store the resolved
  `via_device_id`, and the reconcilers keep updating it on rename, so no
  migration is needed.
- Rollback path is a revert of the two fix commits plus a re-tag, following the
  repository rule of publishing a new patch instead of rewriting a shipped tag.

## Minor release 2.1.0

Minor release covering the Local Surface Completion initiative (Phases 1–3):
access hardening, alarm telemetry, and surface visibility. No configuration
migration and no user action required.

### Version and metadata

- [x] `custom_components/firewalla_local/manifest.json` set to `2.1.0`.
- [x] `pyproject.toml` set to `2.1.0`.
- [x] `hacs.json` still matches the supported Home Assistant and HACS contract.
- [ ] Git tag `2.1.0` created on the release commit after merge into `main`.
- [ ] GitHub release published with the summary below.

### Quality gates

- [x] `python -m ruff check .`
- [x] `python -m ruff format --check .`
- [x] `python -m mypy custom_components/firewalla_local`
- [x] `python -m pytest tests/ -v` (`319 passed`)
- [ ] Live smoke: install or upgrade through HACS and confirm setup plus one runtime refresh against a real box.

### What is in this release

**Access hardening (Phase 1)**

- 12 mutating services plus `get_runtime_inventory` are now registered as
  **admin-only** (13 total). `get_host_name_mapping` stays open by decision.
- Services are re-registered on setup so an upgraded gate can never be masked by
  a stale handler surviving a reload.
- Phase 2 extends the gated set to 18 services.

**Alarm telemetry and rule deletion (Phase 2)**

- New `binary_sensor.alarm_active` and `sensor` for the active alarm count, both
  carrying `active_count` / `archived_count` / `pending_count` and a bounded
  per-category summary. The init payload's alarm list is capped at 50, so
  `active_by_category_complete` tells you when that summary is partial rather
  than empty.
- Five alarm services: `get_alarms`, `archive_alarms`, `delete_alarms`,
  `mute_alarm`, and `unmute_alarm`. Deletes require explicit `confirm: true`.
- `mute_alarm` requires an explicit `scope_kind`, because omitting scope on the
  wire produces a box-wide silence.
- Alarm blocks are ordinary policy rules, so there is deliberately **no**
  `block_alarm` / `unblock_alarm` service; manage them through the rule surface.
- New `delete_rule` service to permanently remove a live policy rule.
- Diagnostics now redact alarm device identity, destinations, IPs, MACs, and
  coordinates while keeping `type`, `state`, and `aid` diagnosable.

**Surface visibility (Phase 3)**

- `binary_sensor.network` now exposes `top_talkers`: the top 5 hosts per network
  ranked by combined download and upload. Derived from the init payload at no
  extra request cost. WAN networks report an empty list because the box assigns
  no hosts to a WAN interface.
- `get_runtime_inventory` gained `devices_total`, `devices_online`, and
  `devices_offline` in its summary.
- The online/offline definition now lives in one place (`utils/host_activity.py`)
  and is shared by the entities and the inventory summary, so the two can no
  longer disagree.
- Documentation: a "Rich data lives in entity attributes" section explaining how
  to find the detail behind each entity, a "Using your data across Home
  Assistant" section with REST examples, and the hub framing in the README.

### Breaking-change note (read before upgrading)

This release **tightens access to the service surface**. A **non-admin signed-in
user** can no longer call the 13 admin-gated services directly (18 after Phase 2
service additions). Specifically, a call made by a signed-in non-admin user now
raises `Unauthorized`.

**Automations and scripts are unaffected.** Home Assistant only enforces the
admin check when a call carries a user context, so automation, script, and
integration calls keep working unchanged. This was asserted in tests rather than
assumed.

**Entity control is not gated.** Rule switch entities call the manager directly,
not a service, so anyone with entity control can still toggle an exposed switch.
The admin gate hardens the service surface, not the entity surface. The real
access-control boundary remains which options the user selects (rule switches,
watched devices, SSIDs, and so on).

If a dashboard button or script currently invokes an admin-gated service under a
non-admin account, either call it from an admin account or switch to the
equivalent entity.

### Draft release summary

Firewalla Local 2.1.0 hardens service access, adds Firewalla alarm telemetry, and
makes the integration's rich data easier to find and use.

- **Access hardening:** mutating services and the runtime inventory are now
  admin-only. Automations and scripts are unaffected; only direct calls from a
  signed-in non-admin user are rejected.
- **Alarms:** new alarm-active and active-alarm-count entities with bounded
  category summaries, five new alarm services (query, archive, delete, mute,
  unmute) with confirmation on irreversible deletes, and diagnostics redaction
  that keeps alarms diagnosable without leaking device or location detail.
- **Rules:** a new `delete_rule` service to permanently remove a live policy
  rule.
- **Visibility:** per-network top talkers, device counts in the runtime
  inventory summary, and documentation explaining where each entity's detailed
  attributes live and how to read them over REST.

No configuration changes are required.

### Risk notes and defers

- The admin gate targets the service surface only; exposed control entities
  remain operable by any user with entity control. Documented rather than
  implied.
- `top_talkers` is a summary of the current snapshot, not a time-series. It is
  empty on WAN by design and omits hosts with no recorded traffic.
- `active_by_category` is a lower bound when the box returns more than 50 active
  alarms; check `active_by_category_complete`.
- `TL-` target list names remain unresolvable locally because Firewalla sources
  them from cloud `mspData.targetlists`.
- Alarm archive, mute, and block are effectively one-way on the alarm record —
  only delete removes it. There is no un-archive command.
- **MCP/LLM tool exposure was deferred.** It is planned in
  `plans/in-process/FIREWALLA_LOCAL_MCP_CAPABILITIES_IN-PROCESS.md` and is
  version-gated at Home Assistant 2026.10. This release does not include it and
  does not raise the integration's minimum Home Assistant version.
- Rollback path is a revert of the release commits plus a re-tag, per the
  repository rule of publishing a new patch instead of rewriting a shipped tag.