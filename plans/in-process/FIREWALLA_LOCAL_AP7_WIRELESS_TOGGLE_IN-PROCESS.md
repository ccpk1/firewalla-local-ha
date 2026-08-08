# Initiative: AP7 Wireless Network Toggle (Feature Request #21)

## 1. Initiative snapshot

- **Source:** `ccpk1/firewalla-local-ha` issue #21 — *"[Feature]: Wireless Network Toggle for AP7"* (label: `enhancement`).
- **Requested capability:** A Home Assistant frontend switch to enable/disable a wireless network (e.g. guest SSID) on a Firewalla AP7D / AP7C, plus optional wireless status/diagnostics sensors.
- **Current state (2026-08-07):** The reporter (`squirtbrnr`) submitted two **comprehensive** diagnostic captures (`ap7_wifi_on.json`, `ap7_wifi_off.json`) using the extended diagnostic. These **confirmed** the wireless config location and the toggle control. See §3 and the supporting note.
- **Branch context:** `release-1.2.0`; manifest version `1.2.0-alpha.6`.
- **Architecture clarification (2026-08-05):** **AP7 is the name of the access points**, not the Firewalla box. The AP7 access points require a Firewalla device (here a **Firewalla Purple**, `model: "purple"`) for control. The Firewalla model itself does not matter — if you have a Firewalla device, you can add AP7 access points.
- **Correction (2026-08-07):** The earlier assumption that the user had **5 Firewalla AP7s** was **wrong**. Those 5 APs were **Aruba InstantOn AP22** (managed outside Firewalla, now removed from config). The user actually has **2 Firewalla AP7s**: "Main Floor" and "Upstairs" (both `fwap-D`).

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

### Confirmed findings (2026-08-07)

- **Wireless config location (CONFIRMED):** The wireless config lives in `networkConfig.apc` (the AP controller section) of the raw init payload. This is **not** in the normalized `FirewallaRuntimeSnapshot` — it requires the raw payload.
- **Toggle control (CONFIRMED):** The **only** difference between wifi-on and wifi-off is the `paused` field on one SSID profile: `networkConfig.apc.profile.<uuid>/paused: true` when off, absent when on. This is the wireless toggle.
- **AP7 device model (CONFIRMED):** The user has **2 Firewalla AP7s** (`fwap-D`): "Main Floor" (`20:6D:31:71:1D:D0` @ 192.168.1.3) and "Upstairs" (`20:6D:31:71:55:5C` @ 192.168.1.4), connected via `wg_ap` mesh backhaul peers.
- **Wireless config structure (CONFIRMED):** `networkConfig.apc` contains `assets` (per-AP config), `assets_template.ap_default` (wifiNetworks → ssidProfiles → VLANs, mesh), `profile` (per-SSID: ssid, key, band, encryption, wpa3, paused), and `globalSysConfig`. The user has **3 SSID profiles** on `br0` (main), `br1`/VLAN 100 (guest — the toggled one), and `br2`/VLAN 200.

### Open questions / assumptions

- **Write contract (UNKNOWN — the key assumption):** We have confirmed the **read** path (the `paused` field) but **not** the **write** command. The existing mutations use `cmd` (`policy:update`) or `set` (`policy`) message types. The wireless config is under `networkConfig`, so the write command is unknown. This is the primary assumption for alpha.7 (see the alpha.7 plan).
- **SSID display names (REDACTED in captures):** The actual SSID strings are redacted in the diagnostic (our redaction masks the `ssid` key). The SSID **profile UUIDs** are stable identifiers we can use for selection regardless of display name. At runtime (unredacted), we can read the actual SSID names.
- **AP7 model variance:** AP7D vs AP7C may expose different wireless surfaces. The user has `fwap-D` units.
- **Safe transfer:** The raw payload is large and redaction is best-effort; consider a private channel for future captures.

## 4. Phase summary table

| Phase | Goal | Key output |
| --- | --- | --- |
| 1 | Inventory evidence review | **Complete** — wireless config located in `networkConfig.apc`; toggle = `paused` field |
| 2 | Protocol discovery | Confirm read/write contract (read confirmed; write is the key assumption) |
| 3 | Runtime model + read surface | Normalized wireless model + read-only sensors/report |
| 4 | Write surface + switch | Enable/disable switch + tests + quality-scale update |

