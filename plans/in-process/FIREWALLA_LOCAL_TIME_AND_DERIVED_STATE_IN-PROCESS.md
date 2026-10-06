# Time and Derived State — IN PROCESS

**Initiative:** Every published instant is readable, and every derived value is reproducible
**Owner:** Firewalla Strategist
**Status:** Phase 0 (research) complete; plan open for pressure-testing. No phase started.
**Branch:** `feature/flow-reporting`
**Supporting note:** `FIREWALLA_LOCAL_TIME_AND_DERIVED_STATE_SUP_ENTITY_INVENTORY.md`

---

## 1. Initiative snapshot

Two defects were found on the live box, and they are the same defect: **a published value
that the reader cannot reproduce from the payload.**

**Class A — instants that are not readable.** `list_hosts` publishes
`last_active: 1791258075.36`. There is no date. An agent has nothing to show a user, and
during the TV diagnosis I compared those floats as *numbers* because there was no other
option.

**Class B — derived state whose inputs are unpublished.** `online` is not a fact about a
host; it is `reference - last_active <= window`. None of the three inputs is published.
Measured on the dev box, this produced a **live contradiction**: `get_system_overview`
reported `vpn_hosts: {total: 5, online: 1}` while `list_hosts` reported all five peers
`online: false`, seconds apart. The "online" peer, `chads-laptop-wgvpn`, had last activity
**4.51 days** earlier — it was online only because the reference was derived from the peer
subset, so the newest peer was online by construction. That root cause is fixed
(`5113793`); the *unverifiability* remains.

The same shape appears on a host row: `kadens-phone` published `online: false` with
`last_active` **6.6 minutes** before the reference, because the window is 5 minutes. The
row contains no reference, no window and no `stale` flag, so the value is unexplainable
without reading three source files. An agent cannot do that.

**Why this is in scope for an initiative rather than a patch.** The repository already has
the right *shape* in places — `tested_at` (ISO) plus `tested_at_timestamp` (epoch),
`pause_until` plus `pause_remaining_seconds`, and `build_rule_hit_attributes` publishing
`at` and `timestamp` together. The gap is that the pattern is not **stated, enforced or
tested**, so it is applied unevenly: 23 `.isoformat()` calls and 21 hand-rolled
conversions across seven files, two naming patterns for the same pair, and one published
name (`fired_at`) that means two things on two surfaces.

**Why two prior passes missed this.** Vocabulary Alignment checked *names* — is this called
`host` or `device`. Every check it added is a value or key comparison, so it could not see a
correctly-named field holding a wrong number, and it had no way to notice that three inputs
were driving one output. The defect survived because it is a *semantic* problem in a
*lexical* guard's blind spot. That is the argument for this initiative adding a guard that
asserts a **fact** — recompute the claim from the published fields and compare — rather than
another guard that asserts a shape.

**Why now.** The service and LLM surfaces are being built and have no consumers, so they
are free to change. The **entity** surface is different: users may already have
automations and templates against those attributes. This plan therefore treats the entity
surface as the careful one, and gets the standard right before touching it.

**The constraint that makes this its own initiative.** Vocabulary Alignment answered
"what is this called". This answers "what does this value *mean*, and can the reader
check it". They share a test harness and a doctrine section, so this plan extends both
rather than duplicating them.

---

## 2. Scope and non-goals

### In scope

- State the rule for instants, durations and derived state in `DEVELOPMENT_STANDARDS.md`,
  extending the existing *Time and timezone standards* section (currently timezone-only).
- One conversion helper so format cannot vary per call site.
- **Every published surface** — service responses, LLM tool results, entity attributes and
  entity state. Not a subset: the rule is only a rule if it holds everywhere.
- Publishing the basis for every derived windowed value: the reference instant, the
  applied window, and the box's `stale` flag.
- Naming consistency: one suffix convention for an ISO instant and its epoch twin,
  replacing the **three** patterns currently in use across services and tools.
- Guard tests that assert both the *pairing* and the *reproducibility*, not just presence.
- Migration documentation for anything that breaks.

### Non-goals

- Re-litigating timezone handling. The existing rules (appliance timezone canonical, Home
  Assistant as fallback) stand and are not changed.
- Changing the two configurable windows or their defaults, or the behaviour of
  `device_tracker`'s separate away window.
- Introducing a timestamp `device_class` sensor. No entity's *state* is a time; every
  instant here is an attribute, so the class does not apply.
- Consolidating or restructuring `flow_report` / `runtime_inventory` payloads beyond what
  this naming rule requires.

### The change policy — no shims, no wrappers, no deprecation

**Owner decision, and it governs every phase:** these are new surfaces with no consumers
built against them. There are no users to migrate, so there is nothing to protect and no
reason to carry the cost of a compatibility layer. When a field needs a new name, it is
renamed and the change is **declared breaking**. Explicitly not permitted:

- alias fields (publishing both the old and new name "for now")
- deprecation periods or dual-write windows
- a compatibility shim in any layer, including the LLM tool wrappers
- silent changes where the old name quietly disappears without a migration note

**The one obligation that replaces compatibility work: the break must be *documented*.**
Every rename lands with a row in `USER_GUIDE.md`'s migration table and an entry in
`RELEASE_CHECKLIST.md` §4's known-breaking-change block. "No shim" is not "no notice" — it
means the notice replaces the shim, so a breaking change is still a reviewable, stated
event rather than something a user discovers from a broken template.

**Why this is stated as a rule rather than left to judgement:** the two surfaces have
different risk and the same policy. Services and tools can be renamed freely because
nothing consumes them. Entity attributes may have templates against them, so they get
*more careful documentation*, not a longer compatibility window. Stating one policy stops
the entity work from drifting into the shim that is ruled out here, and stops the service
work from being treated as "reference only" — which is what this plan originally got wrong.

---

## 3. Open questions and external dependencies

