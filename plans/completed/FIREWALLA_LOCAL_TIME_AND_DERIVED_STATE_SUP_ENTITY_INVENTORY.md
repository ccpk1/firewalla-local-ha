# Time and Derived State — Supporting Entity and Attribute Inventory

**Parent plan:** `FIREWALLA_LOCAL_TIME_AND_DERIVED_STATE_COMPLETED.md`
**Purpose:** the measured evidence behind the plan, and the entity-surface inventory the
phases work from. Every number here is from the tree or from a live box response, not from
memory, so "done" stays checkable.

Measured on `feature/flow-reporting` at 774 passing tests, against a live Firewalla Gold
(217 hosts, 313 rules, 10 users).

---

## 1. The live contradiction (Class B)

Taken seconds apart, from the same box, with the same configured window:

| tool | reported |
| --- | --- |
| `get_system_overview` | `vpn_hosts: {total: 5, online: 1, offline: 4}` |
| `list_hosts(kind="pseudo_host")` | all five peers `online: false` |

The five peers and their last activity, newest first:

| peer | `last_active` | age |
| --- | --- | --- |
| `chads-laptop-wgvpn` | 2026-10-02T00:48:18Z | **4.51 days** |
| `chads-phone-wgvpn` | 2026-10-01T17:55:02Z | 4.79 days |
| `chads-phone-awgvpn` | 2026-09-10T13:45:14Z | 25.97 days |
| `kadens-phone-wgvpn` | 2026-08-05T17:32:44Z | 61.81 days |
| `kadens-chromebook-wgvpn` | `null` | — |

**`chads-laptop-wgvpn` was the "1 online", at 4.51 days stale.** The window is 5 minutes.

The mechanism was `count_online_hosts` deriving its own reference:

```python
reference_activity = reference_last_active(hosts)  # max over the subset passed in
```

Counting the peers measured them from the freshest *peer*, so the newest peer was online by
construction. Against the appliance-wide reference — the newest activity anywhere, which was
a living-room TV active seconds earlier — it is offline, as the host list correctly said.

**Fixed in `5113793`.** The reference is now a required parameter and
`host_manager.inventory_reference_activity()` is the single source. Live re-verification
after restart: `vpn_hosts: {total: 5, online: 0, offline: 5}`.

**What remains.** The value is now correct and still unverifiable. Nothing in either
response states the reference instant or the window, so a reader cannot check the claim and
would not have been able to catch the original error.

---

## 2. The unreadable instant (Class A)

`list_hosts` publishes `last_active: 1791258075.36`. A raw float. During the living-room TV
diagnosis three hosts were compared by eye as numbers because there was no date to read —
`1788297903` versus `1791254647` is not obviously "August" versus "now".

Live values demonstrating the gap, all from one `list_hosts` call:

| host | `last_active` published | what it is |
| --- | --- | --- |
| `nas2` | `1791254551.988` | 2026-10-05T22:42:31Z |
| `Kadens-camera` | `1788297903.296` | 2026-09-01T17:25:03Z |
| `switch-gaming` | `1788297898.98` | 2026-09-01T17:24:58Z |

The same instant is published as ISO in six other places. There is no rule, so there is no
reason for the difference.

---

## 3. The entity surface

Every entity attribute or state that holds an instant, a duration, or a value derived from
time. This is the surface the plan is careful with, because users may have programmed
against it.

