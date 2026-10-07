# Vocabulary Alignment — COMPLETED

**Initiative:** One vocabulary across every surface a user or model reads or writes
**Branch:** `feature/flow-reporting` (the vocabulary work continued on it; nothing here
was pushed)
**Depends on:** nothing. Independent of the flow-reporting initiative, though it
finishes work that initiative started.
**Status:** **COMPLETE — all four phases, closed 2026-10-06.** The rule is one word,
`host`, with a single exception where `device` means a Home Assistant device-registry
concept. Every `device`-named published key and value is gone, the LLM instructions and
the prose were swept, and two guards hold it. 763 tests pass; `ruff check`,
`ruff format` and `mypy` are clean.
**Supporting note:** `FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_SUP_INVENTORY.md`
**Last updated:** 2026-10-06

---

## 1. Initiative snapshot

An audit of all 34 services, the entity attributes, the LLM tools and the docs found
that the integration presents **three different vocabularies for the same concepts**,
and in three places **one field name carries two unrelated meanings**. A model or a
user cannot predict the shape of one service from another, which produces wrong
calls rather than merely untidy ones.

The audit is in the supporting note. The headline findings:

| Finding | Evidence |
| --- | --- |
| `target.kind` has **seven** values across services, two of which name the same thing | `network_segment` (segment usage) and `vlan`/`lan` (network config) are both "a network" |
| `scope_kind` carries **three unrelated enums** under one name, across **five** services | `device\|group\|user` (reports), `device\|network\|all` (rules), `device\|group\|user\|network\|all` (alarm silences — a superset, so the union cannot be inferred) |
| `target_type` carries **three treatments** under one name | `dns\|ip\|mac` (rules), **unvalidated `cv.string`** (`get_rules`), `alarm_type\|domain\|ip` (alarm silences) |
| Device selection uses **three** vocabularies | `host_*` (11 services), `scope_kind`+`scope_target` (2), `target_type`+`target_value` (2) |
| `host` and `device` are used interchangeably **in the same register** | `host_mac` next to `target.kind: "device"` |
| 4 of 14 WAN event filters are requested and then discarded | `ethernet_state`, `ap_ethernet_state`, `ap_ethernet_speed_change`, `wpa_connection` are not in the supported sets |

**The root cause is not a missing rule.** `ARCHITECTURE.md` *Lexicon standards*
already states it, including the critical rule that `device` means the Firewalla box
and must not be used for endpoint inventory. The rule was correct and was violated
anyway, three times — most recently by this initiative's own author, who changed
`target.kind` to `device` while reasoning about a protocol leak and did not check the
lexicon. **A rule that is only prose is not enforced.** That is the finding this plan
is built around.

**Why now.** Everything in scope is unreleased, so this is the last moment at which
the vocabulary can be changed without a compatibility shim — and the explicit
constraint is that **no shims or compatibility translators are in scope**.

### The register rule this plan proposes

The audit found the vocabulary is not actually inconsistent; it is **two registers**,
and nobody wrote that down:

| Register | Who reads it | Word | Surfaces |
| --- | --- | --- | --- |
| **Machine** | automations, models, code | **`host`** | service field names and enum values, `target.kind`, `include` values, entity attribute keys, tool parameters |
| **Human** | people | **`device`** | service `name:`/`description:` values, tool descriptions, documentation prose |

Measured support: all 15 device selector fields are `host_*`, all device-facing
service names use `host` (`get_hosts`, `wake_host`, `set_host_membership`), and zero
services are named `*device*`. The machine register is **already** `host`; the newer
services simply did not follow it. The prose surfaces lean the other way — the user
guide says "device" 137 times against 45 "host".

Naming the boundary is what turns the remaining phases from judgement calls into
mechanical edits.

> **Superseded — this proposal was wrong, and the measurement that killed it is why
> Phase 4 exists.** The two-register table above was the plan's opening hypothesis:
> `host` for machine surfaces, `device` for human prose. Phase 4 measured the prose and
> found it did not support a second register. Service-facing text already said `host`
> **111 times against 26** for `device`, so the human register was never `device` — the
> entity attribute *labels* were the outlier that made the split look real. The final
> rule is **one word**, `host`, with a single exception where `device` means a Home
> Assistant device-registry concept. It is stated in `ARCHITECTURE.md` under
> *Vocabulary: `host`, with one exception* and enforced by `test_vocabulary.py`, and the
> prose was swept rather than left in a second register — so the user guide's "device"
> count above no longer holds. The table is kept as the record of what was proposed,
> not as guidance.

