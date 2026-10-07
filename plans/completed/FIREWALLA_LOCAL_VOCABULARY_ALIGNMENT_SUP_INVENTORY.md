# Vocabulary Alignment — Supporting Inventory

**Parent plan:** `FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_COMPLETED.md`
**Status:** closed 2026-10-06. The phases it fed are complete; §1–§8 are the audit as it
was taken, §9–§16 are the design record of what the measurements then changed.
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

1. **Published target kinds.** Every `FirewallaReportTarget(kind=...)` call and every
   target-object dict in **the whole package** must be canonical, where a target
   object is a payload dict carrying both a `kind` and an `id`. A literal is compared
   against the canonical set; a pass-through such as `kind=network.kind.value` is
   reported by its source text, because the shape that hid the `device` violation is
   exactly the shape a literal-only check cannot see. **Scanning one file was a real
   blind spot** — it hid five control-tool kinds including a `wan` that contradicted
   `services.py`; see §8a.
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

### 8a. A second published `target.kind` vocabulary — **RESOLVED**

`llm_tools_control.py` publishes the same `{"kind", "id", "name"}` target object to
the LLM, with a vocabulary §3 never saw:

| File | Published kind | Canonical? |
| --- | --- | --- |
| `llm_tools_control.py` ×5 | `rule` | was no — **now a constant** |
| `llm_tools_control.py` ×4 | `alarm` | was no — **now a constant** |
| `llm_tools_control.py` ×2 | `silence` | was no — **now a constant** |
| `llm_tools_control.py` ×1 | `ssid` | was no — **now a constant** |
| `llm_tools_control.py` ×1 | `wan` | was no and **contradicted `services.py`** — now `network` + `network_kind` |

Resolved by **Option A**: the canonical set widened to every published target kind,
and the guard now scans the whole package. The `wan` collapse into
`network` + `network_kind` removes the contradiction Phase 2 had just introduced —
which was created *by* the fix, because the inventory only looked at one file.

The guard's blind spot was real: it scanned `services.py` only. It is closed, and
proven closed by injecting `kind: "devices"` into `llm_tools_control.py`, which now
fails with `llm_tools_control.py:kind='devices'` where it previously passed.

**What the widened scan then found, and how each was judged.** Widening the scan to
the whole package surfaced four more sites, and only one was a real violation:

| Site | Value | Judgement |
| --- | --- | --- |
| `services.py` `users_section` item | `_MEMBERSHIP_KIND_USER` | **real violation** — an authored kind reached by an undeclared local constant. Now `TARGET_KIND_USER`. |
| `services.py` membership description | `group.kind` | relay — `FirewallaGroupRuntime.kind` is `Literal["group","user"]` |
| `services.py` `groups_section` items | `group.kind` | same relay |
| `services.py` `_serialize_report_target` | `target.kind` | relay — the serializer re-publishing what it was handed |
| `runtime_inventory.py` group record | `'user' if … else 'group'` | both branches canonical |

That distinction is now stated in the guard: it enforces where a kind is **written**
(literal, vocabulary constant, or vocabulary mapping) and accepts where one is
**read back** — a `.kind` attribute, or a conditional whose every branch is already
accepted. The structural test for a target object is stated rather than implied: a
payload dict carrying both a `kind` and an `id`.

### 8b. Payload keys using the human word *(Phase 4)* — **RESOLVED**

Flow records and their member rows published `device_id` and `device_ip` as keys:

| Site | Key |
| --- | --- |
| `services.py` (member rows, record payload) | `device_id`, `device_ip` |
| `models.py` | `device_id`, `device_ip` |
| `utils/flow.py`, `utils/flow_report.py` | the same, as dataclass fields |

These are keys inside a payload, which `ARCHITECTURE.md` explicitly calls machine.
They were violations of the rule as written. The **published** keys were renamed to
`host_*` in §15; the dataclass *field* names stayed, because they are internal.

The reasoning that deferred them — that a mirrored vendor record keeps the vendor's
names — is the part that did not survive measurement. See §15.

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

---

## 9. Phase 3.2 — measured, and the proposed standardisation

**Status: proposal, awaiting approval.** The findings below are measured against the
tree, not inferred. The plan's own §3.2 description was written from the earlier
audit and is **wrong in three places**, corrected here.

### 9a. The audit's three errors, corrected

The plan described "the `target_type` treatment that loses" and "the `mode`
near-duplicate" with the counts it had at planning time. Measuring each schema:

| Claim in §3.2 | Measured |
| --- | --- |
| "`target_type` — **three** treatments" | Three *services*, but only **two vocabularies**, and two of the three are the **same** one (see 9b) |
| "`detail`'s two types (boolean on `get_alarms`, enum elsewhere)" | **Four** treatments: `summary\|records`, **boolean**, `summary\|full` ×2, `summary\|standard` |
| "`mode` near-duplicate" | Also collides with a third, unrelated `mode` (`set_host_dhcp_reservation`: `dynamic\|static`) |

The `detail` finding is the largest in the whole audit and the plan understated it by
half. Every count below comes from parsing each `*_SCHEMA` assignment.

### 9b. `target_type` is one vocabulary plus one genuine collision

| Service | Values | What it names | Validated |
| --- | --- | --- | --- |
| `create_rule` | `dns\|ip\|mac` | **how a new rule matches** — wire values | yes, a **subset** |
| `get_rules` | `cv.string` | filters on `rule.target_type` — **the same field** | **no** |
| `mute_alarm` | `alarm_type\|domain\|ip` | **what kind of thing to silence** | yes |

