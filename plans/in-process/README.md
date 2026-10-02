# In-Process Plans

Place active Firewalla implementation plans in this folder.

- Main plan: `INITIATIVE_NAME_IN-PROCESS.md`
- Supporting note: `INITIATIVE_NAME_SUP_[DESCRIPTOR].md`

Keep plans phase-based, executable, and tied to concrete files.

When an initiative completes, move its plan and supporting notes to `plans/completed/`
and rename the main plan to `INITIATIVE_NAME_COMPLETED.md`.

**Currently in process:** `FIREWALLA_LOCAL_MEMBERSHIP_IN-PROCESS.md` — membership
foundation (group/user kind discriminator) and the device membership service.
**Phase 1 is complete**; Phases 2–4 remain.

- `FIREWALLA_LOCAL_MEMBERSHIP_SUP_BUILDER_HANDOFF.md` — the Phase 1 handoff to
  `Firewalla Builder`. Phase 1 is now complete (executed on `feature/mcp-capabilities`
  as part of PR #52); the file records the outcome and the decisions that superseded
  parts of it, and is kept for the Phase 2–4 record.