### Q1. Does `last_active` become `last_active_at`? — **APPROVED**

`tested_at` / `sampled_at` / `fired_at` are ISO instants named `_at`. `last_active` is an
ISO instant named `_active`. Under a stated rule it is `last_active_at`.

**Owner decision (2026-10-06): approved — "lets be consistent."** The rename lands, is
declared breaking, and carries no compatibility layer, per the change policy in §2. It is
still the largest entity break in the plan (two constant values covering five attributes —
see the supporting note §3), so it keeps the fullest migration entry and stays in the entity
phase alongside the other attribute work.

**What this approval fixes in place, and why it is worth recording.** `last_active` was the
one instant whose name already existed on a user-facing surface, so it was the natural place
to make an exception. Approving it establishes that the suffix rule is a **rule rather than a
preference**: `_at` marks an instant everywhere, with no grandfather clause for the one field
that predates the convention. Every later field now has an unambiguous target instead of a
precedent for special-casing — which is the whole point of naming consistency, and cheaper
now than it would be after another instant is added beside it.

This also settles Q3 by implication: with `_at` mandatory for instants, `_enabled`-style
names cannot be reused for a time. Q3's `_start` / `_end` case is unaffected, because those
are window boundaries rather than points in time and are addressed on their own terms.

**Cascading effect on Phase 3.** Because `last_active` also appears on the service surface
(`get_hosts` → `last_active`, flow records → `timestamp`), Phase 3.3 and Phase 4.2 must land
the **same name** — `last_active_at` plus `last_active_timestamp` — rather than each choosing
its own. One concept, one name, whichever surface publishes it. Phase 4.2's step is already
written to match; the cross-reference is noted here so the two phases cannot drift apart
during implementation.

### Q2. What is the epoch twin called when the ISO name already ends in `_at`?

`runtime_data_updated_at` is already `_at`. Mechanical appending gives
`runtime_data_updated_at_timestamp`, which is ugly. Replacing the temporal suffix gives
`runtime_data_updated_timestamp`, which is prettier but breaks the pattern the four
existing pairs follow (`fired_at` → `fired_at_timestamp`).

**Recommendation:** mechanical — `<iso_name>_timestamp` everywhere, accepting the one ugly
case. A rule with an exception for aesthetics is not a rule.

**ANSWERED in Phase 2 — mechanical, confirmed against the code rather than by taste.** The
surface already follows it in **five** places, and not only as published keys: `tested_at` /
`tested_at_timestamp` is a **model field** name (`models.py:339`), carried through the client
(`client.py:1625`), the manager (`integration_manager.py:1398`) and the sensor. The others
are `sampled_at_timestamp` (`services.py:1020`), `fired_at_timestamp` (`services.py:1350`),
`expires_at_timestamp` (`services.py:1382`) and `synced_at_timestamp` (`services.py:4632`).

So this was never an open question about aesthetics: the convention was already set, and the
only thing missing was a statement of it. There is also a real benefit to the stutter beyond
consistency — the epoch name *contains* the ISO name, so `fired_at` and `fired_at_timestamp`
adjacent in a payload are self-evidently the same concept in two forms, which `fired_timestamp`
would not be.

**Phase 2 got this wrong before it got it right, and the correction is recorded rather than
quietly overwritten.** The epoch twin was first published as `activity_reference_timestamp`
— the prettier stripping form — one phase after recommending against exactly that. The
Phase 1 guard caught it, flagging `activity_reference_at` as untwinned in two modules, which
is the guard doing its job on its author. Renamed to `activity_reference_at_timestamp` to
match the five existing pairs.

### Q3. Are `schedule_next_start` / `schedule_next_end` instants needing the suffix?

They hold ISO datetimes but are named `_start` / `_end`, not `_at`. They are *window
boundaries*, which reads naturally as-is.

**Recommendation:** treat `_at`, `_until`, `_start` and `_end` as the closed set of
temporal suffixes that mark an instant, and keep these two. The alternative —
`schedule_next_start_at` — is noticeably worse and buys nothing, since no other reading of
`next_start` is possible.

**CLOSED 2026-10-06 — left as is by owner decision.** Renaming would cost clarity rather
than buy it, so `schedule_next_start` / `schedule_next_end` keep their `_start` / `_end`
names and are accepted as instants without an `_at`. The guard's suffix set already treats
them as valid, so nothing further is required for them.

### Q4. Where does the basis go — envelope or every row?

Services publish rows, so a per-response envelope is available and cheaper. Entities have
no envelope, so an attribute is the only option.

**Recommendation:** per-surface, not one global answer. Services publish `activity_reference_at` +
`online_window_seconds` once at the response envelope; the three connectivity **entities**
publish them as attributes. Justification for the split: the user's stated care about
entities, plus the fact that an entity attribute is independently inspectable in a
template while a service envelope is read once.

**Settled in Phase 2.** The envelope carries the pair, and `get_hosts` adds one per-row
field that the envelope cannot carry: `stale`. The basis is a *frame*, and `stale` is a
*per-host fact* inside it, so a row whose `online` the basis alone cannot explain needs its
own key. That is the distinction the original question did not draw.

### Q5. Do we publish `stale` as `null` or omit it?

The box does not report `stale` for pseudo-hosts (`null`), and `is_host_online` returns
`None` when there are no timestamps at all.

**Recommendation:** publish with `null`. A key that is sometimes absent forces consumers to
handle absence *and* null; one that is always present with an honest `null` forces only
null. This matches how the rest of the surface behaves.

**Settled in Phase 2.** `get_hosts` rows publish `stale` unconditionally, `null` included.
It is published because it is part of the online *rule*, not merely descriptive: a host the
box has not seen in about a week is offline however recent its activity stamp looks, so
without `stale` a row's `false` directly contradicts the basis beside it.

### Q6. Which entities get the basis?

