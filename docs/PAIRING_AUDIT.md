# Firewalla Local pairing audit

## Purpose

This document captures the known and observed behavior of the Firewalla local
Encipher pairing protocol across multiple sources:

- captured phone traffic (working Gold box)
- captured phone traffic (failing Gold Plus box — safe reports only, decryption
  failed)
- decompiled Android APK v1.69.1
- current Home Assistant integration code

It is a working document meant to identify gaps, track findings, and guide
next steps.

---

## Sources

| Source | Label | Box | Status |
| --- | --- | --- | --- |
| `issue_22_chads_gold/phone_redacted.json` | Gold-working | Gold (original) | Fully decrypted ✅ |
| `phone_decoded_issue22_v2.json` | GP-failing | Gold Plus | Decryption failed (all CRC errors) ❌ |
| APK `wx3.java` | APK-wx3 | — | Decompiled |
| APK `y2.java` | APK-y2 | — | Decompiled |
| APK `n03.java` | APK-n03 | — | Decompiled |
| Integration `client.py` | HA-client | — | Running code |

---

## 1. Outer envelope (HTTP POST body)

### Observed

| Field | Gold-working | GP-failing | APK (`wx3.c`) | HA 1.1.6 | HA 1.1.7-beta.1 |
| --- | --- | --- | --- | --- | --- |
| `message` | ✅ encrypted | ✅ encrypted | ✅ `put("message", m)` | ✅ | ✅ |
| `timestamp` | ✅ float | ✅ int | ✅ `System.currentTimeMillis()/1000` | ✅ int | ✅ int |
| `mtype` | ❌ absent | ❌ absent | ✅ `put("mtype", "msg")` in **caller** (`y2.java`) | ❌ absent | ✅ "msg" |
| `rkeyts` | ❌ absent | ✅ present | ✅ conditional on `jSONObject2.optLong("ts")` | ❌ absent | ❌ absent |

### Key findings

1. The APK's `wx3.c()` builds `{timestamp, message}`. The **caller** `y2.java`
   adds `mtype: "msg"` afterwards. So the phone app DOES send `mtype` in the
   outer envelope — but neither of our captured phone traces show it.

2. The `rkeyts` field is present in the GP-failing capture but absent from the
   Gold-working capture. This is set by the phone app based on box metadata
   (`n73.y0.optLong("ts")`). It is not something we control — it's a
   box-reported value.

3. **The `mtype` commit was based on the APK string analysis, not on captured
   traffic.** The string `,\"compressMode\":1}, \"mtype\":\"msg\"}` found in
   `wx3.d()` was interpreted as the outer envelope, but it is actually the
   **inner** encrypted message structure (the nested JSON before encryption).
   The outer `mtype` is added by `y2.java` via `c.put("mtype", "msg")` where
   `c` is the outer JSON object.

4. **Both our working Gold and the failing GP phone connections succeed without
   `mtype` in the outer envelope.** The APK code sends it, but the actual
   captured traffic does not (or the decode tool is not capturing it). This
   makes `mtype` an unlikely root cause.

---

## 2. Inner message envelope (encrypted payload)

### Observed structure

| Field | Phone (Gold) | Our HA | APK (`wx3.d`) |
| --- | --- | --- | --- |
| `mtype` | `"msg"` | `"msg"` | `"msg"` ✅ |
| `type` | `"jsondata"` | `"jsondata"` | `"jsondata"` ✅ |
| `msg` | `""` | `""` | `""` ✅ |
| `from` | `"iPhone"` | device name | `"Android"` ✅ (intentional) |
| `obj` | present | present | present ✅ |
| `appInfo` | present | present | present ✅ |
| `compressMode` | `1` | `1` | `1` ✅ |

### `obj` structure

| Sub-field | Phone | Our HA |
| --- | --- | --- |
| `type` | `"jsonmsg"` | `"jsonmsg"` ✅ |
| `id` | UUID | UUID ✅ |
| `mtype` | `"init"` | `"init"` ✅ |
| `target` | `"0.0.0.0"` | `"0.0.0.0"` ✅ |
| `data` | varies | varies |

