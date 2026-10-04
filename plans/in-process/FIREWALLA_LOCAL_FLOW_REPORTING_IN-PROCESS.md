# Flow Reporting Service — IN PROCESS

**Initiative:** Flow Reporting Service (`get_flow_report`)
**Branch:** `feature/flow-reporting`, off `main` (the rule-hit-data work is already on `main`)
**Depends on:** `2.5.0-beta.1` (rule hit data), issue #53 (stale rule switches) for one edge case only
**Status:** planning complete — ready for Phase 1 handoff, no implementation started

---

## 1. Initiative snapshot

The Firewalla app's flow report is served entirely from the local box, and it was
confirmed by packet capture on **2026-10-03**. It is **three queries over one data
set**: a windowed **rollup** (`tag` / `host`), the **flow log** (`item: "flows"`),
and the **block log** (`item: "auditLogs"`). All three take
`type: "tag" | "host"` and a target of the tag id or the device MAC, so a group
report and a device report are the same code path with a different target.

Today the integration can surface **none** of it. The closest existing surfaces are
`get_network_segment_usage` (per-network `item=intf` windows) and
`get_time_usage_report` (per-user/app `item=appTimeUsage`), neither of which can
answer *"what did this device or group actually do, and what was blocked?"*.

This initiative adds **one service** — `get_flow_report` — that returns a
**summarized** view by default and raw records on request, plus a read-only LLM tool
over the same normalized data. It is deliberately **one service, not three**: the
rollup, the flow log and the block log are filters and resolution levels over the
same flow data, and splitting them would duplicate target resolution, window
handling and serialization three ways.

The single hardest constraint is that **the box validates almost nothing, and
clamps or ignores what it does not like**. A 168-hour window is served as 24 hours
with no error; a 1-year-old `start`, a `start` after `end` and a negative `count`
are all accepted. So the box's limits are **documented and reported, never encoded**,
and every constraint must be enforced on our side because nothing will be rejected
for us (§3, Q1 and Q2).

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

- One `get_flow_report` service with a summary default and a records mode.
- Target resolution that accepts **a device (MAC or name) or a group/user (name or
  id)** and resolves to `type=host` / `type=tag` internally, reusing the existing
  resolver and its ambiguity handling.
- Window handling: a `DEFAULT_FLOW_REPORT_WINDOW_HOURS` (24) default, caller
  overridable, with **no artificial cap** — the window actually served is read back
  from the response and reported, because the box silently shortens a wider request
  instead of rejecting it.
- Validation on our side, since the box performs none: a bounded positive `count`,
  `hourblock` clamped to at least 1, and no falsy `ts`.
- Pagination: a bounded default page, an explicit **all-available** mode, and an
  exposed cursor.
- `detail: summary` — aggregate totals, top destinations, top flows, blocked
  breakdown, and member ranking.
- `detail: records` — the flow log and the block log, with the `pid` → rule join,
  the `category` filter the block log supports, and byte/duration detail on regular
  flows.
- Direction as a typed field derived from the family name, **not** from `fd`
  (§3, Q4c).
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

**Why it matters.** One busy group held **6,956 records** in its 24-hour window and
the box caps a positive `count` at **5,000**, so a complete read is at least two
calls. Auto-paging is the difference between one request and dozens.

**Recommendation.** Default to **one page**, expose the cursor, promise nothing
about completeness. Provide an explicit all-available mode that walks `nextTs` to
exhaustion. The **only** stop conditions are a wall-clock deadline and a
non-advancing-cursor loop check — never a row cap. When the deadline stops the walk,
return `truncated: true` plus the cursor, so a partial result is never mistaken for
a complete one.

Pages are cheap, which makes this easy to justify: 2,000 records took **0.36s**, so
a two-page day is about a second. The 5,000 cap is a completeness problem, not a
performance one.

### Q2. Do we hard-code the ~24-hour retention?

**Why it matters.** The measurement (24h → 175 rows, 26h → 0) is a snapshot of box
behaviour. Encoding it as a constant means we silently truncate user data the day
Firewalla raises the limit.

**Recommendation (revised — the original design assumed a rejection path that does
not exist).** The default window becomes the constant
`DEFAULT_FLOW_REPORT_WINDOW_HOURS = 24`, mirroring the box's own default, so it can
be changed in one place. **Do not encode a maximum, and do not write a fallback
path**: a probe found the box **rejects nothing** — a 1-year-old `start`, `start`
after `end`, a future `end`, `hourblock: 999` and a negative `count` all return code
200. There is no rejection to catch, and a retry would be dead code.

**The real risk is the opposite of truncation-by-error: the box silently clamps.**
The rollup served exactly **24.00h** for requests of 1h, 24h, 25h, 48h *and* 168h —
identical responses, no error, no indication. So the window must be **read from the
response** (row `begin`/`end`) and reported as the window actually served. A caller
asking for 48 hours and being told 48 hours would be describing data they do not
have, which is the same class of defect as the `host_count` bug the segment report
already guards against.

**Because the box validates nothing, we must.** Client-side validation is required
rather than defensive:
- a non-positive `count` **returns the whole retained window** (~6,956 rows), the
  reverse of the intuitive reading, so it is never forwarded unvalidated
