# Supporting note: plan review — MCP capabilities vs. Core 2026.10 and agent-friendliness

## Purpose

A high-quality review of `FIREWALLA_LOCAL_MCP_CAPABILITIES_IN-PROCESS.md` against two lenses:

1. **Are the Core 2026.10 LLM/MCP capabilities correctly understood and used?** Verified against the Sept 26 2026 developer post (*"LLM tools return a ToolResult and declare their integration"*) and the installed Core tree in `/workspaces/core`.
2. **Are the exposed tools genuinely agent-friendly** — good descriptions, good inputs, good responses — while keeping the agreed backend approach of delegating to existing services?

**This is analysis and recommendation only. No source changes.** Recommendations are ordered by priority at the end.

**Owner clarification (2026-09-30):** alarm *block/unblock* is intentionally **not** exposed — it only creates/changes rules, and rule services already cover that. This supersedes the `block_alarm_target` tool listed in plan §4.3 and investigation note §12.

## Verdict in one line

The plan's platform facts and its **delegate-to-services** architecture are correct and well-researched; the gaps are (a) a **hard correctness bug in the delegation recipe** for control tools, (b) the **control-tool response surface is empty** and must be designed (this is the real "agent-friendly" work), and (c) the **input/annotation contract is under-specified** relative to what 2026.10 actually serves to MCP clients.

## Part 1 — Confirmed correct (no change needed)

Validated against `/workspaces/core`:

- **`llm.ToolResult(data=..., error=...)`** is the return contract. Plain-JSON return is deprecated (warn until **2027.11**). `helpers/llm.py:161`, `async_call_tool` wraps legacy returns.
- **`llm.ToolAnnotations(read_only, destructive, idempotent, open_world)`** exists (`helpers/llm.py:169`) and is served to MCP as `readOnlyHint/destructiveHint/idempotentHint/openWorldHint` (`components/mcp_server/server.py:63`). Docstring confirms defaults are the **least safe** case.
- **`Tool.title`, `Tool.integration`** exist and are served (`server.py:60`, `helpers/llm.py:186-190`). Missing `integration` warns custom integrations until **2027.10**.
- **`required` is preserved** in the MCP input schema (`server.py:56`), `openapi_version="3.1.0"`.
- **`vol.Schema` for tool parameters, never `probatio`** — correct. `probatio` does not exist pre-2026.10; the `install_as_voluptuous()` shim makes `vol.Schema/Required/Optional/In` resolve on both sides. The version-gate + no-eager-import + AST test design in §4.1 is sound and is the right way to protect the 2025.10→2026.9 base.
- **Delegate-to-services is the right backend.** Core's own `ActionTool` (`helpers/llm.py:733`) is literally this pattern: build args → call the service → wrap the result. Our read services already return `JsonObjectType` and are `SupportsResponse.ONLY`, so read tools are thin. Keep this.
- **Tier C exclusion** (`delete_host`, `delete_alarm`, bulk commands) is sound: MCP has no confirmation channel and no reliable success signal for those.
- **Option B (owned `llm.API`)**, read-default-on + single control select, bare-`firewalla_local` id: all good decisions, unchanged.

## Part 2 — Findings and recommendations (priority order)

### P0 — Correctness: the delegation recipe is wrong for control tools (must fix)

**Finding.** Plan §4.2 states *every* tool delegates via `hass.services.async_call(..., return_response=True)`. The write services split across two response modes, and **calling with the wrong mode raises**:

| Service | Response mode | `return_response=True`? |
|---|---|---|
| `pause_rule`, `resume_rule`, `set_ssid_paused` | `SupportsResponse.NONE` | **raises** `service_does_not_support_response` |
| `mute_alarm`, `unmute_alarm`, `archive_alarms` | `SupportsResponse.NONE` | **raises** |
| `set_host_name`, `set_host_dns_hostname`, `set_host_device_type`, `set_host_dhcp_reservation`, `set_host_notify_when_next_online/offline`, `wake_host` | `SupportsResponse.ONLY` | required |
| `run_internet_speed_test` | `SupportsResponse.ONLY` | required |

Evidence: `_SERVICE_REGISTRATIONS` in `services.py:4617-4815`; enforcement in `core.py:2898-2916` (raises `ServiceValidationError` both when `return_response=True` on a `NONE` service and when omitted on an `ONLY` service).