## 5. Per-phase details

### Phase 1 — Inventory evidence review

- [x] Download and store the two submitted diagnostics under `.artifacts/` following the established artifact conventions (see `docs/REVERSE_ENGINEERING_WORKFLOW.md` → "Artifact conventions"). Stored in `.artifacts/ap7-wireless-discovery/` with the reporter's original filenames preserved (`base_line_guest_wifi_off.json`, `guest_wifi_on.json`).
- [x] Re-run a structural diff on the raw files to confirm whether they are truly identical. **Result:** both files are byte-for-byte identical (same MD5 `22b5055f...`, zero diff, 9,657 lines each). **Note:** this was later explained — the reporter forgot to sync before the second capture.
- [x] Search both files for wireless-relevant keys. **Result:** zero wireless/SSID keys found in the normalized snapshot; the raw `networkConfig`/`networkProfiles` was not yet exported.
- [x] Map findings against the current snapshot model. **Result:** the diagnostic captured only the normalized snapshot; the raw payload was not exported.
- [x] **Simple capture path (implemented):** Extended the integration diagnostic (`diagnostics.py`) to include the **raw init payload** (`runtime_init_payload`, redacted) alongside the normalized snapshot.
- [x] **Best-effort init payload redaction (implemented):** Added `helpers/init_payload_redaction.py` (see supporting note for details).
- [x] **Exclusion of non-wireless sections (implemented):** Large non-wireless sections are dropped from the export (see supporting note for details).
- [x] **Comprehensive captures received (2026-08-07):** The reporter submitted `ap7_wifi_on.json` and `ap7_wifi_off.json` with the extended diagnostic. **This confirmed the wireless config location and the toggle control** (see §3 and supporting note).
- [x] **Correction applied (2026-08-07):** The earlier "5 AP7" assumption was wrong — those were Aruba InstantOn AP22. The user has **2 Firewalla AP7s**.
- [ ] **Safe transfer approach (proposed):** Because the raw payload is large and the redaction is best-effort, work with the reporter directly to provide the diagnostic files through a **private channel** (e.g. email or a private upload) rather than posting them publicly on the issue.
- [x] **Decision gate (Phase 1 complete):** Wireless config is confirmed present in the raw `networkConfig.apc` payload. Proceed to Phase 2 (protocol discovery) and the alpha.7 implementation.

### Phase 2 — Protocol discovery

- [x] **Read path confirmed:** The wireless config is part of the raw init payload (`networkConfig.apc`), fetched via `async_get_runtime_init_payload` in `api/client.py`. No separate endpoint needed for reading.
- [ ] **Write contract (UNKNOWN — key assumption):** Confirm the write command for toggling `paused` on an SSID profile. This is the primary unknown for alpha.7. See the alpha.7 implementation plan for the assumption and alternative patterns.
- [ ] Record the confirmed read/write contract in the supporting note with a field-mapping table.
- [ ] **Decision gate:** Proceed to Phase 3/alpha.7 with the confirmed read path and the assumed write path (PoC risk accepted).

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
- **alpha.7 implementation plan:** `plans/in-process/FIREWALLA_LOCAL_AP7_WIRELESS_TOGGLE_ALPHA7_IN-PROCESS.md`.
- Submitted diagnostics: `base_line_guest_wifi_off.json`, `guest_wifi_on.json`, `ap7_wifi_on.json`, `ap7_wifi_off.json` (attached to issue #21).
- `docs/REVERSE_ENGINEERING_WORKFLOW.md` — field-mapping table and capture workflow.
- `custom_components/firewalla_local/api/client.py` — `networkProfiles` / `networkConfig` parsing and runtime init payload.
- `custom_components/firewalla_local/models.py` — `FirewallaRuntimeSnapshot`.
- `custom_components/firewalla_local/helpers/runtime_inventory.py` — inventory report builder.
- `custom_components/firewalla_local/managers/integration_manager.py` — network lookup/segment view.
- `custom_components/firewalla_local/quality_scale.yaml` — quality tracking.