- `hourblock: 0` returns zero rows silently, so it is clamped to at least 1
- a falsy `ts` is treated as absent by the box, so `0` is never sent
- `count` at or below the low single digits is undefined (`count: 1` returned 0
  rows while `count: 0` returned 100), so a sane minimum applies


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

### Q4b. Which query is the block log?

**Why it matters.** The plan originally called `item: "flows"` *"the block log"* and
treated `audit: true` as a blocked-only filter. **Both are wrong**, and the error
was structural rather than cosmetic: a report claiming to show blocks would have
been ~91% regular traffic.

Measured on the same tag, `count: 300`:

| Query | `ltype` breakdown |
| --- | --- |
| `item: "flows"`, `audit: true` | **26 `audit` + 274 `flow`** |
| `item: "flows"`, `audit: false` | **300 `flow`** |
| `item: "auditLogs"`, `audit: true` | **300 `audit`** |

**Recommendation.** `auditLogs` is the blocked-only query; `flows` is the flow log;
`audit: true` *adds* blocked records rather than filtering to them. Discriminate on
`ltype`, and never on the request flag. Phase 2 gets a client method per query, and
Phase 3 selects the family per detail level rather than reusing one method with a
flag. Documentation must call `flows` the **flow log** everywhere.

### Q4c. What determines direction?

**Why it matters.** `fd` looks like the direction field and is not usable as one:
it is `"in"` on all 199 `download` rows **and** all 199 `upload` rows, and 100
endpoints appear in both families with the same `fd` and different totals. A report
built on `fd` would rank one direction as the other.

**Recommendation.** Take direction from the **family name** — `download` / `upload`,
`local:download` / `local:upload`, and the `:in` / `:out` suffix on blocked
families. Do not read `fd` for direction at all. Its actual meaning is unresolved
and deliberately not depended on, so no future clarification can invalidate a
report.

### Q5. What happens when a blocked event's `pid` matches no rule?