---

## 2. Scope and non-goals

### In scope

- One canonical `target` object shape on every response, from one vocabulary module.
- One canonical selector vocabulary for every service that takes a scope.
- Removing the `scope_kind` and `target_type` name collisions.
- Entity attribute keys brought onto the same rule.
- LLM tool parameters, descriptions and the shared prompt, aligned to the same rule.
- Documentation: the register rule stated once and enforced by test.
- A **guard test** that makes the rule mechanical, with an allowlist that shrinks to
  empty by the end of the initiative.
- The WAN event filter/supported-set mismatch, as the first validated instance of the
  "requested and then discarded" class.

### Non-goals

- **No compatibility shims, aliases or translation layers.** The constraint that
  makes this affordable now. A value changes or it does not.
- **No new behaviour.** Every phase is a rename or a reshape; a step that needs new
  logic is a signal the scope has grown.
- **No change to the Firewalla protocol vocabulary in `api/`.** The wire's words
  (`tag`, `mac`, `intf`, `ltype`) are the wire's, and `ARCHITECTURE.md` already
  separates the protocol boundary. Where a wire word must appear, it stays behind
  `api/`.
- **No rule-model redesign.** Rule *target types* (`dns`/`ip`/`mac`) describe how a
  rule matches, which is Firewalla's vocabulary and a genuinely different axis from
  scope identity. Only the *field-name collision* is in scope, not the values.
- **No new entities, services or tools.**
- **No service renames** unless a later phase proves one is required; a service name
  is a stable contract and `network_segment` in a name is descriptive, not a kind.

---

## 3. Open questions and external dependencies

Nine material questions, each with the recommendation this plan acts on. Q8 is a
protocol unknown and is called out as such.

### Q1. Which word for the machine register?

**Recommendation: `host`.** It is what the codebase already does — 15 of 15 device
selector fields, every device-facing service name, and the lexicon's critical rule
which says `device` means the Firewalla box. Choosing `device` would require
rewriting the 11 services and the lexicon to match a term the lexicon forbids.

**This reverses a change made during the flow-reporting initiative**, where
`target.kind` was set to `device`. That change fixed a real problem (the protocol
word `tag` was meaningless to a caller) and introduced a lexicon violation while
doing it, because the lexicon was not consulted. Both facts belong in the record.

### Q2. Do entity attribute keys follow the machine register?

**Recommendation: yes.** The affected keys are read by automations, and a user sees
`devices_online` beside `host_name`, which is the confusion this initiative exists to
remove. `hosts_online` beside `host_name` is self-consistent.

Cost: HA shows attribute keys verbatim, so the UI reads `hosts_online`. Accepted,
because `host` is not obscure — it is already the word in `host_name`, `host_mac` and
every host service, so the attribute is joining an established term rather than
introducing one.

Affected (from the audit): `devices_online`, `devices_offline`, `devices_total`,
`vpn_devices_online`, `vpn_devices_offline`, `vpn_devices_total`, `device_count`,
`associated_devices`, `associated_device_count`, `associated_device_group`,
`device_group`, `device_name`.

### Q3. Is `wan` a `target.kind`, or a `network` with a sub-kind?

**Recommendation: `network`, with `network_kind: "wan"`.** A WAN is a member of
`FirewallaNetworkKind` already, so calling it a separate kind splits a concept the
model has unified. Every network-shaped target then reports
`kind: "network"` plus its own `network_kind` (`lan`/`vlan`/`vpn`/`wan`), which also
retires `network_segment`.

The selector fields stay split (`network_uuid` for segments, `wan_uuid` for the
uplink) because that split reflects what the box accepts, and Q4's conflict rule
makes it unambiguous.

### Q4. Typed selector pairs, or `scope_kind` + `scope_target`?

