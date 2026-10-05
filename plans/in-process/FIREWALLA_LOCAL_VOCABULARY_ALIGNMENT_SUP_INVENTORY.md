# Vocabulary Alignment — Supporting Inventory

**Parent plan:** `FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_IN-PROCESS.md`
**Purpose:** the audit behind the plan, as an exhaustive work list. Phase 1.4 publishes
it; Phases 2–4 consume it; Phase 4.4 proves it empty.

Measured on `feature/flow-reporting` at 728 passing tests. Every count here is from
the tree, not from memory — the point of the note is that "done" is checkable.

---

## 1. The register rule, applied

| Surface | Register | Word | Where it lives |
| --- | --- | --- | --- |
| Service field names | machine | `host` | `SERVICE_FIELD_*` in `const.py`, `.schema` keys in `services.py` |
| Enum values | machine | `host` | `vol.In(...)` tuples, `RULE_TARGET_TYPE_*`, `FirewallaNetworkKind` |
| `target.kind` | machine | `host` | `FirewallaReportTarget(kind=...)` call sites |
| `include` values | machine | `host` | `_normalize_report_include(allowed=...)` |
| Entity attribute keys | machine | `host` | `ATTR_*` values in `const.py` |
| Tool parameters | machine | `host` | `llm_tools_*.py` schemas |
| Service `name:` / `description:` | human | `device` | `services.yaml`, `translations/en.json` |
| Tool descriptions | human | `device` | tool `description` strings |
| Documentation prose | human | `device` | `docs/*.md`, `README.md` |

The boundary that makes this checkable: **a value in an enum or a key in a payload is
machine; a sentence explaining it is human.**

---

## 2. Selector vocabulary by service — the Phase 3 work list

34 services. Classified by how they take a scope.

### 2a. Typed `host_*` pairs — 11 services (already on the rule)

| Service | Device selector |
| --- | --- |
| `delete_host` | `host_mac` |
| `set_host_device_type` | `host_id` / `host_mac` / `host_name` |
| `set_host_dhcp_reservation` | `host_id` / `host_mac` / `host_name` |
| `set_host_dns_hostname` | `host_id` / `host_mac` / `host_name` |
| `set_host_membership` | `host_id` / `host_mac` / `host_name` |
| `set_host_name` | `host_id` / `host_mac` / `host_name` |
| `set_host_notify_when_next_offline` | `host_id` / `host_mac` / `host_name` |
| `set_host_notify_when_next_online` | `host_id` / `host_mac` / `host_name` |
| `wake_host` | `host_id` / `host_mac` / `host_name` |
| `get_hosts` | `host_name` / `host_mac` (filters, not identification) |
| `mute_alarm` | — (uses `scope_kind`/`scope_target` for its alarm scope; see 2c) |

### 2b. `scope_kind` + free-text `scope_target` — 5 services, **3 enums** (the outliers)

| Service | `scope_kind` enum | Note |
| --- | --- | --- |
| `get_flow_report` | `device` \| `group` \| `user` | unreleased |
| `get_time_usage_report` | `device` \| `group` \| `user` | **released in 2.5.0-beta.1** — the enum is changeable only because no shims are in scope |
| `create_rule` | `device` \| `network` \| `all` | different enum, same field name |
| `mute_alarm` / `unmute_alarm` | `device` \| `group` \| `user` \| `network` \| `all` | via the shared `_ALARM_SCOPE_SCHEMA_FIELDS`; a **superset** of the other two |

**Five services, three enums under one name.** One is a superset of another, so a
caller cannot even infer the vocabulary from the union — `device` means "an
endpoint" in two of them and "a scope kind that also admits `all`" in the third.
This is Q4's collision and the reason the recommendation is to delete `scope_kind`
rather than unify it.

**Two constants publish the same field name.** `get_time_usage_report` declares its
scope selector as `SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND`, whose **value** is
`"scope_kind"` — identical on the wire and in the UI to `SERVICE_FIELD_SCOPE_KIND`.
Found by the guard in Phase 1, not by reading: a scan keyed on constant name reports
this field as absent, which is precisely how a guard comes to pass while the value it
exists to find is present. **The guard therefore matches on the published value.**
It is also a finding in its own right — two names for one field, with no reason
recorded — and Phase 3 collapses them.

