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

- reuse of a working Home Assistant config entry for live local protocol access
- direct runtime pulls for current-value comparison without re-pairing
- runtime inventory capture before and after user actions
- remote `tcpdump` capture on the Firewalla box
- decryption and inspection of local port `8833` traffic
- comparison of mutation payloads across rule families

This workflow does not cover first-time pairing design in detail. Pairing is
already documented elsewhere and treated here as a prerequisite.

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