Eight entities derive a windowed boolean or count from the activity reference: watched
device, device tracker, watched user (counts), system status (host and VPN counts), and the
per-network binary sensor.

**Recommendation:** all of them, for one reason — they all read the same reference, so
publishing it on only some would recreate the exact "two answers" problem this initiative
exists to fix.

**Corrected during Phase 2: the count was wrong, and the rule was too broad.** The real set
is **three**, not eight. Two of the eight carry no windowed boolean or count at all: the
per-network binary sensor publishes the box's plain inventory count, and the watched-user
sensor publishes `total_minutes_today`, a calendar-window aggregate from the box. Neither
has a derived value for a basis to explain, so a basis there would be noise that *dilutes*
the signal the other three carry. The rule the list should have stated is not "every entity
that mentions a host" but **"every surface that publishes a value derived from the activity
reference"** — which is the shape of the guard, and the reason the guard is written against
responses and recomputation rather than against a list of entities.

### Q7. Is the existing `uptime` / `uptime_seconds` pair the model to cite?

`uptime` is a human string and `uptime_seconds` is numeric — a **duration** pair, not an
instant pair. The suffix differs (`_seconds` vs `_timestamp`), which is correct: a duration
in seconds and an instant in seconds are different quantities.

**Recommendation:** cite it in the standard as the duration exemplar, leave it unchanged,
and state explicitly that `_seconds` and `_timestamp` are not interchangeable. Recording
this matters because a reader could otherwise "fix" it into an inconsistency.

### Q8. Is the network entity's `host_count` the same number as the service's?

`services.py` publishes `"host_count": len(network_hosts)` with the comment *"The same count
the `network` entity publishes as an attribute."* The entity publishes
`network.device_host_count`, which is the box's own count. Those are two different
computations, and the comment asserts they are identical.

**Recommendation:** treat as a Phase 1 investigation, not a known defect. If they diverge
on live data this is a third instance of the same class and must be resolved before any
attribute rename lands, because it determines which of the two names is correct.

**Answered in Phase 2, and the investigation changed the answer.** They *do* differ, but the
difference is intentional rather than a defect, so this is **not** a third instance of the
class. `device_host_count` is counted from the raw payload's `host.intf` and excludes the
Firewalla box itself, because the box is the gateway rather than a client of any one
network. The overview's `host_count` is counted over the normalized inventory and includes
it, which is exactly why `online` and `offline` reconcile against it and why it cannot
simply be replaced by the other.

The real defect is smaller and sharper: **two different quantities were published under one
name.** The fix is a rename, so it moves to Phase 3. Two things were learned trying to fix
it in Phase 2:

- Publishing the box's number beside ours was attempted and **reverted**. The vocabulary
guard rejected `device_host_count` as a published key, because it names a host as a
"device" — the guard catching a real naming problem in a key that had existed for a while
as a *model field* and never as a published name. That is the evidence the fix is a naming
decision rather than an additive one.
- The comment was worse than the code. It asserted the overview's count *was* the entity's,
which was false. It now states why the two differ and why they are not interchangeable.

### Q9. What is the break policy, now that services and tools are in scope?

**Answered by the owner, and it governs every phase: no shims, no wrappers, no deprecation
periods.** Services and LLM tools have no consumers, so there is nothing to protect; a field
that needs a new name is renamed and the change is declared breaking. Entity attributes get
the same policy — a rename is a rename — but with the most careful migration documentation,
because templates may exist.

**The obligation that replaces compatibility work:** every rename lands with a row in
`USER_GUIDE.md`'s migration table and an entry in `RELEASE_CHECKLIST.md` §4. See §2's change
policy for the full statement.

### Q10. Does naming consistency across surfaces bind service fields too?

`runtime_inventory` publishes `pause_until` as an epoch float while the rule switch and
`get_rules` publish ISO — the same name, two formats.

**Recommendation:** yes. Service time fields are in scope (Q9), and this specific case is a
**name collision with an entity attribute** — the worst kind, because one name means two
things depending on which surface a user reads. Resolved in Phase 3.5, and the twin added in
3.2 means nothing is lost.

**CLOSED 2026-10-06 — left as is by owner decision.** `pause_until` keeps its epoch form in
the runtime inventory and its ISO form on the rule switch and in `get_rules`.

**The residual is recorded rather than treated as resolved, because it is a real
inconsistency and not a preference:** the same name carries two formats depending on which
surface a reader looks at. A caller that reads `pause_until` from `get_rules` and then from
the runtime inventory must handle both a string and a number under one name. The decision
accepts that rather than churn the field; it does not make the two formats agree, so nobody
should read this as the collision having gone away.

### Q11. Was the earlier reading of the owner's instruction wrong?

**Yes, and this is recorded rather than quietly corrected.** The plan's first draft treated
service and LLM time fields as "reference only" on the reading that the instruction *not to
worry about them* meant they were out of scope. The actual instruction was narrower: **do not
worry about legacy compatibility for consumers**, not "do not touch the fields".

The distinction matters in both directions, which is why it is written down:

- **What it does not mean:** leave three competing naming patterns standing, or leave
  `last_active` as a raw float on the service surface, on the grounds that nobody consumes
  it. Nobody consuming it is the *reason it is free to fix*, not a reason to skip it.
- **What it does mean:** no shim, no alias, no dual-write. The work gets *simpler*
  because the compatibility layer is ruled out, not cheaper because the work is skipped.

Under the corrected scope the service and tool surface becomes its own phase (Phase 3),
executed before the entity surface (Phase 4) so the entity renames follow one existing
precedent.

### External dependency

A local Home Assistant instance and the Firewalla box are needed to verify. Both are
available. No upstream or protocol dependency; every finding here is from local
measurement.

### Decisions taken