Note `get_flow_report` and `get_time_usage_report` cannot distinguish a group from a
user that share a name — the defect the typed pairs fix.

### 2c. `target_type` + `target_value` — **three treatments** under one name (Q5)

| Service | Declaration | Meaning |
| --- | --- | --- |
| `create_rule` | `vol.In(("dns", "ip", "mac"))` | what the **rule** matches on |
| `get_rules` | **`cv.string` — unvalidated** | the same concept, as a filter, accepting anything |
| `mute_alarm` | `vol.In(("alarm_type", "domain", "ip"))` | what **alarm** to silence |

The `get_rules` row is the worse of the three: the same field name is a **validated
enum** in one service and an **unvalidated free string** in another, so a caller
typo silently filters to nothing rather than failing. Any unification must decide
whether `get_rules` should validate, and against which vocabulary — a wrong value
there today produces an empty result indistinguishable from "no such rules".

`mute_alarm` carries **both** collisions at once: `target_type`/`target_value` for
the remote entity *and* `scope_kind`/`scope_target` for the alarm scope. It is the
single service that most needs Phase 3.

### 2d. Group and user selectors — two vocabularies

| Service | Fields | Vocab |
| --- | --- | --- |
| `set_host_membership` | `group_name` / `group_id` / `user_name` / `user_id` / `clear` | typed, 5 fields |
| reports | `scope_kind: group\|user` + `scope_target` | free-text |

### 2e. Rule selectors — two names for one thing (Phase 3.4)

| Service | Field |
| --- | --- |
| `pause_rule`, `resume_rule` | `rule_target` (free-text, accepts a name) |
| `delete_rule` | `rule_id` (typed) |
| `get_rules` | no selector (filters only) |

### 2f. Already consistent — no change

| Scope | Fields | Services |
| --- | --- | --- |
| network | `network_uuid` / `network_name` | `get_network_segment_report`, `get_network_segment_usage`, `set_host_dhcp_reservation` |
| WAN | `wan_uuid` / `wan_name` | 5 services (speed tests, quality, WAN usage, WAN events, run test) |
| config entry | `config_entry_id` / `config_entry_name` | all 34, injected by the tool base class |
| alarm | `alarm_id`, `exception_id` | `archive_alarms`, `delete_alarms`, `unmute_alarm` |
| SSID | `ssid_profile_id` | `set_ssid_paused` |

### 2g. Generic names worth reviewing alongside (not in the original nine questions)

| Field | Services | Actual values | Concern |
| --- | --- | --- | --- |
| `kind` | `get_hosts` | `mac_host` \| `pseudo_host` | the single most generic field name in the surface; the values are a host-inventory distinction a caller cannot guess from the name |
| `mode` | `archive_alarms`, `delete_alarms`, `set_host_dhcp_reservation` | `this` \| `all_active` — and `this` \| `all_active` \| `all_archived` on delete | three services, **two** vocabulary sets, and the two alarm services are near-duplicates that differ only by one value |
| `detail` | 5 report services | boolean on `get_alarms`, enum on the others | one name, two types |

These are recorded because they are the same *class* of finding — a name that does
not tell a caller what it holds — even though they are outside the register question.
Phase 3 decides whether any is in scope; if not, they are recorded, not fixed.

> `mode` is the closest to a defect rather than a naming concern: `archive_alarms`
> and `delete_alarms` take the same selector with different allowed values, so a
> caller reading one and passing it to the other gets a validation error for a value
> it was told was valid. Worth a Phase 3 step even if the rename is declined.

---

## 3. Response `target.kind` — the Phase 2 work list

Every emitter found in `services.py`:

| Emitter | Value | Canonical | Change |
| --- | --- | --- | --- |
| host services (5 call sites) | `"host"` | `host` | **none — already the rule** |
| `_serialize_network_segment_usage` | `"network_segment"` | `network` + `network_kind` | rename |
| `_serialize_network_segment_report` | `network.kind.value` → `lan`/`vlan`/`vpn`/`wan` | `network` + `network_kind` | rename + carry sub-kind |
| WAN usage | `"wan"` | `network` + `network_kind: "wan"` | per Q3 |
| `get_time_usage_report` | `target.scope_kind` → `device`/`group`/`user` | `host`/`group`/`user` | rename `device` |
| `get_flow_report` | `target.scope_kind` → `device`/`group`/`user` | `host`/`group`/`user` | rename `device` |

