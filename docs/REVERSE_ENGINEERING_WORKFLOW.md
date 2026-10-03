# Firewalla Local reverse engineering workflow

## Purpose

This document records the working method used to test and reverse engineer the
Firewalla local runtime protocol for this repository.

It has two goals:

- preserve the exact testing and capture workflow so future protocol work is
  repeatable
- preserve confirmed findings in a durable matrix so implementation can follow
  evidence instead of memory

This document is intentionally operational. It is not vendor documentation.

## Contract-first research method

Reverse engineering should begin with published Firewalla contracts whenever
they exist.

The goal is not only to discover what the local box sends. The goal is to map
local runtime behavior onto the most trustworthy Firewalla action, write, and
read contracts, then record any local-only extensions separately.

Use this order of evidence:

1. published Firewalla action endpoints and required inputs
2. published Firewalla create or update payloads
3. published Firewalla read models and query shapes
4. local runtime steady-state payloads
5. local runtime mutation captures
6. Home Assistant-specific derived interpretations

Interpretation rules:

- published contracts define the baseline nouns, object boundaries, and narrow
  required inputs
- local captures confirm how the local box expresses or mutates those concepts
- local-only fields should be tracked as extensions, not as replacements for
  published Firewalla concepts
- a single live payload shape is evidence of implementation detail, not proof
  that the public model is wrong

### Required workflow before new modeling work

Before designing a new service, normalized DTO, or mutation contract:

1. read the relevant Firewalla public docs if they exist
2. extract the published action, write, and read contracts
3. list which fields are canonical Firewalla fields versus integration-derived
   fields
4. only then inspect local captures to map transport details and missing data

Recommended field-mapping table for substantial work:

- published field or action
- local raw field or payload location
- normalized canonical field
- Home Assistant-derived field, if any
- confidence and evidence source

This prevents the repository from drifting into a bottom-up model shaped only
by whichever local fields were easiest to capture first.

## Scope

This workflow covers:

- the full first-time pairing protocol (QR → cloud → local runtime)

  *(This was the most critical reverse-engineering finding. The pairing
  protocol is not published by Firewalla and was discovered entirely through
  live capture and trial. Do not treat it as a prerequisite — it is preserved
  here because nowhere else in the repo documents it end-to-end.)*

- reuse of a working Home Assistant config entry for live local protocol access
- direct runtime pulls for current-value comparison without re-pairing
- runtime inventory capture before and after user actions
- remote `tcpdump` capture on the Firewalla box
- decryption and inspection of local port `8833` traffic
- comparison of mutation payloads across rule families

## Pairing protocol (full sequence)

This section documents the reverse-engineered pairing protocol end-to-end. It
is the most critical finding in this repository. Without it, there is no
integration.

> **Critical timeline fact — read this first**
>
> The pairing protocol works identically for **every client** (iPhone, Home
> Assistant, etc.). The symmetric key it produces is **per-box, not per-client**.
> All clients that pair with the same box receive the same AES key.
>
> We did not need the iPhone's symmetric key. The actual order of events was:
>
> 1. **We paired ourselves first.** We scanned the box's QR code, ran the
>    cloud provisioning flow (Steps 1–6 below), and obtained **our own**
>    `symmetric_key`. The proof is in `.artifacts/poc/20260323-174620/`.
> 2. **We captured the iPhone separately.** While the iPhone performed
>    actions, we SSH'd into the box and ran `tcpdump` on port 8833.
> 3. **We decrypted the iPhone's traffic with our key.** Because the key is
>    box-level, the same AES material that our integration uses also decrypts
>    every other client's traffic to that box.
>
> This is why `utils/analyze_capture.py` can decrypt any pcap from your
> paired box without re-pairing — it loads *your* key from the Home Assistant
> config entry, and that key works for all traffic to that box.

### What the QR code contains

The Firewalla box displays a QR code on its screen containing JSON with these
fields:

| Field | Type | Example | Purpose |
| --- | --- | --- | --- |
| `gid` | string | `e4734492-...` | Group ID identifying the box |
| `license` | string | `b56208b3-...` | Device license key |
| `seed` | string | `rev4872430275...` | Random seed for pre-pairing crypto |
| `ek` | string | `9DAKEbaxhP7M...` | Encrypted pairing code (base64) |
| `ipaddress` | string | `23.245.207.179` | Public WAN IP |
| `model` | string | `gold` | Box model |
| `type` | string | `fb` | Always `fb` |
| `deviceName` | string | `Firewalla` | Box display name |
| `licensemode` | string | `1` | License mode |
| `rr` | string | `e767` | Short rendezvous reference |

Reference: `.artifacts/poc/20260323-174620/qr.json`

### Step 1 — Decrypt the QR pairing code

The `ek` field is AES-256-CBC encrypted with IV = 16 zero bytes. The
encryption key is derived from the QR data:

```
bootstrap_key = license[:8] + seed
plaintext = AES-256-CBC-decrypt(ek, bootstrap_key, iv=0..0)
```

The decrypted plaintext reveals a rendezvous object:

```json
{"r": "e7679e89-...", "evalue": {"license": "b56208b3-..."}}
```

The `r` value is the rendezvous ID (`rid`). The `evalue` is the license
assertion that will be sent to the Firewalla cloud.

Reference: `.artifacts/poc/20260323-174620/pairing_code.json`

### Step 2 — Generate an RSA keypair

Generate a 2048-bit RSA keypair formatted for Firewalla ETP:

- public key: SPKI PEM (`SubjectPublicKeyInfo`)
- private key: PKCS#8 PEM

The private key never leaves the client. The public key is sent to the cloud.

Code reference: `api/crypto.py::generate_firewalla_keys()`

### Step 3 — Cloud login (`POST /login/eptoken`)

Send to `https://firewalla.encipher.io/app/api/v2/login/eptoken`:

```json
{
  "assertion": {
    "name": "<device name>",
    "info": {"name": "circle"},
    "publicKey": "<SPKI public PEM>",
    "appId": "com.rottiesoft.circle",
    "appSecret": "fbb05afa-...",
    "signature": ""
  }
}
```

The response contains:

| Field | Purpose |
| --- | --- |
| `access_token` | Bearer token for subsequent cloud API calls |
| `eid` | Encryption endpoint ID (identifies this pairing session) |
| `aid` | Account ID (the provisioning identity on the cloud side) |
| `groups` | Group records (initially empty) |

The `appId` and `appSecret` constants were determined by capturing the
Firewalla mobile app's cloud traffic. They are the same values the official
app uses.

Code reference: `api/auth.py::build_login_payload()`

### Step 4 — Cloud rendezvous (`POST /ept/rendezvous/me`)

Use the access token to link this pairing to the box:

```json
{
  "rid": "<rendezvous_id from QR>",
  "evalue": "{\"license\":\"<license>\"}"
}
```

The `evalue` must be compact JSON (no whitespace), matching the NodeJS
`JSON.stringify` serialization.

This tells the Firewalla cloud "this client is pairing with box X". The cloud
relays the rendezvous, and the Firewalla box generates a symmetric key for
local communication, storing it in a cloud group record under the client's
identity.

Code reference: `api/auth.py::build_cloud_link_payload()`

### Step 5 — Poll for the group record

The box does not return the symmetric key immediately. The integration polls
the cloud endpoints in this order:

1. `GET /ept/group/me` — first candidate endpoint
2. `GET /ept/groups/me` — second candidate endpoint
3. `POST /login/eptoken` — fallback if neither group endpoint returned data;
   this refreshes the cloud identity and the fresh response includes a
   `groups` array

The first two are GET requests using the existing access token. The third is
a full POST re-login that produces a new identity with candidate groups.
Steps 1-2 are repeated across multiple poll attempts with a 3-second
interval between attempts.

The group record contains `symmetricKeys`, an array of RSA-encrypted
symmetric key objects. Each object has a `key` field that is the symmetric
key material encrypted with the public key sent in Step 3. The matching
group is identified by comparing the group `_id` field against the QR
`gid`.

**Key observation: some boxes return an `rkey` rotation key, others don't.**

### Step 6 — Decrypt the symmetric key

The symmetric key is stored in the group record's `symmetricKeys` array.
There are two possible derivation paths. Some boxes return an `rkey` rotation
key — those that don't use the direct key:

**Path A — Direct key:** Decrypt the `key` field of the first symmetric key
entry with the RSA private key:

```
symmetric_key_plain = RSA-decrypt(symmetricKeys[0].key, private_pem)
```

This yields the 32-byte raw AES key material used for all subsequent local
communication. The first 32 UTF-8 bytes of this material form the AES-256
key.

**Path B — Rotation key:** If `symmetricKeys[0].rkey` is a non-empty JSON
string, it takes priority over the direct key. Parse it as JSON, extract
its `"key"` field, and RSA-decrypt it:

```
intermediate_key = RSA-decrypt(symmetricKeys[0].key, private_pem)
rkey_payload = JSON.parse(symmetricKeys[0].rkey)
symmetric_key_plain = RSA-decrypt(rkey_payload.key, private_pem)
```

The presence of `rkey` is indicated by the `rkeyts` field in the outer
envelope of encipher messages (the `ts` value from the `rkey` JSON).

The APK method `n73.m15464y()` implements this priority:

```java
public String m15464y() {
    String m15454C = m15454C();  // try rkey.key first
    if (m15454C.length() == 0) {
        m15454C = m15456E();     // fall back to symmetricKeys[0].key
    }
    return m15454C.length() > 32 ? m15454C.substring(0, 32) : m15454C;
}
```

The `xname` field in the group JSON is AES-encrypted box metadata (box name,
model), not an encrypted key. It is decrypted using the same intermediate key.

### Summary of what you get out of pairing

| Credential | Source | Purpose |
| --- | --- | --- |
| `gid` | QR code | Identifies the box group for local endpoints |
| `eid` | Cloud login response | Identifies this pairing session |
| `aid` | Cloud login response | Account ID |
| `host` | User-supplied IP or `fire.walla` | Where to reach the box |
| `license` | QR code | Device license (stored for reauth) |
| `symmetric_key` | RSA-decrypted from group record | AES-256 key for local traffic |

These six values are stored in the Home Assistant config entry and are all
that is needed for local runtime access. Pairing is never repeated unless the
entry is removed.

Reference: `.artifacts/poc/20260323-174620/bootstrap.json`
Reference: `.artifacts/poc/20260323-174620/identity.json`

### Crypto chain summary

```
QR ek ──AES-256-CBC──> rendezvous ID
       key = license[:8] + seed
       iv  = 16 zero bytes

Cloud login ──> access_token + eid + aid
Cloud rendezvous ──> box generates symmetric key, stores in cloud group
Group poll ──> RSA-encrypted symmetric key
RSA decrypt (2048-bit private key) ──> raw symmetric key material

Every local POST:
  build Firewalla envelope (mtype + message with from/obj/appInfo)
  json.dumps(envelope, separators=(",", ":")) ──> AES-256-CBC(key) ──> base64
  outer payload = {"message": base64_ciphertext, "timestamp": <now>}
  POST http://{host}:8833/v1/encipher/message/{gid}

### Key derivation (two paths)

The symmetric key used for AES-256-CBC encryption comes from one of two
sources depending on what the cloud returns during provisioning:

1. **`rkey` (rotation key, preferred):** If the first `symmetricKeys[0]`
   entry contains a non-empty `rkey` field, it is parsed as JSON and its `key`
   field is RSA-decrypted. The result is the actual encryption key.

2. **Direct key (fallback):** If `rkey` is absent, `symmetricKeys[0].key`
   is RSA-decrypted directly.

The APK's `n73.m15464y()` method implements this priority:

```java
public String m15464y() {
    String m15454C = m15454C();  // try rkey.key first
    if (m15454C.length() == 0) {
        m15454C = m15456E();     // fall back to symmetricKeys[0].key
    }
    return m15454C.length() > 32 ? m15454C.substring(0, 32) : m15454C;
}
```

The `rkey` field is a JSON string from `symmetricKeys[0].rkey`. The app
parses it into box metadata (`n73.y0`) via `ue3.m18976a()` → `m15455D()`:

| `rkey` JSON field | Maps to | Used as |
| --- | --- | --- |
| `key` | RSA-decrypted → encryption key | `m15454C()` → `m15464y()` |
| `ts` | `n73.y0.ts` | `rkeyts` in outer envelope |
| `ttl` | `n73.y0.ttl` | Key rotation interval |

The full chain from cloud response to encrypted message is:

```
symmetricKeys[0] ──> ue3.m18976a() ──> {key, rkey}
    │                                    │
    │ rkey present?                      │
    ├── yes ──> JSON.parse(rkey)         │
    │           └── .key ──> RSA-decrypt ─┤
    │                                     │
    └── no  ──> symmetricKeys[0].key      │
                └── RSA-decrypt ──────────┤
                                          ▼
                              m15464y() ──> AES key (32 bytes)
                                          │
                                          ▼
                              wx3.c() ──> AES-256-CBC encrypt
                                          │
                                          ▼
                              POST /v1/encipher/message/{gid}
```

### POC artifacts

The repository preserves three successive successful pairing runs under
`.artifacts/poc/`:

- `20260323-174620` — First successful full pairing
- `20260323-175103` — Second run (timing test)
- `20260323-175408` — Third run (full validation)

Each directory contains the complete artifact set:

| File | Contains |
| --- | --- |
| `qr.json` | Raw QR data from the box screen |
| `pairing_code.json` | Decrypted QR `ek` → rendezvous ID and license evalue |
| `bootstrap.json` | Cloud login results (aid, eid, gid, encrypted symmetric key) |
| `identity.json` | Final provisioning identity (aid, eid) |
| `cloud_link_response.txt` | Cloud rendezvous response confirming the link |
| `group_fetch.json` | Group record polling metadata |
| `local_init_message.json` | The encrypted init request sent to the box |
| `local_payload.json` | The raw encrypted local response |
| `local_response_decrypted.json` | Decrypted init response — the full runtime payload |
| `local_response.txt` | Raw HTTP response text |
| `summary.json` | End-to-end success for cloud + local steps |

### Live pairing in the integration code

The pairing protocol is implemented in:

- `api/auth.py` — Cloud provisioning helpers (`async_provision_firewalla_credentials`)
- `api/crypto.py` — Key generation, AES encryption, RSA encryption
- `config_flow.py` — Home Assistant config flow that calls the provisioning
  helpers

### Confirmed identity values

The captured iPhone pairing request revealed the outer HTTP fingerprint and
inner appInfo identity used by the official app. These are documented for
reference because they confirm the protocol family, not because the
integration should impersonate them.

Captured iPhone init request (from
`.captures/pairing_other_device_8833.pcap`, decrypted via
`utils/analyze_capture.py`):

```
Outer HTTP headers:
  User-Agent: Firewalla/89 CFNetwork/3860.400.51 Darwin/25.3.0
  Accept: application/json
  Accept-Language: en-US,en;q=0.9

Outer envelope fields:
  from:       iPhone

Inner appInfo:
  appID:      com.rottiesoft.circle
  deviceName: iPhone
  platform:   ios
  timezone:   America/New_York
  version:    1.68-89
  language:   en
  eid:        X4fp-7w651edXhvxCX53tg
  ios:        26.3-1
