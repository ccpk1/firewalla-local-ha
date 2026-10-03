# SUP — Consumer audit: flow reporting and the single-logic-path requirement

**Supports:** `plans/in-process/FIREWALLA_LOCAL_FLOW_REPORTING_IN-PROCESS.md`
**Purpose:** answer the owner's three direct requests — *no artificial caps*,
*support both bounded defaults and all-available reads*, and *audit the existing
consumers so intensive, complex flow-data handling has one logic path and stays
efficient* — and then pressure-test the draft plan against its own gaps, traps and
opportunities.

Written 2026-10-03 against `main` (rule hit data merged).

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
| Device id from `device` / `mac` / `deviceMac` | **3** | `_build_network_flow_rankings`, `_build_network_activity_hosts` (×2 blocks), `_build_network_usage_buckets` |
| Metric from `<metric>` / `bytes` / `count` | **2** | `_build_network_flow_rankings`, `_build_network_activity_hosts` |
| Destination from `host` / `domain` + `ip` | 1 | `_build_network_flow_rankings` |
| Ranking-payload unwrapping | 1 | `_resolve_network_ranking_payload` |
| Download/upload window shape | **3 ser/deser** | extractor, service serializer, attribute serializer |

A field-name variation is currently fixed in three places or silently missed in one.

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

## 3. Ranking: one question, three implementations waiting to happen

`_build_network_top_talkers` already ranks devices by
`(-(download + upload), name.casefold(), mac)` and truncates at
`_TOP_TALKER_LIMIT = 5`. `_build_network_hosts` sorts by a near-identical key,
`_build_network_flow_rankings` by `(-value, host_name, host_id)`, and
`_build_network_usage_buckets` by `(-total, -sessions, key)`.

Four sort keys that all answer "rank by traffic, break ties deterministically" and
each does it slightly differently — `_build_network_hosts` includes `host_name`
before `host_id`, `_build_network_flow_rankings` does not casefold, and only the
top-talker path has a limit. The flow report's `top_members` and `top_destinations`
need the same questions answered.

**Recommendation.** Phase 1.4 makes these target-agnostic with **one tie-break
rule**, keeping `5` as a parameter default rather than a second constant. Where the
four keys genuinely disagree on ordering of same-value rows, that is a **finding to
report**, not something to silently normalize — the output ordering of the existing
services is observable behaviour.

---

## 4. Gaps in the draft plan

- **No stated answer for "count returned vs count available".** The events response
  carries the box's own `count`. If we return 300 of 1,400, the summary must say so,
  or a reader will conclude the target was quiet. Phase 3.6's envelope has room for
  this in `summary`; it is not yet a step. **Add it to 3.5.**
- **No `next_cursor` naming decision.** The plan mentions exposing the cursor but not
  its name or whether it is opaque. Recommendation: `next_cursor`, carrying `ts`
  verbatim, documented as opaque so a future change to the cursor's meaning is not a
  breaking change.
- **No plan for what `time_basis` means on the events view.** The rollup is a
  windowed aggregate; the event log is a *reverse walk from a timestamp*. These are
  genuinely different time semantics and `kind` must distinguish them, or `is_partial`
  will be meaningless. **Add to 3.6.**
- **No coverage target for the fail-soft path (2.7).** A behaviour that only appears
  when the box misbehaves needs a test that fabricates the bad shape, otherwise
  2.7 is untested prose.
- **No decision on where the flow manager code lives.**
  `managers/integration_manager.py` is already the largest module in the repo and
  holds four of the seven coercers. Recommendation: a new
  `managers/flow_manager.py` for the flow view building, with the *shared* core
  lifted to `utils/` in Phase 1. Do not grow `integration_manager.py` further.
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
  row-throughput measurement on a 2000-row page across four families.

---

## 5. Traps

| # | Trap | Why it bites | Mitigation |
| --- | --- | --- | --- |
| **T1** | A fourth flow-processing path | The five existing builders already answer these questions for `item=intf` (§1); a new path diverges silently | Phase 1 generalizes them; Phase 3 adds no builder |
| **T2** | A second usage-window parser | Rollup reuses `newLast24`/`last60`/`last30`/`last12Months` | Phase 1.4 shares the extractor |
| **T3** | A second device ranker | Four near-identical sort keys already exist; `top_talkers` answers this | Phase 1.4, one tie-break rule, `5` as a parameter default |
| **T4** | Empty reported as "nothing happened" | Retention is a hard ~24h cutoff; an empty page is indistinguishable from a quiet target | Always return the window searched, the served window, and the box's own `count` |
| **T5** | Duplicate rows across a page boundary | `ts` bounds are inclusive, so adjacent pages overlap | Dedupe on `(ts, device, pid, domain or ip, port)` — Phase 2.5 |
| **T6** | A bespoke response envelope | Four report services share an envelope; a fifth shape fragments the surface | Phase 3.6 reuses the existing serializers |
| **T7** | Conflating `hourblock` with retention | An earlier probe blamed `hourblock: 168` for a failure actually caused by an out-of-range `start` | Documented explicitly in 2.4; every `hourblock` 1–168 works |
| **T8** | Unbounded service response | 300 rows per 0.3h on a busy group; a full day is thousands of identity-bearing rows | Summary default, bounded page default, explicit opt-in for all-available (Q1) |
| **T9** | A silent filter no-op | `audit: true` unverified; `exclude` values unknown | Q10's `ltype` assertion; `exclude` stays internal (Q4) |
| **T10** | Implying the block log is complete | `domain` is 283/300 but `category` is 91 and `app` is 30; `host`/`ip` only 15–17 | Phase 3.5 must not summarize absent fields as zero |
| **T11** | `pid` → rule join dropping rows | Rule ids are not durable across delete/re-create (issue #53) | Q5: keep the row, null the name, count it |
| **T12** | Ambiguous target name | A name can be both a group and a device | Reuse the existing resolver's ambiguity error — Phase 3.1 |
| **T13** | Refactor changing observable ordering | The four existing sort keys disagree on same-value rows; ordering is visible in service output and snapshots | Phase 1.4 reports such rows as a finding rather than normalizing silently |
| **T14** | Consolidation changing a coercion result | Three of the seven coercers disagree; strictness changes what some call sites return | Phase 1.2: record every call site whose behaviour changes |
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
  any existing surface. This is the differentiator, and it is why the events detail
  belongs in the initiative's scope rather than a later increment.
- **O2 — one normalization, three consumers.** The service, the LLM tool and any
  future sensor should read the same view object. Building it once in Phase 3 is what
  makes Phase 4 cheap.
- **O3 — the consolidation pays for itself four times over.** Collapsing seven
  coercers, three device-id resolvers, two metric resolvers and four sort keys
  removes a real class of latent bug, independent of flow reporting. The existing
  segment report and the `network_usage` / `top_talkers` attributes improve as a side
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