**Seven emitters, five values, two of which name the same thing.** `network_segment`
and `vlan` are both "a network"; `device` and `host` are both "an endpoint".

> **Information-loss check (Phase 2.3).** Collapsing `lan`/`vlan`/`vpn`/`wan` into
> `network` loses a real distinction, so it **must** be carried on a `network_kind`
> field. A `get_network_config` caller that today reads `kind: "vlan"` must still be
> able to tell a VLAN from a VPN after the change. Verify per service; a collapse
> that drops information is a regression dressed as consistency.

---

## 4. Entity attribute keys — the Phase 4 work list

`ATTR_*` values in `const.py` whose value uses the wrong register's word:

| Constant | Current value | Proposed | Consumer |
| --- | --- | --- | --- |
| `ATTR_SYSTEM_DEVICES_ONLINE` | `devices_online` | `hosts_online` | system-status binary sensor |
| `ATTR_SYSTEM_DEVICES_OFFLINE` | `devices_offline` | `hosts_offline` | same |
| `ATTR_SYSTEM_DEVICES_TOTAL` | `devices_total` | `hosts_total` | same |
| `ATTR_SYSTEM_VPN_DEVICES_ONLINE` | `vpn_devices_online` | `vpn_hosts_online` | same |
| `ATTR_SYSTEM_VPN_DEVICES_OFFLINE` | `vpn_devices_offline` | `vpn_hosts_offline` | same |
| `ATTR_SYSTEM_VPN_DEVICES_TOTAL` | `vpn_devices_total` | `vpn_hosts_total` | same |
| `ATTR_NETWORK_DEVICE_COUNT` | `device_count` | `host_count` | network binary sensor |
| `ATTR_WATCHED_USER_ASSOCIATED_DEVICES` | `associated_devices` | `associated_hosts` | watched-user sensor |
| `ATTR_WATCHED_USER_ASSOCIATED_DEVICE_COUNT` | `associated_device_count` | `associated_host_count` | same |
| `ATTR_WATCHED_USER_ASSOCIATED_DEVICE_GROUP` | `associated_device_group` | `associated_host_group` | same |
| `ATTR_WATCHED_DEVICE_DEVICE_GROUP` | `device_group` | `host_group` | watched-device binary sensor |
| `ATTR_ALARM_DEVICE_NAME` | `device_name` | `host_name` | alarm surfaces |

**12 values.** The constant *names* (`ATTR_WATCHED_DEVICE_*`) are Python identifiers
and are separate from the values — the values are what a user and an automation see.
Renaming the constants too is optional and should be decided in Phase 4.1; renaming
the values is the contract change.

> **Zeroing check (Phase 4.1).** A rename with one missed consumer produces a silently
> absent attribute, not an error. The consumers are `binary_sensor.py`, `sensor.py`,
> the diagnostics dump, the tests, and the `USER_GUIDE.md` *Rich data lives in entity
> attributes* section. Grep each value, not each constant name.

---

## 5. Requested and then discarded — the Phase 4.2 class

The one confirmed instance, found while fixing the WAN event filters:

| Filter requested | In the supported set? | Effect |
| --- | --- | --- |
| `state/dualwan_state` | yes | returned |
| `state/wan_state` | yes | returned |
| `state/overall_wan_state` | yes | returned |
| `state/ethernet_state` | **no** | requested, discarded |
| `state/ap_ethernet_state` | **no** | requested, discarded |
| `state/ap_ethernet_speed_change` | **no** | requested, discarded |
| `action/wpa_connection` | **no** | requested, discarded |
| `action/system_reboot` | yes | returned |
| `action/ping_RTT`, `ping_lossrate` | yes | returned |
| `action/dns_RTT`, `dns_lossrate` | yes | returned |
| `action/http_RTT`, `http_lossrate` | yes | returned |
| `state/dns` | yes (opt-in) | returned only with `include_dns` |