`create_rule` and `get_rules` are **not a collision**: they are the same concept —
the rule's matcher type — and `const.py` already defines six values for it
(`RULE_TARGET_TYPE_CATEGORY/DNS/IP/MAC/NETWORK/REMOTE_PORT`). Both depart from those
constants: `create_rule` validates 3 of the 6, `get_rules` validates none. And
`create_rule` is not merely narrower — **it cannot express `category`, `network` or
`remotePort` rules**, while `get_rules` can filter on them and the test fixtures carry
`category` rules (19 occurrences across 4 test files), so the narrower enum is already
out of step with the data the integration handles. The pair is one vocabulary with a
drift problem, not a naming problem. The rules side also mirrors the protocol record,
which is why it keeps the name: `FirewallaPolicyRule.target` / `.target_type` are wire
fields.

Only `mute_alarm` is a real collision — a different concept under the same name. And
its values are **our own**, not the wire's: `alarm_manager` translates `domain`→`dns`
and `alarm_type`→`alarmType`. So renaming them is free of protocol consequence.

### 9c. `scope_kind` has three more enums, and two `all` members

| Service | Values | Wire form (verified in `alarm_manager._get_scope_payload`) |
| --- | --- | --- |
| `create_rule` | `device\|network\|all` | MAC tuple / network |
| `mute_alarm` | `device\|group\|user\|network\|all` | `p.device.mac` / `p.tag.ids` / **`p.intf.id`** |

**`unmute_alarm` takes no scope** — checked, because an earlier version of this table
said it did. It identifies the silence by `exception_id` or `alarm_id`, and
`_ALARM_SCOPE_SCHEMA_FIELDS` has exactly one consumer. So the remaining scope work
touches **two** services, not three.

Verified: device scope is a **MAC**; group and user scopes are **tag ids**. The
network scope's `p.intf.id` is **verified as of 10c** — the reverse-engineering note
documents it as a network ID, and a captured flow record carries a UUID of the same
shape as `FirewallaNetwork.uuid`.

### 9d. Q8 — answered, and the answer is "leave it"

`RULE_TARGET_TYPE_MAC` describes **how a rule matches**; the host identity travels
separately in the rule's `scope` tuple (`create_rule` puts the MAC there, and
`FirewallaRuleTemplate.scope` is a tuple of MACs). So `mac` is a **matcher**, not an
identity, and the plan's condition ("if the handler presents it as an identity")
is not met. **It stays as the wire says** — which is exactly what the Q8 check was
for, so this is a resolved question rather than a deferred one.

### 9e. The organising principle

Two rules, and the second is what dissolves most of the work:

1. **One name carries one vocabulary.** A field name may not mean two different
   things across services.
2. **An enum member that restates the selection's arity is a smell.** `all` (in two
   enums here) and `this` (in two more) both say *"no selection"* or *"the one you
   named"* — which the **presence or absence of a selector already says**. Every
   `all` and every `this` in this integration is removable by making the selector
   optional or required, not by inventing a better word.

This is why renaming `this` is the wrong fix: the problem is not that the word is
poor, it is that the axis should not be an enum at all.

### 9f. The recommendation

**1. `target_type`/`target_value` — rules keep it, silences get their own name.**
Rules keep the pair because it mirrors the protocol record. `create_rule` and
`get_rules` both move to the `RULE_TARGET_TYPE_*` constants, with `create_rule`
gaining whatever it can actually create and `get_rules` gaining validation — a typo
today returns an empty list indistinguishable from "no such rules", the same defect
class as 4.2. `mute_alarm`/`unmute_alarm` rename to **`match_type` / `match_value`**:
it names the operation (*which alarms to match and silence*) and stops reusing
`target`, which everywhere else means what a rule blocks.

**2. `mode` on the alarm services — split into `alarm_id` XOR `alarm_set`.**
`alarm_id` names one alarm; `alarm_set` (`active` | `archived`) names a population.
Exactly one, enforced by the same rule the scopes use. `this` disappears because
naming an alarm *is* selecting one, and today's `mode: "this"` with no `alarm_id` is a
runtime error that becomes unrepresentable. `set_host_dhcp_reservation`'s `mode` is
untouched: it is a different concept, and it stops colliding the moment the alarm
axis is gone. Its values already match the `ip_assignment.mode` it writes.

**3. `scope_kind` — typed pairs, `all` by omission, on the two remaining services.**
- `create_rule`: `host_mac` | `network_uuid`/`network_name` | omit → all
- `mute_alarm`/`unmute_alarm`: the host/group/user pairs, plus a network pair

  **gated on 9c**: the network form is recommended but must not be named until
  `p.intf.id` is verified. Host, group and user can proceed without it.

**4. `detail` — one vocabulary, `summary|full`.**
Four treatments collapse to two values. `full` is already used twice and reads
better than `standard`; `get_alarms`' boolean becomes the enum and
`get_time_usage_report`'s `standard` becomes `full`. **The one real cost:**
`get_flow_report`'s `records` becomes `full`, losing a word that currently carries
the "includes the raw records" cue — mitigated because the value alone never carried
it (the tool description does), but it is the only place this change subtracts
information, and it is called out rather than buried.

**5. The conflict keys — six keys with three meanings become two.**
`host_selector_conflict`, `network_selector_conflict`,
`speed_test_wan_selector_conflict`, `scope_selector_conflict`,
`pause_rule_timing_conflict` and `membership_target_conflict` all say "you supplied
the wrong number of these fields", in three different wordings. They become
`selector_conflict` and `selector_required`, carrying the accepted field list as a
placeholder, so each service gets an accurate message with no key of its own. The
helper needs `required` and *at-most-one* modes, because `pause_rule` accepts
neither field and `_resolve_requested_host` already has a `required` flag.
`membership_target_conflict` keeps one bespoke rule: its `clear` axis is separate
from the four membership fields.

