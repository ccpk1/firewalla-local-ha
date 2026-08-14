# Initiative: AP7 Wireless Toggle — alpha.7 Implementation Plan

## 1. Initiative snapshot

- **Source:** `ccpk1/firewalla-local-ha` issue #21 — *"[Feature]: Wireless Network Toggle for AP7"*.
- **Goal for alpha.7:** Deliver a working, testable wireless control surface for the AP7 access points, accepting PoC-level risk on the unconfirmed write contract.
- **Confirmed evidence (2026-08-07):** Wireless config lives in `networkConfig.apc`; the toggle is the `paused` field on an SSID profile. Read path confirmed; write path assumed.
- **Branch context:** `release-1.2.0`; current version `1.2.0-alpha.6` → target `1.2.0-alpha.7`.

## 2. Scope and non-goals

**In scope (alpha.7)**
- Read-only wireless status surface (SSID profiles, per-AP status) — zero risk, confirmed read path.
- A **testable write path** for toggling `paused` on an SSID profile — the core request, with the write contract as an explicit assumption.
- A small set of **services/actions** (not full switch entities) so the user can test the write path quickly.

**Non-goals (alpha.7)**
- Full switch-platform entities with options-flow selection (deferred until the write contract is confirmed).
- Channel/band control, mesh key/SSID changes, `globalSysConfig` changes (riskier, unconfirmed).
- Per-AP `pauseWifi`, LED control (deferred — see §7).

## 3. Key assumption: the write contract

### The problem
We have **confirmed** the read path (the `paused` field in `networkConfig.apc.profile.<uuid>`). We have **not** confirmed the **write command** — the exact Encipher message that tells the Firewalla to set `paused` on a profile.

### Existing mutation patterns (what we can leverage)
The codebase already has two mutation patterns in `api/client.py`:

| Pattern | Message type | Item | Example |
| --- | --- | --- | --- |
| Rule update | `cmd` | `policy:update` | `async_update_rule_control_only` |
| Host policy set | `set` | `policy` | `async_set_host_policy` |

The wireless config is under `networkConfig`, which is neither `policy` (rules) nor a host. So the write command is genuinely unknown.

### The chosen assumption (primary path)
**Assumption A — a `set` command targeting the AP controller config.** We assume the write is a `set` message with an item that addresses the AP controller (`apc`) or the network config, carrying the full `apc` payload (or the specific profile) with `paused` set. This mirrors `async_set_host_policy` (a `set` with a `value` payload).

**Why this was chosen over the alternatives:**
- The `set` message type is the natural fit for "write a config value" (vs. `cmd` which is for actions like speed-test/wake).
- The `apc` config is a stateful config blob, not an action — `set` is the semantically correct transport.
- It's the closest analog to the existing `async_set_host_policy` which writes a config payload.

### Alternative patterns (for fallback testing)
- **Assumption B — a `cmd` message with a wireless-specific item** (e.g. `item: "apc"` or `item: "wifi"`). If `set` doesn't work, try `cmd`.
- **Assumption C — a `set` on `networkConfig`** with the full `networkConfig` payload (not just `apc`). More invasive but may be what the app sends.

### How to allow multiple testing paths (simple)
To let the user test multiple patterns without code changes, we'll make the write command **configurable**:
- Add a service field (or config option) that selects the write pattern: `set_apc`, `cmd_apc`, `set_networkconfig`.
- Default to Assumption A, but allow the user to try B or C via the service call.
- This is cheap (a string field) and lets us validate all three against the live box in one round.

## 4. Phase summary table

| Phase | Focus | Deliverable |
| --- | --- | --- |
| 1 | Read-only wireless surface | Normalized wireless model + read-only sensors/report |
| 2 | Testable write path (services) | 2-3 services to toggle `paused` with configurable write pattern |
| 3 | Validation + user test | Live test with the reporter, confirm the write contract |
| 4 | Promote to switch entities | Convert confirmed services into switch entities + options flow |

## 5. Per-phase details

### Phase 1 — Read-only wireless surface