**4 of 14 filters return data the normalizer drops.** The box ignores an unknown
filter silently, so the failure mode is indistinguishable from a quiet period — the
same shape as the `ranking_families_unavailable` problem fixed in the flow work.

**Phase 4.2 must resolve each from a capture, not a guess**, then audit for the same
class elsewhere: any other place a value is accepted and ignored, or requested and
discarded. Candidate search: every `vol.In` tuple against the set of values the
corresponding handler branches on.

These four are deliberately **absent from the guard's work list** in §7. Whether a
filter is discarded depends on which families the box returns, which is protocol
knowledge, not a property of the source text — so the guard cannot see it and listing
it there would be a claim the test does not make. The guard's list is exactly what the
guard can prove.

---

## 6. Churn — what the phases cost

Re-measured in Phase 1.4 against the tree. **The earlier version of this table was
not reproducible**, so it has been replaced by numbers that are, with the command
that produces each. A cost estimate nobody can re-derive is not a cost estimate.

```bash
# the Phase 2/3 surface: values, field names, and their constants
p='network_segment|scope_kind|target_type|rule_target|target_kind'
grep -rlE "$p" --include='*.py' tests/     # files
grep -rhE "$p" --include='*.py' tests/     # occurrences
```

| Surface | Count | How measured | Phases |
| --- | --- | --- | --- |
| Services with a selector to migrate | **9 distinct**, across 11 selector assignments — 5 `scope_kind`, 3 `target_type`, 3 rule selectors; `create_rule` and `mute_alarm` each carry two | `services.py` schema scan | 3 |
| Response `target.kind` emitters | **6** | the guard's target-kind set | 2 |
| Response emitters, all kinds | 7 | §3 | 2 |
| Entity attribute values | **12** | the guard's constant set | 4 |
| WAN filters to resolve | 4 | §5 | 4 |
| Test files embedding a changing value | **17** | the grep above, `-l` | 2, 3, 4 |
| Lines embedding one | **207** | the grep above, `-h \| wc -l` | 2, 3, 4 |
| Of those, top-level `assert` lines | **7** | `grep -rhE "assert.*($p)"` | 2, 3, 4 |
| Documents naming a governed field | **4** under `docs/` | `grep -rlE "$p" --include='*.md' docs/` | 4 |
| Documents stating the rule instead | **2** — `ARCHITECTURE.md`, `DEVELOPMENT_STANDARDS.md` | by inspection; neither names a governed field, by design | 1 |

**The 7-versus-207 gap is the important number.** Only seven of the 207 references
sit in an `assert`. The rest are inside mock payloads, expected-dict literals, and
call arguments — so a rename that stops matching changes *what the test sets up and
compares* without touching a single assertion. The suite can go green on a
half-migrated value because the fixture and the expectation were renamed together
while the production code was not. That is why Phase 4.5's absolute guard matters
more than the per-phase edits: nothing else in the chain notices.

Test files by occurrence count:

| File | refs | File | refs |
| --- | --- | --- | --- |
| `test_services.py` | 57 | `test_rule_manager.py` | 11 |
| `test_models.py` | 21 | `test_runtime_inventory.py` | 10 |
| `test_config_flow.py` | 21 | `test_llm_tools.py` | 4 |
| `test_vocabulary.py` | 18 | `test_alarm_manager.py` | 4 |
| `test_flow_manager.py` | 17 | `test_llm_contract.py` | 3 |
| `test_switch.py` | 16 | `test_init.py` | 3 |
| `test_client.py` | 15 | `test_diagnostics.py` | 3 |
| `test_llm_control.py` | 2 | `test_llm_errors.py` | 1 |
| `test_flow_report.py` | 1 | | |

`test_vocabulary.py`'s 18 are the guard's own work list and reasons — Phase 4
shrinks them as it deletes entries, so they are churn this initiative creates rather
than churn it pays down. The pre-existing figure is **189 across 16 files**.

Entity-attribute values add **5** more files: `test_binary_sensor.py`,
`test_device_tracker.py`, `test_sensor.py`, `test_services.py`, `test_vocabulary.py`.

> **The two-pin trap.** `test_init.py` pins the registered service set in two
> separate places, and the flow-reporting initiative was caught by that. Any change
> to a service or field must satisfy both, and a rename that updates one is a
> half-done change that still passes.