**Recommendation: typed pairs, and `scope_kind` is removed entirely.**

- Reports currently take `scope_kind` (`device|group|user`) + a free-text
  `scope_target`; 11 other services take typed pairs (`host_mac`/`host_name`,
  `group_id`/`group_name`, …). The reports are the outliers.
- `scope_kind` is not one field with three values — it is **three different enums
  across five services**, one of which is a superset of another. A caller cannot
  infer the vocabulary at all.
- Typed pairs also fix a defect `scope_target` has today: a group and a user can
  share a name on a real box, and a single free-text field cannot tell them apart.
  The membership tools split into four fields for exactly this reason, and the
  reasoning is already recorded in the LLM contract test.
- **Removing `scope_kind` resolves Q4's collision by deletion** rather than by
  patching three enums, which is why it is the recommendation over unifying them.

Mechanism: a service declares which pairs it accepts; a shared helper enforces
"exactly one pair, and not both members of a pair" and raises one translation-keyed
error, replacing the per-service `*_selector_conflict` errors.

### Q5. How to resolve the `target_type` collision?

**Recommendation: rules keep `target_type`/`target_value`; alarm silences are
renamed, and `get_rules` gains validation.**

`RULE_TARGET_TYPE_*` constants and the rule vocabulary are established and large;
the alarm-silence selector is two services. A deviation from the rule vocabulary
would need justifying; renaming the smaller, newer surface does not.

The audit found a third treatment neither of those covers: **`get_rules` declares the
same field as `cv.string`**, so a typo silently filters to nothing rather than
failing. Fixing that is in scope, because "a wrong value produces an empty result
indistinguishable from a real one" is the same defect class as the WAN event filters
in Phase 4.2 — the vocabulary work is what surfaced it.

The exact new names for the alarm-silence fields are chosen in Phase 3.2 after
reading the handler, and recorded there with the reason.

### Q6. Do service names containing `network_segment` change?

**Recommendation: no.** `get_network_segment_report` and
`get_network_segment_usage` name what they do; "segment" is descriptive English, not
a `kind` value, and the human register permits it. What must change is the
`target.kind` those services emit, which this plan changes.

### Q7. Does the flow report's `include: ["device_detail"]` become `host_detail`?

**Recommendation: yes.** An `include` value is a machine value. It is also
unreleased, so the change is free.

### Q8. Does the box accept a host-scoped rule target, or only `mac`? *(protocol
unknown)*

**Not resolved here, and not required.** `RULE_TARGET_TYPE_MAC = "mac"` describes how
a rule matches, and the wire vocabulary is the wire's. Per the non-goals this value
is **out of scope** unless reading the handler in Phase 3.2 shows it being presented
to a user as an identity rather than as a matcher. If it is, it becomes a Phase 3
step with its own justification; if it is not, it stays as the wire says. Flagged so
the decision is deliberate rather than missed.

### Q9. Guard test: absolute from day one, or an allowlist that shrinks?

**Recommendation: allowlist that shrinks, and it must reach empty before the
initiative closes.** An absolute test cannot be added to a codebase that violates it,
and a documented exemption list is the pattern this repository already uses for
exactly this purpose (`_INTENTIONAL_OMISSIONS` in the LLM contract test). The
allowlist is also the work list: every phase removes its entries, and a non-empty
allowlist at the end is a failed phase, not a passing one.

---

## 4. Phase summary