| # | Decision | Date |
| --- | --- | --- |
| Q1 | `last_active` → `last_active_at`, declared breaking, no shim | 2026-10-06 |
| Q9 | No shims, wrappers, aliases or deprecation anywhere; documentation is the compatibility | 2026-10-06 |
| Q11 | Service and LLM time fields are **in scope**; free to rename because nothing consumes them | 2026-10-06 |
| Q4 | Basis goes on the **envelope**, plus per-row `stale` — a frame is per-response, a fact is per-row | 2026-10-06 |
| Q5 | `stale` is always published, `null` included, because it is part of the online rule | 2026-10-06 |
| Q6 | Only the **three** surfaces with a derived value get a basis, not all eight that mention a host | 2026-10-06 |
| Q8 | Not a defect: two intentional quantities under one name. Fix is a rename, moved to Phase 3 | 2026-10-06 |
| Q2 | Mechanical: `<iso_name>_timestamp`, matching the five pairs already in the code | 2026-10-06 |
| Q3 | Closed — `_start` / `_end` stay; renaming would cost clarity, not buy it | 2026-10-06 |
| Q6 | Superseded by the scoped/flat decision below for the nested case | 2026-10-06 |
| Q10 | **Reversed 2026-10-06** — `pause_until` is ISO on both surfaces with a twin; the leave-as-is option was unrepresentable | 2026-10-06 |
| Q12 | **Scoped naming permitted in service and tool responses; entity attributes flat** | 2026-10-06 |

**No open questions remain.** Q6 is recorded as superseded rather than closed because the
scoped/flat decision governs the nested case it was asking about, and leaving both would have
left two answers in the plan.

**Q12 is a new question, and it is answered but not yet fully applied.** It arose from the
Phase 3 pre-analysis rather than from §3, so it has no section of its own: the decision is
stated in Phase 3's pre-analysis, the collision it exposes is `build_rule_hit_attributes`, and
the guard `test_entity_instants_name_their_concept` now enforces it. Applying it is Phase 3.1
and Phase 4.

---

## 4. Phase summary table

| Phase | Name | Deliverable | Gate |
| --- | --- | --- | --- |
| **1** | The rule, the helper, and the checks | The three concepts stated in `DEVELOPMENT_STANDARDS.md`, one `iso_instant()` helper, and two guard tests that **fail on today's payload** | **MET** — guards failed for their intended reasons, recorded in the supporting note §9; no published value changed |
| **2** | Publish the basis | Reference instant, applied window and `stale` on every windowed surface — the connectivity entities, the count attributes, and the three service envelopes | **MET** — three guards pass, each proven non-vacuous; additive only, no existing key changed. Two plan errors found and corrected (see §5) |
| **3** | Converge the service and tool surfaces | Every service instant named and paired, on one rule with two families; the shared bare-key builder named | **MET** — the bare-name guard passes outright; the twin guard's remaining gaps are all entity-side. Two plan predictions were wrong (see §5 Phase 3) |
| **4** | Converge the entity surface | `last_active_at` + twin, `fired_at` format repaired, twins added for every ISO-only entity instant, all conversions routed through the helper | Every entity instant has both forms under the same one pattern; breaks recorded in the migration table |
| **5** | Close the loop | `USER_GUIDE.md`, `RELEASE_CHECKLIST.md`, quality-scale check, and the guard extended to entity attributes | Docs match the payload; the guard covers entities, not just service responses |

Phases are sequential, and **1 → 2 → 3 → 4 → 5 is deliberate**:

- **1 first** because it is the contract, and because both guards must be shown failing
  before anything is trusted to pass.
- **2 second** because it is purely additive and closes the agent-facing failure without a
  single breaking change. If the initiative stopped here, the correctness problem would
  already be solved.
- **3 before 4** because the service and tool surfaces can be converged freely — no
  consumers — and doing them first means the entity renames cite **one** precedent instead
  of choosing between the three that exist today.
- **4 after 3** because it is the only phase with a compatibility surface, and it should be
  the last thing that breaks.

**Phase 1 is not optional and is not documentation busywork** — it is what makes Phases 3
and 4 mechanical and gives Phase 2 something to be checked against.

---

## 5. Phase details

### Phase 1 — The rule, the helper, and the checks — **COMPLETE**

Purpose: write the contract and prove it fails before changing any value.

**Done in one commit.** 796 tests pass, 3 held as `xfail(strict=True)`, `ruff` /
`ruff format` / `mypy` clean. No published value changed. The measured guard output is
recorded in the supporting note §9.

- [x] **1.1 State the three concepts** in the *Time and timezone standards* section of
      `docs/DEVELOPMENT_STANDARDS.md`: **instant**, **duration**, and **windowed state**,
      plus the closed suffix set (`_at`, `_until`, `_timestamp`, `_seconds`, `_start`,
      `_end`) and the reproducibility rule as a blockquote. Two worked examples were added
      rather than the rule alone — the `online: false` beside a 6.6-minute-old
      `last_active`, and the peers-measured-against-themselves defect — because the failure
      is much easier to recognise than to describe. The existing timezone bullets were kept
      intact under their own heading; they were never wrong.
- [x] **1.2 Record the non-equivalence** of `_seconds` and `_timestamp`, citing
      `uptime` / `uptime_seconds` as the duration exemplar, so a later reader does not
      "align" a pair that is already right.
- [x] **1.3 Add `iso_instant()` and `epoch_instant()`** to `utils/values.py`. Both are
      idempotent — they accept epoch seconds, an ISO string, a numeric string, or a
      `datetime` — because a caller may hold either form and should not have to know which.
      Non-finite input (`nan`, `inf`) is rejected: `datetime.fromtimestamp` raises on both,
      so without the guard a malformed payload would crash an entity update instead of
      reporting a missing value. That was found by testing, not by reasoning.
