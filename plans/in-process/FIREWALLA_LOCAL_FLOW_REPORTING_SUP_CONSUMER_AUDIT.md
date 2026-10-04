# SUP — Consumer audit: flow reporting and the single-logic-path requirement

**Supports:** `plans/in-process/FIREWALLA_LOCAL_FLOW_REPORTING_IN-PROCESS.md`
**Purpose:** answer the owner's three direct requests — *no artificial caps*,
*support both bounded defaults and all-available reads*, and *audit the existing
consumers so intensive, complex flow-data handling has one logic path and stays
efficient* — and then pressure-test the draft plan against its own gaps, traps and
opportunities.

Written 2026-10-03 against `main` (rule hit data merged). Revised the same day
against `feature/flow-reporting` after Phase 1 landed and after Firewalla's
published MSP flow model was cross-checked; sections 2b, 3 and the resolved-item
notes reflect that.

**Scope note:** Firewalla documents this model for its **MSP** cloud API. The
integration uses local access, which has no MSP layer, so the published model is
used as a statement of **intent** and not as an interface. Where the two disagree,
the measurement wins and the disagreement is recorded.

---

## 1. The finding: the integration already processes this data

The owner's point was that duplication exists **in the analysis and processing of
flow data**, not just in small helpers. That is correct, and it is a larger finding
than it first appears.

**The rollup is the per-target version of a family the integration already parses.**
`item=intf` carries the same `flows` families (`download`, `upload`, `appDetails`,
`categoryDetails`) and the same per-host counters (`conn`, `dns`, `ntp`, `dnsB`,
`ipB`, `ipD`, `download`, `upload`) that the flow rollup returns. The RE doc already
states this — *"This is the same family as the `systemFlows`-shaped data"* — and also
records that the box-wide `systemFlows` windows have **no** consumer today.

So the required processing mostly **already exists**, in `integration_manager.py`:

| Existing builder | Builds | Same as the flow report's | Consumed by |
| --- | --- | --- | --- |
| `_build_network_flow_rankings` | `FirewallaNetworkHostRanking` — `remote_host`, `remote_ip`, `value` | top destinations / top flows | segment report / usage (`get_network_segment_*`) |
| `_build_network_usage_buckets` | `FirewallaNetworkUsageBucket` — bytes, duration, sessions, active devices, latest ts | app / category rollup buckets | segment report / usage |
| `_build_network_activity_hosts` | `FirewallaNetworkHostTotals` from `appDetails` / `recent` / ranking families | per-device attribution | segment usage (`activity_hosts`) |
| `_build_network_hosts` | `FirewallaNetworkHostTotals` — `conn`/`dns`/`dnsB`/`ipB`/`ipD`/`ntp` | per-member totals | segment report (`hosts[]`) |
| `_build_network_top_talkers` | ranked devices, `_TOP_TALKER_LIMIT = 5` | `top_members` | `binary_sensor` `top_talkers` attribute |
| `_resolve_network_ranking_payload` | unwraps `{flows: []}` / `download` / `upload` / `items` / `results` | rollup family unwrapping | the two above |
| `_extract_usage_window` | `FirewallaNetworkUsageWindow` from `totalDownload` / `totalUpload` | the rollup's windowed totals | segment report / usage, `network_usage` attribute |

Both consumer surfaces the owner named are here: **entity attributes**
(`network_usage`, `top_talkers` in `binary_sensor.py`) and the **network usage
reports** (`services.py`). The three serializations of the same window concept are
also already spread across three modules:

- `services.py` — `_serialize_network_host_ranking`, `_serialize_network_usage_bucket`,
  `_serialize_network_usage_metric`
- `binary_sensor.py` — `_serialize_usage`, `_serialize_usage_window`,
  `_serialize_top_talkers`
- `integration_manager.py` — the builders themselves

**Conclusion.** The flow report should **reuse** these (generalized from network
scope to target scope) and add almost no processing of its own. Phase 1 of the plan
does exactly that. Building the flow report first and consolidating later would
guarantee a fourth parallel implementation of destination ranking, bucket
aggregation and device attribution.

### Duplicated inner steps

Inside those builders, the same decoding is written out repeatedly:

| Step | Copies | Where |
| --- | --- | --- |
| Device id from `device` / `mac` / `deviceMac` | **5** | `_build_network_flow_rankings`, `_build_network_activity_hosts` (×3 blocks), `_build_network_usage_buckets` |
| Metric from `<metric>` / `bytes` / `count` | **2** | `_build_network_flow_rankings`, `_build_network_activity_hosts` |
| Destination from `host` / `domain` + `ip` | 1 | `_build_network_flow_rankings` |
| Ranking-payload unwrapping | 1 | `_resolve_network_ranking_payload` |
| Download/upload window shape | **3 ser/deser** | extractor, service serializer, attribute serializer |
| Per-host sort key | **2 identical** | `_build_network_top_talkers`, `_build_network_hosts` |
| **Target resolution** (exact id → casefolded name → 0/1/many) | **3** | `_resolve_requested_host`, `_resolve_membership_target`, `_resolve_usage_history_target` — ~322 lines |

A field-name variation is currently fixed in three places or silently missed in one.

(An earlier revision of this note gave the device-id count as three and the
integer-coercer count as seven helpers in one place. Both were understated: the
count is five for the device id, and there are seven **integer** helpers plus six
**boolean** helpers plus two further ad-hoc numeric coercers found on review.)

### Target resolution is already triplicated

Found while planning Phase 2, and **pre-existing** — it is not caused by this
initiative:

| Resolver | Lines | Selectors | Returns |
| --- | --- | --- | --- |
| `_resolve_requested_host` | 86 | `host_id` / `host_mac` / `host_name` | `FirewallaHostRuntime` |
| `_resolve_membership_target` | 94 | group and user name/id | `FirewallaGroupRuntime` |
| `_resolve_usage_history_target` | 142 | one free-text device/user/group | `FirewallaUsageHistoryTarget` |

All three run the same algorithm. Adding the flow service as a fourth consumer
would make it four, so the matching core is extracted once (Q12) — but **not** as a
single unified resolver, because the three differ in ways that matter:

- **They match different name fields.** `_resolve_requested_host` matches five
  (`host_name`, `dns_hostname`, `dhcp_name`, `dns_fqdn`, watched choice); the usage
  resolver matches two. `llm_tools_read.py` documents the intent — `host_name` is
  *"the one to match a user's words against"* and `dhcp_name` is *"device-supplied
  and unreliable... never use it to identify a device"*. So the **narrower** matcher
  is the one following the documented rule.
- **They report ambiguity differently.** The host and membership resolvers name the
  matches so the caller can choose; the usage resolver does not.
- **Their errors are translation keys**, which `ARCHITECTURE.md` assigns to the
  service layer.

**Consequence to decide, not refactor:** the same device resolves through
`get_hosts` by its DHCP name but not through `get_time_usage_report`. Either the
host resolver is too permissive (it will accept an unreliable device-supplied name)
or the usage resolver is too narrow. This needs a decision about intent, and it is
**not** flow-reporting work.

### The efficiency problem

`_build_network_activity_hosts` accumulates into
`dict[str, dict[str, object]]`, then walks that dict a **second time** with `cast()`
on every field to build the dataclasses. That is double boxing per row, on the
hotter of the two passes.

It matters at real volume: `count: 2000` returned 2000 rows spanning ~5.7h, and a
page carries four families. The plan's step 1.5 requires single-pass accumulation
with a **before/after measurement on a 2000-row page**, so the improvement is
evidenced rather than claimed.

---

## 2. Numeric coercion: seven implementations, three disagreements

This is a supporting finding rather than the main one, but it is on the same path:
flow rows carry **string-typed numbers** — `"count": "236214"`, `"port": ["443"]` —
and every one of these coercers is used somewhere in the flow path.