### `appInfo` structure

| Field | Phone (Gold) | Our HA |
| --- | --- | --- |
| `deviceName` | `"iPhone"` | `"Firewalla-Local-HA-v1"` |
| `appID` | `"com.rottiesoft.circle"` | `"com.rottiesoft.circle"` ✅ |
| `platform` | `"ios"` | `sys.platform` |
| `timezone` | `"America/New_York"` | user timezone |
| `language` | `"en"` | `"en"` ✅ |
| `version` | `"1.69.1-71"` | `"1.68.89"` ⚠️ outdated |
| `eid` | redacted | our eid |
| `ios` | `"26.5-0"` | ❌ absent |

---

## 3. Init message sequence

### Gold-working

| Step | Time | Direction | Content | Size | Response |
| --- | --- | --- | --- | --- | --- |
| 1 | T+0s | POST | simple init: `{get, COMMAND_TIMEOUT}` | 677B | 200 (192KB) |
| 2 | T+5s | POST | full init: `{dapOps, fwapcOps, embeddedOps}` | 1609B | 200 (197KB) |
| 3 | T+11s | GET | SSE (encrypted in URL) | 0B | 200 (13KB) |
| 4 | T+11s | GET | SSE (encrypted in URL) | 0B | 200 (26KB) |
| 5 | T+16s | POST | full init (repeat) | 1601B | 200 (197KB) |

### GP-failing (safe report only — decryption failed)

| Step | Time | Direction | Content | Size | Response |
| --- | --- | --- | --- | --- | --- |
| 1 | T+0s | POST | ? | 624B | 200 (378B) |
| 2 | T+5s | POST | ? | 629B | 200 (378B) |
| 3 | T+5s | POST | ? | 621B | 200 (378B) |
| 4 | T+6s | POST | ? | 623B | 200 (378B) |
| 5 | T+6s | POST | ? | 622B | 200 (378B) |
| 6 | T+6s | POST | ? | 623B | 200 (378B) |
| 7 | T+7s | POST | ? | 624B | 200 (378B) |
| 8 | T+7s | GET | SSE | 0B | 200 (970B) |
| 9 | T+7s | GET | SSE | 0B | 200 (970B) |
| 10 | T+7s | GET | SSE | 0B | 200 (5900B) |
| 11 | T+7s | POST | full init | 1647B | 200 (414KB) |

### HA current (1.1.6)

| Step | Direction | Content | Size | Response |
| --- | --- | --- | --- | --- |
| 1 | POST | simple init: `{COMMAND_TIMEOUT, get}` | 657B | 412 (12B) |
| 2-22 | POST | (same message × 21) | 657B | 412 (12B) |

### Key differences

1. **Gold-working response sizes:** The first POST returns 192KB (full runtime
   data). The box is immediately ready.

2. **GP-failing response sizes:** The first 7 POSTs return only 378B (small
   acknowledgments). The box is not returning full data until the 11th POST.

3. **GP-failing sends 7 POSTs before SSE** — the Gold-working sends 1 POST
   before SSE. This suggests the GP box requires more handshake messages.

4. **HA sends identical messages on retry** — the phone never repeats the same
   message. Each POST has different content (different sizes: 624, 629, 621,
   623, 622, 623, 624).

---

## 4. fwapcOps and embeddedOps

### Phone (Gold-working) init message 2

```json
{
  "fwapcOps": [
    {"key": "stationControls", "method": "GET", "path": "/config/stations"},
    {"key": "switchTopology", "method": "GET", "path": "/status/wired_station"},
    {"key": "switchInfo", "method": "GET", "path": "/status/switch"},
    {"key": "fwapcCountry", "method": "GET", "path": "/config/country"}
  ],
  "embeddedOps": [
    {
      "item": "events",
      "key": "latest24MainNetworkEvents",
      "target": "0.0.0.0",
      "value": {
        "min": <timestamp>,
        "reverse": true,
        "parse_json": true,
        "filters": [
          {"event_type": "action", "sub_type": "system_reboot"},
          {"event_type": "state", "sub_type": "dualwan_state"},
          {"event_type": "state", "sub_type": "wan_state"}
        ]
      }
    }
  ],
  "dapOps": [
    {"key": "dapInfo", "method": "GET", "path": "/info"}
  ],
  "get": "0.0.0.0",
  "value": {}
}
```