| Phase | Name | Deliverable | Gate |
| --- | --- | --- | --- |
| **1** | The rule, and the machinery that enforces it | The register rule stated once in `ARCHITECTURE.md` and `DEVELOPMENT_STANDARDS.md`, the wrong `Scoped identity` section corrected, the audit published as a reference note, and a guard test whose allowlist names every current violation | Guard test added and proven to fail on a deliberately introduced violation; every current violation is in the allowlist; **no production behaviour changed** |
| **2** | Responses: one canonical `target` | One vocabulary module; every serializer emits `kind` from it; `network_segment` retired; the network sub-kind carried as `network_kind` rather than as the kind; tool descriptions aligned | Full suite green; each service's `target` asserted against the canonical set; allowlist shrinks by the response-side entries |
| **3** | Inputs: one selector vocabulary | Typed selector pairs everywhere; `scope_kind` removed; the `target_type` collision resolved; one shared conflict rule replacing the per-service ones; `services.yaml`, translations and tool parameters aligned | Full suite green; one test per service proving exactly-one-selector and the conflict path; allowlist shrinks by the input-side entries |
| **4** | Entities, residual findings, and the absolute guard | Entity attribute keys and labels on the rule; every `device`-named published key and value removed; the LLM tool instructions swept; 4.2 closed by measurement; docs swept; **the allowlist deleted** | Full suite green with **no allowlist**; a deliberately introduced violation fails; no published key or value contains `device` except the `device_tracker` platform name and the host-prefixed `host_device_type`; `ARCHITECTURE.md` states the rule as one word plus the Home Assistant exception |

Phases are sequential. **Phase 1 is not optional and is not documentation busywork.**
It is the phase that makes the other three mechanical: without a written register
rule and a shrinking allowlist, each later phase re-litigates the same judgement
calls, which is exactly how the current state arose.

---

## 5. Phase details

### Phase 1 — The rule, and the machinery that enforces it

**COMPLETE.** 731 tests pass (728 baseline + 3 guard). `ruff check`, `ruff format`,
and `mypy` clean. No production file changed.

Purpose: state the register boundary in the two documents that define standards,
correct the section that states it wrongly, publish the audit as the reference the
later phases work from, and add the guard test that turns the rule from prose into a
build failure. No production code changes.

- [x] **1.1 State the register rule in `ARCHITECTURE.md`.** Done — *Register boundary*
      subsection added to *Lexicon standards*: machine surfaces use `host`, human
      surfaces use `device`, with the surface list from §1. States **which field
      names are machine** (service field names, enum values, `target.kind`, `include`
      values, entity attribute keys, tool parameters) and **which are human**
      (`name:` / `description:` values, tool descriptions, documentation prose), plus
      a positional test for classifying a new field: a value inside an enum or a key
      inside a payload is machine, a sentence explaining it is human.
- [x] **1.2 Correct the `Scoped identity` section.** Done — the table row now reads
      `| device | host | the MAC |`; `target.kind` is stated as the machine register
      (`host`/`group`/`user`/`network`); a rule was added that a network reports
      `kind: network` and carries its own type separately; and the section records
      that it was broken twice in opposite directions. The protocol word `tag` is
      noted as never published.
- [x] **1.3 Add the rule to `DEVELOPMENT_STANDARDS.md`.** Done — *Register boundary
      rule* added after *Normalized host identity* (7 bullets), plus 3 *Review rules*
      entries: register declaration, round-trip, and values-requested-but-discarded.
      A boundary-enforcement line covers published values.
- [x] **1.4 Confirm the audit note against the tree.** Done, and it **found two
      defects in the note and one in the measurement method**:
      1. **Two constants publish one field name.** `SERVICE_FIELD_SCOPE_KIND` and
         `SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND` both have the value `"scope_kind"`.
         A name-keyed scan reports the second as absent — which is how a guard comes
         to pass while the value it exists to find is present. The guard now matches
         on the **published value**.
      2. **The churn table was not reproducible.** Its `99 assertions / 17 files /`
         `6 documents` did not survive re-measurement; §6 now gives numbers with the
         command that produces each. The file count of 17 held; the assertion count
         did not, and the replacement is more useful — **only 7 of 207 references sit
         in an `assert`**, so a half-done rename can leave the suite green.
      3. **Nine services, not the three originally implied**, across 11 selector
         assignments: 5 `scope_kind`, 3 `target_type`, 3 rule selectors, with
         `create_rule` and `mute_alarm` each carrying two.
      The inventory's §7 is now the guard's literal output — 23 keys — so the two
      agree exactly, as this step requires.
- [x] **1.5 Add the guard test with an allowlist.** Done — `test_vocabulary.py`,
      AST-based, 3 tests, 23 work-list entries. It checks published `target.kind`
      values (a pass-through is reported by source text, because that shape hid the
      `device` violation), guarded machine enums (`scope_kind`, `target_type`),
      and guarded constant values (`SERVICE_FIELD_*`, `ATTR_*`). Unresolvable enum
      elements **fail closed**. Substring matching was replaced by tokenising so
      `host_device_type` is not a false positive.