| Helper | Location | `bool` | `float` | `str` | `"12.5"` |
| --- | --- | --- | --- | --- | --- |
| `_coerce_int` | `api/client.py:2436` | `1` / `0` | `int(v)` | `int(float(v))` if truthy | `12` |
| `_normalized_int_value` | `managers/integration_manager.py:146` | `None` | `int(v)` | `int(v)`, no strip | `None` |
| `_optional_int` | `managers/integration_manager.py:1386` | `1` / `0` | `int(v)` | `int(v)`, no strip | `None` |
| `_normalized_int` | `managers/integration_manager.py:2394` | `None` | `int(v)` | strip, then `int` | `None` |
| `_normalized_number` | `managers/integration_manager.py:2428` | `None` | `float(v)` | strip, `int` else `float` | `12.5` |
| `_optional_int` | `services.py:1996` | `1` / `0` | `int(v)` | `int(v)` if truthy, no strip | `None` |
| `_normalized_int` | `utils/network.py:90` | `None` | **`None`** | `int(v)`, no strip | `None` |

**Three material disagreements:**

1. **`bool` handling.** Three helpers return `int(True) == 1`; four return `None`.
   For a *count* field, `true` becoming `1` is a wrong number rather than a missing
   one — the worse failure.
2. **`float` support.** `utils/network.py` rejects floats outright; everything else
   truncates. A JSON `2.0` count would vanish on one path and read as `2` on another.
3. **String stripping.** Only two of seven strip whitespace, so `" 443"` is `443` on
   one path and `None` on another.

**Recommendation.** Consolidate to one strict helper in `utils/`. Strictness is the
right default here because every consumer treats these values as measurements, and a
*missing* measurement is recoverable while a *wrong* one is not. Migrate the call
sites in Phase 1, and report any call site whose behaviour changes as a finding —
those are latent bugs this initiative surfaces rather than creates.

---

## 2b. Boolean coercion: six implementations, two incompatible conventions

Found by re-auditing after the first pass missed the client's helper because its name
does not match the `_normalized_*` / `_optional_*` pattern the first grep used.

| Helper | Location | `bool` | `int` | `str` |
| --- | --- | --- | --- | --- |
| `_coerce_boolish` | `api/client.py:2444` | ✓ | `bool(v)` | `{"1","true","yes"}` / `{"0","false","no",""}` |
| `_optional_bool` | `managers/integration_manager.py:1301` | ✓ | `bool(v)` | **None** |
| `_optional_bool` | `services.py:1984` | ✓ | `bool(v)` | **None** |
| `_normalized_bool` | `managers/integration_manager.py:2308` | ✓ | **None** | `"true"`/`"false"` |
| `_normalized_optional_bool` | `models.py:179` | ✓ | **None** | `"true"`/`"false"` |
| `_normalized_bool` | `utils/network.py:83` | ✓ | **None** | `"true"`/`"false"` |

Two camps: three accept integers and no strings, three accept `"true"`/`"false"` and
no integers. A field was readable by whichever camp happened to be wired to it.

**Measured against live payloads**, the box uses four encodings:

| Field | Live encodings | Read correctly by |
| --- | --- | --- |
| 16 assorted flags (`active`, `ready`, `trust`, …) | real `bool` | either camp |
| **`autoDeleteWhenExpires`** | **`"0"`×24, `"1"`×1** | only the integer camp (`_coerce_boolish`) |
| **`useBf`** | **`""`×36, `True`×24** | **neither** — `""` needs declining, not answering |
| `disabled` | `"1"`/`"0"` | its own dedicated membership test |

**Two defects, one of them a latent trap rather than a live bug:**

1. **`autoDeleteWhenExpires` was read by the string-only camp** and so returned
   `None` for all 25 live values. It has no caller, which is why nothing broke; the
   client path reads the same field correctly through `_coerce_boolish`.
2. **`""` must not be read as `False`.** `useBf` is present exactly on DNS-only
   rules: the 36 `""` rules and 24 `True` rules are all `dnsmasq_only: True`, and
   `_coerce_boolish` would read those 36 as `False`. It is not routed through that
   field today, and the template default (`None` → `True`) happens to be correct —
   but reading `""` as `False` anywhere near this field would **invert the flag** on
   rule creation, since the create payload sends `useBf` verbatim.

**Recommendation.** One union coercer accepting all four encodings and **declining
the empty string**, since `""` is an opaque per-field marker rather than a value.

---

## 3. Ranking: one question, three implementations waiting to happen

`_build_network_top_talkers` already ranked devices by
`(-(download + upload), name.casefold(), mac)` and truncated at
`_TOP_TALKER_LIMIT = 5`; `_build_network_hosts` used a byte-identical key; and
`_build_network_flow_rankings` used `(-value, name, id)` — the same shape **without
the casefold**, so a top-destination list ordered by codepoint could place
`"Zebra"` before `"apple"` while a top-talker list of the same equal-valued pair did
the opposite.

