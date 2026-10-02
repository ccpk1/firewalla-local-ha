# Initiative: MCP Capabilities (LLM tool surface)

## 1. Initiative snapshot

- **Status: COMPLETE (2026-10-02).** Phases 4.0–4.5 and 5.0–5.9 are implemented, tested, and documented. **34 tools** (12 read, 17 control, 5 destructive), **five** availability modes, **467 tests** passing, ruff/format/mypy clean. Released as **2.2.0**. The only item that cannot be closed from the repository alone is the live runtime smoke check, which the release checklist owns.
- **Origin:** this plan was split out of `FIREWALLA_LOCAL_SURFACE_COMPLETION_COMPLETED.md` (archived in `plans/completed/`) on 2026-09-30, when that initiative closed after shipping Phases 1–3 in release **2.1.0**. It is the former *Phase 4 — MCP implementation*, carried forward at full fidelity with its decisions, constraints and research notes intact.
- **Why it was split:** the rest of that initiative was a hardening-and-exposure exercise on an existing surface. This is a **new surface** with its own version-gating problem, its own safety model, and a distinct test strategy. Keeping it in the original plan would have held a release for a body of work that had not started.
- **What it builds:** an owned `llm.API` registered by this integration (version-gated at Core 2026.10), exposing ~10 read tools by default and tiered control tools behind a single options toggle, with an **MCP tool reference (the spec)**, a prompt fragment derived from it, and tests.
- **Current state (2026-10-01):** Phases 4.0–4.5 are **Complete** — 33 tools (12 read / 16 control / 5 destructive), four availability modes, 451 tests passing, ruff/format/mypy clean. **Phase 5 (feedback and tuning)** was opened the same day, after the first live end-to-end sessions and a full live pull of every read tool from the working dev box. Phase 5 is driven entirely by measured behaviour on real hardware — see §5.0 and the payload table in §5.2.
- **The problem it solves:** Home Assistant's `mcp_server` integration serves any registered LLM API automatically. Registering our own API means a user with an MCP client (or Aspsist) can ask questions about their network and act on it, with real auth and audit, instead of needing a sidecar or a cloud subscription.
- **Explicitly not in scope:** shipping our own MCP server, emulating MSP endpoints, or building a separate search/query API. Home Assistant already provides MCP; we only contribute tools.
- **Prerequisites — both already satisfied:** the Phase 1 **admin gate is live** (it is the actual write protection, because `/api/mcp` requires no admin) and the Phase 3 **documentation approach is settled**.

## 2. Scope and non-goals

**In scope**

1. **Version gating and graceful degradation** — register nothing on Core older than 2026.10, keep the integration loading normally there, and hide the options that do not apply.
2. **Read tools** — tools delegating to existing services, available in the read tiers. `summary_only` becomes the default when its curated overview tool lands in Phase 5.7. Includes a scoped `list_rules` discovery tool (see 4.2) so the headline `pause_rule`/`resume_rule` actions have a cheap, non-admin target-discovery path.
3. **Control tools** — Tier A and Tier B writes, registered only when the user opts in. Includes **block-alarm-target**, realized as **policy-rule creation** (not an alarm command) — see 4.3.
3b. **Destructive tools (4.3b)** — a fourth `full` mode adds the irreversible/bulk set (`delete_host`, `delete_alarm`, `delete_all_alarms`, `archive_all_alarms`, `delete_rule`), each requiring `confirm: true` and declaring the `destructive` annotation.
4. **Safety design** — annotations (all four flags), idempotency pre-checks, explicit scope requirements, prompt-injection guidance, and destructive operations isolated behind the explicit `full` mode.
5. **Spec, contract and disclosure** — an **MCP tool reference** (`docs/MCP_TOOL_REFERENCE.md`, created first — the authoritative spec + surface record), a prompt fragment derived from it, and user-facing disclosure of the Core 2026.10 requirement (the user guide links the reference).

**Enabling backend (small, but required):** expose the rule create/delete seam that the alarm-block folds into. (1) **`create_rule`** — a thin, admin-gated service over the existing `client.async_create_rule`/`policy:create` with a `RuleManager.async_create_rule` wrapper (services must not build payloads at the service layer). It gains an optional **`alarm_id`/`aid` reference + auto-archive** so the alarm-block reuses `create_rule` rather than duplicating composition, and it must return the new rule `pid` (currently `-> None`) so the tool can report the id to undo. (2) **`list_rules`** — a non-admin, scoped rule-listing service (today only admin-gated `get_runtime_inventory` lists rules) for target discovery and by-alarm unblock. Both are thin over existing managers; the block/unblock **tools** are facades over them. See 4.2/4.3.

**Non-goals**

- **No MCP server.** `mcp_server` already serves any registered LLM API.
- **No destructive operations below `full`.** Irreversible and bulk actions are available only in the explicit `full` mode, with the destructive annotation and a required `confirm: true` input; this is a guard against accidental calls, not user consent.
- **No new floor.** The integration's minimum Home Assistant version stays where it is.
- **No duplicated business logic.** Every tool delegates to a service; tools must not reimplement validation or payload construction. Where the enabling service is missing (rule-create/block), add the thin service + manager method rather than calling the client from the tool.
- **No separate alarm-block layer.** Block/unblock is rule creation/deletion with the alarm recorded as a back-reference (`aid`) — never a parallel rule store (RE Findings 31/34).
- **No MSP-shaped output.** If MSP-shaped data is ever wanted, it belongs in a consumer reading HA's REST API.

## 3. Confirmed constraints (design around these)

These were verified during the original investigation. Do not re-derive them; the research notes hold the evidence.

### Platform and version floor