```

**How we decoded this:** We paired our own Home Assistant integration first
(Steps 1–6 above), which gave us the box-level symmetric key. Then we
captured the iPhone's traffic via remote `tcpdump` on the Firewalla box and
decrypted it using `utils/analyze_capture.py` with *our* key. Because the
symmetric key is per-box, it worked.

The integration uses the same `appID` (`com.rottiesoft.circle`) but identifies
itself transparently as the integration rather than as an iPhone. This was an
intentional design choice: spoofing the exact iPhone identity would be brittle
(maintenance cost on version changes), would not prevent backend blocking on
its own, and creates a sharper failure mode if the vendor ever inspects
traffic.

## Preconditions

Before using this workflow, confirm all of the following:

- the repository has a working `firewalla_local` config entry in
  Home Assistant Core at `core/config/.storage/core.config_entries`
- the stored config entry contains a valid local runtime credential set:
  `aid`, `eid`, `gid`, `host`, `license`, and `symmetric_key`
- the Firewalla box is reachable over LAN
- SSH access to the Firewalla box is available for remote packet capture
- the local Python environment can import the integration's API client

## Core tools

The current workflow uses these tools and files.

### Runtime credential source

- `core/config/.storage/core.config_entries`

This is used as the source of truth for the live Firewalla config entry during
protocol capture work. It avoids re-pairing while reverse engineering the local
runtime.

### Direct runtime pull helper

- `utils/pull_runtime.py`

This helper:

- loads the first working `firewalla_local` config entry from Home Assistant storage
- constructs `FirewallaApiClient` with the stored local runtime credentials
- pulls the current raw init payload from the box without re-pairing
- writes a timestamped comparison artifact set under `.artifacts/runtime-pull/`
- writes a compact per-user usage summary to speed up watched-user investigations, including current internet totals, unique totals, and per-app buckets when present

Use this first when the question is about what the box reports right now, for
example current user usage fields or the exact contents of `userTags`.

Applicability interpretation note:

- local rule payloads may still express direct-to-user assignment through a backing group tag plus affiliated user metadata
- when that happens, Home Assistant-facing rule applicability should record both the readable label and the applicability kind as `user`
- preserve the raw backing group reference only in diagnostic or capture artifacts, not in the default Home Assistant-facing applicability attributes

### Runtime inventory capture helper

- `.tmp/capture_runtime_inventory.py` (local, gitignored convenience script)

This script:

- loads the first `firewalla_local` config entry from Home Assistant storage
- constructs `FirewallaApiClient`
- requests the raw init payload from the local runtime
- normalizes that payload into the repository's current inventory report shape
- writes the structured result to a JSON artifact file

> **Staleness warning.** This helper lives in `.tmp/`, which is gitignored and is
> not maintained alongside the integration. Its call signature drifts whenever
> `build_runtime_inventory_report` changes, and it has broken that way before.
> For before/after membership or rule state, prefer the maintained
> `utils/pull_runtime.py` — it writes the raw `runtime_init.json`, which is what
> packet captures are diffed against anyway. Use the `.tmp` helper only when the
> normalized inventory report itself is the thing you need.

### Packet capture analysis helper

- `utils/analyze_capture.py`

This script:

- loads the symmetric key from Home Assistant storage
- reads a `.pcap` file captured from port `8833`
- reassembles HTTP streams
- decrypts Firewalla message payloads using the integration crypto helpers
- prints the decoded request or response contents for inspection

Limitations: it inspects only `POST` bodies on port `8833`. It does not report
other HTTP methods, does not decode server-sent events, and cannot see an action
that leaves the box. Use the widened helper below for those.

**It also cannot inspect responses, which matters more than it sounds.** Two
independent limits stack up:

- response bodies are printed **truncated to 800 characters**
- responses are **zlib-compressed inside the encrypted envelope**, so the print
  shows the compressed blob, not the data

Any question whose answer is in a response body — which is most read-side
reverse engineering — needs the untruncated dumper described next.

### Response dumper (compressed-response aware)

- `.tmp/dump_all.py <pcap> <out.json> [client-ip]`

Prints every decrypted message in **both directions** with full bodies, and
decompresses responses. Response payloads arrive as:

```json
{"compressed": 1, "payload": "<base64 of zlib-compressed JSON>"}
```

and decompress to:

```json
{"code": 200, "data": [{"msg": {...request echo...}, "result": {"data": {...}}}]}
```

So the useful body is `data[].result.data`, keyed by the echoed `msg.data.item`.

**Use this whenever the finding lives in a response.** It is a `.tmp/` helper
rather than a tracked util because it was written for one investigation, but the
decoding itself is now documented here so the next reader does not have to
rediscover it.

### Widened capture analysis helper

- `utils/analyze_capture_wide.py`

Use this for captures that may include cloud or push traffic. It prints four
sections:

1. **TLS flows** — destination endpoint, SNI server name, byte totals, and the
   first/last packet time. A cloud-only mutation is still visible here even
   though the TLS content stays opaque. `--sni-only` prints just this section.
2. **Local runtime (port 8833)** — *every* HTTP method, not only `POST`. Each
   `batchAction` is expanded, so the individual `set` / `cmd` / `init` steps and
   any `tags` / `userTags` values are shown directly.
3. **Server-sent events** — the `event:liveStats` push stream on port 8833,
   decoded end to end. The chain is: chunked transfer-encoding → AES-256-CBC
   with the box key → JSON envelope `{"compressed": 1, "payload": "<base64>"}`
   → base64 → zlib → JSON. `undecoded=0` means every event decoded cleanly.
4. **DNS queries** — resolved names, which help attribute an unknown endpoint.

It finds the box key the same way as the standard helper, so it needs no
re-pairing and accepts the same credential source.

### User-facing capture tool

- `tools/support/capture_firewalla_packets.py`
- `tools/support/capture_firewalla_packets_requirements.txt`
- `tools/support/run_capture_firewalla_packets.bat`
- `tools/support/WINDOWS_PACKET_CAPTURE_USAGE.md`

This is the self-service path for a **user** who does not have developer access
to this repository. It prompts for the box address and SSH password, starts the
remote capture, downloads the pcap, and can produce a redacted safe report that
excludes keys, addresses, and the raw capture.

Point users at this tool and its usage note rather than at the internal steps in
this document. The internal workflow assumes a paired development environment
with a stored config entry and a trusted SSH key; the support tool assumes
neither.

### Remote capture transport

- `ssh`
- `scp`
- `tcpdump`

The current workflow captures traffic on the Firewalla box directly rather than
trying to infer mutations from Home Assistant alone.

## Artifact conventions

Artifacts are split by workflow.

Current-value runtime pulls should be written under `.artifacts/runtime-pull/`.

Recommended runtime-pull contents:

- `.artifacts/runtime-pull/<timestamp>/runtime_init.json`
- `.artifacts/runtime-pull/<timestamp>/user_usage_summary.json`
- `.artifacts/runtime-pull/<timestamp>/summary.json`

Mutation-capture artifacts remain under `.tmp/`.

Recommended naming pattern:

- inventory before action: `.tmp/capture_<name>_before.json`
- inventory after action: `.tmp/capture_<name>_after.json`
- intermediate state captures: `.tmp/capture_<name>_after_<state>.json`
- packet capture: `.tmp/firewalla_<name>_capture.pcap`

Examples already used:

- `.tmp/capture_persistent_before.json`
- `.tmp/capture_persistent_after.json`
- `.tmp/firewalla_mutation_persistent_capture.pcap`
- `.tmp/capture_internet_after_off.json`
- `.tmp/firewalla_internet_reenable_capture.pcap`

## Preferred current-value workflow

Use this workflow whenever you need a fresh comparison pull from the live box
and do not need packet-level mutation evidence.

### 1. Reuse the working Home Assistant credentials

Use the existing `firewalla_local` config entry in
`core/config/.storage/core.config_entries`.

Reason:

- this avoids re-pairing, QR churn, and cloud-link timing issues

### 2. Run the direct runtime pull helper

Run:

```bash
python -m utils.pull_runtime
```

Optional custom artifact root:

```bash
python -m utils.pull_runtime --artifact-dir .artifacts/runtime-pull
```

Outputs:

- `runtime_init.json`: the raw local payload the integration currently reads
- `user_usage_summary.json`: compact current user usage values and per-app buckets
- `summary.json`: capture metadata and high-level counts

### 3. Compare the current pull before escalating

Inspect the fresh `runtime_init.json` for the fields you care about before
moving to packet capture. This is the preferred first step for questions like:

- whether a user usage field exists in the local payload at all
- whether `totalMins` and `uniqueMins` changed since the last pull
- whether a value shown in the Firewalla app appears in the current local init payload

Current watched-user baseline:

- `internetTimeUsageToday` is the first-choice source for user total and unique
  internet usage minutes when present
- `appTimeUsageToday` is the source for per-app watched-user usage buckets
- associated watched-user device and activity metadata may require
  integration-side joins against normalized hosts and affiliated groups
- direct-to-user assignment in the Firewalla app may still appear in local
  payloads as a backing group or tag plus affiliated user metadata; treat that
  backing group as an implementation detail until a user-facing surface proves
  otherwise
- when captures show both a backing group name and an affiliated user name,
  record both in the evidence, but do not assume the backing group should be
  shown in Home Assistant

### 4. Escalate to packet capture only when needed

Move to `tcpdump` plus `utils/analyze_capture.py` only when you need proof of:

- exact mutation message shapes
- encrypted request or response ordering
- fields that appear only during a live action and not in steady-state runtime data

## Choosing a capture

Pick the lane before you start; it decides the tool and the filter.

| Lane | Use when | Filter | Tool |
| --- | --- | --- | --- |
| **A — current value** | you need what the box reports now, with no mutation proof | none | `utils/pull_runtime.py` |
| **B — local mutation** | the action is expected on the local runtime (rules, group membership, host settings) | `port 8833` | `utils/analyze_capture.py` |
| **C — widened** | the action may leave the box, or you do not know where it lands | `port 8833 or 443 or 80 or 8443 or 53` | `utils/analyze_capture_wide.py` |
| **U — user self-service** | a user is capturing without developer access | managed by the tool | `tools/support/capture_firewalla_packets.py` |

- **Start with Lane A.** It is free, needs no capture, and often answers the
  question on its own.
- **Escalate to a packet lane only for mutation proof** — exact message shapes,
  ordering, or fields that appear only during a live action.
- **When unsure between B and C, choose C.** A widened capture is a superset: if
  the action turns out to be local you still have the port 8833 evidence, and if
  it is cloud-mediated you are not left guessing. The only cost is a larger pcap.
- **Never guess the lane from the UI.** An action that looks local in the app may
  be written by the cloud and merely reflected on the box, and vice versa.

## Standard workflow (local mutation capture)

### 0. Set the capture variables

Keep these in one place; every command below uses them.

```bash
BOX_HOST=<box-ip-or-fire.walla>   # the Firewalla box
SSH_USER=pi                        # fixed by Firewalla firmware
SSH_KEY=<path-to-ssh-key>          # a key the box already trusts
CLIENT_IP=<app-client-ip>          # the phone running the Firewalla app
CAPTURE_NAME=<short-label>         # e.g. host_rename, group_add
```

### 1. Confirm live credentials

Inspect the Home Assistant config entry and confirm:

- host value
- `gid`
- presence of `aid`, `eid`, and `symmetric_key`

Reason:

- the workflow depends on local runtime access without repeating QR pairing

### 2. Capture baseline state

Run the maintained pull helper:

```bash
python -m utils.pull_runtime --artifact-dir .artifacts/<CAPTURE_NAME>
```

It prints the timestamped directory it wrote. Keep that path; it is the "before"
side of the diff.

Purpose:

- establish the exact pre-action state
- identify existing rule or tag IDs that may be updated rather than created

### 3. Inspect the baseline for the target scope

Before capturing packets, inspect the baseline for:

- the target group, user, or host
- any existing rules whose `applies_to`, `target_name`, or `tag_refs` overlap
  the target
- whether the current state is absent, enabled, or disabled

Reason:

- Firewalla does not always use the same mutation strategy for every rule
  family

### 4. Clear old captures and confirm free space

The box's `/tmp` is small and fills quickly, and a full disk silently produces
zero-byte pcaps.

```bash
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$SSH_USER@$BOX_HOST" \
  "sudo rm -f /tmp/*.pcap; df -h /tmp | tail -1"
```

### 5. Arm remote `tcpdump`

```bash
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$SSH_USER@$BOX_HOST" \
  "sudo tcpdump -i any -s 0 -U -w /tmp/$CAPTURE_NAME.pcap \
     host $CLIENT_IP and port 8833"
```

Notes:

- `-U` writes each packet to disk immediately, so the file is flushed and its
  size can be verified at any moment. Without it, a pcap copied too early can be
  truncated.
- Scope to the app client's IP. Capturing every host on port 8833 adds noise and
  size for no benefit.
- Reason the port matters: local runtime mutations travel over encrypted HTTP on
  port `8833`.

Leave this running while the action is performed.

### 6. Perform the app action

Have the user perform the action in the Firewalla app. A single action is
easiest to correlate, but one capture can hold several actions if the user
records their order — attribution is then by timestamp.

### 7. Stop the capture by PID, then verify

Stop **only your own** capture, by PID. Never blanket-`pkill tcpdump`: the box
runs its own IPv6 router-advertisement sniffers under `tcpdump`, and killing
them disturbs its network monitoring.

```bash
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$SSH_USER@$BOX_HOST" \
  "PID=\$(pgrep -f 'tcpdump.*$CAPTURE_NAME'); \
   [ -n \"\$PID\" ] && sudo kill -INT \$PID; sleep 2; \
   stat -c '%s' /tmp/$CAPTURE_NAME.pcap"
```

Confirm the size is stable and non-zero before copying.

### 8. Copy the pcap, then free the box

```bash
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$SSH_USER@$BOX_HOST:/tmp/$CAPTURE_NAME.pcap" .tmp/$CAPTURE_NAME.pcap

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$SSH_USER@$BOX_HOST" "sudo rm -f /tmp/$CAPTURE_NAME.pcap"
```

Copy first, delete second. The local `.tmp/` copy is the artifact; the remote
file is scratch space and must not be left behind.

### 9. Capture post-action state

```bash
python -m utils.pull_runtime --artifact-dir .artifacts/<CAPTURE_NAME>
```

Note the new timestamped directory. This is the "after" side of the diff.

### 10. Decrypt the packet capture

```bash
python -m utils.analyze_capture .tmp/$CAPTURE_NAME.pcap --client-ip $CLIENT_IP
```

Add `--pairing-only` to suppress live-stream `GET` and `text/event-stream`
traffic. Inspect each decoded request for:

- outer message type such as `cmd` or `init`
- inner `item` field such as `policy:create`, `policy:delete`, `policy:update`,
  or `policy`
- the full `value` payload

### 11. Diff the two pulls

Compare the before and after `runtime_init.json` and identify:

- new, removed, or in-place-updated identifiers
- changes to `enabled`, `dnsmasq_only`, `target`, `target_type`, `tags`,
  `userTags`, and timing fields

### 12. Record the finding in this document

Every confirmed capture should update:

- the findings matrix
- the mutation-family notes
- the open questions list if new uncertainty appears

## Widened capture workflow (cloud and push traffic)

Use this when the local-mutation workflow above shows **no** traffic for the
action, or when you do not yet know where the action lands.

Only two things change: the filter and the analysis tool.

```bash
"sudo tcpdump -i any -s 0 -U -w /tmp/$CAPTURE_NAME.pcap \
   host $CLIENT_IP and ( port 8833 or port 443 or port 80 or port 8443 or port 53 )"
```

```bash
python -m utils.analyze_capture_wide .tmp/$CAPTURE_NAME.pcap --client-ip $CLIENT_IP
```

How to read the result:

- **A TLS flow but no port 8833 traffic** → the action is cloud-mediated. The
  capture proves *which* endpoint was contacted and *when*, but not the payload:
  TLS content is opaque to this tool.
- **Both present** → the app wrote locally *and* contacted the cloud. Take the
  write contract from the port 8833 sections and use the TLS section for
  correlation.
- **`undecoded=0` on the SSE section** → the push stream decoded cleanly. A
  non-zero count means an event shape changed and the decoder needs updating.

A worked example: a device-to-user assignment produced **zero** port 8833
traffic and a TLS session to the vendor's cloud endpoint, while the box later
reported the assignment as an ordinary host tag. See the cloud-mediated
device-to-user finding in the Additional host-settings section for the full
contract.

### Can we see inside TLS?

Not with this tool. The app-side credentials recovered during the pairing work
mean decrypting the app's cloud session is possible in principle, but no tooling
exists for it yet. Until then, treat cloud payloads as opaque and recover the
contract from the box's own representation instead — that is what the widened
workflow above is designed to do.

## Safety and repeatability rules

- capture one app action at a time
- preserve before and after inventory artifacts for every capture
- prefer the stored Home Assistant config entry over ad hoc credentials
- prefer published Firewalla contracts over ad hoc interpretation when both are
  available
- do not guess mutation semantics from UI labels alone
- do not assume every switchable rule family uses `create` and `delete`
- do not assume every disabled rule is deleted when turned off
- do not assume an action is local because it looks local in the app; when the
  location is unknown, use the widened lane
- never blanket-kill `tcpdump` on the box; stop your own capture by PID
- verify the pcap is non-zero before analysing it; a zero-byte capture means the
  remote disk filled or `tcpdump` never started
- delete the remote pcap after copying it; the box's `/tmp` is small

## Modeling output rule

When reverse engineering produces a new durable understanding, record it in the
right layer:

- update this workflow document for capture steps, evidence sources, payload
  findings, and confidence notes
- update `docs/RULE_MODEL.md` when the durable canonical rule interpretation or
  extension policy changes
- update `docs/ARCHITECTURE.md` only when ownership boundaries or repository
  structure need to change

This separation keeps capture evidence, canonical modeling, and repository
architecture from drifting into one mixed document.

## Confirmed protocol baseline

The following are confirmed by repository code and live captures.

### Transport baseline

- local runtime endpoint: `http://{host}:8833/v1/encipher/message/{gid}`
- transport: HTTP POST
- payload security: AES-256-CBC encrypted Firewalla message envelopes
- credential set used for runtime: `gid`, `eid`, `aid`, `symmetric_key`

### Proven payload families so far

| Family | Create strategy | Off strategy | Re-enable strategy | Notes |
| --- | --- | --- | --- | --- |
| Category rule block, temporary | `policy:create` with `expire` and `autoDeleteWhenExpires` | `policy:delete` before expiry or auto-removal after expiry | not applicable | Example: `Block for 1 minute` or `Block for 1 hour` on `social` for `AV_SMART_TV` |
| Category rule block, persistent | `policy:create` without expiry fields | not yet fully confirmed | not yet captured | Example: `Always block` on `social` for `AV_SMART_TV` |
| Internet block | `policy:create` when absent | `policy:update` with `disabled: 1` or `policy:delete` | `policy:update` with `disabled: 0` | Example: `Traffic from & to Internet` for `AV_SMART_TV` |
| Direct DNS allow, device-scoped | existing rule observed only | `policy:update` with `disabled: 1` and `idleTs` for timed pause | inventory confirms same-rule re-enable with cleared `idleTs`; payload not captured in this run | Example: `allow dns dns.google` for Kaden's Chromebook |
| AP7 wireless SSID pause | read via `networkConfig.apc.profile.<uuid>.paused` | `set` with `item: networkConfig`, full `networkConfig` in `value.config`, `ts` + `COMMAND_TIMEOUT`/`LAN_ONLY` (confirmed 2026-09-03) | `set` with `paused` absent to resume | Example: pause/resume "Universe Guest" on VLAN 100 |
| Internet quality (ping latency/loss) | `get` with `item: networkMonitorData`, `value: {}` (confirmed 2026-09-10) | read-only | read-only | Per-WAN 15-min samples; `stat {lossrate, max, mean, median, min}`; loss is a fraction, latency in ms; ~24h history in one call |

## Unified Network model

The Firewalla app treats LAN, VLAN, VPN, and WAN as **one unified "Network"
concept** with a shared detail page (name, type, VLAN ID, associated ports,
IPv4/IPv6 + DHCP, mDNS Relay, SSDP Relay, Block ICMP, device count, data usage,
related rules). The integration mirrors this with a single normalized
`FirewallaNetwork` model plus a per-network binary sensor. All mappings below are
**confirmed** by live box pulls (2026-08-25) and the APK runtime model.

### Network identity and kind

The unified registry is `networkConfig.interface`, keyed by **category**. The
category key is the source of the granular `network_kind` discriminator
(`lan`/`vlan`/`vpn`/`wan`) — it is **not** the box's coarse raw `type` field.

Router-Mode boxes segment their LANs one of two ways: as a **LAG `bond`** to a
managed switch (VLANs ride on the bond) or as per-network **`bridge`**
interfaces that carry direct ports and/or tagged VLAN members directly. Both
are LAN networks; the reverse-engineered captures below cover both layouts.

| App screen | `networkConfig.interface` category | `network_kind` | Notes |
| --- | --- | --- | --- |
| LAN (`LAN-MGMT`) | `bond` | `lan` | bond of `eth2`+`eth3`; VLANs ride on the bond (`bond0.10`) |
| LAN (`Guest`, `Home`, `Mgmt`, …) | `bridge` | `lan` | per-network bridge; `intf` lists direct ports and/or tagged VLAN members (e.g. `br1` Guest → `eth3.101`) |
| VLAN (`VLAN60 IOT`, `VLAN90 GUEST/DMZ`, …) | `vlan` | `vlan` | entry `vid` = VLAN id; `intf` = parent bond. A VLAN **referenced by a bridge's `intf`** is transport for that bridge and is **not** surfaced as its own network |
| VPN (`AmneziaWG`, `OpenVPN`, `WireGuard`) | `amneziawg` / `openvpn` / `wireguard` | `vpn` | `wgPeers`/`awgPeers` are per-peer hosts, **not** VPN networks |
| WAN (`WAN-ONE`) | `phy` | `wan` | only a `phy` entry whose `meta.type == "wan"`; unnamed `phy` ports (eth1/2/3) are hardware, not networks |
| WAN (wireless uplink) | `wlan` | `wan` | only when `meta.type == "wan"`; the box joins a Wi-Fi network as a client (`wpaSupplicant`), so it is a wireless WAN uplink, not a wireless LAN AP |

Each entry carries a `meta` block: `name` (display name), `type` (`lan`/`wan`
only — coarse), `uuid`. The `network_kind` is derived from the category key so
`vlan` and `vpn` are distinguishable despite all reporting `meta.type='lan'`.

### Detail fields

| App field | Raw path | Normalized | Entity attribute |
| --- | --- | --- | --- |
| Name | `networkConfig.interface.<cat>.<name>.meta.name` → `networkProfiles` display fields | `FirewallaNetwork.name` | (entity name) |
| Kind | `networkConfig.interface` category key | `FirewallaNetwork.kind` | `network_kind` |
| VLAN ID | `networkConfig.interface.vlan.<name>.vid`; a `bridge`/`bond` surfaces the `vid` of its tagged member(s) (e.g. `br3` Home → `eth3.100` → 100). An untagged network (only physical ports) has no VLAN. | `FirewallaNetwork.vlan_id` | `vlan_id` |
| DNS servers | `networkProfiles[uuid].dns`; only meaningful for WAN. LAN/VLAN/VPN set it `null` matching the Firewalla app, which does not list DNS for local networks (they inherit WAN DNS via `networkConfig.dns[<intf>].useNameserversFromWAN`). | `FirewallaNetwork.dns_servers` | `dns_servers` |
| Ethernet ports | `phy`/`wlan` WAN = its device name; `bond`/`bridge` = `intf` members; `vlan` = dereference `intf` parent to members; every member is dereferenced through parent chains (bridge → VLAN → physical port); VPN = none | `FirewallaNetwork.ports` | `ports` |
| IPv4 address | `networkProfiles[uuid].ipv4` (bare) / `item=intf` `ipv4` | `FirewallaNetwork.ipv4_addresses` | `ipv4_addresses` |
| IPv4 subnet | `networkProfiles[uuid].ipv4Subnet(s)` (CIDR) | `FirewallaNetwork.ipv4_subnets` | `ipv4_subnets` |
| IPv6 address | `item=intf` → `ipv6` | `FirewallaNetwork.ipv6_addresses` | `ipv6_addresses` |
| IPv6 subnet | `item=intf` → `ipv6Subnets` | `FirewallaNetwork.ipv6_subnets` | `ipv6_subnets` |
| Gateway | `networkProfiles[uuid].gateway`, falls back to `networkConfig.dhcp[<intf>].gateway` | `FirewallaNetwork.gateway` | `gateway` |
| DHCP | `networkConfig.dhcp[<intf>]` (gateway, subnetMask, lease, range, nameservers, searchDomain) | `FirewallaNetwork.dhcp` | `dhcp` |
| Device count | `hosts[]` with `host.intf == <network uuid>`, excluding the Firewalla box (`macVendor` contains `firewalla`) | `FirewallaNetwork.device_host_count` | `device_count` |

### Advanced options

| App toggle | Raw path | Normalized | Entity attribute |
| --- | --- | --- | --- |
| mDNS Relay | `networkConfig.mdns_reflector[<intf>].enabled` | `FirewallaNetwork.mdns_relay` | `mdns_relay` |
| SSDP Relay | `networkConfig.mroute[<intf>].routes[]` with `cidr: 239.255.255.250`; absent entry = off | `FirewallaNetwork.ssdp_relay` | `ssdp_relay` |
| Block ICMP | `networkConfig.icmp[<intf>].echoRequest` — **inverted** (`block_icmp = not echoRequest`; the box clears `echoRequest` when Block ICMP is on) | `FirewallaNetwork.block_icmp` | `block_icmp` |

### Data usage

| Kind | Source | Normalized | Entity attribute |
| --- | --- | --- | --- |
| LAN / VLAN / VPN | `item=intf` (`async_get_network_interface_payload`) windows `newLast24`/`last60`/`last30`/`last12Months` `totalDownload`/`totalUpload` | `FirewallaNetwork.usage` | `network_usage` |
| WAN (monthly) | `monthlyDataUsageOnWans[<wan uuid>].totalDownload`/`totalUpload` | `FirewallaNetwork.usage.monthly` | `network_usage.monthly` |

Per-network usage is surfaced via a **single logic path**: the integration
manager fetches `item=intf` once per poll (resilient to per-network failures —
OpenVPN returns a 500 for `item=intf`, all others work) and the entity
`network_usage` attribute, the `get_network_segment_report` usage section, and
the `get_network_segment_usage` service all consume the same manager views.
WAN networks have **no windowed source** — a WAN's `item=intf` windows are all
zero and the box-wide init windows are aggregate (not per-WAN) — so a WAN
`network_usage` carries only the **`monthly`** key (current calendar month from
`monthlyDataUsageOnWans`), never conflated with the rolling `last_30d` window.
WAN monthly totals also remain on the System Status `current_wan_usage` /
`get_wan_data_usage` surface.

#### Per-host flow and block counters (`item=intf`)

The same `item=intf` payload that carries the windows above also carries
**per-host flow counters** under its `hosts` map, and these are genuinely
per-device rather than per-network. Each host entry exposes:

| Key | Meaning |
| --- | --- |
| `conn` / `dns` / `ntp` | connection, DNS and NTP flow counts |
| **`dnsB`** | **DNS queries blocked** |
| **`ipB`** | **IP flows blocked** |
| **`ipD`** | **IP flows denied** |
| `download` / `upload` | byte totals per host |

Normalized to `FirewallaNetworkHostTotals` and surfaced through
`_serialize_network_host_totals` as `dns_blocked` / `ip_blocked` / `ip_denied`,
reachable via the `get_network_segment_report` (`hosts[]`) and
`get_network_segment_usage` services. `view.activity_hosts` carries the richer
per-host rows built from the payload's `flows` families
(`_build_network_activity_hosts`).

**This is the local block accounting the integration already had.** It is
per-host and windowed by whatever the `item=intf` request asks for, so it answers
"how much is being blocked for this device" — a count — where the rule hit data
answers "what exactly was blocked, and by which rule". The two are complementary:
the counter is aggregate and per-network-request scoped, the rule hit is
specific and arrives on every init pull.

Also on the init payload, for completeness, are three box-wide 24-hour flow
windows in `systemFlows` — `upload`, `download` and `dnsB` — each
`{begin, end, flows[]}` where a flow is `{domain, count, app?, category?,
flowTags?}`. These are **aggregate across the box**, not per-device, so they
answer "what is this network talking to" and not "what is this device doing".
Nothing in the integration consumes them today.

Two further per-device sources exist but are **Device Active Protect state, not a
flow log**: `host.policy.dap.flows` / `last24` / `ipFlows` / `dnsFlows` /
`icmpFlows` hold the destinations DAP has learned for that device, and
`host.policy.dap.finalRuleSet` reports its `defaultAction`, `isolation` and the
allow/block rule ids DAP installed. They are only present for DAP-managed
devices, and they describe what DAP permits rather than what actually crossed.

**Per-rule hit data** is the fourth source and the most directly useful: see the
rule hit findings under *Inventory-confirmed durable rule findings*.

### Box identity and port detail

The System Status entity surfaces box-level identity and physical-port detail
from the init payload:

| App field | Raw path | Normalized | Entity attribute |
| --- | --- | --- | --- |
| Box version | `longVersion` / `versionStr` | `FirewallaSystemInfo.software_version` | `software_version` |
| WAN IP | WAN network `networkProfiles[<wan_uuid>].ipv4` (primary = lowest port) | `FirewallaSystemStatus.wan_ip` / `wan_ips` | `wan_ip` / `wan_ips` |
| Port MAC | `nicStates[<port>].address` | per-port `mac` | `ports[<port>].mac` |
| Port speed | `nicStates[<port>].speed` (Mbps; `-1` = inactive) | per-port `speed_mbps` | `ports[<port>].speed_mbps` |
| Port link | `nicStates[<port>].carrier` (`1`/`0`) | per-port `link` | `ports[<port>].link` |
| Bluetooth MAC | `btMac` | `FirewallaSystemStatus` (raw) | `bluetooth_mac` |
| Box time zone | `timezone` | `FirewallaSystemStatus.timezone_name` | `timezone` |
| Release type | `releaseType` / `firmwareReleaseType` | `FirewallaSystemStatus.firmware_release_type` | `firmware_release_type` |
| Uptime | `uptime` | `FirewallaSystemStatus.uptime_seconds` | `uptime` / `uptime_seconds` |

Notes:

- `nicStates` is keyed by physical port (`eth0`..`eth3` on a Gold SE) and
  carries `address` (MAC), `speed` (Mbps, `-1` when disconnected), `carrier`
  (link up/down), and `duplex`. The `ports` attribute bundles these per port.
- The Firewalla app exposes DNS servers for the **WAN only**; local networks
  inherit WAN DNS via `networkConfig.dns[<intf>].useNameserversFromWAN`, so the
  per-network `dns_servers` attribute is surfaced for WAN networks only.
- **WAN IP source (2026-09-10):** The box-level `wan_ip`/`wan_ips` are derived
  from the **WAN network inventory** (`networkProfiles[<wan_uuid>].ipv4`), not
  from the init payload's `publicIp`/`publicIps`. On some models (e.g. Gold SE)
  `publicIp`/`publicIps` can report a DNS resolver address (an Amazon Route 53
  IP in the reported case) instead of the actual WAN IP, while the WAN network
  entities carry the correct per-WAN IPv4. The primary WAN is the one with the
  lowest port number (e.g. `eth0` over `eth1`); `wan_ip` is the primary WAN's
  first IPv4 and `wan_ips` maps each WAN interface name to its first IPv4.
  IPv6 is intentionally not included here — it is surfaced per-network on the
  WAN network entities' `ipv6_addresses` attribute.
- App version and cloud instance are app-side/cloud-side and are **not**
  available from the local box init payload.

### Design notes

- `network_kind` (not `network_type`): the value is the derived granular
  discriminator from the category key. The box's raw `type` field is only
  `lan`/`wan` and is already modeled as `FirewallaNetworkSegmentView.network_type`.
- Keep entity naming kind-agnostic (no `ipv4`/`ipv6` in the unique-id or
  translation keys); the display name renders the kind acronym + network name
  (`Firewalla VLAN VLAN10 CORE Status`).
- A VLAN interface that a bridge references in `intf` is **transport** (e.g.
  `eth3.101` tags the `Guest` bridge), not a standalone network. Only VLANs no
  bridge references are user-facing `vlan` networks. This prevents duplicate
  entities for the same physical network (bridge + its tagging VLAN).
- `wlan` is a wireless WAN uplink only when `meta.type == "wan"`; a non-`wan`
  `wlan` entry (e.g. an AP-facing interface) is skipped, mirroring the `phy`
  WAN guard.

## Inventory-confirmed durable rule findings

This section records confirmed live runtime invariants derived from inventory
comparison and service-driven sparse mutations.

These findings are durable enough to guide implementation, but they are not all
backed by fresh packet captures in this document. Packet-level findings remain
in the findings matrix below.

For the long-term interpretation contract, see `docs/RULE_MODEL.md`.

### Shared persistent control invariants

The following rule families now show the same persistent pause or resume model:

- `allow`
- `block`
- `disturb`
- `qos`
- port-forwarding-flavored `allow`

Observed invariants:

- pause changes the existing rule in place
- pause sets `enabled = false`
- pause clears `activated_time`
- pause preserves `last_activated_time`
- pause advances `updated_time`
- pause populates raw `idleTs`
- resume changes the same rule in place
- resume sets `enabled = true`
- resume clears raw `idleTs`
- resume repopulates `activated_time`
- resume advances `last_activated_time`
- resume advances `updated_time`
- family-specific metadata survives pause and resume unless explicitly changed

### Current temporary-rule interpretation

Current live evidence supports the following distinction:

- `autoDeleteWhenExpires` alone is not enough to mark a rule as temporary
- the strongest current temporary signature is normalized `is_temporary = true`
  together with populated expiry metadata
- reliable expiry indicators include:
  - `expire_seconds`
  - `expires_at`
  - raw `expire`

### Current metadata surfaces

The following metadata groups are now confirmed and should be treated as
descriptive fields layered on top of shared control semantics.

| Metadata group | Representative fields | Interpretation |
| --- | --- | --- |
| Expiry | `expire_seconds`, `expires_at`, raw `expire`, `autoDeleteWhenExpires` | Temporary countdown context or durable timing hints depending on the full rule shape |
| Schedule | raw `cronTime`, raw `duration` | Recurring active-window metadata on durable advanced rules |
| Quota | raw `appTimeUsage`, raw `appTimeUsed` | Durable accounting and enforcement metadata |
| App-backed category | `TLX-fw-*`, `app_name`, `app_uid` | App identity layered on normal `allow` or `block` rule control |
| Disturb | `disturbLevel`, `disturbMethod.*` | Traffic-shaping metadata for disturb rules |
| QoS | `trafficDirection`, `priority`, `qdisc`, `rateLimit`, `app_name`, `app_uid` | QoS metadata on durable rules that still pause and resume in place |
| Port forwarding | `localPort`, `protocol`, `guids`, `userTargetList` | Port-forward context on durable rules that still pause and resume in place |

### App-rule interpretation note

Historical captures recorded an `app_block` action on a grouped app quota rule.

Newer live evidence also shows app-selected rules appearing as ordinary
category-backed `block` rules using `TLX-fw-*` targets plus `app_name` and
`app_uid` metadata.

Current interpretation:

- app identity should be treated as metadata, not proof of a separate baseline
  control family
- if `app_block` reappears in fresh captures, treat it as a specialized app
  enforcement shape rather than assuming all app rules use that action

### Rule ids are not durable across a delete and re-create

**Confirmed live on 2026-10-03.** Firewalla issues a **new `pid`** when a rule is
deleted and created again, even when the replacement is identical in every
visible field. A rule id is therefore only meaningful for as long as that specific
rule instance exists.

The integration turns on this: a rule-backed switch stores the rule id it was
created from (`source_rule_id`) and matches **by id, never by shape**. The
observable consequence, and the evidence from the dev box:

- config entry `Firewalla (192.168.200.129)` has one selected template:
  `source_rule_id: "551"`, name `route category Tiktok for VLAN60 IOT`,
  `action: "route"`, `target: "TLX-rt-tiktok"`, `target_type: "category"`,
  `tag_refs: ["intf:5d24cd11-8253-4557-bb6e-36f883a8e30b"]`
- rule `551` is **absent** from the live payload (321 rules)
- **no live rule matches it**: there are **zero `route` action rules** on the box,
  and **no `TLX-rt-` target of any kind**. The `TLX-fw-tiktok` rules that do exist
  are `block` rules for other groups — a different family entirely

So the rule was deleted and nothing equivalent remains. The switch is unavailable,
and the selection persists so the user can clean it up.

**Two consequences worth stating:**

- **Matching by shape would not have helped here.** There is no route rule at all,
  so a shape-based re-match would have nothing to find. Matching by id is not a
  limitation in this case; it is simply correct.
- **A stale selection is a first-class state, not a bug.** It means "this switch's
  rule no longer exists on the box", which is worth surfacing rather than silently
  dropping the entity.

**Not yet built:** a Home Assistant **repair** for the stale-selection case,
tracked as **issue #53**, recorded in the user guide as a planned improvement.

One note on the evidence above: this was observed on a **development box**, where
rules are turned on and off and deleted for testing far more often than on a real
installation, so stale selections accumulate there more readily. The behaviour is
still worth handling, because the same sequence — delete a rule, re-create it
identically, expect the switch to keep working — is a normal thing for any user to
do.

**This generalizes:** an id read from one call can belong to nothing on a later
call, and re-creating a rule does not restore its id. Anything that caches a rule
id across time must re-resolve rather than trust it.

### Per-rule hit data: `hitCount` and `lastHitFlow`

Confirmed live on 2026-10-03 against the dev box's init payload.

Every policy rule may carry two extra fields:

| Key | Meaning | Coverage on the dev box |
| --- | --- | --- |
| `hitCount` | times the rule has matched, as a **string** | 76 of 321 rules |
| `lastHitFlow` | the **most recent single match** | 54 of 321 rules |

`lastHitFlow` is a flat object. Fields, with their observed coverage across the
54 rules that had one:

| Field | Coverage | Meaning |
| --- | --- | --- |
| `ltype`, `type`, `ts`, `count`, `intf`, `protocol`, `port` | 54/54 | Always present |
| `device`, `deviceIP` | 54/54 | **The device the flow belonged to** |
| `fd` (direction), `devicePort`, `ip` | 47/47/47 | |
| `pid` | 28/54 | The originating rule id |
| `duration`, `apid`, `upload`, `download` | 26/54 | |
| `country`, `dIntf`, `dstMac`, `local`, `dTags` | 23/54 | |
| `host` | 19/54 | Resolved hostname |
| `tags`, `dstTags` | 16/54 | |
| `wanIntf`, `flowTags`, `category`, `app` | 9–15/54 | |
| `domain` | 7/54 | DNS match |
| `userTags` | 6/54 | |

**The destination arrives under one of three keys, and the set is exclusive in
practice:** `host` for a resolved connection, `domain` for a DNS match, and `ip`
when neither resolved. Normalize to one destination plus its kind rather than
leaving the caller to know which family produced it.

**It is a last-hit record, not a log.** Confirmed empirically: `ts` values on the
dev box ranged from **0.0 to 66.5 days** old on rules that were all currently
enabled. A rule's history is not recoverable locally; only its most recent match
is.

**Absent is not a distinct state for the count.** Of 321 rules: 54 carried both
fields, 22 carried `hitCount` only, **0** carried `lastHitFlow` only, and 245
carried neither — and 6 rules carried an **explicit `"0"`**. So the box both
omits the field and writes a zero, and the two are not distinguishable as
"never matched" versus "unknown". Normalized to `hit_count = 0` when absent,
which is honest for the visible rule set.

The one place that matters: **the omission correlates with rule family.** All 184
Device Active Protect rules (`purpose == 'dap'`) fall in the "neither" group and
none carry a count, so for those the field is untracked rather than zero. DAP
rules are excluded from `list_rules` by default, so a `0` is reliable within the
visible set but would be wrong if DAP rules were included.

The block case is the useful one. A `block` rule carrying a `lastHitFlow` names
the device and the destination that rule stopped, so "why can't this device reach
X?" is answerable by reading the rules governing the device and inspecting their
hits. On the dev box 27 `block` rules carried hit data.

**What remains offline:** the app's own UI does not offer a window beyond ~24
hours, and there is no per-rule history — only the most recent match. But a
**local flow *event* log does exist** and is queryable per tag or per host, up to
300 records per call with `nextTs` pagination. See *Flow reporting endpoints*
below. An earlier revision of this document claimed no local blocked-history
query existed; that was wrong.

Used by: `_normalize_rule_hit` in `api/client.py`, surfaced identically to the
`get_rules` service payload (`_serialize_rule_summary`) and to rule-backed switch
entities via the shared `build_rule_hit_attributes` in `models.py`.

Artifacts: `.tmp/survey_flows.py`, `.tmp/probe_flow_containers.py`,
`.tmp/probe_blocked_flows.py`, `.tmp/probe_hit_freshness.py`,
`.tmp/verify_rule_hits.py` (all read-only against the live box).

## Flow reporting and the local block log

**Confirmed by capture on 2026-10-03.** This is the local data behind the
Firewalla app's flow report, and it is **three distinct queries**, not one. All
are `mtype: "get"` with a `type` of `tag` or `host` and a `target` of the tag id
or the device MAC.

This section exists because an earlier revision of this document claimed no local
blocked-history query existed. That was wrong, and it was wrong for a specific
reason worth remembering: **the claim was inferred from the init payload alone**,
and flow reporting is not in the init payload at all. It is only visible by
capturing the app while it displays the report.

### The three queries at a glance

| Query | `item` | Target | Answers | Pagination |
| --- | --- | --- | --- | --- |
| **Rollup** | `tag` / `host` | tag id / MAC | top destinations, per-member ranking, byte totals | none (windowed) |
| **Event log** | `flows` | tag id / MAC | what was blocked, by which rule, for which device | `nextTs` |
| **Audit log** | `auditLogs` | tag id / MAC | same as `flows`, plus `category` / `ets` filters | `nextTs` |

**Drilling down switches the `type`, not just the target.** Selecting a member
inside a group changes `type` from `tag` to `host` and `target` from the tag id to
the device MAC. The same three queries serve both levels, so a group report and a
device report are the same code path with a different target.

### 1. The rollup — `item: "tag"` or `item: "host"`

```json
{"item": "tag", "apiVer": 2, "audit": true, "target": "31",
 "start": 1790949600, "end": 1791036000, "hourblock": 24}
```

This is the same family as the `systemFlows`-shaped data, and it is the one the
init payload caches. Its response carries:

- **`flows`** — the blocked breakdown, split into `dnsB`, `ipB:in`, `ipB:out`,
  `local:ipB:in`, `local:ipB:out`, plus `download` and `upload`. Each block holds
  a `flows[]` of **aggregated top destinations**:

  ```json
  {"host": "catalog.gamepass.com", "ip": "23.1.254.210", "port": ["443"],
   "count": "236214", "country": "FR", "category": "games", "device":
   "CC:28:AA:11:06:B7", "begin": 1790948400, "end": 1791034800,
   "flowTags": ["noise"]}
  ```

  This is the app's **"top destinations"** and **"top flows"**. Grouping is by
  `host`, so a subdomain is its own row — `ye2.c.lencr.org` rather than
  `lencr.org`, and `catalog.gamepass.com` rather than `gamepass.com`. That is the
  granularity distinction the app presents as two separate lists.
- **`hosts`** — **per-member attribution**, keyed by device MAC, each with its own
  byte and blocked totals. This is what drives "top download member in
  KADENS_DEVICES". Only populated on a `tag` request, which is exactly why a
  group or user report can rank members and a device report cannot.
- **`newLast24` / `last60` / `last30` / `last12Months`** — windowed totals, the
  same windows the `item=intf` payload uses.
- **`policy`**, **`name`**, **`uid`**, **`createTs`**.

### 2. The event log — `item: "flows"`

```json
{"item": "flows", "type": "tag", "target": "31", "audit": true,
 "count": 300, "ts": 1791036000, "exclude": []}
```

**This is the block log, and it is the most useful of the three.** Response:
`{count, flows[], nextTs}`. Verified live: **300 records per call**, and `nextTs`
feeds the next call's `ts` — the app paginates by walking `ts` backwards,
observed calling it three times in a row with descending `ts`.

`audit: true` restricts it to audit events, which is the "blocked only" filter in
the app's UI.

Each record names the rule that blocked it. Field coverage measured over a
300-row response:

| Field | Coverage | Meaning |
| --- | --- | --- |
| `device`, `deviceIP`, `tags`, `userTags`, `dTags` | 300/300 | Full attribution |
| `ts`, `count`, `port`, `protocol`, `intf`, `ltype` | 300/300 | `ltype: "audit"` |
| **`pid`** | **296/300** | **The blocking rule's id** |
| `type` | 296/300 | `dns` / `ip` |
| `domain` | 283/300 | DNS match |
| `flowTags` | 238/300 | `["noise"]` marks background traffic |
| `category`, `app` | 91 / 30 | When the box identified them |
| `host`, `ip`, `fd`, `devicePort` | 15–17/300 | Resolved connection detail |

Example record:

```json
{"ltype": "audit", "ts": 1791035437.587, "pid": 6, "type": "dns",
 "device": "CC:28:AA:11:06:B7", "deviceIP": "192.168.200.122",
 "domain": "graph.oculus.com", "port": 53, "protocol": "dns",
 "tags": ["31"], "userTags": ["32"], "dTags": ["1"],
 "flowTags": ["noise"], "count": 2,
 "intf": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2"}
```

**`pid` is the join back to `policyRules`**, so a blocked event can be attributed
to **the rule that caused it** — which the rollup cannot do. That makes the
chain complete: *device → membership → rules → the rule that blocked this flow →
the destination it blocked*.

### 3. The audit log — `item: "auditLogs"`

```json
{"item": "auditLogs", "type": "tag", "target": "31", "count": 300,
 "ts": 1791036000, "exclude": []}
```

Response: `{count, logs[], nextTs}`. Same pagination. Accepts two filters the
`flows` query does not: **`category`** (e.g. `games`) and **`ets`** (an end
bound), so a caller can narrow to one category or a sub-window without paging
through everything.

### What the time filter actually is

The app's window selector is **two separate parameters**:

- **`start` / `end`** — the window bounds, in epoch seconds
- **`hourblock`** — the granularity: `24` for the default 24-hour view, `1` after
  narrowing

Captured transitions on the same tag: `start=1790949600, end=1791036000,
hourblock=24` → `start=1791032400, end=1791036000, hourblock=1`. So narrowing
moved `start` forward and dropped `hourblock` to 1 in one step, which is why the
two must not be conflated.

**The app offers no window beyond about 24 hours.** The `start`/`end` parameters
may accept more, but nothing observed does, so a longer window is unverified —
see *Open questions*.

### Live data volume

Measured against the dev box for one group (`tag: 31`, KADENS_DEVICES):

- the rollup returned **6 blocked families** plus per-member rows
- one `flows` page returned **300 records**, and the app immediately asked for
  another

So a single "what was blocked" question is hundreds of records. Any surface built
on this must bound the response and lead with the summary, never dump the log.

### Artifacts

- `.tmp/firewalla_capture_20261003-135000_flow-reporting.pcap` — the capture,
  covering Payton's Devices (`tag: 29`), KADENS_DEVICES (`tag: 31`), several time
  filter changes, and a drill-down into `CC:28:AA:11:06:B7`
- `.tmp/firewalla_capture_20261003-132919_block-reporting.pcap` — the first
  attempt, which established the request shapes
- decoded with `.tmp/dump_all.py`, summarised by
  `.tmp/summarise_flow_capture.py`, record shapes via `.tmp/show_flow_records.py`
- `.artifacts/flow_reporting/20261003-134922/` and
  `.artifacts/block_reporting/20261003-132758/` — the accompanying pulls

## Findings matrix

This section is the durable record of confirmed findings. Update it after each
new capture.

### Finding 1: Timed category block create

Scenario:

- `AV_SMART_TV` -> `Social` -> `Block for 1 hour`

Observed mutation:

```json
{
  "item": "policy:create",
  "value": {
    "action": "block",
    "autoDeleteWhenExpires": "1",
    "dnsmasq_only": true,
    "expire": 3599,
    "scope": [],
    "tag": ["tag:17"],
    "target": "social",
    "type": "category",
    "updatedTime": 1774301777.038748,
    "useBf": true
  }
}
```

Result:

- created rule `743`
- rule is temporary
- timing fields present in normalized inventory
- the temporary rule family was later re-confirmed with a separate `Block for 1 minute`
  run that created rule `756`

Normalized characteristics:

- `target`: `social`
- `target_type`: `category`
- `tag_refs`: `tag:17`
- `dnsmasq_only`: `true`
- `auto_delete_when_expires`: `true`

Later confirmation run:

- action: `AV_SMART_TV` -> `Social` -> `Block for 1 minute`
- immediate inventory showed rule `756`
- normalized fields included:
  - `expire_seconds`: `51`
  - `auto_delete_when_expires`: `true`
  - `is_temporary`: `true`
- two minutes later, rule `756` was gone with no replacement rule added

Conclusion:

- short-duration quick-block actions create temporary rules
- those rules are separate from the persistent advanced-rule model
- they can disappear either because the user turns them off early or because
  Firewalla auto-removes them at expiry

### Finding 2: Timed category block off

Scenario:

- turn off the 1-hour social block created above

Observed mutation:

```json
{
  "item": "policy:delete",
  "value": {
    "policyID": "743"
  }
}
```

Result:

- removed rule `743`

Additional confirmation:

- the later one-minute run showed that a timed category rule can also disappear
  without an explicit off action
- rule `756` was present immediately after creation and absent two minutes later
- inventory diff for the expiry check was exactly one removed rule and zero added
  rules

### Finding 3: Persistent category block create

Scenario:

- `AV_SMART_TV` -> `Social` -> `Block`

Observed mutation:

```json
{
  "item": "policy:create",
  "value": {
    "action": "block",
    "appTimeUsage": {},
    "disturbLevel": "",
    "disturbMethod": {},
    "dnsmasq_only": true,
    "duration": "",
    "scope": [],
    "tag": ["tag:17"],
    "target": "social",
    "trust": "",
    "type": "category",
    "updatedTime": 1774303259.8190122,
    "useBf": true
  }
}
```

Result:

- created a persistent backing rule rather than a temporary countdown rule
- no `expire` field was present
- no `autoDeleteWhenExpires` field was present
- later re-confirmed with `Gaming` on `AV_SMART_TV`, which created rule `757`
  with the same persistent shape

Interpretation:

- the app appears to expose at least two different user actions behind similar
  block UI affordances
- `Block for 1 hour` behaves like a temporary rule create with expiration and
  auto-delete metadata
- `Block` or `Always block` behaves like creation of a persistent advanced rule
  that can later be paused or resumed in place

Working hypothesis:

- the early create-then-delete behavior was likely caused by testing the timed
  one-hour action rather than the persistent action
- this explains why early captures looked like pure create/delete while later
  captures for persistent rules converged on create once, then update in place

Later confirmation run:

- action: `AV_SMART_TV` -> `Gaming` -> `Block`
- baseline inventory had no `games` category rule for `AV_SMART_TV`
- immediate post-action inventory showed one added rule: `757`
- normalized fields for rule `757` were:
  - `label`: `block category games for AV_SMART_TV (enabled)`
  - `action`: `block`
  - `target`: `games`
  - `target_type`: `category`
  - `tag_refs`: `tag:17`
  - `enabled`: `true`
  - `purpose`: `null`
  - `expire_seconds`: `null`
  - `auto_delete_when_expires`: `null`
  - `is_temporary`: `false`

Conclusion:

- the persistent category-rule path creates a long-lived advanced rule with no
  expiry metadata
- this is distinct from the quick timed block flow, which creates a temporary
  auto-removing rule
- the remaining category-rule question is no longer create shape, but whether
  later off uses `policy:update`, `policy:delete`, or both depending on the UI
  path

### Finding 4: Persistent category rule explicit full delete

Scenario:

- delete the detailed persistent `games` category rule for `AV_SMART_TV`

Observed mutation:

```json
{
  "item": "policy:delete",
  "value": {
    "policyID": "758"
  }
}
```

Result:

- baseline inventory contained rule `758`
- post-delete inventory no longer contained rule `758`
- no replacement rule was added

Conclusion:

- explicit deletion of a persistent category rule uses `policy:delete`
- this matches the explicit delete path already observed for internet-block
  detailed rules
- this does not prove the normal off or pause path, only the full-delete path

### Finding 5: Network display names come from `networkConfig.interface` metadata

Scenario:

- network-backed rules in the init payload only exposed interface names such as
  `bond0.10` and `bond0.60` in `networkProfiles`
- local Redis inspection on the box showed richer names like `VLAN10 CORE` and
  `LAN-MGMT`

Observed local sources:

- init payload `networkProfiles[uuid].intf` contains stable interface ids such
  as `bond0.10`
- init payload `networkConfig.interface...meta.name` contains human-facing
  names such as `VLAN10 CORE`, `VLAN60 IOT`, and `LAN-MGMT`
- on-box Redis `sys:network:uuid[uuid]` confirms the same readable names via
  `name` and `desc`

Conclusion:

- the best network label already exists in the local init payload
- integration code should prefer `networkConfig.interface...meta.name`, then
  fall back to profile fields like `desc`, `name`, and finally `intf`
- direct `policy:network:<uuid>` hashes are not the naming source; they only
  carry policy state

Result:

- created rule `744`
- persistent rule

Normalized characteristics:

- `target`: `social`
- `target_type`: `category`
- `tag_refs`: `tag:17`
- `dnsmasq_only`: `true`
- currently modeled by the first implemented switch family

### Finding 4: Internet block create when absent

Scenario:

- `AV_SMART_TV` -> internet block `ON` from no existing internet-block rule

Observed mutation:

```json
{
  "item": "policy:create",
  "value": {
    "action": "block",
    "appTimeUsage": {},
    "disturbLevel": "",
    "disturbMethod": {},
    "dnsmasq_only": true,
    "duration": "",
    "scope": [],
    "tag": ["tag:17"],
    "target": "TAG",
    "trust": "",
    "type": "mac",
    "updatedTime": 1774308289.574883,
    "useBf": ""
  }
}
```

Result:

- created rule `748`

Normalized characteristics:

- label: `block internet for AV_SMART_TV (enabled)`
- `target`: `TAG`
- `target_type`: `mac`
- `tag_refs`: `tag:17`
- `dnsmasq_only`: `true`

Interpretation:

- internet block is a separate rule family from category rule blocks

### Finding 5: Internet block off from enabled state

Scenario:

- `AV_SMART_TV` internet block `OFF` when rule `748` exists and is enabled

Observed mutation:

```json
{
  "item": "policy:update",
  "value": {
    "action": "block",
    "appTimeUsage": {},
    "direction": "bidirection",
    "disabled": 1,
    "disturbLevel": "",
    "disturbMethod": {},
    "dnsmasq_only": true,
    "duration": "",
    "guids": [],
    "idleTs": "",
    "pid": "748",
    "tag": ["tag:17"],
    "target": "TAG",
    "timestamp": 1774308289.602,
    "trust": "",
    "type": "mac",
    "updatedTime": 1774308403.794945,
    "upnp": false,
    "useBf": ""
  }
}
```

Result:

- rule `748` remains present
- rule becomes disabled

Interpretation:

- off is not `policy:delete`
- internet block is a toggleable persistent rule family
- current evidence suggests the first enable may create a durable backing rule
  that remains in place afterward

### Finding 6: Internet block re-enable from disabled state

Scenario:

- `AV_SMART_TV` internet block `ON` when rule `748` exists and is disabled

Observed mutation:

```json
{
  "item": "policy:update",
  "value": {
    "action": "block",
    "activatedTime": "1774308289.71",
    "appTimeUsage": {},
    "direction": "bidirection",
    "disabled": 0,
    "disturbLevel": "",
    "disturbMethod": {},
    "dnsmasq_only": true,
    "duration": "",
    "guids": [],
    "idleTs": "",
    "lastActivatedTime": "1774308289.71",
    "pid": "748",
    "tag": ["tag:17"],
    "target": "TAG",
    "timestamp": "1774308289.602",
    "trust": "",
    "type": "mac",
    "updatedTime": 1774308562.633529,
    "upnp": false,
    "useBf": ""
  }
}
```

Result:

- rule `748` remains present
- rule becomes enabled again

Interpretation:

- re-enable uses in-place update semantics
- a future internet-block switch should prefer update-in-place when the rule is
  already present

### Finding 7: Internet-block UI lifecycle hypothesis

Scenario:

- before the first observed internet-block create, the Firewalla app presented
  the target as `Block: Off`
- after the first create for `AV_SMART_TV`, subsequent off and on actions
  operated on rule `748` with `policy:update` rather than removing it
- the user observed that the app then presents the state as `Block: Paused`
  rather than returning to `Block: Off`

Evidence level:

- partially confirmed by captures
- still a UI-model hypothesis rather than a complete protocol invariant

Confirmed protocol evidence behind the hypothesis:

- first internet-block enable created rule `748`
- turning internet block off did not delete rule `748`
- re-enabling internet block updated rule `748` in place

Current interpretation:

- the app likely uses `Off` for the pre-rule state
- once a persistent internet-block rule has been created for that target, the
  app may switch to an enabled or paused model backed by the same long-lived
  rule record
- this would explain why later toggles are `policy:update` operations instead of
  repeated create and delete cycles

### Finding 8: Standard internet rule shape behind the simple UI

Scenario:

- the user-visible easy-button internet block for `AV_SMART_TV` maps to the
  Firewalla rule shown in the detailed rules view as `Traffic from & to
  Internet`

Captured reference state:

- rule `750`
- label: `block internet for AV_SMART_TV (enabled)`
- `action`: `block`
- `target`: `TAG`
- `target_type`: `mac`
- `tag_refs`: `tag:17`
- `dnsmasq_only`: `true`
- `direction`: `bidirection`
- `is_temporary`: `false`

Interpretation:

- the simplified internet-block UI is a front end for a standard persistent
  detailed-rule record rather than a separate lightweight mechanism

### Finding 9: Internet block can be deleted and remain absent

Scenario:

- from the detailed rules workflow, delete the existing `Traffic from & to
  Internet` rule for `AV_SMART_TV`
- the capture is isolated so the app does not re-create the rule during the
  same observation window

Observed mutation:

```json
{
  "item": "policy:delete",
  "value": {
    "policyID": "750"
  }
}
```

Result:

- removed rule `750`
- no replacement internet-block rule for `AV_SMART_TV` was created in the
  post-action inventory

Interpretation:

- internet block supports a true delete path in addition to the pause or resume
  update path
- the earlier delete-then-create sequence was caused by the specific UI flow,
  not by a mandatory recreate behavior in the protocol

### Finding 10: Direct DNS allow timed pause uses in-place update

Scenario:

- pause `allow dns dns.google` for the rest of today from the Firewalla app
- this rule is a custom device-scoped allow rule tied to Kaden's Chromebook

Captured reference state before mutation:

- rule `640`
- label: `allow dns dns.google (enabled)`
- `action`: `allow`
- `target`: `dns.google`
- `target_type`: `dns`
- `scope`: `50:EB:71:B6:78:3A`
- `tag_refs`: none
- `dnsmasq_only`: `false`
- `direction`: `outbound`
- `is_temporary`: `false`

Observed mutation:

```json
{
  "item": "policy:update",
  "value": {
    "action": "allow",
    "activatedTime": "1766973301.076",
    "appTimeUsage": {},
    "direction": "outbound",
    "disabled": 1,
    "disturbLevel": "",
    "disturbMethod": {},
    "dnsmasq_only": false,
    "duration": "",
    "guids": [],
    "idleTs": 1774324800,
    "lastActivatedTime": "1766973301.076",
    "notes": "Device Kadens Chromebook (192.168.255.159) accessed dns.google on .",
    "pid": "640",
    "scope": ["50:EB:71:B6:78:3A"],
    "target": "dns.google",
    "timestamp": "1766973300.854",
    "trust": true,
    "type": "dns",
    "updatedTime": 1774310237.1027331,
    "upnp": false,
    "useBf": ""
  }
}
```

Result:

- rule `640` remains present
- rule `640` becomes disabled
- no replacement rule is created
- no temporary rule is added to inventory

Interpretation:

- a timed pause for this direct DNS allow rule uses in-place update semantics
- the pause boundary is carried by `idleTs`
- this rule family is not using create or delete for the observed pause action

### Finding 11: Direct DNS allow re-enable clears the pause marker in place

Scenario:

- re-enable the paused `allow dns dns.google` rule after the timed pause was
  applied

Captured evidence:

- the packet capture file fetched for this run was empty, so the exact decoded
  `policy:update` payload was not recovered
- the pre-action and post-action inventories still confirm the rule-state
  transition

Inventory result:

- rule `640` remains present before and after the action
- before re-enable:
  - label: `allow dns dns.google (disabled)`
  - `idleTs`: `1774324800`
  - no `activatedTime` field present in normalized extras
- after re-enable:
  - label: `allow dns dns.google (enabled)`
  - `idleTs`: empty string
  - `activatedTime`: `1774310416.666`
  - `lastActivatedTime`: `1774310416.666`

Interpretation:

- re-enable stays on the same rule ID and clears the pause boundary carried in
  `idleTs`
- the observed behavior is strongly consistent with an in-place `policy:update`
  similar to the previously captured internet-block re-enable flow
- this specific run should still be treated as inventory-confirmed rather than
  payload-confirmed until a non-empty packet capture is collected

### Finding 12: Direct DNS allow can be fully deleted

Scenario:

- delete the `allow dns dns.google` detailed rule for Kaden's Chromebook from
  the detailed rules view

Captured evidence:

- the packet capture file fetched for this run was empty, so the exact decoded
  delete payload was not recovered
- the pre-action and post-action inventories still confirm full removal of the
  rule

Inventory result:

- before delete:
  - rule `640`
  - label: `allow dns dns.google (enabled)`
  - `scope`: `50:EB:71:B6:78:3A`
- after delete:
  - no `dns.google` rule remains in inventory
  - no replacement rule was created during the observation window

Interpretation:

- this direct DNS allow rule supports a true delete path in addition to the
  previously observed timed pause and re-enable behavior
- based on the inventory delta, the expected protocol operation is
  `policy:delete`, but this run should still be treated as inventory-confirmed
  rather than payload-confirmed until a non-empty capture is collected

### Finding 13: Tag-scoped direct DNS allow timed pause uses the same in-place pattern

Scenario:

- pause `allow dns spotify.com for KADEN's Devices (KADEN)` for the rest of
  today

Captured evidence:

- the packet capture for this specific pause run was not usable because the
  Firewalla box had no free space left under `/tmp`
- the pre-action and post-action inventories still confirm the rule-state
  transition

Inventory result:

- rule `211` remains present before and after the action
- before pause:
  - label: `allow dns spotify.com for KADEN's Devices (KADEN) (enabled)`
  - `tag_refs`: `tag:10`
  - `idleTs`: empty string
- after pause:
  - label: `allow dns spotify.com for KADEN's Devices (KADEN) (disabled)`
  - `tag_refs`: `tag:10`
  - `idleTs`: `1774324800`

Interpretation:

- the tag-scoped Spotify rule follows the same observed timed-pause pattern as
  the device-scoped `dns.google` rule
- the rule stays in place, becomes disabled, and carries the pause boundary in
  `idleTs`

### Finding 14: Tag-scoped direct DNS allow re-enable uses in-place update

Scenario:

- re-enable the paused `allow dns spotify.com for KADEN's Devices (KADEN)` rule

Observed mutation:

```json
{
  "item": "policy:update",
  "value": {
    "action": "allow",
    "activatedTime": "1693953160.558",
    "appTimeUsage": {},
    "direction": "outbound",
    "disabled": 0,
    "disturbLevel": "",
    "disturbMethod": {},
    "dnsmasq_only": false,
    "duration": "",
    "guids": [],
    "idleTs": "",
    "lastActivatedTime": "1693953160.558",
    "notes": "",
    "pid": "211",
    "protocol": "",
    "tag": ["tag:10"],
    "target": "spotify.com",
    "targetList": "",
    "timestamp": "1693953160.462",
    "trust": true,
    "type": "dns",
    "updatedTime": 1774310993.8565822,
    "upnp": false,
    "useBf": ""
  }
}
```

Result:

- rule `211` remains present
- rule becomes enabled again
- `idleTs` is cleared back to an empty string

Interpretation:

- tag-scoped direct DNS allow re-enable is payload-confirmed as an in-place
  `policy:update`
- the observed allow-rule shape now matches the device-scoped `dns.google`
  family closely, with scope carried either by `scope` or `tag`

## Implementation impact summary

The current evidence supports at least two switch-control strategies and one
important nuance around internet-rule removal.

### Strategy A: Category-rule switches

Use for category rules such as `block social for AV_SMART_TV`.

- temporary quick-block actions create rules with `expire` and
  `autoDeleteWhenExpires`
- persistent detailed rules create long-lived rules with no expiry fields
- explicit removal of a persistent detailed rule uses `policy:delete`
- the normal off or pause path for a persistent category rule is still not
  cleanly captured in this document

### Strategy B: Internet-block switches

Use for tag-targeted internet block rules such as
`block internet for AV_SMART_TV`.

- create when turned on and absent
- update with `disabled: 1` when turned off
- update with `disabled: 0` when turned on from disabled state
- delete when the user removes the backing detailed rule entirely

Implementation note:

- a future switch implementation should treat pause or resume and explicit rule
  deletion as separate actions
- the standard toggle UX should continue to model the pause or resume path,
  while inventory refresh must also tolerate the backing rule disappearing

### Strategy C: Direct DNS allow rules

Use for direct DNS allow rules such as `allow dns dns.google`.

- update with `disabled: 1` for the observed timed pause action
- carry the pause boundary in `idleTs`
- keep the same rule ID in place during the pause
- re-enable on the same rule ID and clear `idleTs`
- fully delete when the backing detailed rule is removed

Observed scope variants:

- device-scoped via `scope`
- tag-scoped via `tag`

Implementation note:

- this family may need separate handling from category-rule delete semantics
- re-enable and full deletion behavior are still not confirmed

## Next capture targets

### Internet quality (ping latency / packet loss)

**Resolved (2026-09-10):** The read contract is confirmed from a live pull. See
Finding 25 for the exact `get`/`networkMonitorData` shape and value granularity.
No further capture is required for the per-WAN ping latency and packet-loss
sensors or the interval report.

### Direct DNS rules

The next protocol family to confirm is direct DNS rules.

Priority order:

- direct DNS block rules with `dnsmasq_only: true`
- direct DNS allow rules with `dnsmasq_only: false`
- scoped direct DNS allow rules with `tag:` or `intf:` references

Current examples from live inventory:

- `block dns vin13.pbs.ovhnextmillmedia.com`
- `block dns recordedthereby.com`
- `allow dns dns.google`
- `allow dns proxmox.com for PVE`

Questions to answer for this family:

- whether off uses `policy:delete` or `policy:update`
- whether block and allow differ in lifecycle behavior
- whether scoped and unscoped DNS rules share the same mutation contract
- capture the exact re-enable payload for a timed-paused direct DNS rule
- capture the exact delete payload for a device-scoped direct DNS allow rule

### AP7 wireless SSID pause

**Resolved (2026-09-03):** The write contract is now confirmed from a packet
capture. See Finding 24 for the exact `set`/`networkConfig` contract. No
further capture is required for the SSID pause toggle.

Remaining wireless capture opportunities (not required for the toggle):

- per-AP `pauseWifi` / LED control (the `fwapcOps` surface — see Finding 24)
- `stationControls` band-steering / banned-AP control
- channel/band changes

### Group and user membership

**Group membership resolved (2026-10-02):** See Finding 41. Group membership is
a host-scoped `set` on `item: "policy"` writing `value.tags`; no further
capture is required for group add/remove.

**User membership resolved (2026-10-02):** See Finding 42. Device-to-user
assignment is **cloud-mediated** in the app (`firewalla.encipher.io`), but it
lands on the box as the user's **affiliated backing tag** in `host.tags` — the
same shape as a group write. **A local write path is confirmed working**: the
existing host-scoped `set item=policy value.tags=[<affiliated tag>]` assigns a
user directly. No further capture is required for the user path.

**Rule handling on a membership change resolved (2026-10-03):** See Finding 43.
A membership change deletes the rules attached to the device — set or clear,
group or user — ahead of the tags write, in one batch. No further capture needed.

### Flow reporting

**Resolved (2026-10-03):** the three flow-reporting queries are captured and
documented in *Flow reporting and the local block log*. The request shapes, the
response shapes, the pagination and the window parameters are all confirmed.

**Still open:** whether `start`/`end` accept a window longer than the ~24 hours
the app's own UI offers. Confirming needs a widened capture, because a longer
window is not reachable through the UI.

## Open questions

These items remain unconfirmed and should stay visible.

- whether all internet-block rules share the same `target: TAG` and
  `type: mac` contract across other scopes such as users, networks, and other
  groups
- confirm the full persistent category-rule lifecycle for `Always block`,
  especially whether later off uses `policy:update`, `policy:delete`, or a mixed
  contract depending on the UI path
- whether the app permanently transitions an internet-block target from an
  initial `Off` state to a persistent `Paused` or enabled state model after the
  first create, with no later purge of the backing rule under normal UI usage
- whether direct DNS rules use `policy:delete`, `policy:update`, or a mixed
  lifecycle depending on block versus allow
- whether device-scoped and tag-scoped direct DNS allow rules share the same
  delete payload shape
- whether re-enabling a timed-paused direct DNS rule uses the same payload shape
  as internet-block re-enable, in addition to clearing `idleTs`
- whether the box fires the `host:syncAppTimeUsageToTags` follow-up on its own
  after a local membership write, or whether the app must send it
- whether the Firewalla cloud later reconciles or reverts an affiliated tag
  written locally, rather than through the app
- ~~whether the app always sends the full host policy object on membership
  changes, and whether it always sweeps disabled device-scoped rules on remove~~
  — **answered in Finding 43.** The app sends the full 16-key policy object but the
  box does not require it (a `tags`-only write keeps every other key). On a rule
  removal the app deletes **every** rule the device owns — not only disabled ones,
  and not only `dap` — ahead of the tags write, in the same batch
- whether `flows` / `auditLogs` / `tag` accept a `start`/`end` window wider than
  the ~24 hours the app's UI offers, and whether `hourblock` scales beyond 24
  (daily granularity) — the app exposes no such control, so this needs a direct
  probe rather than a UI capture
- whether the `flows` pagination has a depth limit, or whether `nextTs` will walk
  back through retained history indefinitely. The box clearly retains some, but
  the retention horizon is unknown
- how long the box retains flow events at all. This determines whether the event
  log can answer "last week" or only "last day"
- whether `exclude` on `flows` / `auditLogs` filters out specific categories or
  devices: it was sent empty in every capture, so its accepted values are unknown

## AP7 wireless controller findings

The following findings were derived from live diagnostic captures submitted by
a reporter with two Firewalla AP7 access points and confirmed by a live
`get_wireless_status` service readback.

### Finding 19: AP7 wireless config lives in `networkConfig.apc`

**Scenario:**

- reporter with 2 Firewalla AP7s (both `fwap-D`, "Main Floor" and "Upstairs")
  submitted two extended diagnostic captures — one with the guest SSID enabled,
  one with it disabled — using the integration's extended diagnostic download.
- A full recursive diff of the `networkConfig.apc` section between the two
  captures showed **exactly one change**: the `paused` field on the guest SSID
  profile (`f185dc47-2730-48a8-844c-b57aa31af4ba`) was `true` when off and
  absent when on.
- The live `get_wireless_status` service (alpha.7) confirmed the read model
  against the reporter's box.

**Artifacts:**

- `.artifacts/ap7-wireless-discovery/ap7_wifi_on.json`
- `.artifacts/ap7-wireless-discovery/ap7_wifi_off.json`
- `.artifacts/ap7-wireless-discovery/get_wireless_status_alpha7.txt`

**Confirmed `networkConfig.apc` structure:**

| Section | Contents | Confirmation level |
| --- | --- | --- |
| `assets` | Per-AP config: `name`, `model` (`fwap-D`), `channel.5g`, `channel.2g`, `txPower`, `country`, `meshMode`, `led`, `pauseWifi`, `disableAcl`, `timezone`, `publicKey` | **High** — from live readback |
| `assets_template.ap_default.wifiNetworks` | SSID-to-network mapping: `intf`, `vlan`, `ssidProfiles` (UUID list), `dhcp`, `isolate` | **High** — from live readback |
| `assets_template.ap_default.mesh` | Mesh backhaul: `ssid`, `key`, `encryption` | **High** — from capture |
| `profile` | Per-SSID config keyed by UUID: `ssid`, `key`, `band`, `encryption`, `wpa3`, `paused` | **High** — toggle confirmed by on/off diff |
| `globalSysConfig` | Global AP settings: `autoSteer`, `maxComp`, `stormControl`, `useDfsChannels`, `stp`, `lldpd`, `flowControl` | **Medium** — observed but untoggled |

**Observed field values from live readback:**

| Profile UUID | SSID | VLAN | Interface | Band | Paused state |
| --- | --- | --- | --- | --- | --- |
| `cca57d09-...` | Universe | — | br0 | 2.4g+5g+6g | false |
| `f185dc47-...` | Universe Guest | 100 | br1 | 2.4g+5g+6g | **toggled** |
| `6510fea4-...` | Universe IoT | 200 | br2 | 2.4g+5g+6g | false |

| AP asset ID | Name | Model | 5g channel | 2g channel | LED |
| --- | --- | --- | --- | --- | --- |
| `20:6D:31:71:1D:D0` | Main Floor | fwap-D | 149 | 1 | off |
| `20:6D:31:71:55:5C` | Upstairs | fwap-D | 36 | 11 | off |

**Toggle control:**

The wireless on/off toggle for one SSID is the `paused` field on its profile
entry. When `paused` is `true` (or present), the SSID is disabled. When the
field is absent (or `false`), the SSID is enabled.

**Write contract — confirmed (2026-09-03):**

The write contract was confirmed from a packet capture of the app toggling a
wireless network. The app sends a `set` message with `item: "networkConfig"`
carrying the **full** `networkConfig` object (not just `apc`). See Finding 24
for the exact contract.

**Redaction fidelity note:**

The `assets` dict in `networkConfig.apc` is keyed by MAC address. Because the
diagnostic redaction helper replaces MAC-pattern dict keys with `**REDACTED**`,
multiple AP entries are collapsed into one in the redacted diagnostic. The live
service is unaffected. See `helpers/init_payload_redaction.py`.

### Finding 20: AP7 devices are not `connection_type=ap` hosts in the normalized snapshot

The reporter's Firewalla AP7s ("Main Floor" at 192.168.1.3, "Upstairs" at
192.168.1.4) appeared in the normalized `runtime_snapshot.hosts` with
`connection_type=None` and `host_device_type=None`, not with `connection_type
= "ap"` as previously assumed. The earlier `connection_type=ap` entries were
Aruba InstantOn AP22 units that have since been removed.

The AP7s also appear as `wg_peer` hosts with `intf=wg_ap` for their mesh
backhaul connection, and have dedicated entries in `networkConfig.apc.assets`
identified by their MAC address key.

### Finding 24: AP7 wireless SSID pause write contract is a `set` on the full `networkConfig`

**Scenario:**

- The reporter ran the capture tool on Linux (after fixing two script bugs in
  `tools/support/capture_firewalla_packets.py` — see the supporting note §7.1)
  and submitted a decrypted `analysis.json` + safe report zip on 2026-09-03.
- The capture contains the app toggling "Universe Guest" off then on. The two
  `set` writes differ **only** in the `paused` field on the guest profile
  (`f185dc47-2730-48a8-844c-b57aa31af4ba`): `paused: true` to pause, absent to
  resume.
- The box **accepted** both writes: `code=200` with `data: {"ncid": "<id>"}`
  (a network-config id acknowledgment) — not the code 500 from the earlier
  guessed patterns.

**Artifacts:**

- `.tmp/wifi_toggle_capture_20260903/analysis.json`
- `.tmp/wifi_toggle_capture_20260903/safe_report.zip`

**Confirmed write contract:**

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

**Key differences from the earlier guessed `set_networkconfig` pattern:**

1. `value` must be `{"config": {...}}` — the full `networkConfig` object
   (16 keys: `mroute`, `nat`, `routing`, `icmp`, `nat_passthrough`, `dhcp`,
   `version`, `hostapd`, `dns`, `apc`, `upnp`, `app`, `interface`,
   `mdns_reflector`, `sshd`, `ts`), not `{"apc": apc_payload}`.
2. `config.ts` is required — a fresh epoch-millisecond timestamp.
3. `data` includes `COMMAND_TIMEOUT: 90` and `LAN_ONLY: 1` alongside
   `item`/`value`.
4. The `paused` mutation (true to pause, absent to resume) is confirmed correct.

**AP-controller operation surface (`fwapcOps`):**

The init request also carries `fwapcOps` — AP-controller HTTP operations whose
responses are embedded in the init response:

| Op | Path | Returns |
| --- | --- | --- |
| `stationControls` | `GET /config/stations` | Per-client band-steering / banned-AP policy (`bannedAPs`, `mode`) |
| `switchTopology` | `GET /status/wired_station` | Full network topology tree — every device (wired + wireless) with `rssi`, `band`, `ssid`, `parent_port`, `connectionType`, `type` (`device`/`ap`) |
| `switchInfo` | `GET /status/switch` | Switch info (empty in this capture) |
| `fwapcCountry` | `GET /config/country` | Country config (`{"model": "purple"}`) |

This surface is useful for future per-AP status/control (e.g. `pauseWifi`,
LED) and for per-client wireless connection attributes (`rssi`, `band`,
`ssid`, `parent_port`). The integration already requests these ops during
pairing/init (`api/client.py`), but the returned data is not yet parsed into
the normalized model.

### Finding 25: Internet quality is a `networkMonitorData` read with per-WAN ping samples

**Scenario:**

- Confirmed via a live pull (`utils/probe_internet_quality.py`) on the connected
  dev box (2026-09-10) using the stored HA config-entry credentials.
- The app's per-WAN **Internet Quality** view (ping latency and packet loss)
  maps to a single `mtype=get, item=networkMonitorData` read.

**Confirmed read contract:**

```
mtype: get
target: 0.0.0.0
data:
  item: networkMonitorData
  value: {}
```

**Confirmed response shape:**

- Top-level dict keyed by `metric:monitor:raw:ping:<target>:<wan_uuid>` — one
  key per WAN+target, so a **single call returns all WANs** (no per-WAN fan-out).
- Each value is a dict of **epoch-second buckets** (15-minute cadence) whose
  `stat` holds:
  - `lossrate` — a **fraction** (0 = 0%, `0.0017` = 0.17%, `0.165` = 16.5%);
    multiply by 100 for a percentage.
  - `max`, `mean`, `median`, `min` — latency in **milliseconds**.
- Returns roughly **24 hours of history** (98 samples in the probe), so a single
  call serves both the latest-sample sensors and an interval report.

**`events` ping feed (alerting, not sampling):**

- `mtype=get, item=events` filtered to `ping_RTT` / `ping_lossrate` returns
  **threshold-crossing alerts** (only fire when loss/RTT exceeds the limit),
  not a continuous sample stream. It is **not** the sensor source.

**Value granularity notes:**

- The app's hourly drill-down shows the **worst (max) sub-bucket**, not the
  average. The integration surfaces raw 15-minute samples and does **not**
  reproduce that hourly roll-up.

**Artifacts:**

- `.tmp/quality_networkMonitorData.json`
- `.tmp/quality_events.json`

## Additional host-settings findings

### Finding 15: DHCP reservations, notification toggles, device type feedback, and Wake-on-LAN are host-scoped actions

Scenario:

- one mixed app session on a single host performed these actions in sequence:
  - changed IP assignment from dynamic to reserved
  - changed the reserved IPv4 address
  - changed the device type from phone to tablet
  - toggled notify when next online and notify when next offline
  - sent Wake-on-LAN

Artifacts:

- `.tmp/firewalla_dhcp_mixed_actions_capture.pcap`
- `.tmp/firewalla_dhcp_mixed_actions_capture.decoded.txt`
- pre-capture runtime pull: `.artifacts/runtime-pull/20260331-022009/`
- post-capture runtime pull: `.artifacts/runtime-pull/20260331-022718/`

Observed DHCP configuration read model:

- steady-state DHCP configuration is readable from `networkConfig.dhcp`
- per-interface entries currently expose:
  - `gateway`
  - `subnetMask`
  - `lease`
  - `range.from`
  - `range.to`
  - `nameservers`
  - `searchDomain`
  - optional `extraOptions`

Observed reservation mutation:

```json
{
  "item": "policy",
  "target": "74:42:18:08:D2:8D",
  "value": {
    "ipAllocation": {
      "allocations": {
        "d7e5a5c4-0b28-4010-b3c6-dad1a868693f": {
          "ipv4": "192.168.202.102",
          "type": "static"
        }
      }
    }
  }
}
```

Observed reservation storage model:

- reserved-IP state did not move `networkConfig.dhcp`
- reserved-IP ownership is stored per host under:
  - `host.policy.ipAllocation.allocations[<network_or_interface_uuid>]`
- allocation entries currently carry:
  - `type`, such as `static` or `dynamic`
  - `ipv4` when the allocation is static

Observed device-type feedback mutation:

```json
{
  "item": "feedback",
  "value": {
    "key": "device.detect",
    "target": "74:42:18:08:D2:8D",
    "value": {
      "type": "tablet"
    }
  }
}
```

Observed notification mutations:

- notify when next online is carried by host policy boolean `devicePresence`
- notify when next offline is carried by host policy boolean `deviceOffline`

Observed Wake-on-LAN mutation:

```json
{
  "item": "wol:wake"
}
```

Result:

- DHCP range details are segment-scoped configuration data from `networkConfig.dhcp`
- reserved-IP state, notification toggles, and Wake-on-LAN are host-scoped surfaces
- device-type changes are written through the feedback path rather than the host
  policy path

Implementation impact:

- a future network-segment report can safely expose DHCP ranges from
  `networkConfig.dhcp`
- host detail inside that report can safely expose:
  - IP assignment mode derived from host policy allocations
  - reserved IPv4 when present
  - device-type feedback when present
  - notification toggle state from host policy
  - Wake-on-LAN capability or support as a host-facing action affordance
- future services for reservation updates, notification toggles, and
  Wake-on-LAN should be modeled as host-targeted actions, not segment-targeted
  DHCP mutations

### Finding 16: Host rename uses a host-scoped `item=host` write with a null acknowledgement

Scenario:

- renamed host `74:42:18:08:D2:8D` from the official Firewalla app

Artifacts:

- `.tmp/firewalla_host_rename_capture.pcap`
- `.tmp/firewalla_host_rename_capture.decoded.txt`
- pre-action inventory: `.tmp/capture_host_rename_before.json`
- post-action inventory: `.tmp/capture_host_rename_after.json`

Observed rename mutation:

```json
{
  "item": "host",
  "target": "74:42:18:08:D2:8D",
  "value": {
    "name": "Carens Phone 1"
  }
}
```

Transport details:

- outer message type: `set`
- target identifier: host MAC address
- response shape for the captured write: decrypted `code=200` with `data=null`

Observed follow-up read behavior:

- a nearby app read used `mtype=get`, `target=74:42:18:08:D2:8D`, and
  `data={"item":"host",...}`
- the standard runtime init payload consumed by the current integration did not
  immediately expose the renamed value in the fields currently used for host
  display-name normalization at capture time

Conclusion:

- host rename is a host-scoped write distinct from the host policy path
- the mutation contract is low-ambiguity enough to implement a dedicated host
  rename service
- the write acknowledgement path must tolerate `null` response data
- the read model still needs separate confirmation before the integration can
  promise immediate renamed-state readback after the write

### Finding 17: Host identity readback exposes separate human-facing, DNS, and DHCP naming fields

Scenario:

- compared steady-state runtime pulls taken before and after host-focused app
  actions, alongside the raw host records returned in the local init payload

Artifacts:

- `.artifacts/runtime-pull/20260331-022009/`
- `.artifacts/runtime-pull/20260331-022718/`

Observed host identity read model:

- host records can expose multiple naming-related fields at the same time
- currently observed raw fields include:
  - `bname` for the primary human-facing label shown in the app
  - `name` for the DNS-oriented hostname label
  - `dhcpName` for the DHCP-origin hostname value when present
  - `bonjourName` for the Bonjour-discovered hostname value when present
  - `localDomain` for the host-local fully qualified DNS name when present
- segment DHCP configuration exposes `searchDomain` under
  `networkConfig.dhcp[<interface_name>]`

Observed classification read model:

- host classification can be read back from host detect or feedback data
- the normalized write path observed in Finding 15 uses feedback key
  `device.detect` with nested field `value.type`

Implementation impact:

- the integration should keep host identity fields separate in the normalized
  model instead of flattening them into one display-name convenience field
- `host_name` should represent the primary human-facing Firewalla label
- `dns_hostname`, `dns_domain`, and `dns_fqdn` should remain explicit DNS
  surfaces
- `dhcp_name` should remain a provenance-specific DHCP field rather than a
  fallback alias for `host_name`
- `host_device_type` should remain the normalized Firewalla host
  classification field surfaced from detect or feedback data

### Finding 18: Host DNS override uses a host-scoped `item=hostDomain` write, while host rename still uses `item=host`

Scenario:

- changed host classification, host label, and DNS hostname for host
  `4C:1D:96:E3:3A:96` from the official Firewalla app while the phone was on
  the same Wi-Fi segment as the Firewalla box

Artifacts:

- `.tmp/paytons_chromebook_dns_capture.pcap`
- `.tmp/paytons_chromebook_dns_capture.decoded.txt`
- post-action runtime pull: `.artifacts/runtime-pull/20260414-182650/`

Observed mutations:

```json
{
  "item": "feedback",
  "value": {
    "key": "device.detect",
    "target": "4C:1D:96:E3:3A:96",
    "value": {
      "type": "tablet"
    }
  }
}
```

```json
{
  "item": "host",
  "target": "4C:1D:96:E3:3A:96",
  "value": {
    "name": "Paytons Chromebook 2"
  }
}
```

```json
{
  "item": "hostDomain",
  "target": "4C:1D:96:E3:3A:96",
  "value": {
    "customizeDomainName": "paytons.chromebook.3"
  }
}
```

```json
{
  "item": "host",
  "target": "4C:1D:96:E3:3A:96",
  "value": {
    "name": "Paytons Chromebook 4"
  }
}
```

Transport details:

- all four mutations used outer message type `set`
- the host classification write remained targetless at the outer level and
  carried the host MAC under `value.target`
- both host label and host DNS override writes targeted the host MAC directly
- all captured mutation responses acknowledged with decrypted `code=None` and
  `data=null`

Observed readback behavior after the sequence:

- `detect.feedback.type` read back as `tablet`
- `detect.type` still read back as `desktop`
- `name` read back as `Paytons Chromebook 4`
- `localDomain` read back as `paytons.chromebook.4`
- `userLocalDomain` read back as `paytons.chromebook.3`

Conclusion:

- host DNS override is a distinct host-scoped write and does not reuse the
  generic host rename payload
- the local runtime write contract for DNS override is `item=hostDomain` with
  nested field `value.customizeDomainName`
- a later host rename can still update `localDomain` even when an explicit DNS
  override is present
- the explicit DNS override currently reads back separately in
  `userLocalDomain`, so the integration should model that field separately from
  the observed `localDomain`
- host device type should continue to normalize from `detect.feedback.type`
  first, because `detect.type` may remain the vendor or classifier default

### Finding 21: The init request can include inactive hosts via `includeInactiveHosts`

Scenario:

- user observed that devices configured in Firewalla but inactive for a period
  were reported as unavailable by the Home Assistant device tracker, while the
  Firewalla app only showed them after enabling the "Show past devices" toggle

Artifacts:

- `.tmp/show_past_devices.pcap` — packet capture of the iOS app toggling
  "Show past devices" on port 8833
- direct live probe against the box using the Home Assistant config entry
  credentials

Observed init request:

- baseline init request (`get: "0.0.0.0"` only) returned 155 hosts and omitted
  the inactive devices
- with `"includeInactiveHosts": true` added to the init `data`, the box
  returned 224 hosts and included the previously-missing inactive devices

Confirmed:

```json
{
  "get": "0.0.0.0",
  "includeInactiveHosts": true
}
```

Result:

- the device-tracker hosts that had dropped out of the runtime inventory become
  present in the snapshot so the integration can keep them associated with
  their configured trackers and names
- hosts that are present but inactive are still classified by the existing
  `stale` and activity-window logic, so they report `not_home` rather than
  `home`

Normalized characteristics:

- `includeInactiveHosts` is a top-level boolean field in the init `data`
  object, set to `true` to request the full host inventory including devices
  the Firewalla box otherwise filters out
- the app surfaces this behavior as "Show past devices", which lists devices
  that have not been online for the past 7 days
- the integration always sends `includeInactiveHosts: true` so its host
  inventory matches the full set rather than only recently-active devices

### Finding 22: Host deletion uses a `cmd` message with `item=host:delete`

Scenario:

- deleted one host device from the Firewalla mobile app (iOS) while mobile data
  was disabled so the phone's traffic was confined to the local WiFi

Artifacts:

- `.tmp/delete_host_capture.pcap` — packet capture of the iOS app deleting a
  host on port 8833

Observed mutation:

```json
{
  "mtype": "cmd",
  "target": "0.0.0.0",
  "data": {
    "value": {
      "mac": "12:A9:78:EB:EA:02"
    },
    "item": "host:delete"
  }
}
```

Result:

- the host with the given MAC (`12:A9:78:EB:EA:02` in the capture) was removed
  from the device inventory

Normalized characteristics:

- `host:delete` is a `cmd` message (not `set`), matching the mutation pattern
  used by other host commands such as `wol:wake`
- the outer `target` is `0.0.0.0` (box-level), like other `cmd` mutations
- `value` carries only the host `mac` to delete; no IP, hostname, or device type
  is included
- the delete is a single message; the `batchAction` and `init` requests the app
  sends afterward are data refreshes for usage/inventory, not part of the
  deletion mutation

Implementation impact:

- a host-delete service should send a `cmd` message with
  `item: "host:delete"` and `value: {"mac": "<host-mac>"}` targeting
  `0.0.0.0`, matching the existing manager-owned mutation pattern

### Finding 23: Router-Mode LANs can be `bridge` interfaces (not only `bond`)

Scenario:

- a user's Gold SE in Router Mode reported network entities with wrong names
  (`br0`, `br1`, …) and empty ports; a diagnostic download showed all LAN
  networks defined as `bridge` interfaces, and a wireless `wlan` WAN uplink
- the initial reverse-engineering capture (Finding 5) only documented the
  `bond` layout (LAN-MGMT as a LAG of `eth2`+`eth3`, VLANs riding `bond0.10`)
- the new diagnostic proved a second, equally valid Router-Mode topology: LANs
  defined as per-network `bridge` interfaces carrying direct ports and/or
  tagged VLAN members directly

Observed local sources (user diagnostic `runtime_init_payload`):

- `networkConfig.interface.bridge` — `br0`..`br4` with `meta.name` = `Mgmt`,
  `Guest`, `Home`, `VoIP`, `IoT`, `meta.type` = `lan`, and `intf` listing
  direct ports and/or tagged VLAN members:
  - `br0` Mgmt → `intf: ["eth2", "eth3"]`
  - `br1` Guest → `intf: ["eth3.101"]`
  - `br3` Home → `intf: ["eth3.100"]`
  - `br2` VoIP → `intf: ["eth1.102", "eth3.102"]`
  - `br4` IoT → `intf: ["eth3.103"]`
- `networkConfig.interface.vlan` — `eth3.100`..`eth3.103`, `eth1.102` are the
  tagged members behind those bridges (`vid`, `intf: "eth3"`/`"eth1"`)
- `networkConfig.interface.wlan.wlan0` — `meta.name` = `Wireless`,
  `meta.type` = `wan`, carrying `wpaSupplicant` (SSID/PSK) — a wireless WAN
  uplink, not a wireless LAN AP
- `networkConfig.nat` — per-bridge rules `br0-eth0`..`br4-eth0` (each LAN NAT'd
  out through the WAN `eth0`) — confirms Router Mode (Firewalla does NAT)
- `networkConfig.dhcp`/`mdns_reflector`/`icmp` — keyed by the bridge interface
  names (`br0`..`br4`), so advanced options and DHCP are per-bridge

Conclusion:

- Router-Mode boxes define LANs either as a LAG **`bond`** or as per-network
  **`bridge`** interfaces; both are `lan`-kind networks and must be collected
- a `bridge`'s `intf` members are dereferenced through parent chains (bridge →
  tagged VLAN → physical port) to concrete ports, e.g. `br2` VoIP →
  `eth1`+`eth3`
- a VLAN interface that a bridge references in `intf` is **transport** for that
  bridge (e.g. `eth3.101` tags the `Guest` bridge) and is **not** surfaced as
  its own `vlan` network; only VLANs no bridge references are standalone VLANs
- a `wlan` entry is a wireless WAN uplink and maps to `wan` **only** when
  `meta.type == "wan"`; a non-`wan` `wlan` entry is skipped, mirroring the
  `phy` WAN guard
- entity `unique_id`s are uuid-based (`network_<uuid>`), and the bridge uuids
  are identical whether the network is collected from the registry or the
  `networkProfiles` fallback, so fixing the collection does not churn existing
  registry entries — only the display name/ports update

### Finding 41: Group membership is a host-scoped `set` on `item: policy` writing `value.tags`

**Scenario:**

- One app session on a single host (the test device, MAC `<device-mac>`)
  performed two membership actions in order:
  1. removed the host from its group (`<group-a>`), leaving no group association
  2. added the host to another group (`<group-b>`)
- A baseline runtime pull was taken before the session, one continuous
  `tcpdump` captured port `8833` throughout, and a post-action runtime pull was
  taken after.

**Result: confirmed. Group membership is written as `value.tags` on the same
host-scoped `item: "policy"` / `mtype: "set"` path already used for DHCP
reservations and notification toggles.**

Observed action 1 — remove from the group:

```json
{
  "COMMAND_TIMEOUT": 180,
  "item": "batchAction",
  "value": [
    {"data": {"item": "policy:delete", "value": {"policyID": "<policy-id-2>"}}, "mtype": "cmd", "target": "0.0.0.0", "type": "jsonmsg"},
    {"data": {"item": "policy:delete", "value": {"policyID": "<policy-id-1>"}}, "mtype": "cmd", "target": "0.0.0.0", "type": "jsonmsg"},
    {"data": {"item": "policy", "value": {"...": "...", "tags": []}}, "mtype": "set", "target": "<device-mac>", "type": "jsonmsg"}
  ]
}
```

Observed action 2 — add to the other group:

```json
{
  "COMMAND_TIMEOUT": 180,
  "item": "batchAction",
  "value": [
    {"data": {"item": "policy", "value": {"...": "...", "tags": [<group-b-tag>]}}, "mtype": "set", "target": "<device-mac>", "type": "jsonmsg"},
    {"data": {"item": "host:syncAppTimeUsageToTags", "value": {"begin": <epoch>, "mac": "<device-mac>"}}, "mtype": "cmd", "target": "0.0.0.0", "type": "jsonmsg"},
    {"data": {"item": "init", "value": {}, "get": "0.0.0.0", "includeInactiveHosts": true, "fwapcOps": ["..."]}, "mtype": "init", "target": "0.0.0.0", "type": "jsonmsg"}
  ]
}
```

Result:

- host raw `tags` changed from the first group's tag to the second group's tag
- the host top-level `tags` and the nested `host.policy.tags` changed together
- the `policyRules` count dropped by two, matching the two deletes in action 1
- both actions were single `batchAction` posts; each batch's trailing `init`
  request is a data refresh, not part of the membership mutation

Normalized characteristics:

- the mutation is `mtype: "set"`, `item: "policy"`, `target: "<host-mac>"` —
  the same host-policy write family as Finding 15
- membership is expressed as an integer list in `value.tags`
- tag IDs are **integers in the write** but **strings in the read payload**
- the write carries the **entire host policy object**, not a `tags`-only patch:
  `acl`, `adblock`, `bypass_prevention`, `deviceOffline`, `devicePresence`,
  `device_service_scan`, `doh`, `family`, `ipAllocation`, `monitor`,
  `ntp_redirect`, `qos`, `safeSearch`, `unbound`, `weak_password_scan`, `tags`
- `value.tags: []` means "no group"; there is no separate remove command

Side effects of the remove:

- the app also deleted two **disabled, device-scoped rules** for the same MAC:
  - one `allow` / `outbound` / `type: category` /
    `scope: ["<device-mac>"]` / `disabled: "1"`
  - one `block` / `bidirection` / `type: mac` /
    `target: "<device-mac>"` / `disabled: "1"`
- "remove from group" is therefore not tags-only; the app sweeps stale
  device-scoped rules at the same time
- **superseded in part by Finding 43**, which captured the full rule handling on a
  membership change: the app deletes **every** rule the device owns — enabled or
  disabled, `dap` or user-created — ahead of the tags write, in the same batch. The
  two rules deleted here were the only two that device had, so this capture could
  not distinguish "delete the device's rules" from "sweep the disabled ones".
  Finding 43's device carried four rules of mixed state and settled it
- the add fires `host:syncAppTimeUsageToTags` with an app-supplied epoch
  `begin`, so the box re-attributes the host's usage history to the new group

Implementation impact:

- a future group-membership service can reuse the existing host-scoped
  `item: "policy"` writer; no new command family is needed
- the app sends the full policy object, but the box does **not** require it: a
  `tags`-only write keeps every other key (Finding 43). A minimal payload is
  preferable, since it cannot carry a key the caller did not intend to send
- integer tag IDs in the write versus string tag IDs in the read must be
  handled
- "remove" and "add" are the same call with a different `tags` list; matching
  app behavior may also require the device-scoped-rule cleanup and the
  `host:syncAppTimeUsageToTags` follow-up

Open: **user** membership was not exercised in this capture. The same host
policy object also carries `userTags`, which stayed `[]` throughout, so the
device-to-user conduit is expected to be this same `item: "policy"` write with
`userTags` populated — but that is not yet confirmed. The app may instead express
a user assignment through the user's affiliated backing tag (see the user-facing
identity rule), which this capture cannot yet distinguish from a plain group
change.

**Artifacts:**

- `.tmp/firewalla_membership_capture.pcap`
- `.tmp/membership_capture.decoded.txt`
- `.tmp/membership_posts.json`
- pre-capture runtime pull: `.artifacts/membership-capture/20261002-135538/`
- post-capture runtime pull: `.artifacts/membership-capture/20261002-135842/`

### Finding 42: Device-to-user assignment is cloud-mediated and lands locally as the user's affiliated tag

**Scenario:**

- Two captures were used to isolate how the app assigns a device to a **user**
  (as opposed to a group).
- The first capture filtered only the local runtime port (`port 8833`) and the
  user did several actions: assign to a user, assign to a group, remove from
  that group, re-assign to the user, remove from the user.
- Only the two **group** actions produced local traffic (Finding 41 payload
  shape). **None** of the three user actions produced any local message.
- A second capture widened the filter to
  `port 8833 or 443 or 80 or 8443 or 53` and the user performed a single action:
  assign the test device (`<device-mac>`) to a user.

**Result: confirmed. User assignment never touches the local runtime channel.**

Observed in the widened capture:

- **zero** port `8833` traffic during the action
- the app opened a TLS session to the vendor's cloud endpoint
  (`firewalla.encipher.io`), roughly 5.9 KB client / 267 KB server
- the remaining 443 flow was the phone's DNS provider, unrelated to the mutation
- no local message of any HTTP method was observed

Observed effect on the box (post-action runtime pull):

```
host <device-name> (<device-mac>)
  tags:            ['<user-a-tag>']    <- was []
  userTags:        []
  policy.tags:     ['<user-a-tag>']
  policy.userTags: []

tag <user-a-tag>   name: <tag-uuid>
                   policy: {"userTags": ["<user-a-id>"]}

user <user-a-id>   name: <user-a>
                   affiliatedTag: "<user-a-tag>"
```

Normalized interpretation:

- a Firewalla **user** is a backing **tag** with `policy.userTags` naming the
  user id; the user record's `affiliatedTag` points back at that tag
- assigning a device to a user is therefore, at the box, **the same kind of
  write as assigning it to a group** — `host.tags` gains the user's affiliated
  backing tag id
- the group and user cases are **indistinguishable in shape**; only the tag's
  linkage to a user id distinguishes them
- the host `policy.userTags` field remained empty in both cases, so it is **not**
  the device-to-user conduit

**The underlying tag's name is not a reliable signal — and is sometimes a trap:**

A user's backing tag name is **not** uniform across accounts or across the
account's own history. Measured across 10 users on one box:

- **8 of 10** backing tags are named with a bare **UUID** (a
  `XXXXXXXX-XXXX-…` style value) and are unmistakably internal
- **2 of 10** backing tags carry a **human-readable name** (a possessive
  "<owner>'s Devices" style label) that is indistinguishable from an ordinary
  group name

Owner context that explains the split: those two users predate Firewalla's
current user model. When Firewalla first introduced users, a user **was** a
group, and the app displayed it as such. The later model layers a user identity
over a backing tag and hides the tag. The two older users are therefore legacy
artifacts from the original process and its migration; every user created since
(roughly the last 3-6 months here) uses the finalized UUID-named backing tag.

**Consequence — the legacy name is a false positive, not a real group:**

- there is **no separate group** with the legacy backing tag's name; the name
  belongs to the user's backing tag and nothing else
- the human-readable name must **never** be used to decide whether a tag is a
  group or a user
- an affiliated backing tag must **never** be rendered by its raw name: 8 of 10
  would leak a UUID, and the remaining 2 would render a stale legacy label
  instead of the user's current name

**Classification must be by linkage, never by name.** A tag is a user
affiliation when its `policy.userTags` is populated (equivalently, when the tag
id appears as some user record's `affiliatedTag`). Anything else is a plain
group. This holds for both the UUID-named and the legacy human-named backing
tags.

**Existing integration surface that this affects:**

- `groups[]` in the runtime inventory is built from the raw `tags` map, so it
  currently **includes all user backing tags** — both the UUID-named ones and the
  legacy human-named ones. User affiliations are therefore offered as if they
  were groups
- `affiliated_group_name` on a user record is set from the **user's** name rather
  than the backing tag's name, so it is display-safe but not truthful about the
  tag, and it makes any "user (group)" label branch dead code
- per-host resolution is already correct: `_resolve_host_group_name` maps an
  affiliated tag to the **user's** name, so a device in a legacy backing tag
  shows the user name rather than the legacy label

**Write paths differ — this is the central asymmetry:**

| | Group add/remove | User assignment |
| --- | --- | --- |
| Transport | local `8833` | cloud `443` (vendor endpoint) |
| Message | `set item=policy target=<mac> value.tags=[...]` | TLS-encrypted, not visible |
| Local effect | immediate `tags` write | box syncs the affiliated tag in |

Implementation impact:

- user assignment **cannot** be implemented from the local runtime channel the
  way group membership can; the app does not perform it there
- the cloud payload is opaque TLS, so the exact cloud write shape cannot be
  recovered from a packet capture alone
- implementing user assignment against the cloud requires Firewalla's published
  cloud contract (the contract-first method at the top of this document), not a
  local mutation capture
- **the local shortcut is confirmed working:** because the box represents a user
  assignment as just `tags: [<affiliated tag>]`, the existing host-scoped
  `set item=policy value.tags` path **can** express a user assignment directly,
  even though the app performs the write over the cloud. Verified 2026-10-02 on
  the dev box (see the confirmation below)

**Local shortcut verification (2026-10-02):**

- wrote a user's affiliated tag to the test device over the local channel only,
  using the app-shaped 16-key policy object with `value.tags = [<user-tag>]`
- the box accepted the write and the runtime pull reported the new tag
- the user record resolved correctly by its `affiliatedTag`
- the integration's existing normalization already renders it —
  `_resolve_host_group_name` produced the user's name as `group_name`
- the host was then restored to the app's prior state, which also succeeded
- **the app reflects local writes.** After the local user-tag write the Firewalla
  app showed the device under that user with no app-side action taken, so a
  locally written assignment is not treated as second-class by the app
- **group and user tags render distinctly in the app.** The assignment dialog
  lists groups and users together but separates them into their own sections.
  Writing a plain group tag locally (no `policy.userTags` link) put the device
  under the **groups** section; writing a user's affiliated tag put it under the
  **users** section. So the box and the app both preserve the group/user
  distinction even though the wire shape is identical
- **distinguishing the two in data is a tag lookup, not a guess.** A tag is a
  user affiliation when its `policy.userTags` is populated (equivalently, when
  the tag id appears as a user record's `affiliatedTag`); otherwise it is a
  plain group. An implementation must resolve the tag to classify it, because
  `host.tags` carries no type marker of its own
- **removal round-tripped on both paths.** A local write driven by
  `value.tags = [0]` (an invalid tag id the box stripped to `[]`) and a later
  **explicit** `value.tags = []` write both left the host unassigned, and the app
  cleared the assignment in both cases. The two paths are therefore equivalent,
  and an implementation can safely send a clean empty list
- **no cloud revert observed.** The box still reported the locally written tag
  on a read-only pull after the app had been open, so the cloud did not
  reconcile the locally written value within that window
- **caveat on the normalized model:** the assignment surfaces through
  `host.group_name` / `group_ids`, **not** `host.user_ids`. `user_ids` is fed by
  the host `userTags` array, which stays empty. Any user-assignment surface must
  therefore treat an affiliated tag in `tags` as a user assignment, not rely on
  `user_ids`
- **not yet verified:** whether the box fires the `host:syncAppTimeUsageToTags`
  follow-up on its own after a local write, and whether the cloud reconciles a
  locally written affiliated tag over a longer window

**Practical consequence:** a working local user-assignment capability is
achievable today by writing the user's affiliated tag through the existing
host-policy writer — the same contract as group membership. Prefer this over the
cloud path until the cloud contract is documented.

**Artifacts:**

- `.tmp/firewalla_user_assign_capture.pcap` (8833-only; group writes only)
- `.tmp/firewalla_chads_capture.pcap` (widened 8833/443/80/8443/53; cloud call)
- `.tmp/chads_wide.txt` (widened analysis output)
- `.tmp/analyze_wide.py` (method-agnostic + SSE decode + TLS/DNS summary)
- `.tmp/tls_probe.py` (SNI extraction and per-second TLS timeline)
- `.tmp/probe_membership.py` (dry-run-by-default local membership write probe)
- pre/post runtime pulls: `.tmp/capture_chads_before.json`,
  `.tmp/capture_chads_after.json`

### Finding 43: Membership writes may be minimal, and any membership change deletes the rules attached to that device

Three questions left open by Findings 41 and 42 were resolved on the dev box on
2026-10-02 with read-only pulls, reversible writes, and one purpose-built app
capture.

**1. A `tags`-only payload is accepted and clobbers nothing — confirmed.**

Finding 41 recorded the app sending the entire 16-key policy object, and the
implementation impact note in that finding therefore said a faithful write must
send the full object. That reading was too strong: the app's choice is not
evidence that the box *requires* it.

Test: on `shelly1pm-beerfridge` (an unassigned IoT host whose `host.policy`
carries 20 keys), write `{"tags": []}` — the host's own current value, so no
membership changes — over the local channel.

Result:

- the write was accepted, and the response returned the box's fully merged policy
- all 20 policy keys were present before and after, with **zero** lost, changed
  or added keys
- `dap`, `deviceTags`, `ssidTags`, `isolation` and `userTags` all survived, even
  though the app never sends them

This matches how the DHCP reservation writer already behaves — it sends only its
own `ipAllocation` sub-object — and confirms a membership write can send only
`tags`. Sending the app's full object is not required, and a minimal payload is
strictly safer because it cannot carry a policy key the caller did not intend to
send.

**2. A membership change deletes every rule the device owns.**

**The rule, stated plainly:**

> When a device's membership changes, the app deletes **every rule that belongs
> to that device**. "Belongs to the device" means the device's MAC is the rule's
> `target`, or the device's MAC appears in the rule's `scope`. Nothing about the
> rule's `purpose`, `action`, `type`, or `disabled` state affects eligibility: an
> enabled rule the owner created is deleted exactly like a disabled one.
>
> This is not `dap`-specific, and it is not "stale rules only". It is every rule
> on the device. The consequence is visible in the app's own UI, which warns at
> assignment time that the device will follow only its group's rules from then on.

**The box never does this by itself.** Test: on `office-floor-light-bulb-1`,
clear the tags through the local channel with no `policy:delete`, then compare
the rule set. The box **kept both rules**. The deletion is the app's, not the
box's — an integration must issue it explicitly.

**The deletes go first, ahead of the tags write.** Captured on 2026-10-02 with
`rustdesk-server` (`00:AA:BB:CC:60:31`), an **unassigned** device carrying two
**enabled, user-created** rules plus a disabled `dap` pair. It was assigned to
one group **in the app**, with a port 8833 capture armed and runtime pulls either
side.

Before:

| pid | shape | state |
| --- | --- | --- |
| 666 | `block`/`mac`, `dap` | disabled |
| 667 | `allow`/`category`, `dap` | disabled |
| 668 | `block`/`category` → `TLX-fw-youtube` | **enabled, user-created** |
| 669 | `block`/`category` → `TLX-fw-tiktok` | **enabled, user-created** |

The app sent one `batchAction` of seven items, in this order:

```
1. policy:delete  669   <- the enabled user rule
2. policy:delete  668   <- the enabled user rule
3. policy:delete  667   <- dap
4. policy:delete  666   <- dap
5. policy  target=00:AA:BB:CC:60:31  tags=[64]   (16-key object)
6. host:syncAppTimeUsageToTags  begin=1790395200
7. init  (data refresh)
```

After: the device is in `SVR_NAS`, and **all four rules are gone**. Box-wide the
rule count fell by exactly four, nothing was added, and nothing changed.

**What is *not* deleted:**

- rules belonging to **other** devices, even when they are otherwise identical
- rules scoped by group, network, tag, or interface rather than by the device —
  including the group rules the device now inherits. Membership changes the
  device's scope; it does not touch the group's own rules
- any rule that does not name the device's MAC in `target` or `scope`

**A wrong intermediate reading, recorded because it was nearly shipped.** An
earlier version of the integration keyed the delete on `purpose == "dap"`, on
the reasoning that the two ids seen in Finding 41 were `dap`-purposed and that
`purpose` would keep the operation away from user rules. Box-wide that was
already doubtful — 84 of 124 group-assigned hosts still carry a `dap` pair, so
`dap` is what *survives* assignment — and this capture refutes it outright: a
`dap`-only delete would have left this device's two **enabled** user rules
behind, the exact opposite of what the app does. The owner's model was right from
the start.

**User and group assignment behave identically.** A second capture
(2026-10-03) assigned `kadens-phone` (`0C:85:E1:B0:1D:1C`) to the **user**
`KADENS_PHONE`, from unassigned, carrying two **enabled** rules the owner had
created minutes earlier:

```
1. policy:delete  674   <- enabled user rule (TLX-fw-fortnite)
2. policy:delete  673   <- enabled user rule (TLX-fw-instagram)
3. policy  target=0C:85:E1:B0:1D:1C  tags=[73]   (16-key object)
4. host:syncAppTimeUsageToTags
5. init  (data refresh)
```

Box-wide the count fell by exactly two. So there is no user-specific exemption:
assignment deletes the device's own rules whether the target is a group or a
user, and the batch shape is identical.

**`clear` deletes them too.** Finding 41 is a capture of a *removal*
(`tags: []`), and its batch carried `policy:delete` for that device's two rules.
A live check on `kadens-phone` reproduced it: clearing its user assignment removed
its device-scoped rule. So the deletion is not specific to assignment — **any**
membership change deletes the device's own rules.

**The blast radius differs by what the device has to lose, not by the verb.**
Measured on the dev box:

| Membership state | Hosts | Carry their own rules |
| --- | --- | --- |
| assigned to a **group** | 123 | 83 — almost always just the disabled `dap` pair |
| assigned to a **user** | 32 | 1 |
| unassigned | 61 | 13 |

A device in a group carries no user rules of its own: what it holds is Firewalla's
own Device Active Protect pair. An unassigned device can hold real rules, which is
exactly the case both captures deleted. So a `clear` on a group-assigned device
usually destroys only `dap` bookkeeping, while a `set` from unassigned destroys
rules the owner wrote.

**What is *not* deleted:**

- rules belonging to **other** devices, even when they are otherwise identical
- rules attached to a **user or group** (`tag`), including the user the device is
  leaving. Their 13 rules stayed intact through the user capture above, and still
  cover that user's other devices
- rules scoped by network, interface or tag rather than by the device
- any rule that does not name the device's MAC in `target` or `scope`

Note the two things a membership change does, which are easy to conflate:

- **inheritance changes** — leaving a user means that user's rules stop reaching
  the device. Nothing is deleted, and re-assigning restores it
- **the device's own rules are deleted** — irreversible, unrelated to the user's
  rules

**Implementation.** Select by device membership in the rule, not by `purpose`:

```python
(rule.target_type == RULE_TARGET_TYPE_MAC and rule.target.upper() == mac)
or any(scope.upper() == mac for scope in rule.scope)
```

Applied to every rule regardless of purpose or enabled state, and issued
**before** the tags write. On the captured device that is exactly ids 666–669.
The behaviour is not a corner case: `home-assistant`, `portainer` and `caddy-int`
all carry device-scoped rules today, so assigning any of them to a group removes
those rules — as the app does.

**3. `host:syncAppTimeUsageToTags` — what it is, sent on assignment too.**

Both captured batches carried it. The tags-write-only batch from Finding 41 had
it on the **add**; this assignment batch has it as item 6, after the tags write.
Its value is `{"begin": 1790395200, "mac": "<mac>"}`, and decoding `begin`:

```
1790395200  ->  2026-09-26T00:00:00-04:00 (box timezone, America/New_York)
capture     ->  2026-10-02T22:18:17+00:00
```

`begin` is a **midnight in the box's own timezone, seven days back including the
current day**. Firewalla tracks per-app usage against a **tag** — a group or a
user — because that is what the app-time limits are attached to. When a device
moves, its usage for that window was attributed to the old tag. This command
tells the box to re-attribute the device's app-time usage to the new tag.

**Recommendation: still do not send it.** It is usage-accounting backfill, and
separating it from the rest of the work is deliberate:

- membership and the rule cleanup are both correct without it, and both are now
  capture-verified
- the window is inferred from **two samples that agree**, which is better than
  one but still an inference. A wrong window silently mis-attributes usage
  accounting, which is worse than not sending it
- the integration reads usage; it does not own Firewalla's app-time limits. The
  only affected surface is a tag's usage history in the app, which the box
  reconciles on its own schedule

Revisit if the integration ever writes usage limits, and confirm the window
against a third sample before then.

**Artifacts:**

- `.tmp/check_classification.py` (read-only: live classification check)
- `.tmp/list_host_membership.py` (read-only: host membership dump)
- `.tmp/list_device_rules.py` (read-only: device-scoped rule discovery)
- `.tmp/test_minimal_write.py` (minimal-write key-preservation probe)
- `.tmp/test_rule_sweep.py` (rule-sweep probe, self-restoring)
- `.tmp/preflight_capture.py` (read-only: target state and candidate devices)
- `.tmp/diff_capture.py <before> <after>` (per-device and box-wide rule diff)
- `.tmp/dump_membership.py <pcap> <out.json> [client-ip]` (full decrypted POST bodies,
  the tool that produced the seven-item batch above)
- `.tmp/reconstruct_capture.py` (pre/post pull diff for the original 575/576 delete)
- `.tmp/rule_correlation.py`, `.tmp/dap_analysis.py` (`dap` correlation, `begin` decode)
- `.tmp/test_own_rules_hypothesis.py` (the group/user/none rule-ownership table)
- `.tmp/capture_device_rules.py` (the captured device's full rule set)
- `.tmp/verify_dap_selector.py` (read-only selector check)
- `.tmp/analyse_what_changed.py` (field-level diff of everything a membership change touched)
- `.tmp/confirm_deleted_vs_detached.py` (proves deletion vs detach-and-re-home)
- `.tmp/check_clear_is_safe.py` (own-rule ownership by membership state)
- `.tmp/explain_kadens_phone.py` (device rules vs user rules for one host)
- **the group-assignment capture** — the evidence for the rule-deletion rule:
  `.tmp/firewalla_capture_20261002-221733_rustdesk-group-add.pcap`, with pulls
  `.artifacts/rustdesk_group_add/20261002-214538/` (before) and
  `.../20261002-221837/` (after)
- **the user-assignment capture** — shows user and group behave identically:
  `.tmp/firewalla_capture_20261003-014641_kadens-phone-reassign.pcap`, with pulls
  `.artifacts/kadens_phone_reassign/20261003-014439/` (before) and
  `.../20261003-014807/` (after)
- both were taken with `tools/support/capture_firewalla_packets.py --host <box>
  --client-ip <phone> --label <name>`, the maintained workflow for this, and
  decoded with `.tmp/dump_membership.py <pcap> <out.json> <client-ip>`
- `.artifacts/membership-capture/20261002-135538/` and `.../20261002-135842/`
  (the pulls the original 575/576 ids were read out of)

## Alarm findings

### Finding 26: Alarm state arrives in the init payload as two fields plus three counts

**Scenario:**

- Confirmed by a live pull (`utils/pull_runtime.py`) on the connected dev box
  (2026-09-30), and cross-checked against the Firewalla app's own alarm count.
- The integration parses **neither** field today; alarms are currently unused.

**Confirmed `mtype=init` response fields:**

| Key | Type | Notes |
| --- | --- | --- |
| `activeAlarmCount` | `optInt` | Authoritative active total. **This is what the app displays** |
| `archivedAlarmCount` | `optInt` | Archived total |
| `pendingAlarmCount` | `optInt` | Pending total (observed `0`) |
| `newAlarms` | `JSONArray` | The active alarm records — **capped at 50** |

APK references: `xz2.java` line ~4295 reads `activeAlarmCount` via `optInt`;
line ~4054 reads `newAlarms` via `getJSONArray` and hands it to a `gx2`
container of `fx2` alarm objects. The alarm parser itself
(`fx2.m10449j0(JSONObject)`) **failed to decompile** (“Method not decompiled”),
so field names were recovered from live payloads instead of the APK.

**Critical: `newAlarms` is capped at 50 and is NOT the count.**

Observed live: `activeAlarmCount = 243` while `len(newAlarms) = 50`, and
`archivedAlarmCount = 5`. **Never derive the alarm total from `len(newAlarms)`.**
Use `activeAlarmCount`. Use the retrieval API in Finding 27 for the full set.

**Confirmed per-alarm field surface** (union across 50 records, with occurrence
counts — fields are sparse):

| Field | Present | Notes |
| --- | --- | --- |
| `aid` | 50/50 | Alarm id, **string**; used as `alarmID` in commands |
| `alarmTimestamp` | 50/50 | When the alarm fired, **epoch as a string** |
| `timestamp` | 50/50 | A **second, different** timestamp (typically earlier) |
| `device` | 50/50 | Device name, or an IP for VPN-origin alarms |
| `message` | 50/50 | Human-readable, or an info constant like `INFO_ALARM_VPN_CLIENT_CONNECTION` |
| `state` | 50/50 | Only `active` observed — **even for archived alarms** |
| `type` | 50/50 | `ALARM_*` class (see Finding 30) |
| `p.cloud.decision` | 50/50 | `alarm` |
| `p.fi` | 50/50 | Feature id |
| `p.device.name` / `.mac` | 50/50 | `p.device.mac` is the command's `device` scope |
| `p.id`-family (`p.device.id`, `.ip`) | 49/50 | |
| `p.intf.name` / `.desc` / `.id` / `.subnet` | 50/50 | Originating interface |
| `p.dest.*` | 33–44/50 | Destination: `.app`, `.app.id`, `.category`, `.country`, `.domain`, `.id`, `.ip`, `.latitude`, `.longitude`, `.name`, `.name.suffix`, `.port` |
| `p.protocol` | 43/50 | |
| `p.tag.ids` / `.names`, `p.utag.ids` / `.names`, `p.dtag.ids` / `.names` | 35–46/50 | Group / user / device tag membership |
| `p.timestampTimezone` | 34/50 | Display-formatted local time |
| `p.showMap` | 34/50 | |
| `p.action.block`, `p.alarm.trigger`, `p.local_is_client`, `p.from`, `p.security.*`, `result`, `result_policy`, `p.severity` | 9/50 | Present only on **security/blocked** alarms (`ALARM_INTEL`) |
| `p.begin.ts`, `p.end.ts`, `p.duration`, `p.flows`, `p.percentage`, `p.totalUsage` | 5/50 | Present only on **bandwidth** alarms |
| `p.quarantine`, `p.vpnType`, `p.dest.wg.peer`, `p.device.wgPeer` | 1–2/50 | VPN-specific |

**Important field conventions:**

- **`p.*` keys are literally flat dotted strings**, not nested objects. Parse
  them as a map, not a hierarchy.
- **`p.dest.latitude` / `p.dest.longitude` are present on ~44/50 records** and
  give precise destination geolocation. Treat as sensitive.
- **`p.severity` is sparse** (9/50) and observed only as `minor`, alongside
  `p.severity.score`. It is not a reliable required field.
- **`state` does NOT indicate archived** — archived records still report
  `state: "active"`. Only membership in the `archivedAlarms` list distinguishes
  them.

**Artifacts:**

- `.artifacts/alarm-verify/*/runtime_init.json` (live pulls)
- `.tmp/live_gold/20260910-165331/runtime_init.json` (older pull; line 2 count,
  line 45611 `newAlarms`)

### Finding 27: Alarm retrieval uses `item=alarms`, `item=archivedAlarms` and `item=alarmDetail`

**Scenario:**

- Confirmed live (2026-09-30) with the stored HA config-entry credentials.
- The init payload's `newAlarms` is capped at 50, so full retrieval needs these
  dedicated reads.

**Confirmed read contracts:**

```
# Active alarms
mtype: get
target: 0.0.0.0
data:
  item: alarms
  value: {count: <page size>, offset: <n>}

