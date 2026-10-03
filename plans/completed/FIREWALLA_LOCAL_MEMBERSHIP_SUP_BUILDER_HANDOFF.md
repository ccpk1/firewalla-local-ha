# Builder handoff: Membership — Phase 1 (semantics and the collection model)

> **STATUS: COMPLETE — executed 2026-10-02 on `feature/mcp-capabilities`, not a
> new branch.** Phase 1 shipped as part of PR #52 instead of a fresh
> `feature/membership-foundation` branch, per owner direction, because PR #52 is
> the only place `llm_tools_control.py` exists and Phase 4 needs it. Two parts of
> this handoff were superseded by owner decisions taken during execution and are
> annotated inline below: **1.1 was answered rather than captured**, and **no
> separate user-affiliation count was added**. The next increment is **Phase 2**.

**Target agent:** `Firewalla Builder`
**Plan:** `plans/completed/FIREWALLA_LOCAL_MEMBERSHIP_COMPLETED.md` (initiative: Membership Foundation and Device Assignment Control)
**Evidence:** `docs/REVERSE_ENGINEERING_WORKFLOW.md` Findings 41 and 42
**Contract:** `docs/ARCHITECTURE.md` → *Group and user collection rule*

## Purpose

Implementation-ready handoff to **start the membership initiative at Phase 1** — the
membership-semantics confirmation and the group/user collection model.

This handoff authorizes **Phase 1 only**. Phase 2 (the service), Phase 3 (the
accurate surface) and Phase 4 (assistant exposure) follow per the plan, each handed
off after the previous one is done and validated.

## Prerequisite: one owner-assisted step, and a branch decision

**1.1 cannot be done alone.** It requires the owner to place a device in a group and

then in a user in the Firewalla app while a runtime pull is taken. Do not guess the
answer or infer it from the app's UI layout. Ask the owner to perform the app steps;
you take the pull and record the result.

> **Superseded.** The owner answered 1.1 directly: the app permits exactly one
> membership per device. No capture was needed, and no clarifying step is
> outstanding.

**Branch decision.** Branch off **`main`** only after PR #52 (the MCP/LLM tool
surface) has merged. Phases 1–3 are independent of that PR and could run on a branch
off `main` today; **Phase 4 is not** — it edits `llm_tools_control.py`, which exists
only in PR #52. If Phase 4 is wanted before #52 merges, branch off
`feature/mcp-capabilities` instead and say so in the PR. Do not create a second,
divergent copy of the LLM tool modules.

```bash
git checkout main && git pull
git checkout -b feature/membership-foundation
```

Confirm the branch before touching code.

> **Superseded.** Owner chose the second option: work stayed on
> `feature/mcp-capabilities` so Phase 4 can follow in the same branch and PR #52 can
> be updated to include the membership work. No `feature/membership-foundation`
> branch was created, and no second copy of the LLM tool modules exists.

## Scope — Phase 1 (plan steps 1.1–1.7)

1. **1.1 Confirm multi-membership (owner-assisted).** One device into a group, then
   also into a user. Pull the runtime and record whether `host.tags` holds one entry
   or several. Record in `docs/REVERSE_ENGINEERING_WORKFLOW.md` as a numbered
   finding and close the blocking question in the plan.
2. **1.2 Choose the service signature** from 1.1 and write the decision into the plan
   **before** Phase 2 starts: `assign` + `remove` over a set if membership is multi,
   `set` + `clear` if it is single.
3. **1.3 Kind discriminator in the snapshot** — `FirewallaGroupRuntime` gains `kind`
   (`"group"` / `"user"`) and `user_id`, classified in
   `api/client.py::_normalize_group_inventory`.
4. **1.4 Consistent inventory report** — `RuntimeGroupRecord` gains the same fields;
   classify in `_build_group_inventory`; user entries take the user's name.
5. **1.5 Unify `affiliated_group_name`** across all four readers, and remove the
   choice-label branch that leaks a raw tag name.
6. **1.6 Reconciled counts** — `group_count` counts only `kind == "group"`. **No
   user-affiliation count is added:** owner direction, because each user maps 1:1 to
   one backing tag so a second field could only ever disagree through a defect. The
   user collection and `user_count` carry that population instead.
7. **1.7 Update model tests** for the new shape, including the legacy human-named
   tag case and the UUID-named case.

## The blocking question, and the fallback

**Can a host hold more than one membership at once?** Every captured write sent a
whole `tags` list, but every observed value was either `[]` or a single id. The
answer decides the service signature, not the model change — 1.3–1.7 land either way.

**If 1.1 cannot be completed now, do not stall the model change.** Model decision 1.2
as `set` + `clear` (whole-list replacement), which is faithful to the observed wire
behaviour and can be widened to `assign`/`remove` later without breaking callers.
Say in the PR that the question is still open and why.

## Source of truth

If this handoff conflicts with these, they win:

1. `docs/ARCHITECTURE.md` → *Group and user collection rule* (the contract)
2. `plans/completed/FIREWALLA_LOCAL_MEMBERSHIP_COMPLETED.md` §3, §3b and Phase 1
3. `docs/REVERSE_ENGINEERING_WORKFLOW.md` Findings 41 and 42
4. this handoff

## Non-negotiable guardrails

- **Classification is by linkage, never by name.** An entry is a `user` entry
  because its tag appears as a user record's `affiliatedTag`, not because of what the
  tag is called. 8 of 10 are UUID-named and 2 are legacy human labels; name-based
  logic misfires on both.
- **A user entry's display name is the user's name.** The backing tag's own name must
  never be rendered — it is a bare UUID or a stale legacy label.
- **Do not retire `_build_affiliated_user_lookup`.** It has two live callers
  (`api/client.py:1975`, `:2433`). It stops being used for *classification* only.
- **Do not rename the host field `group_name`.** Per-host resolution is already
  correct; the breakage is in the collection.
- **Do not touch `api/auth.py`.** Its `groups` concept is the cloud pairing model
  (`CloudGroupRecord`, `_LOGIN_FIELD_GROUPS`, the cloud groups endpoint). Unrelated,
  and a name collision trap.
- **No aliases, no compatibility shims, no deprecation period.** Owner direction:
  fix the model properly and call out the breaking changes in the release.
- **Fix the choice-label leak.** `user_manager.py:51-57` renders
  `f"{user.name} ({user.affiliated_group_name})"`, which with a UUID-named backing
  tag puts a **bare UUID into an options-flow label today**. This is a present-day
  user-visible defect, not cosmetics.
- **Work from the §3b inventory.** It lists every user/group consumer with the step
  that covers it, plus two verified non-consumers (`diagnostics.py`, the cloud
  groups). Do not re-derive it with grep alone — the host-facing and rule-facing
  consumers are not reachable by searching for `get_groups()`.

## Required implementation order

1. Branch (above).
2. 1.1 with the owner, or record it as open and take the fallback.
3. 1.2 signature decision written into the plan.
4. 1.3 model + client classification.
5. 1.4 inventory report.
6. 1.5 naming unification and the choice-label fix.
7. 1.6 counts.
8. 1.7 tests.
9. Run validation; stop.

## Done criteria (Phase 1 complete only when all hold) — ALL MET

- [x] Branch created, and the PR states which base it used. *(Stayed on
      `feature/mcp-capabilities`; PR #52 will state it.)*
- [x] The multi-membership question is **answered and recorded**. *(Owner: one
      membership per device.)*
- [x] 1.2's signature decision is written in the plan. *(One service, single-slot
      replace, four LLM tools.)*
- [x] `kind` and `user_id` exist on both the snapshot group type and the inventory
      record; classification is by `affiliatedTag` linkage.
- [x] A user entry's display name is the user's name in both the snapshot and the
      inventory report; no UUID or legacy tag label can reach a rendered surface.
- [x] `affiliated_group_name` has **one** meaning, and the choices label no longer
      appends a tag name. *(The helper was removed outright.)*
- [x] `group_count` excludes user affiliations. *(No separate affiliation count, by
      owner direction; `docs/ARCHITECTURE.md` was corrected to match.)*
- [x] Every row in §3b whose "covered by" is a Phase 1 step is satisfied.
- [x] Validation green (below).

## Validation

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy custom_components/firewalla_local
python -m pytest tests/ -v
```

Baseline before this work: **483 tests pass**, ruff/format/mypy clean. Phase 1
intentionally changed assertions that encoded the old shape. Two more had to change
than this handoff predicted: the usage-history **group-scope** test resolved its
target by the legacy tag label, so the fixture gained a genuine plain group and the
test now resolves that group. A failure anywhere else would have been a consumer
that was missed, not a test to update blindly — none occurred, which is the evidence
that §3b's inventory was complete.

**Post-Phase-1 result: 483 tests pass** (unchanged count), ruff/format/mypy clean.

## Stop points — ask rather than decide

- 1.1's result changes the service shape in a way §3 does not cover.
- A §3b consumer needs a behaviour change beyond the kind discriminator.
- The model change forces a decision the *Group and user collection rule* does not
  answer.
- Phase 4 is wanted before PR #52 merges.

> **Phase 1 outcome:** none of these triggered. Two plan corrections were found and
> folded in rather than decided silently — `_build_group_policy_controls` was only
> coincidentally correct, and the inventory's user index did not share the client's
> `type` filter. Both are now aligned, so the two modules cannot diverge.

## After Phase 1

Report results, then the initiative continues per the plan: **Phase 2** the
admin-gated membership service → **Phase 3** the accurate reported surface →
**Phase 4** the reversible LLM control tool. Each is handed off separately. Phase 2
additionally requires `translations/en.json` entries — this repository has no
`strings.json`, and `test_every_service_has_a_translation_and_no_orphans` fails
without them.