- [x] **1.6 Prove the guard fails.** Done, **in both directions**:
      - injected `ATTR_TEMP_GUARD_PROOF: Final = "temp_devices_online"` → failed
        with `['ATTR_TEMP_GUARD_PROOF']`; reverted
      - removing a violation from the work list while it is still present → failed
        with "these are fixed but still listed as violations"

      The second direction is what makes the list a work list rather than a
      suppression list, and it was observed rather than argued for.

**Deliberately not covered by the guard**, and why: the `target_type` name collision
(no human word, so a collision not a register violation — Phase 3.2), the requested-
then-discarded filters (depends on protocol knowledge, not source text — Phase 4.2),
and documentation prose (the guard reads code — Phase 4.3).

### Phase 2 — Responses: one canonical `target`

**COMPLETE for the report surface.** 732 tests pass. `ruff`, `ruff format`, `mypy`
clean. The work list shrank from 23 entries to 17.

Purpose: every response names its scope from one vocabulary, and the one concept the
codebase already unified — a network — stops being reported under two names.

- [x] **2.1 Create the canonical vocabulary module.** Done, in `const.py`: it already
      owns `SERVICE_FIELD_*`, is imported by every layer, and is free of
      `homeassistant` imports, so it stays importable from the pure layers. It gains
      `TARGET_KIND_HOST` / `_GROUP` / `_USER` / `_NETWORK`, plus
      `TARGET_KIND_BY_REPORT_SCOPE`, which maps the request vocabulary onto the
      published one. The network sub-kinds need no new source: `FirewallaNetworkKind`
      is already the single one.
- [x] **2.2 Emit `target` from the module everywhere.** Done — all 11
      `FirewallaReportTarget` call sites. The five static ones use `TARGET_KIND_HOST`;
      the two scope-driven ones index `TARGET_KIND_BY_REPORT_SCOPE`, which is why
      that map exists rather than a per-service conditional. `network_segment` is
      retired.
- [x] **2.3 Carry the network sub-kind as a field.** Done — `network_kind` on
      `FirewallaReportTarget`, published by `_serialize_report_target`. The
      information-loss check passed and found one real gap: the segment *usage*
      serializer had no `FirewallaNetwork` to read the kind from, only the segment
      identity. Rather than derive it from `view.network_type` (the raw wire string,
      a guess), the lookup the report path already performed inline was extracted to
      `_require_full_network` and both paths now use it. **A WAN collection is
      `network` with a null `id`**, not a second kind: the narrowing is already
      expressed by absence, so no information is lost and the set stays closed.
- [x] **2.4 Align the LLM tool descriptions.** Done, and this uncovered an
      **unassigned** item: Q7 answered `include: ["device_detail"]` → `host_detail`
      but no phase step owned it, so it would silently never have happened.
      Answering a question is not the same as scheduling it. Renamed here, since it
      is a published machine value on the same response as `target.kind` and leaving
      it would have produced `target.kind: "host"` beside `applied.device_detail`.
      The guard gained `FLOW_REPORT_` as a guarded constant prefix so it cannot
      regress.
- [x] **2.5 Shrink the allowlist and validate.** Done — the six response-side entries
      are gone, and `_TARGET_KIND_VIOLATIONS` was deleted rather than left empty. The
      guard now resolves the vocabulary module instead of only literals, and asserts
      the module's constants and its own set agree, so neither can drift.

**Two gaps this phase surfaced that the plan did not inventory — see the inventory
note §8.** Both are outside Phase 2's stated boundary and neither is fixed by it:
a second published `target.kind` vocabulary in the control tools (including a `wan`
that now contradicts the report vocabulary), and payload keys using the human word
in flow records. The first needs an owner decision because it changes the canonical
set, which Phase 1 fixed.

### Phase 3 — Inputs: one selector vocabulary

**COMPLETE.** 755 tests pass. `ruff check`, `ruff format`, and `mypy` clean. The
guard's enum work list is **empty**; the 12 remaining entries are entity attribute
keys, which are Phase 4's.