- [ ] Add a normalized wireless model (SSID profiles + per-AP assets) derived from `networkConfig.apc` in `models.py`.
- [ ] Add parsing in `api/client.py` (or a new `managers/wireless_manager.py`) so the coordinator carries normalized wireless state.
- [ ] Extend `helpers/runtime_inventory.py` to report wireless state in `get_runtime_inventory` (structured + markdown).
- [ ] Add read-only sensors: per-SSID status (paused/enabled), per-AP status (name, model, channel, meshMode).
- [ ] Add tests in `tests/components/firewalla_local/` covering normalization and inventory reporting.
- [ ] Update `translations/en.json` for new entity names/attributes.
- [ ] Update `quality_scale.yaml` only for behavior that actually exists.

### Phase 2 — Testable write path (services)

- [ ] Add `async_set_ssid_paused(profile_uuid, paused, write_pattern)` to `api/client.py` — sends the mutation using the selected write pattern (default Assumption A).
- [ ] Add a `wireless_manager` method `async_set_ssid_paused(...)` that applies an optimistic update to the in-memory payload (mirrors `rule_manager`).
- [ ] Add 2-3 services in `services.py` / `services.yaml`:
  - `set_ssid_paused` (profile_uuid, paused, write_pattern) — the core toggle
  - `get_wireless_status` — returns the current wireless config (read-only, for verification)
  - (optional) `set_ap_pause_wifi` (ap_id, paused) — per-AP pause, if we want to test it
- [ ] Add tests for the services (state read, toggle, optimistic update, failure handling).
- [ ] Update `translations/en.json` for service names/descriptions.

### Phase 3 — Validation + user test

- [x] Release alpha.7 with the services.
- [x] Ask the reporter to test `set_ssid_paused` on the guest SSID (profile `f185dc47-...`).
- [x] All three write patterns tested; all rejected with code 500.
- [x] Read path (`get_wireless_status`) confirmed: returned 3 SSID profiles with
      real names ("Universe", "Universe Guest", "Universe IoT") and 2 AP7
      access points ("Main Floor", "Upstairs").
- [ ] **Write contract UNCONFIRMED** — requires packet capture of the app-to-box
      traffic. See the updated REVERSE_ENGINEERING_WORKFLOW.md for the protocol
      details and capture requirements.

### Phase 4 — Promote to switch entities

- [ ] **BLOCKED** on write contract — cannot promote until packet capture
      confirms the write command. See the next-capture section below for what
      to request from the reporter.

## 6. Validation strategy