So exactly the Tier A control tools the plan is most excited about (`pause_rule`, `resume_rule`, `set_ssid_paused`, mute/unmute) would fail under the written recipe.

**Recommendation.** Split the recipe by response mode:
- `ONLY` services → `return_response=True`, wrap the payload.
- `NONE` services → `return_response=False`, **synthesize** the action-result envelope (see P1).

Add a per-service **response-mode column** to the contract doc, and one test per control tool asserting the call mode matches the registration.

### P1 — Agent-friendliness: design the control-tool response (the real work)

**Finding.** Because `pause_rule`/`resume_rule`/`set_ssid_paused`/`mute_alarm`/`archive_alarms` return **nothing**, there is no service payload to wrap. The plan's `{"result": ..., "meta": ...}` envelope assumes a result exists. For writes, the tool must construct the response itself. This is precisely where "high quality changes" lives — an agent must be able to confirm a change landed and know how to undo it.

**Recommendation — standard action-result envelope** for every control tool:
- `status`: `applied` | `already_in_state` | `failed`
- `changed`: bool
- `target`: resolved id + human name (echo what was acted on)
- `before` / `after`: the state that changed (e.g. `enabled: true → false`)
- `undo`: the exact call to reverse it (e.g. `resume_rule(rule_target=...)`)
- `warnings`: [] or degradations

This also makes the planned **idempotency pre-check** observable: return `already_in_state` instead of silently no-op-ing. Keep the read envelope tight (token cost) — `meta` stays minimal.

### P1 — Agent-friendliness: per-field `description=` on inputs (cheap, high leverage)

**Finding.** Field descriptions **do** reach the MCP `inputSchema`, but only when attached to the schema marker. Core builds agent schemas exactly this way: `probatio.Required(field, description=field_description)` → `probatio.to_openapi(...)` (`helpers/llm.py:690-700`, `553-660`). Both voluptuous and probatio markers accept `description=`, so `vol.Optional(field, description=...)` works on both sides of the migration.

**Recommendation.** Make per-field `description=` **mandatory** for every tool parameter, and describe enums by *meaning* not value (`last_60_minutes` → "last 60 minutes of samples, not a rolling hour"). Requiredness is already machine-visible via `required`, so descriptions should say *why* a field matters and how to discover valid values (e.g. rule IDs from `list_rules`). The plan mentions this in the investigation note Layer 3 but does not make it a hard step in §4.2/§4.3 — it should be.

### P1 — Agent-friendliness: specify all four annotation flags per tool

**Finding.** The plan mandates only `read_only`/`destructive`. But 2026.10 serves **all four** flags to MCP, and the least-safe defaults mean an unspecified flag reads as dangerous/non-idempotent.

**Recommendation — set all four per tool:**
- `read_only=True, destructive=False` for reads (as planned).
- `idempotent=True` for `pause_rule`/`resume_rule`/`set_host_name`/notify toggles (re-call is a no-op with the pre-check); **`idempotent=False`** for `run_internet_speed_test` (costs WAN bandwidth every call) and `wake_host` (sends a packet).
- `open_world`: **`True` for tools that poll the live box** (any `refresh=True` read, `run_internet_speed_test`) — it tells the agent results are a snapshot of an external system that can change; **`False`** for reads served purely from cached coordinator data. This is an under-used signal that helps the agent reason about staleness.

### P2 — Capability gap: no cheap target-discovery path for the headline action

**Finding.** `pause_rule`/`resume_rule` take `rule_target` (a rule ID). The only tool-visible surface listing rule IDs is `get_runtime_inventory`, which is **admin-gated** *and* a very large payload (rules + networks + hosts + users + groups). So the "single most-requested action" depends on the heaviest, admin-only read tool just to discover its target. Rules exist as switch entities, but tools do not see entities.

**Recommendation.** Add a scoped **`list_rules`** read tool (rule_id, name, `is_paused`/`enabled`, purpose, target scope) — cheap, non-admin, and the natural discovery step before `pause_rule`. This is the single biggest usability win for agents. (Fallback: document that IDs come from rule switches / `get_runtime_inventory`, but a scoped tool is better.)

### P3 — Accuracy: reconcile the dropped alarm block/unblock