### Our HA

```json
{
  "dapOps": [
    {"key": "dapInfo", "method": "GET", "path": "/info"}
  ],
  "fwapcOps": [
    {"key": "stationControls", "method": "GET", "path": "/config/stations"}
  ],
  "get": "0.0.0.0",
  "value": {}
}
```

### Gaps

- Missing 3 `fwapcOps`: `switchTopology`, `switchInfo`, `fwapcCountry`
- Missing `embeddedOps` entirely (events query for latest 24h network events)
- The `n03.n()` APK method confirms the phone sends all of these

---

## 5. `rkeyts` origin

The `rkeyts` value in the outer envelope comes from the APK source:

```java
// wx3.java - c() method
JSONObject jSONObject2 = n73Var.y0;
long optLong = jSONObject2 != null ? jSONObject2.optLong("ts") : 0L;
if (optLong > 0) {
    jSONObject.put("rkeyts", optLong);
}

// y2.java - case 2 (local message send)
JSONObject c = wx3Var.c(n73Var);
c.put("mtype", "msg");
JSONObject jSONObject = n73Var.y0;
if ((jSONObject != null ? jSONObject.optLong("ts") : 0L) == 0) {
    c.put("rkeyts", 1);
}
```

The `rkeyts` is a box-level timestamp from `n73.y0.ts`. If the box has no `ts`,
the app sends `rkeyts: 1`. This is a sync/replay-prevention mechanism, not
something we can control. The presence of `rkeyts` in the GP-failing capture
and its absence in the Gold-working capture is a box firmware difference.

---

## 6. `mtype` in outer envelope — origin

The `mtype` commit was based on analysis of the APK `wx3.d()` method:

```java
// wx3.d() — builds the inner encrypted message string
sb.append(",\"compressMode\":1}, \"mtype\":\"msg\"}");
```

This string was interpreted as the outer envelope format, but it is actually
the **inner** message structure. The outer `mtype` is added by `y2.java`:

```java
// y2.java — case 2, after calling wx3.c()
JSONObject c = wx3Var.c(n73Var);   // builds {timestamp, message}
c.put("mtype", "msg");              // adds mtype to outer
```

The APK confirms the phone app sends `mtype` in the outer envelope. However,
**neither captured phone trace shows it.** Possible explanations:

1. The decode tool's pcap reassembly loses the outermost JSON layer.
2. The phone's `okhttp` library sends the outer envelope differently than raw
   JSON.
3. The box accepts messages both with and without `mtype`, and the phone
   stopped sending it in a newer app version.

---

## 7. Key provisioning — the unresolved issue

Three capture attempts from the GP-failing user all produced "Invalid padding
bytes" on every message. The provisioning succeeds (writes a key file), but
the key cannot decrypt any captured traffic. This is the central unresolved
issue.

### Possible explanations

1. **The provisioning flow returns a key that doesn't match the box.** This is
   the leading theory. On Gold, the same code returns a matching key.

2. **The QR code is consumed by provisioning, and the phone's fresh QR creates
   a different key.** But the symmetric key is supposed to be per-box, not
   per-client. If it were per-client, our working Gold capture would also fail.

3. **The user's Npcap/scapy setup is still not correctly parsing the pcap.**
   But the user tried 3 times with different approaches, and the second attempt
   used the updated batch file.

4. **The box invalidates the key between provisioning and phone pairing.** The
   provisioning runs first, then the phone pairs under a fresh QR. If the key
   rotates, the provisioning key would be stale.

---

## 8. APK provisioning flow — symmetric key extraction

### Cloud login response parsing (`z73.m21307g`)

