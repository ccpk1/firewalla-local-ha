# Initiative: AP7 Wireless Network Toggle (Feature Request #21)

## 1. Initiative snapshot

- **Source:** `ccpk1/firewalla-local-ha` issue #21 — *"[Feature]: Wireless Network Toggle for AP7"* (label: `enhancement`).
- **Requested capability:** A Home Assistant frontend switch to enable/disable a wireless network (e.g. guest SSID) on a Firewalla AP7D / AP7C, plus optional wireless status/diagnostics sensors.
- **Current state:** The reporter (`squirtbrnr`) has now submitted the requested diagnostic inventory (two files), which is the first concrete evidence we have for the wireless mapping. This plan captures that evidence and turns it into an executable reverse-engineering + buildout path.
- **Branch context:** `release-1.2.0`; manifest version `1.2.0-alpha.4`.
- **Latest thread state (2026-08-05):** The maintainer (`ccpk1`) posted a follow-up question to the reporter asking whether they used the **"Sync Runtime"** button and waited before the second download, since runtime data is polled on an interval and only updates on the next polling cycle or a forced sync. This caveat is central to interpreting the two submitted files (see §3).
- **Architecture clarification (2026-08-05):** **AP7 is the name of the access points**, not the Firewalla box. The AP7 access points require a Firewalla device (here a **Firewalla Purple**, `model: "purple"`) for control. The working theory is that since the AP7 requires a Firewalla device, some of the AP7 config must be stored on the Firewalla. The Firewalla model itself does not matter — if you have a Firewalla device, you can add AP7 access points.

## 2. Scope and non-goals

**In scope**
- Locate and confirm where wireless/SSID broadcast state lives in the Firewalla local runtime.
- Establish a read path (and, if confirmed, a write path) for enabling/disabling a wireless network.
- Surface the state as a Home Assistant switch (and, where evidence supports it, status/diagnostics sensors).
- Keep everything translation-ready and quality-scale-tracked.

**Non-goals (until evidence exists)**
- Controlling non-wireless AP7 hardware settings (LEDs, bands, channels) — out of scope unless the inventory proves a clean contract.
- Building any switch/sensor surface from guessed fields. No surface is created until the mapping is confirmed.
- Any cloud-only control path; this integration is local-first.

## 3. Open questions / external dependencies

- **Where does wireless config live?** The submitted diagnostics contain *only rules* for the guest network, with **no SSID broadcast / config parameters** visible. The AP7 access points appear as hosts (`connection_type=ap`, `host_device_type=ap`) but with no wireless config. This *suggests* the wireless config is **not** in the current normalized runtime snapshot — **but this is not yet conclusive** (see the sync caveat below).
- **Sync caveat (critical):** The two submitted files are **byte-for-byte identical** (same MD5, zero diff). The maintainer's follow-up question asks whether the reporter forced a **"Sync Runtime"** before the second download. Because runtime data is polled on an interval, a second download taken without a forced sync can capture a **stale snapshot** — meaning the identical files may reflect a capture-timing problem, **not** the absence of wireless state. The "identical files" finding is therefore **inconclusive** until the reporter confirms they synced before the second capture.
- **Diagnostic coverage gap:** The diagnostic export captures only the **normalized** `FirewallaRuntimeSnapshot`. It does **not** include the raw init payload, `networkProfiles`, or `networkConfig` — the very keys where wireless config might live. To inspect wireless state, we need the raw payload (via `utils/pull_runtime.py` or an extended diagnostic), not just the normalized snapshot.
- **Is the wireless state readable via the same local `encipher/message` endpoint, or a different one?** Unknown — must be confirmed by capture, not assumed.
- **Is there a write contract?** Unknown. Enabling/disabling an SSID may be a distinct mutation (not a rule update).
- **Do the two submitted files differ at all?** The reporter states a file compare showed them *identical*. This has been re-verified against the raw files: they are byte-identical (same MD5, zero diff). The reporter sanitized them for PII, but the byte-identical result is independent of redaction.
- **AP7 model variance:** AP7D vs AP7C may expose different wireless surfaces. The reporter has 5 AP7 access points (UPSTAIRS-AP, MAIN-FLOOR-AP, KITCHEN-AP, GARAGE-AP, BASEMENT-AP), all on the "Universe" network.

## 4. Phase summary table

