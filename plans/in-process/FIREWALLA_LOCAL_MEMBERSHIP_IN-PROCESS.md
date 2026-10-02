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
3. Report counts from the single classification that produced the collection, so a
   group count and the user collection can never diverge (no separately derived
   affiliation count).
4. Build one admin-gated service that assigns a device to a group or a user, and
   clears either membership.
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
- **No multi-group semantics invented.** A device holds exactly one membership
  (Phase 1, owner-confirmed); a service call replaces it rather than adding to it.
- **No change to Firewalla *cloud* groups.** `api/auth.py` has its own `groups`
  concept (`CloudGroupRecord`, `_LOGIN_FIELD_GROUPS`, `extract_group_credentials`,
  the cloud `groups` endpoint and its polling fallback). That is the pairing and
  account model, unrelated to on-box device membership, and it is **not** touched
  here. The two are easy to conflate by name; the plan means the on-box `tags`
  collection only.

## 3. Open questions / external dependencies

### Resolved (2026-10-02, owner-confirmed)

- **Can a host hold more than one membership at once? — No.** The Firewalla app
  permits exactly one membership per device. Groups and users are two flavours of
  the same single slot, not two independent slots, so assigning a group to a device
  already assigned to a user **replaces** the user, and vice versa.
  - **Service signature (1.2): one slot, replaced wholesale** — not
    `assign`/`remove` over a set.
  - **Absence of composition is confirmed, not assumed.** A host can be in a group
    **or** a user, never both, so there is no untouched list member to preserve.
  - **Tool shape (owner-approved): 4 tools** — `set_host_group`,
    `clear_host_group`, `set_host_user`, `clear_host_user` — all backed by **one**
    admin-gated service. Separate tools per kind are required rather than a single
    free-text target because group and user names collide in real data: the legacy
    user backing tags are literally named `"<owner>'s Devices"`, indistinguishable
    from a group name. N tools over one service is an established pattern here
    (`_SetHostNotifyTool` backs two tools from one handler).
  - **The app's presentation is mirrored.** The app lists groups and users together
    on one screen but separated into sections; the collection keeps them together
    with a `kind` discriminator for exactly that reason.

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
  classification set. Classification is derived from the normalized user records'
  `affiliatedTag` instead. The helper itself stays: it still has two live callers
  that use it to label a host's tags.
- **Entity surfaces already resolve to the user-facing identity.**
  `_resolve_host_group_name` maps an affiliated tag to the user's name, so
  watched-device and device-tracker attributes are correct today. The breakage in
  the current model is in the **collection**, not in per-host resolution.

### Known inconsistency — resolved in Phase 1.5

`affiliated_group_name` carried **three different meanings** across **four readers**
today:

| Location | Value before 1.5 |
| --- | --- |
| `api/client.py::_normalize_user_inventory` | the **tag's** raw name |
| `helpers/runtime_inventory.py::_build_user_inventory` | the **user's** name |
| `managers/user_manager.py::_build_watched_user_view` | the **user's** name (forced) |
| `services.py:3560` (overview `identifiers`) | pass-through of the client value |

The client-side value was the one that could surface a UUID or a legacy label, and
the overview passed it straight out. One meaning won — the user's name, per
`docs/ARCHITECTURE.md` — and the client is now the site that was corrected, which
fixes the other three by construction. The field is **kept**: after 1.5 it equals
the user's name wherever `affiliated_group_id` is set, and it is the sole source for
the shipped `associated_device_group` watched-user attribute
(`const.py:142`, `sensor.py:535`). The name is a mild misnomer now; a rename to
`affiliated_tag_name` is deliberately a **separate later cleanup**, not part of this
initiative.

## 3b. Consumer inventory (verified 2026-10-02)

Every place in the repository that reads user or group data, established by
reading each site rather than by grep alone. This is the coverage contract for
the phase steps: no consumer may be left unaccounted for.

### Data model and normalization

