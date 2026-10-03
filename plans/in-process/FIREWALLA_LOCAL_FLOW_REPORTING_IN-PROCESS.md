# Flow Reporting Service — IN PROCESS

**Initiative:** Flow Reporting Service (`get_flow_report`)
**Branch:** `feature/flow-reporting`, off `main` (the rule-hit-data work is already on `main`)
**Depends on:** `2.5.0-beta.1` (rule hit data), issue #53 (stale rule switches) for one edge case only
**Status:** planning complete — ready for Phase 1 handoff, no implementation started

---

## 1. Initiative snapshot

The Firewalla app's flow report is served entirely from the local box, and it was
confirmed by packet capture on **2026-10-03**. It is **three queries over one data
set**: a windowed **rollup**, an **event log** (`flows`), and an **audit log**
(`auditLogs`). All three take `type: "tag" | "host"` and a target of the tag id or
the device MAC, so a group report and a device report are the same code path with a
different target.

Today the integration can surface **none** of it. The closest existing surfaces are
`get_network_segment_usage` (per-network `item=intf` windows) and
`get_time_usage_report` (per-user/app `item=appTimeUsage`), neither of which can
answer *"what did this device or group actually do, and what was blocked?"*.

This initiative adds **one service** — `get_flow_report` — that returns a
**summarized** view by default and raw rows on request, plus a read-only LLM tool
over the same normalized data. It is deliberately **one service, not three**: the
rollup, the event log and the audit log are filters and resolution levels over the
same flow data, and splitting them would duplicate target resolution, window
handling and serialization three ways.

The single hardest constraint is that **the box's limits are not ours to encode**.
The measured retention is ~24 hours and an out-of-range window is a protocol error
(code 500), but Firewalla can change both tomorrow. So retention is **documented and
reported, never hard-coded** (§3, Q2).

The second, and the one that shapes Phase 1, is that **this data family is not new
to the integration**. The `item=intf` payload already carries the same `flows`
families the rollup carries (`download`, `upload`, `appDetails`,
`categoryDetails`, plus per-host `conn` / `dns` / `dnsB` / `ipB` / `ipD` / `ntp`),
and `integration_manager.py` already normalizes them through five builders —
`_build_network_flow_rankings`, `_build_network_usage_buckets`,
`_build_network_activity_hosts`, `_build_network_hosts`, and
`_build_network_top_talkers`. Those builders already feed **entity attributes**
(`network_usage`, `top_talkers`) and the **network usage reports**
(`get_network_segment_report`, `get_network_segment_usage`).

So the flow report is mostly a question of **reusing that processing at a different
scope**, not writing new processing. Phase 1 exists to make that true before any
new consumer exists that could tilt toward a parallel path.

---

## 2. Scope and non-goals

### In scope

- One `get_flow_report` service with a summary default and an events mode.
- Target resolution that accepts **a device (MAC or name) or a group/user (name or
  id)** and resolves to `type=host` / `type=tag` internally, reusing the existing
  resolver and its ambiguity handling.
- Window handling: a 24-hour default, caller-overridable, with **no artificial cap**
  and a graceful, reported fallback when the box rejects a window.
- Pagination: a bounded default page, an explicit **all-available** mode, and an
  exposed cursor.
- `detail: summary` — aggregate totals, top destinations, top flows, blocked
  breakdown, and member ranking.
- `detail: events` — the block log, with the `pid` → rule join, and the audit log's
  `category` filter.
- A shared flow-processing core so the flow report and the existing usage paths
  (segment report, segment usage, `network_usage` / `top_talkers` attributes) use
  **one** implementation of row extraction, destination ranking, bucket
  aggregation, device attribution and window parsing — and one that does not box
  rows twice on the way through.
- A read-only LLM tool that returns the same data shape.
- Docs: `USER_GUIDE.md`, `MCP_TOOL_REFERENCE.md`, `REVERSE_ENGINEERING_WORKFLOW.md`.

### Non-goals

- **No new entities or sensors.** No coordinator polling of the flow endpoints.
- **No merge of `get_network_segment_usage` into this service.** Different scope
  (per-network vs per-target) and different source (`item=intf` vs the rollup).
  They share the window *shape* and must share the *parser*, not the service.
- **No `exclude` field exposed.** Its accepted values are unverified (§3, Q4).
- **No retention enforcement in code.** See Q2.
- No changes to rule switches or the rule hit data shipped in `2.5.0-beta.1`.

---

## 3. Open questions and external dependencies