**6. `get_hosts`' `kind` — accepted as-is.** `mac_host`/`pseudo_host` is a machine
vocabulary naming a host's own classification, contains no human word, and mirrors the
protocol's distinction. Nothing to change, recorded so it is a decision rather than an
omission. (Note the field lives on `get_hosts`, whose schema is named
`GET_HOST_NAME_MAPPING_SCHEMA` — a schema name that no longer describes it, since the
service returns hosts with their identity, not a name mapping. Worth a rename for the
same reason 2.2 renamed `network_segment`, but it is an internal name and not
user-visible, so it is noted rather than sequenced.)

### 9g. Rejected alternatives

| Alternative | Why not |
| --- | --- |
| Unify the three `scope_kind` enums into one superset | Keeps a field whose vocabulary a caller cannot infer, and keeps `device` in the machine register. The plan already rejected this for Q4 and the reports proved it: typed pairs delete the collision, they do not reconcile it |
| Rename `mode`'s values (`one`/`active`/`archived`) | Still an enum encoding arity, still allows `one` with no id. Cheaper, but fixes the word and not the axis |
| Give silences three typed fields (`alarm_type`/`domain`/`ip`) | `domain` and `ip` are too vague as service-level fields, and `alarm_type` already means a *filter* on `get_alarms` — it would become a third meaning of one name |
| Rename the rules side to free `target_*` for silences | The rules side mirrors `FirewallaPolicyRule.target`/`.target_type`; breaking that correspondence to keep a name on the smaller surface is backwards |

### 9h. Churn

| Surface | Count |
| --- | --- |
| Services with a selector to change | 4 (`create_rule`, `get_rules`, `mute_alarm`, plus the two alarm bulk services already migrated) |
| Services changing `detail` | 3 (`get_alarms`, `get_time_usage_report`, `get_flow_report`) |
| Translation keys removed / added | 6 removed · 2 added · 3 added (`match_*`, `alarm_set`) |
| LLM tools touched | 6 (`create_rule`, `get_rules`, `mute_alarm`, plus `archive_alarm`/`archive_all_alarms`/`delete_alarm`/`delete_all_alarms` already migrated) plus their `_INTENTIONAL_OMISSIONS` entries |
| Guard work-list entries cleared | 3 (both remaining `scope_kind`s and the unvalidated `target_type`) |

**Sequencing.** 9f-2 and 9f-5 are independent of the protocol question and can land
first. 9f-1's rules half is independent. 9f-3's **network** form is the only part
gated on a capture, and 9f-4 is the only part that subtracts information — so both
are worth confirming before they are built rather than after.

---

## 10. Phase 3.2 — decisions taken, and what landed

### 10a. The owner's three answers

| Question | Answer | Consequence |
| --- | --- | --- |
| Silence match fields | **`alarm_match_type` / `alarm_match_value`** | Chosen over `match_*` for explicitness. It also avoids a second meaning of `match` in the same signature, since the manager already had a local `match_type` for the *wire* key |
| Alarm population field | **`alarm_status`** (`active`/`archived`) | Checked for collision — see 10b |
| `detail: full` | **Accepted** if consistent elsewhere | `full` is already the word on two services; 9f-4 not yet built |

### 10b. `alarm_status` — checked, and it does not collide

Measured: **no service field is named `status` anywhere.** The word appears in
`get_wireless_status` (a service *name*), in entity translation keys
(`system_status`, `ap_status`), in `FirewallaWanEventStatus` (a nested model), and in
`_STATUS_ENABLED` / `_STATUS_DISABLED`, which are a **rule's** enabled state inside a
display string.

The one adjacency worth stating: an alarm carries its own `state` string, normalized
from the wire with no constants and **compared nowhere** — it is never published as
an attribute and never branched on. So `alarm_status` cannot be confused with
anything the integration acts on, and the two words describe different things (a
population the operation selects, versus an uninterpreted wire string).

**Limitation to carry:** the box's snapshot reports a **third** population,
`pending_alarm_count`, which the alarm commands cannot select. `alarm_status` names
only the two that are reachable, and the vocabulary comment says so rather than
implying the enum is the whole model.

### 10c. The network scope is no longer gated — evidence found

9c said `p.intf.id` was unverified. It is verified, by the reverse-engineering note
this repository already keeps:

- `docs/REVERSE_ENGINEERING_WORKFLOW.md` documents `| p.intf.id | a network |` and
  cross-references the MSP model, where `network` → `scope.value` = **network ID** →
  local `p.intf.id`.
- A captured flow record carries `"intf": "95169e6a-a7c9-4d6a-8e83-6061b4812bf2"` — a
  UUID, the same shape as `FirewallaNetwork.uuid`.

So a network scope is a network id, and `network_uuid` / `network_name` are the
correct field names. **The gate is lifted**, though the migration is still not built
(see 10e).

### 10d. What landed in this step

**Silences.** `target_type`/`target_value` → `alarm_match_type`/`alarm_match_value`,
with `MATCH_TYPE_ALARM_TYPE / _DOMAIN / _IP` as the vocabulary and the wire
translation (`alarmType` / `dns` / `ip`) left in the manager. Naming the caller's
values and the wire's the same thing was also actively confusing, because
`alarm_match_value` carries the alarm's own `alarm_type` value — "match the alarm
type ALARM_INTEL" reads as a contradiction when both are called `target`.