| Consumer | Where | Reads | Covered by |
| --- | --- | --- | --- |
| Group collection | `api/client.py:2191` `_normalize_group_inventory` | every key in raw `tags`, no discriminator | 1.3 |
| User normalization | `api/client.py:2172-2175` | `affiliated_group_name` from the tag-name lookup | 1.5 |
| Affiliated-user lookup | `api/client.py:1611` `_build_affiliated_user_lookup` | `userTags[*].affiliatedTag` + a required name | 1.3 (classification must stop relying on it) |
| Host group label | `api/client.py:1777` `_resolve_host_group_name` | `affiliated_users` first, then the raw `tags` name | 1.3 / 3.2 (fallback can render a tag name) |
| Inventory groups | `helpers/runtime_inventory.py:332` | **already** derives `user_ids` from `policy.userTags` | 1.4 |
| Inventory users | `helpers/runtime_inventory.py:382` | `affiliated_group_name` forced to the user's name | 1.5 |
| Models | `models.py:841`, `:857`, `:835/836` | `FirewallaGroupRuntime`, `FirewallaUserRuntime`, host `group_ids`/`user_ids` | 1.3 |

### Collection consumers

| Consumer | Where | Reads | Covered by |
| --- | --- | --- | --- |
| Group accessor | `integration_manager.py:292` `get_groups()` | the whole collection | 1.3 |
| Usage-history scope | `services.py:3205` `_resolve_usage_history_target` | `group.name` **only** | **3.4 (the defect)** |
| Overview counts / identifiers | `services.py:3542-3543`, `:3560` | `snapshot.groups`, `snapshot.users` | 3.1 |
| Inventory counts | `helpers/runtime_inventory.py:605`, `:661` | `group_count` | 1.6 |
| Group policy controls | `helpers/runtime_inventory.py:400` | policy keys, **skips** `userTags` | 1.4 (now skips `kind == "user"` outright) |
| Group markdown | `helpers/runtime_inventory.py:419` | `group["name"]` | 1.4 |

### Host-facing consumers of `group_name` / `group_ids` / `user_ids`

These do **not** read the collection, so Phase 3.4's grep will not find them:

| Consumer | Where | Reads | Covered by |
| --- | --- | --- | --- |
| Watched-device attribute | `binary_sensor.py:806` | `host.group_name` | 3.2 |
| Device-tracker attribute | `device_tracker.py:187` | `host.group_name` | 3.2 |
| Host record | `services.py:4042` | `host.group_name` | 3.4 (extended) |
| `get_hosts` group filter | `services.py:4092-4095` | `host.group_name` match | 3.4 (extended) |
| `get_hosts` user filter | `services.py:4114` | `host.user_ids` | 3.4 (extended) |
| Rule switch attributes | `switch.py:175-179` | `rule.applies_to(_kind)` | 3.4 (extended) |
| Rule applicability text | `models.py:1413` | `rule.applies_to` | 3.4 (extended) |
| Rule filtering | `rule_manager.py:260` | `rule.applies_to` | 3.4 (extended) |

### User-facing consumers

| Consumer | Where | Reads | Covered by |
| --- | --- | --- | --- |
| Association join | `user_manager.py:102-114` | `host.user_ids`, `host.group_ids` | 3.3 (document the 1:1 invariant) |
| Watched-user view | `user_manager.py:117-160` | `affiliated_group_name` (forced) | 1.5 |
| **Choice label** | `user_manager.py:51-57` `_format_user_choice_label` | renders `affiliated_group_name` | **1.5 (live leak — see below)** |
| Choices | `user_manager.py:61`, `:77` | user records | 1.3 |
| Watched-user attribute | `sensor.py:534-536` | `affiliated_group_name` | 3.2 |
| Options flow | `config_flow.py:878`, `:893`, `:1137-1186` | user choices, `CONF_WATCHED_USERS` | 3.2 (verified via choice label) |
| Entity helper | `entity.py:85` `get_watched_user` | user id | none needed |

### Verified non-consumers

- **`diagnostics.py`** — no group or user references at all, so no diagnostic
  output changes. Confirmed by search, so this does not need re-checking later.
- **`api/auth.py` cloud groups** — a different concept; excluded by the non-goal above.

### Live defect found during this review (fixed in Phase 1.5)

`user_manager.py:51-57` `_format_user_choice_label` rendered
`f"{user.name} ({user.affiliated_group_name})"` whenever the two differed. With a
UUID-named backing tag that put a **bare UUID into an options-flow choice label
today**. It was present-day user-visible behaviour, not hypothetical, so Phase 1.5
treated removing it as a required fix rather than optional cleanup. With
`affiliated_group_name` unified to the user's name the branch became provably dead,
and the helper was removed entirely, so a `name (name)` label is now impossible
rather than merely unlikely.