Ten material questions, each with the recommendation I would act on. Nothing else is
open; if a question is not listed here it is already answered by capture evidence.

### Q1. Does the response ever auto-paginate to exhaustion?

**Why it matters.** `count` is a record count, not a time slice: 300 rows spanned
0.3h on a busy group, so a full day is a *lot* of rows and a lot of round trips
against the box. Auto-paging is the difference between one request and dozens.

**Recommendation.** Default to **one page**, expose the cursor, promise nothing
about completeness. Provide an explicit all-available mode that walks `nextTs` to
exhaustion. The **only** stop conditions are a wall-clock deadline and a
repeated-cursor loop check — never a row cap. When the deadline stops the walk,
return `truncated: true` plus the cursor, so a partial result is never mistaken for
a complete one.

### Q2. Do we hard-code the ~24-hour retention?

**Why it matters.** The measurement (24h → 175 rows, 26h → 0, out-of-range → code
500) is a snapshot of box behaviour. Encoding it as a constant means we silently
truncate user data the day Firewalla raises the limit.

**Recommendation.** **Do not encode it.** Default the window to 24 hours as a
*default*, then attempt whatever the caller asked for. On a window rejection, retry
once at a window known to work, return the window **actually served**, and raise a
`window_exceeded` warning naming the requested window. Put the observed limit in
docs, in the service field description, and in the tool description — nowhere in
logic. This satisfies "no artificial caps" while still never handing a user a bare
protocol error.

### Q3. Is `hosts` absent, or an empty list, on a device target?

**Why it matters.** Verified: a `host` request returns `hosts: []` while the same
target as a `tag` returns members. Returning an empty list reads as **"this group
has no members"**, which is a false statement.

**Recommendation.** Omit the section and list `member_ranking` in
`unavailable_sections`. Mirrors the existing segment-report rule that an absent
section is unambiguous and an empty placeholder is not.

### Q4. Should `exclude` be exposed?

**Why it matters.** It is present in every captured request as `[]`. Its accepted
values are unverified. A guessed filter value **silently removes data** with no
error.

**Recommendation.** Keep it internal, always `[]`, and not a service field. Note it
as an open protocol question. A caller filtering by guess is worse than a caller
filtering client-side.

### Q5. What happens when a blocked event's `pid` matches no rule?