- Run `python -m ruff check .` and `python -m ruff format .`.
- Run `python -m mypy custom_components/firewalla_local`.
- Run `python -m pytest tests/ -v` (focused scopes allowed during iteration; final report states what was/wasn't run).
- Confirm no root-level module drift (wireless logic must live in an owned manager/helper).
- Confirm translations are regenerated and quality-scale is honest (`todo`/`exempt` until behavior exists).

## 7. Deferred items (with rationale)

- **Full switch entities (Phase 4):** Deferred until the write contract is confirmed. Building the full switch + options flow before confirming the write would be wasted effort if the write pattern is wrong.
- **Per-AP `pauseWifi`:** Directionally clear but not yet observed toggled in a capture. Deferred to keep alpha.7 focused; can be added once the SSID toggle is confirmed.
- **LED control:** Low risk but not the core request; deferred.
- **Channel/band control:** Riskier (could disrupt connectivity); deferred pending more evidence.
- **Mesh key/SSID changes:** Sensitive and not the toggle use case; deferred.

## 8. References

- Issue: `ccpk1/firewalla-local-ha#21`.
- Artifacts: `.artifacts/ap7-wireless-discovery/ap7_wifi_on.json`, `ap7_wifi_off.json`.
- `custom_components/firewalla_local/api/client.py` — mutation patterns (`async_set_host_policy`, `async_update_rule_control_only`).
- `custom_components/firewalla_local/managers/rule_manager.py` — optimistic-update pattern.
- `custom_components/firewalla_local/switch.py` — existing switch platform.
- `plans/in-process/FIREWALLA_LOCAL_AP7_WIRELESS_TOGGLE_SUP_INVENTORY.md` — evidence.

## 9. Expanded proposal: what is "leveraged" vs. what is AP7-unique

This section clarifies the boundary between reusing existing integration
concepts and adding AP7-specific surfaces. It answers: how does this fit with
the existing device / tracked-device model, and how do we guarantee zero impact
on users who only have a Firewalla (no AP7s)?

### 9.1 What we are NOT adding (reuse of existing concepts)

The following are **already supported** and will be **reused as-is**, not
duplicated:

| Existing concept | Where it lives today | How AP7 fits in |
| --- | --- | --- |
| **Devices / tracked devices** | `device_tracker.py`, host inventory (`hosts`) | AP7s are already hosts in the runtime payload. They appear as tracked devices today (e.g. "Main Floor", "Upstairs"). We do **not** create a parallel device model. |
| **Sensors** | `sensor.py` | Per-AP read-only attributes (channel, meshMode, model) surface as **attributes on the existing device tracker / sensor entities**, not new entity types. |
| **Switches** | `switch.py` | The SSID pause toggle, once the write contract is confirmed, becomes a **switch entity** following the existing `FirewallaSwitch` pattern. |
| **Services/actions** | `services.py` | `get_wireless_status` / `set_ssid_paused` are services, consistent with the existing service surface. |
| **Coordinator / manager pattern** | `coordinator.py`, `managers/` | `wireless_manager` follows the same manager pattern as `rule_manager`. |

**Key point:** AP7 support does **not** introduce a new entity platform or a new
device-tracking paradigm. It layers a small, optional read/write surface on top
of concepts that already exist.

### 9.2 What IS new / AP7-unique

Only these are genuinely new, and each is scoped to the `networkConfig.apc`
section that only exists when AP7s are present:

| New surface | What it is | Why it's AP7-unique |
| --- | --- | --- |
| **SSID profile model** | `FirewallaSsidProfile` (ssid, band, encryption, wpa3, paused, vlan, intf) | Derived from `networkConfig.apc.profile` — only present with AP7s. |
| **Access point model** | `FirewallaAccessPoint` (name, model, channel, meshMode, led, pauseWifi) | Derived from `networkConfig.apc.assets` — only present with AP7s. |
| **SSID pause switch** | A switch per SSID profile toggling `paused` | The core feature request; only meaningful when AP7s broadcast SSIDs. |
| **Wireless status service** | `get_wireless_status` returning the structured wireless view | Read-only verification surface for the wireless config. |

### 9.3 How it fits with devices / tracked devices

- The **AP7 access points are already tracked devices** (they are hosts with
  MACs in the runtime payload). We do **not** create separate "AP" entities.
- The **SSID profiles are NOT devices** — they are wireless network configs.
  Each SSID becomes a **switch** (pause/resume), not a device.
- The **wireless manager** reads from the same raw init payload the coordinator
  already holds; it does not add a new polling loop or a new connection.

### 9.4 Guaranteeing zero impact on non-AP7 users

- **Conditional presence:** `networkConfig.apc` only exists in the raw payload
  when AP7s are present. If the section is absent, `wireless_manager` reports an
  empty surface and no wireless entities/services are created.
- **No new polling:** the wireless manager reads from the existing coordinator
  refresh; it adds no network traffic.
- **No entity churn:** non-AP7 users see no new entities, no new services in
  their UI, and no change to existing device/sensor/switch behavior.
- **Graceful degradation:** if the section is present but malformed, the manager
  returns an empty surface rather than raising, so a partial/odd payload cannot
  break setup.
- **Feature-gated services:** `set_ssid_paused` validates the profile exists and
  raises a clear `ServiceValidationError` if the target SSID is not present —
  it cannot affect a non-AP7 setup because there are no profiles to target.

### 9.5 Summary table

| Concern | Leveraged (existing) | New (AP7-unique) |
| --- | --- | --- |
| Device tracking | AP7s are already tracked devices | — |
| Read-only status | sensor attributes | SSID profile + AP model |
| Control surface | switch platform pattern | SSID pause switch |
| Services | service pattern | get_wireless_status, set_ssid_paused |
| Data source | existing coordinator payload | `networkConfig.apc` parsing |
| Non-AP7 impact | — | none (conditional presence) |