**Resolved in Phase 1.** The two identical keys collapsed into
`host_traffic_sort_key` and the flow ranking now shares the casefold via
`metric_ranking_sort_key`. The three remaining keys are documented in
`utils/flow.py` with why their **primary** keys legitimately differ — one ranks by a
combined total, one by a single metric, one by a session-count tie-break — so the
differences are intentional and stated rather than accidental and silent.

Measured impact on real data: **zero** ordering changes across 414 captured ranking
rows (no duplicate-value group contains a mixed-case name), so this removed a latent
inconsistency without altering any output.


---

## 4. Gaps in the draft plan

- **No stated answer for "count returned vs count available".** A record response
  carries the box's own `count`. If we return 300 of 1,400, the summary must say so,
  or a reader will conclude the target was quiet. Phase 3.6's envelope has room for
  this in `summary`; it is not yet a step. **Add it to 3.5.**
- **No `next_cursor` naming decision.** The plan mentions exposing the cursor but not
  its name or whether it is opaque. Recommendation: `next_cursor`, carrying `ts`
  verbatim, documented as opaque so a future change to the cursor's meaning is not a
  breaking change.
- **No plan for what `time_basis` means on the log views.** The rollup is a
  windowed aggregate; a record log is a *reverse walk from a timestamp*. These are
  genuinely different time semantics and `kind` must distinguish them, or `is_partial`
  will be meaningless. **Add to 3.6.**
- **No coverage target for the fail-soft path (2.7).** A behaviour that only appears
  when the box misbehaves needs a test that fabricates the bad shape, otherwise
  2.7 is untested prose.
- **No decision on where the flow manager code lives.**
  `managers/integration_manager.py` is already the largest module in the repo.
  Recommendation, **agreed and now in the plan**: a new `managers/flow_manager.py`
  in Phase 2 for the flow view building, with the *shared* core in `utils/` as of
  Phase 1. Do not grow `integration_manager.py` further. Confirmed in Q13 that it
  must subclass `FirewallaBaseManager`, so wiring it touches four files rather than
  one.
- ~~No confirmed answer on default identity exposure.~~ **Closed 2026-10-03.** The
  owner confirmed: gate by default exactly as the segment report does, but keep it
  retrievable — `include: ["device_detail"]` returns per-device attribution at both
  detail levels. Recorded as Q9 and Phase 3.4, with a test covering **both** sides
  so the gate cannot quietly become a wall.
- **No stated rule that Phase 3 may add builders.** The plan now says it explicitly:
  Phase 3 consumes the Phase 1 core and adds no new flow processing. Without that
  rule stated, a builder added in Phase 3 recreates the exact duplication this
  initiative exists to remove.
- **No before/after evidence for the efficiency work.** Step 1.5 asks for a single
  pass, which is an assertion until measured. The validation table now requires a
  row-throughput measurement on a 2000-row page across four families. **Dropped by
  owner decision** as one-off activity; the change is reasoned rather than
  benchmarked.

### Resolved by the MSP cross-check (2026-10-03)

The plan claimed `item: "flows"` was the block log and that `audit: true` filtered
it to blocks. **Both were wrong**, and the error was structural. Measured:

| Query | `ltype` breakdown |
| --- | --- |
| `item: "flows"`, `audit: true` | 26 `audit` + 274 `flow` |
| `item: "flows"`, `audit: false` | 300 `flow` |
| `item: "auditLogs"`, `audit: true` | **300 `audit`** |

So `auditLogs` is the block log and `audit` **adds** blocked records rather than
filtering to them. A report built on the original reading would have been ~91%
regular traffic while claiming to show blocks. Recorded as Q4b, with Q10 inverted
(the assertion must be that a blocked read is all-`audit`, not the reverse) and
Phase 2 split into three named client methods.

A second probe settled direction. `fd` is `"in"` on all 199 `download` **and** all
199 `upload` rows, with 100 endpoints appearing in both families at the same `fd`
and different totals, and it is absent on `dnsB` entirely. **Direction must come
from the family name** — recorded as Q4c so nothing depends on `fd`.