# Archived alarms
mtype: get
target: 0.0.0.0
data:
  item: archivedAlarms
  value: {limit: <page size>, offset: <n>}

# One alarm with full detail
mtype: get
target: 0.0.0.0
data:
  item: alarmDetail
  value: {alarmID: "<aid>"}
```

**Confirmed response shape:** `{"count": <n>, "alarms": [ ... ]}`. The
response's `count` is the **number of records in this page**, not a total — use
`activeAlarmCount` / `archivedAlarmCount` from the init payload for totals.

**The two items accept DIFFERENT page-size keys — this is a real trap.**

> **Corrected 2026-09-30 (later the same day).** An earlier revision of this
> finding stated that `count` was the page-size key and `limit` was ignored.
> That is **only true for `alarms`**. Testing with a large archived set proved
> `archivedAlarms` is the opposite. Both behaviours are now measured
> separately below; do not generalise one to the other.

**`item=archivedAlarms` uses `limit` (+ `offset`) and ignores `count`.**
Measured with 243 archived records:

| `value` | Returned |
| --- | --- |
| `{}` (bare) | 50 (default page) |
| `{"count": 1000}` | **50** — `count` ignored |
| `{"count": 243}` | **50** — ignored |
| `{"limit": 10}` | 10 |
| `{"limit": 100}` | 100 |
| `{"limit": 250}` | **243** — full set |
| `{"limit": 500}` | 243 |
| `{"limit": 1000}` | 243 |

**`offset` pages correctly for `archivedAlarms`** — verified contiguous,
non-overlapping pages of 50:

| `value` | Returned | Newest → oldest |
| --- | --- | --- |
| `{"limit": 50, "offset": 0}` | 50 | 1732 → 1680 |
| `{"limit": 50, "offset": 50}` | 50 | 1679 → 1630 |
| `{"limit": 50, "offset": 100}` | 50 | 1629 → 1580 |
| `{"limit": 50, "offset": 200}` | 43 | 1529 → 1487 |
| `{"limit": 50, "offset": 240}` | 3 | 1489 → 1487 |

**`item=alarms` used `count` and ignored `limit`.** Measured earlier the same
day with 243 active records:

| `value` | Returned |
| --- | --- |
| `{}` (bare) | 50 |
| `{"limit": 200}` | **50** — `limit` ignored |
| `{"count": 200}` | **200** |
| `{"count": 1000}` | **243** — full set |
| `{"count": 5000}` | 243 |

**The asymmetry is confirmed — resolved 2026-09-30 (same day, later test).**

> An earlier note here flagged the `alarms` row as needing re-verification. That
> is now closed. `alarms` genuinely uses `count` and genuinely ignores both
> `limit` and `offset`, while `archivedAlarms` uses `limit` and honours `offset`.
> The two items are **not** interchangeable, and the disagreement is real rather
> than an artifact of running the two tests at different times.

**`item=alarms` ignores `offset` entirely.** Measured with exactly one active
alarm present, so any applied offset would have returned zero records:

| `value` | Returned |
| --- | --- |
| `{"offset": 0}` | 1 |
| `{"offset": 1}` | **1** — offset not applied |
| `{"offset": 2}` | **1** — offset not applied |
| `{"limit": 50, "offset": 1}` | 1 |
| `{"count": 50, "offset": 1}` | 1 |

Compare `archivedAlarms`, where `{"limit": 50, "offset": 243}` correctly returned
**0** — a clean boundary check proving `offset` *is* implemented there.

**Consequence:** the active alarm list has **no working pagination**. The only way
to retrieve more than the default 50 is a large `count`, which returns the whole
set in one response. That is acceptable because the active set is inherently
bounded in practice, but it means a caller cannot page the active list.

**Practical guidance:** because the two handlers disagree, **send all three keys**
— `{"count": N, "limit": N, "offset": M}`. Unknown keys are ignored, so each item
reads the one it understands and the caller does not have to know which. This is
what `utils/probe_alarm_control.py::_fetch_alarms` does. Note that `offset` is
still useful to send for `archivedAlarms`; for `alarms` it is harmlessly ignored.

**`item=alarmDetail` adds enrichment the list view does not carry:**

Extra keys observed on a detail read (~51 keys vs ~15 in the list view):

- `e.dest.ip.range`, `e.dest.ip.cidr`, `e.dest.ip.country`, `e.dest.ip.city`,
  `e.dest.ip.org` — IP-range, CIDR and **ISP/organisation** enrichment
- `e.transfer`
- `p.utag.names`, `p.tag.names` — tag names as `{uid, name}` objects

`alarmDetail` works for **archived** alarms as well as active ones, so a detail
lookup by `aid` does not need the alarm to be active.

**Cost note:** `alarmDetail` is **one request per alarm**. Fanning it out over
243 alarms is 243 requests; make it opt-in rather than default.

**Aids are non-contiguous** in the active list (…1729, **1727**, 1726…), because
an archived alarm's aid is removed from the active set. Sequence gaps are
therefore normal, not corruption.

**Artifacts:** captured in the alarm verification session (2026-09-30).

### Finding 28: Alarm mutations are `cmd` messages with an `alarmID` value

**Scenario:**

- Confirmed live (2026-09-30) by sending each command to the gold box.
- All six operations were executed and their effects verified against the
  `activeAlarmCount` / `archivedAlarmCount` / `exceptionRules` / `policyRules`
  containers.

**Confirmed command contracts** (`mtype=cmd`, `target=0.0.0.0`,
`value.alarmID` is the alarm's `aid`):

| Operation | `item` | `value` | Observed response |
| --- | --- | --- | --- |
| Archive (dismiss) | `alarm:ignore` | `{alarmID}` | `{"ignoreIds": ["<aid>"]}` |
| Archive all | `alarm:ignoreAll` | — | — |
| Delete | `alarm:delete` | `{alarmID}` | — |
| Delete all active | `alarm:deleteActiveAll` | — | — |
| Delete all archived | `alarm:deleteArchivedAll` | — | — |
| Mute | `alarm:allow` | `{alarmID, matchAll, info{...}}` | `{"exception": {..., "eid": "<n>"}}` |
| Unmute | `alarm:unallow` | `{alarmID}` | `{}` |
| Block | `alarm:block` | `{alarmID, matchAll, info{...}}` | `{"policy": {"pid": "<n>", ...}, "otherAlarms": [], "alreadyExists": false, "updated": false}` |
| Unblock | `alarm:unblock` | `{alarmID}` | `{}` |

The command builder is `ku7.m14063c` (simple id-only commands) and
`ku7.m14064d` (mute/block with scope). `l33` maps `GET`=1 and `CMD`=3, matching
the pairing already used across this document.

**`alarmID` is the alarm's `aid`** — confirmed at `fx2.java` (~line 1626):
`optString("aid")` is stored in the field later used as `alarmID`.

**The `device` scope is `p.device.mac`** — confirmed at `fx2.java` (~line 1622).
Note this can be a synthetic value such as
`wg_peer:wWDLO7vE+dpUiwDONgXorPyR/e6YAKme+aLmgVIlRn8=` for VPN-origin alarms,
not a real MAC.

**Measured effects (live):**

| Step | `activeAlarmCount` | `archivedAlarmCount` | `exceptionRules` | `policyRules` |
| --- | --- | --- | --- | --- |
| Baseline | 248 | 0 | 99 | 306 |
| After `alarm:ignore` | **247** | — | 99 | 306 |
| After `alarm:allow` (mute) | **246** | — | **100** | 306 |
| After `alarm:block` | **244** | — | 100 | **307** |
| After `alarm:unallow` | 244 | — | 99 | 307 |
| After `alarm:unblock` | 244 | — | 99 | **306** |
| After `alarm:delete` ×2 | 243 | 5 → **3** | 99 | 306 |

**Archive decrements the count immediately** — there is no lag. Every operation
was reflected in the next payload.

**`unallow` / `unblock` do NOT un-archive.** After muting and un-muting, and
after blocking and unblocking, the alarm remained in `archivedAlarms`. Removing
the exception or block rule restores the *rule/exception* state only. **There is
no un-archive command**; only `alarm:delete` removes the record.

**Consequence: archive, mute and block are all effectively one-way on the alarm
record.** Only `delete` removes it from `archivedAlarms`. Any test that targets a
real alarm permanently alters the user's alarm history.

**Artifacts:** `utils/probe_alarm_control.py` (dry-run by default; `--confirm`
required to write).

### Finding 29: Mute/block scope and the three mute durations

**Scenario:**

- Confirmed from `AlarmMuteScheduleDialog`, `AlarmMuteDialog`,
  `AlarmActionHelper.getMuteApplyToItems` and `cd0.m2349a`; mute durations were
  also verified live.

**The app exposes exactly three mute durations** (`AlarmMuteScheduleDialog`):

| Option | `expireTs` computation |
| --- | --- |
| 1 hour | `(System.currentTimeMillis() / 1000) + 3600` |
| Today | `ZonedDateTime.now(boxTz).plusDays(1).truncatedTo(DAYS).toEpochSecond()` — **start of tomorrow in the box's timezone** |
| Always | `-1` sentinel ⇒ `expireTs` is **omitted from the payload entirely** |

The box's timezone is reported in the init payload as `timezone` (observed
`America/New_York`). Verified live: a 1-hour mute stored `expireTs` on the
resulting exception rule, and a “today” mute resolved to midnight local.

**This mirrors the existing `pause_rule` idiom.** `pause_rule` already computes
`int(dt_util.utcnow().timestamp()) + seconds`, and `_RAW_RULE_EXPIRE_TS_KEY`
(`"expireTs"`) is already defined in `helpers/runtime_inventory.py`. Reuse both;
do not add a second expiry convention.

**Scope comes from the `info` keys, NOT from `matchAll`.**

> **Corrected 2026-09-30 (third correction to this section).** An earlier revision
> claimed that `matchAll: 1` meant a global mute. **That was wrong** — it was an
> inference from a single observation, not a measurement. A direct four-way test
> (below) shows `matchAll` changing nothing. The scope decision is entirely
> governed by whether the device/tag/interface key is present in `info`.

Measured by blocking on an archived alarm and inspecting the resulting rule's
`scope` array, which is the same scope resolution a mute uses:

| `value` | Resulting `scope` |
| --- | --- |
| `matchAll: 1` + `info.device` | `["0C:85:E1:EB:6A:AF"]` — device-scoped |
| `matchAll: 0` + `info.device` | `["0C:85:E1:EB:6A:AF"]` — **identical** |
| `matchAll: 1`, no `info.device` | `null` — **global** |
| `matchAll: 0`, no `info.device` | `null` — **identical** |

**`matchAll` made no observable difference in any tested path.** It is always
written as `1` or `0` by the app (`ku7.m14064d`), but its effect is **not
determined**. Possibilities are that it governs something untested (matching
multiple alarm instances), or that it is a legacy field the box ignores. Treat it
as **required-but-inert**: keep sending it for fidelity with the app, and do not
build behaviour on it.

**What actually determines scope** (from `cua.m8202c`, which a mute shares with
`exception:create`):

| `info` key present | Scope granted |
| --- | --- |
| `p.device.mac` | that device |
| `p.tag.ids` | a group or user tag |
| `p.intf.id` | a network |
| **none of the above** | **all — every device on the box** |

Measured on the mute path (`exception:create`), confirming the key-driven
behaviour and that `matchAll` is stored but does not affect scope:

| `value` | Stored scope keys |
| --- | --- |
| no scope key, no `matchAll` | *(none)* — all devices |
| `matchAll: 1` + `p.device.mac` | `matchAll`, `p.device.mac` |
| `matchAll: 0` + `p.device.mac` | `matchAll`, `p.device.mac` — **identical to `matchAll: 1`** |
| `matchAll: 1`, no device | `matchAll` only — all devices |

**The MSP data model is explicit where the local wire format is implicit.**
`docs.firewalla.net/data-models/alarm/` defines **five** scope types and — the
important part — models `all` as a **first-class value**, not as absence:

| MSP `scope.type` | `scope.value` | Local `info` key |
| --- | --- | --- |
| `device` | device ID | `p.device.mac` |
| `group` | group ID | `p.tag.ids` |
| `user` | user ID | `p.tag.ids` |
| `network` | network ID | `p.intf.id` |
| `all` | — *(not used)* | **no scope key at all** |

**`scope` is a required field in the MSP mute body.** MSP therefore forces the
caller to state a scope, and `all` is an intentional selection. Locally the same
outcome is reached by *omitting* the keys — identical on the wire, but it means an
unintended global mute is what a caller gets by forgetting a field.

**Design consequence — mirror MSP's model, not the local wire format.** The
integration's mute service should take **`scope` as a required enum with an
explicit `all` value**, then translate `all` into key omission internally. That
makes "silence everything" a deliberate choice rather than a default. Do **not**
expose the local omission behaviour directly.

The same applies to the target: MSP requires `target` (`alarmType` / `domain` /
`ip`), while locally an omitted target is a whole-alarm-type mute. Expose
`alarmType` explicitly rather than leaning on absence — see Finding 34.

The app's "apply to" picker (`AlarmActionHelper.getMuteApplyToItems`, offering
**device / user / network / global**) already presents the choice explicitly, and
its `global` option is the `null` case that writes no key.


**`alarm:block` payload differences** (`ku7.m14064d` + `cd0.m2349a`):

- Same envelope as `allow`, but for `type` in (`dns`, `category`) it adds
  **`dnsmasq_only: true`** to `info`.
- **Blocks carry no `expireTs`** — the app never sets one for a block.
- For `category` blocks the app also adds a `customizedKeys` object with
  `app_uid` and `app_name`; for allows it sets `p.dest.app.id` instead.

**`matchAll` is always written** as `1` or `0` in both allow and block payloads.

### Finding 30: Alarm types and the app's filter grouping

**Scenario:**

- Recovered from `AlarmFiltersHelper.filterCategories` and
  `AlarmsHelper.allFilterTypesWithImplicit`.
- **Filtering is purely client-side**: these are `type` strings already present
  in the alarm list, so no additional box call is required to filter.

**Full type list** (`", "` separated in `filterCategories`):

`ALARM_INTEL`, `ALARM_LARGE_UPLOAD`, `ALARM_UPNP`,
`ALARM_LARGE_UPLOAD_2` (feature-gated behind `vf0.f34745H1`),
`ALARM_NEW_DEVICE`, `ALARM_VPN_CLIENT_CONNECTION`, `ALARM_VIDEO`,
`ALARM_GAME`, `ALARM_PORN`, `ALARM_DEVICE_BACK_ONLINE`,
`ALARM_ABNORMAL_BANDWIDTH_USAGE`, `ALARM_OVER_DATA_PLAN_USAGE`,
`ALARM_VPN_DISCONNECT`, `ALARM_DUAL_WAN`.

**Implicit companions** — the app folds related types into a filter category so
filtering matches user expectations. **A filter that ignores these will
under-report versus the app:**

- `ALARM_INTEL` → also `ALARM_BRO_NOTICE`, `ALARM_CUSTOMIZED_SECURITY`,
  `ALARM_SURICATA_NOTICE`
- `ALARM_DEVICE_BACK_ONLINE` → also `ALARM_DEVICE_OFFLINE`
- `ALARM_VPN_DISCONNECT` → also `ALARM_VPN_RESTORE`, `ALARM_VWG_CONN`

So the app's user-facing filters map as: **security → `ALARM_INTEL` (+3)**,
**abnormal upload → `ALARM_LARGE_UPLOAD`**, **open port → `ALARM_UPNP`**.

**MSP-only filter values** exist in `MspAlarmFilterType` with query values
`create`, `ignore` and `review` (Behavioural / Archived / Needs review). These
are **MSP API concepts**, not local runtime items, and are out of scope for the
local integration.

**Orphan types worth noting:** `ALARM_GAME`, `ALARM_VIDEO` and
`ALARM_ABNORMAL_BANDWIDTH_USAGE` were all observed in live data but
`ALARM_DEVICE_BACK_ONLINE`, `ALARM_VPN_DISCONNECT` and `ALARM_DUAL_WAN` were
not, so some listed categories may be dormant on this hardware.

### Finding 31: Alarm blocks create ordinary policy rules

**Scenario:**

- Confirmed live (2026-09-30): a block on `vimeo.com` for one MAC incremented
  `policyRules` from 306 to **307** and returned `{"policy": {"pid": "652", ...}}`.

**The created rule is a normal policy rule** and is already parsed by
`RuleManager`. Observed rule fields:

```json
{
  "pid": "652",
  "action": "block",
  "aid": "1728",
  "alarm_type": "ALARM_VIDEO",
  "reason": "ALARM_VIDEO",
  "type": "dns",
  "target": "vimeo.com",
  "target_name": "player.vimeo.com",
  "target_ip": "162.159.128.61",
  "if.type": "dns",
  "if.target": "vimeo.com",
  "dnsmasq_only": true,
  "scope": ["0C:85:E1:B0:1D:1C"],
  "direction": "bidirection",
  "activatedTime": "1790732668.522",
  "lastActivatedTime": "1790732668.522"
}
```

**Consequences:**

- The rule carries an **`aid` back-reference** to the alarm that created it, so
  alarm-created blocks are identifiable within the rule inventory.
- `alarm:unblock` removed the rule and `policyRules` returned to 306.
- **Do not build a separate rule layer for alarm blocks** — surface them through
  the existing rule machinery (`RuleManager`, `_COMMAND_POLICY_CREATE` /
  `_COMMAND_POLICY_DELETE`).
- Blocking therefore consumes a **policy rule slot** (`policyRuleNumber`), which
  is a finite resource worth noting for a bulk-block design.

### Finding 32: Bulk alarm commands (`ignoreAll`, `deleteArchivedAll`, `deleteActiveAll`)

**Scenario:**

- Confirmed live (2026-09-30) against the gold box.
- These are the app's "clear all" style operations. Unlike the single-record
  commands in Finding 28, they take an **empty value object** and no `alarmID`.

**Confirmed command contracts** (`mtype=cmd`, `target=0.0.0.0`, empty value):

| Operation | `item` | `value` | Response |
| --- | --- | --- | --- |
| Archive all active | `alarm:ignoreAll` | `{}` | `{}` |
| Delete all archived | `alarm:deleteArchivedAll` | `{}` | `{}` |
| Delete all active | `alarm:deleteActiveAll` | `{}` | **not tested** |

The builder is `ku7.m14063c`-adjacent: the app routes these through
`n03.m15334c0(item, cont)`, which builds an **empty** `JSONObject` and dispatches
via `n03.m15316F(box, item, {}, null, cont)` — i.e. `{"item": item, "value": {}}`.
`n03.m15318H` shows the same `{"item", "value"}` envelope for the `GET` variant.

**Measured effects:**

`alarm:ignoreAll` — archives every active alarm:

| | Before | After |
| --- | --- | --- |
| `activeAlarmCount` | 243 | **0** |
| `archivedAlarmCount` | 0 | **243** |
| `pendingAlarmCount` | 0 | 0 |
| `exceptionRules` | 99 | 99 (unchanged) |
| `policyRules` | 306 | 306 (unchanged) |

Spot-checked that previously-active aids (`1727`–`1732`, `1487`) all appear in
the `archivedAlarms` list afterwards, so the records **move** rather than being
discarded. `newAlarms` also dropped to 0.

`alarm:deleteArchivedAll` — deletes every archived alarm:

| | Before | After |
| --- | --- | --- |
| `activeAlarmCount` | 243 | 243 (unchanged) |
| `archivedAlarmCount` | **3** | **0** |
| `archivedAlarms` list | `['1723','1728','1733']` | `[]` |

Both return an empty `{}` body — the response carries **no confirmation**, so the
only way to verify success is to re-read the counts.

**Both are irreversible.** `ignoreAll` is the more recoverable of the two: the
alarms move to the archive where they remain visible and retrievable via
`item=archivedAlarms`. `deleteArchivedAll` destroys them permanently. There is
no un-archive command (Finding 28), so `ignoreAll` followed by
`deleteArchivedAll` is equivalent to a permanent bulk wipe.

**Side effect during this investigation:** running `ignoreAll` archived the
owner's entire active alarm history (243 records). This was explicitly
authorised for testing, and the alarms remain in the archive rather than being
lost — but it is a good illustration of why these commands need a confirmation
gate and should never be wired to a bare button.

**`alarm:deleteActiveAll` — confirmed 2026-09-30.** Now verified, closing the last
unverified alarm command. APK reference: `AlarmViewDelegate$setupMoreOperations$1$d$1$1$r$1`,
the `$deleteAllArchived == false` branch.

| | Before | After |
| --- | --- | --- |
| `activeAlarmCount` | 1 | **0** |
| `archivedAlarmCount` | 243 | 243 (unchanged) |
| `archivedAlarms` contains the deleted aid | — | **No** |

**It permanently deletes rather than archiving.** The single active alarm (`aid`
1735) disappeared from **both** the active and the archived lists. So the two
bulk deletes are complementary and neither is recoverable:

- `deleteActiveAll` → permanently removes every active alarm
- `deleteArchivedAll` → permanently removes every archived alarm

**All nine alarm commands are now live-verified.** No alarm operation remains
documented-from-APK-only.

**Artifacts:** `utils/probe_alarm_control.py --action {archive-all,
delete-archived-all, delete-active-all}` (dry-run by default).

### Finding 33: Silences are a separate object with two create paths and two delete paths

**Scenario:**

- Confirmed live (2026-09-30) after an initial partial reading of the app missed
  the standalone paths. The owner confirmed the app can mute and unmute an
  **archived** alarm, which does not fit `alarm:allow` — investigation found a
  second, alarm-independent mechanism.
- MSP documentation corroborates the model:
  *"muting … archives the alarm and instructs the box to create a silence
  exception"*, while *"archiving does not create a silence exception"*.

**A silence is its own object, not a flag on an alarm.**

Exception records live in the top-level `exceptionRules` array. Two identifier
fields matter and they are **not interchangeable**:

| Field | Identity | Used by |
| --- | --- | --- |
| `aid` | the originating alarm | `alarm:unallow` |
| `eid` | the exception itself | `exception:delete` |

**Confirmed: `fx2.java` reads `optString("eid")` into the field used as
`exceptionID`.** An exception created standalone has **no `aid` at all**.

**Two create paths:**

| Path | `item` | value | Requires |
| --- | --- | --- | --- |
| Mute from an alarm | `alarm:allow` | `{alarmID, matchAll, info{...}}` | an **active** alarm |
| Standalone mute | `exception:create` | see payload below | **nothing** |

`alarm:allow` operates on an active alarm — it archives that alarm *and* creates
the silence. **It returns HTTP 500 against an archived alarm**, because there is
no active record to act on. This is not a limitation on muting archived alarms;
it means `alarm:allow` is simply the wrong command in that context.

`exception:create` is the standalone path and needs no alarm:

```json
{
  "item": "exception:create",
  "value": {
    "type": "ALARM_GAME",
    "if.target": "example-mute-test.com",
    "if.type": "dns",
    "p.dest.name": "example-mute-test.com",
    "target_name": "example-mute-test.com"
  }
}
```

- `p.dest.name` is used for `if.type: "dns"`; `p.dest.ip` for `if.type: "ip"`
  (`AlarmSettingCategoryMuteDialog`, via `cua.m8202c`).
- Device scoping is added by `cua.m8202c`: **`p.device.mac`** for a device,
  **`p.tag.ids`** for a group/user tag, **`p.intf.id`** for a network. Omit all
  three for a global silence.
- Builders: `cua.m8200a` / `cua.m8201b`; item constant in `n33` (`EF77`).

Measured live: `exception:create` returned the created record with a fresh
`eid` (`106`) and `exceptionRules` grew 99 → 100. **No `aid` was present**, which
is what makes it independent of any alarm.

**Two delete paths:**

| Path | `item` | value | Scope |
| --- | --- | --- | --- |
| Alarm-tied unmute | `alarm:unallow` | `{alarmID: <aid>}` | **only** exceptions carrying that `aid` |
| Universal unmute | `exception:delete` | `{exceptionID: <eid>}` | **any** exception |

Measured live: `exception:delete` with `{"exceptionID": "106"}` removed the
standalone silence (exceptions 100 → 99) and returned `{}`.

Measured live: `alarm:unallow` with an **`eid`** passed as `alarmID` returned
**HTTP 500** and the silence remained. So `alarm:unallow` genuinely resolves by
alarm, not by exception.

**Why the app needs both:** `AlarmUnDoListener` issues `alarm:unallow` when the
user undoes a mute from the alarm feed (the alarm is known). `AlarmSettingsView`
and `am4.java` choose `alarm:unallow` when a matching alarm still exists, and
fall back to `exception:delete` when it does not. That fallback is what makes
mute-then-unmute work for **archived** alarms.

**Design consequence — `exception:delete` is the more general primitive.**
Any exception can be removed by `eid`, so a caller that already holds the
exception record never needs `alarm:unallow`. `alarm:unallow` is a convenience
that resolves alarm → exception internally. An integration that reads
`exceptionRules` and exposes `eid` can implement unmute with `exception:delete`
alone.

**The mute-scope caveat from Finding 29 still applies to both paths:** the
device/tag/network scope must be explicit. Omitting the scope keys produces a
**global** silence, which is the broadest possible action.

**Artifacts:** live session 2026-09-30; `AlarmSettingCategoryMuteDialog$saveDestinationRule$1$r$1.java`,
`cua.java`, `am4.java`, `AlarmSettingsView.java`, `AlarmUnDoListener.java`.

**Related MSP documentation** (`docs.firewalla.net/api-reference/alarm/`) confirms
the same model and adds: archive and mute require MSP 2.11.0+, `limit` caps at
500 with a default of 200 and cursor pagination, and mute takes an explicit
`target` (`alarmType` / `domain` / `ip`) plus `scope` (`all` / `device` / …).
The local runtime uses the equivalent `matchAll` + `info` envelope instead.

### Finding 34: Blocking is pure rule creation; silences support a target-less whole-type mute

**Scenario:**

- Confirmed live (2026-09-30). Two questions were open: whether block needs an
  active alarm, and whether the whole-alarm-type mute the MSP docs describe
  (`target: {type: "alarmType"}`) exists locally.

**Blocking does NOT need an active alarm — it is pure rule creation.**

The MSP API exposes **no** "block an alarm" or "unblock an alarm" endpoint. Its
alarm surface is only get / delete / archive / mute. That is a strong signal that
blocking is not an alarm feature at all: the app's block button creates an
ordinary policy rule, and the alarm's `aid` is merely recorded on it as a
back-reference.

Tested by blocking an **archived** alarm (`aid` 1726, `live-video.net`, scoped to
one MAC):

| | |
| --- | --- |
| Result | `{"policy": {"pid": "653", ...}}` — a new policy rule |
| `policyRules` | 321 → **322** |
| `alarm:unblock` | 322 → **321**, rule removed |

Note the `alarm:` prefix on the command is a UI-level naming choice, not
evidence of alarm ownership — the created object is a plain rule, and `RuleManager`
already parses it. **The MSP API's omission of a block endpoint is consistent with
this and is now explained.**

**A target-less silence is a whole-alarm-type mute.**

MSP's `target: {type: "alarmType"}` (silence every future alarm of this type,
whatever the destination) maps locally to `exception:create` with **`type` and no
target**:

```json
{ "item": "exception:create", "value": { "type": "ALARM_GAME" } }
```

Stored minimally as `{"type": "ALARM_GAME", "timestamp": ..., "eid": "108"}` —
no `if.target`, no `if.type`, no device keys. Verified: exceptions 99 → 100, then
removed by `exception:delete` back to 99.

This means the local silence surface covers **all three** MSP target forms:

| MSP `target.type` | Local equivalent |
| --- | --- |
| `alarmType` | `exception:create` with `type` only, no target |
| `domain` | `exception:create` with `if.type: "dns"` + `if.target` + `p.dest.name` |
| `ip` | `exception:create` with `if.type: "ip"` + `if.target` + `p.dest.ip` |

and all three MSP `scope` forms (`all` / `device` / group) via the presence or
absence of the device/tag/intf keys (Finding 29).

**Design consequence:** the local silence API is **a superset of MSP's mute
capability**, and one `exception:create` path expresses every variant MSP needs
three documented parameter combinations for. A single mute service parameterised
on (target type, target value, scope) covers the whole surface.

**There is one thing MSP does better, and it should be copied.** MSP requires
**both** `target` and `scope` in the mute body. Locally both are optional, with
omission meaning "whole alarm type" and "all devices" respectively — so the
broadest possible mute is what a caller gets by leaving fields out. MSP's
strictness is the safer design. **Mirror it: make `scope` required with an
explicit `all` value, and expose `alarmType` as an explicit target type rather
than relying on an omitted target.** The wire format stays identical; only the
service contract is stricter.

### MSP data model reference (for parity checks)

Recorded because it is a stable published contract and a useful cross-check when
a local field's meaning is unclear.

**Mute target types:** `alarmType` *(no value — silences every future alarm of
that type regardless of destination)*, `domain` *(wildcard matching applied
automatically, so `example.com` also matches `sub.example.com`)*, `ip`.

**Mute scope types:** `device`, `group`, `user`, `network`, `all` — see the table
in Finding 29.

**Alarm type is a NUMBER in MSP**, not the local `ALARM_*` string:

| MSP | Meaning | | MSP | Meaning |
| --- | --- | --- | --- | --- |
| 1 | Security Activity | | 9 | Gaming Activity |
| 2 | Abnormal Upload | | 10 | Porn Activity |
| 3 | Large Bandwidth Usage | | 11 | VPN Activity |
| 4 | Monthly Data Plan | | 12 | VPN Connection Restored |
| 5 | New Device | | 13 | VPN Connection Error |
| 6 | Device Back Online | | 14 | Open Port |
| 7 | Device Offline | | 15 | Internet Connectivity Update |
| 8 | Video Activity | | 16 | Large Upload |

This confirms the "Security Activity / Abnormal Upload / Open Port" filters the
app exposes map to MSP types 1, 2 and 14 — consistent with the `ALARM_INTEL`,
`ALARM_LARGE_UPLOAD` and `ALARM_UPNP` local strings plus their implicit
companions (Finding 30).

**Alarm status is a NUMBER in MSP: 1 = active, 2 = archived.** Note the
divergence — locally there is no status field, `state` is always `"active"`, and
archived is determined by **list membership** (`archivedAlarms`). Do not expect a
local status field to appear; the two models represent the same idea differently.

**Remote/category enums worth noting:** `Region` is a 2-letter ISO 3166 code, and
`Category` is one of `ad edu games gamble intel p2p porn private social shopping
video vpn` — the last maps to our `p.dest.category`.

**Artifacts:** live session 2026-09-30; MSP alarm docs at
`docs.firewalla.net/api-reference/alarm/`.

### Finding 35: `scope` is one concept across rules, silences and usage history — do not invent a fourth form

**Scenario:**

- Raised during alarm service design as a duplication risk. Confirmed by
  comparing MSP's data model against existing integration code.

**MSP models scope identically for rules and alarms.** The Searching reference
documents the Rule qualifier as returning
`scope: {"type": "device", "value": "AA:BB:CC:DD:EE:FF"}` — the **same**
structured shape as the alarm Mute Scope. So MSP has **one** scope concept, and
applies it wherever a target set is needed.

**Locally the same concept already exists in two forms, and a third was about to
be invented:**

| Where | Shape | Status |
| --- | --- | --- |
| Rule create payload (`models.py`) | `scope: list[str]` — flat identifiers, e.g. `["0C:85:E1:B0:1D:1C"]` | **Existing** |
| Usage history (`get_time_usage_report`) | `scope_kind` + `scope_target` — kind enum plus one value | **Existing** |
| Alarm mute (proposed) | `scope` + `scope_value` | ❌ **Would have been a duplicate of the row above** |

**The established convention is `scope_kind` + `scope_target`.** Used verbatim:

```python
SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND: Final = "scope_kind"
SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET: Final = "scope_target"
```

```python
vol.Required(SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND): vol.In(("device", "group", "user")),
vol.Required(SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET): cv.string,
```

**The vocabularies already agree.** MSP's alarm scope types are
`device, group, user, network, all`. The local usage-history enum is
`device, group, user` — **a subset of the same three values, in the same order**.
That is not a coincidence; the local surface was already built to match MSP's
scope vocabulary.

**Alarms therefore need only extend the existing enum**, not introduce anything
new:

| `scope_kind` | Local protocol translation |
| --- | --- |
| `device` | `p.device.mac` |
| `group` | `p.tag.ids` |
| `user` | `p.tag.ids` |
| `network` | `p.intf.id` |
| `all` | omit every scope key |

This mirrors the existing internal mapping already in `services.py`, which
translates `scope_kind=device → request_scope_type=host` and
`scope_kind=user → request_scope_type=tag` — a kind→protocol-type seam that
alarms can reuse rather than re-implement.

**Conclusion: use `scope_kind` + `scope_target` for alarm mute and block, and
extend the enum with `network` and `all`.** Do **not** introduce `scope` /
`scope_value`, and do **not** reuse the MSP wire name `scope` for a parameter —
`scope` already means the flat rule identifier list elsewhere in the codebase.

**Why the shapes differ at all.** The structured `{type, value}` form is MSP's
API-layer abstraction. Locally every write path uses flat keys or lists
(`p.device.mac`, `p.tag.ids`, `p.intf.id` for silences; a flat list for rule
create). The structured form is therefore a **service-contract** concern, and the
translation to flat keys belongs in the manager — not in the service schema and
not in the model.

### Finding 36: MSP search and pagination conventions

**Scenario:**

- Reviewed because the local page-size behaviour was previously unclear
  (Finding 27 recorded that local `alarms` honours `count` while `archivedAlarms`
  honours `limit`).

**Pagination is cursor-based, not offset.**

- Every paged response except the last carries a base64 **`next_cursor`**.
- Every request after the first must echo it back as **`cursor`**.
- The canonical loop is `while (1) { fetch; push results; if (!next_cursor) break; params.cursor = next_cursor; }`.

**`limit` is the documented page-size name: default 200, maximum 500.**

This resolves the earlier local confusion. **`limit` is the MSP-canonical name**,
which explains why the local `archivedAlarms` handler honours it — that item is
MSP-shaped. The local `alarms` item honouring `count` is the **outlier**, not the
norm.

**Design consequence:** name our service parameter **`limit`**, not `count` —
it matches MSP, matches the local `archivedAlarms` item, and matches what a user
familiar with Firewalla will expect. Send both keys on the wire (Finding 27), but
expose only `limit` in the service contract.

**A `ts` default window exists in MSP and has no local equivalent.** From the
Alarm qualifiers: *"If no `ts` qualifier is provided, results default to the last
30 days."* The local `alarms` item has no such window — `count: 1000` returned
all 243 regardless of age. Worth knowing when sizing a default page.

**Alarm search exposes a documented qualifier surface** (MSP Searching → Alarm
Qualifiers), considerably richer than a simple type filter:

| Qualifier | Alias | Example |
| --- | --- | --- |
| `ts` | — | `ts:<1695196894.395` — with `sortBy` for ordering |
| `type` | `AlarmType` | `type:1,2,3` or by name |
| `status` | — | `status:active` |
| `box.id`, `box.name` | `Box` | |
| `box.group.id` | — | |
| `device.id` | `Mac` | `"AA:BB:CC:DD:EE:FF"` |
| `device.name` | `Device` | `device.name:iphone` |
| `device.network.id`, `device.network.name` | `Network` | |
| `remote.category` | `Category` | `remote.category:porn,game` |
| `remote.domain` | `Domain` | `remote.domain:google.com` |
| `remote.region` | `Region` | 2-letter ISO code |
| `transfer.download` / `.upload` / `.total` | `Download`/`Upload`/`Total` | `>10MB`, with units |

Query syntax supports literals, wildcards (`*iphone*`), quoted strings,
exclusion (`-status:active`), numeric comparisons (`>`, `>=`, `<`, `<=`) and
ranges (`n-m`), across space-separated terms. **Syntax is MSP-only** — the local
runtime takes no query grammar, as established earlier. Recorded only so our
service's simple filters can be documented as a deliberate subset rather than
looking like an oversight.

**Units are decimal, not binary:** `KB = 1000 B`, `MB = 1000 KB`, `GB = 1000 MB`,
`TB = 1000 GB`. Relevant if any byte thresholding is ever exposed.

### Finding 37: Alarm data-model terminology — align to MSP and to our own existing names

**Scenario:**

- Reviewed MSP's published Alarm data model
  (`docs.firewalla.net/data-models/alarm/`) against the local `p.*` keys
  enumerated in Finding 26 and against naming already present in this codebase.

**The local payload carries nearly everything MSP models — under different names.**

| Concept | MSP field | Local raw key | Local normalized name today |
| --- | --- | --- | --- |
| Destination host | `remote.domain` | `p.dest.domain` / `.name` | **`remote_host`** ✔ already aligned |
| Destination IP | `remote.ip` | `p.dest.ip` | **`remote_ip`** ✔ already aligned |
| Destination region | `remote.region` | `p.dest.country` | *(not modelled)* |
| Destination category | `remote.category` | `p.dest.category` | *(not modelled)* |
| Destination app | *(none — local only)* | `p.dest.app` / `.app.id` | *(not modelled)* |
| LAN device | `device.name` / `.id` / `.ip` | `p.device.name` / `.mac` / `.ip` | *(no alarm model yet)* |
| Network | `device.network` | `p.intf.name` / `.desc` / `.id` / `.subnet` | *(not modelled)* |
| Group / user | `device.group` | `p.tag.*` / `p.utag.*` | *(not modelled)* |
| Transport | `protocol` | `p.protocol` | ✔ same word |
| Timestamp | `ts` | `timestamp` **and** `alarmTimestamp` | *(two candidates)* |
| Status | `status` (1 active / 2 archived) | `state` (always `"active"`) | *(no equivalent)* |

**`remote_*` is already our word — `dest` is not.** Measured: `dest` appears
**zero times** in `models.py`, and `remote_host` / `remote_ip` already exist on
`FirewallaNetworkHostRanking`, populated in `integration_manager.py` and
serialized in `services.py`. MSP also calls it `remote`. **So the alarm model
should use `remote_*`.** Using `dest_*` would be a third vocabulary for a concept
we already name, against both our own precedent and Firewalla's.

**Values agree where names differ.** `p.dest.country` holds ISO 3166 alpha-2
codes — observed `US` (204), `GB` (2), `DE` (1) across 231 records — which is
exactly MSP's `remote.region` definition (*"Region of the remote IP, a 2-letter
ISO 3166 code"*). Only the **name** diverges: `country` locally, `region` in MSP.
Both are defensible; `region` matches Firewalla's model, `country` is more
plainly understood. **Pick one and document it** rather than leaving a raw
passthrough.

**`p.protocol` matches MSP exactly** — observed `tcp` (150) and `udp` (55), the
same two values MSP documents.

**Category vocabulary genuinely diverges — and has an internal inconsistency.**

MSP `Category` is: `ad edu games gamble intel p2p porn private social shopping
video vpn`. Observed locally across 231 records: `games` (125), **`av` (71)**,
`intel` (9).

- `games` and `intel` **match** MSP.
- **`av` does not exist in MSP's list** — MSP's equivalent is `video`.

Separately, the local vocabulary is **internally inconsistent about number**: the
category is plural (`games`) while the alarm *type* is singular (`ALARM_GAME`).
And the category says `av` while the type says `ALARM_VIDEO` — two words for the
same idea within one payload.

**This is unresolved and should not be guessed at.** Options are that MSP maps
`av → video` in its own API layer, or that the two vocabularies are genuinely
different. **Recommendation: keep local category values raw for now** (consistent
with the raw-`ALARM_*`-type decision), document `av` as the box's audio/video
value, and do not build a mapping table to MSP's vocabulary without evidence that
one is needed.

**Two timestamps where MSP has one.** MSP models a single `ts`. Locally
`timestamp` and `alarmTimestamp` are both present and **differ** (observed gaps
of seconds to minutes). **Recommendation: treat `alarmTimestamp` as the MSP `ts`
equivalent** — it is the later, alarm-specific value, while `timestamp` appears
to be the underlying flow or detection time. Decide once, document the choice on
the field, and surface only one by default.

**`status` has no local equivalent, and should not be invented.** MSP reports
1 = active / 2 = archived as a field. Locally `state` is **always `"active"`** —
observed on all 231 records including archived ones — and archived-ness is
expressed only by **list membership** (`archivedAlarms`). If the integration
needs to expose archived state, derive it and name it as such
(`is_archived` from list membership); do **not** add a `status` field implying a
payload source that does not exist.

**MSP models some things the local payload does not carry at all.** Worth knowing
so their absence is not mistaken for a parsing gap:

- **`direction`** (`inbound` / `outbound` / `local`) — no `direction` key observed
  in any alarm record. Rules carry `direction: bidirection`; alarms do not
  appear to.
- **`dataPlan`** (`quota`, `begin`, `end`) — for MSP type 4. No `quota` key
  observed; the nearest local evidence is `p.totalUsage` on bandwidth alarms.
- **`wan`** (`name`, `status`, `active`, `switched`, `type`, `ready`) — for MSP
  type 15. Locally WAN state lives in the separate `events` timeline
  (`FirewallaWanEvent`), not on alarms.
- **`port`** (`devicePort`, `protocol`, `publicPort`, `description`) — for MSP
  type 14. Local `p.device.port` exists on security alarms but is a bare value,
  not the structured object.
- **`vpn`** (`id`, `name`, `type`, `subType`, `deviceCount`, `strict`) — local has
  only `p.vpnType` and the peer keys, not the full object.

**Fields local to the box with no MSP equivalent** (do not expect to map them):
`p.cloud.decision`, `p.severity` / `p.severity.score`, `p.quarantine`,
`p.fi`, `p.showMap`, `p.timestampTimezone`, `p.action.block`, `p.alarm.trigger`,
`p.security.*`, `result` / `result_policy` / `result_method`,
`p.local_is_client`, `p.from`, `p.dest.app` / `.app.id`, `p.begin.ts` / `p.end.ts`
/ `p.duration` / `p.flows` / `p.percentage` / `p.totalUsage`.

**Alignment summary — what to adopt before building:**

1. **`remote_*`, not `dest_*`** — matches MSP and our own existing model.
2. **`remote_region`, not `remote_country`** — matches MSP's name for identical
   ISO alpha-2 data. *(Or keep `country`; but choose deliberately.)*
3. **`alarmTimestamp` is the `ts` equivalent.** Surface one timestamp by default.
4. **No `status` field.** Derive `is_archived` from list membership if needed.
5. **Keep `ALARM_*` types and category values raw**, and document `av` as the
   box's audio/video category.
6. **Do not invent MSP sub-objects** (`transfer`, `vpn`, `wan`, `port`,
   `dataPlan`) unless a real need appears; the flat local keys work.

### Finding 38: Rule data model cross-check — what it clarifies for alarms

**Scenario:**

- Reviewed MSP's Rule data model (`docs.firewalla.net/data-models/rule/`) against
  Finding 37's open alarm-alignment questions and against the existing local rule
  implementation. Purpose: see whether the second model resolves anything the
  first left ambiguous.

**Six things it clarifies.**

**1. MSP does not have one canonical category list — it has two.** This resolves
the `av` question's framing:

| Model | Categories |
| --- | --- |
| MSP **Rule** target | `drugs games gamble p2p porn social shopping video violence vpn` |
| MSP **Alarm** remote | `ad edu games gamble intel p2p porn private social shopping video vpn` |

Against a 213-bit intersection of games / gamble / p2p / porn / social / shopping /
video / vpn, each model adds its own: Rule adds `drugs`, `violence`; Alarm adds
`ad`, `edu`, `intel`, `private`.

**Consequence:** there is no single upstream vocabulary to align to, and the
integration already targets both surfaces. Keeping category values **raw** — the
existing decision — is now clearly correct rather than merely convenient. The
local `av` value remains local-only with no MSP counterpart in either list.

**2. `region` has cross-model precedent; `country` has none.** MSP uses
`region` in **both** the Rule target (`region`, 2-letter ISO 3166) and the Alarm
remote (`remote.region`, also 2-letter ISO 3166). The word `country` appears
nowhere in either MSP model, yet the local payload key is `p.dest.country`.

**Consequence:** strengthens the recommendation to normalize to
`remote_region`. `country` stays as the raw key name only.

**3. The `all` scope value is alarm-mute-specific, not a general scope concept.**
MSP defines:

| Model | Scope types |
| --- | --- |
| Rule | `device group user network` — *"unset for all devices"* |
| Alarm mute | `device group user network all` |

So rules express "all devices" by **absence**, exactly like the local wire format,
while alarm mute is the one place MSP models `all` explicitly.

**Consequence:** keep `all` in the **alarm** service enum only. Do not push it into
a shared scope helper that rules also use, since rules legitimately mean
"all" by omission. This also confirms the local usage-history enum
(`device, group, user`) is correctly a subset.

**4. Derived status is already the local pattern — so `is_archived` fits.**
MSP Rule carries `status: active | paused` and `resumeTs`. Locally
`FirewallaPolicyRule` has **no status field**: it holds `enabled` plus an
`idle_ts` property read from the raw payload, and derives the display value:

```python
status = _STATUS_ENABLED if rule.enabled else _STATUS_DISABLED
```

**Consequence:** deriving alarm archived-state rather than expecting a payload
field is **consistent with how rules already work**, not an alarm-specific
workaround. It also explains why alarms have no status field — the local runtime
consistently represents state as a boolean plus an auxiliary timestamp rather
than a status enum.

*(Note the vocabulary differs anyway: local rules say `enabled`/`disabled`, MSP
says `active`/`paused`. Not worth changing, but do not treat MSP's strings as
authoritative for our surfaces.)*

**5. Multiple timestamps is a pattern, not an anomaly.** MSP Rule carries `ts`
(created), `updateTs` (last update) and `resumeTs` (auto-resume); MSP Alarm
carries only `ts`. Locally the alarm has **two** (`timestamp` and
`alarmTimestamp`) and rules carry `last_activated_time` plus `idle_ts`.

**Consequence:** the two alarm timestamps are unremarkable in context, and
`alarmTimestamp` mapping to `fired_at` remains the sensible choice. Expect more
than one timestamp per record and name each explicitly rather than picking a
generic `timestamp` field.

**6. `direction` genuinely does not exist on alarms.** MSP Rule defines
`direction: bidirection | inbound | outbound`, and local rules already carry
`direction: bidirection`. MSP Alarm has no `direction` field, and no `direction`
key was observed in any local alarm record.

**Consequence:** confirmed as a real payload difference. Do not add a `direction`
field to the alarm model.

**Two divergences worth noting without acting on them:**

- **`dnsOnly` vs `dnsmasq_only`.** MSP models DNS-only as a **boolean flag** on
  a target (`dnsOnly`, defaulting true for block rules on `category`/`app`/
  `targetlist`/`domain`). Locally, `dns` is a **target *type*** and the payload
  key is `dnsmasq_only`. Structural difference, not just a name: MSP qualifies a
  target, we select one. Both are valid; do not force alignment.
- **Time limits use different models.** MSP has an `action: "timelimit"` with a
  `timeUsage` object (`quota`, `used` in minutes). Locally, time limits are
  expressed through `disturbLevel` / `disturbMethod` / `appTimeUsage` and the
  `disturb` action. MSP's documented action list is
  `allow | block | timelimit`; ours is `allow | block | disturb | qos | route` —
  **the local set is wider and differently shaped.** Treat MSP's list as
  incomplete for local purposes, not as the target vocabulary.

**Summary of what the rule model settles:** all six of Finding 37's alignment
decisions stand, four of them with stronger evidence than the alarm model alone
provided. It also removes a possible over-correction — do **not** generalise the
`all` scope value beyond alarm mute.

### Finding 39: Alarm reads accept NO time filter — and the box already retains roughly 30 days

**Scenario:**

- A 30-day default window was specified for the alarm read service on the
  assumption that the local runtime accepted a time bound, extrapolated from
  MSP's `ts` search qualifier. This was **not verified** and the assumption was
  challenged before implementation. Tested directly.

**Result: no time filter exists. All eight candidate parameter names were
silently ignored.**

Measured against 230 archived records with a cutoff of `newest - 24h`:

| `value` | Returned |
| --- | --- |
| `{"limit": 1000}` (baseline) | 230 |
| `{"limit": 1000, "tsFrom": <cutoff>}` | **230** — ignored |
| `{"limit": 1000, "beginTs": <cutoff>}` | **230** — ignored |
| `{"limit": 1000, "from": <cutoff>}` | **230** — ignored |
| `{"limit": 1000, "begin": <cutoff>}` | **230** — ignored |
| `{"limit": 1000, "since": <cutoff>}` | **230** — ignored |
| `{"limit": 1000, "days": 1}` | **230** — ignored |
| `{"limit": 1000, "ts": <cutoff>}` | **230** — ignored |
| `{"limit": 1000, "query": "ts:><cutoff>"}` | **230** — ignored |

Unknown keys are **silently discarded**, not rejected — so a caller passing a
time bound gets no error and no filtering. That is the dangerous shape: the
parameter appears accepted.

This is consistent with the general finding that **the local runtime takes no
query grammar**. MSP's `ts` qualifier is a search-API concept with no local
equivalent. Do not retry this.

**But the 30-day default is satisfied anyway — by the box itself.**

| Item | Records | Oldest record age |
| --- | --- | --- |
| `archivedAlarms` | 230 | **29.9 days** |
| `alarms` | 0 *(no active alarms at test time)* | — |

The oldest alarm the box will return is ~30 days old, and the archive spans the
full retained history (it contains everything ever archived, including records
created before the current session). **No alarm older than ~30 days exists to
retrieve.**

**Interpretation — stated with appropriate caution.** This is **one observation**
and is consistent with a ~30-day box-side retention policy, but a retention
policy is *not* proven: the alternative is that no older alarms happen to exist
on this box. The practical conclusion holds either way:

- **No client-side 30-day filtering is needed**, because the box does not return
  older records.
- **No `ts_from` parameter should be added**, because there is nothing to filter
  and no server-side mechanism to filter with.
- **`limit` returns the newest N, full stop** — with no window to configure.

**Design consequence:** drop the planned `ts_from` parameter. Document on the
service that the box retains roughly the last 30 days and that `limit` therefore
returns the newest records available within that retained set. If a caller needs
"alarms in the last hour", that is client-side filtering over a small `limit` —
which is cheap precisely because the retained set is bounded.

**Artifacts:** live session 2026-09-30, `utils/probe_alarm_control.py`.

### Finding 40: WAN events require the app's `filters` — an unfiltered read is a DNS-probe firehose

**Scenario:**

- The `get_wan_events` service returned 99 records dominated by events the
  Firewalla app does not show in its WAN events view. The owner compared the app
  (3 events over several days: one high-latency alert, one `WAN-ONE` restored,
  one WAN disconnected) against the service output and found no correlation.
- Suspected cause: the service issues a bare `item=events` read, while the
  pairing/init path sends a `filters` array (`api/client.py:723-735`).

**Result: confirmed. The app filters; an unfiltered read is dominated by the
box's own DNS health probes.**

Measured on the live box 2026-10-01 via `item=events` with `parse_json` and
`reverse` set, grouping raw records by `state_type` / `action_type`:

| `value` | Records | Composition |
| --- | --- | --- |
| unfiltered, `limit_count: 100` | 100 | **93 `dns`**, 6 `ping`, 1 `ping_RTT` |
| app filters, `limit_count: 100` | **2** | `wan_state` ×2 |
| app filters, `min` = 7 days | **2** | `wan_state` ×2 |
| ping filters, `min` = 7 days | **1** | `ping_RTT` ×1 |
| `dns` filter only, `min` = 7 days | **162** | `dns` ×162 |

The DNS probes are `state_key` / `name_server` = `127.0.0.1` with
`dns_test_domain` = `github.com`, firing roughly every three minutes — the box
health-checking its own resolver. **162 of them accumulate in a week**, so a
count-limited unfiltered read returns almost nothing else. The app never asks
for them.

**The app's filter set (verbatim from the init capture):**

```json
"value": {
  "min": <24h_ago_ms>,
  "reverse": true,
  "parse_json": true,
  "filters": [
    {"event_type": "action", "sub_type": "system_reboot"},
    {"event_type": "state", "sub_type": "dualwan_state"},
    {"event_type": "state", "sub_type": "wan_state"}
  ]
}
```

Filtered to that set, the two `wan_state` records are exactly the owner's
`WAN-ONE restored` / `WAN disconnected` pair. The third event the app shows —
the high-latency alert — comes from the **separate** `ping_RTT` / `ping_lossrate`
action feed (Finding 25), which is a threshold-crossing alert stream, not a
sample stream. That is the alert feed, not a WAN link event.

**`min` is honoured here — unlike alarm reads.** `item=events` accepts a
millisecond epoch `min` and filters by it (the 7-day window returned a strict
subset of the unfiltered set, and the DNS filter returned 162 in-week records).
This is a **direct contrast with Finding 39**, where alarm reads silently ignore
every candidate time parameter. The events item is the one place so far where a
time bound actually works. `limit_count` / `limit_offset` also work, but a count
limit over the unfiltered firehose is unstable by construction — it returns
whatever the newest N records happen to be.

**Ordering note:** the records carry `ts` in **milliseconds**, and the payload is
requested with `reverse: true` (newest first). The normalized model converts to
seconds.

**Implementation impact:**

- **Send `filters` on every `item=events` read.** An unfiltered read is not a
  WAN event read; it is the DNS probe log with a WAN event occasionally in it.
- **`ping_RTT` / `ping_lossrate` do not belong in WAN events.** They are the
  Internet Quality alert feed — quality already surfaces ping latency (mean /
  max / median / min) and packet loss percentage from `networkMonitorData`
  (Finding 25), so latency and loss have a correct home and should not be
  duplicated as link events.
- **`system_reboot` is not currently a supported action family.** The normalized
  model accepts only `ping_RTT` / `ping_lossrate` for `event_type: "action"`
  (`_SUPPORTED_WAN_EVENT_ACTION_FAMILIES`), so the app's `system_reboot` filter
  would produce records the model silently drops. Add the family if reboots are
  wanted.
- **`dns` should not be a default family.** It is in
  `_SUPPORTED_WAN_EVENT_STATE_FAMILIES`, which is why DNS probes reach the
  normalized output at all. Keep it reachable only as an explicit exception.
- **A 7-day window is affordable once filtered.** With the app's filter set the
  entire retained history here is 2 records, so `min` can be used as the primary
  selector instead of a count limit.

**Design consequence for the service/tool:** default to the app's link-state
filter set over a **7-day** `min` window, exclude `dns` unless explicitly
requested, and leave latency/loss alerting to Internet Quality. That reduces the
payload from 57,762 bytes of mostly-DNS noise to a handful of real events.

**Artifacts:** live session 2026-10-01; raw probe output
`/tmp/wanprobe_*.json`; comparison `.tmp/quality_events.json` (the ping alert
feed, captured 2026-09-10).

## Capture workflow note

Later in reverse engineering, repeated zero-byte pcap files were traced to two
operational issues rather than protocol behavior:

- remote `/tmp` on the Firewalla box had filled to 100% from accumulated capture
  files
- relying on the VS Code terminal lifecycle was not a reliable way to ensure the
  remote `tcpdump` process had flushed and exited before copying the pcap

Current mitigation:

- delete old remote capture files regularly
- stop remote `tcpdump` explicitly by PID with `SIGINT`
- verify remote file size before copying the pcap locally
- whether other rule families use `policy:update` rather than `delete`
- whether `useBf` empty string versus boolean `true` is semantically important
  or just shape variance
- whether there are additional rule families that toggle in place without being
  obvious from the UI label
- whether time-bounded pause or resume actions rely on a separate update
  contract rather than create and delete

## Maintenance rules for this document

When a new capture is completed:

- add the scenario to the findings matrix
- include the exact decoded mutation payload
- record whether the action created, deleted, or updated an existing rule
- record the resulting normalized rule shape
- record the implementation impact if the new family changes switch behavior

Do not summarize away payload fields that may later matter for the protocol.

**Where to look for prior evidence.** When this document is silent on a payload,
check `.tmp/` **before** concluding the shape is unknown. `.tmp/` is gitignored,
so it does not appear in normal repository searches, yet it holds a large corpus
of decoded captures, live runtime pulls and two decompiled APK trees:

- `.tmp/live_gold/<timestamp>/runtime_init.json` — full init payloads
- `.tmp/firewalla_*_capture.decoded.txt` — decoded command/response captures
- `.tmp/capture_*.json` — before/after mutation captures
- `.tmp/Firewalla_1.69.1+(27)_jadx/` and `..._jadx_debug/` — decompiled sources
  (the `_debug` tree sometimes yields readable bodies where the other does not)

Finding 26 is the worked example: `newAlarms` and `activeAlarmCount` were
initially recorded here as undocumented, then recovered in full from
`.tmp/config_entry-*.json` and `.tmp/live_gold/`. Record the **artifact path** in
every finding so the evidence is reproducible rather than re-derived.

**Live pulls are the preferred evidence source** for shape confirmation:
`python utils/pull_runtime.py --artifact-dir <dir>` reads the working credentials
from the Home Assistant config entry, so it needs no re-pairing and no packet
capture. For write contracts, `utils/probe_alarm_control.py` (and similar
probes) send real commands and are dry-run by default.

**Warn about side effects.** Some commands are not reversible. Alarm
archive/mute/block leave the alarm archived permanently (Finding 28); only
`alarm:delete` removes it. Any finding that documents a write command must state
whether it is reversible, and probes that write should target a value the user
can afford to lose — ideally confirming first with the owner.

**Treat bulk commands as a separate risk class.** `alarm:ignoreAll` and
`alarm:deleteArchivedAll` (Finding 32) return an empty `{}` **whether or not they
succeeded**, so the response is no confirmation at all — success can only be
established by re-reading the counts. They also act on everything, so there is no
blast-radius limit. Document them with an explicit irreversibility warning, verify
via counts, and never infer success from the response body.

**Correct your own earlier findings explicitly.** When a later measurement
overturns an earlier one, edit the original finding and mark the correction in
place rather than silently rewriting it — see the `count`/`limit` correction in
Finding 27, which is the second time a first-pass claim in this section proved
wrong. Recording *that* a claim was wrong is as useful as the corrected claim,
because it tells the next reader which conclusions were single-observation.

## Appendix: APK reverse engineering

This section documents how the Firewalla Android APK was obtained and
decompiled during the Gold SE 412 investigation (Issue 14). It is preserved
here so the process can be reproduced when a newer app version needs analysis.

### Downloading the APK

1. **Find the APK on a third-party APK mirror.** The Firewalla app (package
   `com.firewalla.chancellor`) is available from sites such as APKMirror or
   APKPure. Search for `Firewalla` and download the variant matching the
   target version.

2. **Extract the APK.** If the download is an `.apkm` (APK Mirror bundle),
   extract it — the main APK file is the one with the package name, e.g.
   `com.firewalla.chancellor.apk`.

3. **Verify the manifest.** The APK metadata (package, version, SDK levels)
   can be read without decompilation:
   ```bash
   unzip -p com.firewalla.chancellor.apk AndroidManifest.xml | strings | head -30
   ```
   The confirmed identifiers are `com.firewalla.chancellor`, version
   `1.69.1 (27)`, min SDK 29, target SDK 36.

### Decompiling with JADX

[JADX](https://github.com/skylot/jadx) is a DEX-to-Java decompiler that
handles most ProGuard / R8 obfuscation.

1. **Install JADX** (if not already present):

   ```bash
   # Download the latest release
   curl -L -o jadx.zip https://github.com/skylot/jadx/releases/download/v1.5.1/jadx-1.5.1.zip
   unzip jadx.zip -d /tmp/jadx
   ```

2. **Run JADX:**

   ```bash
   /tmp/jadx/bin/jadx -d /tmp/jadx_src --show-bad-code -j 8 \
     /path/to/com.firewalla.chancellor.apk
   ```

   - `-d` — output directory for decompiled Java sources
   - `--show-bad-code` — emit decompilation attempts even for methods JADX
     cannot fully recover (due to R8 control-flow flattening)
   - `-j 8` — use 8 parallel threads

3. **Expected outcome.** The majority of the codebase decompiles into readable
   Java under `/tmp/jadx_src/sources/defpackage/`. Some methods in classes
   like `fy3`, `s73`, and `a93` will fail to decompile due to R8 control-flow
   flattening — their bodies emit as error stubs or bad-code blocks. These
   methods can still be inspected at the Smali level if needed (see below).

### Key files in the decompiled source

| File | Purpose |
| --- | --- |
| `wx3.java` | Message envelope builder. `d()` constructs the inner encrypted JSON; `c()` builds the outer HTTP payload with `timestamp` and `message` keys. |
| `y2.java` | Message sending coroutine. Case 2 handles local encipher messages — it calls `wx3.c()` then adds `"mtype":"msg"` to the outer payload (though captured traffic does not show this field). |
| `s73.java` | HTTP client for local communication. The `U()` method (heavily obfuscated) orchestrates message sending. |
| `n73.java` | Box descriptor model. `m15464y()` resolves the encryption key with `rkey` priority. Contains model sets including `gse` (Gold SE) alongside `gold`, `gold_plus`, etc. |
| `fy3.java` | Main message hub / router — sends messages via cloud (`a()`) and local (`b()`) paths. Contains obfuscated methods. |
| `ue3.java` | Symmetric key entry parser — extracts `key` (RSA-encrypted) and `rkey` (rotation key JSON) from the cloud group response. |
| `s97.java` | Crypto utilities — AES-256-CBC encrypt/decrypt, RSA decrypt, and the `m18101c()` / `m18106q()` helpers used by the key derivation chain. |
| `ku7.java` | Alarm (and related) action command builder. `m14063c(item, box, alarm, cont)` builds id-only commands (`alarm:ignore`, `alarm:delete`, `alarm:unallow`, `alarm:unblock`); `m14064d(applyTo, item, type, target, box, alarm, expireTs, archiveByType, app, cont)` builds scoped mute/block payloads. `m14068k(...)` builds the `alarmDetail` read. See Findings 28–29. |
| `fx2.java` | Alarm model. Field mapping confirmed: `optString("aid")` → the value used as `alarmID`, and `optString("p.device.mac")` → the mute/block `device` scope. The parser `m10449j0(JSONObject)` did **not** decompile, so field names were recovered from live payloads. See Finding 26. |
| `gx2.java` | Alarm container — holds `ArrayList<fx2>`; `m11206b(JSONArray)` parses the `newAlarms` array. |
| `AlarmMuteScheduleDialog.java` | Defines the three mute durations and their `expireTs` computations. See Finding 29. |
| `AlarmFiltersHelper.java` | `filterCategories()` returns the alarm type list used by the app's filters. See Finding 30. |
| `AlarmsHelper.java` | `allFilterTypesWithImplicit()` adds the implicit companion types folded into each filter category. See Finding 30. |
| `cd0.java` | `m2349a(info, action)` adds `dnsmasq_only` to `dns`/`category` block payloads. See Finding 29. |
| `l33.java` | Message-type enum — `GET`=1, `SET`=2, `CMD`=3, `INIT`=4. Confirms alarms use `get` for reads and `cmd` for writes. |

### Confirmed outer payload format (Android app v1.69.1)

From `y2.java` case 2 and `wx3.java`:

```java
// wx3.c() builds:
JSONObject outer = new JSONObject();
outer.put("timestamp", System.currentTimeMillis() / 1000);
outer.put("message", encrypted_payload);

