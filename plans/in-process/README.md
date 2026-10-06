# In-Process Plans

Place active Firewalla implementation plans in this folder.

- Main plan: `INITIATIVE_NAME_IN-PROCESS.md`
- Supporting note: `INITIATIVE_NAME_SUP_[DESCRIPTOR].md`

Keep plans phase-based, executable, and tied to concrete files.

When an initiative completes, move its plan and supporting notes to `plans/completed/`
and rename the main plan to `INITIATIVE_NAME_COMPLETED.md`.

Completed initiatives are archived in `plans/completed/`. Recent ones:

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

## Latest completed initiative

### Time and Derived State

All five phases complete and validated on `feature/flow-reporting`. Moved to
`plans/completed/`.

- `FIREWALLA_LOCAL_TIME_AND_DERIVED_STATE_COMPLETED.md` — the plan, every phase closed. Stated one
  rule for instants, durations and derived state; published the basis for every windowed
  value on both service and entity surfaces; and converged the instant naming patterns behind
  guards that assert reproducibility, not just presence.
- `FIREWALLA_LOCAL_TIME_AND_DERIVED_STATE_SUP_ENTITY_INVENTORY.md` — the measured evidence:
  the live `vpn_hosts` contradiction, the entity families that derive a value without
  publishing its inputs, the ISO-only entity instants, and the competing service naming
  patterns.

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
preference, and removes the precedent a later field could cite for special-casing.

**All five phases landed 2026-10-06.** Two decisions were reversed mid-flight with the
reversal recorded rather than folded in: Q10 (`pause_until` left as-is, then found to be
*unrepresentable* once the guard could see `helpers/`) and, in Phase 2, the epoch twin's own
name, which the Phase 1 guard caught. Both are documented in the completed plan.

---

## What remains on this branch

Everything implemented is complete, guarded and documented. What is left is to push the
branch and cut the release. Both initiatives' migration tables are written and verified
(`docs/USER_GUIDE.md` and `docs/RELEASE_CHECKLIST.md` §4), so the release notes are
transcription rather than authoring.