**Why it matters.** `pid` covers 296/300 rows and joins back to `policyRules`. But a
rule can be deleted and re-created under a new id (issue #53), and dev-box rules are
recreated routinely. A naive join drops the row.

**Recommendation.** Emit the event with `rule_id` set and `rule_name` null, and
count it in `summary.unattributed_events`. Never drop the row: the block happened,
and an unattributed block is exactly the signal worth surfacing. This is the same
class of failure the stale-switch repair addresses, and it must not become a second
silent hole.

### Q6. Is the windowed total a duplicate of `get_network_segment_usage`?

**Why it matters.** The rollup carries `newLast24` / `last60` / `last30` /
`last12Months` — the *same* window keys as the `item=intf` payload. That looks like
duplication and invites a second parser.

**Recommendation.** Split by **source**, share by **shape**. The *service* stays
separate: different scope (per-target vs per-network), different source
(`item=intf` vs the tag/host rollup), different lifecycle (coordinator-cached vs
live). The *processing* must be shared, and this is the strongest version of the
finding: `item=intf` already yields the same `flows` families and the same per-host
counters the rollup does, so **the flow report should call the existing builders,
generalized from network scope to target scope** — not grow a fourth. Reuse the
window extractor for `newLast24` / `last60` / `last30` / `last12Months`, and state
the source in `provenance` so a consumer can tell the two apart.

### Q7. Live fetch, or cached?

**Recommendation.** Live, per call. The rollup is a single request and caching
reintroduces the staleness and coordinator coupling the service exists to avoid. If
the box proves slow in practice, add a short-TTL cache *behind the same manager
method* so no caller changes.

### Q8. Default detail, and default volume?

**Recommendation.** `detail: summary` by default, with **no event rows at all**
unless asked — a block-log dump as a default response would be unusable and would
put thousands of identity-bearing rows into a service response. Service default
`count: 300` (one page); the tool always asks for summary.

### Q9. How much identity does the summary expose by default?

**Why it matters.** Destination rows carry household members' domains and IPs, and
per-member ranking and event rows carry MACs and internal IPs. The repo already gates
identity-bearing host rows in the segment report behind an explicit include.

**Recommendation (owner-confirmed).** Gate identity **the same way the segment
report does — off by default, retrieved on request**. Default output is aggregates
plus top destinations; per-device attribution is reachable whenever a caller asks
for it, not withheld:

- `include: ["device_detail"]` adds `top_members` and the event `device` /
  `deviceIP` fields, at **both** detail levels.
- The gate is a **default, never a wall**. Anything identity-bearing must remain
  obtainable in one call; if a value can never be retrieved, that is a bug, not a
  privacy control.
- When the target is itself a single device, that device's own identity is the
  subject of the question and is returned without the flag.

Identity is therefore a **default-shape** decision, not a capability limit — the same
principle as the retention and page-size answers in the audit note.

### Q10. How do we know `audit: true` actually filtered?

**Why it matters.** `audit: true` is understood to mean "blocked only". If the box
ignores it under some condition, a filter that is silently a no-op is worse than no
filter, because the caller builds conclusions on it.

**Recommendation.** After a filtered fetch, check the returned rows carry
`ltype: audit`. If they do not, raise a `filter_not_applied` warning. It is one
cheap assertion that converts a silent wrong answer into a stated one.

---

## 4. Phase summary

| Phase | Name | Deliverable | Gate |
| --- | --- | --- | --- |
| **1** | Shared flow core | The existing `item=intf` flow processing (row reader, destination ranking, bucket aggregation, device attribution, window parsing) consolidated into one target-agnostic core, and the existing consumers migrated onto it. No new behaviour. | Existing tests pass unchanged; no behaviour diff; one pass over rows. |
| **2** | Protocol layer | Client methods for all three queries with window handling, pagination and fail-soft; typed raw-payload models. | Live read-only verification on the dev box; recorded in the RE doc. |
| **3** | Normalization | One view builder producing summary and events over the Phase 1 core, reusing target resolution. | Unit tests against a fixture built from the real 300-record capture. |
| **4** | Surface | Service, translations, LLM tool, docs, quality scale. | Full validation suite green; live end-to-end call. |

Phases are sequential. **Phase 1 is not optional, and it is not busywork.** The flow
report needs the *same* processing the integration already does for `item=intf` at a
different scope. Building it without first generalizing that processing would produce
a parallel implementation of row extraction, destination ranking, bucket aggregation
and device attribution — four more places for the two paths to disagree (see the audit
note).

---

## 5. Phase details

### Phase 1 — Shared flow core (no new behaviour)

Purpose: the flow report needs the processing the integration **already does** for
`item=intf`, at a different scope. Phase 1 generalizes that processing into one core
and moves the existing consumers onto it, so Phase 3 can reuse it instead of writing
a fourth implementation. Nothing here changes what any existing surface returns.

- [ ] **1.1 Inventory the existing flow-processing surface and freeze it.** Confirm
      the five builders, their consumers, and the duplicated inner steps from the
      audit note's table: `_build_network_flow_rankings` (destinations),
      `_build_network_usage_buckets` (app/category aggregation),
      `_build_network_activity_hosts` and `_build_network_hosts` (device
      attribution), `_build_network_top_talkers` (ranking),
      `_resolve_network_ranking_payload` (unwrapping). Name the consumers:
      `binary_sensor.py` `network_usage` / `top_talkers` attributes, and
      `services.py` `get_network_segment_report` / `get_network_segment_usage`.
      Agree the canonical home for each capability before moving anything.
- [ ] **1.2 Consolidate numeric coercion to one implementation.** Seven helpers
      across five modules, disagreeing on three real inputs: whether a `bool` is `1`
      or `None`, whether a `float` is accepted at all, and whether a string is
      stripped. Flow rows are **string-typed numbers** (`"count": "236214"`,
      `"port": ["443"]`), and they flow through these helpers today, so this is
      directly load-bearing. Canonical home `utils/` (it already holds
      `_normalized_int`); pick the **strictest** behaviour — reject `bool`, accept
      only exact numeric strings — and record every call site whose result changes as
      a deliberate finding rather than averaging the differences away.
- [ ] **1.3 Extract the one flow record reader.** Every flow row today is decoded by
      hand, and four of those steps are duplicated: device id from
      `device` / `mac` / `deviceMac` (**three** copies), the metric value from
      `<metric>` / `bytes` / `count` (**two** copies), the destination from
      `host` / `domain` plus `ip`, and payload unwrapping in
      `_resolve_network_ranking_payload` (`{flows: []}`, `download`, `upload`,
      `items`, `results`). Collapse into one reader that yields a normalized row, so
      a field-name variation is fixed once rather than in four places.
- [ ] **1.4 Make the aggregators target-agnostic.** Generalize, without changing
      their output shapes: destination ranking from `_build_network_flow_rankings`,
      bucket aggregation from `_build_network_usage_buckets`, device attribution from
      `_build_network_activity_hosts` + `_build_network_hosts`, top-device ranking
      from `_build_network_top_talkers` (keeping `_TOP_TALKER_LIMIT = 5` as a
      parameter default, not a second constant), and the window parser from
      `_extract_usage_window` for `newLast24` / `last60` / `last30` /
      `last12Months`. The flow rollup and the `item=intf` `flows` block are the
      **same family**, which is what makes this a generalization rather than an
      abstraction over nothing.
- [ ] **1.5 Make it one pass.** `_build_network_activity_hosts` builds a
      `dict[str, dict[str, object]]` and then walks it a second time with `cast()` on
      every field to build the dataclasses — double boxing per row. With `count:
      2000` pages spanning ~5.7h on a busy target, and four families per page, that
      is the processing cost the owner flagged. Accumulate into the final dataclass
      (or tuples) in a single pass, and record a before/after measurement on a
      2000-row page so the improvement is evidenced rather than asserted. Do not
      trade correctness for it: keep the deterministic sort keys identical.
- [ ] **1.6 Migrate the existing consumers and prove no behaviour change.** Point
      `binary_sensor.py`'s `network_usage` / `top_talkers` and `services.py`'s
      segment report and segment usage at the Phase 1 core. Run the full suite;
      expect **no** snapshot or assertion change. A changed snapshot is a finding,
      not a fix — stop and report it rather than updating it.
- [ ] **1.7 Land the models, constants and the flow manager.** Add
      `FirewallaFlowDestination`, `FirewallaFlowEvent`, `FirewallaFlowMember`,
      `FirewallaFlowRollup`, `FirewallaFlowReportView` to `models.py` (no Home
      Assistant imports), the service/attribute/translation keys to `const.py`, and
      put the flow *view building* in a new `managers/flow_manager.py`.
      `integration_manager.py` is already the largest module in the repo and holds
      four of the seven coercers; the shared core goes to `utils/` (1.2–1.5) and the
      flow-only view building goes in the new manager.

### Phase 2 — Protocol layer

- [ ] **2.1 Add `async_get_flow_rollup_payload`.** `item` = `tag` or `host`,
      `apiVer: 2`, `audit: true`, `start`, `end`, `hourblock`, targeting the tag id
      or MAC. Returns the raw dict.
- [ ] **2.2 Add `async_get_flow_events_payload`.** `item: "flows"`, `type`, `count`,
      `ts`, `exclude: []`. Returns `{count, flows, nextTs}`-shaped data plus the
      reported `count`.
- [ ] **2.3 Add `async_get_flow_audit_payload`.** `item: "auditLogs"`, same as 2.2
      plus optional `category` and `ets`. Only add `category` if the service exposes
      it (Q4 keeps `exclude` internal; `category` is confirmed, so expose it).
- [ ] **2.4 Implement window resolution with no encoded cap.** Default 24h; attempt
      the requested window; on rejection retry once at a known-good window; return
      the window actually served plus a `window_exceeded` indicator. Record the
      observed ~24h limit as a docstring fact, not a constant. **Do not conflate
      `hourblock` (granularity) with retention** — an earlier probe misattributed a
      failure to `hourblock` when the cause was an out-of-range `start`.
- [ ] **2.5 Implement pagination with a deadline and a loop check.** Walk `nextTs`
      only in all-available mode. Stop on deadline, on a repeated `nextTs`, or on an
      empty page. **Dedupe across the page boundary** on a stable tuple
      (`ts`, `device`, `pid`, `domain` or `ip`, `port`) because `ts` bounds are
      inclusive and adjacent pages overlap. Expose the cursor as **`next_cursor`**,
      carrying `ts` verbatim and documented as **opaque**, so the cursor's meaning can
      change later without a breaking change.
- [ ] **2.6 Verify read-only against the dev box** for one tag and one host: window
      default and override, one page, all-available on a small target, a
      deliberately over-wide window (expect the fallback and warning, not a raise),
      and a `category`-filtered audit read. Record every result in
      `REVERSE_ENGINEERING_WORKFLOW.md`.
- [ ] **2.7 Fail soft.** A shape change or a rejected request returns *unavailable*
      rather than raising, matching the existing `item=intf` posture toward
      OpenVPN's 500. The service reports what it could not read.

### Phase 3 — Normalization

- [ ] **3.1 Reuse target resolution.** Accept a device (MAC or name) or a
      group/user (name or id); resolve to `type` + target through the existing
      resolver. Ambiguity raises the same class of error as
      `time_usage_report_scope_ambiguous`; not found raises the same class as
      `time_usage_report_scope_not_found`. **Do not add a parallel name→id lookup.**
- [ ] **3.2 Build the summary from the rollup using the Phase 1 core.** Totals from
      the shared window extractor (1.4); destination rows from the shared
      destination ranking (1.4) — grouped by `host`, which is the subdomain-granular
      row and therefore the app's "top flows", with the registrable grouping derived
      from the **same rows** for "top destinations". These are two presentations of
      one row set, not two fetches. **The rollup's `flows` families are the same
      shape as `item=intf`'s, so this step must consume the shared builders and add
      none.**
- [ ] **3.3 Add the blocked breakdown.** `dnsB`, `ipB:in`, `ipB:out`,
      `local:ipB:*` from the rollup, reported as separate directions because in/out
      are different questions.
- [ ] **3.4 Add member ranking via the shared ranker (1.4)**, mark
      `member_ranking` unavailable on device targets (Q3), and implement Q9's
      confirmed gate: per-device attribution (`top_members`, event `device` /
      `deviceIP`) is **absent by default** and returned when
      `include: ["device_detail"]` is set, at both detail levels. A single-device
      target returns its own identity without the flag. Ensure the gated values are
      always reachable — never permanently withheld.
- [ ] **3.5 Build the events view.** Normalize each record, join `pid` → rule via
      the existing rule index, and apply Q5's rule: unmatched `pid` keeps the row
      with `rule_name: null` and increments `unattributed_events`. Apply Q10's
      `ltype` assertion. Keep the partial coverage visible — `domain` is 283/300, but
      `category` is 91 and `app` is 30, so the summary must not imply completeness.
      Report the box's own `count` alongside rows returned (`rows_returned` vs
      `rows_available`), so a bounded read is never read as a quiet target.