| Phase | Goal | Key output |
| --- | --- | --- |
| 1 | Inventory evidence review | Confirmed mapping (or confirmed absence) of wireless state in current snapshot |
| 2 | Protocol discovery | Confirmed read/write contract for wireless state |
| 3 | Runtime model + read surface | Normalized wireless model + read-only sensors/report |
| 4 | Write surface + switch | Confirmed enable/disable switch + tests + quality-scale update |

## 5. Per-phase details

### Phase 1 — Inventory evidence review

- [x] Download and store the two submitted diagnostics under `.artifacts/` following the established artifact conventions (see `docs/REVERSE_ENGINEERING_WORKFLOW.md` → "Artifact conventions"). Stored in `.artifacts/ap7-wireless-discovery/` with the reporter's original filenames preserved (`base_line_guest_wifi_off.json`, `guest_wifi_on.json`).
- [x] Re-run a structural diff on the raw files to confirm whether they are truly identical. **Result:** both files are byte-for-byte identical (same MD5 `22b5055f...`, zero diff, 9,657 lines each).
- [x] Search both files for wireless-relevant keys: `ssid`, `wifi`, `wireless`, `ap7`, `guest`, `broadcast`, `radio`, `band`, `channel`, `networkProfiles`, `networkConfig`. **Result:** zero wireless/SSID keys found; `guest` appears only as firewall policy rules scoped to the "Universe Guest" network; the 5 AP7 access points appear as hosts (`connection_type=ap`) with no wireless config.
- [x] Map findings against the current snapshot model (`FirewallaRuntimeSnapshot` in `models.py`) and the existing `networkProfiles` / `networkConfig` parsing in `api/client.py` and `managers/integration_manager.py`. **Result:** the diagnostic captures only the normalized snapshot; the raw `networkProfiles`/`networkConfig` payload is not exported, so wireless state (if any) is not visible in the diagnostic.
- [x] Record the finding in a supporting note (`FIREWALLA_LOCAL_AP7_WIRELESS_TOGGLE_SUP_INVENTORY.md`): which fields are present, which are absent, and the confidence level.
- [ ] **Blocked on reporter:** Confirm whether the reporter used the **"Sync Runtime"** button and waited before the second download. Until confirmed, the identical-files result is inconclusive (may be a stale snapshot rather than absence of wireless state).
- [x] **Simple capture path (implemented):** Extended the integration diagnostic (`diagnostics.py`) to include the **raw init payload** (`runtime_init_payload`, redacted) alongside the normalized snapshot. This means the reporter can now get a full runtime pull with the **same diagnostic download they already know how to do** — no repo, venv, or CLI required. The raw payload includes `networkProfiles` / `networkConfig`, where wireless config may live.
- [x] **Best-effort init payload redaction (implemented):** Added `helpers/init_payload_redaction.py` which walks the raw init payload and redacts known sensitive keys plus common sensitive value patterns (JWTs, MAC addresses, IPv4 addresses, emails). Verified against a real full-pull diagnostic: **0 emails, 0 MACs, 0 IPs, 0 JWTs remain** after redaction. Covered fields include `jwt`, `ddnsToken`, `btMac`, `cpuid`, `publicIp`, `ddns`, `localDomainSuffix`, host identifying fields, WireGuard peer keys/names, the AP controller mesh key/SSID, and MAC/IP/email patterns in both values and dict keys.
- [x] **Exclusion of non-wireless sections (implemented):** To preserve traceability while reducing sensitivity, large non-wireless sections are now **dropped entirely** from the export rather than redacted. Excluded: `userTags`, `internetSpeedtestResults`, `systemFlows`, `last60`/`last30`/`newLast24`/`last12Months`, `latestAllStateEvents`/`latestStateEventsError`/`networkMonitorEvents`, `customizedCategories`, `deviceTags`/`tags`, `sysMetrics`, `monthlyDataUsage*`, `networkMetrics`, `newAlarms`. Kept (wireless-relevant): `networkConfig` (the AP controller `apc`/`mesh`/`ssid` core), `hosts` (kept because an AP7 environment populates `ssidTags`), `policyRules`, `exceptionRules`, `appConfs`, `policy`, `runtimeFeatures`, `runtimeDynamicFeatures`, `apController`. Also added internal-domain redaction (`*.ccpk.us` and subdomains) in the retained sections. Verified: personal names and internal domains are gone; size drops from ~930 KB to ~580 KB.
- [ ] **Safe transfer approach (proposed):** Because the raw payload is large and the redaction is best-effort, work with the reporter directly to provide the diagnostic files through a **private channel** (e.g. email or a private upload) rather than posting them publicly on the issue. This avoids any residual risk from unredacted data and removes the burden of manual review on the reporter.
- [ ] **Blocked on reporter (re-capture):** Ask the reporter to (1) hit **"Sync Runtime"**, wait a few seconds, (2) download the diagnostic, (3) make the wireless change in the app, (4) hit **"Sync Runtime"** again, wait, (5) download a second diagnostic, and post both (or send privately). The new `runtime_init_payload` field will expose the raw wireless config for comparison.
- [ ] **Decision gate:** If wireless config is genuinely absent from the raw payload (and the sync caveat is resolved), proceed to Phase 2. If it is present but unmodeled, skip to Phase 3. If the sync caveat is unresolved, request a re-capture from the reporter before concluding absence.