| entity | field | holds | today | twin | basis |
| --- | --- | --- | --- | --- | --- |
| `binary_sensor` watched device | **state** (`is_on`) | derived boolean | `bool` | — | **missing** |
| `binary_sensor` watched device | `last_active` → **`last_active_at`** | instant | ISO | **add** | — |
| `device_tracker` | **state** (`home`) | derived boolean | `bool` | — | **missing** |
| `device_tracker` | `last_active` → **`last_active_at`** | instant | ISO | **add** | — |
| `sensor` watched user | `last_active` → **`last_active_at`** | instant | ISO | **add** | — |
| `sensor` watched user | `associated_host_count` | derived count | `int` | — | **missing** |
| `binary_sensor` system status | `hosts_online` / `_offline` / `_total` | derived counts | `int` | — | **missing** |
| `binary_sensor` system status | `vpn_hosts_online` / `_offline` / `_total` | derived counts | `int` | — | **missing** |
| `binary_sensor` system status | `runtime_data_updated_at` | instant | ISO | none | — |
| `binary_sensor` system status | `uptime` | duration | human string | `uptime_seconds` | — |
| `binary_sensor` system status | `uptime_seconds` | duration | `int` | ✓ paired | — |
| `binary_sensor` network | `host_count` | count | `int` | — | see §5 |
| `binary_sensor` alarm | `fired_at` | instant | **epoch float** | **add** | — |
| `sensor` speed test | `tested_at` | instant | ISO | none | — |
| `sensor` internet quality | `sampled_at` | instant | ISO | none | — |
| `switch` rule | `is_paused` | derived boolean | `bool` | — | `pause_until` ✓ |
| `switch` rule | `pause_until` | instant | ISO | none | — |
| `switch` rule | `pause_remaining_seconds` | relative duration | `int` | — | — |
| `switch` rule | `schedule_next_start` | instant | ISO | none | — |
| `switch` rule | `schedule_next_end` | instant | ISO | none | — |
| `switch` rule | `last_hit` | nested dict | `at` ISO + `timestamp` epoch | ✓ paired | — |

Bold entries are the approved target state rather than the current one. The `last_active`
renames are approved (plan Q1); the twins are additions, not renames.

### What this table shows

- **Eight families derive a value from the activity reference and publish no part of it.**
  The watched-device state, the device-tracker state, the watched-user count, the system
  host counts, the VPN host counts, and each network's counts.
- **Six instants are ISO with no epoch twin** — `last_active` (×3 entities, being renamed),
  `pause_until`, `schedule_next_start`, `schedule_next_end`, plus `tested_at`, `sampled_at`
  and `runtime_data_updated_at` on their sensors.
- **`fired_at` is the one outright wrong format.** It is a raw epoch float on the entity,
  while the *service* publishes ISO under the same name. One name, two formats.
- **Two families are already correct** and are the shape to generalise:
  `uptime` / `uptime_seconds` (a duration pair, correctly using `_seconds`), and
  `last_hit` with `at` + `timestamp` (an instant pair, correctly paired).
- **`is_paused` looks like an exception but is not.** It was redefined to `not enabled`, so
  `enabled` is its basis and it needs nothing further. `pause_until` then answers the
  separate question of whether the box will resume it. That two-field split — the boolean
  plus the boundary — is the pattern Phase 2 generalises.

### Deliberately excluded, and why

Recording the exclusions so a later reader does not assume the table is complete by
accident:

| field | why excluded |
| --- | --- |
| `ATTR_SSID_PAUSED` (`paused`) | the SSID's own admin state, not derived from any time |
| `ATTR_AP_TIMEZONE`, `ATTR_SYSTEM_TIMEZONE` | timezone *names*, not instants |
| `ATTR_SYSTEM_RUNTIME_DATA_UPDATED_AT` | an instant, but a *snapshot age* rather than a device activity time — it has no window and derives nothing |
| diagnostics payloads | raw vendor structures, already redacted, not a curated surface |
| `expire_seconds`, `schedule_duration`, `time_limit_quota` / `_used` | durations and quotas, correctly numeric; the `_seconds` rule already covers them |
### A simplification worth knowing before Phase 4

Two constant *values* cover five entity attributes:

- `ATTR_WATCHED_DEVICE_LAST_ACTIVE` = `"last_active"` is published by **both** the
  watched-device binary sensor and the device tracker, so one rename fixes both platforms.
