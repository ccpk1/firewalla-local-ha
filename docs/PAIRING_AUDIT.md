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
this.f22533K = jSONObject.getString("info");      // AES-encrypted box metadata
this.f22534X = jSONObject.getString("xname");     // AES-encrypted box name

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
- `rkey` (`f33133b`) — a rotation key JSON string
- `gid`, `expires`, `effective`, `createdAt`, `name`, `eid`, `inb`

### `m15455D()` — parse `rkey` into box metadata

```java
public JSONObject m15455D() {
    ue3 ue3Var = (ue3) arrayList.get(0);
    if (ue3Var.f33133b.length() != 0) {  // rkey is non-empty
        return new JSONObject(ue3Var.f33133b);  // parse rkey as JSON → n73.y0
    }
    return null;
}
```

The `rkey` field is a JSON string containing at minimum:
```json
{"key": "<RSA-encrypted-rotation-key>", "ts": <timestamp>, "ttl": <seconds>}
```

This gets parsed into `n73.y0` (box metadata). The `ts` value from this JSON
is what appears as `rkeyts` in the outer envelope.

### `m15454C()` — get the rotation key

```java
public String m15454C() {
    if (this.f22531I0.length() > 0) return this.f22531I0;  // cached
    JSONObject jSONObject = this.f22542y0;  // n73.y0 = parsed rkey JSON
    if (jSONObject == null) return Strings.EMPTY;
    String optString = jSONObject.optString("key");  // rkey.key
    return s97.m18106q(optString, s97.f29914K);  // RSA-decrypt
}
```

This RSA-decrypts the `key` field from the `rkey` JSON. The result is the
**rotation key** — a different symmetric key than `symmetricKeys[0].key`.

### `m15456E()` — get the fallback symmetric key

```java
public String m15456E() {
    if (this.f22530H0.length() > 0) return this.f22530H0;  // cached
    ArrayList arrayList = this.f22541x0;  // symmetricKeys array
    if (arrayList.isEmpty()) return Strings.EMPTY;
    String m18106q = s97.m18106q(
        ((ue3) arrayList.get(0)).f33132a,  // symmetricKeys[0].key
        s97.f29914K                         // RSA private key
    );
    this.f22530H0 = m18106q;
    return m18106q;
}
```

This RSA-decrypts `symmetricKeys[0].key` — the fallback key.

### `m15464y()` — the actual key used for local Encipher encryption

```java
public String m15464y() {
    String m15454C = m15454C();  // try rkey.key first
    if (m15454C.length() == 0) {
        m15454C = m15456E();     // fall back to symmetricKeys[0].key
    }
    return m15454C.length() > 32 ? m15454C.substring(0, 32) : m15454C;
}
```

**This is the method called by `wx3.c()` to get the encryption key.**
It tries the rotation key (`rkey.key`) first, and only falls back to
`symmetricKeys[0].key` if `rkey` is absent.

### Key priority

1. **`rkey.key`** (RSA-decrypted) — used when `symmetricKeys[0].rkey` is
   a non-empty JSON string containing a `key` field
2. **`symmetricKeys[0].key`** (RSA-decrypted) — fallback when `rkey` is absent

### Our HA integration's approach — MISSING `rkey` support

Our HA code only implements the fallback path:
1. RSA-decrypt `symmetricKeys[0].key` → use directly

On boxes where `rkey` is present (Gold Plus, based on `rkeyts` evidence),
the APK uses the rotation key from `rkey.key`, which is a different value.
Our code uses the wrong key, producing HTTP 412.

### What about `rkeyts`?

The `rkeyts` field in the outer envelope comes from `n73.y0.optLong("ts")`,
which is the `ts` value from the `rkey` JSON. Its presence in the GP-failing
capture and absence in the Gold-working capture confirms that `rkey` is
present on Gold Plus but absent on Gold.

### Cloud-brokered pairing scenarios

The APK shows multiple pairing paths:

1. **Standard pairing** (`ProgressDialog.pairing()`): cloud login → rendezvous →
   group poll → extract key from `symmetricKeys`

2. **Migration pairing** (`ProgressDialog.migrate()`): used when upgrading from
   an older box. Copies settings from source box to target box.

3. **Bluetooth pairing** (`PairingHelper.tryBindBluetooth`): uses Bluetooth to
   establish initial connection. May bypass cloud rendezvous entirely.

4. **Simple mode pairing** (`RestoreFromBackupDialog`): restores from cloud
   backup.

The standard pairing path (path 1) is what our HA code implements.

---

## 9. Fixes applied in 1.1.8-alpha.1

### 9.1 `rkey` rotation key support

**Root cause:** The APK's `n73.m15464y()` tries `symmetricKeys[0].rkey.key`
first (RSA-decrypted), then falls back to `symmetricKeys[0].key`. Our code
only used the fallback. On boxes with `rkey` present (Gold Plus, Gold SE),
the actual encryption key is the rotation key from `rkey.key`, not
`symmetricKeys[0].key`.

**Fix:** `extract_group_credentials()` in `auth.py` now checks for `rkey`:
- If `symmetricKeys[0].rkey` is a non-empty string: parse as JSON, extract
  `key` field, RSA-decrypt it → that's the symmetric key
- If `rkey` is absent or parsing fails: use `symmetricKeys[0].key` directly
  (unchanged Gold behavior)

**Same fix applied to:** `capture_firewalla_packets.py` — both group-poll
paths now check for `rkey`.

### 9.2 Reverted `mtype` from outer envelope

**Finding:** The `mtype: "msg"` field was added in 1.1.7-beta.1 based on APK
string analysis of `wx3.d()`. However, that string is the **inner** encrypted
message structure, not the outer envelope. Neither captured phone trace shows
`mtype` in the outer envelope.

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

### 9.4 Diagnostic output in capture tool

**Fix:** Added diagnostic output to `capture_firewalla_packets.py` that
reports group fields (including `rkey` presence), key derivation path, and
derived key length/prefix.

---

## 10. Open questions

1. Why does the APK send `mtype` in the outer envelope but neither captured
   phone trace shows it?
2. Why does the GP-failing box return 378B responses (small acks) while the
   Gold-working box returns 192KB (full runtime data) on the first POST?
3. Why does the GP-failing phone send 7 POSTs before SSE while the
   Gold-working phone sends 1?
4. Are there cloud-brokered pairing paths that use a different key derivation
   than the standard path?