The cloud login response contains a `groups` array. Each group is parsed into
an `n73` object via `n73.m15460I()`:

```java
// n73.m15460I() — parses group JSON from cloud
this.f22533K = jSONObject.getString("info");      // encrypted box info
this.f22534X = jSONObject.getString("xname");     // RSA-encrypted symmetric key

// Parse symmetricKeys array
JSONArray jSONArray = jSONObject.getJSONArray("symmetricKeys");
for (int i = 0; i < length; i++) {
    ue3 ue3Var = new ue3();
    ue3Var.m18976a(jSONArray.getJSONObject(i));
    arrayList.add(ue3Var);
}

// Decrypt box info to get model
JSONObject jSONObject2 = new JSONObject(
    s97.m18101c(this.f22533K, m15456E().substring(0, 32))
);
```

### `ue3` — symmetric key entry

Each `symmetricKeys` array entry has:
- `key` (`f33132a`) — the RSA-encrypted symmetric key
- `rkey` (`f33133b`) — a rotation key reference
- `gid`, `expires`, `effective`, `createdAt`, `name`, `eid`, `inb`

### `m15456E()` — get decryption key

```java
public String m15456E() {
    if (this.f22530H0.length() > 0) return this.f22530H0;
    ArrayList arrayList = this.f22541x0;  // symmetricKeys array
    if (arrayList.isEmpty()) return Strings.EMPTY;
    String m18106q = s97.m18106q(
        ((ue3) arrayList.get(0)).f33132a,  // first symmetricKey's "key" field
        s97.f29914K                         // RSA private key
    );
    this.f22530H0 = m18106q;
    return m18106q;
}
```

This RSA-decrypts the first `symmetricKeys[0].key` using the app's RSA private
key (`s97.f29914K`).

### `m15457F()` — get the symmetric key for local communication

```java
public String m15457F() {
    String str = this.f22535Y;
    if (str != null) return str;                    // cached value

    qc3 qc3Var = this.f22536Z;
    if (qc3Var != null) {
        // PATH A: use locally stored box config key
        this.f22535Y = qc3Var.f27093b;
    } else {
        // PATH B: decrypt xname using the RSA-decrypted symmetric key
        this.f22535Y = s97.m18101c(
            this.f22534X,              // xname (AES-encrypted symmetric key)
            m15456E().substring(0, 32) // first 32 bytes of RSA-decrypted key
        );
    }
    return this.f22535Y;
}
```

### Two key derivation paths

**PATH A** (`qc3` exists): The key comes from a locally stored box config
object (`qc3.f27093b`). This is used when the box has already been paired and
the key is cached locally.

**PATH B** (`qc3` is null): The key is derived by:
1. RSA-decrypting `symmetricKeys[0].key` → get the intermediate key
2. Taking the first 32 bytes of that intermediate key
3. AES-decrypting `xname` using that 32-byte key with zero IV

### Our HA integration's approach

Our HA code does:
1. RSA-decrypt `symmetricKeys[0].key` → get the symmetric key
2. Use that key directly for AES encryption

**The difference:** Our code uses the RSA-decrypted `symmetricKeys[0].key`
directly as the AES key. The APK uses it as an **intermediate key** — it takes
only the first 32 bytes and then uses that to AES-decrypt `xname`, which yields
the actual symmetric key.

### This could be the root cause

If `symmetricKeys[0].key` and `xname` are both present in the cloud response,
the APK uses `xname` (PATH B) to derive the actual key. Our code uses
`symmetricKeys[0].key` directly. On Gold, these might produce the same result
(if `xname` is absent or the key is short enough). On Gold Plus, they might
differ.

### What about `rkeyts`?

The `rkeyts` field comes from `n73.f22542y0` (the box metadata JSON object).
This is populated from the init response, not from the cloud login. The
presence of `rkeyts` in the GP-failing capture suggests the box has a `ts`
value in its metadata that the Gold box doesn't have. This is a box state
difference, not a provisioning difference.

### Cloud-brokered pairing scenarios