Purpose: every service that takes a scope takes it the same way, the two name
collisions are gone, and one shared helper replaces the per-service conflict rules.

**What the phase delivered beyond the plan:**

| Change | Why it was needed |
| --- | --- |
| Rule scope: host, group, user, network, or every host | `create_rule` could not express three of the four, and a network scope **silently became a box-wide rule** |
| `all_hosts` flag | The wide case was reachable by omission, both on the wire and through a dropped selector |
| One `_resolve_scope_identity` | A user is written as its **affiliated tag** under the group prefix; a second copy of that rule is how the services would drift |
| `get_rules` validated | A typo returned an empty list that looked like "no such rules" |
| `applies_to_kind` publishes `host` | A vendor word was reaching a live entity attribute as a machine value |
| One `detail` vocabulary | Five treatments, one of them a boolean named `detail` |
| Two guards | The scope rules and the detail vocabulary now fail the build when broken |

**Commits, in order:** `eb247f8` (silence fields), `83b3aa2` (scope), `0e3aff3`
(detail), `5920c7f` (docs).

**One item carried forward as an unresolved protocol question, with a capture
request — see inventory §12.** The rule write forms are implemented to match the
read side, which is the strongest available evidence and the only form that makes
the round-trip work, but they are not capture-verified.

**Superseded plan text.** 3.2 described "the `target_type` treatment that loses" and
a "`mode` near-duplicate". Measurement corrected both: `target_type` was one
vocabulary with a validation gap rather than three treatments, and `mode` was three
unrelated uses. The decisions actually taken are recorded in inventory §9-§12.

### Phase 4 — Entities, residual findings, and the absolute guard — **COMPLETE**

Purpose: the remaining user-visible surface, the one live instance of the
"requested then discarded" class, and the deletion of the allowlist that makes the
rule absolute.

- [x] **4.1 Bring entity attribute keys onto the rule.** The twelve `ATTR_*` **values**
      renamed (`devices_online` → `hosts_online`, `associated_devices` →
      `associated_hosts`, and so on) and their **labels** with them, so the key and the
      label agree. Every consumer updated: `binary_sensor.py`, `sensor.py`,
      `device_tracker.py`, the diagnostics dump, the tests, and `USER_GUIDE.md`. Recorded
      as a breaking change with an old→new table.
- [x] **4.1b The eight `device_*` payload keys.** Added after 4.1, because asking whether
      the documentation should state that `host` is primary exposed them: if an agent
      reads `device_id` in a flow row it has to guess whether that means a host. Measuring
      it killed the justification a first draft had already written into the docs — there
      is no "mirrored vendor record" register, because the record layer renames the
      vendor's keys in that same row (`dstMac` → `destination_mac`, `pid` →
      `blocked_by_rule_id`). So `device_id`/`device_ip`/`device_port`, `device_name`,
      `device_ids`, `device_type`, `device_host_count` and `device_rules` were renamed
      too, and the duplicate `device_host_count` deleted. Full record in the inventory
      note §15.
- [x] **4.1c Eight more published names, and the instructions.** Confirming the flow
      reports end to end showed the payloads were clean and the *instructions describing
      them* were not: the tool descriptions said `device` 97 times against 35 `host`
      while the keys they describe said `host` throughout. Sweeping them found three more
      shapes the `device_` scan had missed — the bare `devices` / `vpn_devices` sections,
      `active_device_count`, and the `destination_kind` **value** `device`, now `peer`.
      A new guard reads published keys by syntax position rather than by constant value,
      which is what let all of these through. Full record in the inventory note §16.
- [x] **4.2 Closable only by measurement, and measurement closed it.** Probed live: the
      four filters (`ethernet_state`, `ap_ethernet_state`, `ap_ethernet_speed_change`,
      `wpa_connection`) returned **zero** events over 400 days, and the unfiltered
      firehose — 173 events, of which 154 dns, 14 ping, 2 `overall_wan_state`, 2
      `wan_state`, 1 `ping_RTT` — contains none of them. So there is nothing to gain by
      adding a family and nothing broken by the discard. **Left as-is**, deliberately:
      the filter set mirrors the app's fourteen, and `544b18e` established that parity on
      purpose.