---

## 7. The guard's work list — what Phase 1.5 must cover

**Status: added in Phase 1.5**, in `tests/components/firewalla_local/test_vocabulary.py`.
The table below is the guard's actual output, verified against the tree rather than
predicted. **23 entries**, grouped by the phase that removes each.

| Group | Entries | Removed in |
| --- | --- | --- |
| Response kinds not canonical | **6** | 2 |
| Guarded machine enums | **5** | 3 |
| Entity attribute values | **12** | 4 |

Per the plan, the list in the test is authoritative and must equal these 23 keys
exactly. Verbatim:

```
services.py:kind='network_segment'      services.py:kind='wan'
services.py:kind=network.kind.value     services.py:kind=target.scope_kind
services.py:kind=target_kind            services.py:kind=view.target.scope_kind

CREATE_RULE_SCHEMA.SERVICE_FIELD_SCOPE_KIND
GET_FLOW_REPORT_SCHEMA.SERVICE_FIELD_SCOPE_KIND
GET_RULES_SCHEMA.SERVICE_FIELD_TARGET_TYPE
GET_TIME_USAGE_REPORT_SCHEMA.SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND
_ALARM_SCOPE_SCHEMA_FIELDS.SERVICE_FIELD_SCOPE_KIND

ATTR_ALARM_DEVICE_NAME                    ATTR_NETWORK_DEVICE_COUNT
ATTR_SYSTEM_DEVICES_OFFLINE               ATTR_SYSTEM_DEVICES_ONLINE
ATTR_SYSTEM_DEVICES_TOTAL                 ATTR_SYSTEM_VPN_DEVICES_OFFLINE
ATTR_SYSTEM_VPN_DEVICES_ONLINE            ATTR_SYSTEM_VPN_DEVICES_TOTAL
ATTR_WATCHED_DEVICE_DEVICE_GROUP          ATTR_WATCHED_USER_ASSOCIATED_DEVICES
ATTR_WATCHED_USER_ASSOCIATED_DEVICE_COUNT
ATTR_WATCHED_USER_ASSOCIATED_DEVICE_GROUP
```

The four `scope_kind` entries are four **schema instances** covering five services
(the alarm pair shares one schema) and three distinct enums, which is why §2b
and §7 count differently and neither is wrong.

**An allowlist entry that no phase removes is a planning failure, not an approved
exemption.** Phase 4.4 deletes the list outright; if it cannot be deleted, the
initiative is not finished.

### What the guard checks, and what it deliberately does not

Checks:

1. **Published target kinds.** Every `FirewallaReportTarget(kind=...)` in `services.py`
   is canonical. A literal is compared against the canonical set; a pass-through such
   as `kind=network.kind.value` is reported by its source text, because the shape that
   hid the `device` violation is exactly the shape a literal-only check cannot see.
2. **Guarded machine enums.** A field whose published value is `scope_kind` or
   `target_type` must be a `vol.In` **and** its values must not use the human word.
   Matching is on the published value, not the constant name, because two constants
   share the name `scope_kind`.
3. **Guarded constant values.** `SERVICE_FIELD_*` and `ATTR_*` values must not name a
   host with the human word, tokenised rather than substring-matched so
   `host_device_type` — where `device` modifies `type` — is not a false positive.

Does **not** check, and why:

- **The `target_type` name collision.** `mute_alarm` carries a different vocabulary
  under the same name, but neither vocabulary contains the human word, so it is a
  collision rather than a register violation. Detecting "one name, two vocabularies"
  needs the semantics of each enum, not its spelling; it is tracked in §2c and
  resolved in Phase 3.2.
- **The `mode` near-duplicate.** Same reason.
- **Whether a value is validated at all, outside the guarded fields.** `get_rules`'
  unvalidated `target_type` is caught because that field name is guarded; an
  unvalidated field elsewhere is not. Phase 4.2 audits that class.
- **Documentation prose.** The guard reads code. Phase 4.3 sweeps the documents, and
  one test does assert the canonical set appears in `ARCHITECTURE.md`.

### Two failure directions, both proven

| Injected | Result |
| --- | --- |
| A new violation (a temporary `ATTR_*` value using the human word) | **Failed**: "new violations of the register boundary" |
| A violation fixed without removing its work-list entry | **Failed**: "these are fixed but still listed as violations" |