The APK shows multiple pairing paths:

1. **Standard pairing** (`ProgressDialog.pairing()`): cloud login → rendezvous →
   group poll → extract key from `symmetricKeys`/`xname`

2. **Migration pairing** (`ProgressDialog.migrate()`): used when upgrading from
   an older box. Copies settings from source box to target box. The key may
   come from the source box's local config (`qc3`) rather than from the cloud.

3. **Bluetooth pairing** (`PairingHelper.tryBindBluetooth`): uses Bluetooth to
   establish initial connection. May bypass cloud rendezvous entirely.

4. **Simple mode pairing** (`RestoreFromBackupDialog`): restores from cloud
   backup. May use a different key derivation path.

The standard pairing path (path 1) is what our HA code implements. If some
boxes require a different path (e.g., migration), the key derivation would
differ.

---

## 9. Fixes applied in 1.1.8-alpha.1

### 9.1 Two-tier key derivation (`xname` support)

**Root cause:** The cloud provisioning response contains a `symmetricKeys` array
where each entry's `key` field is RSA-encrypted. On older boxes (Gold), the
RSA-decrypted key IS the final symmetric key. On newer boxes (Gold Plus, Gold
SE), the RSA-decrypted key is a **Key-Encryption Key (KEK)** — the actual
symmetric key is AES-CBC encrypted inside a separate `xname` field in the group
JSON.

**Fix:** `extract_group_credentials()` in `auth.py` now checks for `xname`:
- If present: RSA-decrypt `symmetricKeys[0].key` → take first 32 bytes →
  AES-decrypt `xname` → that's the actual symmetric key
- If absent: use the RSA-decrypted key directly (unchanged Gold behavior)
- Falls back gracefully on decryption errors

**Same fix applied to:** `capture_firewalla_packets.py` — the capture tool's
`_provision_symmetric_key()` function had the same bug. This was likely the
cause of the Issue 22 user's 3 failed decode attempts (the tool was deriving
the wrong key on their Gold Plus).

### 9.2 Reverted `mtype` from outer envelope

**Finding:** The `mtype: "msg"` field was added in 1.1.7-beta.1 based on APK
string analysis of `wx3.d()`. However, that string is the **inner** encrypted
message structure, not the outer envelope. Neither captured phone trace shows
`mtype` in the outer envelope. The APK's `y2.java` does add it via
`c.put("mtype", "msg")`, but the box accepts messages without it.

**Fix:** Removed `_RAW_MESSAGE_MTYPE_KEY` and the `"mtype": "msg"` field from
the outer payload in `client.py`.

### 9.3 Aligned init message with phone flow

**Finding:** The phone's full init message includes 4 `fwapcOps` entries and
an `embeddedOps` events query. Our HA code only sent 1 `fwapcOps` entry and
no `embeddedOps`.

**Fix:** Updated `async_get_pairing_runtime_init_payload()` in `client.py` to
include:
- `fwapcOps`: `stationControls`, `switchTopology`, `switchInfo`, `fwapcCountry`
- `embeddedOps`: `latest24MainNetworkEvents` with event filters for
  `system_reboot`, `dualwan_state`, `wan_state`

### 9.4 Debug logging for group JSON

**Fix:** Added debug logging in `auth.py` that logs whether each group has
`xname` and how many `symmetricKeys` entries it has. Also logs when two-tier
key wrapping is activated and when fallback occurs.

---

## 10. Open questions

1. Why does the APK send `mtype` in the outer envelope but neither captured
   phone trace shows it?
2. Why does the GP-failing box return 378B responses (small acks) while the
   Gold-working box returns 192KB (full runtime data) on the first POST?
3. Why does the GP-failing phone send 7 POSTs before SSE while the
   Gold-working phone sends 1?
4. Does the `rkeyts` field matter for message acceptance?
5. Are there cloud-brokered pairing paths that use a different key derivation
   than the standard path?
6. Does the Gold box's cloud response contain `xname`? (Debug logging added
   in 1.1.8-alpha.1 will answer this on next pairing.)