- [x] **4.3 Sweep the documents.** `USER_GUIDE.md` (examples plus the *Upgrading* table),
      `MCP_TOOL_REFERENCE.md`, `ARCHITECTURE.md`, `DEVELOPMENT_STANDARDS.md`,
      `RELEASE_CHECKLIST.md`. `REVERSE_ENGINEERING_WORKFLOW.md` gained the rule-scope
      finding. Re-swept in 4.1b after the doctrine was corrected.
- [x] **4.4 Delete the allowlist.** `_KNOWN_VIOLATIONS` is **deleted, not emptied** — an
      empty allowlist is an invitation to add an entry. The three checks assert zero
      violations with no exemption mechanism. Confirmed by injecting a violation into
      `ATTR_ALARM_HOST_NAME` and watching it fail with nowhere to record it. A fourth test
      proves the scanners read real data, so a passing suite cannot mean "the scanner
      stopped working".
- [x] **4.5 Quality scale and close.** No quality-scale rule regressed (`docs-actions` and
      `action-exceptions` still `done`; the renamed keys are covered by
      `action-exceptions`). The guard's *widening* was declined on purpose — scanning
      literal payload keys would have been a second breaking wave on a weaker argument —
      and the guard's stated scope was narrowed to match what it enforces, with the gap
      named inside the guard rather than left ambiguous. The doctrine was corrected from
      the two-register rule to one word plus the Home Assistant exception, on measurement.

**Two things deliberately not done**, both recorded rather than silently skipped:

- **`ATTR_WATCHED_DEVICE_*`** keeps its prefix. The values are clean; only the private
  constant name says `device`, and it is the feature's name next to `device_tracker`.
  **Owner decision (2026-10-06): fine as-is.** No published name carries `device` as a
  result, so the rule holds without it.
- **`get_runtime_inventory` publishes both `host_count` and `hosts_total`** — two names
  for usually the same number, computed two ways. Pre-existing; renaming the second made
  the pair visible. Merging them is a behaviour change nobody asked for.
- **Three test rules may still exist on the dev box** (`test 1` / `test 2` / `test 3`,
  each blocking `example.com`), left by the capture work in Phase 3. Removing them is the
  owner's to do and is not part of this initiative.

---

## 6. Validation strategy

| Phase | Validation |
| --- | --- |
| **1** | Guard test added **and proven to fail** on an injected violation. No production change, so the existing suite must pass unchanged — that is the proof Phase 1 changed only documents and tests. |
| **2** | Full suite green; every service's `target` asserted against the canonical set; the network sub-kind verified present on each service that previously emitted it, so the collapse is shown not to lose information. |
| **3** | Full suite green; per-service tests for the exactly-one-selector rule and the conflict path; a group and a user sharing a name resolve to different targets; translation parity re-checked in both directions (every exception constant has a message, every service has an entry, field sets match). |
| **4** | Full suite green **with no allowlist**; an injected violation fails; a deliberately introduced non-canonical value in each of the four surfaces fails. Live read-only verification that a renamed response field is still populated and that the WAN event fix returns real events. |

Commands: `python -m ruff check .` · `python -m ruff format .` ·
`python -m mypy custom_components/firewalla_local` · `python -m pytest tests/ -v`

Baseline at planning time: **728 tests pass**, ruff check and format clean, mypy
clean across 46 files. The audit found **99 test assertions** and **6 documents**
referencing values this plan changes, which is the bulk of the work — the code
changes are small and wide rather than deep.

---

## 7. References

**The rule that already exists and was violated:**
- `docs/ARCHITECTURE.md` → *Lexicon standards* — the `Device` and `Host` entries and
  the critical rule `never use device for Firewalla endpoint inventory, naming
  fields, or selector behavior`. **This is the rule; the plan enforces it rather than
  inventing a new one.**
- `docs/ARCHITECTURE.md` → *Scoped identity* — added by the flow-reporting
  initiative; **states the kind as `device` and is wrong**; corrected in 1.2.