### Resolved: the window and count contract (2026-10-03)

A third and fourth probe replaced the plan's window design entirely, because the
original assumed the box rejects a bad window and **it does not**. Every request
below returned **code 200**:

| Request | Result |
| --- | --- |
| `start` after `end` | normal response |
| `end` seven days in the future | normal response |
| `start` **1 year** back | normal response, same 24h of data |
| `hourblock: 168`, `999` | normal response |
| **`hourblock: 0`** | **200, zero rows** |
| `ts: 0` | 200, treated as absent (falsy), defaulted to now |
| `count: -5` | **200, ~6,950 rows** |

Two consequences, both now in the plan:

1. **No rejection path, so no fallback code.** Q2's "retry once at a known-good
   window" was written for an error that cannot be produced. Removed. The earlier
   RE doc claim of a code 500 on a 7-day start is **not reproducible** and has been
   retracted.
2. **The box clamps silently where it does not ignore.** The rollup served exactly
   **24.00h** for 1h, 24h, 25h, 48h and 168h requests — identical data, no
   indication. The served window must therefore be **read from the response**, or a
   caller asking for 48 hours is told they got 48 hours.

**`count` also turned out to have a hard ceiling and a dangerous floor.** An earlier
reading of "no fixed cap observed" tested only 300 and 2000:

| `count` | rows |
| --- | --- |
| 50 – 5000 | exactly that many |
| 5001 – 100000 | **5000** (silently capped) |
| **-1** | **6,956 — the entire retained window** |
| 0 | 100 |
| 1 | **0** |

So a positive count is capped at 5,000, a **negative count returns everything**, and
the low single digits are undefined. Since a busy group held 6,956 records in one
day, the cap is why pagination is required rather than optional — and a
caller-supplied count must never be forwarded unvalidated, because `-1` is the
opposite of "nothing". Two constants now carry this:
`DEFAULT_FLOW_REPORT_WINDOW_HOURS` and `MAX_FLOW_LOG_PAGE_SIZE`.

---

## 5. Traps