// If the box metadata (n73.y0) has a "ts" value, send it as rkeyts:
long optLong = jSONObject2 != null ? jSONObject2.optLong("ts") : 0L;
if (optLong > 0) {
    outer.put("rkeyts", optLong);
}

// y2.java caller then adds:
c.put("mtype", "msg");       // mtype added to outer by the message sender
c.put("rkeyts", 1);          // fallback: rkeyts=1 when box has no ts
```

The APK source confirms the app sends both `timestamp` and `mtype"msg"` in
the outer envelope, plus `rkeyts` when available. **However, captured phone
traffic does not show `mtype` in the outer envelope** — neither the working
Gold capture nor the Gold Plus capture. The box accepts messages both with
and without it. The integration does not send `mtype` in the outer envelope.

The final HTTP body sent to `POST /v1/encipher/message/{gid}`:

```json
{"timestamp": 1234567890, "message": "<encrypted>"}
```

When `rkeyts` is present (box has rotation key metadata):

```json
{"timestamp": 1234567890, "message": "<encrypted>", "rkeyts": 1765640872536}
```

### Captured init message structure

The phone's full init sequence (captured from v1.69.1-71 on iOS) uses a
multi-stage approach. The first init is a simple handshake:

```json
{
  "from": "iPhone",
  "obj": {
    "mtype": "init",
    "id": "<uuid>",
    "data": {
      "get": "0.0.0.0",
      "COMMAND_TIMEOUT": 15
    },
    "type": "jsonmsg",
    "target": "0.0.0.0"
  },
  "appInfo": {
    "deviceName": "iPhone",
    "appID": "com.rottiesoft.circle",
    "platform": "ios",
    "timezone": "America/New_York",
    "language": "en",
    "version": "1.69.1-71",
    "eid": "<eid>",
    "ios": "26.5-0"
  },
  "msg": "",
  "type": "jsondata",
  "compressMode": 1,
  "mtype": "msg"
}
```

The second init requests multiple back-end data sources:

```json
{
  "from": "iPhone",
  "obj": {
    "mtype": "init",
    "id": "<uuid>",
    "data": {
      "value": {},
      "get": "0.0.0.0",
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
            "min": <24h_ago_ms>,
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
      ]
    },
    "type": "jsonmsg",
    "target": "0.0.0.0"
  },
  "appInfo": {"<same as above>"},
  "msg": "",
  "type": "jsondata",
  "compressMode": 1,
  "mtype": "msg"
}
```

The phone repeats the second init up to 3 times, interleaved with SSE/GET
polling for live stats, before the box returns the full runtime payload.

### Init request variants

The init request supports a boolean `includeInactiveHosts` field that controls
whether the returned `hosts` array includes devices that have not been online
recently. The Firewalla app surfaces this as the "Show past devices" toggle
(devices not seen online in the past 7 days).

```json
{
  "get": "0.0.0.0",
  "includeInactiveHosts": true
}
```

- `false` or omitted: the box returns only recently-active hosts
- `true`: the box returns the full host inventory including inactive devices
- the integration always sends `includeInactiveHosts: true` so configured
  device-tracker and watched-device hosts remain present even when inactive

### Inner encrypted envelope format (for reference)

From `wx3.d()`:

```java
String inner = "{\"message\":{\"mtype\":\"msg\",\"type\":\"jsondata\",\"msg\":\"\",\"from\":\"Android\""
    + ",\"obj\":" + serialized_obj
    + ",\"appInfo\":" + app_info_json
    + ",\"compressMode\":1}, \"mtype\":\"msg\"}";