### Corrections found while executing Phase 1

Two claims in the original §3b review were wrong and are corrected above:

1. **Group policy controls were not "verified correct".** `_build_group_policy_controls`
   skipped only the `userTags` key, so a user backing tag carrying any other policy
   key would have produced report rows named after a user. Real backing tags happen
   to carry nothing else, so this was correct only by coincidence. `1.4` now skips
   user entries by `kind`, so it holds by construction.
2. **The inventory's user index was not aligned with the client's.**
   `_build_user_index` accepted every `userTags` record, while
   `api/client.py::_normalize_user_inventory` skips records whose `type` is present
   and not `"user"`. A non-user record carrying an `affiliatedTag` would therefore
   have classified a tag differently in the two modules. `1.4` applies the same
   `type` rule in both, so classification cannot diverge.

## 4. Phase summary

| Phase | Focus | Key output | Status |
| --- | --- | --- | --- |
| 1 | Resolve membership semantics and land the model | Single-membership confirmed; `kind` + `user_id` on the collection; one meaning for `affiliated_group_name`; single-path group count | **Complete 2026-10-02** |
| 2 | Build the membership service | One admin-gated service (single-slot set/clear, group or user) backed by 4 LLM tools, with validation and tests | **Complete 2026-10-02** |
| 3 | Make the reported surface accurate | Corrected overview counts, verified entity joins, updated read-tool text | Not started |
| 4 | Expose it to assistants | Four reversible LLM control tools, prompt fragment, contracts and docs | Not started |

## 5. Phase details

### Phase 1 — Membership semantics and the collection model — COMPLETE (2026-10-02)

Goal: confirm how many memberships a host may hold, then land the data-model change
so every later phase builds on a correct foundation.

- [x] **1.1 Confirm multi-membership.** Answered by the owner: the Firewalla app
      permits exactly one membership per device, so a group and a user are two
      flavours of one slot, not two independent slots. See the resolved section in
      §3.
- [x] **1.2 Choose the service signature.** One slot, replaced wholesale — not
      `assign` / `remove` over a set. The write is the same host-scoped
      `set item=policy value.tags` call for both kinds. Owner-approved tool shape:
      **4 tools** (`set_host_group`, `clear_host_group`, `set_host_user`,
      `clear_host_user`) over **one** admin-gated service, because group and user
      names collide in real data (legacy user backing tags are named
      `"<owner>'s Devices"`).
- [x] **1.3 Add the kind discriminator to the snapshot.** `FirewallaGroupRuntime`
      gained `kind: Literal["group", "user"]` and `user_id: str | None = None`.
      `_normalize_group_inventory` now takes the normalized users and classifies by
      linkage, never by name — it builds an affiliation map from
      `FirewallaUserRuntime.affiliated_group_id` and discards the backing tag's own
      name for user entries. `build_runtime_snapshot` normalizes users before groups
      so both derive from one source. `_build_affiliated_user_lookup` is **not**
      retired: it still has two live callers (`api/client.py:1975`, `:2433`), and it
      only stops being used for classification.
- [x] **1.4 Make the inventory report consistent.** `RuntimeGroupRecord` gained
      `kind` and `user_id`; `_build_group_inventory` classifies from `affiliatedTag`
      via `_build_user_index` and sets a user entry's `name` to the user's name; the
      markdown group section shows the kind. Two corrections were required beyond the
      original wording:
      1. classification is from `affiliatedTag` linkage, **not** from
         `policy.userTags` — the two agree in practice, but linkage is the rule the
         Architecture states and does not depend on a policy key surviving.
      2. `_build_group_policy_controls` now skips `kind == "user"` outright. Its
         old `userTags`-key skip was correct only by coincidence: a user backing tag
         carrying any other policy key would have produced rows named after a user.
      `_build_user_index` also gained the client's `type != "user"` filter, so the
      inventory and the client cannot disagree about who is a user.
