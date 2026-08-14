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

- `.tmp/capture_runtime_inventory.py`

This script:

- loads the first `firewalla_local` config entry from Home Assistant storage
- constructs `FirewallaApiClient`
- requests the raw init payload from the local runtime
- normalizes that payload into the repository's current inventory report shape
- writes the structured result to a JSON artifact file

### Packet capture analysis helper

- `utils/analyze_capture.py`

This script:

- loads the symmetric key from Home Assistant storage
- reads a `.pcap` file captured from port `8833`
- reassembles HTTP streams
- decrypts Firewalla message payloads using the integration crypto helpers
- prints the decoded request or response contents for inspection

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

## Standard workflow

Use this sequence for any new rule-family investigation.

### 1. Confirm live credentials

Inspect the Home Assistant config entry and confirm:

- host value
- `gid`
- presence of `aid`, `eid`, and `symmetric_key`

Reason:

- the workflow depends on local runtime access without repeating QR pairing

### 2. Capture baseline inventory

Run `.tmp/capture_runtime_inventory.py` and write a baseline artifact.

Purpose:

- establish the exact pre-action rule state
- identify any existing rule IDs that may be updated rather than created

### 3. Inspect baseline for the target scope

Before capturing packets, inspect the inventory for:

- the target group or host
- any existing rules whose `applies_to`, `target_name`, or `tag_refs` overlap
  the target
- whether the current state is absent, enabled, or disabled

Reason:

- Firewalla does not always use the same mutation strategy for every rule
  family

### 4. Arm remote `tcpdump`

Start `tcpdump` on the Firewalla box over SSH.

Current pattern:

```bash
ssh -i .tmp/firewalla_temp_ssh_key \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  pi@fire.walla \
  "sudo tcpdump -i any -s 0 -w /tmp/<capture_name>.pcap port 8833"
```

Reason:

- local runtime mutations occur over encrypted HTTP on port `8833`

### 5. Perform one user action only

Have the user perform exactly one action in the Firewalla app, for example:

- create a timed block
- turn a persistent block off
- turn internet block on
- re-enable a disabled internet block rule

Reason:

- a single action makes the inventory delta and decrypted packet trace easier to
  correlate

### 6. Stop capture and copy the pcap locally

Stop the remote `tcpdump` and copy the pcap to `.tmp/` with `scp`.

### 7. Capture post-action inventory

Run `.tmp/capture_runtime_inventory.py` again and write a new artifact.

Purpose:

- identify whether a rule was created, deleted, or updated in place

### 8. Decrypt the packet capture

Run `utils/analyze_capture.py <pcap_path>`.

If the capture is noisy, scope the report to the pairing phone with
`utils/analyze_capture.py <pcap_path> --client-ip <phone_ip>`.

If you want to suppress live-stream `GET` and `text/event-stream` traffic and
focus only on the pairing `POST` flow, add `--pairing-only`.

Inspect the decoded request for:

- outer message type such as `cmd` or `init`
- inner `item` field such as `policy:create`, `policy:delete`, or
  `policy:update`
- full `value` payload

### 9. Diff inventories

Compare pre-action and post-action inventories and identify:

- new rule IDs
- removed rule IDs
- rules updated in place
- changes to `enabled`, `dnsmasq_only`, `target`, `target_type`, and timing
  fields

### 10. Record the finding in this document

Every confirmed capture should update:

- the findings matrix
- the mutation-family notes
- the open questions list if new uncertainty appears

## Safety and repeatability rules

- capture one app action at a time
- preserve before and after inventory artifacts for every capture
- prefer the stored Home Assistant config entry over ad hoc credentials
- prefer published Firewalla contracts over ad hoc interpretation when both are
  available
- do not guess mutation semantics from UI labels alone
- do not assume every switchable rule family uses `create` and `delete`
- do not assume every disabled rule is deleted when turned off

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
| AP7 wireless SSID pause | read via `networkConfig.apc.profile.<uuid>.paused` | **unconfirmed** — three candidate write patterns rejected with code 500 | not applicable until write contract is confirmed | Example: pause/resume "Universe Guest" on VLAN 100 |

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

The write contract for the `paused` field on an SSID profile is unconfirmed.
All three candidate write patterns (set_apc, cmd_apc, set_networkconfig) were
rejected with code 500. The correct write command must be determined from a
packet capture of the Firewalla app toggling a wireless network.

Required capture:

- toggle a wireless network (enable → disable) in the Firewalla app
- capture the decrypted `set` or `cmd` message directed at the AP controller
- the target SSID profile UUID is `f185dc47-2730-48a8-844c-b57aa31af4ba`
  (Universe Guest, VLAN 100) for the reporter's setup

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
- the exact AP7 wireless SSID pause write command (all three alpha.7
  candidates rejected — requires a fresh packet capture; see §"Next capture
  targets" above)

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

**Write contract — unconfirmed:**

Three candidate write patterns were tested in alpha.7 (`set_apc`, `cmd_apc`,
`set_networkconfig`). All three were rejected by the Firewalla box with
protocol code 500. The correct write command remains unknown and requires
packet capture of the app-to-box traffic during a wireless toggle.

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