The second is the property that makes the list a work list rather than a suppression
list, and it was observed during development rather than argued for.

---

## 8. What Phase 2 surfaced that this note did not inventory

Phase 2 was scoped to the seven `services.py` emitters in §3. Executing it showed
that scope was drawn too tightly in two places, and that the guard's coverage is
narrower than the rule it states. All three are recorded here rather than fixed
silently, because each changes something a phase already declared settled.

### 8a. A second published `target.kind` vocabulary *(needs an owner decision)*

`llm_tools_control.py` publishes the same `{"kind", "id", "name"}` target object to
the LLM, with a vocabulary §3 never saw:

| File | Published kind | Canonical? |
| --- | --- | --- |
| `llm_tools_control.py` ×3 | `rule` | no |
| `llm_tools_control.py` ×2 | `alarm` | no |
| `llm_tools_control.py` ×2 | `silence` | no |
| `llm_tools_control.py` ×1 | `ssid` | no |
| `llm_tools_control.py` ×1 | `wan` | **no — and now contradicts `services.py`** |

The `wan` is the sharp one. Phase 2 retargeted every report to
`kind: "network"` + `network_kind: "wan"`, and the speed-test control tool still
publishes `kind: "wan"` for the same concept. The two surfaces disagree, which is
the exact defect the initiative exists to remove — introduced *by* the fix, because
the inventory only looked at one file.

The guard never saw any of this: it scans `services.py` only. **That blind spot was
flagged as a risk when Phase 1 shipped, and it was correct.**

This needs a decision because it changes the canonical set, which Phase 1 fixed:

- **Option A (recommended).** Widen the set to every published target kind —
  `host`, `group`, `user`, `network`, `rule`, `alarm`, `silence`, `ssid` — and scan
  the whole package. One vocabulary for "what can a target name", with the report
  scopes a subset of it. `wan` collapses into `network` + `network_kind` as already
  done. Cost: one constant, one guard set, one `ARCHITECTURE.md` sentence, and the
  control-tool `wan`.
- **Option B.** Declare two vocabularies — report scopes and action targets — and
  document the boundary. Cheaper, but leaves two `kind` vocabularies under one name,
  which is §2c's collision problem in a new place.

Recommendation is A: the object shape is identical, the reader is the same reader,
and B re-creates the ambiguity the whole initiative is about.

### 8b. Payload keys using the human word *(Phase 4)*

Flow records and their member rows publish `device_id` and `device_ip` as keys:

| Site | Key |
| --- | --- |
| `services.py` (member rows, record payload) | `device_id`, `device_ip` |
| `models.py` | `device_id`, `device_ip` |
| `utils/flow.py`, `utils/flow_report.py` | the same, as dataclass fields |

These are keys inside a payload, which `ARCHITECTURE.md` explicitly calls machine.
They are violations of the rule as written. They are **not** in the guard, because
8c below. Phase 4 owns them, alongside the twelve `ATTR_*` values.

### 8c. The guard is narrower than the rule *(Phase 4.5)*

`ARCHITECTURE.md` says "a key inside a payload is machine". The guard checks three
things: `target.kind` expressions, two named enum fields, and the values of
`SERVICE_FIELD_*` / `ATTR_*` / `FLOW_REPORT_*` constants.

So it does **not** see:

- any dict key written literally in `services.py`, `models.py`, or a helper — which
  is how 8b survives
- the enum values inside `llm_tools_read.py` / `llm_tools_control.py` schemas, which
  duplicate the service schemas — which is how 8a survives

Both were found by reading, not by the test. **Phase 4.5's "absolute guard" must
widen the scan to the whole package and to literal payload keys**, or the rule stays
partly unenforced and the allowlist reaching empty will mean less than it appears to.
Recorded now so Phase 4.5 is specified by evidence rather than intent.

### 8d. An answered question with no owner

Q7 (does `device_detail` become `host_detail`) was answered "yes" in the plan, and no
phase step owned the change. It would have been silently skipped. It was done in
Phase 2 — but the general point is worth keeping: **answering a question is not
scheduling the work**, and this note is the only place that maps one to the other.
