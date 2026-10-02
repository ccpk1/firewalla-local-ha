# Initiative: Membership Foundation and Device Assignment Control

## 1. Initiative snapshot

- **Trigger:** Reverse engineering on 2026-10-02 confirmed the full device membership
  write contract and disproved the assumptions behind the existing group data model.
  Findings 41 and 42 in `docs/REVERSE_ENGINEERING_WORKFLOW.md` are the evidence base.
- **What was learned, and why it forces a change:**
  1. **Group membership is writable locally.** It is a host-scoped `set` on
     `item: "policy"` writing `value.tags` as an integer tag-id list — the same
     writer already used for DHCP reservations and notification toggles.
  2. **User assignment is the same write.** The app performs it over the cloud, but
     the box represents it as the same `tags` list holding the user's affiliated
     backing tag. A local write of that tag is accepted, persists, and is reflected
     in the app. So one contract covers groups and users.
  3. **The group collection is not a group collection.** `groups[]`
     (`helpers/runtime_inventory.py`) and `snapshot.groups` (`api/client.py`) are
     built from the raw `tags` map, so they contain user backing tags as well as real
     groups. On the dev box that is **10 of 28** entries. The Firewalla app shows
     both in one list but separates them visually; it does **not** expose a user's
     backing tag as a selectable group.
  4. **Backing tag names are unreliable.** 8 of 10 affiliated tags are named with a
     bare UUID; 2 are legacy human-named labels (owner context: those two users
     predate Firewalla's current user model, when a user *was* a group). Rendering
     them leaks UUIDs or a stale label, and name-based classification misfires.
- **Decision taken (owner, 2026-10-02): mimic the app.** Keep one collection, add a
  `group` / `user` kind discriminator, and report group and user counts accurately.
  This is now recorded as the *Group and user collection rule* in
  `docs/ARCHITECTURE.md`.
- **Explicit owner direction:** no aliases, no compatibility shims, no deprecation
  period. Fix the model properly and call out the breaking changes.
- **Through-line:** *Fix the collection model → build one membership service →
  make the reported surface accurate → expose it to assistants.*

## 2. Scope and non-goals

**In scope**

1. Add a `group` / `user` kind discriminator to the group collection across the
   client snapshot, the inventory report, and the overview counts.
2. Give every user-backed entry the user's display name and affiliated user id.
3. Report group and user counts separately so they reconcile to the collection size.
4. Build one admin-gated service that assigns a device to a group or a user, and
   removes it from either.
5. Keep every existing entity surface that derives from membership working:
   watched-device `device_group`, device-tracker attributes, and watched-user
   associated-host joins.
6. Make `get_system_overview` report users and groups accurately.
7. Add a reversible LLM control tool backed by the new service, and update the
   prompt fragment and tool contracts.

**Non-goals**

- **No aliasing or compatibility layer.** Old shapes are replaced, not supported
  alongside. Breaking changes are called out in the release.
- **No cloud API client.** The cloud path is why the app's own user assignment is
  opaque; the confirmed local write makes it unnecessary.
- **No membership history or audit log.** Out of scope.
- **No new entity platforms.** Membership surfaces as attributes, service calls and
  LLM tools, not as new entities.
- **No rename of the Python field `group_name` on hosts** in this initiative;
  only the collection model changes. Host `group_name` already resolves to the
  user-facing identity and is correct.
- **No multi-group semantics invented.** Whether a device may hold several
  memberships is confirmed in Phase 1, not assumed.

## 3. Open questions / external dependencies

### Blocking (must be resolved before the dependent phase)

- **Can a host hold more than one membership at once?** Every captured write sent a
  whole `tags` list, but all observed values were either `[]` or a single id. The
  app dialog presents groups and users in sections, which is consistent with either
  a single selection or a multi-select. **This decides the service signature**
  (`assign`/`remove` over a set versus `set`/`clear`). Phase 1 resolves it with one
  targeted capture. **Fallback if it cannot be resolved:** model the service as
  `set` + `clear` (whole-list replacement), which is faithful to the observed wire
  behavior and can be widened later without breaking callers.
- **Does a plain group and a user assignment compose?** Related to the above. If a
  host can be in one group *and* one user, the collection memberships coexist and
  the service needs to preserve the untouched list members while replacing the one
  being changed. Phase 1 answers this too.

### Confirmed constraints (design around these)

- **The wire write is a full-policy replace.** The app sends the entire 16-key
  `host.policy` object, not a `tags`-only patch, and deliberately omits `dap`,
  `deviceTags` and `ssidTags` (the box preserves those itself). Any implementation
  must send the app-shaped 16-key object. Proven shape is in
  `.tmp/probe_membership.py::_POLICY_KEYS`.
- **Tag ids are integers in the write and strings in the read.** Both forms appear
  in the same protocol.
- **Removal is `value.tags: []`.** Verified equivalent on both the `[0]`-stripped
  path and an explicit empty list; the app clears the assignment either way.
- **The existing writer is reusable.** `FirewallaApiClient.async_set_host_policy`
  already performs the host-scoped `set` on `item: "policy"`. No new transport or
  command family is needed.
- **A stale lookaside helper exists.** `_build_affiliated_user_lookup` only records
  a tag when the user **has a name**, so it cannot be used as the exclusion or
  classification set. Classification must read `affiliatedTag` from user records
  directly.
- **Entity surfaces already resolve to the user-facing identity.**
  `_resolve_host_group_name` maps an affiliated tag to the user's name, so
  watched-device and device-tracker attributes are correct today. The breakage in
  the current model is in the **collection**, not in per-host resolution.

### Known inconsistency to fix (not an open question, a defect)

`affiliated_group_name` means three different things today:

| Location | Current value |
| --- | --- |
| `api/client.py::_normalize_user_inventory` | the **tag's** raw name |
| `helpers/runtime_inventory.py::_build_user_inventory` | the **user's** name |
| `managers/user_manager.py::_build_watched_user_view` | the **user's** name (forced) |

The client-side value is the one that can surface a UUID or a legacy label. One
meaning must win, and the rule in `docs/ARCHITECTURE.md` says it is the user's name.

## 4. Phase summary

| Phase | Focus | Key output |
| --- | --- | --- |
| 1 | Resolve membership semantics and land the model | Confirmed single/multi membership; `kind` + `user_id` on the collection; consistent naming |
| 2 | Build the membership service | One admin-gated service for assign/remove across groups and users, with validation and tests |
| 3 | Make the reported surface accurate | Corrected overview counts, verified entity joins, updated read-tool text |
| 4 | Expose it to assistants | Reversible LLM control tool, prompt fragment, contracts and docs |

## 5. Phase details

### Phase 1 — Membership semantics and the collection model

Goal: confirm how many memberships a host may hold, then land the data-model change
so every later phase builds on a correct foundation.

- [ ] **1.1 Confirm multi-membership.** With the owner, use the app to place one
      device in a group and then also in a user (and vice versa), and pull the
      runtime. Record whether `host.tags` holds one entry or several. Capture with
      the widened lane if the app uses the cloud path. Record the result in
      `docs/REVERSE_ENGINEERING_WORKFLOW.md` and close the blocking question.
- [ ] **1.2 Choose the service signature** from 1.1: `assign` + `remove` over a set
      if membership is multi, or `set` + `clear` if it is single. Write the decision
      into the plan before starting Phase 2.
- [ ] **1.3 Add the kind discriminator to the snapshot.** In
      `custom_components/firewalla_local/models.py`, extend `FirewallaGroupRuntime`
      with `kind` (`"group"` / `"user"`) and `user_id: str | None`. Update
      `api/client.py::_normalize_group_inventory` to classify by reading
      `affiliatedTag` from the user records directly, and to set the display name
      from the user record for user entries. Leave `_build_affiliated_user_lookup`
      untouched for its existing consumer, or retire it if Phase 3 finds no caller.
- [ ] **1.4 Make the inventory report consistent.** In
      `helpers/runtime_inventory.py`: add `kind` and `user_id` to
      `RuntimeGroupRecord`, classify in `_build_group_inventory`, and set a user
      entry's `name` to the user's name. Update the markdown group section to show
      the kind. Keep `group_policy_controls` as-is — it already skips the
      `userTags` key, so user entries contribute nothing.
- [ ] **1.5 Unify `affiliated_group_name`.** Pick one meaning — the user's name, per
      `docs/ARCHITECTURE.md` — and apply it in `api/client.py`,
      `helpers/runtime_inventory.py`, and `managers/user_manager.py`. Remove the now
      dead `name (group)` branch in `user_manager.py` if the values are always
      equal.
- [ ] **1.6 Report reconciled counts.** In `helpers/runtime_inventory.py`, change
      `group_count` to count only `kind == "group"` and add a user-affiliation
      count. Note in code that each user maps 1:1 to exactly one backing tag, so a
      user-affiliation count equals the user count by construction.
- [ ] **1.7 Update model tests.** Update `test_runtime_inventory.py`,
      `test_client.py`, and any fixture asserting on `groups[]`, `group_count`, or
      `affiliated_group_name`, including the legacy human-named-tag case (classified
      `user`, displayed with the user's name) and the UUID-named case.

### Phase 2 — The membership service

Goal: one admin-gated service that changes a device's group or user membership.

- [ ] **2.1 Add constants.** In `custom_components/firewalla_local/const.py`: the
      service name, the membership kind field, the membership target field, and
      translation keys for the new validation failures. Reuse
      `SERVICE_FIELD_MODE`, `SERVICE_FIELD_HOST_MAC`, `SERVICE_FIELD_HOST_NAME`,
      `SERVICE_FIELD_REFRESH`, and the config-entry selectors.
- [ ] **2.2 Build the app-shaped policy payload.** Add a helper that reads the
      host's current raw policy, preserves the app's 16 keys, and replaces only
      `tags`. Do not reuse `_build_host_ip_allocation_policy_value`, which is
      allocation-specific. Base it on the proven shape in
      `.tmp/probe_membership.py`.
- [ ] **2.3 Resolve the membership target.** Accept a target by id or by name and
      resolve it against the classified collection, so a caller can pass either a
      group name or a user name. Reject ambiguous matches and unknown targets with
      translated errors, following the existing selector-resolution pattern in
      `services.py`.
- [ ] **2.4 Implement the handler.** In `services.py`, add the schema and the
      handler, then register it in `_SERVICE_REGISTRATIONS` as admin-gated with
      `SupportsResponse.ONLY`. Write through the existing
      `integration_manager` → `async_set_host_policy` path. Preserve list members
      the caller did not touch when membership turns out to be multi (Phase 1).
- [ ] **2.5 Document the service.** In `services.yaml`, follow the existing host
      service style — description, field descriptions, example values, and the
      translation-ready wording used by the other host-setting services. Reference
      the service from the host-actions section of `docs/USER_GUIDE.md`.
- [ ] **2.6 Promote the probe.** Move the proven write probe out of gitignored
      `.tmp/` into a tracked utility alongside the capture tooling, so the contract
      is reproducible. Keep it dry-run by default, matching
      `utils/probe_alarm_control.py` and `utils/probe_internet_quality.py`.
- [ ] **2.7 Tests.** Cover: assign to a group, assign to a user, remove each,
      unknown target rejected, ambiguous target rejected, tag-id type handling,
      and that the payload sent is the app-shaped key set with only `tags` changed.

### Phase 3 — Accurate surface and preserved entity behavior

Goal: make the reported surface correct without breaking anything downstream.

- [ ] **3.1 Fix the overview counts.** In
      `services.py::_async_handle_get_system_overview`, report the group count from
      the classified collection and add the user-affiliation count. Confirm
      `include: ["identifiers"]` items carry the kind so a consumer can tell them
      apart. Existing tests at `test_services.py:3700,3819,3821` need updating.
- [ ] **3.2 Audit the entity surfaces.** Verify that watched-device
      (`binary_sensor.py:806`), device-tracker (`device_tracker.py:187`), and
      watched-user (`sensor.py:536`) attributes are unchanged in meaning and that
      the user-facing identity rule still holds for a device in a legacy
      human-named backing tag. Add a regression test using a legacy-shaped fixture.
- [ ] **3.3 Audit the association joins.** Confirm
      `managers/user_manager.py::_get_associated_hosts_for_user` still resolves
      associated devices through the backing tag id in `host.group_ids`, and that
      the 1:1 user-to-tag invariant is documented where it is relied on.
- [ ] **3.4 Audit remaining group consumers.** Grep for every use of
      `snapshot.groups`, `get_groups()`, and `groups[]`, and confirm each consumer
      either uses the kind or is provably unaffected. **One consumer needs a real
      fix:** `services.py::_resolve_usage_history_target` (line 3112, reached from
      `_async_handle_get_time_usage_report` at line 4749) resolves a
      `scope_kind="group"` request against `get_groups()` and matches on
      `group.name`. Once a user-backed entry carries the user's name, a group-scoped
      request can resolve to a user's backing tag and return that user's usage
      labelled as a group. The group branch must skip entries whose kind is `user`
      (and the `user` branch continues to resolve users through the user manager).
      Add a test that a group-scoped request with a user's name is rejected rather
      than silently resolved.
- [ ] **3.5 Update read-tool text.** Adjust `llm_tools_read.py` strings that
      describe `group_name`/`group` so they state that the collection holds groups
      and users and that the kind distinguishes them.
- [ ] **3.6 Re-run the full suite** and confirm no entity or service snapshot drifts
      for reasons other than the intended count and kind changes.

### Phase 4 — Assistant exposure

Goal: let an assistant change a device's membership as a reversible control.

- [ ] **4.1 Add the control tool.** In
      `llm_tools_control.py`, add a tool following the
      `SetHostDhcpReservationTool` pattern — reversible annotations, host selector
      plus membership selector, delegating to the new service with
      `_returns_response = True`. Register it in `_CONTROL_TOOL_CLASSES` (not the
      destructive list) since it is reversible.
- [ ] **4.2 Update the prompt fragment.** In `llm_tools_common.py`, note that a
      device's membership can be changed, that groups and users are both valid
      targets, and that the change is reversible.
- [ ] **4.3 Document the contract.** Add the tool to
      `docs/MCP_TOOL_REFERENCE.md` in the existing per-tool format, using the same
      annotation and availability fields as its neighbours.
- [ ] **4.4 Tests.** Cover the tool's schema, its service delegation, its
      response envelope, and its registration tier. Update
      `test_llm_contract.py` if it asserts an exact tool count or list.
- [ ] **4.5 Verify availability tiers.** Confirm the tool appears at
      read-and-control and above and not in summary-only, consistent with the other
      reversible controls.

## 6. Validation strategy

- **Per phase:** `python -m ruff check .`, `python -m ruff format .`,
  `python -m mypy custom_components/firewalla_local`, `python -m pytest tests/ -v`.
- **Phase 1 is the highest-risk phase.** It changes a published shape that entities
  and services read. Do not start Phase 2 until the full suite is green, and treat
  any failing test as a signal that a consumer was missed rather than a test to
  update blindly.
- **Live verification:** after Phase 2, run the service against the dev box for
  assign-to-group, assign-to-user, and remove, and confirm each in the Firewalla
  app. Membership writes are trivially reversible, so a live check is safe and is
  the strongest evidence the contract still holds.
- **Contract checks:** confirm the write sends the app-shaped key set, integer tag
  ids, and that removal sends an explicit empty list.
- **Regression focus:** legacy human-named backing tags, UUID-named backing tags,
  real groups, and a device with no membership.

## 7. Breaking changes to call out

- `groups` / `groups[]` entries gain `kind` and `user_id`, and a user-backed entry's
  `name` changes from the raw tag name to the user's name.
- `group_count` shrinks to real groups only; a user-affiliation count is added.
- Any consumer summing `group_count` to get a collection total must switch to the
  two counts or the collection length.

## 8. References

- `docs/ARCHITECTURE.md` — *Group and user collection rule* (the contract this plan
  implements) and the existing *Identity presentation rule*.
- `docs/REVERSE_ENGINEERING_WORKFLOW.md` — Finding 41 (group membership write
  contract), Finding 42 (user assignment is cloud-mediated but locally writable;
  backing-tag name trap), and the standard and widened capture workflows.
- `docs/DEVELOPMENT_STANDARDS.md` — user-facing identity rules.
- `docs/MCP_TOOL_REFERENCE.md` — the per-tool documentation format for Phase 4.
- Code: `api/client.py` (`_normalize_group_inventory`, `_normalize_user_inventory`,
  `_build_affiliated_user_lookup`, `async_set_host_policy`),
  `helpers/runtime_inventory.py` (`_build_group_inventory`, `_build_user_inventory`),
  `managers/user_manager.py` (`_get_associated_hosts_for_user`,
  `_build_watched_user_view`), `models.py` (`FirewallaGroupRuntime`),
  `services.py` (`_resolve_usage_history_target`, `_async_handle_get_system_overview`),
  `llm_tools_control.py`, `llm_tools_common.py`, `llm_tools_read.py`.
- Tests: `test_runtime_inventory.py`, `test_client.py`, `test_services.py`,
  `test_init.py`, `test_sensor.py`, `test_llm_contract.py`.
- Evidence artifacts: `.tmp/probe_membership.py`, `.tmp/firewalla_membership_capture.pcap`,
  the widened cloud capture and its before/after runtime pulls under `.tmp/`,
  all documented in `docs/REVERSE_ENGINEERING_WORKFLOW.md` Finding 42.