**Finding.** Owner confirms alarm block/unblock is unnecessary (it is rule create/change, already covered). Plan §4.3 and investigation note §12 still list `block_alarm_target` as Tier A.

**Recommendation.** Remove `block_alarm_target` from §4.3 and §12; note the decision and its reason so it is not re-proposed. The remaining alarm tool surface (`get_alarms`, `set_alarm_muted`, `archive_alarm`) is unaffected.

### P3 — Contract: responses are opaque text and must be JSON-safe

**Finding.** HA's `mcp_server` serves **no output schema / `structuredContent`** — `_format_tool` sets only `inputSchema`, `title`, `description`, `annotations` (`server.py:42-68`); `call_tool` returns `TextContent(json.dumps(data))` + `isError` (`server.py:180-193`). And `json.dumps` is called **without** `default=custom_serializer`, so the returned `data` must be strictly JSON-serializable (no `datetime`, `set`, custom objects) or serialization raises and surfaces as a tool error.

**Recommendation.** Fold two constraints into the contract doc + contract test: (1) the response contract is convention + tests only — no protocol enforcement (which is exactly why `meta.response_type` matters: the model has no schema to tell it the shape); (2) every envelope must be plain JSON types. Note `custom_serializer` on `APIInstance` only affects *input* schema conversion, not output.

### P4 — Notes (no design change)

- **Prefix enforcement is on the `llm.py` platform path, not the owned-API path.** `_async_report_tool_issues` (`components/llm/__init__.py:100-128`) checks `f"{domain}__"` for tools from the `async_get_tools` platform hook. For Option B the prefix is a *convention*, not platform-enforced — keep `firewalla_local__` (it is right and future-proofs an Option A layer), but fix the stated rationale in §"Tool contract". Also note `MergedAPI`/`NamespacedTool` (`helpers/llm.py:420, 490`) prepends `namespace__` when the user picks **"All LLM APIs"** in `mcp_server`, so externally our tools can appear double-prefixed — account for this in the contract test (assert on the un-namespaced name).
- **The prompt fragment is served as an MCP Prompt.** `mcp_server.server.handle_list_prompts` / `handle_get_prompt` expose `llm_api.api_prompt` as a first-class, client-fetchable MCP Prompt. This raises the value of the contract-derived prompt in Phase 4.4 — it is user/agent-visible, not just injected context.

## Part 3 — Prioritized recommendation list

1. **(P0)** Branch tool delegation on service response mode; `NONE` writes call with `return_response=False`. Add a response-mode column + per-tool call-mode tests.
2. **(P1)** Define the standard **action-result envelope** for control tools (`status`/`changed`/`target`/`before`/`after`/`undo`), since services return nothing.
3. **(P1)** Make **per-field `description=`** mandatory on every tool parameter; explain enums by meaning.
4. **(P1)** Specify **all four annotation flags** per tool, including `idempotent` and `open_world`.
5. **(P2)** Add a scoped **`list_rules`** read tool for cheap, non-admin target discovery before `pause_rule`/`resume_rule`.
6. **(P3)** Remove the dropped alarm **block/unblock** references from plan §4.3 and investigation note §12.
7. **(P3)** State the **JSON-safe response** constraint and the "no output schema" limitation in the contract doc + test.
8. **(P4)** Correct the **prefix-enforcement rationale** and account for `MergedAPI` namespacing in the contract test; note the prompt-as-MCP-Prompt.

## Open questions

- Should the action-result `before`/`after` be sourced from a post-write read (extra call) or echoed from the request plus the pre-check state? A post-write re-read is more trustworthy but costs a second call on `refresh`-bearing paths.
- Does `list_rules` need to expose rule *purpose/target scope* for the model to choose the right rule, or is `rule_id + name + paused` enough?
- Confirm the `open_world` split (live-poll vs cached) matches how each read service actually sources data (`refresh=True` path vs coordinator cache) before hard-coding flags.

## Second-pass review — traps, gaps, opportunities (after the plan update)

### Traps (will silently misbehave)