**The alarm `mode` axis is gone.** `alarm_id` XOR `alarm_status`, both optional,
exactly one required. `this` disappears because naming an alarm *is* selecting one.
**The failure mode is now unrepresentable rather than caught:** `mode: "this"` with
no `alarm_id` used to be a runtime error, and is now impossible.

**Archive takes no set parameter.** `ARCHIVE_ALARMS_SCHEMA` offers only
`alarm_status: active`, because archiving is meaningful only for an active alarm, and
the manager method takes just an `alarm_id` — a status argument the method would
ignore is exactly the "requested then discarded" smell this initiative removes. The
enum keeps one value deliberately: it is the explicit statement of intent that stops
a forgotten field archiving the whole set.

**Six conflict keys → two.** `TRANS_KEY_EXCEPTION_SELECTOR_CONFLICT` /
`_REQUIRED`, carrying `{selector_fields}`, so each service names the fields it
actually accepts and no service needs its own key. `select_exclusive` is the one
implementation, and `select_scope` is now that function with the scope vocabulary
attached rather than a second copy of the rule.

**Validation before I/O.** Selecting the alarm set now happens before the config
entry is resolved, so an invalid call fails on its own terms rather than on entry
state. Found by the new test: with no entry loaded the handler raised
`multiple_entries_loaded` instead.

### 10e. Still open from 9f

- **9f-3, the `scope_kind` migration** — and the network evidence changes its shape.
- **9f-4, `detail` unification.**
- **9f-1's rules half** — `create_rule` / `get_rules` onto `RULE_TARGET_TYPE_*`.

### 10f. A safety tension 9f-3 has to resolve, surfaced while building this

The reverse-engineering note records **why** the alarm services required an explicit
`scope_kind`: locally, "all devices" is reached by *omitting* every scope key, so
"an accidental global mute is what a caller gets by forgetting a field. Requiring the
value makes it a deliberate choice."

That argues against the "omit → all" form 9f-3 proposes for `create_rule`, and it is
the same hazard the new alarm design just closed by requiring exactly one selector.
Two consistent options:

1. **Scope pairs XOR an explicit wide marker**, mirroring `set_host_group`'s
   `clear: true` — which is already this integration's precedent for "the
   no-specific-target case, chosen deliberately". The marker needs a name that does
   not collide with `scope`, which elsewhere means the flat rule identifier list.
2. **Require a scope on `mute_alarm`**, dropping the box-wide case. Simplest and
   safest, but removes a real capability (silence an alarm type everywhere).

Option 1 preserves both the capability and the safety property, and matches an
existing pattern, so it is the recommendation — but it is a design choice about a
mutating service, so it is being put back rather than taken unilaterally.

### 10g. `create_rule`'s scope is worse than "requested then discarded" — measured

Checked before writing 9f-3, and the finding is stronger than 9c recorded. Read
`services.py` 4538-4545:

```python
scope_kind = cast(str | None, call.data.get(SERVICE_FIELD_SCOPE_KIND))
scope_target = cast(str | None, call.data.get(SERVICE_FIELD_SCOPE_TARGET))
scope = (scope_target,) if scope_kind == "device" and scope_target is not None else ()
```

The field is declared `vol.In(("device", "network", "all"))`, but **only `device` is
ever read**. So:

| Caller writes | Intended | Actually created |
| --- | --- | --- |
| `scope_kind: device`, MAC | rule applies to that host | correct |
| `scope_kind: all` | every host | every host — *coincidentally correct* |
| **`scope_kind: network`, VLAN10 id** | **rule applies to VLAN10** | **empty scope = every host** |

**A network-scoped rule becomes a box-wide rule, silently.** An empty scope is the
all-device scope, which is not inference: `scope_kind: "all"` maps to the same `()`,
and `block_alarm_target` relies on omitting scope entirely to mean "block everywhere".
So the two paths that should be different are the same value.

Three further defects in the same field, all in the untested path:

1. **`scope_target` is `cv.string`, passed raw as a scope value.** The wire expects
   MACs there (`scope: list[str]`). A caller writing a host name gets that name sent
   as if it were a MAC, with nothing in the integration checking otherwise.
2. **Nothing enforces that the target matches the kind.** `device` + a network id, or
   `network` + a MAC, are both accepted.
3. **Coverage: none.** No test exercises `create_rule`'s scope at all. Grepping the
   suite for a non-report `scope_kind` finds only the LLM schema declaration and two
   *alarm* tests. The silent widening has never been asserted either way.

This is why 9f-3 is not cosmetic. The unifying change is what removes a defect that
turns a narrow rule into a sweeping one without an error, and the typed pairs are
what make the mistake impossible rather than merely visible.

---

## 11. Phase 3.2 — the scope decisions, and the rule tag-ref trap

### 11a. Decisions taken

| Item | Decision |
| --- | --- |
| The wide case | **`all_hosts: true`** — stated, never inferred. Machine word `host` |
| Silence match fields | **`alarm_target_type` / `alarm_target_value`** — reverses the earlier `alarm_match_*`, see 11b |
| Group/user rule scope | **Exposed now** — it closes a broken round-trip, see 11d |
| Single group or user | The app allows **one** group or **one** user, never both, never several |

### 11b. `target` beats `match`, and the reversal is deliberate

`alarm_match_type`/`alarm_match_value` were introduced two commits earlier and are
replaced by `alarm_target_type`/`alarm_target_value`. Three measurements:

| Evidence | Count / shape |
| --- | --- |
| `target` in `services.py` / `api/client.py` / `models.py` | 139 / 108 / 80 |
| `match` in the same files | 81 / 3 / 9 |
| The vendor's own silence payload | `{"type": …, "target": …}`, `"if.target"`, `"target_name"` |
| The vendor's rule payload | `type` + `target`, the same shape |