```

This produces a nested JSON that gets encrypted and placed in the outer
`"message"` field. The integration uses the equivalent structure directly
(without the redundant outer `"message"` wrapper) by building the inner
envelope as a flat object.

### Alternative: Smali extraction via Apktool

For methods that JADX cannot decompile (R8 control-flow flattening), the
Smali assembly is always recoverable:

```bash
# Install Apktool
curl -L -o /tmp/apktool.jar https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.10.0.jar

# Decompile to Smali
java -jar /tmp/apktool.jar d com.firewalla.chancellor.apk -o /tmp/apktool_out

# Search for specific method
grep -rn ".method.*sendMessage\|.method.*encrypt\|.method.*buildPayload" /tmp/apktool_out/
```

Smali preserves all instructions including those lost to control-flow
flattening, at the cost of readability.

### Reproducibility notes

- JADX output is deterministic for a given APK and version — re-running
  produces the same decompiled source.
- The obfuscated class names (e.g., `wx3`, `y2`, `s73`, `fy3`) are assigned
  by ProGuard/R8 and will differ between app versions. Search by string
  constants (`"mtype"`, `"compressMode"`, `"com.rottiesoft.circle"`) to
  locate the equivalent classes in a newer APK.
- The APK used for this analysis was `com.firewalla.chancellor` version
  `1.69.1 (27)`. Later versions may change the message format.

## Appendix: Runtime data model (`xz2.java`)

The decompiled `xz2.java` class is the app's central runtime model. It
receives the init response JSON and parses every field with its expected
type. This class IS the schema that was previously reverse-engineered by
trial and error from packet captures.

### How to extract the current schema

To regenerate the field map for a newer APK version:

```bash
grep -oP '"[a-zA-Z]+"' /tmp/jadx_src/sources/defpackage/xz2.java | sort -u
```

This lists every JSON key string referenced in the model class. To get the
expected type for each key, search the `i()` method (the JSON parser):

```bash
grep -n 'optJSONObject\|optString\|optInt\|optLong\|optBoolean\|optJSONArray' \
  /tmp/jadx_src/sources/defpackage/xz2.java