- [x] **1.4 Write the pairing guard** in a new
      `tests/components/firewalla_local/test_time_contract.py`. **Deviation from the plan:**
      the plan said to extend `test_vocabulary.py`; a separate module was used instead,
      because that guard checks *names* and this one checks *facts about values*, and
      merging them would put two different rules behind one filename. It imports the
      vocabulary module's scanners, so nothing was duplicated. Found **six** real gaps.
- [x] **1.5 Write the reproducibility guard** — recomputes `as_of - last_active <= window`
      for every host row and compares it to the published `online`. Handles the three-state
      case: a host with no activity is skipped rather than asserted, since `online` may
      legitimately be `None` (Q6 note in the plan). Fails for `get_hosts` and
      `get_system_overview` alike.
- [x] **1.6 Prove both guards fail** — recorded verbatim in the supporting note §9, together
      with **two flaws the guards themselves had on the first run**: the scanner read dict
      literals only and so missed every attribute added by subscript assignment (ten keys in
      `switch.py`, none of them `pause_until`), and the service-call helper passed `refresh`
      to a service that does not accept it. Both were caught by the anti-vacuity check, which
      is the case for having one.

**Held, not skipped.** The three failing guards carry `xfail(strict=True)` with a reason
naming the phase that resolves each. They fail today, so the suite is green; when Phase 2
and Phases 3–4 make them pass, `strict=True` turns that into a suite failure, so the marker
cannot outlive the work.

**Gate met:** both guards failed for their intended reasons before any value changed, the
output is recorded, and the suite is green with the failures held rather than hidden.
- [x] **1.5 Write the reproducibility guard** — for every published windowed boolean,
      recompute `reference - <row>_timestamp <= window` and assert it equals the published
      boolean. This is the assertion that would have caught the VPN contradiction. It must
      handle three states, not two: the value can be `None` as well as true or false
      (`is_host_online` returns `None` when no host anywhere carries a timestamp, and
      `stale` is `null` for pseudo-hosts). A guard written for booleans only would fail
      spuriously on a quiet network and be relaxed until it meant nothing.
- [x] **1.6 Prove both guards fail on the current tree** and record the output in the
      supporting note. A guard that has never failed is not evidence.

**Gate:** the two guards fail for the right reasons on today's payload; `ruff`, `mypy` and
the suite are otherwise green; **no published value has changed**.

### Phase 2 — Publish the basis — **COMPLETE**

Purpose: make every derived windowed value checkable from the payload alone. Entirely
additive.

- [x] **2.1 One accessor returning the basis as a pair** — `FirewallaHostManager.activity_basis()`
      returns a `FirewallaActivityBasis(reference_at, window_seconds)`. The public
      `inventory_reference_activity()` was folded into it, so the reference cannot now be
      obtained without the window it pairs with. The three internal connectivity methods
      unpack it; `device_tracker_away_window_seconds` is deliberately *not* part of it,
      because presence is a wall-clock frame.
- [x] **2.2 Add the constants** to `const.py` — `ATTR_ACTIVITY_REFERENCE_AT`,
      `ATTR_ACTIVITY_REFERENCE_AT_TIMESTAMP`, `ATTR_ONLINE_WINDOW_SECONDS`,
      `ATTR_DEVICE_TRACKER_AWAY_WINDOW_SECONDS`. No fourth suffix was invented (Q3/Q7).
- [x] **2.3 Publish the basis on the connectivity entities** — the watched-device binary
      sensor and the device tracker. **Deviation:** the watched-user sensor does *not* get
      it. It publishes `last_active` as information, and its `native_value` is
      `total_minutes_today` — a calendar-window aggregate from the box, not a derived
      windowed boolean. There is no derived value there for a basis to explain, so adding
      one would be noise. Its instant still needs its epoch twin, which is Phase 4.
- [x] **2.4 Publish the basis on the count-bearing entities** — system status. The
      per-network binary sensor needs none: its `host_count` is `device_host_count`, an
      inventory count with no windowed boolean beside it.