- `ATTR_WATCHED_USER_LAST_ACTIVE` = `"last_active"` is a second constant with the same
  value, on the watched-user sensor.

So Phase 4.2 changes two constant values, not three attribute sites. The apparent breadth of
that rename is smaller than the inventory table's row count suggests, which is worth stating
because the table is what makes the break look expensive.

**The rename is approved (plan Q1, 2026-10-06).** `last_active` → `last_active_at`, with
`last_active_timestamp` as the twin.

Three things this fixes, worth recording before implementation:

1. **The name is currently wrong in a documented way.** `tested_at`, `sampled_at` and
   `fired_at` all mark an instant with `_at`. `last_active` marks an instant with `_active`,
   which is a *state* adjective rather than a time marker — the suffix says whether the host
   is active now, while the value is when it last was. `last_active_at` says what it holds.
2. **The service surface publishes the same concept under a different name again.** `get_hosts`
   → `last_active` (epoch), flow records → `timestamp` (epoch). When the entity becomes
   `last_active_at`, the service must match — otherwise this initiative creates the very
   defect it exists to remove. Phase 3.3 and Phase 4.2 are therefore coupled by name, not
   merely similar.
3. **`ATTR_WATCHED_DEVICE_LAST_ACTIVE` is named for the concept, not the format.** The
   constant keeps its identity as the "when was this host last active" attribute; only its
   published value string changes. So the diff is two string literals and their consumers,
   while the constant name stays readable in the code that builds the attribute.

**Why it was worth approving rather than exempting.** `last_active` is the only instant whose
name already predates the convention, which made it the natural candidate for a grandfather
clause — and a grandfather clause is exactly what turns a rule into a preference. With it
renamed, no future instant can cite it as precedent for special-casing, and the `_at` suffix
becomes checkable rather than aspirational.

---

## 4. The service and LLM tool surface (Phase 3)

**In scope.** An earlier draft of the plan recorded this surface as "reference only". That
was a misreading of the owner's instruction, corrected in plan Q11: the instruction was that
we need not worry about **legacy compatibility for consumers**, not that the fields are out
of scope. Nothing consumes these responses, which makes them the *freest* thing in the
repository to normalize — no shim, no alias, rename and declare it breaking.

### The three competing patterns

**Pattern 1 — ISO then epoch, `<name>_at` + `<name>_timestamp`** (the intended one):

`tested_at` / `tested_at_timestamp`, `sampled_at` / `sampled_at_timestamp`,
`fired_at` / `fired_at_timestamp`, `expires_at` / `expires_at_timestamp`,
`synced_at` / `synced_at_timestamp`.

**Pattern 2 — epoch bare, ISO suffixed `_iso`:**

`timestamp` / `timestamp_iso` (flow records, WAN events).

**Pattern 3 — epoch then ISO, both suffixed:**

`start_timestamp` / `start_timestamp_iso`, `end_timestamp` / `end_timestamp_iso`,
`begin_timestamp` / `begin_timestamp_iso`, `anchor_timestamp` / `anchor_timestamp_iso`.

**Three patterns for one concept, and one more that is already right.**
`build_rule_hit_attributes` publishes `at` (ISO) + `timestamp` (epoch) — the reference
implementation, and the one Phase 3 generalises. It was written correctly and the others
drifted around it.

### The four gaps on this surface

| gap | fields |
| --- | --- |
| epoch-only, no readable form (Class A) | `get_hosts` → `last_active`; flow records → `timestamp`; `get_runtime_inventory` → `activated_time`, `last_activated_time`, `updated_time`, `expires_at`, `pause_until` |
| ISO-only, no twin (Class A, inverse) | `tested_at`, `sampled_at`, `fired_at`, `expires_at`, `synced_at`, `pause_until` |
| no basis for a derived value (Class B) | `get_hosts` → `online`; `get_system_overview` → `hosts.*`, `networks[].online`, `vpn_hosts.*`; `get_runtime_inventory` → `hosts_online/offline` |
| one name, two formats | `pause_until` — epoch in `get_runtime_inventory`, ISO in `get_rules` and the rule switch |

