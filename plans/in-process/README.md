# In-Process Plans

Place active Firewalla implementation plans in this folder.

- Main plan: `INITIATIVE_NAME_IN-PROCESS.md`
- Supporting note: `INITIATIVE_NAME_SUP_[DESCRIPTOR].md`

Keep plans phase-based, executable, and tied to concrete files.

When an initiative completes, move its plan and supporting notes to `plans/completed/`
and rename the main plan to `INITIATIVE_NAME_COMPLETED.md`.

**Two initiatives are in process.** The most recent *completed* initiative,
*Membership Foundation and Device Assignment Control*, finished on 2026-10-03 and is
archived in `plans/completed/`:

- `plans/completed/FIREWALLA_LOCAL_MEMBERSHIP_COMPLETED.md` — the initiative plan,
  all four phases complete.
- `plans/completed/FIREWALLA_LOCAL_MEMBERSHIP_SUP_BUILDER_HANDOFF.md` — the Phase 1
  handoff to `Firewalla Builder`, kept for the record of the decisions that
  superseded parts of it.

---

## Current initiatives

### 1. Flow Reporting Service

Delivered — all four phases complete and validated on `feature/flow-reporting`.

- `FIREWALLA_LOCAL_FLOW_REPORTING_IN-PROCESS.md` — the plan, every step closed.
- `FIREWALLA_LOCAL_FLOW_REPORTING_SUP_CONSUMER_AUDIT.md` — the existing-consumer
  audit behind Phase 1.

Held in process because it is **not yet released and not yet pushed**, and because
the vocabulary initiative below finishes work it started — it is where `target.kind`
first appeared.

### 2. Vocabulary Alignment

**Phase 1 complete** (`e675690`) — the register rule is stated in
`ARCHITECTURE.md` and `DEVELOPMENT_STANDARDS.md`, and `test_vocabulary.py` enforces
it with a 23-entry work list that each later phase shrinks. Phases 2–4 not started.

- `FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_IN-PROCESS.md` — the plan. States the
  register rule (`host` for machine surfaces, `device` for human prose), corrects the
  `ARCHITECTURE.md` section that states it wrongly, and adds a guard test with a
  shrinking allowlist so the remaining phases are mechanical rather than
  re-litigated.
- `FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_SUP_INVENTORY.md` — the audit as an
  exhaustive work list: every service's selectors, every response kind, the three
  `scope_kind` enums, the three `target_type` treatments, the twelve entity attribute
  values, the requested-then-discarded filters, and the churn estimate. §7 is the
  guard's literal output.

**Ordering note.** Vocabulary Alignment Phase 1 (documents and the guard test) can
run immediately. Its Phases 2–4 change `get_flow_report`'s `target.kind` and its
`include` value, so if both initiatives are worked at once, **Vocabulary Alignment
Phase 2 should land before the flow plan is pushed** — otherwise the flow plan's
recorded `target.kind: "device"` is published and then changed.
