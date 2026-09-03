# Initiative: AP7 Wireless — Confirmed Write Contract, Capture Tool Fix, and Watched-Device WiFi Attributes

## 1. Initiative snapshot

- **Source:** `ccpk1/firewalla-local-ha` issue #21 — *"[Feature]: Wireless Network Toggle for AP7"*.
- **Branch:** `ccpk1/issue21-wireless-write` (created 2026-09-03).
- **Status:** The write contract is now **CONFIRMED** from a packet capture submitted by the reporter on 2026-09-03. This plan covers the three workstreams the maintainer approved for drafting:
  1. Fix the capture tool bugs the reporter had to patch manually.
  2. Rework the wireless toggle write to match the confirmed contract.
  3. Surface WiFi attributes on the watched-device binary sensors.
- **Evidence:** `.tmp/wifi_toggle_capture_20260903/analysis.json` + safe report zip. Supporting note: `plans/in-process/FIREWALLA_LOCAL_AP7_WIRELESS_TOGGLE_SUP_INVENTORY.md` §7.

## 2. Confirmed write contract (from capture)

The app sends a `set` message with `item: "networkConfig"` carrying the **full** `networkConfig` object:

```
mtype: set
target: 0.0.0.0
data:
  COMMAND_TIMEOUT: 90
  LAN_ONLY: 1
  item: networkConfig
  value:
    config:
      <full networkConfig, 16 top-level keys>
      apc:
        assets: {...}
        assets_template: {...}
        profile:
          <uuid>: { ..., paused: true }   # or paused absent
        globalSysConfig: {...}
      ts: <epoch ms>
```

**Key differences from our current `set_networkconfig` implementation:**

1. `value` must be `{"config": {...}}` — the full `networkConfig` (16 keys), not `{"apc": apc_payload}`.
2. `config.ts` is required — a fresh epoch-ms timestamp.
3. `data` includes `COMMAND_TIMEOUT: 90` and `LAN_ONLY: 1`.
4. The `paused` mutation (true to pause, absent to resume) is **confirmed correct** — the only diff between the two captured writes.

**The write is accepted:** box responds `code=200` with `data: {"ncid": "<id>"}`.

### Why the wide write is correct (evidence)

The integration's other writes are **narrow** (single control point): `cmd` with
`item: policy:update` carrying only the rule, `set` with `item: host` carrying
only the name, etc. The `networkConfig` write is **unusually wide** — it carries
the entire config blob for a single SSID pause. This is not a guess; it is the
app's actual, confirmed behavior, verified from three independent sources:

1. **Packet capture (ground truth):** the app sent `value: {"config": <full
   16-key networkConfig>}`, `item: "networkConfig"`, `target: "0.0.0.0"` for
   the SSID pause toggle, and the box accepted it (`code 200`, `ncid` ack).
2. **Decompiled APK** `n03.java` (lines 478-479):
   ```java
   jSONObject2.put("config", jSONObject);   // value = {"config": <full networkConfig>}
   return t(jSONObject2, "networkConfig", "0.0.0.0");  // item=networkConfig, target=0.0.0.0
   ```
   This is the exact `value.config` + `item: networkConfig` envelope.
3. **Decompiled APK** `APSSIDProfileEditDialog.java` (save path): the app does
   `FWNetworkConfig.Companion.getCurrentConfig().duplicate()` — duplicates the
   **entire** config — mutates one profile's `paused`, then saves the whole
   thing back via the networkConfig write.

So the wide write is the app's design: it always sends the full `networkConfig`
for any SSID profile change. The integration must mirror this to be accepted.

## 3. Workstream 1 — Fix the capture tool

**Files:** `tools/support/capture_firewalla_packets.py`

**Bugs (confirmed in source):**