**Why it matters.** `pid` is present on **every** blocked record (300/300 measured)
and joins back to `policyRules`. But a rule can be deleted and re-created under a new
id (issue #53), and dev-box rules are recreated routinely. A naive join drops the row.

**Recommendation.** Emit the record with `rule_id` set and `rule_name` null, and
count it in `summary.unattributed_blocks`. Never drop the row: the block happened,
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

**Recommendation.** `detail: summary` by default, with **no records at all**
unless asked — a block-log dump as a default response would be unusable and would
put thousands of identity-bearing rows into a service response. Service default
`count: 300` (one page); the tool always asks for summary.

### Q9. How much identity does the summary expose by default?

**Why it matters.** Destination rows carry household members' domains and IPs, and
per-member ranking and records carry MACs and internal IPs. The repo already gates
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

**Why it matters.** `audit: true` was understood to mean "blocked only". If the box
ignored it under some condition, a filter that is silently a no-op is worse than no
filter, because the caller builds conclusions on it.

**Recommendation (revised — the original version of this question was based on a
wrong premise).** Q4b answers it: `audit: true` does not filter to blocked records,
it *adds* them, so there is nothing to verify. The correct check is the inverse:
after a blocked-only read, assert the rows are `ltype: "audit"`, because
`auditLogs` is what produces them. A second assertion is worth having — that a
*regular* read (`flows`, `audit: false`) contains no `ltype: "audit"` rows, which
is what would catch the box changing the flag's meaning in the other direction.

### Q11. Is the flow report an admin service?

**Why it matters.** The plan said admin, on the grounds that flow data is
household-wide. But the **LLM read tools only ever call non-admin services**, so an
admin registration would put the Phase 4 tool outside the surface it belongs to.

**Measured across all 33 registrations:**

| | Count |
| --- | --- |
| Total services | 33 |
| Admin | 20 |
| Non-admin | 13 |
| Admin **and** a read (`SERVICE_GET_*`) | **1** — `get_runtime_inventory` |
| Non-admin reads | 12 |

Every non-admin service bar one is a read; the exception is `sync_runtime`, a
refresh trigger. The single admin read is `get_runtime_inventory`, which returns the
entire unredacted runtime inventory as a bulk diagnostic dump — a different category
from a scoped, summarized report.

The decisive evidence is the tool surface: **all 13 tools in `llm_tools_read.py`
call non-admin services, and none calls the one admin read.** All 25 tools in
`llm_tools_control.py` call admin services. So the flag tracks *mutation and bulk
export*, and the read-tool surface structurally depends on reads being non-admin.

**Recommendation.** `admin=False`, matching every other query service. The
sensitivity argument does not distinguish it: per-user app usage is already
non-admin, and flow destinations are comparable.

### Q12. Should target resolution be shared with the existing services?

**Why it matters.** Resolution for a device or group/user already exists, and the
flow service needs the same thing.

**Finding — the duplication already exists, and it is three-way.** Independent of
this initiative there are three resolvers, ~322 lines in total:

| Resolver | Lines | Selectors | Returns |
| --- | --- | --- | --- |
| `_resolve_requested_host` | 86 | `host_id` / `host_mac` / `host_name` | `FirewallaHostRuntime` |
| `_resolve_membership_target` | 94 | group and user name/id | `FirewallaGroupRuntime` |
| `_resolve_usage_history_target` | 142 | one free-text device/user/group | `FirewallaUsageHistoryTarget` |

All three implement the same algorithm: exact id match, then casefolded name
match, then exactly-one → return / more-than-one → ambiguous / none → not found.

**But one shared resolver is the wrong shape**, for three reasons:

1. **The name fields matched differ, and the difference looks deliberate.**
   `_resolve_requested_host` matches five fields (`host_name`, `dns_hostname`,
   `dhcp_name`, `dns_fqdn`, watched choice); the usage resolver matches two
   (`host_name`, watched choice). `llm_tools_read.py` documents the intent —
   *"`host_name` is the primary human-facing label and the one to match a user's
   words against... `dhcp_name` is device-supplied and unreliable — never use it to
   identify a device."* So the **narrower** matcher follows the documented rule, and
   the host resolver's inclusion of `dhcp_name` is the questionable one.
2. **Error content differs by intent.** The host and membership resolvers name the
   matches in the ambiguous error so the caller can choose; the usage one does not.
   That is a UX difference, not an accident to erase.
3. **The errors are translation-key `ServiceValidationError`s**, which
   `ARCHITECTURE.md` assigns to the **service layer** ("mapping failures into
   translation-ready Home Assistant exceptions"). A single resolver would need
   injected keys, match-list formatting and a per-type projection — a
   many-parameter function, which is an abstraction over three real differences.

**Recommendation.** Extract the **matching core**, not a unified resolver: one
helper that takes candidates and a selector and returns `(exact, name_matches)`,
with no exceptions and no translation keys. Each caller keeps its own error mapping,
match-list formatting and return type. That removes the repeated algorithm without
flattening three legitimately different contracts.

**Two findings to report, not fix silently:**

- The same device resolves through `get_hosts` by its **DHCP name** but not through
  `get_time_usage_report`. Real inconsistency; needs a decision about which matcher
  is correct, not a refactor.
- It is **pre-existing** duplication. Worth doing, but it is not flow-reporting
  work, and it should not be presented as such.

### Q13. Phase 2 corrections found while writing the plan into code

Four items the plan had wrong, all verified against the code rather than assumed.

**1. `FlowManager` must subclass `FirewallaBaseManager`.** The plan implied a
client-only constructor. Every manager takes `(coordinator, entry, client)`, so the
flow manager matches. Adding it therefore touches four files — `managers/flow_manager.py`,
`managers/__init__.py`, `coordinator.py` (attribute, `attach_managers` parameter,
`FirewallaRuntimeData` field) and `__init__.py` (instantiate, pass through).

**2. Fail-soft belongs in the manager, not the client.** The client **raises**
`FirewallaProtocolError` on a bad shape and every existing method follows that
pattern. `FlowManager` catches and returns *unavailable*, exactly as
`async_refresh_network_usage` keeps its previous cache on a per-network failure.

**3. The dedupe key is unsafe on regular records.** `(ts, device, pid, domain, port)`
was written against blocked records, where `pid` exists. On a regular record `pid` is
absent, so one device opening many connections to the same host in the same second
collides and silently under-counts. **Dedupe on the row's own serialized content**,
which is exact and needs no tuning.

**4. `nextTs` must not be rounded.** It is a float (`1791060537.785`) and passing it
back is how pagination walks; rounding to an int could skip records. The cursor
carries it verbatim and is only ever tested for equality or non-advance.

### Q14. What would this look like if we built it today, with the published models?

**Why it matters.** Much of the host/rule model was derived by reverse engineering
before Firewalla's published Device and Rule models were found. Those models
corroborate most of it but correct a few readings, and correcting them now is
cheaper than after the flow report is built on top.

**The published model in one line:** a **Device** is the atomic unit (id prefixed by
type, defaulting to MAC), and it is targeted through a **Scope** of
`{type, value}` where `type` ∈ `device` / `group` / `user` / `network`.

**Where we already match:**

| Published | Ours |
| --- | --- |
| `scope.type` ∈ device/group/user/network | `scope_kind` — **we support three of four** |
| Device `group` is singular | confirmed one-membership-per-device |
| Device ID is prefixed by type | we handle `wg_peer:` / `awg_peer:`; `if:` exists but is unmatched |
| Rule `direction` | our `traffic_direction` |
| Rule `hit: {count, lastHitTs}` | our `hit_count` / `last_hit` |
| `dnsOnly` defaults true on block rules for category/app/targetlist/domain | explains `dnsmasq_only` + `useBf` |
| `protocol` ∈ tcp/udp | our rule `protocol` |

**Three readings to correct, all cheap now and expensive later:**

1. **`device_mac` is a misnomer.** It holds a device id, and **3 of 48 live rule
   hits (6%)** are `wg_peer:` / `awg_peer:` / `if:`. The vendor calls it a **Device
   ID**. Rename to `device_id` in the model and the attributes.
2. **`network` scope is missing** from `scope_kind`, which accepts
   `device` / `group` / `user`. Add it, and **document the limitation honestly**:
   the local flow queries take `type: tag|host` only, so a network-scoped *flow*
   report is not expressible even though a network-scoped *rule* is.
3. **`category` is two different closed sets.** Flow/device `category` is
   12 values; rule **target** `category` is 11, and neither contains the other
   (`edu` / `ad` / `intel` / `private` are flow-only, `drugs` / `violence` are
   rule-only). Validating one against the other would reject valid data.

**The one structural rework worth doing in this initiative: unify the flow record.**

`lastHitFlow` is **not** a reduced summary — it is a **full flow record**, the same
shape a flow-log page returns. Evidence: `ltype`, `type`, `count`, `intf`,
`protocol`, `port`, `device`, `deviceIP` and `ts` are present on **all 48** records,
and the optional fields appear in the same proportions as on a flow page.

`FirewallaRuleHit` was hand-built before that was known and reads **10 of the record's
35 fields**, dropping among others `download` / `upload` / `duration` (21/48),
`count` (48/48), `ltype` (48/48), `dstMac` (21/48), `country` (19/48), `pid`
(27/48) and the interface joins.

So there should be **one flow-record model and one reader**, consumed by both the
rule-hit surface and the flow report. Doing this now:
- removes a second hand-built subset instead of adding a third,
- recovers the byte, duration and attribution fields a rule report wants,
- and makes the `device_id` rename a single change.

Doing the flow report first would mean building on the subset and redoing both.

**Recommended, bounded rework (folded into Phase 3, not a new initiative):**

| # | Change | Cost |
| --- | --- | --- |
| R1 | Rename `device_mac` → `device_id` in the hit model and attributes | small |
| R2 | Replace `FirewallaRuleHit` with the shared flow-record model; keep `build_rule_hit_attributes` as the attribute projector | small–medium |
| R3 | Surface the recovered `download` / `upload` / `duration` / `count` / `ltype` on rule hits | small |
| R4 | Add `network` to `scope_kind`; document that flows cannot be network-scoped | small |
| R5 | Split the `category` sets — flow (12) and rule-target (11) — in constants | small |
| R6 | Extract the shared matching core (Q12) | medium |

**Explicitly out of scope:** the `dhcp_name` matcher inconsistency, the
`statsResetTs` field, `targetlist` / `remotePort` as distinct rule target types, and
the `timeUsage` shape divergence. All recorded, none needed for the flow report.


---

## 4. Phase summary

| Phase | Name | Deliverable | Gate |
| --- | --- | --- | --- |
| **1** | Shared flow core | **COMPLETE** — one numeric-coercion policy, one shared flow-row reader, single-pass host accumulation, one usage-window projection, plus enforced `utils/` and `api/` purity tests. No new behaviour. | 560 tests pass (37 new); no existing assertion or snapshot changed. |
| **2** | Protocol layer | `managers/flow_manager.py` and client methods for all three queries, with window handling, pagination and fail-soft; typed raw-payload models. | Live read-only verification on the dev box; recorded in the RE doc. |
| **3** | Normalization | One view builder producing the summary and both record families over the Phase 1 core, reusing target resolution; flow models land here with their first caller. | Unit tests against a fixture built from the real 300-record capture. |
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

**COMPLETE — executed 2026-10-03 on `feature/flow-reporting`.** Validation: 601
tests pass (76 new), `ruff check` and `ruff format` clean, `mypy` clean across 43
files. No existing assertion or snapshot was modified.

| Commit | Step | Result |
| --- | --- | --- |
| `a468824` | 1.2 | `utils/values.py`; seven integer coercers → one policy, four identical string coercers → one |
| `66d1214` | 1.3–1.5 | `utils/flow.py`; five row-reading duplicates → one reader, single-pass accumulation |
| `77225a8` | 1.6 | `helpers/usage_report.py`; duplicate usage serializers → one projection |
| `d8705f9` | 1.7 | boundary tests enforcing `utils/` and `api/` purity |
| (this commit) | 1.8–1.10 | six boolean coercers → one union policy; `metric_ranking_sort_key`; two further coercers consolidated |

- [x] **1.1 Inventory the existing flow-processing surface and freeze it.** Confirmed
      the five builders and their consumers. Two corrections to the audit note: the
      device-id resolution (`device` / `mac` / `deviceMac`) appears **five** times,
      not three, and the integer-helper count was understated — it is seven integer
      helpers plus six boolean helpers plus two ad-hoc numeric coercers.
- [x] **1.2 Consolidate numeric coercion to one implementation.** Done. Two policies
      in `utils/values.py`: `normalized_int` and `normalized_number`, plus
      `normalized_float` and `normalized_string`. **Approach changed from the plan's
      "strictest behaviour"** to behaviour-preserving, because the phase gate
      requires no behavioural diff and the strictest reading was not
      behaviour-preserving (see the deviation note below).
- [x] **1.3 Extract the one flow record reader.** Done. `flow_row_host_id`,
      `flow_row_metric_value`, `flow_row_remote_host`, `flow_row_remote_ip`, and
      `iter_flow_rows`. `_resolve_network_ranking_payload` deleted.
- [x] **1.4 Make the aggregators target-agnostic.** Done, in the narrower form the
      architecture allows: the *row reading* became shared and pure, while the
      *view shaping* stayed with the owning manager. The two byte-for-byte identical
      per-host sort keys collapsed into `host_traffic_sort_key`.
- [x] **1.5 Make the activity build one pass.** Done — `dict[str, dict[str, object]]`
      plus a `cast()`-per-field second walk replaced by a typed `FlowHostActivity`
      accumulator shaped once. **The before/after measurement was dropped** by owner
      decision as one-off activity.
- [x] **1.6 Share the usage-window serializer.** Done. Two exact duplicate
      serializer pairs (entity + services) collapsed into
      `helpers/usage_report.py`.
- [x] **1.7 (reduced) Boundary tests.** `ARCHITECTURE.md` calls for a check that
      `utils/` imports no Home Assistant; the suite had three boundary tests and
      none was about imports. Added, and both `utils/` and `api/` pass. The unused
      flow models were **deferred to Phase 3** and `managers/flow_manager.py` to
      **Phase 2**, where each has a real owner and caller.
- [x] **1.8 Consolidate boolean coercion.** Done. **Six** boolean helpers across
      five modules collapsed onto `normalized_bool`, which accepts all four
      encodings the box uses (`bool`, `0`/`1`, `"1"`/`"0"`, `"true"`/`"false"`) and
      **explicitly declines the empty string**. See the deviation note and
      *Phase 1 findings* below — this closed a real trap on
      `autoDeleteWhenExpires` and preserved the correct `useBf` behaviour.
- [x] **1.9 Fix the ranking sort-key casefold.** Done. The top-download and
      top-upload lists ordered names by codepoint while the other two flow keys
      folded case, so the same equal-valued destination pair could order
      differently between two lists. `metric_ranking_sort_key` now matches, and the
      three distinct keys are documented in `utils/flow.py` with why their primary
      keys legitimately differ.
- [x] **1.10 Consolidate the two remaining ad-hoc coercers found in review.**
      `client._alarm_count` used a bare `isinstance` integer test, which would
      silently report `0` if the box ever sent a count as a string — as it does for
      several other counts. `binary_sensor._normalized_port_speed` was a sixth
      numeric parser. Both now delegate.


#### Deviations from the plan as written

1. **1.2 is behaviour-preserving, not strictest-behaviour.** Pick-one-strictest
   could not satisfy the phase's own "no behaviour diff" gate: three coercers read
   `True` as `1` and one accepted `"12.5"` as `12`. Two narrowings were still made
   and are documented at the delegating call site — `True` now reads as absent
   rather than `1`, and a fractional string is no longer truncated. Both are the
   safer failure for a measurement. 523 pre-existing tests pass unchanged.
2. **1.7's flow models deferred to Phase 3.** `FirewallaFlowDestination`,
   `FirewallaFlowEvent`, `FirewallaFlowMember`, `FirewallaFlowRollup`, and
   `FirewallaFlowReportView` have no caller until Phase 3. Adding them now would be
   untested, unused code, which the repository's "smallest coherent change" rule
   argues against and which would also fail the phase's own no-dead-code spirit.
3. **`managers/flow_manager.py` moved to Phase 2.** `ARCHITECTURE.md` allows an
   additional manager "only when a separate orchestration boundary is justified".
   Phase 1 has no flow orchestration to own; the manager arrives in Phase 2 with the
   three client calls it will actually own.
4. **The usage-window extractor moved to `utils/flow.py`.** The plan had it staying
   in the manager. It is pure, and Phase 2's flow manager needs it, so leaving it
   private in `integration_manager.py` would have forced a cross-module private
   import. It is now `extract_usage_window`, shared by the manager and available to
   the flow manager.
5. **1.8 accepts the empty string as neither true nor false**, where the plan
   implied one merged convention would win. Neither camp was right: `""` is an
   opaque marker, and reading it as `False` would invert `useBf` on rule creation.
   The union policy declines it instead.

#### Phase 1 findings — resolved and outstanding

**Resolved in Phase 1 (steps 1.8–1.10):**

- **Six boolean coercers on two incompatible conventions** — both camps read only
  one of the four encodings the box uses. Collapsed onto `normalized_bool`, which
  accepts all four and declines the empty string. Two defects closed: a property
  that read `autoDeleteWhenExpires` (`"0"`/`"1"`) as always-`None`, and a latent
  `""`-as-`False` inversion on `useBf`.
- **The flow ranking key did not casefold** while the other two did, so two lists
  answering "top destinations" could order an equal-valued pair differently.
  Aligned; measured **zero** ordering changes on 414 real rows.
- **Two further ad-hoc coercers** consolidated: `_alarm_count` (a bare
  `isinstance` test that would read a string count as `0`) and
  `_normalized_port_speed` (a sixth numeric parser).

**Outstanding — recorded, deliberately not changed:**

- **The entity and the service disagree on empty usage.** The entity omits the
  `network_usage` attribute when a network has no usage; the service reports
  all-`None` windows. Preserved, not resolved: "attribute absent" and "attribute
  present but empty" are already treated differently elsewhere, so changing either
  direction is an observable behaviour change.
- **A zero metric falls through to the next field**, and an all-zero row reports
  `0` rather than absent. Preserved from the `or` chain; a test caught the naive
  "first present value" rewrite changing which rows a report includes.
- **`useBf` remains `""` on DNS-only rules.** Correct as-is (the template defaults
  `None` → `True`, which matches the source rule), and now documented in the RE doc
  with the correlation that proves it. The regression risk is that a future reader
  "simplifies" it into a boolean test.

### Phase 2 — Protocol layer

- [ ] **2.1 Add `async_get_flow_rollup_payload`.** `item` = `tag` or `host`,
      `apiVer: 2`, `audit: true`, `start`, `end`, `hourblock`, targeting the tag id
      or MAC. Returns the raw dict.
- [ ] **2.2 Add `async_get_flow_log_payload`.** `item: "flows"`, `type`, `count`,
      `ts`, `exclude: []`, and **`audit` as a caller-supplied flag** — it *adds*
      blocked records rather than filtering to them (Q4b), so the flag is not a
      blocked-only switch. Returns `{count, flows, nextTs}`. A docstring must state
      that `audit: false` yields regular traffic only, because the name invites the
      opposite reading.
- [ ] **2.3 Add `async_get_blocked_flow_payload`.** `item: "auditLogs"`, same as
      2.2 plus optional `category` and `ets`. **This is the blocked-only query**
      (Q4b) and the response key is `logs`, not `flows`. Keep `exclude` internal
      (Q4); `category` is confirmed, so expose it.
- [ ] **2.4 Resolve the window from a constant, and report what was served.** Default
      `DEFAULT_FLOW_REPORT_WINDOW_HOURS` (24, mirroring the box's own default) so it
      changes in one place. **Send it and read back what the box actually covered**
      from the row `begin`/`end`, then report *that* as the served window, with a
      `window_clamped` warning when the served span is shorter than the requested
      one. The box rejects nothing and clamps silently — a 168h request was served
      24.00h with code 200 — so there is **no rejection to catch and no fallback to
      write**. Do **not** conflate `hourblock` (granularity) with the window, and
      clamp `hourblock` to at least 1 because `0` silently returns nothing.
- [ ] **2.5 Implement pagination with a deadline and a loop check.** Walk `nextTs`
      only in all-available mode. Stop on deadline, on a **non-advancing** cursor, or
      on an empty page. **Validate `count` before every call**: it must be a positive
      integer at or above a sane minimum and at or below `MAX_FLOW_LOG_PAGE_SIZE`
      (5000). The box caps a positive value silently, **and a non-positive value
      bypasses the cap and returns the entire retained window** (~6,956 rows
      measured), so an unvalidated caller value is a way to pull the whole log.
      **Dedupe across the page boundary** on a stable tuple
      (`ts`, `device`, `pid`, `domain` or `ip`, `port`) because `ts` bounds are
      inclusive and adjacent pages overlap, and **record how many rows were dropped
      as duplicates** (`records_dropped_as_duplicates`) so an under-count is visible.
      Expose the cursor as **`next_cursor`**, carrying `ts` verbatim and documented
      as **opaque**, so its meaning can change later without a breaking change.
- [ ] **2.6 Verify read-only against the dev box** for one tag and one host: window
      default and override, one page, all-available on a small target, a
      deliberately over-wide window (expect the fallback and warning, not a raise),
      and a `category`-filtered blocked read. Record every result in
      `REVERSE_ENGINEERING_WORKFLOW.md`.
- [ ] **2.7 Fail soft.** A shape change or a rejected request returns *unavailable*
      rather than raising, matching the existing `item=intf` posture toward
      OpenVPN's 500. The service reports what it could not read.
- [ ] **2.8 Create `managers/flow_manager.py`.** Moved here from Phase 1, where it
      had no orchestration to own. It owns the three client calls, the window
      fallback, and pagination; it consumes `utils/flow.py` for row reading and
      follows the existing manager shape (constructor takes the client, exposes
      async methods). Add the flow-report models to `models.py` in Phase 3, with
      their first caller.

### Phase 3 — Normalization

- [ ] **3.1 Reuse target resolution.** Accept a device (MAC or name) or a
      group/user (name or id); resolve to `type` + target through the existing
      resolver. Ambiguity raises the same class of error as
      `time_usage_report_scope_ambiguous`; not found raises the same class as
      `time_usage_report_scope_not_found`. **Do not add a parallel name→id lookup.**
- [ ] **3.1b Extract the shared matching core (Q12).** Three resolvers already
      implement the same algorithm — `_resolve_requested_host`,
      `_resolve_membership_target` and `_resolve_usage_history_target`, ~322 lines
      between them. Extract **only the matching core** (exact id, then casefolded
      name, then zero/one/many) into one helper returning `(exact, name_matches)`
      with no exceptions and no translation keys. **Do not build a single unified
      resolver**: the three differ in the name fields they match, in whether the
      ambiguous error names the matches, and in their return types, and the errors
      are translation-key `ServiceValidationError`s which `ARCHITECTURE.md` assigns
      to the service layer. Each caller keeps its own error mapping and match-list
      formatting. **Full suite must pass with no changed expectations**, since this
      touches two shipped services.
- [ ] **3.1c Fold in the Q14 rework before building on top of it.** In order:
      **R1** rename `device_mac` → `device_id` in the hit model and attributes (the
      field holds a device id; 3 of 48 live values are `wg_peer:` / `awg_peer:` /
      `if:`); **R2** replace `FirewallaRuleHit` with the shared flow-record model and
      keep `build_rule_hit_attributes` as its attribute projector, so there is **one**
      reader for a record the box stores in one shape; **R3** surface the recovered
      `download` / `upload` / `duration` / `count` / `ltype`; **R4** add `network` to
      `scope_kind` and document that flows cannot be network-scoped (`type: tag|host`
      only); **R5** split the two `category` sets in constants — flow/device 12,
      rule-target 11, and neither contains the other. This must land **before** the
      flow view is built, so the view consumes the shared record rather than the
      subset.
- [ ] **3.2 Build the summary from the rollup using the Phase 1 core.** Totals from
      the shared window extractor `extract_usage_window` in `utils/flow.py`;
      destination rows from the shared
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
      confirmed gate: per-device attribution (`top_members`, record `device` /
      `deviceIP`) is **absent by default** and returned when
      `include: ["device_detail"]` is set, at both detail levels. A single-device
      target returns its own identity without the flag. Ensure the gated values are
      always reachable — never permanently withheld.
- [ ] **3.5 Build the blocked and regular views.** Discriminate on **`ltype`**, not
      on the request flag (Q4b): `"audit"` is a blocked record, `"flow"` is regular
      traffic. Join `pid` → rule via the existing rule index, and apply Q5's rule:
      unmatched `pid` keeps the row with `rule_name: null` and increments
      `unattributed_blocks`. Apply Q10's inverted assertion — a blocked read must be
      all-`audit`, and a regular read must contain none. Keep the partial coverage
      visible: on blocked records `domain` is 265/300 but `category` is 52 and `app`
      is 10; on regular records `host`/`ip` are near-complete but `category` is
      111/300. The summary must not imply completeness. Report the box's own `count`
      alongside rows returned (`rows_returned` vs `rows_available`), so a bounded
      read is never read as a quiet target. **A blocked record has no bytes** — never
      report its absent `download`/`upload` as `0`. A **regular** record carries
      `download`, `upload`, `duration`, `devicePort`, and `apid`, so it can answer
      "how much and for how long" where a blocked record only answers "what was
      stopped".
- [ ] **3.5b Model direction explicitly.** Add a typed `direction`
      (`inbound` / `outbound` / `local`) derived from the **family name**, matching
      the vendor's documented field (Q4c). Do **not** read `fd`: it is `"in"` on both
      the `download` and `upload` families and on 300/300 regular records, so it
      cannot be a byte direction and would invert a report.
- [ ] **3.5c Derive the unit from the family, and name fields for the unit.** The
      family a row came from decides what its `count` means: `download` / `upload` /
      `local:download` / `local:upload` → **bytes**; `dnsB` / `ipB:*` / `local:*B:*`
      → **block count**; `local:in` / `local:out` → connections. Firewalla's own API
      documents the overload, so it is intended, not a quirk. **Never name a field
      `value`**: a generic name is what let a byte total and a block count become
      interchangeable in the existing ranking builder.
- [ ] **3.5d Coerce `port` and `devicePort` to tuples.** Measured: `port` is a
      **list** on every rollup row (207/207 `download`) and an **`int`** on every
      event row (1500/1500); `devicePort` follows the same split (`["8080"]` on a
      rollup row, `54568` on a record). A reader that assumes either shape returns
      nothing or a stray character.
- [ ] **3.5e Add a third destination kind for local flows.** `local:` families carry
      **`dstMac`** and no `host` / `domain` / `country`, because a LAN peer has no
      hostname. The vendor's model covers this — `destination.id` is "device ID if
      local, otherwise remote host domain or ip" — so `destination_kind` needs `mac`
      alongside domain and ip, and `dstMac` resolves against the host inventory.
- [ ] **3.5f Resolve the network and the group joins.** `intf` → local network name
      and `oIntf` / `wanIntf` → WAN name, both through `build_network_inventory` with
      no extra request (verified live: `VLAN10 CORE` and `WAN-ONE`). `tags` /
      `userTags` → group and user names through the existing indexes. This closes the
      same identity chain the rule and membership surfaces already use.
- [ ] **3.6 Emit the shared report envelope.** `config_entry_id`, `target`, `query`,
      `time_basis` (`_serialize_report_time_basis`), `summary`, sections,
      `metadata` (`_serialize_report_metadata` with `applied`, `warnings`,
      `unavailable_sections`, `provenance`). State the source (`item=tag|host` and
      `item=flows|auditLogs`) in `provenance` so it cannot be confused with the
      `item=intf` usage service. Never build a bespoke envelope. **The two views
      have different time semantics** — the rollup is a windowed aggregate, the log
      is a reverse walk from a timestamp — so `time_basis.kind` must distinguish
      them (`window` vs `flow_log`), or `is_partial` becomes meaningless.
- [ ] **3.6b Adopt the vendor's field names where they are better.** `is_blocked`
      (v. `ltype`), `block_type` (v. `type`), `region` (wire `country`),
      `flow_direction`, `bytes_download` / `bytes_upload`. Where a wire name is
      clearer, keep it and say so in `provenance`. **Validate `category` against the
      documented closed set** — `ad`, `edu`, `games`, `gamble`, `intel`, `p2p`,
      `porn`, `private`, `social`, `shopping`, `video`, `vpn` — and pass an
      unrecognised value through rather than dropping the row.
- [ ] **3.6c Document `ts` as the flow's *end* instant.** The vendor states it
      explicitly ("the time the flow ended"), and it is not obvious from the name.
      It matters for any window that a caller compares against.
- [ ] **3.7 Tests against the real capture.** Build the fixture from the 300
      captured records and the live rollup, and cover: summary shape; blocked and
      regular records with attributed and unattributed rules; member ranking absent
      on a device target; window fallback + warning; pagination dedupe across a
      boundary; deadline
      truncation sets `truncated`; `rows_returned` vs `rows_available`; and **both
      sides of the Q9 gate** — per-device fields absent by default and present with
      `include: ["device_detail"]` — so the gate cannot silently become a wall.
      **Also fabricate the malformed payloads** — a wrong shape, a missing
      `flows` key, a non-dict rollup — so the fail-soft path (2.7) is covered by a
      test rather than by prose. Snapshot the shapes.

### Phase 4 — Surface

- [ ] **4.1 Service schema and handler** in `services.py`, registered in
      `_SERVICE_REGISTRATIONS` as **read-only and `admin=False`** — matching every
      other query service (Q11). It must be non-admin or the Phase 4 tool cannot
      live in `llm_tools_read.py`, where all 13 read tools call non-admin services.
- [ ] **4.2 Field descriptions** in `services.yaml`, with the observed retention
      limit stated in prose on the window field.
- [ ] **4.3 Translations.** `strings.json` + regenerate
      `translations/en.json`; exception keys for scope ambiguous / not found / flow
      report failed, following the existing naming.
- [ ] **4.4 LLM tool** in `llm_tools_read.py` at the read-only tier: summary-first
      with the window and its actual served span stated, and an explicit sentence
      that the data covers the last ~24 hours rather than being a history. Update
      `llm_tools_common.py` if the target parameter is shared. This depends on 4.1
      being non-admin (Q11).
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
| **1** | **Done.** 560 tests pass with no existing assertion or snapshot changed; `ruff check`, `ruff format`, `mypy` clean. The before/after throughput measurement was dropped by owner decision as one-off activity. |
| **2** | Read-only live probes on the dev box, one tag + one host; results recorded in the RE doc. No writes. |
| **3** | Unit tests over the capture-derived fixture, including the adversarial cases (unmatched `pid`, boundary dedupe, over-wide window, device-target member ranking, both sides of the Q9 gate). A review check that Phase 3 **added no new flow builder**. |
| **4** | Full suite; live end-to-end for both detail levels; `python3 -m script.hassfest` if manifest or translation metadata moves. |

Commands: `python -m ruff check .` · `python -m ruff format .` ·
`python -m mypy custom_components/firewalla_local` · `python -m pytest tests/ -v`

---

## 7. References

- `docs/REVERSE_ENGINEERING_WORKFLOW.md` → *Flow reporting and the local block log*
  (the three queries, the blocked/regular split, field coverage, the `pid` join),
  *Limits: retention, page size, and window validity*, *`fd` is not the traffic
  direction*, and *Cross-check against Firewalla's published API*.
- Firewalla's published flow model, used as the statement of *intent* while
  reverse engineering established what the box actually sends:
  `docs.firewalla.net/data-models/flow/` and `docs.firewalla.net/api-reference/flow/`.
  Local access has no MSP layer; the model still corroborated the direction, block
  type, destination-kind, retention and `count`-overload readings, and corrected
  two assumptions (Q4b, Q4c).
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
- `custom_components/firewalla_local/binary_sensor.py` — `_serialize_top_talkers`
  and the `network_usage` attribute, now rendering through the shared usage
  projection (Phase 1.6).
- `custom_components/firewalla_local/services.py` — `_serialize_network_host_ranking`,
  `_serialize_network_usage_bucket`, `_serialize_network_usage_metric`; the report
  serializers the shared usage projection replaced (Phase 1.6).
- `custom_components/firewalla_local/const.py` — `DEFAULT_FLOW_REPORT_WINDOW_HOURS`
  and `MAX_FLOW_LOG_PAGE_SIZE`, the two constants the window and page design rests
  on.
- `custom_components/firewalla_local/utils/values.py` — the single numeric, boolean
  and string coercion policy (Phase 1.2 and 1.8).
- `custom_components/firewalla_local/utils/flow.py` — the single flow-row reader,
  host accumulator, per-host sort keys, and the usage-window extractor
  (Phase 1.3–1.5, 1.9).
- `custom_components/firewalla_local/helpers/usage_report.py` — the single usage
  window/summary projection shared by the entity and the services (Phase 1.6).
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
**Authorizes:** **Phase 1 only** (steps 1.1–1.10). Phases 2–4 are handed off
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
