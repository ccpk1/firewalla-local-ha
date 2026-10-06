# In-Process Plans

Place active Firewalla implementation plans in this folder.

- Main plan: `INITIATIVE_NAME_IN-PROCESS.md`
- Supporting note: `INITIATIVE_NAME_SUP_[DESCRIPTOR].md`

Keep plans phase-based, executable, and tied to concrete files.

When an initiative completes, move its plan and supporting notes to `plans/completed/`
and rename the main plan to `INITIATIVE_NAME_COMPLETED.md`.

**One initiative is in process.** The two most recent *completed* initiatives are
archived in `plans/completed/`:

- *Vocabulary Alignment*, closed 2026-10-06 —
  `plans/completed/FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_COMPLETED.md` (the plan, all four
  phases complete) and
  `plans/completed/FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_SUP_INVENTORY.md` (the audit;
  §9–§16 are the design record — the measured state, the capture that resolved
  rule-scope writes, the `device_*` measurement, and the three sweeps that each
  produced a different class of bug).
- *Membership Foundation and Device Assignment Control*, finished 2026-10-03 —
  `plans/completed/FIREWALLA_LOCAL_MEMBERSHIP_COMPLETED.md` (the plan, all four phases
  complete) and `plans/completed/FIREWALLA_LOCAL_MEMBERSHIP_SUP_BUILDER_HANDOFF.md`
  (the Phase 1 handoff to `Firewalla Builder`, kept for the record of the decisions
  that superseded parts of it).

---

## Current initiatives

### 1. Flow Reporting Service

Delivered — all four phases complete and validated on `feature/flow-reporting`.

- `FIREWALLA_LOCAL_FLOW_REPORTING_IN-PROCESS.md` — the plan, every step closed.
- `FIREWALLA_LOCAL_FLOW_REPORTING_SUP_CONSUMER_AUDIT.md` — the existing-consumer
  audit behind Phase 1.

Held in process because it is **not yet released and not yet pushed**. The vocabulary
initiative that finished work it started — it is where `target.kind` first appeared — is
now closed, so there is nothing left to sequence against it.

### 2. Time and Derived State

Planned — Phase 0 (research) complete, no phase started. Open for pressure-testing.

- `FIREWALLA_LOCAL_TIME_AND_DERIVED_STATE_IN-PROCESS.md` — the plan, five phases. States one
  rule for instants, durations and derived state; publishes the basis for every windowed
  value on both service and entity surfaces; and converges the instant naming patterns behind
  a guard that asserts reproducibility, not just presence.
- `FIREWALLA_LOCAL_TIME_AND_DERIVED_STATE_SUP_ENTITY_INVENTORY.md` — the measured evidence:
  the live `vpn_hosts` contradiction, the eight entity families that derive a value without
  publishing its inputs, the six ISO-only entity instants, and the three competing service
  naming patterns.

**Sequencing note, and a correction.** This initiative was opened to fix two defects found
on the live box — `vpn_hosts` reporting `online: 1` while `list_hosts` reported all five
peers offline, and `last_active` published as an unreadable epoch. The first defect's root
cause was fixed immediately (`5113793`): `count_online_hosts` derived its reference from
whatever subset it was handed, so a subset became its own clock. **The plan is therefore not
about fixing that bug** — it is about the rule, the basis publication and the guards that
stop the next one, since the same class of defect had already survived two prior
normalization passes.

**Scope correction, recorded in plan Q11.** The first draft had service and LLM time fields
out of scope, reading "we do not need to worry about these fields" as a scope instruction.
It was a compatibility instruction: **no shims and no deprecation, but the fields are fully
in scope.** So the service and tool surfaces became their own phase (Phase 3), executed
*before* the entity phase, because they have no consumers and can therefore be converged with
no cost — establishing the one naming precedent the entity renames then follow.

**Staged by risk, not by size.** Phase 1 (rule and guards) and Phase 2 (publish the basis)
change no existing value. Phase 3 is a large break that is entirely free. Phase 4 is the only
phase with a compatibility surface — entity attributes — and gets the fullest migration
documentation. No phase introduces a shim.

**Q1 approved 2026-10-06:** `last_active` → `last_active_at`, declared breaking, no shim.
It was the only instant whose name predated the convention, so it was the natural candidate
for an exception — approving it instead makes the `_at` suffix a rule rather than a
preference, and removes the precedent a later field could cite for special-casing. Phase 4
is therefore no longer gated on a decision; only its migration documentation remains as work.

---

## Sequencing across initiatives

Both open initiatives touch the same branch. Order that avoids rework:

1. **Time and Derived State Phases 1–2** — the rule, the guards and the basis. Additive; no
   published value changes; closes the agent-facing unverifiability. Independent of Flow
   Reporting.
2. **Time and Derived State Phase 3** — service and tool convergence. Breaking, free, and
   worth doing before any release note is written, because it removes three competing naming
   patterns from the same package the entity work then cites.
3. **Flow Reporting push** — its four phases are complete and it is only held for release, so
   it can go whenever the branch is being pushed.
4. **Time and Derived State Phases 4–5** — the entity renames and the documentation close.
   Do these *after* the release decision so the migration table lands once rather than being
   rewritten against a moving target.

If only one thing ships, ship Time and Derived State Phases 1–3: the rule, the basis, and one
instant naming pattern across every service and tool, which together make every value in the
integration reproducible from its own payload.