- [x] **2.5 Update the three service responses' envelopes** — `get_hosts`,
      `get_system_overview`, and `get_runtime_inventory` (the basis lands in the inventory
      report's `summary`, beside the counts it explains). `get_hosts` host rows also gained
      `stale`, without which an `online: false` that the basis says should be `true` is
      unexplainable.
- [x] **2.6 Resolve Q8** — see below.

**Two decisions the work forced, both recorded because the plan's wording was wrong.**

1. **The reference is `activity_reference_at`, not `as_of`.** The plan said `as_of`, which
   takes none of the closed suffix set written in Phase 1 and would have been the first
   published temporal field to opt out of the convention it introduces. `measured_at` was
   rejected as actively misleading: it reads as "when the snapshot was taken", so a caller
   computing `now - last_active` from it gets a *different* answer than the published
   `online` — the exact defect this initiative exists to fix. `activity_reference_at`
   matches the code's own `reference_last_active`.

   **Its epoch twin is `activity_reference_at_timestamp`**, following Q2's mechanical rule
   and the five pairs already in the code. The first attempt used
   `activity_reference_timestamp`; the Phase 1 guard flagged it in two modules and it was
   renamed. Recorded because the slip is instructive: the same pull toward a prettier name
   that Q2 rejected is what produced it, one phase later, in the phase that was supposed to
   be the easy additive one.

2. **Q8 was not a bug, and its fix belongs in Phase 3.** `device_host_count` is counted
   from the raw payload's `host.intf` and **excludes the Firewalla box**, because the box
   is the gateway rather than a client of any one network. The overview's `host_count` is
   counted over the normalized inventory and **includes** it, which is why `online` and
   `offline` reconcile against it. They are two different questions, not two answers. The
   defect is that both were published under one name, and the fix is a rename — so it
   stays in Phase 3. Adding the box's number to the overview beside ours was attempted and
   reverted: the vocabulary guard rejected `device_host_count` as a published key for
   naming a host as a "device", which is the guard working correctly and the reason this is
   a naming decision rather than an additive one.

**Gate met.** All three Phase 1 basis guards pass and were proven non-vacuous (fed `{}`,
each fails). The twin guard is still `xfail(strict=True)` — untouched, as planned, because
it belongs to Phases 3 and 4. Suite: 799 passed, 1 xfailed. `ruff check`, `ruff format`
and `mypy` clean.

**Still open after Phase 2:** `USER_GUIDE.md` has not been updated with the new attributes.
Moved to Phase 5 rather than done here, so the guide is written once against the converged
names instead of twice.

**Finding handed to Phase 3 — the guard does not see `helpers/`.** `_CONTRACT_MODULES` is
`PUBLISHING_MODULES` plus `llm_tools_read.py`, and `PUBLISHING_MODULES` stops at the entity
platforms. `helpers/runtime_inventory.py` is therefore unscanned, which matters for two
reasons: it is where Q10's `pause_until` epoch/ISO collision lives, and Phase 2 published the
basis into its `summary`. The guard could not see either. Extending the module list is part of
Phase 3, and it will very likely surface gaps this inventory does not list.

### Phase 3 — Converge the service and tool surfaces — **COMPLETE**

Purpose: make the service and LLM surfaces obey the rule, and establish the single
precedent the entity phase then follows. Every change here is breaking by declaration and
carries no compatibility cost, because nothing consumes these responses yet.

**Pre-analysis (2026-10-06) — the inventory was taken from the guard and from `grep`, not
from this plan's own summary, and three of the items below were wrong as written.**

Four instant patterns actually exist, not three:

| # | pattern | example | site |
| --- | --- | --- | --- |
| 1 | `at` + bare `timestamp` | `last_hit.at` / `.timestamp` | `models.py:2030` |
| 2 | `<name>_at` + `<name>_at_timestamp` | `fired_at` / `fired_at_timestamp` | `services.py:1349` |
| 3 | bare `timestamp` + `timestamp_iso` | `sample.timestamp` | `services.py:1859`, `3775` |
| 4 | `<name>_timestamp_iso` | `begin_timestamp_iso` | `services.py:1291` |

Pattern 1 is a **fourth** pattern the plan did not list, and it is in the one place the plan
called the correct reference. Item 3.1 therefore cannot simply cite `build_rule_hit_attributes`
as already-correct: its `at` and `timestamp` are **bare**, carrying no concept name, so they do
not satisfy the closed suffix set Phase 1 wrote. It is correct *in a different style* — scoped
naming, where the concept is the parent key (`last_hit.at`).

**Answered the same day: scoped naming is permitted in service and tool responses; entity
attributes are flat.** The parent key supplies the concept in a nested response, so `at`
there is not ambiguous. An entity attribute is flat and has no parent, so `at` and `timestamp`
there are incomplete names rather than shorthand.

**The one place the two rules collide, and it is not resolvable by picking a side.**
`build_rule_hit_attributes` (`models.py:1982`) is called from **both** sides:

- `services.py:971` — the rule service payload, where scoped naming is fine.
- `switch.py:202` — `attributes[ATTR_RULE_LAST_HIT]`, an entity attribute, where it is not.

One builder, two consumers, opposite rules. Splitting it would duplicate a 35-field shape and
let the two drift, which is the drift the shared builder exists to prevent. The resolution is
to name the concept in the keys — `at` -> `matched_at`, `timestamp` -> `matched_at_timestamp` —
which is valid under **both** rules at once: scoped, because the parent still contextualises
it, and self-describing, because each key now says what it is an instant of. That is a 2-key
rename in one function, not a restructure.

**A guard now encodes the rule, because it could not be enforced by statement alone.**
`test_entity_instants_name_their_concept` scans the eight entity-publishing modules for a bare
`at` or `timestamp` key. It is `xfail(strict=True)` and currently flags exactly one module:
`models.py: ['at', 'timestamp']`. `models.py` is deliberately classified as an entity surface
rather than a service one — attributing the shared builder to the service half is the
attribution error that would put the defect straight back out of sight.

**A guard coverage hole, found while taking this inventory.** The suffix check uses
`endswith("_at")`, which `"at"` does not match, so bare `at` and bare `timestamp` are
invisible to it. That is how pattern 1 escaped a guard built to find exactly this. The guard
needs a second check for scoped names, or the style must be forbidden — either way it cannot
stay blind.

**Item 3.2 is already done and must not be redone.** It lists `tested_at`, `sampled_at`,
`fired_at`, `expires_at` and `synced_at` as needing epoch twins. They all already have them
(`services.py:987`, `1020`, `1350`, `1382`, `4632`). The only genuine gap on the service
surface is **`pause_until`**. The plan's list was written from the entity surface's gaps and
carried across without checking — the same assumption error as Q8.

- [x] **3.1 Converge the instant naming patterns** into one. Scoped nesting is allowed in
      service and tool responses, so "one pattern" means one way of **naming** an instant,
      not one payload shape.
- [x] **3.2 Pair every service instant that is ISO-only today** — verified list was
      **`pause_until` only**, now paired.
- [x] **3.3 Give every epoch-only service field an ISO form.** `get_hosts` → `last_active`
      is Phase 4; the `get_runtime_inventory` rule record is done here, including three
      fields whose *names* were also outside the closed set.
- [x] **3.4 Publish the basis on the remaining service surfaces** — **verified, nothing
      added.** All eight windowed report surfaces already publish `time_basis`, and none of
      them derives a connectivity boolean, so Phase 2's basis does not apply to them. The
      plan guessed "the flow report's window fields and the `get_user_usage` periods" as
      likely candidates; both already declare their window, so the guess was wrong in the
      harmless direction.
- [x] **3.5 Resolve the `pause_until` collision** (Q10) — **this one came back, see below.**
- [x] **3.6 Extend the guard's module list to include `helpers/`** — done, and it
      immediately found the collision in 3.5 rather than only after the fact.
- [x] **3.7 Align the LLM tool metadata** — `docs/MCP_TOOL_REFERENCE.md` now names
      `matched_at` / `matched_at_timestamp` and `pause_until_timestamp`.
- [x] **3.8 Run the Phase 1 guards** — the bare-name guard passes outright (its
      `strict=True` marker was removed); the twin guard still `xfail`s with every remaining
      gap entity-side.

**Two answers the work found, both different from what this plan predicted.**

1. **The naming rule has two coherent families, not one, and that is correct.** The plan
   said "one pattern". Convergence actually produces two, because they answer different
   questions and `time_period` already used the second:

   | family | shape | for | examples |
   | --- | --- | --- | --- |
   | **point** | `<concept>_at` + `<concept>_at_timestamp` | when something *happened* | `tested_at`, `fired_at`, `matched_at`, `sampled_at` |
   | **position** | `<boundary>` + `<boundary>_timestamp` | a named place in a **window** | `start`, `end`, `begin`, `anchor` |

   Both name their concept, both are in the closed suffix set, and `position` was already
   in the code as `start` + `start_timestamp`. Discovering it prevented a wrong rename:
   `time_basis` was first changed to `begin_at` + `begin_at_timestamp`, which was uniform
   with the point family and **inconsistent with `time_period` beside it**. Reverted to
   `begin` + `begin_timestamp`, which is a two-word change (drop `_iso`) instead of a
   six-word one. The general lesson is that "one pattern" was the wrong goal — the goal is
   **one rule for choosing** a pattern, and the rule is which question the value answers.

2. **Q10 could not survive contact with the guard, and was resolved rather than left.**
   The owner closed Q10 as leave-as-is on the reasoning that changing `pause_until` would
   cost more than it bought. Extending the guard to `helpers/` then showed the state was
   not merely inconsistent but **unrepresentable under the suffix rule**: the guard
   requires `<name>_timestamp` as the twin of an ISO `<name>`, and `runtime_inventory`
   published `pause_until` as an *epoch*, so its twin had no valid name. `expires_at` had
   the same defect — an `_at` key holding a number, with `expires_at` meaning a date in
   `services.py` and a number here.

   Both are ISO on both surfaces now, with `_timestamp` twins. This **reverses the Q10
   closure**, so it is recorded as a reversal rather than folded in quietly: the earlier
   decision was made without the guard being able to see the file, and the new evidence
   removes the option it chose. The residual Q10 accepted — one name, two formats — is
   gone as a side effect, which is the outcome the owner wanted from leaving it alone.

**Gate:** one naming pattern across services and LLM tools; every instant paired; every
windowed value carries its basis; no `_iso` suffix and no unscoped bare `timestamp` remains.
Breaks recorded in `USER_GUIDE.md` and `RELEASE_CHECKLIST.md` (finalised in Phase 5).

### Phase 4 — Converge the entity surface

Purpose: bring the entity attributes to the same rule the services now follow. This is the
only phase with a compatibility surface — users may have templates against these attributes
— so it gets the most careful migration documentation, and no shim.

**Q12 applies here in full: every entity instant is flat and names its concept.** There is no
parent key on an entity attribute to supply the concept, so `at` and `timestamp` are not
available as shorthand — the whole reason `build_rule_hit_attributes` has to lose them in
Phase 3.1. The guard `test_entity_instants_name_their_concept` covers this phase.

- [ ] **4.1 Repair `fired_at`** on the alarm binary sensor. It publishes a raw epoch float
      while the service publishes ISO under the same name — one name, two formats, one of
      them wrong. It becomes ISO with a `fired_at_timestamp` twin, matching what Phase 3
      settled.
- [ ] **4.2 Rename `last_active` to `last_active_at`** on the watched-device binary sensor,
      the device tracker and the watched-user sensor, and add `last_active_timestamp`
      (**Q1 — approved 2026-10-06**; two constant values cover all five attributes). The
      service surface publishes the same concept, so the name must match Phase 3.3 exactly:
      one concept, one name, whichever surface carries it.
- [ ] **4.3 Add the missing twins** for every ISO-only entity instant: `pause_until`,
      `tested_at`, `sampled_at`, and `runtime_data_updated_at` (Q2 for the last one's name).

      **`schedule_next_start` / `schedule_next_end` are excluded — settled 2026-10-06.**
      Both their names *and* their absence of twins stand. They are the one accepted exception
      to the twin rule, recorded here rather than left implicit so a later reader finding them
      untwinned knows it was decided. This does not contradict Q2's "no exceptions" ruling:
      that was about *deriving a name* from a rule, where any carve-out makes the derivation
      unsound, whereas this is about *which values are published at all*. Schedule window
      boundaries are read as dates in a schedule, not used for arithmetic against a reference
      instant.
- [ ] **4.4 Route every conversion through `iso_instant()`** — replace the 21 hand-rolled
      sites across `binary_sensor.py`, `device_tracker.py`, `sensor.py`, `switch.py`,
      `services.py`, `models.py` and `managers/integration_manager.py`. Two styles exist
      today (`datetime.fromtimestamp(t, UTC)` 12× and `dt_util.utc_from_timestamp(t)` 2×);
      one survives. Doing this after 3.4 means the service sites are already converted.
- [ ] **4.5 Confirm the naming convention holds across every entity pair**, by running the
      Phase 1 pairing guard and recording what it now covers.

**Gate:** every entity instant has both forms under the same one pattern the services use;
the pairing guard passes; the reproducibility guard still passes; every break is listed in
`USER_GUIDE.md`'s migration table and `RELEASE_CHECKLIST.md`.

**Execution note.** Phase 3 exists as its own phase for one reason: the service and tool
surfaces can be converged with no risk at all, and doing that *first* means Phase 4 cites a
pattern that already exists in the codebase rather than arguing one into being from three
competing examples. If Phase 4 is ever deferred, Phase 3 still stands on its own as a
completed improvement.

### Phase 5 — Close the loop

Purpose: make the standard operational and give the guards reach over the surface that
matters most.

- [ ] **5.1 Extend `USER_GUIDE.md`** — the *Upgrading* migration table gains the Phase 3
      **and** Phase 4 renames with old-to-new rows, and the attribute documentation gains
      the basis fields with one worked example showing how to recompute `online` in a
      template.
- [ ] **5.2 Extend `RELEASE_CHECKLIST.md`** §4's known-breaking-change block with both sets
      of renames, following the existing breaks/fix/not-affected/migration shape, and
      naming the no-shim policy so a reviewer does not ask for one.
- [ ] **5.3 Check the quality scale** — `docs-actions`, `action-exceptions` and
      `strict-typing` are the rules this could touch. Confirm none regresses; correct
      `quality_scale.yaml` only if implementation state actually changed.
- [ ] **5.4 Extend the guard's reach to entity attributes.** The Phase 1 guards should cover
      `ATTR_*` *values* as published keys, not only service-response literals, so an entity
      attribute cannot be added one-legged. This is the gap that let `pause_until` ship
      without its twin.
- [ ] **5.5 Review the standard against what was built** and correct the document where the
      implementation disagreed with it, the way Vocabulary Alignment §1 was corrected rather
      than quietly edited.

**Gate:** documentation matches the payload; the guards cover entities and services; no
quality-scale rule regressed.

---

## 6. Validation strategy

Run after each phase, from the repository root:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy custom_components/firewalla_local
python -m pytest tests/ -q
```

Phase-specific evidence, which is the part that matters:

- **Phase 1** — paste the failing guard output into the supporting note before implementing.
  Both guards must fail for the intended reason, not an import error.
- **Phase 2** — take a live `list_hosts` / `get_system_overview` response and recompute one
  host's `online` and one count by hand from the published fields only. Record the
  arithmetic. This is the acceptance test for the whole initiative.
- **Phase 3** — take a live service response before and after and show that no `_iso` suffix
  and no bare `timestamp` key remains, and that a previously epoch-only field now carries
  both forms. `get_flow_report` and `get_runtime_inventory` are the two with the most to
  change, so they are the evidence to record.
- **Phase 4** — before/after on a live entity attribute for `fired_at` and `last_active`,
  showing the same instant in both formats.
- **Guard enforcement** — for each new guard, inject the defect it exists to catch and
  confirm it fails. Every guard in this plan must be shown failing at least once; the
  repository has already established this standard (`test_vocabulary.py`, and the injected
  defects recorded in the vocabulary inventory note).
- **Regression watch** — the `device_tracker` window must remain independently configurable
  (default 15 minutes, distinct from the 5-minute connectivity window) and must keep using
  wall-clock. Phase 2 publishes its basis; it must not unify it.

A local Home Assistant restart is required to serve changed entity attributes. Restart, then
inspect one entity of each affected family through the developer tools template editor.

---

## 7. References

- `docs/DEVELOPMENT_STANDARDS.md` — *Time and timezone standards* (to extend),
  *Constant naming rule* / usage matrix (`ATTR_*` ownership), *one concept never gets two
  published names*.
- `docs/ARCHITECTURE.md` — *Vocabulary: `host`, with one exception*; the network
  `kind` / `network_kind` precedent for publishing a coarse and a specific value together.
- `tests/components/firewalla_local/test_vocabulary.py` — the scan-the-package pattern,
  `_published_key_literals()`, and the convention that every guard is proven to fail.
- `plans/completed/FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_COMPLETED.md` and its
  `_SUP_INVENTORY.md` — the immediate predecessor; §15 and §16 are the record of the
  measurement-over-assumption discipline this plan inherits.
- `custom_components/firewalla_local/utils/host_activity.py` — `reference_last_active`,
  `is_host_online`, `count_online_hosts`; the three inputs of every windowed value.
- `custom_components/firewalla_local/managers/host_manager.py` —
  `inventory_reference_activity`, `watched_device_online_window_seconds`,
  `device_tracker_away_window_seconds`.
- `docs/RULE_MODEL.md` — pause/resume state semantics, referenced because `is_paused` and
  `pause_until` are already a correct basis pair and are the shape to generalise.

---

## 8. Delivery note

Phases 1–5 are intended as five reviewable changes, not one. Phase 2 fixes an agent-facing
correctness failure and breaks nothing. Phase 3 is the large break, and it is free — no
consumers, no shims, one naming pattern established. Phase 4 is the careful break, and it is
now approved rather than gated: the only remaining risk there is migration documentation,
not a decision.

If only part of this ships, ship **Phases 1–3**: the rule, the basis, and the service and
tool surfaces converged. Together those make every value in the integration reproducible
from its own payload and leave exactly one instant naming pattern in the codebase, with the
entity surface as the only remaining consumer of the old shape.

**A note on the scope correction.** This plan's first draft had the service and LLM time
fields out of scope. They are in scope, and the corrected reading is recorded in Q11 rather
than edited away, because the misreading is instructive: "we do not need to worry about
these fields" was about **compatibility**, not about the fields. The distinction is what
turns three competing naming patterns from a documented status quo into a Phase 3 task, and
it is the difference between this plan being a formatting pass and being a correctness pass.

**A note on the Q1 approval.** `last_active` was the only instant whose name already existed
on a user-facing surface, which made it the obvious candidate for a grandfather clause. It
was approved anyway, and that is the more useful outcome than the rename itself: the suffix
rule now holds with no exception for the field that predates it, so no later instant can cite
`last_active` as precedent for special-casing. If the plan ships in phases, Phase 4.2 should
still land in the entity phase rather than being pulled early, because it is the change users
are most likely to notice and it deserves to land with the migration table, not ahead of it.