- **Version floor and gating for this feature: Core 2026.10.** LLM APIs date from 2024.6 and `mcp_server` from 2025.2, so registering a tool needs neither — but 2026.10 is what makes the safety design possible (annotations, `ToolResult`, `integration`, preserved `required`). **Do not raise the integration's overall floor.** Instead guard registration behind a version check, keep the LLM API imports lazy (in `llm_api.py`, imported only inside the guard) so older Core still loads, hide the MCP options where unsupported, and log once rather than raising a repair. Design in the investigation note §10.2.
- **The LLM API module is `llm_api.py`, never `llm.py` — verified.** HA's `llm` integration registers itself as an integration platform under the name `"llm"` (`components/llm/__init__.py`), and `loader.platforms_exists()` discovers a contributing integration by the filename matching the platform name (`loader.py:1259`). So a file named `llm.py` would be **auto-imported by HA's `llm` integration outside our version guard**, expecting the `async_get_tools` platform hook — the wrong mechanism for an owned `API`, and a load-time hazard on older Core. `llm_api.py` is not discovered, and we import it only inside the guard.
- **The version predicate lives in `helpers/llm_support.py`, not `const.py`.** `const.py` must stay framework-free because `api/auth.py` and `api/client.py` import it and `ARCHITECTURE.md` forbids `api/` importing `homeassistant.*`. Keep only the pure tuple `MIN_LLM_TOOLS_HA_VERSION` in `const.py`; put `llm_tools_supported()` (which imports `homeassistant.const`) in `helpers/llm_support.py`, which `api/` never imports.
- **Home Assistant migrated its validation engine from voluptuous to probatio.** `voluptuous` is no longer installed; `requirements.txt` pins `probatio==0.12.4`; `VolSchemaType = probatio.Schema | ...`. **Our code is not broken** — `homeassistant/__init__.py` calls `install_as_voluptuous()` to alias the old name in `sys.modules`, explicitly for custom integrations that still import it. **Use `vol.Schema` everywhere in this integration**, including new LLM tool schemas, so it resolves on both sides of the migration. Never import `probatio` directly.
- **`Tool.parameters` is typed `probatio.Schema` on Core 2026.10+, but the integration must not import `probatio`.** `probatio` does not exist before 2026.10, so a module-level import would raise `ImportError` and stop the integration loading for users on the 2025.10 floor. Build tool schemas with `vol.Schema` / `vol.Required` / `vol.Optional` / `vol.In`, which resolve on both sides of the migration (verified: the shim's top-level surface includes all of them).

### Tool contract

- **The LLM tool contract changed in Core 2026.10.** Tools return `llm.ToolResult(data=..., error=...)` instead of plain JSON, must declare `integration = DOMAIN`, and build parameter schemas with **`vol.Schema`** (version-agnostic). Plain-JSON returns are deprecated (warning until **2027.11**); a missing `integration` warns until **2027.10** for custom integrations; unprefixed tool names break in **2027.3**.
- **Tool names must be `firewalla_local__`-prefixed.** Enforcement lives in `components/llm/__init__.py::_async_report_tool_issues`, which checks tools returned from the **`llm.py` platform hook** and breaks in 2027.3. For our **owned `llm.API`** (Option B) this is a *convention, not platform-enforced* — keep the prefix (it is correct and future-proofs an Option A layer), but do not rely on the platform to catch it. Also note `MergedAPI`/`NamespacedTool` (`helpers/llm.py:420, 490`) prepends `namespace__` when the user picks **"All LLM APIs"** in `mcp_server`, so externally our tools can appear double-prefixed; assert on the un-namespaced name in the contract test.
- **MCP tool annotations require Core 2026.10 — confirmed present.** `llm.ToolAnnotations(read_only, destructive, idempotent, open_world)` now exists in `helpers/llm.py`, and `mcp_server._format_tool` maps all four flags to MCP. **Annotation defaults are the least safe case**, so read tools must declare `read_only=True, destructive=False` explicitly. `required` is now preserved in the MCP schema, and `title` is served. **Set all four flags per tool** — not just `read_only`/`destructive`: `idempotent` for pause/resume/set_name/notify toggles (re-call is a no-op with the pre-check), `idempotent=False` for `run_internet_speed_test`/`wake_host`; `open_world=True` for live-box polls (results are a snapshot of an external system), `open_world=False` for cached reads.
- **Service response modes split, and calling with the wrong mode raises.** Read services are `SupportsResponse.ONLY` (must use `return_response=True`). Write services split: `pause_rule`, `resume_rule`, `set_ssid_paused`, `mute_alarm`, `unmute_alarm`, `archive_alarms` are `SupportsResponse.NONE`, while `set_host_*`, `wake_host`, `run_internet_speed_test` are `SupportsResponse.ONLY`. `core.py:2898-2916` raises `ServiceValidationError` when `return_response=True` hits a `NONE` service **and** when it is omitted on an `ONLY` service. The tool layer **must branch on the service's response mode** — see 4.3.
- **`mcp_server` serves no output schema — responses are opaque JSON text.** `_format_tool` sets only `inputSchema`, `title`, `description`, `annotations`; `call_tool` returns `TextContent(json.dumps(data))` + `isError` with **no** `custom_serializer`. So (a) the response contract is enforced only by our own tests, and (b) every envelope must be strictly JSON-serializable (no `datetime`/`set`/custom objects) or serialization raises. `meta.response_type` is therefore genuinely valuable — the model has no schema to tell it the shape.
- **Input field descriptions reach the MCP `inputSchema` via the schema marker.** Core builds agent schemas as `vol.Required(field, description=...)` / `vol.Optional(field, description=...)` → `probatio.to_openapi(...)` (`helpers/llm.py:690-700`). Both voluptuous and probatio markers accept `description=`, so this resolves on both sides of the migration. Make `description=` **mandatory** on every tool parameter; describe enums by meaning, not value.
- **The prompt fragment is served as a first-class MCP Prompt.** `mcp_server.server.handle_list_prompts` / `handle_get_prompt` expose `llm_api.api_prompt` as a client-fetchable MCP Prompt, not just injected context — this raises the value of the contract-derived prompt in 4.4.

### Exposure and safety

- **MCP endpoint exposure differs by path — verified.** `/api/mcp/<api_id>` raises `Unauthorized` unless `request["hass_user"].is_admin` (except Assist), but `/api/mcp` (the *configured* API) requires **no** admin. Both build the tool context via `HAView.context()` → `Context(user_id=user.id)`, which the tool passes through as `context=llm_context.context`. **Consequence: only the admin-gated service actually stops a non-admin write.** Endpoint checks are not sufficient protection — which is why the Phase 1 admin gate is a hard prerequisite.
- **Writes create a prompt-injection surface.** Host names, DNS names, domains and alarm messages are attacker-influencable and appear in read-tool output. Pairing reads with writes in one toolset means a malicious device name could attempt to steer the model. Mitigations: instruct the model to treat tool results as data only, isolate destructive operations in the explicit `full` mode, resolve targets from read output, and rely on the admin gate.
- **Existing validation is a safety asset.** Reservation and rule validation raise `ServiceValidationError`, and `mcp_server.call_tool` surfaces it to the model as text. Bad writes are rejected at the service layer with an actionable message, independent of the LLM.

### Environment

- **Two distinct MCP integrations exist.** `mcp_server` exposes HA *to* MCP clients; `mcp` consumes external MCP servers *into* HA as LLM APIs. Do not conflate them.

## 4. Phase summary table

| Phase | Focus | Key deliverables | Status | Depends on |
|---|---|---|---|---|
| 4.0 | **MCP tool reference (the spec)** | `docs/MCP_TOOL_REFERENCE.md` — conventions + grouped tool catalog + per-tool template; the authoritative spec & surface record, referenced from the user guide. **Complete** — covers all 34 tools; a contract test now fails if a registered tool is undocumented | **Complete** | none — **first step** |
| 4.1 | Foundation and older-Core safety proof | version guard (`const.py` tuple + `helpers/llm_support.py` predicate), `llm_api.py` API shell, guarded registration + unload, options toggle, pre-2026.10 proof | **Complete** (329 tests pass) | 4.0 (spec exists) |
| 4.2 | Read tools | **Complete** — 12 read tools in `llm_tools_read.py` (incl. `sync_runtime` and new `get_rules` service), available in read tiers | Complete | 4.1 |
| 4.3 | Control tools | **Complete** — 16 control tools in `llm_tools_control.py` behind `read_and_control`; `create_rule` service + `from_alarm` + `aid` parity; effect tests | Complete | 4.2 |
| 4.3b | Destructive tier | **Complete** — 4th mode `full`; 5 destructive tools (`archive_all_alarms`, `delete_alarm`, `delete_all_alarms`, `delete_host`, `delete_rule`) with `confirm` + `destructive` annotation | Complete | 4.3 |
| 4.4 | Prompt fragment and contract tests | **Complete** — prompt fragment in `llm_tools_common.py` wired as `api_prompt`; consolidated contract tests (`test_llm_contract.py`); alarm timestamp field fix | Complete | 4.0 + 4.2 |
| 4.5 | Tests, docs and disclosure | **Complete** — error-path tests, README footnote, USER_GUIDE MCP section; no quality-scale change | Complete | 4.1–4.4 |

**Phase 5 — feedback and tuning.** Driven by live use on real hardware (2026-10-01). The surface is built and working; these phases fix what live data revealed.

| Phase | Focus | Key deliverables | Status | Depends on |
|---|---|---|---|---|
| 5.0 | Correctness fixes from live pulls | **Complete** — D1 `window` default (`last_60_minutes`); D7 WAN events app filters + 7-day window + `system_reboot`; D8 WAN usage `["day","week"]`; D4/D5 VPN pseudo-host caveats; D6 naming roles | **Complete** (443 tests pass) | 4.5 |
| 5.1 | Privacy defaults and disclosure | **Complete** — default flipped to `summary_only`; user-guide tier ladder with the public-IP and external-endpoint lines; options labels describe what each tier sends ("recommended" removed); README section; credential guarantee **verified in code** and pinned by a test | **Complete** | 5.7 |
| 5.2 | Payload reduction | **Complete** — `list_hosts` `detail: summary\|full` + filters; `list_rules` filters + product-purpose exclusion + `applies_to`/`tag_refs`/`purpose`; `vpn_client` exposed; default is the inventory's `visible_rules` (117) via a shared predicate. Measured live: hosts **−22%**, rules **−53%**, VPN-only **−98%**, rules-enabled **−78%** | **Complete** (452 tests pass) | 5.0 |
| 5.3 | Discovery gaps | **Merged into 5.7** — `get_network_overview` is the shared discovery and curated-summary tool; no separate network/group/user list tools | **Merged into 5.7** | 5.2 |
| 5.4 | Rule-model clarity | **Complete** — `applies_to` + `tag_refs` + `purpose` on rule summaries; GUI→name resolution needed **no work** (verified: 0 of 89 `applies_to` values are GUIDs). Prompt paragraph still owed under 5.6 | **Complete** (448 tests pass) | 5.2 |
| 5.5 | Runtime sync | **Complete** — non-admin `sync_runtime` service (read tier, `SupportsResponse.ONLY`) + read-tier tool. Live: first call **13.63 s**, repeat **0.00 s** with an identical timestamp (debounce proven) | **Complete** (451 tests pass) | 4.5 |
| 5.6 | Action confirmation and response specificity | **Complete** — prompt instructions for precise action reporting (`before`/`after`, `already_in_state`, `undo`), blast-radius confirmation, and the rule-attachment model; reference notes that confirmation is the client's to enforce | **Complete** (462 tests pass) | 5.1 |
| 5.7 | Anonymous (summary-only) tool tier | **Complete** — 5th mode `summary_only` (now the default); `get_system_overview` service + tool; the anonymous tier registers that one tool with a schema that cannot request identifiers | **Complete** (460 tests pass) | 5.2 |
| 5.8 | Config-change re-registration + network-config hosts | **Complete** — **D9** LLM mode change now reloads and re-registers (verified by test); **D10** `get_network_config` host section is now an opt-in `include`, absent by default | **Complete** (441 tests pass) | 5.0 |
| 5.9 | VPN device counts on the system-status entity | **Complete** — `ATTR_SYSTEM_VPN_DEVICES_TOTAL` / `_ONLINE` / `_OFFLINE` on the system-status entity, via shared `host_manager` count accessors also used by the summary | **Complete** (460 tests pass) | 5.7 |

Ordering inside Phase 5 is risk-ordered again: **5.0 fixes a guaranteed 400 and undocumented nulls before anything else is built on those payloads**; **5.1 changes a default and is user-visible, so it lands before feature work**; **5.2 reduces payloads, which shrinks the problem 5.3/5.4 then solve**.

Ordering across the initiative is deliberate: **4.0 defines the spec first** (a design deliverable, not code), so every tool is written to one consistent pattern. Then implementation is risk-ordered — the riskiest constraint (**older-Core safety**, 4.1) is proven **before any tool is built**.

## 5. Per-phase details

### 4.0 — MCP tool reference (the spec) — **first step**

**Author `docs/MCP_TOOL_REFERENCE.md` before any code.** This is the single authoritative **spec and surface record**: it lists every available and planned tool in logical groups, and Phases 4.2–4.5 build to it. It is **separate from `docs/USER_GUIDE.md`** and **referenced from the USER_GUIDE MCP section** — the guide links here rather than duplicating the catalog.

**Why first:** one consistent tool pattern is far easier to build and review against than to retrofit. Writing the reference forces the naming, input, output and grouping decisions up front; the code then matches the spec instead of the spec drifting after the code.

**Doc structure (top to bottom):**
1. **Conventions (the shared contract)** — the read envelope + action-result envelope, the units/suffix convention, tool naming, the four annotation flags, per-service response-mode, and the JSON-safe / no-output-schema note. Kept in one place so the prompt and the tools cannot drift from it.
2. **Tool catalog (grouped, ordered)** — every tool, in the groups below, each following one fixed template.

**Logical groups (order = discover → understand → act):**
1. **Know my network** (discovery) — `list_hosts`, `list_rules`, `get_network_config` (`get_network_segment_report`). *(Note: `get_runtime_inventory` is deliberately **not** exposed — see Decisions.)*
2. **Usage & health** (analytics) — `get_network_usage` (top talkers), `get_wan_usage`, `get_wan_events`, `get_user_usage` (time), `get_internet_quality`, `get_speed_tests`, `get_wireless_status`.
3. **Manage devices** (host writes) — `set_host_name`, `set_host_dhcp_reservation`, `set_host_dns_hostname`, `set_host_device_type`, `set_host_notify_when_next_online/offline`, `wake_host`.
4. **Control access** (rules + wireless) — `pause_rule`, `resume_rule`, `set_ssid_paused`.
5. **Respond to alarms** — `get_alarms`, `set_alarm_muted`, `block_alarm_target`, `unblock_alarm_target`, `archive_alarm`.

Within each group: **reads first, then controls**, ordered by likely intent. List the **Full-only destructive set once**, in a closing section (`delete_host`, `delete_alarm`, `delete_all_alarms`, `archive_all_alarms`, `delete_rule`); and list the **never-exposed** items (`get_runtime_inventory`, generic `create_rule`).

**Per-tool template (pattern adherence — every tool uses this exact shape, in this order):**
- **Name** — `firewalla_local__<name>`
- **Answers** — the user question it responds to (one line)
- **When to use / not to use** — disambiguation from its nearest sibling
- **Inputs** — flat, each with type + `description` + valid values / how to discover them
- **Returns** — the envelope (read) or action-result (control) shape
- **Availability & tier** — default-on read / control behind the toggle / A / B
- **Reversibility & undo** — for controls (the `undo` call)
- **Annotations** — the four flags

**Tool-authoring standard (apply to both this reference and the runtime tool descriptions):**
- **Naming** — `firewalla_local__<service_name>`, `<verb>_<noun>` (`list_`/`get_`/`set_`/`pause_`/`resume_`/`block_`/`unblock_`); control tool names can mirror the service names exactly. Note the deliberate **intent-over-CRUD** choice for `block_alarm_target`/`unblock_alarm_target` (vs generic `create_rule`/`delete_rule`).
- **Flat params over nested objects** — "nested objects are awkward for the LLM." `block_alarm_target`/`set_alarm_muted` take flat `target_type`/`target_value`/`scope_type`/`scope_value`, not a raw dict. (Our local rule payloads stay flat: `type`/`target`/`scope` — do not copy the MSP nested `{"type":..., "value":...}` shape.)
- **Description content** (the model reads these) — contrast near-neighbors (`archive` "unlike `delete_alarm`, which is irreversible"); state reversibility + the undo verb (`delete_rule`: "irreversible — consider `pause_rule` to disable it reversibly"); name side effects; flag default blast radius (`mute` default `matchAll` = network-wide); enum + when-a-value-is-required (`target_type: 'alarm_type' (no value) or 'domain' (target_value = the domain)`); param provenance/discovery-first ("`rule_id` comes from `list_rules`"); bold the gotcha + document the return + one worked example. The API prompt carries the shared preference for these purpose-built tools; do not repeat it in every tool description.
- **Field whitelist** — a `RULE_CREATE_FIELDS`-style constant mirroring **`FirewallaRuleCreatePayload`**, used by `from_alarm` to carry only creatable fields and to document `create_rule` inputs (do not copy the MSP field set).

Keep it simple and consistent — this document is the pattern every tool must match. The contract tests (4.4/4.5) assert against it.

### 4.1 — Foundation and the older-Core safety proof

**How to test pre-2026.10 without running pre-2026.10 — this is the practical answer.** You do **not** need an old Home Assistant instance. The three real failure modes are all testable on latest Core:

1. **Guard logic — pure unit test.** `llm_tools_supported()` is a tuple comparison. Test it directly with values below, at, and above `(2026, 10)`. `llm_support.py` imports `MAJOR_VERSION, MINOR_VERSION` from `homeassistant.const`, so patch the **integration's** binding (`custom_components.firewalla_local.llm_support.MAJOR_VERSION` / `.MINOR_VERSION`) — patching `homeassistant.const` will not affect an already-bound name.
2. **Conditional wiring — mock the helper.** Patch `llm_tools_supported()` to return `False` and assert: setup **succeeds**, `llm.async_register_api` is **not** called, and no MCP option is offered. This is the test that protects existing users.
3. **No eager imports — static AST test.** Walk the source of every module that loads unconditionally and assert no **module-level** `import probatio` or `from homeassistant.helpers.llm import ...ToolResult/ToolAnnotations/...`. This is the highest-value test in the set, because a module-level import is an `ImportError` at load time that a latest-only CI run will **never** surface.

Optional and lower priority: a CI matrix leg on 2025.10. Genuinely thorough, but slow, and items 1–3 cover the actual failure modes. Defer unless the cost is trivial.

- [x] Add the version constant to `const.py` — `MIN_LLM_TOOLS_HA_VERSION: Final = (2026, 10)` **only** (a pure tuple; `const.py` must stay framework-free because `api/auth.py` and `api/client.py` import it, and `api/` may not import `homeassistant.*`).
- [x] Add the predicate to a **new HA-aware module `helpers/llm_support.py`** (not `const.py`, not `api/`): `llm_tools_supported() -> bool` comparing `(MAJOR_VERSION, MINOR_VERSION)` imported from `homeassistant.const`. `api/` never imports this module.
- [x] Create **`llm_api.py`** containing the API class only — **no tools yet**. **Do not name it `llm.py`** — that is HA's integration-platform filename, auto-imported by the `llm` integration outside our guard (verified: `components/llm/__init__.py` registers the `"llm"` platform; `loader.platforms_exists()` discovers it by filename). API id strategy implemented (bare `firewalla_local` for the sole entry; suffixed beyond; entry-id fallback on collision).
- [x] Register in `async_setup_entry` **inside the guard only**, and unregister with `entry.async_on_unload(unsub)`. Do **not** import `llm` or `llm_api` at module top level in `__init__.py` — `llm_api` is imported lazily inside the guarded branch.
- [x] Confirm the registration lifecycle: the API is unregistered on entry unload (covered by `test_api_is_unregistered_on_entry_unload`) and does not leak across reloads.
- [x] **Prove the older-Core path before building anything else.** Covered by the guard boundary tests, the mocked-helper wiring test, and the static AST test in `tests/components/firewalla_local/test_llm_support.py`.
- [x] Add the options toggle (three-state: Off / Read only default / Read and control), hidden when unsupported (`system_settings` step; `SelectSelector` + `CONF_LLM_TOOL_MODE`).

**Verification note (2026-10-01):** the dev/test environment runs **Home Assistant 2026.9.0b0**, i.e. *before* the gate boundary — so on this env `llm_tools_supported()` is `False` and nothing registers, which is itself the older-Core behavior under test. The supported-path tests patch the predicate to exercise registration. **Runtime verification against 2026.10 (a live client seeing the tools) must wait until the dev env is upgraded to 2026.10.**

### 4.2 — Read tools

- [x] Implement the ~10 read tools, each delegating via `hass.services.async_call(DOMAIN, <service>, tool_args, context=llm_context.context, blocking=True, return_response=True)`. Read services are `SupportsResponse.ONLY`, so `return_response=True` is correct here (do **not** reuse this recipe for the `NONE` control tools — see 4.3).
- [x] **4.2a — infrastructure + first tools.** `llm_tools_read.py` (`_FirewallaReadTool` base: injects `config_entry_id`, wraps `ToolResult(data={"result": …, "meta": {"response_type": …}})`; `_READ_ANNOTATIONS` = read-only/idempotent/`open_world=False`), `ListHostsTool`, `ListRulesTool`, wired into `llm_api.py`. New non-admin **`get_rules` service** (`RuleManager.get_rules()`, `FirewallaPolicyRule.alarm_id` property) with `services.yaml` + translation entries. Tests: `test_llm_tools.py` (envelope, flat rule shape incl. `alarm_id`, host records, annotations, off-mode absence).
- [x] **4.2b — remaining read tools:** `get_network_config`, `get_network_usage`, `get_wan_usage`, `get_wan_events`, `get_user_usage`, `get_internet_quality`, `get_speed_tests`, `get_wireless_status`, `get_alarms`. All thin `_FirewallaReadTool` subclasses with flat, described inputs; `refresh` exposed optionally (slow, usually unnecessary). Tests cover envelope, annotations/idempotent/`open_world=False`, full-catalog pin, and per-parameter descriptions. **357 tests pass.**
- [x] Add a scoped **`list_rules`** discovery tool (rule_id, name, `is_paused`/`enabled`, action, target scope) backed by the rule inventory (`RuleManager.get_*` / runtime inventory rules slice). This is the cheap, non-admin way to resolve `rule_target` before `pause_rule`/`resume_rule`; today that discovery requires the heavy admin-gated `get_runtime_inventory`. Prefer a dedicated service (or a `detail: "rules"` filter) over exposing the full inventory. **Also resolve scope targets** (person → device-group tag, valid app ids, network) so a model can compose rule/block scope without guessing — the `list_users`/`list_apps` helper pattern.
- [x] Frame host discovery as **`list_hosts`** (or shape `get_host_inventory` this way): return each host's `name`, `device_type`, `ip_assignment.mode` / `reserved_ipv4`, and online status **as the primary shape**, not as a "name mapping" by-product. This is the discovery feed for the crown-jewel **DHCP-reservation and rename** workflows — the name should read like "show me my devices," not "resolve a name." (Keep `get_host_name_mapping` only if a pure name→host resolver is separately useful.)
- [x] Make the **high-value host/network/wireless controls first-class** — these differentiate us from any MSP-based tool (whose only write is a device rename): `set_host_dhcp_reservation`, `set_host_name`, `set_ssid_paused`, `set_host_dns_hostname`, `set_host_device_type`, `set_host_notify_when_next_online/offline`, `wake_host`, `get_network_segment_usage` (top talkers), `get_wireless_status`, `get_internet_quality_report`/`run_internet_speed_test`. Call out the **read→write pairings** in the prompt fragment: `list_hosts` → DHCP reserve/rename; top talkers → pause rule; `get_wireless_status` → `set_ssid_paused`.
- [x] Every tool declares `name` (`firewalla_local__`-prefixed), `title`, `description`, `integration = DOMAIN`, `annotations` (**all four flags**), and a `vol.Schema` parameter schema (**never `probatio`**).
- [x] Every parameter carries **`description=`** on its `vol.Required`/`vol.Optional` marker; enums are described by meaning. This is how field guidance reaches the MCP `inputSchema`.
- [x] Return `llm.ToolResult(data={"result": ..., "meta": ...})`. Add `meta.response_type`, and `applied_limit`/`truncated` only when a limit actually cut data. The envelope must be **strictly JSON-serializable** (no `datetime`/`set`).
- [x] Wire multi-entry resolution: each tool must resolve the correct entry (from `llm_context` or an explicit selector) rather than assuming one.
- [x] Read tools are **registered by default**; the option can turn them off.

### 4.3 — Control tools

- [x] **Verify the Phase 1 admin gate is still live first.** This is the actual write protection, because `/api/mcp` requires no admin.
- [x] **Branch delegation on the service's response mode — the single `return_response=True` recipe is wrong here.** `pause_rule`, `resume_rule`, `set_ssid_paused`, `mute_alarm`, `unmute_alarm`, `archive_alarms` are `SupportsResponse.NONE` → call with `return_response=False` and **synthesize** the result envelope. `set_host_*`, `wake_host`, `run_internet_speed_test` are `SupportsResponse.ONLY` → call with `return_response=True` and wrap the payload. Calling the wrong way raises `ServiceValidationError` (`core.py:2898-2916`). Record each service's response mode in the MCP tool reference's conventions section and add one test per control tool asserting the call mode matches the registration.
- [x] **Define a standard action-result envelope** for control tools (the `NONE` writes return nothing, so the tool builds the response). Required fields: `status` (`applied` | `already_in_state` | `failed`), `changed`, `target` (resolved id + name), `before`/`after`, `undo` (the exact reversing call), `warnings`. Keep it strictly JSON-serializable.
- [x] Implement Tier A (`pause_rule`, `resume_rule`, `set_ssid_paused`, `set_host_dhcp_reservation`, `set_host_name`, `wake_host`, notify toggles, `set_host_device_type`) and Tier B (`set_host_dns_hostname`, `run_internet_speed_test`) — registered **only** when the option enables control tools.
- [x] **Keep destructive tools out of control modes.** `delete_host` and the other irreversible/bulk actions are implemented only in the opt-in `full` mode with the destructive annotation and `confirm: true`; that input is not user confirmation.
- [x] **Block-alarm-target folds into `create_rule` — not a separate block service/command. Per RE Findings 31/34 and USER_GUIDE §Services, blocking a target from an alarm is just **rule creation** (`policy:create`, `action: block`) with the alarm's target/scope and an `aid` back-reference; **unblocking is `delete_rule`** on that rule. The client has **no `alarm:block`/`alarm:unblock`** — only `policy:create`/`policy:delete` — and the composition is ~99% identical to any rule create, so it must **reuse `create_rule`, not duplicate it**. There must be **no separate alarm-block layer or block-specific composition**. Shape:
  - **`create_rule` is the base** (expose a thin, admin-gated `create_rule` service over the existing `client.async_create_rule`/`policy:create`, with a `RuleManager` create wrapper). The rule composition (target/scope/action → payload) lives in **one** manager path used by every rule create.
  - **Block = `create_rule` + an alarm reference.** Fold an optional **`alarm_id`** into `create_rule`: when present, a shared **`FirewallaRuleTemplate.from_alarm(alarm, scope_override)`** helper derives the template from the alarm (target = app/domain, scope = device/user/network — the app's editable "Matching App / scope" dialog), records the `aid`/`alarm_type`/`reason` back-reference, and triggers **auto-archive** of the alarm (the app's behavior). This is the only alarm-specific logic (~1%): `from_alarm`, the `aid` write, the archive call.
  - **Unblock = `delete_rule`** (existing base service) on the rule created for the alarm — resolved by `pid` (same session) or by the `aid` back-reference (cross session). General `delete_rule` stays unexposed/Tier C as a broad MCP tool; the block/unblock **tool** is a bounded facade (below).
  - **Tool surface: a matched `block_alarm_target` / `unblock_alarm_target` pair** (clear verbs, matching the Firewalla app's Block/Unblock buttons and the create/delete semantics), delegating to `create_rule` (block) / `delete_rule` (unblock); idempotent via `already_in_state`. Do **not** expose generic `create_rule`/`delete_rule` as broad MCP tools (blast radius). A single `set_alarm_target_blocked(alarm_id, blocked: bool)` set-to-state tool (matching `set_alarm_muted`/`set_ssid_paused`) is the acceptable consolidation alternative.
  - **Parity additions ("add a reference to get parity")** — three small model gaps to make the alarm↔rule link work: (1) carry `aid`/`alarm_type`/`reason` on the **create payload** (`FirewallaRuleCreatePayload`/`FirewallaRuleTemplate`) so `policy:create` records the back-reference; (2) **parse `aid` onto `FirewallaPolicyRule`** (today it is only in `raw_update_payload`) so `list_rules` and unblock resolve it; (3) **return the created `pid`** from `async_create_rule` (currently `-> None`; `policy:create` returns `{"policy": {"pid": ...}}`) so the action-result envelope reports the id to undo.
  - **Undo/`delete` resolution:** same-session block returns `pid`, so unblock `policy:delete`s that `pid` directly (no index lookup); cross-session unblock resolves `alarm_id` → rule by `aid`. If using the `pid` path, ensure `async_delete_rule` does not require a stale `_rule_index` entry (a freshly created rule is not indexed until refresh) — fall back to `client.async_delete_rule(pid)` or optimistically register. Each block consumes a finite `policyRuleNumber` slot (RE Finding 31) — state this in the tool description.
- [x] **Alarm tools — keep mute/silence distinct from block/rule** (tiering per investigation note §12): `get_alarms` read tool (default 10, `count` to widen — the cap matters more for an LLM, since a large payload is context, not just data); `set_alarm_muted` (mute/unmute **silences** via `mute_alarm`/`unmute_alarm`, `exceptionRules`) and `block_alarm_target`/`unblock_alarm_target` (block/unblock **rules**, above) and `archive_alarm` (single, control — no un-archive) as control tools; the bulk `archive_all_alarms` and `delete_*` alarm actions are Full-only destructive; `delete_alarm` and both bulk commands as **Tier C excluded**. The mute tool must require an explicit scope (`matchAll: 1` mutes for every device) and use the app's three fixed durations (`1h`/`today`/`always`) as an enum.
- [x] **Restrict `archive_alarm` to a single alarm.** `ARCHIVE_ALARMS_SCHEMA.mode: "this" | "all_active"` — `all_active` **is** the bulk "ignore all" (RE Finding 32). The tool must accept only `mode: "this"` + `alarm_id`; do not pass `all_active` through, or the Tier C bulk exclusion is silently bypassed.
- [x] Set annotations per tool — **all four flags**: `read_only=False` for writes; `destructive` only for the Full-only destructive set (e.g. `delete_host`); `idempotent` for pause/resume/set_name/notify/block (a repeat is a no-op after the pre-check), `idempotent=False` for `run_internet_speed_test`/`wake_host`; `open_world=False` everywhere.
- [x] Add idempotency pre-checks (do not act when already in the desired state) and surface them as `status: already_in_state` rather than a silent no-op.
- [x] State effect, reversibility and how to undo in every control tool's description (the `undo` field also carries it machine-readably).
- [x] **Standardize host resolution + `target` echo across every host write** (`set_host_*`, `wake_host`): the tool accepts a human-meaningful selector (name/MAC), resolves it to one host, and echoes the resolved host in the action-result `target` field — the agent never threads `host_id` by hand. Keep this consistent across all host writes.
- [x] **Never blindly retry a non-idempotent write.** `run_internet_speed_test` and `wake_host` are `idempotent=False`; a timed-out call must not silently double-apply (the third-party tool encodes exactly this). Pair the annotation with the call behavior.

The earlier checklist language describing all Tier C operations as excluded is superseded by the settled Full-only destructive tier in the decisions below.

### 4.4 — Prompt fragment and contract tests

- [x] **Derive the prompt fragment from the MCP tool reference** (4.0) — `llm_tools_common.py` holds one `PROMPT` constant (guard-loaded, alongside the shared `format_tool_name` helper) wired as `api_prompt` in `llm_api.py`. Covers the units/suffix contract, `metadata`/`provenance`/`warnings`/`is_partial`, opaque `TL-`/`TLX-` IDs, `refresh` cost, both envelope shapes, the four modes, `undo`/`already_in_state`, read→write pairings, "prefer these tools", and the injection instruction. A contract test asserts the required concepts are present so it cannot silently drift.
- [x] The **tool-authoring standard** (naming, flat params, description patterns, field whitelist) lives in **4.0**; applied to the runtime tool descriptions.
- [x] **Conformity fix:** `fired_at` / `expires_at` held epoch numbers under the ISO-suffixed `_at` name. Corrected to the established `X_at` (ISO 8601) + `X_at_timestamp` (epoch) pairing used by speed tests and internet quality. (2.1.0 was released the previous day with no consumers, so this is a clean fix rather than a breaking change.)
- [x] Contract tests (consolidated here from 4.5) in `tests/components/firewalla_local/test_llm_contract.py`: full tool contract (name prefix, title, description, `integration`, `open_world=False`), per-parameter descriptions, destructive annotation set, read/write split, prompt coverage, and JSON-serializability of both envelope shapes via `json.dumps`.

### 4.5 — Tests, docs and user-facing disclosure

- [x] **Per-tool error paths** (`test_llm_errors.py`, 17 tests): missing required arg, unknown arg, unknown tool, invalid duration, bad reservation mode, missing alarm selector, missing mute scope, and confirm gating. Plus a read-tool error path.
- [x] **Gating tests** and the **static AST no-eager-import test** shipped in 4.1 and still pass (the guard-loaded module list now includes `llm_tools_common.py`).
- [x] **README asterisk + footnote** added to the Home Assistant requirement line, stating the 2026.10 requirement for AI/MCP tools and that older Core is unaffected.
- [x] **USER_GUIDE MCP section** ("AI assistants and MCP") added under "Using your data across Home Assistant", covering enablement, the four modes with the destructive warning, the admin gate, and the 2026.10 requirement — **linking `docs/MCP_TOOL_REFERENCE.md`** for the catalog rather than duplicating it. The options-flow list also references it.
- [x] **The MCP tool reference is the authoritative surface record** — no separate `SURFACE_INVENTORY.md`; the contract tests enforce it.
- [x] `quality_scale.yaml` **needs no change** — there is no MCP/LLM rule, and the closest rules (`action-setup`, `strict-typing`) are already `done` with comments that remain accurate.

**Two defects found and fixed during 4.5:**

1. **Tools crashed with a bare `KeyError` on a malformed call.** `async_call_tool` does *not* validate args against `tool.parameters` (its docstring claims to, but it does not — verified), and `mcp_server.call_tool` passes client arguments straight through. Tools that indexed `tool_input.tool_args[...]` therefore raised `KeyError` on a missing required argument. Fixed with a `_args()` helper on both tool bases that validates against the declared schema, so a missing/unknown argument is a clean validation error. All direct indexes removed.
2. **Destructive tools advertised a `confirm` parameter they ignored.** Their schemas declared `confirm` required, but the bodies hard-coded `True`, so the documented "requires `confirm: true`" gate was not real. The destructive tools now honour the caller's `confirm` (absent → clean validation error), matching the reference. `unblock_alarm_target` (the sanctioned undo, control tier) no longer advertises `confirm` and sets it internally.

### 5.0 — Correctness fixes from live pulls

**Evidence base.** Every read tool was pulled live from the dev box on 2026-10-01 through the authenticated REST API (entry `01KY0E6H9YV3EYEPEZWHDSNCTT`). Real inventory: **218 hosts** (109 online / 109 offline, 24 with no IP, 103 with DHCP reservations, 5 VPN pseudo-hosts), **305 rules**, **28 groups**, **10 users**, **10 networks**. These are not synthetic counts — they are what the fixtures must eventually approximate.

- [x] **D1 — `get_network_usage` cannot be called with its documented defaults.** `GET_NETWORK_SEGMENT_USAGE_SCHEMA` declares `window` `vol.Optional`, but the handler raises `TRANS_KEY_EXCEPTION_NETWORK_USAGE_WINDOW_REQUIRED` (`"Provide a window for this network segment usage service call."`). The tool description claims *"Defaults to the service default when omitted"*, so a compliant call **always fails**. Confirmed live: the call without `window` returned HTTP 400. **Fix: default `window` to `last_60_minutes`** — the smallest of the four allowed values (`last_60_minutes`, `last_24_hours`, `last_30_days`, `last_12_months`) and the one that keeps the payload small by default. Keep the schema and the description in agreement, and add a test that the no-arg call succeeds.
- [x] **D7 — `get_wan_events` returns DNS health probes instead of WAN events.** **This is the most serious defect found.** Live pull: **98 of 99 records are `family: "dns"`**, all with `state_key: "127.0.0.1"` and `dns_test_domain: "github.com"`, roughly every three minutes over a 75-hour span. Exactly **one** record is a real WAN event. The owner's app shows three WAN events for the same period (one latency alert, `WAN-ONE` restored, WAN disconnected) and no per-minute activity. Root cause: **`async_get_wan_events_payload` sends no `filters`.** The pairing/init path *does* (`api/client.py:723-735`). Compounding factor: `_SUPPORTED_WAN_EVENT_STATE_FAMILIES` **includes `"dns"`**, admitting DNS probes to the normalized model. **Root cause proven live 2026-10-01** (now recorded as `REVERSE_ENGINEERING_WORKFLOW.md` **Finding 40**):

  | `item=events` read | Records | Composition |
  |---|---:|---|
  | unfiltered, `limit_count: 100` | 100 | **93 `dns`**, 6 `ping`, 1 `ping_RTT` |
  | app filters, `limit_count: 100` | **2** | `wan_state` ×2 |
  | app filters, `min` = 7 days | **2** | `wan_state` ×2 |
  | ping filters, `min` = 7 days | **1** | `ping_RTT` ×1 |
  | `dns` filter only, `min` = 7 days | **162** | `dns` ×162 |

  **Fix, per owner direction (2026-10-01):**
  1. **Send the app's link-state filter set** — `{action, system_reboot}`, `{state, dualwan_state}`, `{state, wan_state}` — so the tool returns real link events. **Also add `system_reboot` to `_SUPPORTED_WAN_EVENT_ACTION_FAMILIES`**, which today accepts only `ping_RTT`/`ping_lossrate` and would silently drop the app's reboot filter.
  2. **Exclude `dns` by default, available only as an explicit exception.** The app never surfaces it; 162 records/week of self-generated resolver probes is not a WAN event. Keep it reachable behind an opt-in rather than removing it from the family set outright.
  3. **Remove `ping_RTT` / `ping_lossrate` from WAN events — and do not move them to Internet Quality either.** Both destinations are wrong. Internet Quality is a **data and facts report** (live: `ping_latency_ms` 23.1, `ping_latency_max_ms` 32.1, `ping_packet_loss_percent` 0.17, all from `networkMonitorData`), and the owner's direction is that it stays that way. So the alerts leave WAN events and are **not** added to quality.

     **Correction to a reasonable assumption — they are not alarms.** The owner expected these to live with alarms, and that would be the natural home. But **no ping, latency or loss alarm type exists.** The full known taxonomy (`REVERSE_ENGINEERING_WORKFLOW.md` Finding 30) is `ALARM_INTEL`, `ALARM_LARGE_UPLOAD`, `ALARM_UPNP`, `ALARM_NEW_DEVICE`, `ALARM_VPN_CLIENT_CONNECTION`, `ALARM_VIDEO`, `ALARM_GAME`, `ALARM_PORN`, `ALARM_DEVICE_BACK_ONLINE`, `ALARM_ABNORMAL_BANDWIDTH_USAGE`, `ALARM_OVER_DATA_PLAN_USAGE`, `ALARM_VPN_DISCONNECT`, `ALARM_DUAL_WAN` — all content-based or connectivity-state-based. Live confirms it: 2 active alarms, both `ALARM_VIDEO`, and no ping/latency/loss type anywhere across 230 archived alarms or 99 exceptions. `ALARM_DUAL_WAN` is dual-WAN *state*, not latency.

     They are a **standalone threshold-crossing feed** (`item=events`, `event_type: action`, `action_type: ping_RTT|ping_lossrate`, carrying `rtt`/`rttLimit` and `lossrate`/`lossrateLimit`). Not alarms, and **they must not be synthesised into alarm records** — fabricating alarm rows would corrupt the alarm surface for a cosmetic gain.

    **Settled owner decision:** keep these alerts out of the tool surface. They are not WAN connectivity events, not Internet Quality facts, and not alarms; do not synthesize records or add an opt-in flag.
  4. **Default to a 7-day `min` window.** Filtered output is tiny (2 records for the entire retained history here), and `min` **is** honoured by `item=events` — unlike alarm reads, which silently ignore every time parameter (`REVERSE_ENGINEERING_WORKFLOW.md` Finding 39). Prefer `min` as the primary selector; a count limit over an event firehose is unstable by construction. Keep `limit` as a safety cap, and expose `offset` for paging.
- [x] **D8 — `get_wan_usage` defaults to the period least likely to be wanted.** Live `current_periods` defaults to `["month"]`. The owner's assessment is that the useful answers are **day and week** totals without history. Measured: default (month only) 1,924 B; `["day","week"]` **2,464 B (+540 B)** and it surfaces the week total (15.7 GB live); month+week+day 2,981 B; history is the only thing that inflates it (`detail=full` + 30 daily periods = 22,551 B, **12×**). **Fix: default `current_periods` to `["day","week"]`** and keep `history_count` at `0` by default, so the common question costs ~2.5 KB and history must be asked for explicitly.
- [x] **D4 — `host_id` is not always a MAC.** 5 live records are VPN peers with `mac: null` and base64-ish ids (`wg_peer:<…>`, `awg_peer:<…>`, `kind: "pseudo_host"`). Every host control tool takes `host_mac`, so an agent that pipes `host_id` into `set_host_name`/`wake_host` will fail confusingly. **Fix:** state the `kind` discriminator in `list_hosts` and in the host-write tool descriptions, and say these peers have no MAC.
- [x] **D5 — `ip_assignment` is nullable.** The same 5 pseudo-hosts carry `ip_assignment: null`. Document it; do not assume the nested object exists.
- [x] **D6 — three name-like fields with no guidance.** `list_hosts` exposes `host_name`, `dns_hostname`, and `dhcp_name`. Live divergence: `dns_hostname` differs from `host_name` in only **3 of 218** (pure sanitisation: `UxPlay@im-lost` → `uxplayim-lost`, `kadens-chromebook` → `kadens.chromebook`, `Intel Corporate` → `intel.corporate`), but **`dhcp_name` differs from `host_name` in 91 of 154 (59%)** with device-supplied junk (`nvidia-shield` → `android-66fc79bd9bb55411`, `ring-backdoor` → `RingDoorbell`, `ftv-veranda` → `amazon-21315c414`). `REVERSE_ENGINEERING_WORKFLOW.md` Finding 17 is explicit: `dhcp_name` is a provenance-specific DHCP field, **not** a fallback alias for `host_name`; `ARCHITECTURE.md` and `DEVELOPMENT_STANDARDS.md` both forbid reintroducing such aliases. **Fix:** label the three fields by role and state plainly that `dhcp_name` must not be used to identify a device. This is the item that "tripped us up during development" — the trap is real and the live numbers quantify it.

### 5.1 — Privacy defaults and disclosure

- [x] **Default to `summary_only`** (superseding the earlier `off` decision — see the Phase 5 decisions). `DEFAULT_LLM_TOOL_MODE` becomes `LLM_TOOL_MODE_SUMMARY_ONLY`. It answers the common questions with **no addresses and no hardware identifiers**, so it is a defensible default for a local-first product, and it makes the feature discoverable. `off` remains available for users who want the surface inert.
- [x] **Remove "recommended" from the `read_only` label** and describe each mode by what it actually sends rather than how it ranks. This matters more now that the default is the restricted tier — the labels have to make the escalation ladder legible.
- [x] **State what actually leaves the network**, by example not inventory: network names and counts (summary mode); device names, IP addresses, and MAC addresses (read mode). Deliberately do **not** publish a full field list yet — that belongs in `MCP_TOOL_REFERENCE.md` later, once the shapes have settled.
- [x] **State the positive guarantee alongside the negative one:** credentials, pairing keys, symmetric keys, and passwords are structurally absent from tool output, not merely omitted. **Verify this claim in code before publishing it** — one pass confirming no serialiser can reach key material.
- [x] **Lead with the anonymous tier.** The strongest sentence available is now *"summary mode sends network names and counts, never addresses or hardware identifiers."* Disclosure of what `read_only` adds comes second.
- [x] **Call out public IP on its own** — `get_speed_tests.public_ip` and `get_wan_events.wan_interface_address` identify the **household on the internet**, a different category from LAN device identity. It is the most sensitive field in the surface and deserves its own line, not a mention inside a list.
- [x] Frame it as capability and boundary, not apology: a firewall MCP that cannot see MAC and IP cannot answer firewall questions. Over-redacting `fqdn`/MAC would make the surface useless — the disclosure and the tier ladder are the honest answer, not removal.
- [x] Update `USER_GUIDE.md`, the options-flow label/description, and `README.md` consistently. **Done 2026-10-01** — user guide gained the five-tier table, the "be deliberate about raising it" warning, and the public-IP / external-endpoint / credential paragraphs; the options selector gained a `summary_only` label and lost "recommended" from `read_only`; the README gained an AI section that leads the risk rather than the reassurance.

**Reference-coverage guard (2026-10-01).** `sync_runtime` and `unmute_alarm` shipped with no mention in `MCP_TOOL_REFERENCE.md` — the authoritative spec — and nothing tied the document to the code, so the drift was invisible. `test_reference_documents_every_registered_tool` now fails if any registered tool is unnamed in the reference, accepting either the prefixed heading form or the bare name used by the index and the destructive list.

### 5.2 — Payload reduction

**Implemented 2026-10-01. Re-measured live on the same box (the numbers below are measured, not estimated).**

| Call | Before | After | Change |
|---|---:|---:|---:|
| `list_hosts` default (`summary`) | 90,908 B | **71,284 B** | **−22%** |
| `list_hosts` `detail: full` | 90,908 B | 96,311 B | +6% |
| `list_hosts` `kind: pseudo_host` (VPN only) | 90,908 B | **1,633 B** | **−98%** |
| `list_rules` default | 72,757 B (305 rules) | **34,363 B** (123) | **−53%** |
| `list_rules` `enabled: true` | 72,757 B | **15,988 B** (58) | **−78%** |
| `list_rules` `include_purpose: ["dap"]` | n/a (no opt-in) | 88,918 B (305) | full set retained |

`list_hosts` `full` grew because `vpn_client` was added to **both** shapes — the new field is worth the 6%, and `summary` still nets −22%.

**Deviation to confirm — `list_rules` default is 123 rules, not the plan's 117.** The plan said to reuse the inventory's `visible_rules` (user-managed **and** not dap **and** not family). The implementation filters on **purpose only**, giving 123. The 6-rule difference is the `system_managed` set — measured live, and all six are **enabled, active blocking rules**:

```
651 block ip 66.132.195.91      enabled=True
648 block ip 3.130.168.2        enabled=True
647 block ip 66.132.172.36      enabled=True
646 block ip 3.131.220.121      enabled=True
645 block ip 18.116.101.220     enabled=True
1   block category default_c    enabled=True
```

These are alarm-intel auto-blocks — consequences of the user's own alarms, not product-owned internals. This earlier recommendation is superseded by the settled Phase 5 decision: the default follows the inventory's `visible_rules` contract (117 rules), while these rules remain available through the explicit opt-in path. The current service filters by purpose only and returns 123, so this is an outstanding 5.2 implementation correction, not a design question. Reuse the inventory classification rather than adding another approximation in the service.

**5.4's "resolve tag GUIDs to names" task is already satisfied — no work needed.** Measured live: of the 89 rules carrying `applies_to`, **zero** are GUID-shaped. Every value resolves to a readable name (`PAYTONS_PHONE`, `KADENS_PHONE`, `KADENS_DEVICES`, `SHARED`, `SVR_PVE`). The GUID names observed earlier are the group's own `name` field *in the inventory*, not what reaches a rule's `applies_to` — the existing resolution path already maps them through the group→user relation. Verified against the specific groups whose inventory names are GUIDs (rules `512`, `508`, `470`, `480`, `504`, `506`) and all resolve cleanly.

**Measured cost of the nine heaviest live payloads.** Filtering and tool instructions are two halves of the same fix — the table lists both.

| Tool | Live bytes | ~tokens | Filtering lever | Tool-instruction lever |
|---|---:|---:|---|---|
| `list_hosts` | 90,908 | 22,727 | name / mac / group / user / network / online / kind / has_reservation | `detail: summary\|full`; state that `summary` is the default for "which device" questions |
| `list_rules` | 72,757 | 18,189 | **default to `visible_rules` (117, not 305)**; `enabled` / `action` / `target_type` / `applies_to` | tell the agent that 59% are internal DAP rules it should not surface |
| `get_wan_events` | 57,762 | 14,440 | **send `filters` — see D7**; exclude `dns` by default; 7-day `min` window | state that the default is real link events only, and that a wider window is cheap |
| `get_alarms` (`detail=true`) | 24,253 | 6,063 | already has `limit` (default 10) | keep the existing "raise limit deliberately" wording |
| `get_wan_usage` (`detail=full` + 30 days history) | 22,551 | 5,637 | **default `current_periods` to `["day","week"]` with `history_count=0` → 2,464 B** | note that history is **12×** the default; ask for it explicitly |
| `get_network_config` | 21,147 | 5,286 | network selector | see D2 — the agent cannot currently discover names |
| `get_network_usage` | 7,623 | 1,905 | `window` + `top_n` | see D1 — must become callable with defaults |
| `get_user_usage` | 3,735 | 933 | already scoped | see D3 — scope targets are undiscoverable |
| `get_wireless_status` | 80 | 20 | none needed | keep as-is |

- [x] **`list_hosts` gains `detail: "summary" | "full"`.** Summary drops `dns_fqdn` (derivable from `dns_hostname` + `dns_domain` — holds for 196/218), collapses `ip_assignment`, and omits `dhcp_name`. Measured field costs: `ip_assignment` 21,676 B, `dns_fqdn` 5,469 B, `dhcp_name` 2,290 B; `host_id` duplicates `mac` for 213/218 at 4,318 B. Expected saving **~40–45%** with no loss of identity. This tool is new in this dev cycle, so the shape can change freely.
- [x] **`list_hosts` gains filters** — `host_name` (substring), `mac`/`host_id`, `group_name`, `user`, `network_name`, `online`, `kind`, `has_reservation`. This is the direct fix for the observed "list everything, then narrow" loop. Live support: 28 distinct group names, 103 reservations, a clean 109/109 online split, 5 pseudo-hosts, 10 networks. Implement filters **on the existing service**, not via a new search service, to keep the tool↔service mapping 1:1.
- [x] **`list_rules` gains filters** — `enabled`, `action`, `target_type`, `applies_to`. Live: 247/305 disabled, actions `block` 173 / `allow` 122 / `qos` 10, types `category` 173 / `mac` 105 / `ip` 12 / `network` 6 / `dns` 5 / `country` 3 / `net` 1.
- [x] **Exclude `dap`-purpose rules by default** (see 5.4). Measured on the tool shape: all 305 rules = **81,435 B**; non-DAP 123 = **29,974 B** (63% cut); non-DAP **and enabled** = **14,119 B** (83% cut). Live `rule_switch_candidate_count` is 116, so ~189 returned rules are not actionable — the payload is carrying mostly noise today.
- [ ] Re-measure after each change against the same live box and record the before/after in the reference. **Deferred to the release checklist (2026-10-02):** no box is reachable from the dev container, so this cannot be run here. The in-repo guarantee is the response *shape* — `list_hosts` `detail: summary` and the rule default are asserted exhaustively by tests — while the byte counts in the table above remain the pre-change baseline. Whoever runs the runtime smoke check should re-pull each tool and update this table.

**Payload-narrowing guidance is part of the tool contract (2026-10-01).** 5.2's table lists a "tool-instruction lever" beside every filtering lever, and only two tools ever carried one (`get_wan_usage`: "history is roughly 12x the size"; `get_alarms`: "raise limit deliberately"). The two heaviest tools — `list_hosts` (~18k tokens live) and `list_rules` (~8.6k) — shipped their filters with no instruction to use them, so the documented "list everything, then narrow" loop was still the path of least resistance. Each heavy tool's description now states plainly that filters narrow server-side and that the model should pass them, and the reference carries the same expectation. `test_large_payload_tools_tell_the_model_to_narrow` pins the four phrases so the guidance cannot be trimmed away silently. This is cheap relative to what it prevents: ~120 tokens of description against an 18k-token payload.

**Reference corrections found while doing this (2026-10-01).** The reference's `get_network_config` entry claimed the network selector was "optional — all networks if omitted", but the handler calls `_resolve_requested_network_required` — one network per call, always. Its `list_hosts` entry listed only `refresh` and the entry selectors, omitting all eight filters and `detail`. Both are the same class of defect as the earlier D2 bug: spec text drifting from the code it is supposed to describe.

### 5.3 — Discovery gaps

- [x] **D2 — the agent cannot discover network names.** `get_network_config` and `get_network_usage` need a network selector, and `_NETWORK_UUID_DESCRIPTION` says to get it *"from list_hosts / get_network_config"* — but `list_hosts` only exposes `ip_assignment.network_uuid` (a GUID, and `null` for the 5 pseudo-hosts), and `get_network_config` needs the selector to be callable at all. Real names (`VLAN60 IOT`, `LAN-MGMT`, `WAN-ONE`, `AmneziaWG`, `OpenVPN`, `WireGuard`, 10 total) are reachable from **no tool**. Today the agent must guess. Fix by exposing network identity in `list_hosts` output and/or a small network-list read surface.
- [x] **D3 — the agent cannot discover group or user ids.** `get_user_usage` requires `scope_target` for `group` and `user` kinds, but `list_hosts` yields MACs only. The 28 groups and 10 users (`CARENS_PHONE`, `CHADS_DEVICES`, …) are therefore unreachable, making group/user usage queries effectively unusable.
- [x] **Consider the Firewalla summary / overview tool** (owner request). One concise, high-level call returning device count, online/offline split, networks with names and IP ranges, group and user counts, rule counts, alarm counts, and WAN status — the shape of the network in one call instead of five. Live numbers show it would replace the common opening sequence. Keep it **concise** and note that it is intended **once per session**; the prompt fragment should point at it as the entry point. Resist explaining how Firewalla works inside the tool — the mechanics belong in the prompt fragment (5.4), where they cost nothing per-call.

#### Recommendation: yes, build it — as Option C, the discovery surface

**Direct answer to "would it be worthwhile, and how would it inform the other tools?"** Yes, and it is the strongest candidate of the three discovery options. Recommendation: **build it, and let it carry the discovery burden rather than adding three separate list tools.**

**Why it is worthwhile — three distinct arguments:**

1. **It closes D2 and D3 in one tool in read tiers.** Networks (D2) and groups/users (D3) are both undiscoverable today, and both are needed as *inputs* to other tools (`get_network_config`, `get_network_usage` need a network selector; `get_user_usage` needs a group or user id). In `read_only` and above, the overview returns networks with names and UUIDs and groups/users with names and ids. `summary_only` deliberately withholds group/user identities and returns counts only. This supplies identifiers exactly where dependent tools are available without weakening the anonymous-tier contract.

2. **It is cheap, and it is the cheapest possible first call.** Every number it needs is already computed in the runtime snapshot — `summary` in `runtime_inventory.py` already carries `host_count`, `devices_total`, `devices_online`, `devices_offline`, `network_count`, `group_count`, `user_count`, `policy_rule_count`, `visible_rule_count`, and the network list with UUIDs and kinds. **This is nearly a serialisation exercise, not new logic** — the same "the data already exists" situation as the `applies_to` fix. A bounded summary should land in the low kilobytes; the current 1.15 MB `get_runtime_inventory` payload is 288k tokens precisely because it dumps every rule and host.

3. **It reduces total session cost, not just latency.** The alternative opening moves today are `list_hosts` (22,727 tokens) or `get_runtime_inventory` (288,343 tokens — and admin-gated). A summary that answers "how many devices, which networks, is the WAN up?" for a few hundred tokens replaces the expensive opening call. **This is the real test to validate:** not "does it save a call" but "does it lower total tokens per session", because it only wins if agents use it *instead of* the big calls rather than *before* them.

**How it informs the other tools — this is the part that makes it more than a convenience.** The summary is the **discovery and routing layer** for the whole surface:

- **It supplies the identifiers every other tool needs.** Network name/UUID → `get_network_config`, `get_network_usage`. Group id / user id → `get_user_usage`. Online/offline counts → whether a device question is even worth asking. Today those come from nowhere.
- **It tells the agent which questions are answerable at all.** Knowing there are 10 networks, 28 groups, and 109 online devices sets the agent's expectations before it starts calling: it will not look for a fourth SSID, or ask "which user" when it has never seen a user id.
- **It is the natural place to carry the rule-model orientation** (5.4) — one or two lines on the three attachment channels, so the shape of the network and the shape of the rules arrive together, once, at the start.
- **It gives the prompt fragment a concrete entry point.** "Start with the summary when the user asks something general" is a crisp, cheap instruction; "call list_hosts and hope" is not.
- **It is the right home for the DAP/policy-control explanation**, because that context is per-session, not per-call. Putting it in the prompt costs tokens on every request; putting it in a once-per-session summary costs it once.

**Tool name:** `firewalla_local__get_network_overview` (backing service `get_network_overview`). "Overview" rather than "summary" so the name reads as orientation, and so it stays distinct from the `summary` block that already exists inside other payloads.

**Base content — the exact sections.** Every item below is already collected; none of it needs new gathering logic. The table describes the read-tier discovery shape; `summary_only` uses the narrower field whitelist in §5.7 and omits group/user identities and all addresses.

| Section | Fields | Already computed in |
|---|---|---|
| `appliance` | `name`, `model`, `software_version`, `uptime_seconds`, `cloud_connected`, `cpu_usage_1m`, `memory_usage_percent`, `wan_ip` | `FirewallaApplianceIdentityInput` / `FirewallaSystemStatus` |
| `networks` | `count`, and per network: `uuid`, `name`, `kind`, `ipv4_subnets` | `runtime_inventory.networks[]` |
| `devices` | `total`, `online`, `offline`, `host_count`, `with_reservation` | `summary.devices_total` / `devices_online` / `devices_offline` / `host_count` |
| `groups` | `count`, and per group: `id`, `name`, `user_names` | `runtime_inventory.groups[]` |
| `users` | `count`, and per user: `id`, `name`, `affiliated_group_name` | `runtime_inventory.users[]` |
| `rules` | **counts only** — `total`, `visible`, `visible_enabled`, `dap`, `family`, `system_managed` | `summary.*_rule_count` |
| `alarms` | `active`, `archived`, `pending` | alarm counts |
| `wan` | `count`, and per WAN: `uuid`, `name`, `status` | `networks[]` filtered to `kind == "wan"` |
| `wireless` | `ssid_count`, `access_point_count` | `get_wireless_status` shape |
| `identifiers` | the reusable ids, grouped for lookup | see Layer 2 below |

**Include network IP ranges — but only the subnet.** `get_network_config` already returns `addressing.ipv4_subnets` (live: `192.168.254.1/27`) and `dhcp.range`. Put **`ipv4_subnets` on each network entry** so "what's my network layout?" is answerable directly. Do **not** include the DHCP range, DNS servers or ports per network — that is `get_network_config`'s job, and duplicating it would double the payload.

**Counts-vs-collections is the only size rule.** `devices` and `rules` are **counts only**. `networks`, `groups`, `users` and `wan` are the deliberate exception and carry identities, because those are precisely what is undiscoverable today (D2/D3). **No byte cap is imposed** — the guard is that no section ever carries a record collection, so the payload cannot grow with the network's size.

**Explicitly excluded** — each has a dedicated tool, and adding any of them is how this becomes `get_runtime_inventory` (1.15 MB / 288k tokens) again: host records, rule records, alarm records, per-network usage, speed tests, internet quality samples.

#### Leverage contract — how the overview gets used by the other tools

Four layers, deliberately redundant, because no single one is reliable on its own.

**Layer 1 — the name and description position it as the entry point.** The description's first sentence is the imperative: *"Start here. Call this once at the beginning of a session for any general question about the network."* Then state what it returns and, just as importantly, what it does **not**.

**Layer 2 — the response carries a labelled `identifiers` block.** Do not make the agent dig ids out of nested lists; label them for reuse:

```json
"identifiers": {
  "networks": [{"uuid": "…", "name": "VLAN60 IOT", "kind": "vlan"}],
  "groups":   [{"id": "31", "name": "KADEN's Devices", "user_names": ["KADENS_DEVICES"]}],
  "users":    [{"id": "78", "name": "CARENS_PHONE", "affiliated_group_name": "CARENS_PHONE"}],
  "wan":      [{"uuid": "…", "name": "WAN-ONE"}]
}
```

**Layer 3 — every dependent tool names its discovery source.** This is the layer that actually enforces the contract: at the moment the agent needs a value, it is told where to get it. The rule is **point at the nearest discovery surface**, not always at the overview:

| Tool | Selector it needs | Its description must name |
|---|---|---|
| `get_network_config` | `network_name` / `network_uuid` | **`get_network_overview`** |
| `get_network_usage` | `network_name` / `network_uuid` | **`get_network_overview`** |
| `get_user_usage` | `scope_target` (group or user id) | **`get_network_overview`** |
| `get_alarms`, alarm block/mute tools | `alarm_id` | `get_alarms` |
| `pause_rule` / `resume_rule` | `rule_target` | `list_rules` |
| host writes (`set_host_*`, `wake_host`) | `host_mac` / `host_name` | `list_hosts` |
| `set_ssid_paused` | `ssid_profile_id` | `get_wireless_status` |

Today `_NETWORK_UUID_DESCRIPTION` says to get the network from *"list_hosts / get_network_config"* — and **neither can supply it** (D2). That text is the bug; Layer 3 is the fix, and the same pattern should be applied to `get_user_usage`, whose `scope_target` is currently also undiscoverable (D3).

**Layer 4 — the prompt fragment states the opening move and the once-per-session rule.** One sentence: *"For a general question about the network, call `get_network_overview` first — it returns the network, group, and user identifiers the other tools need. Call it once per session unless the network has changed."* Plus a division-of-labour line so the agent does not try to answer detail from it.

**Anti-drift guard (required, not optional).** Both the overview description **and** the `list_hosts` / `list_rules` descriptions must state the split: overview returns **counts and identifiers**; the list tools return **records**. Without this, the agent will answer "which device has IP x.x.x.x" from a count, or re-call the overview for every question.

**Where the rule-model orientation lives — deliberately not in this tool.** The 5.4 paragraph belongs in the **prompt fragment**, which is already paid for on every request, so adding it there is free. Putting it in the overview body would cost tokens once per session to duplicate something the prompt already says. Division of labour: **the overview describes the shape of the network; the prompt describes the shape of the rules.**

**Design constraints (so it does not become the thing it replaces):**

- **No arbitrary size budget (settled 2026-10-01).** An earlier ≤ 8 KB / 10 KB cap was dropped: it was an invented constraint, not a platform limit. The real guard is the design rule below — the overview returns **counts and identities, never record collections** — which is what actually keeps it from becoming a second `get_runtime_inventory`. Prefer simplicity over a magic number.
- **Not a substitute for `list_hosts`/`list_rules`.** Those stay the detailed reads; the overview is orientation only.
- **Read tier, non-admin, `read_only=True`, `idempotent=True`, `open_world=False`.** Aggregates and identity, no writes.
- **Reuse the existing counts.** Do not recompute them in a new code path — a second counting implementation will drift from the first.
- **Privacy note for 5.1:** `summary_only` discloses network names and aggregate counts, but no group/user names, ids, addresses, or hardware identifiers. Read tiers add names and ids for discovery; those are disclosed as a separate capability.

**Sequencing:** build it **in 5.3, after 5.2**, and **before** deciding on separate network/group/user list tools — Layer 2 plus Layer 3 very likely makes those unnecessary.

### 5.4 — Rule-model clarity

**The three attachment channels (measured live).** Firewalla attaches a rule in one of three ways. All three are in the runtime snapshot; **only one reaches the agent.**

| Attachment | Live count | Representation | Exposed today |
|---|---:|---|---|
| Device (MAC) | 107 | `scope: ["B4:96:91:10:FD:2C"]` | yes |
| **Group / user tag** | **83** | `tag_refs: ["tag:31"]` → `applies_to: ["KADENS_DEVICES"]` | **no** |
| Network interface | 6 | `tag_refs: ["intf:95169e6a-…"]` → `applies_to: ["VLAN10 CORE"]` | **no** |
| Unattached | 109 | — | n/a |

- [x] **Add structured `applies_to` (+ `tag_refs`) to the rule summary.** `_serialize_rule_summary` emits `rule_id, name, action, enabled, is_paused, target, target_name, target_type, scope, alarm_id` and **drops `applies_to` entirely** (`any("applies_to" in x)` was `False` across all 305 live rules). **89 of 305 rules carry `applies_to`.** The information leaks only as prose inside `name` (`"allow category TL-… for NET_INFRASTRUCTURE"`), which the agent cannot filter or reason on. Serialisation-only; this is the highest-value single fix in Phase 5.
- [x] **Resolve tag GUIDs to names.** Live resolution is inconsistent — the same family of group rules surfaces both readable (`KADEN's Devices`, `PAYTON's Devices`) and raw-GUID (`8E773D92-…` = `PAYTONS_PHONE`, `B60C3BFD-…` = `KADENS_PHONE`, `E50ED187-…` = `SHARED_GAMING`, `BDE8BA46-…` = `SHARED`) names. Whichever field is exposed must resolve through the group→user mapping, or the agent will still be guessing.
- [x] **Exclude `purpose == "dap"` rules by default.** **182 of 305 (59%)** are Device Active Protect internals (`allow category DAP - <mac> [dap_xxxx]`, `block mac app-game1 [<mac>]`). This matches `RULE_MODEL.md`, which already lists `dap` under *Default excluded purposes* for the switch surface — the concept exists but was never applied to `list_rules`. **Important: `management.classification` does not catch these** — 299 of 305 are `user_managed` and only 6 are `system_managed` (the alarm-intel IP blocks). The discriminator is `purpose`, not classification. Provide an explicit opt-in to include them.
- [x] **Add a prompt-fragment paragraph on the rule model** — the three attachment channels, that a device inherits its group's and user's rules, that device-level rules exist only when created against a device tag, and that DAP rules are product-owned and not user-facing. Implemented in the prompt and the `list_rules` description, condensed to the model plus the precedence rule. **Refined 2026-10-01 (owner direction): attachment *replaces*, it does not add** — once a device belongs to a group or user, its rules come from that group or user and device-level rules no longer apply to it, so "what covers this device?" is answered from membership. Stated identically in the prompt, the `list_rules` description, and the reference so the agent cannot get two mental models. **Provenance: owner-provided product behaviour, not reproduced from a live capture** — the repo holds no rule payloads, so this is recorded as owner knowledge rather than verified inference, and the same is flagged inline in the reference.
- [x] **G2 — RESOLVED, and it is much simpler than this plan first suggested (2026-10-01).** Two successive drafts got this wrong in opposite directions, so state it plainly:

  > **Policy controls are settings, not rules. They are one shared configuration vocabulary applied at both network and group scope, and they do not map to rules at all.**

  Evidence — the **same keys** appear at both scopes, which is what makes it a settings layer:

  | Scope | Where | Keys |
  |---|---|---|
  | Network | `get_network_config` → `sections.configuration.policy` | 13: `adblock`, `safeSearch`, `family`, `doh`, `unbound`, `monitor`, `ntp_redirect`, `weak_password_scan`, `device_service_scan`, `acl`, `qos`, `newDeviceTag`, `vpnClient` |
  | Group | `runtime_inventory` → `group_policy_controls` | the same 9 of those keys |

  A **rule** is a separate object that references a group through `tag_refs: ["tag:<group_id>"]`. A **policy control** is an attribute *of* that group (or network segment). They are different kinds of thing, which is why there is nothing to map.

  **They do not correlate, in either direction.** Live:

  | Group | Non-default policy | Rules via `tag:<id>` |
  |---|---|---:|
  | `69` SHARED | *(none)* | 5 |
  | `31` KADEN's Devices | `family`, `monitor` | 14 |
  | `29` PAYTON's Devices | `safeSearch`, `family`, `monitor` | 13 |

  Groups with no policy settings carry rules; groups with policy settings carry unrelated rules. The counts are independent.

  **The earlier `family` claim is refuted.** This plan previously asserted that `family` — a policy key *and* a rule purpose — was "the one genuine materialization link". It is not. **Two live groups have `family: true` and there are zero `purpose: family` rules** (purpose distribution across all 305: `dap` 182, `None` 118, `port_forwarding` 4, `firewall` 1). The overlap is a coincidence of vocabulary, not a relationship, and `family_rule_count: 0` is simply zero.

  **Design consequence — the easy part, now that it is framed correctly:** expose policy controls as **group/network settings** and rules as **rules**. Never merge, never synthesise a mapping, never ask which control produced which rule. A group view is two labelled sections: *settings* (policy keys) and *rules* (its `tag:<id>` set). The `tag:<group_id>` join is still useful for **grouping a group's rules**, which is all it was ever for.
- [x] **Use the inventory's own classification for the `list_rules` default (implemented 2026-10-01).** `runtime_inventory.py` computes the right set: `visible_rules` = user-managed **and** not `dap` **and** not `family`. Live: **117 rules, 52 enabled**. The default now reuses a shared `is_user_visible_rule` predicate used by *both* the inventory and `get_rules`, so the two cannot drift. `dap`/`family` remain behind `include_purpose`; subsystem-owned rules (the alarm-intel auto-blocks) are behind the new `include_system_managed` flag.

### 5.5 — Runtime sync

**Implemented and verified live 2026-10-01.**

- [x] **Non-admin `sync_runtime` service** — `SupportsResponse.ONLY`, returns `synced`, `synced_at` (ISO), `synced_at_timestamp`, and `config_entry_id`. `services.yaml` entry added.
- [x] **`sync_runtime` read-tier tool**, `read_only=True`, `destructive=False`, **`idempotent=True`**, `open_world=False`. Registered in `_READ_TOOL_CLASSES`; description states the coalescing window so the agent can sequence sync-once → `refresh=false`.
- [x] **Verified live:** first call **13.63 s**, immediate repeat **0.00 s** with an **identical `synced_at`** — the debounce performs no second poll, which is what makes the idempotency claim true in practice rather than only in theory. A following `list_hosts` with `refresh=false` returned in **0.00 s**, so the sync-once pattern works.

**Operational finding worth remembering — a config-entry reload does not re-import a module.** Adding `sync_runtime` to the module-level registration table had no effect after `homeassistant.reload_config_entry`: the live instance still showed 30 services and rejected the call. A **full process restart** was required (31 services). Module-level constants and registration tuples are evaluated at import, and `reload` re-runs setup, not import. Any future change to `SERVICE_REGISTRATIONS`, `_READ_TOOL_CLASSES`, or a module-level table needs a process restart to verify — and the same applies to anyone testing this repo against a running Home Assistant.

- [x] **Add a non-admin `sync_runtime` service** mirroring the existing `sync_runtime` button (`button.py:21`, backed by `coordinator.async_request_refresh()`). No service exists today — only the entity.
- [x] **Add the `sync_runtime` read-tier tool**, `read_only=True`, `destructive=False`, **`idempotent=True`**, `open_world=False`. **Settled 2026-10-01 (owner call): the operation is idempotent.** Repeating it any number of times leaves the same end state — a synced snapshot. A longer wall-clock time for the first call is a transaction cost, not a state change, and the annotation describes end state, not cost. Do not encode the debounce as `idempotent=False`.
- [x] **Document the coalescing in the description**, because it is genuine and useful: HA's `async_request_refresh` runs through a debouncer with `REQUEST_REFRESH_DEFAULT_COOLDOWN = 10`. Measured live on `list_hosts`: the first call took **11.11 s**, subsequent calls within the window took **0.00 s** — with *or* without `refresh=true`. So `refresh=true` on several tools in one turn costs **one** poll, not N. The tool's value is therefore an explicit fresh-now verb plus sync-once→`refresh=false` sequencing, not throughput. **This is unrelated to the WAN-events window** — a correction to an earlier draft that conflated the two; they share no code.
- [x] Place it in the **read tier** so it is available in the default mode; it is harmless and helpful, and gating it would deny it to the users who most need to avoid re-polling.
- [x] Mention it in the prompt fragment's read→write/discovery guidance.

### 5.6 — Action confirmation and response specificity

**Problem (owner observation, live use):** the assistant does not stop and ask before making changes, and reports actions imprecisely ("yeah, I did it").

**Platform constraint.** `llm.Tool` (`homeassistant/helpers/llm.py:182`) exposes only `name`, `title`, `description`, `parameters`, `annotations`, `integration`, and `async_call` — there is **no confirmation or continuation hook**. A tool cannot pause mid-turn to ask. So two levers exist:

1. **`annotations.destructive`** — the standards-aligned signal. Clients (Claude Desktop and similar) use it to require their own confirmation. Our destructive tier already sets it; **control tools do not**, so clients will not prompt for them. This is intentional and should stay: `pause_rule` and `set_host_name` are routine.
2. **Prompt instruction** — the only lever for non-destructive controls. No client-side prompt will fire for them.

- [x] **Add a prompt-fragment instruction requiring specificity after any control call:** name the resolved target, state exactly what changed (or that nothing changed because it was already in state), and state how to undo. The action-result envelope already carries `status` / `changed` / `target` / `undo`, so this is an instruction to *surface* existing data — no new plumbing. This is the higher-value half and should land regardless.
- [x] **Add a confirmation instruction for high-blast-radius controls.** Prefer a *scoped* rule over a blanket one: require explicit user confirmation for actions that affect more than one device or are network-wide (SSID pause, alarm mute without a scope, rule pause on a group or network rule), while allowing routine single-device writes to proceed. State the intended change and scope, then wait.
- [x] **Do not attempt a tool-side confirmation gate.** `confirm: true` on the destructive tier is a speed bump against accidental model calls, **not** user confirmation — the model sets it itself, so it proves nothing. Say so in the reference so the distinction is not lost; do not extend the pattern to control tools as a stand-in for consent.
- [x] Note in `MCP_TOOL_REFERENCE.md` that confirmation behaviour is ultimately the **client's** to enforce, and that our contribution is accurate annotations plus precise action reporting.

### 5.7 — Anonymous (summary-only) tool tier
**Owner proposal (2026-10-01):** add a read tier that exposes **no MAC or IP addresses** — possibly just the overview — so a user can get useful answers without sending device identity to an LLM provider.

**Verdict: yes, build it — and it is a better privacy answer than the disclosure wording in 5.1.** 5.1 tells the user what is sent; this gives them somewhere to go instead. It also produces the one privacy claim that is strong enough to lead with.

**The rule, stated once so it can be enforced unambiguously:**

> **No identifiers and no addresses. Counts, names of things, and performance metrics only.**

Deliberately excluded, with the reason each matters:

| Excluded | Why |
|---|---|
| **MAC / `host_id`** | Persistent hardware identifier; survives IP changes |
| **IP addresses (LAN)** | Device identity + network topology |
| **IP addresses (public)** | **The single most sensitive field** — `get_speed_tests.public_ip` and `get_wan_events.wan_interface_address` identify the *household* on the internet, not just a device on the LAN |
| **Hostnames / `dhcp_name` / `dns_*`** | Frequently contain people's names |
| **Person and group names** | `user_names` and group names like `KADEN's Devices` are personal data even without an address |
| **SSID names** | Commonly contain a household or surname |
| **Serial number** | Device-unique identifier |
| **Internal subnets** | Topology; enables reconnaissance even without host records |

**Evidence — what each live tool actually exposes.** Measured against the 2026-10-01 payloads:

| Tool | Identity-bearing fields found live | Anonymous-safe? |
|---|---|---|
| `list_hosts` | `mac`, `ip_address`, `host_name`, `dns_fqdn`, `dns_hostname`, `dhcp_name`, `group_name`, `reserved_ipv4` | **No** |
| `get_network_config` | **embeds the full per-network host list** — `host_id` (=MAC), `host_name`, `ip_address`, `dhcp_name`, `reserved_ipv4` (10 hosts live) | **No** |
| `get_network_usage` | per-device top talkers with `host_id` (=MAC), `host_name`, `ip_address` | **No** |
| `get_user_usage` | `device_name`, person-level usage | **No** |
| `get_alarms` | `device_name`, `remote_ip`, `remote_latitude`, `remote_longitude` | **No** |
| `list_rules` | `scope` MACs, MAC targets, `target_name` | **No** |
| `get_wireless_status` | `ssid_profiles`, `access_points` (empty on this box, but structurally present) | **No** |
| `get_speed_tests` | `public_ip`, `isp`, `server_country` + metrics | **With redaction** |
| `get_wan_events` | `wan_interface_address` (public IP), `name_server` | **With redaction** |
| `get_wan_usage` | WAN `name` only | **Yes** |
| `get_internet_quality` | `wan_name` only; latency/loss are metrics | **Yes** |
| `get_network_overview` | counts only, once identifiers are gated | **Yes (counts form)** |

**Two findings that change the shape of this feature:**

1. **`get_network_config` is a second hosts listing.** It embeds `sections.hosts.items` with MAC, hostname, IP and reservation. It was previously treated as a low-sensitivity topology read; it is not. Any future sensitivity labelling must account for this.
2. **`get_speed_tests` and `get_wan_events` leak the public IP**, which is a different and worse category than LAN identity. Worth calling out on its own in 5.1's disclosure.

**Correction (owner, 2026-10-01): this is not a tier over existing tools.** An earlier draft proposed a "safe subset" of the read tools. That was wrong, and the reason matters: **reusing an existing tool means inheriting its payload**, and every read tool carries something sensitive as a side effect (`get_speed_tests` → `public_ip`, `get_internet_quality` → manageable, `list_hosts` → MAC/IP). Auditing tools for leaks is an ongoing obligation that will break the moment a payload gains a field.

**Instead: one purpose-built, curated tool.** The safe tier is a **single tool** — the Firewalla system summary report — whose every field is chosen deliberately. Safe by construction, not by filtering or by audit: if a field is not in the curated list, it cannot appear, and a future payload change cannot leak through it because it does not pass payloads through at all.

**This tool is the same artefact as `get_network_overview` in §5.3.** One tool, two roles:

| Mode | Role |
|---|---|
| `summary_only` | The **entire** tool surface — answers the common questions, nothing else registered |
| `read_only` and above | The **discovery layer** for the other tools (the §5.3 leverage contract) |

That convergence is a simplification, not a coincidence: the thing that makes a good safe default (a small, curated, non-identifying summary) is the same thing that makes a good first call (orientation plus the identifiers other tools need). **Build it once.** In `summary_only` the identifiers section is *absent because those tools are absent too* — so there is nothing to reference and nothing to withhold.

**Exact contents — the authoritative spec (owner-confirmed 2026-10-01).** Deliberately close to the existing system-status entity attributes, which are already a vetted, non-identifying set. **This list is the contract**: a field not here is not in the payload.

| Section | Fields | Source / notes |
|---|---|---|
| `config_entry_id` | the entry id | Standard envelope field |
| `llm_access` | `mode` (the active `llm_tool_mode`), `tool_count`, `note` | Self-awareness. The `note` carries the *"raise the AI access level in the integration options for more detail"* pointer |
| `appliance` | `model`, `software_version`, `firmware_release_type`, `box_image_codename`, `box_image_version`, `cloud_connected`, `booting_complete`, `uptime_seconds`, `timezone_name`, `cpu_usage_1m`, `memory_usage_percent`, `memory_free_mb`, `disk_usage_percent_by_mount` | Reuses `ATTR_SYSTEM_*`. **Excludes** `host` (the box's **LAN IP**), `serial_number`, `ddns` (a public hostname), `wan_ip` / `wan_ips` (public IP), `bluetooth_mac` (a MAC) — all present on the entity, none permitted here |
| `devices` | `total`, `online`, `offline` | Counts only. **These already include the VPN peers** — see the VPN note below, and do not double-count |
| `vpn_devices` | `total`, `online`, `offline` | **Mirrors the `devices` naming exactly** (owner direction). Live verified 2026-10-01: **5 / 1 / 4** — see the VPN note below |
| `networks` | `count`, `items[]` → `uuid`, `name`, `kind`, `device_count`, `online`, `offline` | **Names included** (owner-approved: infrastructure labels, verified non-personal across all 10 live networks). Per-network counts owner-approved; `online`/`offline` are computed by filtering hosts on `network_uuid` (data already in memory) |
| `groups` | `count` | **Count only — no items, no ids, no names.** A bare id list has no function here; see the mapping note below |
| `users` | `count` | **Count only — no items, no ids, no names.** Same reason |
| `rules` | `total`, `visible`, `enabled`, `dap`, `family`, `system_managed` | Counts only — no rule records, no `scope`, no targets |
| `alarms` | `active`, `archived` | Counts only. **`pending` removed** — see the alarm note below. **No** `remote_ip`, `remote_host`, lat/long, or `device_name` |
| `wan` | `count`, `items[]` → `uuid`, `name`, `kind`, `status`, `latest_speed_test`, `internet_quality` | Speed test and quality are **per-WAN, nested** — see the nesting decision below. **No** `wan_interface_address` (public IP), no `name_server` |

**Speed test and internet quality are nested per WAN (owner-raised 2026-10-01).** Both reads already carry `wan_uuid` + `wan_name` on every record, so they are inherently per-WAN and a flat top-level section would force a reader to match records to WANs by hand — exactly the mismatch risk the summary exists to remove. **Decision: nest them on each `wan.items[]` entry**, not as separate top-level sections:

```json
"wan": {
  "count": 1,
  "items": [{
    "uuid": "8d5a7f20-…", "name": "WAN-ONE", "kind": "wan", "status": "…",
    "latest_speed_test": {
      "tested_at": "2026-10-01T12:03:38+00:00",
      "download_mbps": 504.95, "upload_mbps": …, "latency_ms": 30.24,
      "jitter_ms": …, "packet_loss_percent": …,
      "download_megabytes": …, "upload_megabytes": …
    },
    "internet_quality": {
      "sampled_at": "2026-10-01T15:00:00+00:00",
      "ping_latency_ms": 22.2, "ping_latency_max_ms": …,
      "ping_latency_median_ms": …, "ping_latency_min_ms": …,
      "ping_packet_loss_percent": 0.0
    }
  }]
}
```

Why nesting beats two flat lists plus a WAN list: WAN identity is stated **once**, each metric is unambiguously attached to its WAN, the shape does not change when a second WAN appears, and it **removes two top-level sections**. The cost is one extra level of nesting, well within what an agent handles. **Excluded** from both: `public_ip`, `isp`, `server_country`, `server_host`, `server_location`, `server_sponsor`; and `ping_target` (a public IP literal).

**`pending` is dropped from the alarm counts (owner call, corroborated).** `pendingAlarmCount` **does** exist in the raw payload and is already normalized — but it is **`0`** in every observation, it appears in neither the app's alarm surface nor the `ALARM_*` taxonomy (`REVERSE_ENGINEERING_WORKFLOW.md` Finding 30), and there is no evidence it is ever non-zero. A curated summary should not present a category we cannot substantiate. **Removed from the summary**; the existing entity attribute (`ATTR_ALARM_PENDING_COUNT`) is left untouched, since changing it there is a separate and unnecessary edit.

**VPN note — corrected by live verification with a real connected client (2026-10-01).** An earlier draft proposed `vpn_connected` from per-host `policy.vpnClient.state`. **That was wrong and is withdrawn.** With `chads-phone` deliberately connected for the test, the facts are:

| Check | Result |
|---|---|
| `chads-phone` (connected right now) `policy.vpnClient` | **`{}`** — empty dict, no `state` at all |
| Hosts with `vpnClient.state is True` | **0** |
| Hosts with `vpnClient.state is False` | 51 — unrelated to peers (VPN-policy flag on ordinary LAN devices) |

So `policy.vpnClient.state` is **not** the connected indicator and must not be built on. It is currently normalized into `FirewallaHostVpnClient` but exposed nowhere; it stays that way, and is documented as a red herring so nobody revives it.

**What the VPN devices actually are:** the normalized **pseudo hosts**, built from the top-level `wgPeers` (4) + `awgPeers` (1) inventories. They identify by `mac.startswith(("wg_peer:", "awg_peer:"))` — note they are **already present in the normalized `hosts` tuple and already in `list_hosts` output** with `kind: "pseudo_host"`. They are *not* derived from the VPN *network* objects (`vpnProfiles` is empty, and the many `<proto>vpnClientProfiles` lists are all empty here), so the source is the peer inventories specifically.

**Verified counts — exactly matching the owner's expectation:**

| Host | `last_active` age at check |
|---|---|
| `chads-phone-wgvpn` | **70 s** ← the client just connected |
| `chads-laptop-wgvpn` | 147,544 s |
| `chads-phone-awgvpn` | 1,829,168 s |
| `kadens-phone-wgvpn` | 4,925,918 s |
| `kadens-chromebook-wgvpn` | never |

→ **`vpn_devices` = 5 total / 1 online / 4 offline.** Stable across every window tested (300 s through 86,400 s), because exactly one peer is recent and the rest are hours-to-months stale.

**Implementation is a subset view, not new plumbing.** `last_active` is already populated for peers from the peer inventory's `lastActiveTimestamp`, so the existing `count_online_hosts(hosts, online_window_seconds=…)` works on them unchanged — no peer-specific window, no new activity logic. Two consequences worth stating:

- **`devices.total` (218) already includes the 5 VPN peers**; the 213 non-VPN hosts are the remainder. So `vpn_devices` is a **breakdown of `devices`**, not an additional population — the summary must present it that way or a reader will add them together.
- Methods mirror the existing three exactly (`count_total_devices` / `count_online_devices` / `count_offline_devices`) → `count_vpn_total_devices` / `count_vpn_online_devices` / `count_vpn_offline_devices`, all filtering the same `get_hosts()` result.

**`list_hosts` — no new `vpn` filter needed.** The `kind` filter already specified in §5.2 (`mac_host` / `pseudo_host`) covers "show me only my VPN devices", and the peers already appear in the output. Add a dedicated `vpn` flag only if `kind` proves awkward in practice. What *is* needed is exposing `vpn_client` on each host row — currently the model carries it but `list_hosts` drops it (§5.2).

**Everything the owner asked for is covered:** model, uptime, networks with names, last speed test, internet quality with date, and counts for groups/users/rules/alarms. The `llm_access` section answers *"what can you see?"* directly.

**Group and user counts only — the deliberate asymmetry.** Networks carry names because a network name is a *label* (`VLAN60 IOT`). Groups and users carry no names because those names are *people* (`KADEN's Devices`, `CARENS_PHONE`). Ids are also omitted rather than sent bare: in `summary_only` there are no other tools to consume an id, so a list of bare numbers serves nothing while still being stable per-household tokens. **Names and ids travel together, in `read_only` and above** — which is also where they become functional, since `get_user_usage` and `pause_rule` accept them as selectors.

**Read mode carries names AND ids — confirmed, required (2026-10-01).** The question was whether read mode exposes names only or names plus ids. **Both, because ids are the deterministic path.** Verified in `_resolve_usage_history_target`: for all three scope kinds (`device`, `user`, `group`) the id is **exact-matched first**, and a name is a case-folded **fallback that raises an ambiguity error** when it matches more than one. So names alone would produce avoidable ambiguity failures. Read mode must therefore expose:

- **Groups** — `id` + `name` (and `user_ids` / `user_names` for the group→member mapping)
- **Users** — `id` + `name` + `affiliated_group_id`
- **Rules** — `applies_to` (names) **and** `tag_refs` (the `tag:<group_id>` ids), which is exactly the §5.4 fix

Names serve correlation ("my kid's tablet"); ids serve lookup. Sending only one of the two breaks a real workflow either way.

**The rule, restated so it stays enforceable:**

> **No addresses and no hardware identifiers. Names, ids, counts, and performance metrics only.**

Excluded absolutely — a payload containing any of these is a defect, not a trade-off:

| Excluded | Why |
|---|---|
| **MAC / `host_id`** | Persistent hardware identifier; survives IP changes |
| **IP addresses (LAN)** | Device identity + topology |
| **IP addresses (public)** | **The most sensitive field in the surface** — `get_speed_tests.public_ip` and `get_wan_events.wan_interface_address` identify the *household* on the internet, not a device on the LAN |
| **Hostnames / `dhcp_name` / `dns_*`** | Frequently contain people's names |
| **SSID names** | Commonly contain a household or surname |
| **Serial number** | Device-unique identifier |
| **Internal subnets** | Topology; enables reconnaissance without host records |
| **`remote_ip` / lat / long** | Third-party endpoints and physical location |

**Evidence — what each live tool actually exposes.** Measured against the 2026-10-01 payloads. This is why the tier is a curated tool rather than a subset: every one of these carries something from the exclusion list.

| Tool | Identity-bearing fields found live | Reusable as-is? |
|---|---|---|
| `list_hosts` | `mac`, `ip_address`, `host_name`, `dns_fqdn`, `dns_hostname`, `dhcp_name`, `group_name`, `reserved_ipv4` | **No** |
| `get_network_config` | **embeds the full per-network host list** — `host_id` (=MAC), `host_name`, `ip_address`, `dhcp_name`, `reserved_ipv4` (10 hosts live) | **No** |
| `get_network_usage` | per-device top talkers with `host_id` (=MAC), `host_name`, `ip_address` | **No** |
| `get_user_usage` | `device_name`, person-level usage | **No** |
| `get_alarms` | `device_name`, `remote_ip`, `remote_latitude`, `remote_longitude` | **No** |
| `list_rules` | `scope` MACs, MAC targets, `target_name` | **No** |
| `get_wireless_status` | `ssid_profiles`, `access_points` (empty on this box, structurally present) | **No** |
| `get_speed_tests` | `public_ip`, `isp`, `server_country` alongside the metrics | **No — but the curated report can carry its metrics** |
| `get_wan_events` | `wan_interface_address` (public IP), `name_server` | **No** |
| `get_wan_usage` | WAN `name` only | Yes |
| `get_internet_quality` | `wan_name` only; latency/loss are metrics | Yes — but the curated report carries it, so it needs no separate tool |

**Two findings that this design absorbs:**

1. **`get_network_config` is a second hosts listing.** It was previously treated as a low-sensitivity topology read; it embeds 10 host records with MAC and IP. Sensitivity labelling must account for this, and the curated report is the answer — it takes only network identity, never the host section.
2. **`get_speed_tests` and `get_wan_events` leak the public IP.** The curated report takes the speed-test *metrics* and the WAN *name* and drops everything else, so the leak is structurally impossible rather than redacted.

**Design: capability removal, never runtime filtering.** In `summary_only` the other tools are **not registered at all** — not hidden, not filtered. There is no redaction function to get wrong and no field that merely happens to be omitted. This is the difference between *"we do not return it"* and *"it is not reachable"*, and only the latter is worth publishing as a privacy claim.

**Naming is settled: `summary_only`.** It is descriptive, fits the existing `read_only` / `read_and_control` style, and avoids over-claiming anonymity. Describe it as the curated report with network names, aggregate counts, and performance metrics, without device addresses, group/user names, or hardware identifiers.

**Placement in the mode ladder** (becomes five states):

| Mode | Exposure |
|---|---|
| `off` | nothing |
| `summary_only` | the curated system summary report, and nothing else |
| `read_only` | full read set, with the summary as the discovery layer |
| `read_and_control` | + control tools |
| `full` | + destructive tools |

**Default is settled: `summary_only`, flipped atomically with this tool.** It answers common questions with no addresses or hardware identifiers and makes the feature discoverable. `off` remains available for users who want the surface inert; higher-detail tiers remain explicit choices.

**Prompt and description implications — required, not optional:**

- The report's description states its own limit explicitly (*"curated summary only; device-level detail requires a higher access level"*), so the agent does not infer or hallucinate a device list.
- **The "want more detail?" advice (owner direction).** The report should carry a short, static pointer: *"This report is intentionally limited. For device names and addresses, rules, alarms, or usage detail, the user must raise Firewalla's AI access level in the integration options."* This turns the tier from a dead end into a clear upgrade path, and it is the honest answer when the agent cannot fulfil a request.
- The `llm_access` section makes that self-describing rather than relying on the agent to infer it from missing tools.
- Tool count in `summary_only` drops from **33 to 1**, which is a substantial side benefit — a smaller surface is cheaper and less error-prone.

**Open risk:** the tier's value depends on users understanding the trade. The option description carries that weight and needs care in 5.1's wording pass. The group/user-name decision is settled: names and ids are absent in `summary_only` and available in `read_only` and above.

### 5.8 — Config-change re-registration and `get_network_config` host section

**Both implemented 2026-10-01. 441 tests pass; ruff, format and mypy clean.**

**D9 — RECOMMENDATION: names in read mode only; ids and counts in summary mode.** This is the answer to the owner's question (*"not having these groups and names accessible to the agent is an issue we still need to iron out"*), and it resolves the tension rather than trading it off:

> **Names exist to serve correlation — mapping the user's words to an id that another tool can accept. In `summary_only` there are no other tools, so names have no function. They are decoration there and identity leakage in exchange for nothing.**

Four reasons this is the right line, not a compromise:

1. **Function.** The names' whole job is discovery: "my kid's tablet" → the right `scope_target` for `get_user_usage`, or the right `rule_target` for `pause_rule`. In `summary_only` those tools are absent, so a name has nothing to correlate with. **Ids alone satisfy discovery at every higher mode**, because the other tools accept ids too.
2. **The owner's original spec already said ids.** The request was *"list of groups with group ID association, list of networks with ids, list of users with ids"* — **ids**. The names were introduced in this plan, not asked for. Removing them in summary mode returns to the spec.
3. **The escalation is coherent.** Names are strictly *less* sensitive than the MAC and IP that `read_only` already exposes. So "names arrive with read mode" is not an arbitrary extra restriction — it is a lower rung on a ladder the user climbs anyway. Nothing is lost by deferring them.
4. **The privacy claim becomes absolute.** *No names, no addresses, no hardware identifiers* is checkable in one sentence and assertable in one test. "No addresses but names, sometimes" is neither.

**Second recommendation — if network identity is wanted in summary mode, allow network names only.** Network names are **infrastructure labels**, verified against all 10 live networks (`VLAN60 IOT`, `LAN-MGMT`, `WAN-ONE`, `IOT`/`GUEST` segmentation, VPN labels) — none contain personal data. Groups and users are the opposite: `KADEN's Devices`, `CARENS_PHONE`, `PAYTONS_DEVICES` are people. So the natural boundary is *network names are topology, group and user names are personal*. This lets summary mode answer "how many devices are on my IoT network" (a genuinely common question) while keeping person names out. **Recommended only if that question matters; the primary recommendation above is simpler.**

**Rejected — pseudonymised names ("Group A", "Group B").** Worst of both: it destroys the correlation that names exist to provide, while still emitting a stable per-group token that the provider can track across sessions. It looks safe without being useful.

| Mode | Network names | Group / user names | Ids | Addresses |
|---|---|---|---|---|
| `summary_only` | ✅ *(per second recommendation; optional)* | ❌ | ✅ ids only | ❌ |
| `read_only` and above | ✅ | ✅ | ✅ | ✅ (already the case) |

**D9 — changing the LLM tool mode does not take effect without a manual reload (confirmed defect).** Owner-reported: switching from read-only to read-and-control required manually reloading the integration.

**Root cause, traced precisely.** `async_setup_entry` already registers an options update listener (`entry.add_update_listener(coordinator.async_handle_entry_reload_requested)`). That handler decides whether a change is *meaningful* by comparing a fixed set of settings before reloading:

```python
        if (
            current_selected_rule_ids == _get_selected_rule_ids(entry.options)
            and current_watched_device_macs == _get_watched_device_macs(entry.options)
            and current_device_tracker_macs == _get_device_tracker_macs(entry.options)
            and current_watched_user_ids == _get_watched_user_ids(entry.options)
            and current_enable_network_entities == enable_network_entities
            and current_enable_ssid_entities == enable_ssid_entities
        ):
            self.async_update_listeners()
            return
```

**`llm_tool_mode` is not in that list.** So a mode change persists the option (`async_update_entry_options` → `hass.config_entries.async_update_entry`, which does *not* reload), falls into the "nothing meaningful changed" branch, calls `async_update_listeners()` and returns. The API was registered during setup with the old mode and is never re-registered. Exactly the reported symptom.

**Fix: add the LLM tool mode to the meaningful-change comparison.** One more condition in the existing guard, comparing the mode that is **currently registered** against the incoming options value. The existing checks read live objects (`entry.runtime_data.rule_manager.selected_templates`, `host_manager.configured_*`), so the LLM mode needs an equivalent "what is active right now" source — the mode is captured at registration time in `_async_setup_llm_api`, so record it where the handler can read it. The smallest coherent option is to mirror the coordinator's existing `_enable_network_entities` / `_enable_ssid_entities` snapshot pattern, which exists for exactly this purpose; the alternative is to read the registered `FirewallaLocalAPI`'s mode. Prefer the snapshot field — it matches the established shape and needs no lookup.

On a mismatch the handler falls through to `await hass.config_entries.async_reload(entry.entry_id)`, which unloads (firing `entry.async_on_unload(unregister)`, so the old API is removed) and sets up again with the new mode. That is the correct end state and reuses the tested path.

**Why reload rather than in-place re-registration.** Re-registering without a reload is attractive — no entity churn, no box re-poll — but it needs new plumbing to track the active unregister callback, sequence unregister-before-register, and avoid a duplicate API id. A mode change is a deliberate, rare user action in the options flow, so a full reload is an acceptable cost, and it is what the existing handler is explicitly for (*"Reload a config entry after mutable updates such as options changes"*). Recommend the reload; note in-place re-registration as a possible later optimisation if reloads prove disruptive. **Not** a guess worth making now.

**Test:** change the mode via options, let the listener run, and assert the registered API's tool set matches the new mode without an explicit reload — plus a negative case asserting an unrelated option save still does *not* trigger a reload.

**D10 — `get_network_config` should not include hosts by default (owner direction).** The service always returns `sections.hosts` with `count` and `items`, and on the live box that is **10 full host records** (`host_id` = MAC, `host_name`, `ip_address`, `dhcp_name`, `reserved_ipv4`) inside what is otherwise a network-configuration report. It dominates the payload and it is the reason the tool cannot be considered low-sensitivity (see §5.7).

**Fix: make `hosts` an opt-in include, default off.** `GET_NETWORK_SEGMENT_REPORT_SCHEMA` currently has no `include` field at all (`network_uuid`, `network_name`, `refresh` only), so add one using the established pattern — `SERVICE_FIELD_INCLUDE` with `_normalize_report_include` already exists and is used by `get_wan_usage` and others. Allowed value: `"hosts"`. Then:

- **Default:** `sections` carries `configuration`, `addressing`, `dns`, `dhcp`, `usage` — the actual network configuration — with `hosts` absent entirely (not present-and-empty, so the agent is not tempted to read meaning into an empty list).
- **Opt-in:** `include: ["hosts"]` restores today's behaviour for callers that genuinely need the segments' members.

This is also a **payload reduction** consistent with §5.2, and it removes the cross-tool leak identified in §5.7 finding 1 without needing a separate sensitivity mechanism.

**D9 — implemented.** The coordinator now snapshots the active mode (`self._llm_tool_mode`, mirroring the existing `_enable_network_entities` / `_enable_ssid_entities` pattern) and the reload comparison includes it. `coordinator.py` had `get_llm_tool_mode` available already, so no new import was needed. Tests: `test_options_change_to_llm_mode_re_registers_without_manual_reload` (off → read_only re-registers with no manual reload) and `test_options_change_unrelated_to_llm_does_not_reload` (guards against over-correcting into a reload on every save).

**D10 — implemented.** `GET_NETWORK_SEGMENT_REPORT_SCHEMA` gained an `include` field accepting `"hosts"`, built with the existing `_normalize_report_include` helper and the `cv.ensure_list_csv` idiom used elsewhere. `_serialize_network_segment_report` takes `applied_include` and only builds host rows when included; the section (and its provenance entry) is **absent**, never empty. Section building moved to a small `_network_segment_report_sections` helper so the conditional is in one place. Live effect: the default report drops the 10 host records (MAC, hostname, IP, reservation) that previously dominated it. Tests: `test_get_network_segment_report_service_omits_hosts_by_default`, plus the existing configuration-report test updated to opt in — preserving the host-serialization coverage rather than deleting it.

### 5.9 — VPN device counts on the system-status entity

**Owner suggestion (2026-10-01), and it is the right call: the counts belong on the entity as well as in the summary.** The system-status entity already carries an exact precedent — `ATTR_SYSTEM_DEVICES_TOTAL` / `ATTR_SYSTEM_DEVICES_ONLINE` / `ATTR_SYSTEM_DEVICES_OFFLINE` (from `host_manager.count_total_devices()` / `count_online_devices()` / `count_offline_devices()`). VPN counts sit naturally in that run and are useful well beyond the AI surface: dashboardable, history-trackable, and automatable with no LLM involved.

**Naming mirrors the existing device counts (owner direction, and it is the consistent choice):**

| Attribute | Meaning | Live value |
|---|---|---|
| `ATTR_SYSTEM_VPN_DEVICES_TOTAL` | configured VPN peers | **5** |
| `ATTR_SYSTEM_VPN_DEVICES_ONLINE` | peers with recent activity | **1** |
| `ATTR_SYSTEM_VPN_DEVICES_OFFLINE` | the remainder | **4** |

- [x] Add the three attributes to the const/attribute set, beside the existing device-count attributes.
- [x] Add `count_vpn_total_devices()` / `count_vpn_online_devices()` / `count_vpn_offline_devices()` to `host_manager`, shaped exactly like the three existing count methods — filter `get_hosts()` to peers, reuse `count_online_hosts` unchanged.
- [x] Add a shared peer-prefix constant (`"wg_peer"` / `"awg_peer"`) rather than leaving the literals scattered — the prefixes are currently hardcoded in `api/client.py` while `services.py` uses a MAC-shape heuristic (`_supports_wake_on_lan`). One constant, used by both.
- [x] Add the attributes to the entity translation strings, and to `icons.json` if the surrounding attributes have entries there.
- [x] **One implementation, multiple consumers.** The entity and the summary must read the **same** accessors, so the numbers can never disagree — the same "do not maintain two counting implementations" rule already applied to the overview's counts.

**Do not add `vpn_devices` to `devices.total`.** The 5 peers are already counted in `devices_total` (218); the summary must present `vpn_devices` as a **breakdown** of `devices`, not a separate population.

### 5.10 — External architecture review (2026-10-01) — disposition

An external review proposed five refactors. Each claim was verified against the code and against `probatio.to_openapi` output before accepting. **Three accepted, one corrected, one rejected.**

| # | Proposal | Verdict | Evidence |
|---|---|---|---|
| 1 | Keep `domain__tool` double-underscore namespacing | **Accepted — no change needed** | Already compliant: every tool is `firewalla_local__<action>`; a catalog test pins the exact set |
| 2 | Remove the per-tool `_PREFERRED_PREFIX` | **Accepted** | Measured **31 tokens × 33 tools ≈ 1,023 tokens** on *every* request. The prompt already states the preference once |
| 3 | Co-locate `PROMPT` into `llm_api.py` | **Superseded — consolidated into `llm_tools_common.py` (2026-10-01)** | The original objection was to mixing docs-derived prose into *registration plumbing*. Once a shared `llm_tools_common.py` exists for `format_tool_name`, the prompt belongs there: one LLM-surface module, not three. `llm_prompt.py` is retired |
| 4 | Move `_host_target` into the base class | **Accepted — real defect** | **Confirmed**: 5 call sites use `SetHostNameTool._host_target(...)`, a peer-class cross-reference |
| 5 | Strip descriptions that restate schema defaults | **Corrected — do not apply blanket** | Only **3** tool params carry a schema `default=`; **19** descriptions mention a default. Stripping would delete the model's *only* source of truth in **16 of 19** cases |

**On #2 — the saving is real but the mitigation matters.** The prompt already carries *"Prefer these purpose-built `firewalla_local__*` tools over any generic `firewalla_local.*` service/action tool another client may expose."* The per-tool copy is a second, weaker instance of the same instruction. Removing it must be paired with a test asserting the prompt still carries the preference sentence, so the nudge cannot silently vanish.

**On #5 — verified with `probatio.to_openapi`, not assumed.** A param declared `Optional(x, default=True, description="Defaults to true")` emits both `"default": true` **and** the description, so the sentence is genuinely redundant *there*. But a param whose default is applied in the service handler — e.g. `limit` described as *"Defaults to 100"* — emits **no `default` key**, so the description is the only signal. Applying this proposal widely would have silently degraded 16 fields. **Correct action: trim only where a schema `default=` exists (3 params, ~15 tokens), and leave the rest.**

**Additional finding — the review's own `PROMPT` draft contradicts its DRY rationale.** It proposes replacing the wildcard `firewalla_local__*` with four hardcoded tool names (`list_hosts`, `list_rules`, `get_wireless_status`, `get_alarms`). That *introduces* the duplication the same document argues against, and creates exactly the "silent mismatch" risk it warns about. Our current prompt uses the wildcard, so the DRY concern is already satisfied where it matters.

**Accepted as a genuine improvement — the `format_tool_name` helper.** Hardcoded `name = "firewalla_local__<action>"` in 33 classes duplicates the domain string and risks a typo that only the catalog test would catch. A tiny `format_tool_name(action)` helper derived from `DOMAIN` removes the duplication at zero runtime cost. **Constraint:** keep it a **static class attribute** (`name = format_tool_name("list_hosts")`), not an `__init__` assignment — HA reads `tool.name` off the instance but the static form keeps tools introspectable without instantiation and matches the existing class-attribute contract.

Implementation of #2, #4 and the helper is trivial and self-contained; #5 is a 3-field trim. **#3 was revisited (2026-10-01):** the owner's call is to consolidate, so `PROMPT` and `format_tool_name` now share `llm_tools_common.py` and `llm_prompt.py` is deleted. The concern was never the prompt's location in the abstract — it was placing it in `llm_api.py`, which is registration plumbing; a dedicated common module answers that.

### Decisions already made — do not re-litigate

- **The MCP tool reference (`docs/MCP_TOOL_REFERENCE.md`) is the single authoritative spec + surface record**, authored **first** (4.0), logically grouped/ordered with one consistent per-tool template. It is **separate from the user guide** and **referenced from it** (the guide links the catalog, never duplicates it). Implementation and the prompt derive from it; contract tests assert against it. There is no separate `SURFACE_INVENTORY.md`.
- **Option B (owned `llm.API`)** was chosen over contributing tools directly, on opt-in, admin-endpoint and old-Core-neutrality grounds. *(Investigation note §6.1.)*
- **Availability model:** read tools default-on with a single control toggle.
- **API id strategy:** bare `firewalla_local` for the sole entry, slug-suffixed beyond (investigation note §6.1).
- **`set_ssid_paused` is included** as a Tier A control.
- **Version floor stays 2025.10**; only MCP registration is gated at 2026.10.
- **Tier C is no longer excluded entirely — it is a fourth, opt-in mode (decided 2026-10-01).** The exposure option is now **four-state**: `off` / `read_only` / `read_and_control` / `full`. **`full` adds the destructive set** — irreversible (no undo) or bulk operations — so a user who occasionally needs one can enable it deliberately and monitor closely, instead of having no safe path. Every destructive tool requires `confirm: true` and declares the MCP `destructive` annotation. Nothing is released yet, so no migration is required. **Destructive set (Full only):** `archive_all_alarms`, `delete_alarm`, `delete_all_alarms`, `delete_host`, `delete_rule`. `archive_alarm` (single) stays a **control** tool — it keeps the record and is normal dismiss behaviour; only the **bulk** archive-all is in the destructive tier. `get_runtime_inventory` and generic `create_rule` stay unexposed at every mode.
- **`open_world` remains `false` on every tool, including destructive ones** — they act on the user's own bounded box.
- **The destructive tools' `undo` field is `null`** — they are not reversible, and the envelope says so honestly rather than implying a reversal exists.
- **Alarm-block folds into the `create_rule` service (not a separate service/command).** Per RE Findings 31/34 and USER_GUIDE §Services: blocking is just **rule creation** (`policy:create`) with the alarm's target/scope and an `aid` back-reference; **unblocking is `delete_rule`** on that rule. The composition is ~99% identical to any rule create, so `create_rule` gains an optional `alarm_id`/`aid` reference (+ auto-archive side effect) for parity rather than a parallel block path. The client has no `alarm:block`/`alarm:unblock`, and there is **no separate alarm-block layer**.
- **LLM tools are `block_alarm_target` / `unblock_alarm_target`** (a matched pair — clear verbs, matching the Firewalla app's Block/Unblock buttons and the create/delete semantics) as thin facades over the `create_rule`/`delete_rule` services. A single `set_alarm_target_blocked(alarm_id, blocked: bool)` set-to-state tool (matching `set_alarm_muted`/`set_ssid_paused`) is the acceptable consolidation alternative. Generic `create_rule`/`delete_rule` are **not** exposed as broad MCP tools (blast radius; `delete_rule` stays Tier C).
- **Control tools return a synthesized action-result envelope**, because the `NONE` write services return nothing. `status`/`changed`/`target`/`before`/`after`/`undo`.
- **All four annotation flags and per-parameter `description=` are mandatory** — this is the agent-friendliness contract, not optional polish.
- **`get_runtime_inventory` is NOT exposed as an MCP tool.** It is admin-gated and a huge payload (privacy + context cost). Host discovery is `list_hosts` (wraps the non-admin `get_host_name_mapping`); `list_rules` wraps a new non-admin `get_rules` service. `get_runtime_inventory` remains a service for humans/automations only.
- **Read-tool decisions confirmed (2026-10-01).** `list_rules` uses a **new non-admin `get_rules` service** (it cannot reuse the admin-gated, whole-inventory `get_runtime_inventory` without admin-locking and a large payload). `get_alarms` **reuses the existing non-admin `get_alarms` service** — no new service. **`meta.truncated` is dropped** (services slice internally and expose no total, so truncation cannot be derived honestly); the service payload's own `metadata.applied` already carries applied limits. **`open_world=False` on every tool** (they act on the user's own bounded box; matches HA core's convention). Read tools live in a guard-loaded **`llm_tools_read.py`**; each injects its own `config_entry_id`.
- **Tool messages are English-only — confirmed, no translation work.** `llm.Tool.name/title/description` are plain strings (no translation mechanism); `mcp_server._format_tool` copies them verbatim; and `HomeAssistantError.__str__` renders errors "in English, regardless of the configured language." This is correct for LLM/MCP consumption. Only UI surfaces (services.yaml, entity names, config flow) are translation-backed — a separate concern.

**Phase 5 decisions (settled 2026-10-01):**

- **`sync_runtime` is idempotent.** Repeating it any number of times yields the same end state (a synced snapshot). Longer wall-clock time on the first call is transaction cost, not a state change — the annotation describes end state, so `idempotent=True`. The 10 s debounce is documented in the description, not encoded in the annotation.
- **The default tool mode becomes `summary_only` (settled 2026-10-01, supersedes an earlier `off` decision).** It answers the common questions with no addresses and no hardware identifiers, which is a defensible default for a local-first product, and it makes the feature discoverable — whereas `off` means most users never find it. `read_only` and above stay explicit opt-ins, and `off` remains available. The flip lands in the implementation order's step 4, once the tool it exposes exists.
- **Privacy is handled by disclosure, not by removal.** MAC, IP, and FQDN are what make a firewall tool useful; over-redacting them produces a useless surface. The mitigation is stating clearly what is sent and guaranteeing that credentials and keys are structurally absent.
- **The full field list is deliberately not published yet.** Examples (IP, MAC) go in the options dialog and user guide now; a complete inventory waits until the shapes settle, and then belongs in `MCP_TOOL_REFERENCE.md`.
- **`applies_to` and `tag_refs` become structured rule fields.** 89 of 305 live rules carry an attachment the agent currently cannot see; folding it into the `name` string as prose is not a substitute.
- **`dap`-purpose rules are excluded from `list_rules` by default**, with an explicit opt-in to include them. The discriminator is `purpose`, **not** `management.classification` (which reports 299/305 as `user_managed`), and the exclusion matches the purpose list already documented in `RULE_MODEL.md`. **Refined 2026-10-01:** the default set is the inventory's own `visible_rules` (user-managed, not `dap`, not `family`) — **117 rules, 52 enabled** live — reused from `runtime_inventory.py` rather than re-derived in the service.
- **`get_wan_events` must send `filters`.** The unfiltered `item=events` read is an event firehose dominated by the box's own DNS health probes — 93 of the newest 100 live records, and 162 in a week — which is not what the product shows as a WAN event. The pairing/init path already sends the correct filter set (`api/client.py:723-735`); the service path must reuse it rather than issuing a bare count-limited read.
- **`get_wan_events` returns real connectivity events only (settled 2026-10-01).** The default filter set is the app's link-state set — `{action, system_reboot}`, `{state, dualwan_state}`, `{state, wan_state}` — over a **7-day `min` window**. `dns` is **excluded by default** and reachable only as an explicit exception (the app never shows it, and it is the box health-checking its own resolver). `ping_RTT`/`ping_lossrate` are **removed from the default**, and are **not** moved to Internet Quality: quality stays a facts-and-data report. `system_reboot` must be added to `_SUPPORTED_WAN_EVENT_ACTION_FAMILIES`, which today accepts only the ping families and would silently drop it.
- **Latency/loss alerts are not alarms, and no synthetic alarms will be created.** There is no ping/latency/loss alarm type in the product taxonomy or the live data — they are a standalone threshold-crossing feed. They are **not** added to `get_wan_events` (see the next entries), and fabricating alarm rows to place them "with alarms" is explicitly rejected.
- **Group policy controls are settings, not rules, and are never mapped to them.** The same vocabulary appears at both network scope (`get_network_config` → `sections.configuration.policy`, 13 keys) and group scope (9 keys), which is what makes it a settings layer. Rules reference groups via `tag_refs: ["tag:<group_id>"]`; policy controls are attributes *of* the group. Live counts are independent (group `69` has no policy settings and 5 rules; group `31` has policy settings and 14 unrelated rules), and the previously-claimed `family` link is **refuted** — two groups have `family: true` and zero `family`-purpose rules exist. A group view is two labelled sections: *settings* and *rules*.
- **The overview tool is `get_network_overview`, and it is a discovery contract, not just a convenience (settled 2026-10-01).** It carries a labelled `identifiers` block, every dependent tool names it as the source of its selector (or names the nearest discovery surface instead), and the prompt fragment states the open-once-per-session rule. Hard constraint: **counts and identifiers, never record collections** — no byte cap. The rule-model orientation lives in the **prompt fragment, not the overview body** — the prompt is already paid for on every request.
- **The safe tier is one purpose-built curated tool, never a subset of existing tools (corrected 2026-10-01).** An earlier draft proposed reusing the read tools with fields hidden. That inherits every tool's payload and therefore every tool's leaks — `get_speed_tests.public_ip`, `list_hosts` MAC/IP, `get_alarms` lat/long — and creates a permanent audit obligation that breaks the moment a payload gains a field. Instead the tier is a **single Firewalla system summary report** whose every field is chosen deliberately, so a leak is structurally impossible rather than filtered. **The same tool is `get_network_overview`** — one artefact serving as the entire `summary_only` surface and, at higher modes, the discovery layer for the other tools.
- **Speed test and internet quality are nested per WAN inside the `wan` section (settled 2026-10-01).** Both reads carry `wan_uuid` + `wan_name` per record, so they are inherently per-WAN. Nesting states WAN identity once, removes any record-to-WAN matching risk, keeps the shape stable as WANs are added, and removes two top-level sections.
- **`pending` is not surfaced as an alarm count (settled 2026-10-01).** `pendingAlarmCount` exists in the raw payload but is `0` in every observation and appears in neither the app surface nor the `ALARM_*` taxonomy. A curated summary should not present an unsubstantiated category. The existing entity attribute is left as-is.
- **VPN counts are a breakdown of `devices`, named to mirror it (settled 2026-10-01, live-verified).** `vpn_devices_total` / `vpn_devices_online` / `vpn_devices_offline` — **5 / 1 / 4** on the live box with one client connected. The population is the **pseudo hosts** (`mac.startswith(("wg_peer:", "awg_peer:"))`), normalized from `wgPeers` + `awgPeers`, and they **already sit inside `devices.total`** so the summary must not add them again. Online reuses `count_online_hosts` unchanged — no peer-specific window.
- **`policy.vpnClient.state` is not the VPN connected indicator and must not be revived (settled 2026-10-01, live-verified).** With a client deliberately connected for the test, its `vpnClient` was `{}` and **no host anywhere** had `state: True`. The 51 hosts showing `state: False` are an unrelated LAN VPN-policy flag. An earlier draft of this plan proposed building on it; that is withdrawn.
- **WAN events and `sync_runtime` are unrelated concerns (correction, 2026-10-01).** An earlier draft conflated them. `sync_runtime` polls the box for a fresh snapshot; the 7-day window is a **WAN-events** default. They share no code and must not be linked in the plan or the docs.
- **The WAN-events window defaults to 7 days and is configurable (owner direction, 2026-10-01).** A fixed default with an override, not a hard constant.
- **Latency/loss stay out of `get_wan_events` entirely.** They already live in `get_internet_quality`, which is the facts-and-data report — restated by the owner 2026-10-01. The opt-in flag contemplated earlier is therefore unnecessary; the families are simply not in the default set.
- **The summary report carries network names, but not group or user names, in `summary_only` (settled 2026-10-01; supersedes an earlier "names may be included" entry).** Network names are infrastructure labels (`VLAN60 IOT`, verified non-personal across all 10 live networks). Group and user names are people (`KADEN's Devices`, `CARENS_PHONE`), so those entries are **count-only** — ids omitted too, since nothing in `summary_only` consumes them. Names and ids arrive together with `read_only`, which is also where they become functional. Pseudonymised names are rejected — they destroy the correlation while still emitting a trackable token.
- **Changing the LLM tool mode must re-register without a manual reload (implemented 2026-10-01).** The options update listener compared six settings and **omitted `llm_tool_mode`**, so a mode change hit the "nothing meaningful changed" branch and the API kept its old registration. Fixed by snapshotting the active mode on the coordinator and adding it to the comparison, so the handler falls through to `async_reload`. Full reload over in-place re-registration — a mode change is rare and deliberate, and reload is what that handler exists for.
- **`get_network_config` must not include hosts by default (implemented 2026-10-01).** It embedded 10 full host records (MAC, hostname, IP, reservation) inside an otherwise network-level report. `hosts` is now an opt-in `include` value and is **absent** (never empty) by default. This also removes the cross-tool identity leak identified in §5.7.
- **The version gate stays at `(2026, 10)` — verified against Core history, not inferred (settled 2026-10-01).** `ToolResult` landed 2026-09-17 (`282725da9a7d`) and `ToolAnnotations` 2026-09-19 (`7fb69f2e6c08`) — **both after every 2026.9.x release** (2026.9.0 on 09-02 through 2026.9.4 on 09-25) and inside the 2026.10 dev cycle. `merge-base --is-ancestor` confirms both are absent from all five 2026.9 releases. 2026.9's `llm.py` has `LLMContext`, `ToolInput`, `Tool`, `APIInstance`, `API` and `async_register_api`, but **no `ToolResult` / `ToolAnnotations`**, no `title` / `annotations` / `integration` on `Tool`, and `async_call` returns a raw dict. So `(2026, 10)` is exactly the boundary, not conservative. Lowering it would raise `AttributeError` at module scope in `llm_tools_read.py` **inside the previously unguarded import in `async_setup_entry`**, failing the whole config entry — the guard protects the *integration*, not just the tools. 2026.9's `mcp_server` did serve LLM APIs, but its `_format_tool` omitted `inputSchema.required`, `title` and `annotations`, so the destructive-tier `confirm` gate and the client-side confirmation hints would both have been invisible. A 2026.9 target would need a compatibility shim *and* would ship a measurably worse surface.
- **The optional AI layer is contained, not merely version-guarded (implemented 2026-10-01).** The guarded `from .llm_api import …` and the registration call are now wrapped in `try/except Exception` with `LOGGER.exception`, so any failure in the AI layer logs and returns instead of taking down setup. The version guard covers the *known* Core boundary; this covers *unknown* failures (a future Core contract change, a defect in a tool module) on any version. Covered by `test_setup_survives_llm_layer_failure`.
- **`summary_only` capability removal means the other tools are not registered, not filtered (settled 2026-10-01).** Nothing to redact and nothing to get wrong; only "it is not reachable" is worth publishing as a privacy claim. Schema-level capability removal, never runtime field filtering — matching the structural approach used for the credential claim.
- **The summary's contents are fixed by the spec table in §5.7, which is the contract.** Network names are in; group and user entries are count-only; no addresses and no hardware identifiers. Public IP (`get_speed_tests.public_ip`, `get_wan_events.wan_interface_address`) is the **most sensitive field in the surface**, ahead of MAC — it identifies the household on the internet, not a device on the LAN.
- **`min` is a working time selector on `item=events`.** Confirmed live — a 7-day window returns a strict subset, and unlike alarm reads (`REVERSE_ENGINEERING_WORKFLOW.md` Finding 39) the parameter is genuinely honoured. Prefer `min` over a count limit as the primary selector, with `limit` as a safety cap.
- **The summary/overview tool is the recommended discovery surface (settled 2026-10-01).** It closes D2 (networks) and D3 (groups/users) together while supplying the identifiers other tools require, and it reuses counts the runtime snapshot already computes. It is deliberately **not** three separate list tools — Option C. Hard constraint: it returns **counts and identities, never collections** — the structural rule that keeps it from becoming `get_runtime_inventory` again. No byte cap (settled 2026-10-01).
- **Confirmation is enforced at the prompt and annotation layers, never by a tool-side gate.** `llm.Tool` has no confirmation hook, so the tool cannot pause to ask. `annotations.destructive` remains the machine-readable signal clients act on; a prompt instruction covers non-destructive controls. The destructive tier's `confirm: true` is a guard against accidental model calls and is **not** user consent — it must not be extended to control tools as a substitute.

### Carried forward as open questions

- [x] **RESOLVED 2026-10-02 — API id strategy edge case.** The survivor keeps its suffixed id until reload; ids are decided from the entries present at registration time and no runtime reshuffling is attempted. This is documented behaviour in `_resolve_api_id`, and the case is rare enough (removing the sole entry while another exists) that a reshuffle would be more surprising than the suffix. Closing as accepted.
- [x] **RESOLVED 2026-10-02 — no `meta.units` block.** The field-name suffix convention (`_bytes`, `_mbps`, `_ms`, `_percent`, `_count`, `_timestamp`, `_at`) already carries units unambiguously and is asserted by `test_unit_bearing_field_names_follow_the_convention`. A parallel units block would be a second source of truth that could disagree with the names. Dropped permanently.
- [x] **RESOLVED 2026-10-02 — alarm mute caveats are already in the descriptions.** The mandatory scope caveat (`all`/`matchAll` silences every device) and the three fixed durations (`1h`/`today`/`always`) are enforced by the `set_alarm_muted` schema enum and stated in its description, and the reference's Caveats line repeats them. No further work; the item was tracking prose that already shipped.
- [x] **RESOLVED (verified in code 2026-10-01) — alarm↔rule link modeling:** `alarm_id` is carried on `FirewallaPolicyRule` and serialized into rule summaries, the create payload accepts `aid`, and `RuleManager.async_create_rule` now returns `str | None` (the new pid) so a same-session unblock resolves without a refresh.
- [x] **RESOLVED — `before`/`after` are in the envelope, implemented 2026-10-01.** `before` is the observed prior state, supplied only where the idempotency pre-check already read it (`pause_rule`/`resume_rule`); `after` is the **requested** state, echoed from the call's own arguments. Both keys are always present (`null` when unknown) so the envelope shape is stable, and the reference states plainly that `after` is intent, not a re-read of the box. No extra box calls. This is the precision lever 5.6 needs — the agent can now report exactly what changed rather than only that it called something.
- [x] **RESOLVED 2026-10-02 — envelope `schema_version` stays dropped.** The integration owns both the tools and the contract and ships them together; responses are opaque prose the agent reads, not parsed against a schema, and there is no independent consumer to negotiate a version with. `meta.response_type` is sufficient.
- [x] **RESOLVED — confirm the version-gating design in note §10.2** — in particular the `probatio` import ban, version-agnostic `vol.Schema` for tool parameters, hiding the option on old Core, and that setup still succeeds there. **Closed 2026-10-01 with git-history evidence** (see the decision above): the gate is exactly at the contract boundary, and the remaining risk — an unguarded import failing the whole entry — is now fixed by the `try/except` containment.

**Phase 5 anonymous-tier open questions (raised 2026-10-01):**

- [x] **RESOLVED — should group and user names be in the summary report?** **No.** Ids and counts only; names arrive with `read_only`. See §5.8 for the reasoning. Secondary option (network names only) noted if network identity is wanted in summary mode.
- [x] **RESOLVED — the default becomes `summary_only`.** Confirmed by the owner 2026-10-01. See the decision above; 5.1's `off` default is superseded.
- [x] **RESOLVED — read mode exposes names AND ids.** Confirmed required: ids are the exact-match path, names are an ambiguity-prone fallback (`_resolve_usage_history_target`).
- [x] **RESOLVED — mode name is `summary_only`.** Fits the existing verb-noun style and does not over-claim anonymity.
- [x] **RESOLVED — `get_network_config` is identity-bearing.** It embedded a per-network host list (MAC, hostname, IP, reservation); as of D10 the host section is opt-in `include` and absent by default, which removes the leak. Any remaining "low-sensitivity topology read" wording in `MCP_TOOL_REFERENCE.md` should be corrected.
- [x] **RESOLVED — the anonymous speed-test form is not a separate tool.** The curated summary carries the speed-test *metrics* and WAN name only, so `public_ip`/`isp`/`server_country` never appear. No redacted `get_speed_tests` variant is needed.

**Phase 5 open questions (raised 2026-10-01):**

- [x] **RESOLVED — should `dns` stay a supported WAN event family?** Excluded **by default**, reachable as an **explicit exception**. The app never surfaces it, and it is 162 records/week of the box's own resolver probes. Keep it in the family set (so an explicit request can still retrieve it) but never return it by default.
- [x] **RESOLVED — is `min` the right selector for `get_wan_events`?** Yes. `item=events` **does** honour a millisecond `min` window — confirmed live, and a direct contrast with Finding 39 (alarm reads silently ignore every time parameter). Use a **7-day** default window as the primary selector, with `limit` as a safety cap and `offset` for paging. A count limit over an unfiltered firehose is unstable by construction.
- [x] **RESOLVED — do `ping_RTT`/`ping_lossrate` belong in `get_wan_events`?** **No — and they belong nowhere else in the surface either.** No ping/latency/loss alarm type exists in the taxonomy or the live data, so "with alarms" is not available without fabricating records; Internet Quality stays a facts-and-data report. They are a standalone threshold-crossing feed and are **excluded from the tool surface** — superseding the earlier opt-in-flag suggestion.
- [x] **RESOLVED — the WAN-events window is a service/tool parameter, not an options-flow setting.** It is a query concern rather than configuration. The 7-day default is a constant; the override rides on the call.
- [x] **RESOLVED — does `get_wan_events` need a `detail` concept or lower limit?** Neither. The fix is **filters plus a 7-day `min` window**: the payload drops from 57,762 bytes of mostly-DNS noise to a handful of real events (2 records for the entire retained history on this box).
- [x] **RESOLVED — discovery surfaces are Option C, the overview tool.** `get_network_overview` carries network/group/user identities (in read tiers) and is the discovery layer; no separate network/group/user list tools. In `summary_only` it is the curated count-only report and the other tools are absent.
- [x] **RESOLVED — the credential claim is verified in code and locked by a test (2026-10-01).** Verified three ways: `services.py` never reads `entry.data` (which holds `symmetric_key`/`license`/`gid`/`eid`/`aid`); every `last_init_payload` read in the service layer extracts a named non-sensitive subkey (`hosts`, `deviceTags`, `networkProfiles`, `networkConfig`) rather than the whole payload; and the four modules that build tool output name no credential constant or key literal. `test_tool_output_paths_cannot_reach_credentials` asserts it on the AST, so wiring a credential in fails the test first — mutation-checked by injecting a reference and confirming the failure. **Known non-tool gap:** the admin-gated `get_runtime_inventory` service returns an unredacted report; it is deliberately not exposed as a tool, so the tool-output claim holds, but it is worth revisiting if that surface ever changes.- [ ] **Validate the summary tool against real sessions.** See §5.3. The design is settled and it is built in step 4; what is unproven is whether agents actually open with it, and whether it reduces total tokens per session rather than adding an extra call.
- [x] **RESOLVED — yes, external-endpoint data gets its own disclosure line in 5.1.** `get_alarms` (remote IP, host, app, lat/long) and `get_wan_events` describe **third-party** endpoints, not the user's own LAN — a different category from device identity, and it is disclosed separately alongside the public-IP line.

## 6. Validation strategy

Run from the repository root:

```bash
python -m ruff check .
python -m ruff format .
python -m mypy custom_components/firewalla_local
python -m pytest tests/ -v
```

Baseline at split time: **319 tests pass**, ruff/format/mypy clean. **None of that baseline touches LLM tool code** — every test in this plan is new coverage.

Required additions, per the sub-phases above:

- guard unit tests at, below, and above the version boundary
- a mocked-helper wiring test proving setup succeeds and nothing registers when unsupported
- a **static AST test** asserting no module-level `probatio` / `ToolResult` / `ToolAnnotations` import
- per-tool happy-path, envelope-shape, and error-path tests
- a cross-tool contract test (envelope, unit-bearing field names, prefixed names, `integration`, annotations)
- **control-tool response-mode tests** — one per control tool asserting the `return_response` mode matches the service registration (`NONE` vs `ONLY`), so the wrong-mode `ServiceValidationError` cannot ship
- **action-result envelope tests** — every control tool returns `status`/`changed`/`target`/`before`/`after`/`undo`, JSON-serializable
- **block-alarm-target tests** — `create_rule` (with `alarm_id`) returns the new `pid`, records the `aid` back-reference and auto-archives, `unblock_alarm_target`/`delete_rule` removes only its own rule (and works despite the stale `_rule_index`), and `undo` resolves to `unblock_alarm_target`/`pause_rule`
- **input-description and annotation tests** — every parameter has `description=`; all four annotation flags declared on every tool
- **description-content tests** — write tools carry reversibility + the undo verb; key tools name their key fields; near-neighbors are contrasted (e.g. `archive` vs `delete_alarm`)
- **pinned tool-name set test** — the registered tool set exactly equals the catalog in `docs/MCP_TOOL_REFERENCE.md` (accidental add/remove/rename breaks the suite)
- the field-name conformity check in 4.4

**Phase 5 additions:**

- **a no-argument call test for every read tool** — the D1 class of defect (schema says optional, handler requires it) is a guaranteed 400 that only a real call catches
- **filter and `detail` tests** — each filter narrows correctly and returns the unfiltered set when omitted; `detail: summary` is a strict subset of `full` and still carries every identifying field
- **a `list_rules` default-exclusion test** — `dap`/`family`-purpose rules are absent by default and present with the opt-in; assert the default equals the inventory's `visible_rules` set and that the discriminator is `purpose`, not `management.classification`
- **a `get_wan_events` filter test** — the service sends the app's link-state filter set; `dns` records do not appear by default and do appear with the explicit opt-in; `ping_RTT`/`ping_lossrate` do not appear at all; `system_reboot` survives normalization
- **a `get_wan_events` window test** — the 7-day `min` window is sent, and a fixed fixture reproduces the "2 real events instead of 100 DNS probes" outcome
- **a `get_wan_usage` default test** — the no-argument call returns day and week periods with `history_count == 0`
- **a VPN count test** — `vpn_devices_total` counts only peers (`mac.startswith(("wg_peer:", "awg_peer:"))`), `online` reuses `count_online_hosts` unchanged, and `offline` is total minus online. A fixture with one recent and one stale peer pins the behaviour
- **an entity attribute test** — the system-status entity exposes the three VPN attributes alongside the existing device-count attributes

- **an overview leverage test** — the response exposes a labelled `identifiers` block containing networks, groups, users and WAN; every tool whose selector is otherwise undiscoverable (`get_network_config`, `get_network_usage`, `get_user_usage`) names `get_network_overview` in its `description`; and the prompt fragment contains the open-once-per-session instruction. This is the test that stops the contract silently decaying — the D2 defect was exactly this text pointing at tools that cannot supply the value
- **a group-id join test** — every rule's `tag:<group_id>` reference resolves to a group in the inventory, and the join is not used to synthesise a policy-control↔rule mapping
- **an `applies_to` parity test** — every rule carrying an attachment in the source snapshot exposes it in the summary
- **a default-mode test** — a fresh entry defaults to `summary_only` and registers exactly the summary tool
- **a `sync_runtime` test** — the service exists, the tool is read-tier with `idempotent=True`, and a repeat call is a no-op in state terms
- **prompt-coverage tests for the new instructions** — action specificity, the three attachment channels, and the DAP/policy-control distinctions are asserted present, following the existing contract-test pattern
- **an AI-layer containment test** — `test_setup_survives_llm_layer_failure` simulates the tool module failing to import and asserts the entry still reaches `LOADED` with no API registered. This is the regression guard for the unguarded-import defect
- **an anonymous-tier leak test** — in `summary_only`, walk the registered tool's declared schema and a representative response and assert that no MAC, LAN IP, public IP, hostname, SSID, serial number or lat/long can appear. Assert it against the **schema**, not just the output, so a leak cannot hide behind an unused field
- **an anonymous-tier coverage test** — the tier registers exactly **one** tool and it can answer all five owner example questions
- **an options-reload test (D9)** — changing the LLM mode triggers a reload and the registered API's tool set matches the new mode without an explicit reload; plus a negative case asserting an unrelated option save still does not reload
- **a network-config include test (D10)** — `sections.hosts` is absent by default and present with `include: ["hosts"]`, following the existing `_normalize_report_include` pattern
- **a summary-contents test** — the payload contains exactly the documented sections and fields, so an accidental addition is caught. Includes asserting `pending` is absent and that speed test / quality are nested under `wan.items[]` rather than top-level
- **a VPN count test** — `vpn_devices_total` counts only peers (`mac.startswith(("wg_peer:", "awg_peer:"))`), `online` uses the shared window logic unchanged, and `offline` is total minus online. Assert the entity attributes and the summary read the **same** accessor. Include a fixture with one recently active peer and one stale peer to pin the 5/1/4 behaviour
- **an entity attribute test** — the system-status entity exposes the three VPN attributes alongside the existing device-count attributes
- **live re-measurement, not estimates** — after 5.2, re-pull every tool against the same box and record the before/after bytes in `MCP_TOOL_REFERENCE.md`. The table in 5.2 is the baseline; a change that does not reduce a payload should be justified or dropped.

Manual verification in the HA dev instance: confirm the API registers on 2026.10+, that an MCP client sees the tools, that a read tool returns the documented envelope, and that a control tool is refused for a non-admin caller.

### Phase 5 implementation order — ready to execute

Sequenced so each step is independently shippable and nothing is built on a payload that is about to change. **Steps 1–3 are complete**; steps 4–6 remain.

| Step | Phases | Status | Why here |
|---|---|---|---|
| **1** | **5.0** — D1, D4, D5, D6, D7, D8 | **Complete** | Correctness first. D1 was a guaranteed 400, D7 returned the wrong data entirely, D8 defaulted to the least-wanted period. Small, independent, and every later step reads these payloads |
| **2** | **5.2 + 5.4** | **Complete** | Payload reduction and rule-model clarity together, because 5.4's `applies_to` is itself a `list_rules` correctness fix. The `get_rules` default now matches the inventory's `visible_rules` through a shared predicate |
| **3** | **5.5** — `sync_runtime` | **Complete** | Independent and small: a read-tier service plus its tool |
| **4** | **5.7 + 5.9** | **Complete** | The curated summary and the VPN counts landed together, sharing one accessor. The `summary_only` default flipped in the same change that registers the tool, so no state could point at a missing tool. 5.3's discovery surface **merged here** — same artefact, no separate list tools |
| **5** | **5.1** | In progress | The default and the user-guide disclosure landed with step 4; the options-flow label wording and README follow |
| **6** | **5.6** | not-started | Prompt instructions for action specificity and the rule model are cheap and can trail. 5.3 no longer appears here — it merged into step 4 |

**Default-mode note:** `DEFAULT_LLM_TOOL_MODE = summary_only` flips in **step 4**, in the same change that registers the summary tool, so no intermediate state can land a default pointing at a tool that is not built.

## 7. Release 2.2.0

**Version:** `2.2.0` in `manifest.json` and `pyproject.toml`. **Home Assistant floor unchanged** at 2025.10; the AI/MCP surface is gated at Core 2026.10 and is simply absent on older Core.

**Suggested GitHub release body:**

> ### AI assistant & MCP access
> Firewalla Local now registers its own MCP tool surface, so an AI assistant with an MCP client can answer questions about your network — how many devices are online, which network they are on, why the internet dropped — using your local box, with no sidecar and no cloud subscription.
>
> **Privacy-first default.** The new **Summary only** tier is the default. It answers general questions with counts, network names, and performance metrics, and sends **no device addresses, no hardware identifiers, no group or user names, and no public IP**. Raise access to **Read only** for device names and addresses, **Read and control** for reversible actions, or **Full** for destructive ones.
>
> In Summary only the other tools are *not registered at all* — there is nothing to redact and nothing to leak. Every control action still requires an administrator, so a non-admin user cannot change your network through the assistant.
>
> **Read access is a real trade.** Anything above Summary only sends device names, IP and MAC addresses, rule and alarm detail, and your public IP to whichever LLM provider your assistant uses. Use the lowest tier that answers your question.
>
> Requires Home Assistant Core 2026.10 or newer for the AI tools. On older Core the integration works exactly as before.

**Payload and tool-surface work in this release:** filters on `list_hosts` / `list_rules` (with descriptions that tell the model to use them), `detail: summary` by default on host reads, real WAN link events instead of resolver probes, day+week WAN totals, a non-admin `sync_runtime`, and a curated `get_system_overview` that replaces the costly opening call.

**Known risks and defers carried into this release:**

- **Rule-scope precedence is stated as owner-provided product behaviour, not reproduced from a live capture.** The prompt, the `list_rules` description, and the reference all say that once a device belongs to a group or user its device-level rules no longer apply. If a future capture contradicts it, those three sites are the places to fix.
- **Live payload re-measurement (5.2) and the runtime smoke checks were not run in this environment** — no box is reachable from the dev container. The release checklist owns both, and the in-repo guarantee is the response *shape* (asserted exhaustively), not the byte counts.
- The long-term defers in `RELEASE_CHECKLIST.md` (discovery support, rule-family expansion, DHCP admin surfaces, release automation, custom branding) are unchanged.

## 8. References

**Predecessor plan (archived)**

- `plans/completed/FIREWALLA_LOCAL_SURFACE_COMPLETION_COMPLETED.md` — the initiative this plan was split from. Phases 1–3 are complete and shipped in 2.1.0; its Phase 4 section is a pointer to this file.

**Supporting notes (this initiative)**

- `plans/completed/FIREWALLA_LOCAL_MCP_CAPABILITIES_SUP_PLAN_REVIEW.md` — the 2026.10/agent-friendliness review and the second-pass traps/gaps/opportunities.
- `plans/completed/FIREWALLA_LOCAL_MCP_CAPABILITIES_SUP_THIRD_PARTY_REVIEW.md` — review of `djuntgen/firewalla-mcp` (untrusted reference) and our differentiated high-value surface ranking.
- `plans/completed/FIREWALLA_LOCAL_MCP_CAPABILITIES_SUP_BUILDER_HANDOFF.md` — the implementation handoff to `Firewalla Builder` (Phase 4.1; the dev branch is its first step).

**Supporting research notes (archived beside the predecessor plan)**

- `plans/completed/FIREWALLA_LOCAL_SURFACE_COMPLETION_SUP_LLM_MCP_INVESTIGATION.md` — Phase 4 findings, clarity architecture, tool catalog proposal, version design, and decisions. **Start here.**
- `plans/completed/FIREWALLA_LOCAL_SURFACE_COMPLETION_SUP_LLM_MCP_NOTES.md` — raw verified LLM/MCP platform facts, semantic channels, supported paths, corrections to earlier analysis.
- `plans/completed/FIREWALLA_LOCAL_SURFACE_COMPLETION_SUP_CORE_2026_10_CHANGES.md` — the Core 2026.10 platform changes that make this design possible (probatio migration, tool contract, version gating).
- `plans/completed/FIREWALLA_LOCAL_SURFACE_COMPLETION_SUP_SERVICE_ACCESS_MATRIX.md` — service classification and the admin-gating decisions this plan depends on.

**Repository**

- `AGENTS.md`, `README.md`, `pyproject.toml`
- `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_STANDARDS.md`, `docs/QUALITY_REFERENCE.md`
- `docs/USER_GUIDE.md` — where the MCP section and the "Using your data across Home Assistant" framing live
- `docs/MCP_TOOL_REFERENCE.md` — **drafted in 4.0** — the authoritative tool spec + surface record the user guide links to (refine per-tool detail as tools land).
- `docs/REVERSE_ENGINEERING_WORKFLOW.md` — Findings 26–34 (alarm surface) and **Findings 31/34 (block = policy-rule creation, `aid` back-reference, no block endpoint)** — the authority for the block-alarm-target model
- `docs/RULE_MODEL.md` — rule lifecycle, switch-eligibility, pause/resume semantics
- `custom_components/firewalla_local/services.py` — `_SERVICE_REGISTRATIONS`, the admin registration path every tool ultimately depends on
- `custom_components/firewalla_local/managers/rule_manager.py` — `async_pause_rule`/`async_resume_rule`/`async_delete_rule`; where a thin `async_create_rule` wrapper belongs
- `custom_components/firewalla_local/api/client.py` — `async_create_rule` (`policy:create`, currently `-> None`), `async_delete_rule` (`policy:delete`)
- `custom_components/firewalla_local/const.py` — the pure `MIN_LLM_TOOLS_HA_VERSION` tuple (no HA import)
- `custom_components/firewalla_local/helpers/llm_support.py` — **created** — `llm_tools_supported()` predicate (imports `homeassistant.const`)
- **`llm_tools_read.py`** — **created** — the read `llm.Tool` subclasses (guard-loaded only)
- **`llm_tools_control.py`** — **created** — the tiered control `llm.Tool` subclasses (guard-loaded only; registered only in `read_and_control` mode)
- `custom_components/firewalla_local/quality_scale.yaml`

**Home Assistant**

- `homeassistant/helpers/llm.py` — `ToolResult`, `ToolAnnotations`, API registration
- `homeassistant/helpers/service.py` → `async_register_admin_service`, `_async_admin_handler` (the no-`user_id` pass-through)
- `homeassistant/components/mcp_server/` — the thin adapter over the LLM API
- Developer docs — LLM API: creating an API, contributing tools via `llm.py`, and *"Exposing an API over MCP"* (`/api/mcp/<API ID>`, admin token required for non-Assist APIs)
