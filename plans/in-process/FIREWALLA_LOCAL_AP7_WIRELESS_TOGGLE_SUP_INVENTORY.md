# Support note: AP7 wireless inventory evidence (Phase 1)

Source: `ccpk1/firewalla-local-ha` issue #21 — *"[Feature]: Wireless Network Toggle for AP7"*.
Artifacts: `.artifacts/ap7-wireless-discovery/` — `base_line_guest_wifi_off.json`,
`guest_wifi_on.json` (initial, normalized-only), and `ap7_wifi_on.json`,
`ap7_wifi_off.json` (comprehensive, with raw `networkConfig.apc`).

## 1. What the reporter submitted

The reporter (`squirtbrnr`) enabled the guest SSID, waited ~1 minute, and captured
two diagnostic downloads. Both files were sanitized for PII (values replaced with
`**REDACTED**` / `<REDACTED>`).

## 2. Confirmed facts from the raw files

### 2.1 The two files are byte-for-byte identical

- Same MD5: `22b5055f6b45941125c93f6f9ab0fbc0`
- `diff` output: zero lines
- Both are 9,657 lines / 310,850 bytes

This confirms the reporter's own observation. **However**, the maintainer's
follow-up question (issue comment) asks whether the reporter used the **"Sync
Runtime"** button and waited before the second download. Because runtime data is
polled on an interval, a second download without a forced sync can capture a
**stale snapshot**. The identical-files result is therefore **inconclusive** —
it may reflect capture timing rather than the absence of wireless state.

### 2.2 The diagnostic captures only the normalized runtime snapshot

The diagnostic `data` section contains exactly the fields of
`FirewallaRuntimeSnapshot` (`models.py`):

- `entry_data` (redacted credentials)
- `entry_options` (empty)
- `runtime_snapshot` with 8 keys:
  - `appliance_identity`, `appliance_runtime`, `policy_rules` (132),
    `exception_rule_count`, `hosts` (97), `groups` (3), `users` (0),
    `speed_test_results` (30)

The diagnostic does **not** contain the raw init payload, `networkProfiles`, or
`networkConfig`. Those keys exist in the raw payload the client reads
(`api/client.py` `_RAW_NETWORK_PROFILES_KEY` / `_RAW_NETWORK_CONFIG_KEY`) but are
**not** carried into the normalized snapshot, so they are absent from the
diagnostic export.

### 2.3 No wireless / SSID keys exist anywhere in the file

A recursive key scan found **zero** occurrences of: `ssid`, `wifi`, `wireless`,
`ap7`, `broadcast`, `radio`, `band`, `channel`, `wlan`, `access`.

### 2.4 The controller is a Firewalla Purple, not an AP7

`appliance_identity.model == "purple"`. This is consistent with the user's
clarification: **AP7 is the name of the access points**, and the access points
require a Firewalla device (here a Purple) for control. The theory is that since
the AP7 requires a Firewalla device, some of the AP7 config must be stored on the
Firewalla.

### 2.5 The earlier "5 APs" were NOT Firewalla AP7s (corrected)

The initial assumption that the user had 5 Firewalla AP7s was **wrong**. The
reporter clarified that those 5 APs (UPSTAIRS-AP, MAIN-FLOOR-AP, KITCHEN-AP,
GARAGE-AP, BASEMENT-AP) were **Aruba InstantOn AP22** units, managed outside of
Firewalla, broadcasting SSIDs tagged for the appropriate VLAN. They were left
over in the config and have since been removed.

The user actually has **2 Firewalla AP7s** (both `fwap-D` model):

| Host | MAC | IP |
| --- | --- | --- |
| Main Floor | `20:6D:31:71:1D:D0` | 192.168.1.3 |
| Upstairs | `20:6D:31:71:55:5C` | 192.168.1.4 |

These are connected via `wg_ap` mesh backhaul peers (10.132.101.116/.124) and
are fully managed through Firewalla.

### 2.6 "Guest" appears only as firewall policy rules

The 7 `guest` occurrences are all policy rules scoped to a network named
**"Universe Guest"** (via `tag_refs: ["intf:bc0c4b4c-..."]` and
`applies_to: ["Universe Guest"]`). Examples: block vpn/porn/p2p, qos rules.
These are firewall rules, **not** wireless/SSID broadcast config.

## 3. Field-mapping table

| Published concept | Local raw field / location | Normalized field | HA-derived field | Confidence / evidence |
| --- | --- | --- | --- | --- |
| AP7 device presence | `networkConfig.apc.assets.<id>` (name, model `fwap-D`, channel, txPower, meshMode, led, pauseWifi) | — | per-AP device | **High** — confirmed in comprehensive captures |
| Wireless / SSID config | `networkConfig.apc.profile.<uuid>` (ssid, key, band, encryption, wpa3, paused) | — | SSID switch/sensor | **High** — confirmed structure |
| Wireless toggle control | `networkConfig.apc.profile.<uuid>/paused` (true when off, absent when on) | — | SSID switch state | **High** — the only diff between on/off captures |
| SSID → network mapping | `networkConfig.apc.assets_template.ap_default.wifiNetworks` (intf, vlan, ssidProfiles) | — | network association | **High** — confirmed |
| AP mesh backhaul | `wgPeers` with `intf=wg_ap` | — | — | **High** — 2 AP7 peers confirmed |
| Raw `networkProfiles` / `networkConfig` | raw init payload | not normalized | network lookup | **Present in raw payload** |