- [ ] **3.6 Emit the shared report envelope.** `config_entry_id`, `target`, `query`,
      `time_basis` (`_serialize_report_time_basis`), `summary`, sections,
      `metadata` (`_serialize_report_metadata` with `applied`, `warnings`,
      `unavailable_sections`, `provenance`). State the source (`item=tag|host` and
      `item=flows|auditLogs`) in `provenance` so it cannot be confused with the
      `item=intf` usage service. Never build a bespoke envelope. **The two views
      have different time semantics** — the rollup is a windowed aggregate, the event
      log is a reverse walk from a timestamp — so `time_basis.kind` must distinguish
      them (`window` vs `event_log`), or `is_partial` becomes meaningless.
- [ ] **3.7 Tests against the real capture.** Build the fixture from the 300
      captured records and the live rollup, and cover: summary shape; events with
      attributed and unattributed rules; member ranking absent on a device target;
      window fallback + warning; pagination dedupe across a boundary; deadline
      truncation sets `truncated`; `rows_returned` vs `rows_available`; and **both
      sides of the Q9 gate** — per-device fields absent by default and present with
      `include: ["device_detail"]` — so the gate cannot silently become a wall.
      **Also fabricate the malformed payloads** — a wrong shape, a missing
      `flows` key, a non-dict rollup — so the fail-soft path (2.7) is covered by a
      test rather than by prose. Snapshot the shapes.

