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