## 4. Conclusion and decision

- The **wireless config lives in `networkConfig.apc`** of the raw init payload,
  **not** in the normalized `FirewallaRuntimeSnapshot`.
- The **toggle control is the `paused` field** on an SSID profile — the only
  difference between the wifi-on and wifi-off captures.
- The user has **2 Firewalla AP7s** (`fwap-D`), not 5 (the 5 were Aruba AP22).
- The **read path is confirmed**; the **write path is the key assumption** for
  alpha.7 (see the alpha.7 implementation plan).

**Decision gate outcome:** Phase 1 is **complete**. The wireless config and
toggle control are confirmed. Proceed to Phase 2 (protocol discovery) and the
alpha.7 implementation with the confirmed read path and assumed write path.

## 5. Next steps

- [x] **AP7 wireless config located (2026-08-07):** The reporter submitted two
      comprehensive captures (`ap7_wifi_on.json`, `ap7_wifi_off.json`) with the
      extended diagnostic. The wireless config lives in
      `networkConfig.apc` (the AP controller section). The **only** difference
      between wifi-on and wifi-off is the `paused` field on one SSID profile:
      `networkConfig.apc.profile.<uuid>/paused: true` when off, absent when on.
      This is the wireless toggle control.
- [x] **AP7 device model understood:** The reporter clarified the earlier
      assumption was wrong — the 5 APs were **Aruba InstantOn AP22** (managed
      outside Firewalla, now removed). They now have **2 Firewalla AP7s**:
      "Main Floor" (`20:6D:31:71:1D:D0` @ 192.168.1.3) and "Upstairs"
      (`20:6D:31:71:55:5C` @ 192.168.1.4), both `fwap-D` model, connected via
      `wg_ap` mesh backhaul peers (10.132.101.116/.124).
- [x] **Wireless config structure mapped:** `networkConfig.apc` contains:
      `assets` (per-AP device config: name, model, channel, txPower, country,
      meshMode, led, pauseWifi, disableAcl), `assets_template.ap_default`
      (wifiNetworks → ssidProfiles → VLANs, mesh key/ssid), `profile`
      (per-SSID: ssid, key, band, encryption, wpa3, paused), and
      `globalSysConfig` (stp, lldpd, autoSteer, maxComp, useDfsChannels).
      The toggled SSID is on `br1` / `vlan=100`.
- [x] **Implemented:** Extended the integration diagnostic (`diagnostics.py`) to
      include the raw init payload (`runtime_init_payload`, redacted). The
      reporter can now capture the full runtime (including `networkProfiles` /
      `networkConfig`) with the same diagnostic download they already use — no
      repo, venv, or CLI needed.
- [x] **Implemented:** Best-effort redaction for the raw init payload
      (`helpers/init_payload_redaction.py`). Verified against a real full-pull
      diagnostic: **0 emails, 0 MACs, 0 IPs, 0 JWTs remain** after redaction.
      Covers `jwt`, `ddnsToken`, `btMac`, `cpuid`, `publicIp`, `ddns`,
      `localDomainSuffix`, host identifying fields, WireGuard peer keys/names,
      the AP controller mesh key/SSID, and MAC/IP/email patterns in values and
      dict keys.
- [x] **Implemented:** Exclusion of large non-wireless sections to preserve
      traceability while reducing sensitivity. Dropped: `userTags`,
      `internetSpeedtestResults`, `systemFlows`, usage history (`last60`/
      `last30`/`newLast24`/`last12Months`), event/health sections, `customized
      Categories`, `deviceTags`/`tags`, `sysMetrics`, `monthlyDataUsage*`,
      `networkMetrics`, `newAlarms`. Kept: `networkConfig` (wireless core),
      `hosts` (for AP7 `ssidTags`), `policyRules`, `exceptionRules`, `appConfs`,
      `policy`, `runtimeFeatures`, `runtimeDynamicFeatures`, `apController`.
      Added internal-domain redaction (`*.ccpk.us` and subdomains). Verified:
      personal names and internal domains gone; size ~930 KB → ~580 KB.
- [ ] **Safe transfer (proposed):** Work with the reporter to provide the
      diagnostic files through a **private channel** (email or private upload)
      rather than posting publicly on the issue, since the raw payload is large
      and redaction is best-effort.
- [ ] Ask the reporter to re-capture with the new diagnostic: (1) hit
      **"Sync Runtime"**, wait, (2) download diagnostic, (3) make the wireless
      change in the app, (4) hit **"Sync Runtime"** again, wait, (5) download a
      second diagnostic, and send both privately.
- [ ] Re-run the wireless-key scan on the raw `runtime_init_payload` once
      captured.
- [ ] Only then proceed to Phase 2 (protocol discovery) with confirmed evidence.