### Phase 4 — Surface

- [ ] **4.1 Service schema and handler** in `services.py`, registered in
      `_SERVICE_REGISTRATIONS` as a **read-only, admin** service using
      `async_register_admin_service` — the payload is household-wide traffic and
      identity data.
- [ ] **4.2 Field descriptions** in `services.yaml`, with the observed retention
      limit stated in prose on the window field.
- [ ] **4.3 Translations.** `strings.json` + regenerate
      `translations/en.json`; exception keys for scope ambiguous / not found / flow
      report failed, following the existing naming.
- [ ] **4.4 LLM tool** in `llm_tools_read.py` at the read-only tier: summary-first
      with the window and its actual served span stated, and an explicit sentence
      that the data is a recent window rather than history. Update
      `llm_tools_common.py` if the target parameter is shared.
- [ ] **4.5 Docs.** `USER_GUIDE.md` (how to read the report, what the window really
      means, what is withheld and why), `MCP_TOOL_REFERENCE.md`, and
      `REVERSE_ENGINEERING_WORKFLOW.md` (mark the answered open questions:
      retention, page size, window validity).
- [ ] **4.6 Quality scale.** Add `docs-actions` coverage and confirm no rule
      regresses; `action-exceptions` must cover the new exception keys.
- [ ] **4.7 Live end-to-end** run against the dev box for one group and one device,
      both detail levels, and record the transcript in the plan's completion notes.