```

### Confirmed runtime data fields (v1.69.1)

Every key below is parsed from the init response by `xz2.java` lines ~3190-3400.
The type column shows how the app reads the field.

| Key | APK type | Used by integration |
| --- | --- | --- |
| `id` | `optString` | No |
| `jwtToken` | `optString` | No |
| `mspData` | `optJSONObject` → sub-fields | No |
| `alarm` | `optJSONObject` (profiles.alarm) | No |
| `version` | `optString` | No |
| `jwt` | `optString` | No |
| `fwapcCountry` | `optJSONObject` | No |
| `distCodename` | `optString` | No |
| `sysMetrics` | `optJSONObject` | Yes |
| `totalMem` | `optInt` | Yes |
| `wlan` | `optJSONObject` → channels | No |
| `apController` | `optJSONObject` → version | No |
| `mspData.plan` | `optString` | No |
| `mspData.version` | `optString` | No |
| `mspData.channel` | `optString` | No |
| `mspData.mobileAccess` | `optJSONObject` | No |
| `mspData.targetlists` | `optJSONArray` | **Partial** — see below |
| `profiles` | `optJSONObject` (system alarm profiles) | No |
| `userConfig` | `optJSONObject` → user profiles | No |
| `activeAlarmCount` | `optInt` | **Planned** — Finding 26 |
| `archivedAlarmCount` | `optInt` | **Planned** — Finding 26 |
| `pendingAlarmCount` | `optInt` | **Planned** — Finding 26 |
| `newAlarms` | `optJSONArray` → `gx2` of `fx2` | **Planned** — Finding 26; **capped at 50** |
| `model` | `optString` | Yes |
| `mode` | `optString` | Yes |
| `localDomainSuffix` | `optString` | No |
| `dapInfo` | `optJSONObject` | Yes |
| `switchTopology` | `optJSONObject` | No |
| `switchInfo` | `optJSONObject` | No |
| `versionUpdate` | `optJSONObject` → time | No |
| `releaseType` | `optString` | Yes |
| `cpuid` | `optString` | Yes |
| `btMac` | `optString` | No |
| `publicIps` | `optJSONObject` | Yes |
| `longVersion` | `optString` | Yes |
| `updateTime` | `optLong` | No |
| `networkProfiles` | `optJSONObject` | Yes |
| `nicStates` | `optJSONObject` | No |
| `hosts` | `optJSONArray` | Yes |
| `tags` | `optJSONObject` | Yes |
| `userTags` | `optJSONObject` | Yes |
| `deviceTags` | `optJSONObject` | Yes |
| `wgPeers` | `optJSONArray` | Yes |
| `extension` | `optJSONObject` (family) | No |
| `guardianBiz` | `optJSONObject` | No |
| `ddnsToken` | `optString` | No |
| `monthlyDataUsageOnWans` | `optJSONObject` | Yes |
| `internetSpeedtestResults` | `optJSONObject` | Yes |

### Target list data model

Target lists are a complex subsystem in the Firewalla runtime. They are the
primary mechanism for grouping devices, networks, and categories so rules can
reference them by ID.

#### Where target lists live

Target list metadata comes from **`mspData.targetlists`** in the init
response — not from the rule inventory directly. The `mspData` block is a
cloud MSP subscription data structure that includes:

- `plan` — subscription plan identifier
- `features` — feature flag object
- `targetlists` — array of target list item objects
- `mobileAccess` — mobile access configuration
- `channel` — software update channel
- `version` — MSP data version

The `xz2.java` init parser reads this at line ~3235:

```java
JSONObject optJSONObject16 = jSONObject2.optJSONObject("mspData");
if (optJSONObject16 != null) {
    JSONArray optJSONArray = optJSONObject16.optJSONArray("targetlists");
    // each element parsed into a08 (TargetListItem)
}
```

#### Target list ID prefixes

| Prefix | Meaning | Source |
| --- | --- | --- |
| `TLX-fw-*` | Firewalla-managed (predefined) | `gc3.r1` set |
| `TLX-rt-*` | Route target list | `gc3.r1` set |
| `TLX-dt-*` | Disturb (time/pause) target list | `gc3.r1` set |
| `TL-*` | User-created target list | UUID-based |

#### Target list item structure (class `a08`)

Each target list item has these fields from its `toString()`:

```
TargetListItem(
  id              // e.g. "TLX-fw-xxx" or "TL-<uuid>"
  type            // "category", "mac", "network", "TAG"
  name            // display name / friendly name
  scope           // scope identifier
  owner           // owner ID (if applicable)
  category        // category name
  beta            // whether this is a beta feature
  disabled        // whether the list is disabled
  notes           // description text
  count           // member count (devices, IPs, etc.)
  boxMinVersion   // minimum box firmware version
  models          // supported device models
  actions         // allowed action identifiers
  dnsmasqOnly     // whether DNS-only
  lastUpdated     // epoch seconds
  parent          // parent list ID (for hierarchy)
  access          // access level
  rules           // array of rule references (b08 objects)
)
```

#### Rule reference structure (class `b08`)

Each rule reference within a target list contains:

```
b08(
  id       // rule ID (pid)
  disabled // whether the rule is disabled in this context
  type     // rule type
  schedule // schedule reference (cd0)
  scope    // scope
)
```

#### How rules reference target lists

Rules reference target lists in two ways:

1. **`target` field** — The rule's target begins with a target list prefix
   (`TLX-fw-`, `TL-`, etc.) or is a raw category/type string.

2. **`targetList` field** — The rule value JSON contains a `targetList` key:
   - `"targetList": "1"` — boolean shorthand for category-based rules
   - `"targetList": <json object>` — full target specification for
     rules that contain embedded target definitions rather than references

#### How the app resolves friendly names

The app displays target list friendly names by:
1. Loading `mspData.targetlists` from the init response into `a08` objects
2. Looking up each rule's target prefix in the `a08` list by `id`
3. Falling back to the raw ID if no matching target list is found

#### Why our integration has limited target list data

Our integration builds target list references by scanning rule `target`
fields for the `TL-` prefix (`_build_target_list_references` in
`helpers/runtime_inventory.py`). This gives us the rule-to-target-list
relationship, but we **never request or parse `mspData.targetlists`** from
the init response.

This means we can see which rules reference which target lists, but we
cannot resolve the friendly names, types, member counts, or any of the
metadata that the app shows. The raw IDs (like `TLX-fw-block-torrent`)
are opaque without the `mspData.targetlists` lookup table.

#### How to fix this

To get full target list metadata, the init request would need an
additional `dapOp` or equivalent operation to retrieve the `mspData`
block. Alternatively, since `mspData` is part of the existing init
response (it's embedded in the massive `dapInfo` / `fwapcOps` response),
the integration may already be receiving it but discarding it because
our parser doesn't extract `mspData` from the init payload.

Once available, the target list metadata can be stored as a lookup:
`{id: "TLX-fw-xxx" → {name: "Torrents", type: "category", count: 5}}`,
which would let all rule-target-list references resolve to display names.