- [x] **1.5 Unify `affiliated_group_name`.** One meaning — the user's name, per
      `docs/ARCHITECTURE.md` — at all four sites: `api/client.py:2172` was the site
      corrected (it read the backing tag's raw name), which fixes
      `helpers/runtime_inventory.py:392`, `managers/user_manager.py:149` and
      `services.py:3560` by construction. `_format_user_choice_label` was then
      **removed entirely** rather than trimmed: with the value unified its
      `name (group)` branch was provably dead, and a `name (name)` label is now
      impossible rather than merely unlikely. The field itself is **kept** — it is
      the sole source for the shipped `associated_device_group` watched-user
      attribute; see §3.
- [x] **1.6 Report reconciled counts.** `group_count` is derived from the same
      classified list that is emitted (`sum(1 for group in groups if group["kind"] ==
      "group")`), so it cannot diverge from the collection. **No separate
      user-affiliation count was added**, by owner direction: each user maps 1:1 to
      one backing tag, so such a field could only ever disagree through a defect.
      `docs/ARCHITECTURE.md` was corrected to match.
- [x] **1.7 Update model tests.** `test_runtime_inventory.py` now carries both the
      legacy human-named backing tag (`"KADEN's Devices"` → `KADEN`) and a
      UUID-named one, asserts the rendered group bullets and that neither the legacy
      label nor the UUID leaks, and asserts group policy controls exclude user
      entries. `test_client.py`, `test_init.py` and `test_services.py` fixtures were
      updated for the new `kind` field and the unified name; the usage-history
      fixture gained a genuine plain group so its group-scope test still exercises a
      real group instead of silently resolving a user entry.


### Phase 2 — The membership service — COMPLETE (2026-10-02)

Goal: one admin-gated service that sets or clears a device's single group or user
membership. Signature is fixed by 1.2: **one service**, kind-explicit and
mutually exclusive target fields, backing **four** LLM tools in Phase 4.

- [x] **2.1 Add constants.** `SERVICE_SET_HOST_MEMBERSHIP`, `SERVICE_FIELD_CLEAR`,
      `SERVICE_FIELD_GROUP_ID`, `SERVICE_FIELD_USER_ID`, `SERVICE_FIELD_USER_NAME`,
      the two ambiguity placeholders, and seven translation keys were added to
      `const.py`. `SERVICE_FIELD_GROUP_NAME` already existed.
- [x] **2.2 Build the payload — minimal, confirmed live.** The owner's DHCP-writer
      hypothesis was tested on the box and holds: a `{"tags": [...]}`-only write is
      accepted and leaves every other policy key untouched. Recorded as Finding 43.
      The builder sends only `tags`, so it cannot carry a key the caller did not
      intend to send. The app's full 16-key object is **not** required.
- [x] **2.3 Resolve the membership target.** `_resolve_membership_target` resolves
      against the **classified** collection and is scoped by kind: a group selector
      only matches a `kind == "group"` entry and a user selector only a
      `kind == "user"` entry. Tests pin the cross-kind cases (tag `10` is a user's
      backing tag, tag `99` is a plain group) so a selector that stopped being
      scoped would fail loudly. Ambiguous and unknown targets raise translated
      errors.
- [x] **2.4 Implement the handler.** `_async_handle_set_host_membership` plus
      `SET_HOST_MEMBERSHIP_SCHEMA`, registered admin-gated with
      `SupportsResponse.ONLY`. Exactly one of `{group, user, clear}` is enforced in
      the handler, because voluptuous cannot express it. Writes through the existing
      `integration_manager` → `async_set_host_policy` path. The response carries
      `membership.before`, `membership.after` and a `changed` flag so a caller can
      tell whether the single slot actually moved.
- [x] **2.4b Rule handling on a membership change — CONFIRMED BY CAPTURE and
      implemented.** Three readings of the same evidence, the last one settled by a
      purpose-built capture. The owner's model was right from the start: assign a
      device to a group and it carries no rules of its own, which the app warns
      about at assignment time.
      1. **The box deletes nothing on its own — confirmed.** Clearing tags locally
         left the device's rules intact.
      2. **The app deletes every rule the device owns — confirmed.** `rustdesk-server`
         (unassigned, carrying two **enabled** user rules plus a disabled `dap`
         pair) was assigned to one group in the app with a port 8833 capture armed.
         The app sent one `batchAction`: `policy:delete` for **all four** rules in
         order, then the tags write, then `host:syncAppTimeUsageToTags`. All four
         rules were gone afterwards. The rule count fell by exactly four.
      3. **A `dap`-keyed delete was wrong and is recorded as such.** An intermediate
         version keyed the delete on `purpose == "dap"`. Measured box-wide it was
         already doubtful — 84 of 124 group-assigned hosts still carry a `dap` pair,
         so `dap` is what *survives* assignment — and the capture refuted it: a
         `dap`-only delete would have left this device's two enabled user rules
         behind, the opposite of what the app does.
      **Implementation:** delete every rule whose `target` is the device's MAC or
      whose `scope` contains it, regardless of purpose or enabled state, **before**
      the tags write (the capture shows the deletes first). The response reports the
      removed ids as `device_rules.removed`.
- [x] **2.4c `host:syncAppTimeUsageToTags` — decoded, documented, deliberately not
      sent.** `begin` decodes to a midnight in the box's own timezone seven days
      back including the current day. Captured twice now (on the removal in
      Finding 41, and on this assignment), and both samples agree. Firewalla tracks
      per-app usage against a tag, so the command re-attributes a device's usage for
      the current window to its new tag. It is usage-accounting backfill, not part
      of the membership write: membership and the rule cleanup are both correct
      without it, and the affected surface is a tag's usage history in the app,
      which the box reconciles on its own schedule. The window is still an
      inference from two agreeing samples, and a wrong window silently
      mis-attributes usage accounting, so it stays out until the integration
      actually writes usage limits.
- [x] **2.5 Document the service.** `services.yaml`, `translations/en.json` (both
      the `services.<name>` block and the exception messages), and the
      `docs/USER_GUIDE.md` catalog plus a `#### Set host membership` section in the
      host-operator group. The user guide entry states the single-slot replace
      behaviour explicitly, because a user assigning a group to a user-owned device
      will lose the user assignment.
- [x] **2.6 Promote the probe.** `utils/probe_membership.py` is tracked and
      documented, dry-run by default, with `--list`, `--tag`, `--clear`, `--apply`
      and `--restore`. It goes beyond the original `.tmp/` probe by asserting the
      contract Finding 43 established: it diffs the host policy before and after and
      reports any key lost or changed.
- [x] **2.7 Tests.** 15 new tests: assignment by group name, by group id, and by
      user name (asserting the **backing tag** is written and not the user id);
      clear; six bad-target cases including both cross-kind cases and both ambiguity
      paths; four target-shape cases; and a registration pin for the admin gate and
      `SupportsResponse.ONLY`.

### Phase 3 — Accurate surface and preserved entity behavior

Goal: make the reported surface correct without breaking anything downstream.

- [ ] **3.1 Fix the overview counts.** In
      `services.py::_async_handle_get_system_overview`, report the group count from
      the classified collection. **No user-affiliation count is added** (owner
      direction, see 1.6); the `users` section already carries that population.
      Confirm `include: ["identifiers"]` items carry the kind so a consumer can tell
      them apart. The tests that assert on this are `test_services.py` (the
      `assert "items" not in overview["groups"]` case and its `identifiers`
      variant). The count assertions that Phase 1.6 changed were
      `test_runtime_inventory.py` (`group_count`) and `test_init.py` (`group_count`),
      both updated in Phase 1.
- [ ] **3.2 Audit the entity surfaces.** Verify that watched-device
      (`binary_sensor.py:806`), device-tracker (`device_tracker.py:187`), and
      watched-user (`sensor.py:536`) attributes are unchanged in meaning and that
      the user-facing identity rule still holds for a device in a legacy
      human-named backing tag. Add a regression test using a legacy-shaped fixture.
- [ ] **3.3 Audit the association joins.** Confirm
      `managers/user_manager.py::_get_associated_hosts_for_user` still resolves
      associated devices through the backing tag id in `host.group_ids`, and that
      the 1:1 user-to-tag invariant is documented where it is relied on.
- [ ] **3.4 Audit remaining group consumers.** Work from the §3b inventory rather
      than a fresh grep, because two groups of consumers will not be found by
      searching for `snapshot.groups`, `get_groups()`, or `groups[]`:
      the **host-facing** consumers that read `host.group_name`, `host.group_ids`
      or `host.user_ids` (`binary_sensor.py:806`, `device_tracker.py:187`,
      `services.py:4042`, the `get_hosts` group filter at `services.py:4092-4095`,
      the `get_hosts` user filter at `services.py:4114`), and the **rule-facing**
      consumers that read `applies_to` (`switch.py:175-179`, `models.py:1413`,
      `rule_manager.py:260`). Confirm each is either unaffected or handled.
      **One consumer needs a real fix:** `services.py::_resolve_usage_history_target`
      (line 3112, called from `_async_handle_get_time_usage_report` at line 4767)
      resolves a `scope_kind="group"` request against `get_groups()` and matches on
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

- [ ] **4.1 Add the control tools.** In
      `llm_tools_control.py`, add **four** tools — `set_host_group`,
      `clear_host_group`, `set_host_user`, `clear_host_user` — each following the
      `SetHostDhcpReservationTool` pattern: reversible annotations, host selector
      plus (for the `set_` tools) the kind's name-or-id target, delegating to the
      one new service with `_returns_response = True`. Register all four in
      `_CONTROL_TOOL_CLASSES` (not the destructive list) since they are reversible.
      Four tools rather than one free-text target because group and user names
      collide in real data; `_SetHostNotifyTool` is the in-repo precedent for
      several tools over one service.
- [ ] **4.2 Update the prompt fragment.** In `llm_tools_common.py`, note that a
      device's membership can be changed, that groups and users are both valid
      targets, and that the change is reversible.
- [ ] **4.3 Document the contract.** Add the four tools to
      `docs/MCP_TOOL_REFERENCE.md` in the existing per-tool format, using the same
      annotation and availability fields as their neighbours.
- [ ] **4.4 Tests.** Cover each tool's schema, its service delegation, its
      response envelope, and its registration tier. Update
      `test_llm_contract.py` if it asserts an exact tool count or list.
- [ ] **4.5 Verify availability tiers.** Confirm the tools appear at
      read-and-control and above and not in summary-only, consistent with the other
      reversible controls.

## 6. Validation strategy

- **§3b is the coverage contract.** Every user/group consumer in the repository is
  listed there with the step that covers it, and two verified non-consumers
  (`diagnostics.py`, the `api/auth.py` cloud groups) are recorded so they are not
  re-investigated. A phase is not complete while any row's step is unfinished.
- **Per phase:** `python -m ruff check .`, `python -m ruff format .`,
  `python -m mypy custom_components/firewalla_local`, `python -m pytest tests/ -v`.
- **Phase 1 is complete and was the highest-risk phase.** It changed a published
  shape that entities and services read. The full suite was green before Phase 2
  started, and no test outside the predicted set failed — which is the evidence that
  §3b's consumer inventory was complete.
- **Live verification:** after Phase 2, run the service against the dev box for
  set-to-group, set-to-user, and clear, and confirm each in the Firewalla app.
  Membership writes are trivially reversible, so a live check is safe and is
  the strongest evidence the contract still holds.
- **Contract checks:** establish on the dev box whether the minimal `tags`-only
  write (the DHCP-writer shape) is accepted, and whether the box performs the
  stale device-scoped rule sweep itself; integer tag ids; and that clear sends an
explicit empty list.
- **Regression focus:** legacy human-named backing tags, UUID-named backing tags,
  real groups, and a device with no membership.

## 7. Breaking changes to call out

- `groups` / `groups[]` entries gain `kind` and `user_id`, and a user-backed entry's
  `name` changes from the raw tag name to the user's name. *(Landed in Phase 1.)*
- `group_count` shrinks to real groups only. **No user-affiliation count is added** —
  use the `users` collection or `user_count` for that population.
- Any consumer summing `group_count` to get a collection total must switch to the
  collection length.
- `affiliated_group_name` has one meaning now: the user's name. A consumer that
  relied on it carrying the backing tag's name loses that value. *(Landed in
  Phase 1.)*
- The options-flow watched-user label no longer appends a parenthesised tag name, so
  a label that previously leaked a UUID is now just the user's name. *(Landed in
  Phase 1.)*
- **Assigning a membership clears the previous one.** A device holds at most one
  membership (Phase 1, owner-confirmed), so the write replaces `tags` wholesale and
  assigning a group to a device already assigned to a user **removes the user
  assignment** rather than adding alongside it. That is a user-visible outcome of a
  single call and must be stated in the release notes and in the service
  description. This is confirmed behaviour, not a contingency.

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