---

## 6. Validation strategy

| Phase | Validation |
| --- | --- |
| **1** | Full suite unchanged; `ruff check`, `ruff format`, `mypy` clean. Any snapshot diff is a finding. Plus a **single-pass measurement**: row throughput on a 2000-row page across four families, before and after 1.5. |
| **2** | Read-only live probes on the dev box, one tag + one host; results recorded in the RE doc. No writes. |
| **3** | Unit tests over the capture-derived fixture, including the adversarial cases (unmatched `pid`, boundary dedupe, over-wide window, device-target member ranking, both sides of the Q9 gate). A review check that Phase 3 **added no new flow builder**. |
| **4** | Full suite; live end-to-end for both detail levels; `python3 -m script.hassfest` if manifest or translation metadata moves. |

Commands: `python -m ruff check .` · `python -m ruff format .` ·
`python -m mypy custom_components/firewalla_local` · `python -m pytest tests/ -v`

---

## 7. References

- `docs/REVERSE_ENGINEERING_WORKFLOW.md` → *Flow reporting and the local block log*
  (the three queries, field coverage, the `pid` join) and *Limits: retention, page
  size, and window validity*.
- `plans/in-process/FIREWALLA_LOCAL_FLOW_REPORTING_SUP_CONSUMER_AUDIT.md` — the
  existing-consumer audit behind Phase 1, including the gaps, traps and opportunities
  review of this plan.
- `custom_components/firewalla_local/api/client.py` —
  `_async_send_local_message_data`, `async_get_network_interface_payload`.
- `custom_components/firewalla_local/managers/integration_manager.py` — the five
  existing flow builders Phase 1 generalizes: `_build_network_flow_rankings`,
  `_build_network_usage_buckets`, `_build_network_activity_hosts`,
  `_build_network_hosts`, `_build_network_top_talkers`,
  `_resolve_network_ranking_payload`, `_extract_usage_window`, `_TOP_TALKER_LIMIT`.
- `custom_components/firewalla_local/binary_sensor.py` — `_serialize_usage`,
  `_serialize_usage_window`, `_serialize_top_talkers`; the entity-attribute
  consumers Phase 1.6 migrates.
- `custom_components/firewalla_local/services.py` — `_serialize_network_host_ranking`,
  `_serialize_network_usage_bucket`, `_serialize_network_usage_metric`; the report
  consumers Phase 1.6 migrates.
- `custom_components/firewalla_local/utils/network.py` — `_normalized_int`, one of
  the seven coercers Phase 1.2 consolidates.
- `custom_components/firewalla_local/services.py` — `_serialize_report_time_basis`,
  `_serialize_report_metadata`, `_normalize_report_include`, and
  `_serialize_network_segment_report` as the envelope precedent.
- Issue #53 — stale rule switches (the Q5 edge case).
- Captures: `.tmp/firewalla_capture_20261003-135000_flow-reporting.pcap`,
  `.tmp/firewalla_capture_20261003-132919_block-reporting.pcap`;
  pulls in `.artifacts/flow_reporting/` and `.artifacts/block_reporting/`.

---

## 8. Phase 1 handoff to `Firewalla Builder`

**Target agent:** `Firewalla Builder`
**Authorizes:** **Phase 1 only** (steps 1.1–1.7). Phases 2–4 are handed off
individually after the previous phase is validated.
**Blockers:** none. Q9 was confirmed by the owner on 2026-10-03 (gated by default,
always retrievable) and is folded into Phase 3.4.

**Branch.** The rule-hit-data work is on `main`, so the flow branch is created from
`main`, not from `feature/rule-hit-data`:

```bash
git checkout main && git pull
git checkout -b feature/flow-reporting
```

Prerequisite reading, in order: the audit note, then
`docs/REVERSE_ENGINEERING_WORKFLOW.md` → *Flow reporting and the local block log*.

**The one rule for this phase:** no new flow processing. Phase 1 generalizes what
`integration_manager.py` already does for `item=intf` and moves the existing
consumers onto it. If a step appears to need a new builder, that is a signal the
generalization is incomplete — stop and report it, do not add the builder.

Do not begin Phase 2 until Phase 1's suite passes with **no changed expectations**.
