# Support note: AP7 wireless inventory evidence (Phase 1)

Source: `ccpk1/firewalla-local-ha` issue #21 — *"[Feature]: Wireless Network Toggle for AP7"*.
Artifacts: `.artifacts/ap7-wireless-discovery/base_line_guest_wifi_off.json` and
`.artifacts/ap7-wireless-discovery/guest_wifi_on.json`.

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

### 2.5 The AP7 access points appear as hosts

Five hosts have `connection_type == "ap"` and `host_device_type == "ap"`, all on
the "Universe" network:

| Host | MAC | IP |
| --- | --- | --- |
| UPSTAIRS-AP | `34:3A:20:C3:FC:A0` | 192.168.1.9 |
| MAIN-FLOOR-AP | `34:3A:20:C4:03:CE` | 192.168.1.8 |
| KITCHEN-AP | `34:8A:12:C4:06:36` | 192.168.1.5 |
| GARAGE-AP | `34:8A:12:C4:06:06` | 192.168.1.6 |
| BASEMENT-AP | `34:3A:20:C3:FB:8A` | 192.168.1.7 |

These normalized host records contain **no wireless/SSID config** — only MAC,
name, IP, network, connection type, and flow counters.

### 2.6 "Guest" appears only as firewall policy rules

The 7 `guest` occurrences are all policy rules scoped to a network named
**"Universe Guest"** (via `tag_refs: ["intf:bc0c4b4c-..."]` and
`applies_to: ["Universe Guest"]`). Examples: block vpn/porn/p2p, qos rules.
These are firewall rules, **not** wireless/SSID broadcast config.

## 3. Field-mapping table

| Published concept | Local raw field / location | Normalized field | HA-derived field | Confidence / evidence |
| --- | --- | --- | --- | --- |
| AP7 device presence | `hosts[]` with `connection_type=ap`, `host_device_type=ap` | `FirewallaHostRuntime` | watched-device / device tracker | **High** — 5 AP7 hosts confirmed in diagnostic |
| Wireless / SSID broadcast state | **Not present** in normalized snapshot or diagnostic | — | — | **None** — no wireless keys found |
| Guest network (as rule scope) | `policy_rules[]` `tag_refs=intf:...`, `applies_to="Universe Guest"` | `FirewallaPolicyRule` | rule-backed switches | **High** — confirmed rules |
| Raw `networkProfiles` / `networkConfig` | raw init payload (not in diagnostic) | not normalized | network lookup | **Present in raw payload, absent from diagnostic** |

## 4. Conclusion and decision

- The **normalized runtime snapshot does not carry wireless/SSID state**, and the
  diagnostic export does not include the raw `networkProfiles`/`networkConfig`
  payload where such state might live.
- The AP7s are visible as hosts, but with no wireless config.
- Because the two files are identical **and** the sync caveat is unresolved, we
  **cannot yet conclude** that wireless state is absent from the Firewalla
  runtime. It may simply not be captured by the current snapshot/diagnostic.

**Decision gate outcome:** Phase 1 is **blocked on the reporter** confirming the
"Sync Runtime" step. Before proceeding to Phase 2 (protocol discovery), we should
either:
1. Get the reporter to re-capture with a forced sync before the second download,
   **and/or**
2. Capture the **raw init payload** (which includes `networkProfiles` /
   `networkConfig`) rather than only the normalized snapshot, so we can inspect
   the actual wireless config location.

## 5. Next steps

- [x] **Implemented:** Extended the integration diagnostic (`diagnostics.py`) to
      include the raw init payload (`runtime_init_payload`, redacted). The
      reporter can now capture the full runtime (including `networkProfiles` /
      `networkConfig`) with the same diagnostic download they already use — no
      repo, venv, or CLI needed.
- [ ] Ask the reporter to re-capture with the new diagnostic: (1) hit
      **"Sync Runtime"**, wait, (2) download diagnostic, (3) make the wireless
      change in the app, (4) hit **"Sync Runtime"** again, wait, (5) download a
      second diagnostic, and post both.
- [ ] Re-run the wireless-key scan on the raw `runtime_init_payload` once
      captured.
- [ ] Only then proceed to Phase 2 (protocol discovery) with confirmed evidence.