- **T1 — `archive_alarms` inherits a bulk mode.** `ARCHIVE_ALARMS_SCHEMA` has `mode: "this" | "all_active"`. `mode: "all_active"` **is** the bulk "ignore all" command (RE Finding 32 `alarm:ignoreAll`). The plan lists `archive_alarm` as Tier B (single) *and* excludes bulk commands as Tier C — but a tool that passes `mode` through quietly re-exposes the bulk action. **The archive tool must restrict `mode: "this"` + `alarm_id`** (or treat `all_active` as Tier C). Same check for any `delete_alarms`-derived surface.
- **T2 — block `undo` may not resolve.** The created block rule's `pid` is returned by `policy:create`, but `RuleManager.async_delete_rule` resolves from `_rule_index`, which is built from the coordinator's rule list and is **stale right after create**. `delete_rule(rule_id=<pid>)` will return "not found" unless create optimistically registers the rule in the index, triggers a refresh, or the undo path falls back to `client.async_delete_rule`. Fix this or the advertised `undo` fails on first use.
- **T3 — `before`/`after` costs an extra read unless tied to the pre-check.** The idempotency pre-check already reads current state (rule enabled, SSID paused). Source `before` from that same read rather than a second call.

### Gaps (missing pieces)

- **G1 — corrected after investigation (owner was right).** Unblock **is** clean and does not need general `delete_rule`. The client has **no `alarm:block`/`alarm:unblock`** — only `policy:create`/`policy:delete` — so block/unblock is exactly a rule create/delete pair keyed by the alarm `aid` back-reference. Unblock is a **bounded delete of the alarm's rule** (`policy:delete` on that rule), exposed as its own scoped tool (`unblock_alarm_target` or `set_alarm_target_blocked(blocked=false)`); general `delete_rule` stays unexposed/Tier C. My earlier framing ("only reversible if general `delete_rule` is exposed") was wrong. The real work is three small model gaps: carry `aid`/`alarm_type`/`reason` in the **create payload** (so `policy:create` records the back-reference), **parse `aid` onto `FirewallaPolicyRule`** (today it is only in `raw_update_payload`), and **return `pid` from `async_create_rule`** (currently `-> None`).
- **G2 — `list_rules` is a second enabling-service gap.** No non-admin, scoped rule-listing service exists (only admin-gated `get_runtime_inventory`). Note it alongside the rule service as a small dependency. It is also the discovery surface for by-alarm unblock (see O2).
- **G3 — rule create/delete needs `RuleManager` wrappers.** `client.async_create_rule`/`async_delete_rule` exist but the manager has no create method and `async_delete_rule` resolves via a stale `_rule_index`; the standards require services to go through the manager. For the `pid`-based undo, the delete path must not require a freshly-created rule to already be indexed.

### Opportunities (make it better)

- **O1 — affirmed (owner's "could be" is right).** A single **`set_alarm_target_blocked(alarm_id|target, blocked: bool)`** is the clean shape now that block/unblock is a symmetric create/delete pair. It matches the `set_alarm_muted` / `set_ssid_paused` set-to-state precedent, is idempotent by design (`already_in_state` when already in the desired state), and keeps the state decision in one arg. A matched `block_alarm_target`/`unblock_alarm_target` pair is the alternative — more explicit in tool selection. Either works; it is a naming/UX call.
- **O2 — affirmed and elevated to an enabler (related to G1/O1).** Parsing and exposing the `aid` back-reference in `list_rules` is not just provenance — it is how a cross-session agent resolves `alarm_id` → the block rule to delete (by-alarm unblock). Same-session block returns `pid` so unblock can use it directly; `aid` covers the "come back later" path and lets the agent see which rules came from alarms.
- **O3 — dropped (owner is right).** The integration owns both the tools and the contract and ships them together; responses are opaque prose the agent reads, not parsed against a schema, and there is no independent consumer to negotiate a version with. `meta.response_type` is sufficient; a `schema_version` adds cost with no consumer.

### Recommended additions to the plan (from this pass)

1. Restrict the archive tool to single-alarm `mode` (T1).
2. Resolve the block-undo index/refresh timing (T2) and tie `before` to the pre-check (T3).
3. Model the alarm↔rule link: `aid` in the create payload, `aid` parsed on `FirewallaPolicyRule`, `pid` returned from `async_create_rule` (G1/O2).
4. Track the **rule service** (create + scoped unblock) and the **`list_rules` service** as enabling dependencies, with `RuleManager` wrappers (G2/G3).
5. Decide block/unblock naming: single `set_alarm_target_blocked` vs the pair (O1).