### Phase 2 — Protocol discovery

- [ ] Identify which local endpoint(s) the integration currently polls (`async_get_runtime_init_payload` in `api/client.py`) and confirm whether wireless state is part of that payload.
- [ ] If absent, use the reverse-engineering workflow (`docs/REVERSE_ENGINEERING_WORKFLOW.md`) to capture the wireless read path: pair/authenticate, then probe candidate local endpoints for SSID/broadcast state.
- [ ] Confirm the write contract for enabling/disabling a wireless network (payload shape, target identifier, auth scope). Do **not** invent it — capture it.
- [ ] Record the confirmed read/write contract in the supporting note with a field-mapping table (published field → local raw field → normalized field → HA-derived field → confidence/evidence).
- [ ] **Decision gate:** Only proceed to Phase 3 once the read path is confirmed; only proceed to Phase 4 once the write path is confirmed.

### Phase 3 — Runtime model + read surface

- [ ] Extend `FirewallaRuntimeSnapshot` (or add a dedicated wireless model) with the confirmed wireless fields.
- [ ] Add parsing in `api/client.py` (and/or the owning manager) so the coordinator carries normalized wireless state.
- [ ] Extend `helpers/runtime_inventory.py` to report wireless state in `get_runtime_inventory` (structured + markdown).
- [ ] Add read-only sensors (e.g. SSID broadcast status, connected-client counts) **only** where the inventory proves the fields.
- [ ] Add tests in `tests/components/firewalla_local/` covering normalization and inventory reporting.
- [ ] Update `translations/en.json` for any new entity names/attributes.
- [ ] Update `quality_scale.yaml` only for behavior that actually exists.

### Phase 4 — Write surface + switch

- [ ] Add a confirmed write path in `api/client.py` for enabling/disabling a wireless network.
- [ ] Add a `switch` platform entity (or extend the existing switch platform) backed by the confirmed contract, using the existing manager-owned optimistic-update pattern.
- [ ] Wire the switch into the options flow / selection surface only if user-selectable networks are confirmed.
- [ ] Add tests for the switch (state read, toggle, optimistic update, failure handling).
- [ ] Update `services.yaml` / `services.py` only if a service (not just a switch) is warranted.
- [ ] Update `quality_scale.yaml` and release notes for the new surface.

## 6. Validation strategy

- Run `python -m ruff check .` and `python -m ruff format .`.
- Run `python -m mypy custom_components/firewalla_local`.
- Run `python -m pytest tests/ -v` (focused scopes allowed during iteration; final report states what was/wasn't run).
- Confirm no root-level module drift (wireless logic must live in an owned manager/helper, per `FIREWALLA_LOCAL_RUNTIME_BUILDOUT_SUP_PHASE3B_BUILDER_HANDOFF.md`).
- Confirm translations are regenerated and quality-scale is honest (`todo`/`exempt` until behavior exists).

## 7. References

- Issue: `ccpk1/firewalla-local-ha#21` — Wireless Network Toggle for AP7.
- Submitted diagnostics: `base_line_guest_wifi_off.json`, `guest_wifi_on.json` (attached to issue #21).
- `docs/REVERSE_ENGINEERING_WORKFLOW.md` — field-mapping table and capture workflow.
- `custom_components/firewalla_local/api/client.py` — `networkProfiles` / `networkConfig` parsing and runtime init payload.
- `custom_components/firewalla_local/models.py` — `FirewallaRuntimeSnapshot`.
- `custom_components/firewalla_local/helpers/runtime_inventory.py` — inventory report builder.
- `custom_components/firewalla_local/managers/integration_manager.py` — network lookup/segment view.
- `custom_components/firewalla_local/quality_scale.yaml` — quality tracking.