| # | Trap | Why it bites | Mitigation |
| --- | --- | --- | --- |
| **T1** | A fourth flow-processing path | The five existing builders already answer these questions for `item=intf` (§1); a new path diverges silently | Phase 1 generalizes them; Phase 3 adds no builder |
| **T2** | A second usage-window parser | Rollup reuses `newLast24`/`last60`/`last30`/`last12Months` | Phase 1.4 shares the extractor |
| **T3** | A second device ranker | Near-identical sort keys already exist; `top_talkers` answers this | Phase 1.4/1.9: two shared keys, `5` as a parameter default, the three legitimate primary-key differences documented |
| **T4** | Empty reported as "nothing happened" | Retention is a hard ~24h cutoff; an empty page is indistinguishable from a quiet target | Always return the window searched, the served window, and the box's own `count` |
| **T4b** | A window silently clamped | The rollup served 24.00h for 1h, 24h, 25h, 48h and 168h requests with no error, so the request is not evidence of what was returned | Read the served span from the row `begin`/`end`; warn when it is shorter than requested — Phase 2.4 |
| **T4c** | A rejection path written for an error that cannot happen | The box rejects nothing: `start` after `end`, a 1-year-old `start`, `hourblock: 999` and a negative `count` all return 200 | No fallback code; validate client-side instead — Q2, Phase 2.4 |
| **T4d** | A non-positive `count` returning the whole log | `count: -1` returned 6,956 rows (the entire 24h window) and `count: 0` returned 100, so a negative is the opposite of "nothing" | Validate `count` to a positive bounded integer before every call — Phase 2.5 |
| **T4e** | Assuming the requested count is the returned count | A positive count is silently capped at 5,000, and `count: 1` returned 0 rows | Report rows returned against the box's own `count`; enforce the minimum and the cap — Phase 2.5 |
| **T5** | Duplicate rows across a page boundary | `ts` bounds are inclusive, so adjacent pages overlap | Dedupe on `(ts, device, pid, domain or ip, port)` — Phase 2.5 |
| **T6** | A bespoke response envelope | Four report services share an envelope; a fifth shape fragments the surface | Phase 3.6 reuses the existing serializers |
| **T7** | Conflating `hourblock` with retention | `hourblock` is granularity, not the window; every value 1–168 works, and **`0` silently returns nothing** | Documented in 2.4, with a clamp to at least 1 |
| **T8** | Unbounded service response | 6,956 records in one group's 24h window; a full day is thousands of identity-bearing rows | Summary default, bounded page default, explicit opt-in for all-available (Q1) |
| **T9** | A silent filter no-op | `audit: true` does not filter to blocks, it adds them | Phase 2 names one method per query; Phase 3 discriminates on `ltype`; `exclude` stays internal (Q4) |
| **T10** | Implying a record set is complete | Blocked coverage is uneven: `domain` 265/300 but `category` 52 and `app` 10; regular records are near-complete on `host`/`ip` but `category` is 111/300 | Phase 3.5 must not summarize absent fields as zero |
| **T11** | `pid` → rule join dropping rows | Rule ids are not durable across delete/re-create (issue #53) | Q5: keep the row, null the name, count it |
| **T12** | Ambiguous target name | A name can be both a group and a device | Reuse the existing resolver's ambiguity error — Phase 3.1 |
| **T13** | Refactor changing observable ordering | The existing sort keys disagreed on same-value rows; ordering is visible in service output and snapshots | Phase 1.9 aligned the flow keys; measured **zero** ordering changes on 414 real rows |
| **T14** | Consolidation changing a coercion result | The coercers disagreed; strictness changes what some call sites return | Phase 1.2 recorded every change; 601 tests pass with no snapshot touched |
| **T17** | Reporting `fd` as direction | `fd` is `"in"` on both byte families and 100 endpoints carry it on two opposite rows | Q4c: direction comes from the family name only |
| **T18** | One `count` field, two units | `count` is bytes on `download`/`upload` and a block count on `ipB`/`dnsB`, exactly as Firewalla documents | Phase 3.5c derives the unit from the family and forbids a generic `value` field name |
| **T19** | Assuming one shape for `port` | `port` is a list on rollup rows (207/207) and an int on records (1500/1500) | Phase 3.5d coerces both to tuples |
| **T20** | A local flow with no hostname | `local:` families carry `dstMac` and no `host`/`domain`, so a domain-or-ip destination kind cannot represent them | Phase 3.5e adds a `mac` destination kind |
| **T21** | Reading a blocked record's absent bytes as zero | Blocked flows are intercepted before travelling, so they have no bytes at all | Phase 3.5: report absent, never `0` |
| **T22** | Registering a read service as admin | All 13 read tools call non-admin services; the one admin read is a bulk diagnostic dump | Q11: `admin=False`, or the Phase 4 tool cannot be a read tool |
| **T23** | Deduping regular records on `pid` | `pid` is absent on regular records, so the key collapses to `(ts, device, None, host, port)` and one device's many same-second connections collide | Dedupe on the row's serialized content — Phase 2.5 |
| **T24** | Rounding the `nextTs` cursor | It is a float and passing it back is how pagination walks | Carry it verbatim; only test equality/non-advance — Phase 2.5 |
| **T25** | A fourth target resolver | Three already exist (~322 lines) running the same algorithm | Extract the matching core, not a unified resolver — Q12 |
| **T26** | Calling a device id a MAC | `device_mac` holds a device id; 3 of 48 live rule hits are `wg_peer:` / `awg_peer:` / `if:` | Rename to `device_id` — Q14 R1 |
| **T27** | Treating `lastHitFlow` as a reduced summary | It is a **full flow record**; we read 10 of 35 fields and drop bytes, duration, `ltype`, `dstMac` | One flow-record model and reader for both surfaces — Q14 R2/R3 |
| **T28** | Validating `category` against an enum | Locally `category` is an **open set**: a rule's `category` target holds real categories, `TL-`/`TLX-` target-list ids **and** `dap_*` rule ids; a flow record's can be `''` or `'none'` | Pass unknown values through; keep the existing prefix-based target-list handling — Q14 R4 |
| **T29** | Assuming a flow record's `device` resolves to a host | `if:<uuid>` is an interface device with no host-inventory entry | Tolerate an unresolvable device id; report it rather than dropping the record |
| **T30** | Treating the published MSP model as a wire reference | MSP **remaps**: its `hit` is a summary struct where the box stores a full flow record; its target vocabulary (`app`/`internet`/`domain`/`region`/`targetlist`) does not appear locally, and local `mac`/`network` targets have no MSP equivalent | Ground every claim in a local measurement; use MSP for intent only — Q14 |
| **T15** | A default gate becoming a wall | Gating per-device attribution off by default is fine only if it stays reachable | Phase 3.4 plus a test on both sides of the gate |
| **T16** | Efficiency work trading correctness | Single-pass accumulation can drop the deterministic tie-break | Step 1.5 keeps sort keys identical and measures before/after |

---

## 6. Opportunities

- **O0 — most of the processing already exists.** This is the biggest opportunity in
  the audit: the five builders in §1 already do destination ranking, bucket
  aggregation and device attribution for the same `flows` families. The flow report
  is therefore a **scope generalization** over working, tested code rather than a new
  subsystem — provided Phase 1 lands first.
- **O1 — the `pid` join is genuinely new capability.** `device → membership → rule →
  the rule that blocked this flow → the destination it blocked` cannot be answered by
  any existing surface. This is the differentiator, and it is why the record detail
  belongs in the initiative's scope rather than a later increment.
- **O2 — one normalization, three consumers.** The service, the LLM tool and any
  future sensor should read the same view object. Building it once in Phase 3 is what
  makes Phase 4 cheap.
- **O3 — the consolidation pays for itself four times over.** Collapsing seven
  integer coercers, six boolean coercers, two further ad-hoc numeric coercers, five
  device-id resolvers, two metric resolvers and the duplicate sort keys removes a
  real class of latent bug, independent of flow reporting. The existing segment
  report and the `network_usage` / `top_talkers` attributes improve as a side
  effect.
- **O4 — blocked-by-direction is free.** `ipB:in` vs `ipB:out` come back as separate
  families, so "what did this device try to reach" and "what tried to reach it" are
  different answers already present in one response.
- **O5 — naming already exists.** The rollup is the `systemFlows` family the init
  payload caches, so the model and field names have a precedent to match rather than
  invent.
- **O6 — the retention limit becomes a product statement.** Because the answer is
  documented rather than encoded, "the last day" can be stated plainly to users and
  the agent, and it stays correct if Firewalla extends it.
- **O7 — the un-consumed `systemFlows` windows become reachable.** The RE doc notes
  that the box-wide 24h `upload` / `download` / `dnsB` windows have no consumer
  today. The same generalisation makes them a small addition later, at no extra cost.
- **O8 — `lastHitFlow` and the flow log are one record type.** Measured: the local
  `lastHitFlow` is a full flow record (35 fields, core fields on all 48), not a
  summary. So the flow report does not need a new model: it needs the **existing**
  record read in full. That converts a would-be new subsystem into a unification,
  and it recovers the bytes, duration and attribution fields the current hit model
  drops. **Note:** the published `hit` struct is a *different* shape, so this rests
  on local measurement rather than on the documentation.

---

## 7. Pressure-tested answer to "no artificial caps"

Four separate things were being conflated under "caps", and each needs a different
answer:

1. **Retention (~24h)** — a **box** limit, not a policy. Do not encode it. Default
   the window to 24h, attempt whatever is asked, fall back with a warning, and report
   the window actually served. Documentation and instruction text only. *(Q2)*
2. **Default page size** — a **response-size** concern, not a data limit. Default to
   one page, make it caller-controllable, and let all-available walk to exhaustion.
   The only stops are a deadline and a loop check, never a row count. *(Q1)*
3. **Summary vs rows** — a **presentation** choice, not a limit. Summary is the
   default because it is what the question usually wants; rows are always reachable.
4. **Gated identity** — a **default-shape** choice, not a wall. Per-device
   attribution is off by default and returned on request via
   `include: ["device_detail"]`. Anything gated must remain obtainable in one call;
   a value that can never be retrieved is a bug, not a privacy control. *(Q9)*

The test to apply when reviewing Phases 2–4: *if Firewalla doubled the retention
window and the page size tomorrow, which lines would we have to change?* The answer
should be **none in logic** — only prose in docs and the tool description.