`match` was our invention; `target` is both our established word and the vendor's
word for this payload. The `alarm_` prefix stays because bare `target_type` would
collide with the rule's `target_type`, which is a genuinely different enum
(`dns|ip|mac|network|category|remotePort` vs `alarm_type|domain|ip`) — a subset or
superset would not have resolved that, only a distinct name does.

*Honest wrinkle:* of the three values, `alarm_type` maps to the wire's `type` rather
than `target`. The name is exact for two values and slightly loose for the third,
which is better than a name exact for one value and inconsistent with the rest.

### 11c. The rule tag-ref trap — a user's rule reference is a **group**-prefixed tag

**This is the finding the whole caution was about.** The read side, at
`api/client.py` 2595, resolves a rule's tag reference like this:

```python
if tag_prefix == _RAW_TAG_PREFIX_GROUP:  # "tag:"
    if user_names := affiliated_users.get(tag_value):
        return ", ".join(user_names), "user"  # ← a USER, under the GROUP prefix
```

So the box expresses a rule's **user** attachment as `tag:<affiliated_tag_id>` — the
group prefix, carrying the user's *affiliated tag*, not the user id. The prefix
vocabulary (`tag` / `dtag` / `utag` / `userTag` / `intf`) has a `utag` form, and a
rule does **not** use it for a user.

Consequence for the write side, and the reason this had to be checked rather than
assumed:

| Scope | Wire reference | Why |
| --- | --- | --- |
| host | `scope: [<mac>]` | the identity is the MAC; `scope` is the MAC list |
| group | `tag: ["tag:<group_id>"]` | the group's **own** tag id |
| user | `tag: ["tag:<affiliated_tag_id>"]` | the user's **affiliated tag**, under the group prefix |
| network | `tag: ["intf:<network_uuid>"]` | `intf:` is the network prefix |
| all hosts | both lists empty | absence is the wide scope |

Writing `utag:<user_id>` for a user — the obvious-looking choice from the prefix
list — would be wrong for this payload. It is also the same failure shape the flow
work already found: a user id is accepted, answered, and empty.