- `docs/DEVELOPMENT_STANDARDS.md` → *Lexicon standards* — the shorter house form,
  including the `host_name` / `dns_hostname` / `dhcp_name` separation and the
  user-facing identity rule.

**The surfaces audited:**
- `custom_components/firewalla_local/services.py` — all 34 schemas, every
  `FirewallaReportTarget`, `scope_kind` and `target_type` enum, the report
  serializers.
- `custom_components/firewalla_local/services.yaml` — 115 `host` against 59
  `device`; the field-name and description split that defines the register boundary.
- `custom_components/firewalla_local/translations/en.json` — 137 against 71; the
  service and field descriptions a user reads in the UI.
- `custom_components/firewalla_local/const.py` — `SERVICE_FIELD_*`, `ATTR_*`,
  `RULE_TARGET_TYPE_*`; the candidate home for the canonical vocabulary.
- `custom_components/firewalla_local/llm_tools_read.py` and `llm_tools_control.py` —
  tool parameters and descriptions; `llm_tools_common.py` — the shared `PROMPT`.
- `custom_components/firewalla_local/binary_sensor.py`, `sensor.py`,
  `device_tracker.py` — the entity attribute keys.
- `custom_components/firewalla_local/managers/integration_manager.py` — the WAN
  event filters and their supported sets, and the `_build_network_segment_view`
  network-kind pass-through.
- `custom_components/firewalla_local/api/` — the protocol boundary, which the plan
  explicitly does **not** re-vocabulary.

**Precedent used by this plan:**
- `tests/components/firewalla_local/test_llm_contract.py` — `_INTENTIONAL_OMISSIONS`,
  the allowlist-with-reasons pattern the guard test copies, and the AST import that
  shows static analysis is already used in tests.
- `tests/components/firewalla_local/test_llm_contract.py` —
  `test_reference_documents_every_registered_tool`, an example of a test that keeps a
  document and the code in step.
- `tests/components/firewalla_local/test_init.py` — pins the registered service set
  in two places; any service or field change must satisfy both.

**Prior initiative this finishes:**
- `plans/completed/FIREWALLA_LOCAL_FLOW_REPORTING_COMPLETED.md` — introduced
  `target.kind: "device"` and the *Scoped identity* section, both corrected here.
  Its §8 records the `user`/affiliated-tag remap as a deliberate identity/protocol
  separation, which remains correct and is **not** changed by this plan.

---

## 8. Phase 1 handoff to `Firewalla Builder`

**Target agent:** `Firewalla Builder`
**Authorizes:** **Phase 1 only** (steps 1.1–1.6). Phases 2–4 are handed off
individually after the previous phase is validated.
**Blockers:** none. Q1, Q2, Q3, Q4, Q5, Q7 and Q9 are settled with recommendations
above; Q6 is settled (service names do not change); Q8 is explicitly deferred to
Phase 3.2 with its check written down. If the owner rejects a recommendation, stop
and re-plan — Phase 1 states the rule, so changing it after Phase 1 means redoing it.

**The one rule for this phase:** **no production behaviour changes.** Phase 1 edits
two documents, adds one test file, and publishes one supporting note. If a step
appears to need a source change, that is a signal the phase boundary is wrong — stop
and report it, do not make the change.

**Branch:** continue on `feature/flow-reporting`. Nothing is pushed; the vocabulary
work builds on the flow-reporting commits and the suite baseline is 728 tests there.

Prerequisite reading, in order: `docs/ARCHITECTURE.md` → *Lexicon standards* (the
rule, including the critical rule), then → *Scoped identity* (the section being
corrected), then `docs/DEVELOPMENT_STANDARDS.md` → *Lexicon standards*, then
`tests/components/firewalla_local/test_llm_contract.py` → `_INTENTIONAL_OMISSIONS`
(the allowlist pattern the guard test copies).

**The one thing to get right:** the guard test's allowlist. It is the phase work list
for Phases 2–4 and it must name **every** current violation with a reason, or a later
phase will believe it is finished while the test still passes. Take the audit note in
1.4 as its source and make the two agree exactly.

Do not begin Phase 2 until Phase 1's guard test has been **observed failing** on an
injected violation and the suite passes unchanged.