| Location | Bug | Fix |
| --- | --- | --- |
| Lines 401, 487 | `except ValueError, TypeError, json.JSONDecodeError:` — Python 2 syntax, `SyntaxError` on Python 3 | `except (ValueError, TypeError, json.JSONDecodeError):` |
| Lines 647, 959, 1410 | `datetime.UTC` — `AttributeError` (only `from datetime import datetime` imported) | `from datetime import datetime, timezone`; use `timezone.utc` |

**Also consider:**
- The `analysis.json` export produced a **trailing-comma JSON error** (we had to regex-clean it before parsing). Check the JSON serializer in the decode path and fix the trailing-comma emission.
- The reporter noted the analysis contained **unredacted public/private keys** (WiFi password, VPN profile keys). Review the redaction coverage in the decode path to ensure credential fields (`key`, `publicKey`, `privateKey`, mesh `key`, etc.) are redacted in `--redacted-report` mode.

**Validation:** run the tool's `--decode` path against the submitted pcap/key (or a synthetic fixture) and confirm it parses clean JSON with no trailing commas and redacts credential fields.

### 3.1 Ongoing syntax check (regression guard)

The two capture-tool bugs were **recent regressions** (introduced 2026-07-20/21)
that slipped through because the tool has no automated syntax check. To prevent
recurrence:

- Add a **compile check** for the capture tool to the test suite:
  `python -m py_compile tools/support/capture_firewalla_packets.py` (or a
  `compileall` step) so any future `SyntaxError`/import regression fails CI.
- Add a **runtime smoke test** that imports the module and exercises the
  `--decode` path against a small synthetic fixture (or the submitted
  analysis), asserting clean JSON output with no trailing commas.
- Wire both into the existing test/validation commands so they run on every
  change, not just when the tool is used manually.

## 4. Workstream 2 — Rework the wireless toggle write

**Files:**
- `custom_components/firewalla_local/api/client.py` — `async_set_ssid_paused`
- `custom_components/firewalla_local/managers/wireless_manager.py` — `_build_apc_with_paused`, `async_set_ssid_paused`
- `custom_components/firewalla_local/const.py` — write-pattern constants
- `tests/components/firewalla_local/test_services.py` — update tests

**Changes:**

1. **`wireless_manager`:** add a method to build the **full `networkConfig`** payload (not just `apc`) with the target profile's `paused` set/cleared, plus a fresh `ts`. The manager already holds the raw payload (`_last_payload`), so it can deep-copy `networkConfig`, apply the `paused` mutation to `networkConfig.apc.profile.<uuid>`, and set `networkConfig.ts = int(time.time() * 1000)`.

