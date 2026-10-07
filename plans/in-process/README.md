# In-Process Plans

Place active Firewalla implementation plans in this folder.

- Main plan: `INITIATIVE_NAME_IN-PROCESS.md`
- Supporting note: `INITIATIVE_NAME_SUP_[DESCRIPTOR].md`

Keep plans phase-based, executable, and tied to concrete files.

When an initiative completes, move its plan and supporting notes to `plans/completed/`
and rename the main plan to `INITIATIVE_NAME_COMPLETED.md`.

## Recent completions, newest first

- *Time and Derived State*, closed 2026-10-06 —
  `plans/completed/FIREWALLA_LOCAL_TIME_AND_DERIVED_STATE_COMPLETED.md` (the plan, all
  five phases complete) and
  `plans/completed/FIREWALLA_LOCAL_TIME_AND_DERIVED_STATE_SUP_ENTITY_INVENTORY.md` (the
  measured evidence behind it).
- *Flow Reporting Service*, closed 2026-10-06 —
  `plans/completed/FIREWALLA_LOCAL_FLOW_REPORTING_COMPLETED.md` (the plan, all four
  phases complete) and
  `plans/completed/FIREWALLA_LOCAL_FLOW_REPORTING_SUP_CONSUMER_AUDIT.md` (the audit
  behind Phase 1).
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

## What remains on this branch

Everything implemented is complete, guarded and documented. What is left is to push the
branch and cut the release.

The migration tables for the breaking renames now live in
`plans/in-process/RELEASE_NOTES_2.5.0_DRAFT.md`, which is the working source for the
GitHub release body. They were moved out of `docs/USER_GUIDE.md`, because they describe
one upgrade step rather than how the integration works. Confirm each item still matches
the code before publishing.