The third row is the one that produced the live `vpn_hosts` contradiction. The fourth is the
only case where a single *name* means different things depending on which surface a caller
reads, which makes it the most misleading of the four.

**Reachability check, to be honest about coverage:** `destination_kind: "peer"` is a value
these captures were meant to exercise. No live flow record carried a `peer` destination in
the sampled window — every destination row returned `host` — so `peer` is verified by unit
test (`test_flow_utils.py`) and not by observation. Recorded rather than implied.

---

## 5. Open investigation: the network `host_count`

`services.py` publishes:

```python
# The same count the `network` entity publishes as an attribute.
"host_count": len(network_hosts),
```

The entity publishes `network.device_host_count`, which is the box's own count from the
interface payload. **Two different computations, and the comment asserts they are equal.**

This matters more than a comment being stale. If they diverge, one of the two names is
wrong, and Phase 3 is about to rename fields in that area. Resolve before renaming
(plan Q8, step 2.6).

---

## 6. The conversion inventory

There is no shared helper, so every site formats its own instant. 23 `.isoformat()` calls
and 21 conversions across seven files:

| module | `datetime.fromtimestamp` | `dt_util.utc_from_timestamp` |
| --- | --- | --- |
| `services.py` | 12 | 2 |
| `sensor.py` | 3 | — |
| `models.py` | 2 | — |
| `binary_sensor.py` | 1 | — |
| `device_tracker.py` | 1 | — |
| `switch.py` | 1 | — |
| `managers/integration_manager.py` | 1 | — |

Two styles for the same operation is how the format drifted in the first place. One helper
(phase 1.3) removes the possibility rather than the symptom.

---

## 7. Recommendations carried into the plan

1. **Normalize the service and tool surfaces first, not last.** They *are* in scope (plan
   Q11), and they are the freest thing in the repository: no consumers, so no shim, no alias,
   no deprecation. Converging them establishes the one precedent the entity work then cites,
   instead of arguing the entity surface into a pattern while three competing ones sit in the
   same package. This is the change from the plan's first draft, which had them out of scope.
2. **Entity attributes before entity states.** Every breaking change proposed is an
   attribute key. No entity *state* changes meaning in this plan — `is_on` and `home` keep
   their semantics and gain their basis. That keeps the blast radius to templates that read
   attributes, not automations that trigger on state.
3. **Publish, do not unify.** `device_tracker`'s 15-minute away window stays separate from
   the 5-minute connectivity window. Phase 2 gives it the same *transparency*, not the same
   *value*.
4. **One guard per claim.** The pairing guard asserts a shape; the reproducibility guard
   asserts a *fact*. Both must be shown failing before they are trusted. The repository has
   already had a guard pass while the value it existed to find was present, which is why
   this is stated as a requirement rather than a preference.
5. **No shims — the documentation is the compatibility.** Every rename lands with a
   `USER_GUIDE.md` migration row and a `RELEASE_CHECKLIST.md` entry. The plan states this as
   policy (Q9) because the temptation to add an alias is strongest exactly where the break is
   widest, and an alias would permanently publish two names for one concept — the defect this
   whole initiative exists to remove.

---

## 8. Housekeeping found while researching

`plans/in-process/` still contains
`FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_IN-PROCESS.md` and
`FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_SUP_INVENTORY.md`, and `plans/completed/` also
contains `FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_COMPLETED.md` and a
`FIREWALLA_LOCAL_VOCABULARY_ALIGNMENT_SUP_INVENTORY.md` of the same name. The `README.md` in
`in-process/` states the initiative is closed and archived, so the `in-process/` copies look
like stale duplicates from the close-out. Confirm and remove, so the next reader does not
plan against a superseded plan.

---

## 9. Phase 1 — the guards, and what they found on the first run