2. **`client.async_set_ssid_paused`:** change the `set_networkconfig` pattern to send:
   ```python
   data = {
       "COMMAND_TIMEOUT": 90,
       "LAN_ONLY": 1,
       _COMMAND_ITEM_KEY: "networkConfig",
       _COMMAND_VALUE_KEY: {"config": full_network_config},
   }
   ```
   Keep the `set_apc` and `cmd_apc` patterns for now (they're harmless and may be useful for comparison), but the **default** becomes the corrected `set_networkconfig`.

3. **`const.py`:** update the write-pattern constants/descriptions to reflect that `set_networkconfig` is now the confirmed pattern.

4. **Tests:** update `test_services.py` to assert the new payload shape (full `networkConfig` wrapped in `value.config`, `ts` present, `COMMAND_TIMEOUT`/`LAN_ONLY` present). Keep the existing tests for the other patterns.

**Validation:** `python -m ruff check .`, `python -m ruff format .`, `python -m mypy custom_components/firewalla_local`, `python -m pytest tests/ -v`.

## 5. Workstream 3 — Surface WiFi attributes on watched devices

**Files:**
- `custom_components/firewalla_local/models.py` — extend `FirewallaHostRuntime` (or add a wireless-connection model)
- `custom_components/firewalla_local/managers/wireless_manager.py` — parse `switchTopology` into per-MAC wireless connection info
- `custom_components/firewalla_local/binary_sensor.py` — `FirewallaWatchedDeviceBinarySensor.extra_state_attributes`
- `custom_components/firewalla_local/const.py` — new `ATTR_WATCHED_DEVICE_*` constants
- `custom_components/firewalla_local/translations/en.json` — attribute names
- `tests/components/firewalla_local/` — tests

**Data source:** the `switchTopology` section of the init response (already fetched during init — no new polling). Each client node has:
- `connectionType: wireless` vs `wired`
- `ssid` (which SSID)
- `band` (2g/5g)
- `parent_port` (which AP radio, e.g. `ath0`/`ath1`)
- `rssi` (signal strength)
- `type: device` vs `ap`

**Proposed attributes on the watched-device binary sensor:**
- `wifi_ssid` — SSID the device is on (or `None` if wired)
- `wifi_band` — 2g/5g/6g
- `wifi_rssi` — signal strength
- `wifi_ap` — resolved AP name from `parent_port` (via `networkConfig.apc.assets`)

**Design decisions (see §7 for the AP/device-count decisions):**
- Surface on the **watched-device binary sensor** (connectivity surface), not the device tracker (presence surface). The watched-device entity already carries `connection_type`/`network_name`, so WiFi attrs are a natural extension.
- The data is a point-in-time snapshot from the init response (not a live stream), so attrs reflect the last coordinator refresh.

**Validation:** same as Workstream 2.

## 6. Sequencing

1. Workstream 1 (capture tool + syntax-check regression guard) — independent, unblocks future captures.
2. Workstream 2 (write contract) — the core fix; needs a live retest with the reporter.
3. Workstream 3 (WiFi attrs) — independent of 2; can proceed in parallel or after.

## 7. Decisions needed — AP devices and client-count sensors

These are **deferred** pending maintainer decision. The plan does not implement them yet.

### Decision A — Should APs become real HA devices?

**Context:** APs are physical devices with their own MAC (`20:6D:31:71:1D:D0` "Main Floor", `20:6D:31:71:55:5C` "Upstairs"), model (`fwap-D`), and config (`sysConfig`: channels, LED, meshMode, pauseWifi). The `switchTopology` data gives each AP as a `type: ap` node with its clients as children.

**Options:**
- **A1 — Create AP devices in the device registry** (keyed by AP MAC), with a new sensor platform for per-AP entities (client count, channel, LED). Most natural fit; APs are distinct physical devices.
- **A2 — Keep APs as attributes on the existing box device** (no new devices). Lower effort, but loses the "AP is a physical device" semantics and makes per-AP entities awkward.
- **A3 — Defer entirely** until the toggle write is confirmed and shipped.

**Considerations:**
- APs already appear as hosts in the runtime (`wg_peer` with `intf=wg_ap`). Creating registry devices must avoid collision with any host-based device trackers.
- The `switchTopology` distinguishes `type: ap` from `type: device`, so APs can be cleanly identified.
- Non-AP7 users: no `networkConfig.apc` → no AP devices → zero impact.

### Decision B — Client-count sensors

**Context:** `switchTopology` gives each AP's children (clients). A per-AP client-count sensor is a natural, high-value surface.

**Options:**
- **B1 — Per-AP client-count sensor** (one sensor per AP device, from `switchTopology` children count). Natural if A1 is chosen.
- **B2 — Aggregate client-count on the box device** (total wireless clients). Simpler, but less useful for coverage monitoring.
- **B3 — Defer** until A is decided.

### Decision C — Wireless client presence

**Context:** "is this device on WiFi or wired, and on which AP/SSID" is a connectivity fact.

**Options:**
- **C1 — Surface as attributes on the watched-device binary sensor** (consistent with Workstream 3). Recommended.
- **C2 — Surface on the device tracker** (presence entity). Not recommended — muddies the presence-focused entity.

### Recommendation

- **A1** (APs as real devices) — the natural fit, and we have enough data. Sequence after the toggle write is confirmed.
- **B1** (per-AP client-count sensors) — pairs with A1.
- **C1** (watched-device attributes) — consistent with Workstream 3.

## 8. Per-SSID entities (binary sensor + switch) — design

The SSID pause toggle should be promoted from a service-only surface to
**per-SSID entities** under the Firewalla box device, mirroring the existing
per-network entity pattern. This is the natural home: the SSID ``profile`` is a
single global object in ``networkConfig.apc`` (not duplicated per AP), and the
Firewalla box is the controller of the SSIDs just as it is the controller of
the LAN networks.

### 8.1 Entity surfaces

| Surface | Platform | State | Attributes |
| --- | --- | --- | --- |
| SSID status | binary sensor | `is_on` = SSID enabled (not paused) | SSID name, band, encryption, wpa3, VLAN, interface, paused |
| SSID toggle | switch | `is_on` = SSID enabled (not paused) | same context |

### 8.2 Naming pattern (mirrors the network entities)

The network entities use a **kind prefix** in the name template:
`"{network_kind} {network_name} Status"` (e.g. "VLAN VLAN10 CORE Status").
The SSID entities use the same pattern with **"SSID"** as the kind:

- Binary sensor name template: `"{ssid_kind} {ssid_name} Status"` → "SSID Universe Guest Status"
- Switch name template: `"{ssid_kind} {ssid_name}"` → "SSID Universe Guest"

Both flow through translation placeholders (``{ssid_kind}``, ``{ssid_name}``),
exactly like the network pattern. HA applies its native device-prefix and
slugification rules to derive the entity ID.

**Entity ID awareness note:** because HA prefixes the entity name with the
device name (the Firewalla box) and slugifies, the actual entity IDs will look
like:

- `binary_sensor.firewalla_ssid_universe_guest_status`
- `switch.firewalla_ssid_universe_guest`

We do **not** construct these ourselves — following the existing best practices
(translation placeholders + `build_entity_unique_id`) means HA derives them
correctly. This note is for awareness/documentation only.

### 8.3 Unique IDs (stable, registry-level)

Using the existing `build_entity_unique_id` helper:

- Binary sensor: `{entry_id}_ssid_{profile_uuid}_binary_sensor`
- Switch: `{entry_id}_ssid_{profile_uuid}_switch`

The `profile_uuid` is embedded in the `object_id` portion, mirroring how
`network_{network_uuid}` is used for network entities.

### 8.4 Reconciliation

Mirror `async_reconcile_network_entities`: remove stale SSID registry entries
when profiles disappear, using the `_ssid_` prefix check (analogous to the
`_network_` prefix check).

### 8.5 Gating

- New `CONF_ENABLE_SSID_ENTITIES` option (default on), mirroring
  `CONF_ENABLE_NETWORK_ENTITIES`.
- AP7-presence gate: entities only appear when `networkConfig.apc.assets` is
  non-empty. Non-AP7 users see nothing.

### 8.6 Switch behavior

- `turn_on`/`turn_off` call the confirmed `async_set_ssid_paused` write.
- State reflects the runtime `paused` field and updates on coordinator refresh,
  mirroring `FirewallaRuleSwitch`.

## 9. References

- Issue: `ccpk1/firewalla-local-ha#21`.
- Evidence: `.tmp/wifi_toggle_capture_20260903/analysis.json`, `safe_report.zip`.
- Supporting note: `plans/in-process/FIREWALLA_LOCAL_AP7_WIRELESS_TOGGLE_SUP_INVENTORY.md` §7.
- RE doc: `docs/REVERSE_ENGINEERING_WORKFLOW.md` — "AP7 wireless controller findings" (Findings 19-20), "Proven payload families", "Next capture targets".
- Code: `api/client.py` (`async_set_ssid_paused`), `managers/wireless_manager.py`, `binary_sensor.py`, `device_tracker.py`.