**Verification status, stated rather than implied.** The *read* side proves a user
rule ref is `tag:<affiliated>`; whether the *create* path accepts that form is listed
as an **open question** in `REVERSE_ENGINEERING_WORKFLOW.md` ("whether all
internet-block rules share the same `target: TAG` and `type: mac` contract across
other scopes such as users, networks, and other groups"). So the write is implemented
to match the read side — the strongest available evidence, and the only form that
makes the round-trip work — and the tests pin the exact payload so a capture can
confirm or correct it without re-deriving the design.

### 11d. The round-trip this closes

`ARCHITECTURE.md`: *"Anything a service reports as an id, it must also accept as a
selector."* Rules violated it: `get_rules` reports `tag_refs` (`tag:17`) and
`applies_to_kind` (`group`/`user`/`network`), while `create_rule` could write only a
host MAC and silently discarded everything else. You could read what a rule applies
to and not create a rule that applies to it.
---

## 12. Capture request — the rule scope write forms — **RESOLVED 2026-10-05**

Captured (Lane B, `port 8833`, phone client). One internet-block rule created per
scope in the app, pre-action pull diffed against the pushed runtime (325 → 328 rules).

| Created as | `scope` sent | `tag` sent | Read back as |
| --- | --- | --- | --- |
| group `AV_AUDIO` | `""` | `["tag:27"]` | `tag_refs=('tag:27',)` `applies_to_kind=('group',)` |
| **user `KADENS_DEVICES` (uid 32)** | `""` | **`["tag:31"]`** | `tag_refs=('tag:31',)` `applies_to_kind=('user',)` |
| network `VLAN10 CORE` | `""` | `["intf:95169e6a-…"]` | `tag_refs=('intf:…',)` `applies_to_kind=('network',)` |

**Every form the implementation writes was confirmed, including the one that
mattered.** Selecting the *user* in the app produced `tag:31` — the affiliated
backing tag, under the `tag:` prefix — and not the user id and not `utag:32`. That
is exactly what `_resolve_scope_identity` produces, and the read side resolves it
back to `applies_to_kind=('user',)`, so the round-trip closes in both directions.

Two things the capture added beyond the original request:

- **`scope` is empty for a tag-scoped rule** and the pushed rule omits it entirely,
  echoing the reference in `tag` (singular). The read side already keys on `tag`, so
  nothing there needed changing — verified by running the real normalizer over the
  captured payload rather than by inspection.
- **A discrepancy worth knowing:** the app sends the empty scope as the *string*
  `""`, while this integration's builder sends the empty *list* `[]`. Both mean "no
  MAC scope" and the box accepted `""`; whether it is strict about the type is
  unknown, because **our create path has never been captured**. One device-scoped
  rule create would settle it and capture the non-empty `scope` form, which is also
  unseen.

**A note on the app's own vocabulary, from the owner:** the app only offers the
*user* `KADENS_DEVICES` for selection, never the group `KADEN's Devices`. The tag
collection carries both — id `31` is the affiliated backing group for user uid `32` —
which is why the write is `tag:31`. This is the same "a user is backed by a tag"
relationship the flow work established.

The test `test_rule_template_create_value_carries_the_captured_scope_forms` pins all
three captured `tag` arrays verbatim, so the wire form is now guarded by measurement
rather than by the read side's shape. The finding is recorded in
`docs/REVERSE_ENGINEERING_WORKFLOW.md`, and the open question it answered is removed
from that document's list.

### 12b. The alarm mute network scope — still open, lower priority

`_get_scope_payload` sends `p.intf.id` for a network scope. The reverse-engineering
note documents it as a network ID, and the rule capture above confirmed a network's
`uuid` **is** that identifier (`intf:95169e6a-…` is VLAN10 CORE) — so the value is
right. What is still uncaptured is the *key*: `p.intf.id` has never been seen in a
live mute, only documented and matched by shape.

One mute with a network scope would close it. Lower priority than the rule path was,
because that code already existed and is not newly written.

---

## 13. Phase 4 — measured before building

### 13a. The four "discarded" WAN filters return nothing, and never have

§5 listed four requested-then-discarded filters. Measured against the live box before
changing anything:

| Probe | Result |
| --- | --- |
| `action/ping_RTT` (control) | **1 event** — so the query itself works |
| `state/ethernet_state` | 0 |
| `state/ap_ethernet_state` | 0 |
| `state/ap_ethernet_speed_change` | 0 |
| `action/wpa_connection` | 0 |

Over a **400-day** window, all four return zero. And the decisive check: an
unfiltered read of the whole firehose (173 events) contains only `dns` (154), `ping`
(14), `overall_wan_state` (2), `wan_state` (2) and `ping_RTT` (1) — **none of the four
appear anywhere**, so this is not a case of the event being rare within a window.

**Conclusion: these are not requested-then-discarded, because the box has no content
for them.** The filters cost nothing and drop nothing observable.

**Recommendation: leave the code, record the measurement.** Removing the four would
re-diverge from the app's own 14-filter list, and that parity was a deliberate fix —
`544b18e` widened this from 3 filters to 14 precisely because the narrower list missed
latency and loss faults. Trading a measured-harmless parity for a hypothetical is a
bad trade.

**The one thing that stays true:** if a future firmware, or an AP7, ever emits one of
these families, the normalizer would drop it silently. That is the same defect class
the rest of this initiative removed. It is recorded here as a latent risk rather than
fixed, because there is no sample to build against and no observed data to serve —
surfacing them is a feature needing its own evidence. **Lowest priority in the
initiative.**

### 13b. 4.1's blast radius is exactly the 12 attribute keys

Checked before proposing the rename, because the concern was changing user-facing
names. Measured:

| Surface | Contains `device`? | Changes in 4.1? |
| --- | --- | --- |
| Attribute **values** (`ATTR_*` constant values) | yes, 12 of them | **yes** |
| Attribute **labels** (translation `name:`) | yes — *"Devices online"*, *"Device group"* | **no** |
| Entity **names** | no — `'{host_name}'`, `'Presence'` | no |
| Entity **ids** (`object_id`) | **no** — `system_status`, `alarm_active`, `network_{uuid}`, `ap_{id}_system_status`, `mac`, `user_id` | no |
| `device_tracker` | the platform name | no — Home Assistant owns it |
| Entity translation **keys** (`watched_device`) | yes, as a lookup key | optional, see below |

So the rename is **machine-facing only**: an automation reading `devices_online` has
to read `hosts_online`, and nothing a person sees changes. Per the register boundary
that is exactly right — a key inside a payload is machine; a sentence explaining it is
human — and the two are supposed to differ.

**`watched_device` is the one judgement call.** It is the *value* of
`TRANS_KEY_ENTITY_BINARY_SENSOR_WATCHED_DEVICE`, used to look up
`entity.binary_sensor.watched_device`. It is a machine key, so the rule applies, but it
is internal — no user reads it, and nothing derives from it that a user writes. The
entity shows the host's name and its `entity_id` is the host's MAC. **Rename it for
consistency or not; it is not part of the breaking change either way.** Recommendation:
rename only if it is free, and never as part of the same change, so the breaking part
stays narrowly defined.

**Not a finding:** seven pairs of `ATTR_*` constants share a value (`ports`,
`timezone`, `vlan_id`, `wan_name`, `wan_uuid`, `last_active`, `purpose`). Those are the
same key name on different entity types, which is intentional reuse, not the
duplicate-under-one-name defect §2b found. Recorded so the scan result is not mistaken
for a problem later.

---

## 14. Phase 4 — what landed, and the one thing that did not

### 14a. The doctrine was corrected, because measurement contradicted it

This initiative's *Register boundary* — "machine says `host`, human says `device`" —
was **wrong**, and the numbers said so before the code did:

| Human surface | `device` | `host` |
| --- | --- | --- |
| `services.yaml` names and descriptions | 26 | **111** |
| LLM control tool descriptions | 28 | **38** |
| LLM read tool descriptions | 18 | 19 |
| Entity attribute labels | **13** | 0 |
| Options/setup flow prose | **13** | 0 |

The rule described an intention rather than the code. What the code actually does —
and what the pre-existing *critical rule* always said — is **`host` everywhere, except
where `device` means a Home Assistant device-registry concept**. The 13 attribute
labels were the outlier, not the human register.

`ARCHITECTURE.md` now states one vocabulary with one exception, and names
`device_tracker` explicitly, because that platform is Home Assistant's and must never
be renamed. `DEVELOPMENT_STANDARDS.md` gained the same rule plus *"one concept never
gets two published names"* — which is the rule that caught the two service responses.

### 14b. What was renamed

**12 attribute keys and their constant names**, **13 labels**, and **five
same-concept service-response keys**:

| Surface | Count | Breaking? |
| --- | --- | --- |
| `ATTR_*` constant names + values | 12 | values yes, names internal |
| Translation labels (`'Devices online'` → `'Hosts online'`) | 13 | cosmetic — a person reads different words |
| Service-response keys that are the same concept (`get_runtime_inventory`'s three counts; the network list's `host_count`; the alarm's `host_name`) | 5 | **yes** |

The service-response renames were not in the agreed scope; they were required by *"one
concept never gets two published names"*. `get_runtime_inventory` published
`devices_online` while the entity published `devices_online` too — renaming only the
entity would have split one value across two names, which is the defect this initiative
exists to remove.

**Deliberately left alone:**

- **`ATTR_WATCHED_DEVICE_*` constant prefix** (17 constants). The *values* are clean; only
  the internal prefix says `device`. It is the feature's name (`watched_device` is also
  the entity translation key and the options-flow wording), and it sits directly beside
  `device_tracker` — the area the owner asked to treat carefully. Renaming the feature
  is a separate, wider change (options text, entity keys, class names) and is **not**
  part of this. **Decided by the owner on 2026-10-06: fine as-is.** The constants are
  private, so no published name carries `device` as a result and the rule still holds.
  One user-visible string does say `device` about a host — the options label
  *"Unavailable device"* (`TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE`) — and it stays
  with the feature it labels.
- **`device_id` / `device_ip` / `device_name` on flow records, usage rows and member
  rankings.** Originally deferred as §8b. **Now resolved — see §15.** The deferral
  argument ("a mirrored vendor record keeps the vendor's names") did not survive the
  measurement: the record layer renames the vendor's keys in the same row, so keeping
  three of them was drift, not a boundary.

### 14c. The work list is deleted, and the guard's claim was narrowed

`_KNOWN_VIOLATIONS` is **gone** — not empty, deleted. An empty allowlist is an
invitation to add one entry to it. The three checks now assert zero violations, with no
exemption mechanism, and a fourth test proves the scanners are reading real data so a
passing suite cannot mean "the scanner stopped working". Verified by injecting a
violation into `ATTR_ALARM_HOST_NAME` and watching the guard fail with nowhere to record
it.

**4.5's widening was declined, deliberately.** Scanning literal payload keys would have
flagged roughly a dozen more published keys — a second breaking wave on a weaker
argument (internal payload keys rather than published discriminators). Instead the
guard's documented scope was shrunk to match what it enforces, and the uncovered
surfaces are named in the guard itself rather than left ambiguous. A narrower claim that
is completely true beats a broad claim that is mostly true.

That decline was about *widening the guard*, and it still stands: the guard still does
not read literal keys. It was never a reason to leave the keys themselves alone — §15
renamed them by hand, and the service and entity tests that assert exact payloads are
what hold them now. The guard comment was updated to say so, so the gap is not misread
as a deferral.

### 14d. One pre-existing smell surfaced and left alone

`get_runtime_inventory`'s summary publishes **both** `host_count` (raw payload entries)
and `hosts_total` (normalized hosts). They are usually the same number computed two
ways. Renaming the second made the pair visible; merging or dropping one is a behaviour
change nobody asked for, so it is recorded rather than fixed.

## 15. The `device_*` published keys — measured, then removed

Asked whether the LLM instructions and the documentation should state that `host` is
primary *because* flow rows still hand an agent `device_id` / `device_name`, and the agent
would have to guess whether those mean a host. Two answers came out of measuring it, and
the second one replaced the justification that had already been written into the docs.

### 15a. The justification was wrong, in both directions

The first draft of the doctrine said these keys were a **mirrored vendor record** — the
row keeps the vendor's field names, so renaming would break the correspondence with a
capture. That claim was asserted, not measured, and measuring it killed it:

- The vendor's host inventory keys are **`mac`, `bname`, `bonjourName`, `dhcpName`, `ip`,
  `type`, `deviceTags`, `userTags`** — not `device_id` / `device_name` / `device_type`.
- The vendor's flow row *does* say **`device`** for the host id, and **`deviceIP`** and
  **`devicePort`** — so `device_id` / `device_ip` / `device_port` were the closest thing
  to a genuine mirror.
- But that same row's other keys are **renamed by us**: `dstMac` publishes as
  `destination_mac`, `pid` as `blocked_by_rule_id`, `type` as `block_type`, `intf` as
  `network_id`, `country` as `region`. The keys kept verbatim — `port`, `protocol`,
  `apid`, `category`, `app` — are ones that are already exact and are not the host
  concept.

So there was no mirror register to appeal to. The record layer normalizes, and `device`
happened to be the one vendor key that was left alone. The honest statement is the
opposite of the first draft: **the vendor says `device` and we deliberately do not echo
it, because in Home Assistant a *device* is a device-registry entry.** That is the reason
the vocabulary needed to exist in the first place, and it now reads that way in
`ARCHITECTURE.md`, `DEVELOPMENT_STANDARDS.md` and the LLM prompt.

The first draft also over-claimed in the other direction — it promised "these rows are the
only place `device_` still appears; everywhere else the field name says `host`". False:
`device_type`, `device_host_count` and `device_rules` were published too, none of them
from a vendor row. An agent told "everywhere else says host" and then shown `device_type`
beside `host_id` in the same object would be less sure, not more.

### 15b. What was renamed

Eight published keys, in a row-level sweep so no object ends up mixed:

| Was | Now | Class |
| --- | --- | --- |
| `device_id` / `device_ip` / `device_port` | `host_id` / `host_ip` / `host_port` | flow records, rule `last_hit`, and their projections |
| `device_name` | `host_name` | flow member rows, usage rows, network top talkers |
| `device_ids` | `host_ids` | flow destination rows |
| `device_type` | `host_device_type` | network segment host rows and the `set_host_device_type` tool result |
| `device_host_count` | *(deleted)* | it carried the same value as `host_count` in the same dict |
| `device_rules` | `host_rules` | the membership response's removed-rule list |

Two were not drift on someone else's terms — they were internally contradictory already.
`device_type` sat in a row whose siblings were `host_id` and `host_name`, and the same
concept was published as `host_device_type` by the service field, the service result key
and one other serializer. `device_host_count` was a second name for a number already in
the dict under `host_count`.

### 15c. The breaking-change accounting is smaller than it looks

`build_rule_hit_attributes` is released and user-visible — it feeds the `ATTR_RULE_LAST_HIT`
attribute and the `get_rules` service. On `main` it publishes **`device_mac`**; this branch
had already renamed it to `device_id`. Renaming it again to `host_id` is therefore **the
same single break, only better named** — not a second one. `device_ip` and `device_port`
are on the same object and were already changing on this branch.

The remaining breaks are the usage-history rows and the network top-talker rows, both
released, and both covered by the one migration table in `USER_GUIDE.md` and the entry in
`RELEASE_CHECKLIST.md`.

### 15d. What holds it now

The guard in `test_vocabulary.py` reads constant *values*, so it cannot see a literal
payload key — the limitation it states. What holds these eight is the tests that assert
the exact payloads: `test_services.py`, `test_switch.py` and `test_binary_sensor.py` all
compare whole dicts. Verified by injecting `"device_id": member.device_id` back into the
flow member row and watching `test_flow_report_returns_host_detail_when_it_is_asked_for`
fail; restored, 761 pass.

**Measured end state:** `grep` for a literal `device_` key in the package returns only
`device_tracker` / `device_trackers` / `device_tracker_away_window` — the Home Assistant
platform names, which must not move.

## 16. The instructions, and four more key classes the first sweep could not see

Asked to confirm whether the flow reports now return `host_name` / `host_id` or still
say `device`. They return `host_*` — verified by running the service and searching the
serialized response, not by reading the serializer. Measuring it also found that the
*instructions* still said `device` 97 times against 35 `host`, while the payloads they
describe said `host` throughout. That gap is the answer to "would the agent have to
guess": the response was clean, and the description of the response was not.

### 16a. The key inventory was incomplete, in three ways

The `device_` scan that closed §15 looked for keys **starting** with `device_`. Three
shapes slipped past it, and each was found only by asking what a *published key*
actually is:

| Shape | Missed keys |
| --- | --- |
| a bare word, no underscore | `devices`, `vpn_devices` on `get_system_overview`; `devices` on the network-segment usage section and its provenance; `devices` on the time-usage app and category rows |
| a `device` prefix on a count | `active_device_count` |
| a published **value** | `destination_kind: "device"` |

So the honest count was **eight more published names**, not the eight §15 renamed. Two
of these were internally contradictory on their own terms: `active_host_count`'s site
sat in a summary that already had `host_count` and `known_host_count`, and
`destination_kind` offered `host` *and* `device` as two kinds of host-shaped
destination. The second one is why the LAN-peer kind is now `peer` — a word the record
layer had already chosen everywhere else (`peer_id`, `local_peers`,
`_serialize_local_peer`). The vendor never said `device` for that value; we did.

### 16b. Why three sweeps produced three different classes of bug

Worth recording, because each one passed a green suite before being caught:

1. **The line rule rewrote code.** `for device in metric.devices` became
   `for host in metric.hosts` — a rename of the model's field, not of prose. Fixed by
   scoping the sweep to `tokenize` COMMENT and STRING tokens, which makes identifiers
   untouchable by construction.
2. **The offset math was wrong for multi-line tokens.** Slicing within the start line
   duplicated the tail of every multi-line docstring. Fixed by splicing the whole
   source by absolute token offsets.
3. **Markdown has no tokenizer, so the protections have to carry it** — and they did
   not, twice. "Settings → Devices & Services" became "Hosts & Services"; "two other
   meanings of `device`" became "two other meanings of host"; "Device Active Protect"
   wrapped across lines and became "Host Active Protect". Every one of those is a
   phrase about Home Assistant's or Firewalla's own concept, and every one was fixed by
   naming the phrase rather than the word. A prose sweep of user documentation is not
   the same operation as a key rename, and it should not have been attempted with the
   same tool.

The lesson that generalises: **a vocabulary rule stated as "one word" still needs the
exceptions enumerated, because the exceptions are all cases where the word belongs to
someone else.** Home Assistant owns `device` (the registry), the vendor owns
`device`/`deviceIP`/`deviceTags` (its wire), and the app owns "Show past devices" (its
UI). None of those are drift.

### 16c. What holds it now — a guard that reads keys, not values

The §15 guard reads constant *values*, which is exactly why it could not see a literal
key. `test_no_published_key_names_a_host_as_a_device` closes that: it walks the
publishing modules for **dict keys and subscripts by position in the syntax**, and
fails on any literal containing `device` that does not start with `host`. One survivor
is allowed and asserted: `host_device_type`, which carries the prefix. A second test
proves the scanner found real keys, so a pass cannot mean "the scanner walked nothing".

Verified non-vacuous by injecting `"device_name": member.device_name` back into the
flow member row: the guard fails naming the key, and 763 pass when it is restored.

**Measured end state:** the only `device_*` literals left in the package are
`device_tracker`, `device_trackers`, `device_tracker_away_window` — the Home Assistant
platform names, which must not move. The tool layer reads `device` 13 times against
`host` 216, and every one of the 13 is a named exception: `host_device_type` (5),
Firewalla's `Device Active Protect` (1), the app's "Show past devices" (1), the
vocabulary sections that name the word on purpose (6).