Step 1.6 requires both guards to be shown failing **before** the change that satisfies
them. This is that record, taken on `feature/flow-reporting` at 775 passing tests with the
guards newly added.

### The pairing guard

```
{'services.py':     ['pause_until has no pause_until_timestamp'],
 'switch.py':       ['pause_until has no pause_until_timestamp'],
 'binary_sensor.py':['fired_at has no fired_at_timestamp',
                     'runtime_data_updated_at has no runtime_data_updated_at_timestamp'],
 'sensor.py':       ['sampled_at has no sampled_at_timestamp',
                     'tested_at has no tested_at_timestamp']}
```

**Six gaps, and one of them was not in the inventory.** `binary_sensor.py` publishing
`fired_at` with no twin is the entity half of the format conflict recorded in §3 — the
service publishes `fired_at` as ISO and the entity as a raw epoch float, and the guard
found the entity side independently. `sensor.py` holds two more the inventory recorded as
"ISO, no twin" but had not connected to a failing check.

### The reproducibility guard

```
get_hosts publishes a windowed boolean without its basis, so a caller cannot
reproduce it: ['as_of', 'as_of_timestamp', 'online_window_seconds'] absent.
`online` is `as_of - last_active <= online_window_seconds`, and all three inputs
were unpublished -- which is how the same peers read online in one tool and
offline in another.
```

Fails for `get_hosts` and `get_system_overview` alike. This is the Class B defect from §1,
now asserted rather than described.

### Two flaws the guards had on their first run, and what they show

Both were caught by the anti-vacuity check, which is the argument for having one:

1. **The scanner read dict literals only.** `switch.py` contributes ten keys to the scan
   and none of them was `pause_until`, because most entity attributes are added by
   subscript assignment (`attributes[ATTR_RULE_PAUSE_UNTIL] = ...`) after the initial dict
   is built. Reading only `ast.Dict` saw the initial dict and missed every attribute added
   to it. Fixed by also reading `ast.Subscript`, which is what surfaced `switch.py`'s
   `pause_until` gap above.
2. **The service call helper passed `refresh` unconditionally.** `get_system_overview`
   does not accept it, so that guard errored rather than asserting. Fixed by not passing
   it — the client is patched anyway, so a poll would change nothing.

The first is the more useful lesson: the check *looked* like it worked, reported a
plausible partial answer, and was wrong by omission. A guard whose coverage is unverified
reports success for the wrong reason, which is the same failure mode as the `vpn_hosts`
bug — an answer that is confidently incomplete.

### How the failing guards are held in a green suite

`xfail(strict=True)` on each guard, with a reason naming the phase that resolves it. Today
they fail, so the marker is satisfied and the suite stays green. When Phase 2 publishes
the basis, and when Phases 3–4 pair the instants, those tests begin to **pass** — which
under `strict=True` is itself a suite failure, so the marker cannot outlive the work. The
alternative, shipping a red suite, blocks every other change and trains people to ignore
failures; the alternative of no marker at all lets the guard be deleted rather than
satisfied.

---

## 10. Measurement commands

Reproduce any number above:

```bash
# Every published time-ish key in the package
grep -rnE '"[a-z_]*(time|_at|timestamp|until|expires|active)[a-z_]*":' \
  custom_components/firewalla_local/ --include='*.py' | grep -v __pycache__

# Every hand-rolled conversion, to size phase 3.4
grep -rn 'datetime.fromtimestamp\|dt_util.utc_from_timestamp' \
  custom_components/firewalla_local/ --include='*.py' | grep -v __pycache__

# The Phase 1 guards, and their held failures
python -m pytest tests/components/firewalla_local/test_time_contract.py -q
python -m pytest tests/components/firewalla_local/test_time_contract.py -q -rxX

# Live: does the count agree with the list?
#   get_system_overview  -> vpn_hosts
#   list_hosts(kind="pseudo_host") -> hosts[].online
# These disagreed before 5113793 and agree after.
```
