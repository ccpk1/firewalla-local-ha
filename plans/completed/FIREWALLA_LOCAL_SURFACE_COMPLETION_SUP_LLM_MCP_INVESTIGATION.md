# Supporting note: LLM / MCP investigation — surfacing rich data with unambiguous semantics

## Purpose

Record the completed investigation for Phase 4 of `FIREWALLA_LOCAL_SURFACE_COMPLETION_COMPLETED.md`. Phase 4 was deferred to `plans/in-process/FIREWALLA_LOCAL_MCP_CAPABILITIES_IN-PROCESS.md`; this note remains the research base for that plan.

The driving concern: **our data is rich and nuanced, and an LLM must not misinterpret it.** This note answers where response semantics can legally live, what specifically is ambiguous today, and how to make the contract enforceable rather than aspirational.

Raw verified facts about the LLM/MCP machinery are in the companion note `FIREWALLA_LOCAL_SURFACE_COMPLETION_SUP_LLM_MCP_NOTES.md`. This note builds on them and does not repeat them.

**Status:** investigation complete. No implementation authorized. Implementation, if approved, becomes its own initiative.

**Repository baseline verified.** On Core 2026.10.0.dev0 the integration passes ruff, mypy and the full test suite (**290 passed**), confirming the Core update introduced no regressions and that the voluptuous→probatio shim is sufficient at runtime. See `FIREWALLA_LOCAL_SURFACE_COMPLETION_SUP_CORE_2026_10_CHANGES.md` §6 for scope. Note that **none of that validates LLM tool code**, which does not exist yet.

## 1. What an LLM actually sees — the complete semantic budget

Every possible channel, confirmed against the installed Core tree and the developer blog:

| # | Channel | Carries | Notes |
|---|---|---|---|
| 1 | **Tool `name`** | identity, routing | **Must be `firewalla_local__*`.** `llm/__init__.py::_async_report_unprefixed_tools` reports unprefixed names today and **breaks in 2027.3** |
| 2 | **Tool `title`** | short human-readable label | **Core 2026.10+.** New in [the Sept 26, 2026 post](https://developers.home-assistant.io/blog/2026/09/26/llm-tool-result) |
| 3 | **Tool `description`** | free prose | Primary usage guidance. The only per-tool field with no schema constraints |
| 4 | **Tool `annotations`** | machine-readable risk flags | **Core 2026.10+.** `llm.ToolAnnotations(read_only, destructive, idempotent, open_world)` — **"the MCP Server integration serves the title and the annotations to MCP clients"** |
| 5 | **Parameter schema** | types, enums, bounds, per-field `description=`, **and `required`** | `mcp_server._format_tool` copies `inputSchema["properties"]` **and now preserves `required`** — see the corrected note below |
| 6 | **API-level prompt fragment** | cross-cutting interpretation rules | `LLMTools(tools=[...], prompt="...")`; joined with `"\n"` across platforms and merged into `api_prompt` |
| 7 | **The returned data** | the data itself | **Core 2026.10+:** `llm.ToolResult(data=..., error=...)`. `mcp_server` serializes it to MCP text content |

Three consequences that shape the whole design:

- **Annotations are served — confirmed in the updated tree.** `llm.ToolAnnotations(read_only, destructive, idempotent, open_world)` exists in `helpers/llm.py`, and `mcp_server._format_tool` maps all four to MCP's `ToolAnnotations(readOnlyHint, destructiveHint, idempotentHint, openWorldHint)`. Read-only vs. destructive **is** machine-flagable, so the control-tool safety story does not depend on prose alone.
- **Annotation defaults are the least safe case.** The `ToolAnnotations` docstring: *"a tool that declares nothing is taken to write, to be destructive, and to reach outside Home Assistant."* Read tools must **explicitly** declare `read_only=True, destructive=False` — omitting annotations makes a safe tool look dangerous.
- **`required` IS preserved.** `_format_tool` now does `if required := input_schema.get("required"): mcp_schema["required"] = required`, and it emits `openapi_version="3.1.0"`. This supersedes the earlier finding that `required` was dropped — requiredness is machine-visible, so it does not have to be restated in prose (though clear descriptions remain worthwhile).
- **Every tool must declare `integration = DOMAIN`.** The blog states creating a tool without `integration` is deprecated — a custom integration gets a warning until **2027.10** and stops working after. `helpers/llm.py` enforces this via `TOOL_INTEGRATION_BREAKS_IN_HA_VERSION`.
- **Build tool parameter schemas with `vol.Schema`, not `probatio.Schema`.** *(Corrected.)* Core's own LLM platforms use `probatio`, but `probatio` **does not exist on Core < 2026.10** — importing it would prevent the integration from loading for existing users. `vol.Schema` resolves on both sides of the migration: real voluptuous on < 2026.10, the probatio shim on ≥ 2026.10 (verified: the shim's top-level surface includes `Schema`, `Required`, `Optional`, `In`, `Marker`). Same for `vol.Required` / `vol.Optional` / `vol.In`. See §10.2.

## 2. The clarity problem, stated concretely

These are the specific ambiguities found in the existing surfaces. Each one is a real way an LLM could produce a confidently wrong answer.

### 2.1 Semantic / behavioural ambiguities

| Nuance | Why it misleads | Where it lives |
|---|---|---|
| **`refresh` (default `true`) triggers a live box poll** | Not a formatting flag — it has latency and load cost. An LLM will set it arbitrarily unless told | every read service schema |
| **Windows are not uniformly supported** | `get_network_segment_usage` accepts four windows, but WAN windowed usage genuinely is not available; elsewhere a window is required at all | `_resolve_network_segment_usage_window`, `TRANS_KEY_EXCEPTION_NETWORK_USAGE_WINDOW_REQUIRED` |
| **Two different transfer totals that can disagree** | `window_download_total` (from the series) and `derived_download_total` (summed from per-host rows) measure different things and need not match | `_serialize_network_segment_usage` |
| **`activity_hosts` vs `hosts` fallback** | `device_rows = view.activity_hosts or view.hosts` — the same key can mean "activity-derived" or "totals-derived" depending on what the box returned | same function |
| **`top_n` silently truncates** | A truncated ranking can be read as a complete one | `top_n` default 5 |
| **`include: "series"`** | Changes summary-only into summary-plus-raw-samples; not obvious it is optional | schema |
| **`is_partial` / `boundary_source` on `time_basis`** | A partial bucket is not a smaller real value — it is an incomplete measurement | `FirewallaReportTimeBasis` |
| **`provenance.source_field` exposes internal paths** | Values like `flows.appDetails` are diagnostic, not user-meaningful — an LLM may treat them as data | `FirewallaReportProvenance` |
| **`TL-` / `TLX-` targets are opaque IDs** | Target list names require cloud `mspData`; the LLM will see raw IDs and may invent names | `RULE_TARGET_LIST_PREFIX`, reverse-engineering doc |
| **`confirm: true` interlock on `delete_host`** | A destructive call fails without it; the LLM must know it is required and that it is destructive | `DELETE_HOST_SCHEMA` |
| **Multi-entry selection** | `config_entry_id` vs `config_entry_name`, plus ambiguity when names repeat | every service |
| **Read services are `SupportsResponse.ONLY`** | They must be invoked with `return_response`; calling them as fire-and-forget returns nothing | `_SERVICE_REGISTRATIONS` |

### 2.2 Unit and representation traps (the highest-risk category)

These are silent: the value parses fine and means something else.

| Trap | Detail |
|---|---|
| **Bytes vs megabytes** | Network/data-usage fields are `*_bytes`; speed test uses `*_megabytes` / `*_mbps`. Mixing them is a 10⁶ error |
| **Percent vs fraction** | The box stores `lossrate` as a **fraction** (0.165 = 16.5%); we multiply by 100 at the boundary. If any path skips that, the number is off by 100× |
| **Epoch seconds vs ISO 8601** | Report `time_basis` uses epoch ints; several entity attributes render ISO strings. Same underlying value, two representations |
| **`latency` units vary by source** | Speed-test latency, internet-quality ping latency, and `latencyMs` in external prior art are all ms but arrive via different paths |

## 3. Clarity architecture — four layers, cheapest first

Design principle: **cross-cutting rules go in the prompt (sent once per request); per-tool rules go in the tool; per-response additions stay minimal to avoid token bloat.**

### Layer 1 — Prompt fragment (cross-cutting, once per request)

The natural home for the interpretation guide, because it is assembled once per request rather than per response. This is where the understanding lives:

- units contract (bytes, ms, percent 0–100, Mbps)
- `provenance` explains how a section was produced; `warnings` mean the result is degraded or partial
- `time_basis.is_partial` means an incomplete measurement, not a small value
- target list `TL-`/`TLX-` values are raw IDs; human-readable names are unavailable locally by design
- which windows each data source actually supports
- that `refresh` performs a live poll and has a cost
- read-only vs. control tools, and that control tools require admin

### Layer 2 — Tool descriptions (per tool)

For each tool: what question it answers, what it returns, when **not** to use it, and how it differs from its nearest sibling. Disambiguation between neighbouring tools is the highest-value content here.

### Layer 3 — Parameter descriptions (per field)

Every field gets `description=`, built with `vol.Schema` / `vol.Required` / `vol.Optional` (version-agnostic; see §10.2). Enums get their meaning, not just their values (`last_60_minutes` → "last 60 minutes of samples, not a rolling hour"). Requiredness is machine-visible via the schema, so it does not need restating in prose — but a description that says *why* a field matters still improves tool selection.

### Layer 4 — Response envelope (per response, minimal)

**Use the standard: `llm.ToolResult`.** Do not invent an envelope. On Core **2026.10+**, `async_call` returns `llm.ToolResult(data=<payload>, error=<bool>)` — the framework's own contract, replacing the older `{"success": True, "result": ...}` convention that `ActionTool` and `GetLiveContextTool` still use. Returning a plain JSON object is **deprecated** (warning until 2027.11).

So the `meta` block rides inside `data`, not beside it:

```python
return llm.ToolResult(
    data={
        "result": service_result,
        "meta": {"response_type": ..., "truncated": ...},
    },
    error=False,
)
```

`error=True` is the framework's own failure signal, so a failed call no longer has to be encoded as a `success: False` key.

**Recommended: do not restructure the existing service payloads.** The tool wrapper is exactly where the clarity layer can be added *without* breaking the services — this is the key architectural insight. Services stay byte-compatible for existing automations; tools wrap them and add:

- `meta.response_type` — a stable discriminator so the LLM knows which shape it received
- `meta.applied_limit` / `meta.truncated` — only when `top_n`/`limit` actually cut data
- `meta.units` — only for fields where ambiguity genuinely exists

Do **not** emit a full field dictionary per response. Provenance and warnings already carry most of the weight; the rest belongs in the prompt.

## 4. Enforcing the contract (the answer to "how can we be sure")

Prose drifts. The durable answer is to make the contract testable:

1. **One canonical contract document** (extend `docs/SURFACE_INVENTORY.md` or add `docs/LLM_TOOL_CONTRACT.md`) defining the envelope, envelope fields, the **units table**, provenance/warning semantics, and truncation signalling. Humans read this.
2. **The prompt fragment is derived from it**, so the machine-facing rules and the human-facing rules share one source.
3. **Contract tests** that assert, for every registered tool: the response carries the envelope; every unit-bearing field name matches a recognised suffix; every warning code emitted is documented; no undocumented top-level key appears.

Point 3 is what makes this reliable rather than hopeful.

### 4.1 Naming convention as the primary clarity tool

Encode meaning in the field name and most ambiguity disappears before any prose is needed. Proposed suffix contract:

| Suffix | Meaning |
|---|---|
| `_bytes` | bytes |
| `_mbps` / `_megabytes` | network rate / transferred megabytes |
| `_ms` | milliseconds |
| `_percent` | 0–100 |
| `_count` | integer count |
| `_timestamp` | epoch seconds |
| `_at` | ISO 8601 string |
| `is_*` / `has_*` | boolean |

Recommend an audit of existing response fields against this, and correcting outliers. A conformity test keeps it true.

## 5. Tool catalog proposal

**Consolidate.** A thin wrapper per service (22 tools) would flood the context and degrade selection accuracy. Recommend ~9 read-oriented tools, each answering a question a person would actually ask:

| Proposed tool | Backs onto |
|---|---|
| `firewalla_local__get_network_usage` | `get_network_segment_usage` (top talkers, apps, categories, activity) |
| `firewalla_local__get_network_config` | `get_network_segment_report` |
| `firewalla_local__get_runtime_inventory` | `get_runtime_inventory` |
| `firewalla_local__get_host_inventory` | `get_host_name_mapping` |
| `firewalla_local__get_wan_usage` | `get_wan_data_usage` |
| `firewalla_local__get_wan_events` | `get_wan_events` |
| `firewalla_local__get_speed_tests` | `get_speed_test_results` |
| `firewalla_local__get_internet_quality` | `get_internet_quality_report` |
| `firewalla_local__get_user_usage` | `get_time_usage_report` |
| `firewalla_local__get_wireless_status` | `get_wireless_status` |

**Availability model (decided):** the read tools above are **enabled by default** — they carry no write risk and are where most of the value sits — with an option to turn them off for users who want the integration to expose nothing to an LLM. Control tools default to **off**. See §5.2.

### 5.1 Control tools (include, tiered)

**Decision: include control tools.** Excluding them was too conservative. The discovery-and-act workflow is the highest-value thing an LLM can do here, it is already built, and if we do not expose it someone else will build a worse version of it.

The design question is not *whether* but *how to tier by blast radius*.

**Tier A — include (reversible or no persistent state change)**

| Tool | Why it is safe enough |
|---|---|
| `pause_rule` / `resume_rule` | **The single most-requested action.** Fully reversible, and idempotent (already a no-op if already in the desired state) |
| `set_ssid_paused` | **Decided: first-class control.** Pausing an SSID achieves the same outcome as pausing a rule for the devices on that SSID, so it carries the same practical value. Fully reversible. Caveat still stated in its description: it has a **wider blast radius** than a single rule — every client on that SSID disconnects, **including possibly the client issuing the call or the device hosting Home Assistant** |
| `set_host_dhcp_reservation` | High value; reversible by setting mode back to `dynamic`. **Already carries strong validation** — conflict, in-use, invalid, network-ambiguous, network-not-found, out-of-range, required |
| `set_host_name` | Cosmetic rename, trivially reversible |
| `wake_host` | Sends one packet; no persistent state change |
| `set_host_notify_when_next_online` / `_offline` | Notification preferences only |
| `set_host_device_type` | Cosmetic classification |

**Tier B — include with explicit caveats in the description**

| Tool | Caveat that must be stated |
|---|---|
| `set_host_dns_hostname` | Can break name resolution for that host. Reversible but disruptive |
| `run_internet_speed_test` | Consumes WAN bandwidth on demand; can be repeated. Not destructive, but state the cost |

**Tier C — exclude**

| Tool | Reason |
|---|---|
| `delete_host` | **Irreversible.** There is no confirmation channel over MCP (no annotations, no interactive approval), so a mistaken call is unrecoverable. This is the one place where "someone else will build it" does not justify the risk — and we have no way to warn the user in-band |

### 5.2 Guardrails (in order of importance)

1. **The service-level admin gate is the real protection — and Phase 1 is therefore a hard prerequisite.** Verified: `/api/mcp` (the *configured* API endpoint) explicitly **does not require admin**, while `/api/mcp/<api_id>` does. So if a user selects our API as the configured API, a non-admin token can reach our tools. The endpoint check alone is insufficient; the admin-gated service is what actually stops the write. Do not build control tools before Phase 1 lands.
2. **Availability model (decided).** **Read tools are registered by default, with an option to disable them.** Control tools default to **off** and are enabled by a single options toggle. Rationale: read-only exposure is the low-risk default and the source of most value, but a user who wants to expose nothing to an LLM should be able to say so. Control tools are informed consent for write access as a class; per-tool granularity would add option-flow complexity without safety gain, since the admin gate already constrains who can reach them.

   **Recommended shape — a single three-state select** rather than two independent booleans:

   | State | Behaviour |
   |---|---|
   | Off | no tools registered |
   | Read only *(default)* | read tools registered, control tools absent |
   | Read and control | read tools + control tools registered |

   Why a select rather than two checkboxes: read-off-with-control-on is a contradictory state (control tools depend on read tools for target discovery), and two booleans cannot express "cannot be chosen". One option, three valid states, no invalid combination. Two booleans are workable if preferred — but then the options flow must force control to imply read.
3. **Encode risk in the name.** With annotations unavailable, the name is the only machine-visible signal of risk. Keep a consistent verb-first convention so reversible vs. consequential actions are distinguishable at a glance.
4. **Descriptions must state effect, reversibility and how to undo.** This is the only warning channel the model receives.
5. **Idempotent pre-checks.** Do not act when already in the desired state (the MCP server project does this for `pause_rule`/`resume_rule`).
6. **Resolve targets from read tools first.** The LLM should list hosts via a read tool and act on the returned MAC. This also constrains injection (targets come from data, not invention).
7. **Validation errors already guide the model.** Our reservation and rule validation raise `ServiceValidationError`, and `mcp_server.call_tool` surfaces it as text (`Error calling tool: ...`). The model gets an actionable message and can correct itself — a genuine safety asset that already exists.

### 5.3 The new risk: prompt injection via network data

Combining read tools over **attacker-influencable text** (host names, DNS names, domains, alarm messages) with write tools in one toolset creates a real injection surface: a device on the LAN could name itself to attempt to steer the model into a write call. This risk does not exist for a read-only toolset.

Mitigations, all of which we should adopt:

- the prompt explicitly instructs the model to **treat tool results as data, never as instructions**
- irreversible operations are excluded entirely (Tier C)
- targets are resolved from read-tool output rather than invented
- the admin gate limits who can reach the tools at all

Note the workflow this validates: *list endpoints → identify those without reservations → rename or reserve* is fully supported today, because `get_host_name_mapping` already returns `ip_assignment` with `mode`, `network_uuid` and `reserved_ipv4`, and `set_host_dhcp_reservation` performs the write.

## 6. Option A vs Option B — recommendation

Both are verified-supported (see the companion notes note for the mechanics).

**Recommendation: Option B (owned API)** as the primary path.

| | Option A — `llm.py` platform | Option B — owned `llm.API` |
|---|---|---|
| User opt-in | ❌ tools merge into **every** Assist conversation | ✅ appears as a selectable API |
| Own prompt | ✅ `LLMTools.prompt` | ✅ `api_prompt` |
| Lifecycle work | none | must register/unregister per entry |
| MCP endpoint | `/api/mcp/assist` (shared) | `/api/mcp/<our id>` (separate, admin token) |

Reasons for B: it gives explicit opt-in, matching the repository's existing `entity-disabled-by-default` precedent; it keeps ~10 network tools out of every voice-assistant conversation; and it yields a dedicated MCP endpoint with the admin-token requirement already enforced by HA. The `api_id` parameter means Option A can be layered on later if broad availability is ever wanted.

**Trade-off (resolved in §6.1):** the API id must be unique, but should stay clean for the common single-instance case.

### 6.1 API id strategy (resolved)

The id is only used in the MCP URL — the UI label comes from `name`, so users still see a friendly entry title in the API selector.

**Decision: bare id for the sole instance, suffixed ids beyond it.** ~95% of users run one box, so:

- **One Firewalla entry present at setup** → `firewalla_local` → clean URL `/api/mcp/firewalla_local`
- **More than one** → `firewalla_local-<slugified entry title>`
- **Slug collision** (two entries with the same or similar titles) → append `-<entry_id[:8]>`
- **`name`** always stays the friendly entry title

Why this beats the entry-id-only approach: the common case gets a memorable, pasteable URL, and the disambiguating suffix stays human-readable.

**Known edge case — accept and document.** If the sole entry is deleted while another remains, the survivor keeps its suffixed id until it is reloaded; the id is decided from the entries present at setup and is not reshuffled live. Consequence: an MCP URL can change after config-entry churn. This is rare, and reshuffling ids at runtime would be worse (it would break a configured client mid-session). Do **not** persist ids into entry data to work around it — that is disproportionate for a 95%-single-instance integration.

Two implementation cautions: entry titles are user-editable, so slugify defensively and never assume uniqueness; and `llm.async_register_api` raises if an id is already registered, so registration must be collision-safe.

## 7. Implementation shape and effort

### 7.1 The delegation insight (this is what makes it cheap)

A tool does not need to re-implement anything. `ActionTool` in Core demonstrates the supported pattern: call the existing service and take its response.

The consequence for us is significant — **every read tool is a thin adapter over a service that already exists**, because our report services already return `JsonObjectType` and are registered `SupportsResponse.ONLY`:

1. build `tool_args` from the LLM's parameters
2. call `hass.services.async_call(DOMAIN, <service>, tool_args, context=llm_context.context, blocking=True, return_response=True)`
3. wrap the result as `{"success": True, "result": <service result>, "meta": {"response_type": ..., "truncated": ...}}`

Passing `llm_context.context` is also what makes the Phase 1 admin gate work correctly for LLM tool calls — the caller's permissions flow through automatically.

### 7.2 Deliverables

| Item | Content |
|---|---|
| `llm.py` (new) | `FirewallaLocalAPI` (`async_get_api_instance`) + ~9 read `Tool` subclasses + up to ~9 control `Tool` subclasses (gated) + the prompt fragment constant. Every tool declares `name`, `title`, `description`, `integration = DOMAIN`, and `annotations` |
| `__init__.py` | register the API on entry setup, `entry.async_on_unload(...)` to unregister |
| Prompt constant | the cross-cutting interpretation guide (units, provenance, warnings, `is_partial`, `TL-` IDs, refresh cost, read-only vs control) |
| `contract doc` | envelope definition, units table, suffix convention, warning codes — **written in the shared surface-inventory format (§7.4)** |
| Options flow | **single three-state select: Off / Read only (default) / Read and control** |
| Tests | one per tool (happy path + envelope), plus a contract test over all tools |
| Docs | MCP section in the shared surface-inventory format (§7.4), USER_GUIDE enable/connect steps, **plus the README asterisk + footnote stating the 2026.10 requirement (§10.2 rule 9)** |

### 7.3 Messages and translation (researched — the standard already covers errors)

**Verified: error messages are already translated to English for free.**

`homeassistant/exceptions.py::HomeAssistantError.__str__` resolves a `translation_key` through the compiled English translations and its docstring states: *"The message will be in English, regardless of the configured language."* It calls `async_get_exception_message(translation_domain, translation_key, translation_placeholders)`, interpolating placeholders.

Why this matters here: our services already raise `ServiceValidationError` with translation keys and placeholders — reservation validation, pause/resume timing, rule-target-not-found, and the rest. `mcp_server.call_tool` wraps failures as `f"Error calling tool: {e}"`, which invokes `__str__`.

**Consequence:** when the model attempts an invalid write, it receives a natural English sentence resolved from the existing `translations/en.json` — with **no new work** and no new mechanism. This is the Home Assistant standard, and it is precisely the "properly set up for translations" approach. Error-message translation is therefore **already solved**.

**What is *not* covered by a standard — tool names and descriptions:**

- **Tool names must never be translated.** They are routing identifiers used in the MCP protocol and by API clients. Translating them would break calls.
- **Tool descriptions have no translation mechanism.** Verified: `script/hassfest/translations.py::gen_strings_schema` permits `title`, `config`, `options`, `selector`, `entity`, `entity_component`, `services`, `exceptions`, `issues` and similar — there is **no `llm` or `tools` section**, and the schema rejects unknown keys. Every Core integration hardcodes English descriptions (`llm/llm.py`, `todo/llm.py`, `climate/llm.py`, `fan/llm.py`).

**Recommendation:** write descriptions in English, following Core. Do not invent a translation layer — it would fail hassfest validation, and tool descriptions are model instructions rather than user-interface strings, so they are not in scope for HA's translation pipeline.

**Future-proofing, cheaply:** define each tool's name and description as module-level constants (one small mapping per tool) rather than inline literals. If HA ever adds tool translation, extraction becomes mechanical instead of an archaeology exercise.

**Implementation caveat to verify:** confirm that `ServiceValidationError` propagates unchanged through `hass.services.async_call(..., blocking=True, return_response=True)` inside our tool, so the model sees the resolved sentence rather than a re-wrapped message.

### 7.4 Documentation — shared format with the surface inventory

**Decision: document the MCP surface in the same format and location family as the Phase 3 surface inventory**, so a reader sees entities, services and MCP tools as three views of one system rather than three unrelated docs.

Practical shape — extend `docs/SURFACE_INVENTORY.md` (Phase 3) with an **MCP section**, or a sibling `docs/MCP_SURFACE.md` that reuses the identical column layout and cross-links:

| Column | Content |
|---|---|
| Tool name | `firewalla_local__<verb>_<noun>` |
| Backs onto | the service it delegates to |
| Availability | default-on (read) or behind the control toggle |
| Risk tier | A / B (C excluded) |
| Answers | the question a user would actually ask |
| Key caveats | limits, `TL-` IDs, `refresh` cost, truncation, reversibility and how to undo |

Benefits of sharing the format: one reading experience for entities → services → MCP; the tool table is derived from the same service catalog, so drift is visible; and the Phase 3 limitations section (TL- names, unsupported windows) applies verbatim to the MCP tools, since they return the same payloads.

### 7.5 Effort (approximate)

| Area | Effort |
|---|---|
| API class + registration + prompt | Small — mostly declarative |
| ~9 tool classes | Small each (~20–40 lines, largely a schema + a delegation call) |
| Control tools (Tier A/B) | Small each, but each needs a considered description and an idempotency/validation test |
| Field-name audit against the suffix convention | Small, but touches response fields — verify no consumer breaks |
| Contract tests + per-tool tests | **Largest single item** — this is where the real effort sits |
| Docs | Small |

**Overall: low-to-moderate, roughly one focused initiative.** Risk is low because there is **no protocol work** — no new crypto, no new transport, no new endpoint discovery. The work is declarative wrappers plus test discipline. The main cost is the test suite, and the main judgement call is the prompt wording and tool consolidation.

## 8. Limits of this approach (state honestly)

- **Prompt fragments are advisory.** Nothing enforces that a model obeys them. Clarity reduces misinterpretation; it does not eliminate it.
- **No annotations.** Destructive tools cannot be machine-flagged to MCP clients.
- **No `required` in MCP schemas.** Parameter requiredness is prose-only.
- **Tool responses are plain JSON text.** No typed return schema exists — `JsonObjectType` is opaque to the client.
- **No annotation fallback on older versions.** Annotations arrive in 2026.10; on older Core the guardrails fall back to names and prose, which is a second reason to gate the feature to 2026.10+ rather than support both.
- **Context cost.** Every tool and every prompt line competes for context; this is the main argument for consolidation over one-tool-per-service.
- **No confirmation channel.** There is no way to ask the user to approve a call mid-flight, which is precisely why irreversible operations are excluded rather than merely discouraged.
- **Endpoint exposure differs by path.** `/api/mcp/<api_id>` requires admin; `/api/mcp` does not. Security must not depend on which URL the client happens to use — hence the reliance on the service-level gate.

## 9. Recommendation summary

1. **Adopt the four-layer architecture** with cross-cutting rules in the prompt and per-tool rules in the tool.
2. **Delegate, don't re-implement.** Each tool calls the existing service via `hass.services.async_call(..., return_response=True)` and wraps the result — this is what keeps the build small.
3. **Return `llm.ToolResult`**, the standard contract on Core 2026.10+, with the `meta` block inside `data`. Clarity is added at the tool layer without touching service payloads, so services stay backwards compatible.
4. **Every tool declares `name`, `title`, `description`, `integration = DOMAIN`, and `annotations`.** Explicit annotations are required — the defaults are the least safe reading. Parameter schemas use `vol.Schema`, never `probatio` (§10.2).
5. **Consolidate to ~9 read tools**, all prefixed `firewalla_local__`.
6. **Encode units in field names** and test the convention.
7. **Define the contract in one document**, derive the prompt from it, and enforce it with contract tests.
8. **Include control tools**, tiered by blast radius: Tier A reversible actions (including `pause_rule`/`resume_rule` and `set_ssid_paused`), Tier B with caveats, Tier C (irreversible) excluded (§5.1). **Phase 1 admin gating is a hard prerequisite** (§5.2).
9. **Read tools on by default with an option to disable; one select for control tools** (§5.2).
10. **Choose Option B** for opt-in and a dedicated admin-protected MCP endpoint.
11. **Use the bare `firewalla_local` id for the sole entry**, suffixed ids beyond it (§6.1).
12. **Require Core 2026.10 for this feature, and handle older Core gracefully** — gate registration, keep imports version-safe (`vol.Schema`, no `probatio`), hide the option, document the requirement, and test the unsupported path (§10.2).
13. **Document MCP tools in the surface-inventory format** (§7.4).

## 10. Minimum Home Assistant version (researched)

The concern is well-founded: most of this is recent, and the tool contract changes in **2026.10**.

| Capability | Version | Source |
|---|---|---|
| `llm.async_register_api`, LLM APIs, `llm.Tool`, `llm.APIInstance` | **2024.6** | Blog, May 20 2024 — *"Exposing Home Assistant API to LLMs"* |
| `mcp_server` integration | **2025.2** | Integration docs page: *"introduced in Home Assistant 2025.2"* |
| `LLMTools` + the `llm.py` platform hook (`async_get_tools`) | **Not pinned** — needs confirmation | Not covered by any developer blog post I could find |
| `llm.ToolResult`, `llm.ToolAnnotations`, `Tool.title`, `Tool.integration`, MCP serving title + annotations | **2026.10** | Blog, Sept 26 2026 — *"LLM tools return a ToolResult and declare their integration"* |
| Per-API MCP endpoints `/api/mcp/<api_id>` | **Not pinned** — needs confirmation | Documented, but no version stated |

### 10.1 Recommendation: target **2026.10** as the minimum for this feature

Not because it is required to register a tool at all, but because 2026.10 is the release that makes the *safety* design possible:

- **Annotations.** Machine-readable `read_only` / `destructive` served to MCP clients. Without them, our control-tool guardrails fall back to names and prose only.
- **`ToolResult`** — the standard return type, avoiding the deprecated plain-JSON path.
- **`integration`** — required to avoid a deprecation warning that becomes an error for custom integrations in 2027.10.

Targeting 2026.10 means we build the contract **once**, rather than shipping the deprecated shape and rewriting it. Pinning the platform-hook version becomes unnecessary, since 2026.10 is certainly ≥ whatever introduced it.

### 10.2 Graceful handling on older Core (the version window is 12 months wide)

**The floor is 2025.10.** The LLM tooling requires **2026.10**. That leaves **2025.10 through 2026.9 unsupported** — roughly twelve months of the install base, which is far too large a window to ignore or to hand-wave. This is not a corner case; it is most users on any given day.

**Therefore the LLM feature must be absent-but-harmless on older Core, and this has to be designed, not assumed.**

#### The hazard that makes this non-trivial

Core **< 2026.10 has no `probatio`** — it did not exist before the voluptuous replacement. So on older Core:

- **`import probatio` is an `ImportError`.** Because modules are imported at load time, a module-level probatio import does not merely disable the LLM feature — **it prevents the integration from loading at all**, breaking every existing user.
- **`from homeassistant.helpers.llm import ToolResult, ToolAnnotations` is an `ImportError`** for the same reason: those names do not exist yet.

This is the single most dangerous part of adopting the new contract, and it is easy to get wrong. A feature that fails closed is fine; a feature that takes the whole integration down is not.

#### Design rules

1. **Never import `probatio` in this integration.** Not in `llm.py`, not in `__init__.py`, not anywhere at module level. Everything the LLM tools need is reachable version-agnostically through `vol`:

   ```python
   import voluptuous as vol
   ```

   `vol.Schema`, `vol.Required`, `vol.Optional`, `vol.In` and `vol.Marker` all resolve correctly on **both** sides of the migration: real voluptuous on < 2026.10, and the probatio shim on ≥ 2026.10 (verified — the shim's top-level surface includes `Schema`, `Required`, `Optional`, `In` and `Marker`). **This is why `vol.Schema` is the correct choice for tool parameters, superseding the earlier recommendation to use `probatio.Schema`.**
2. **Do not import `ToolResult` or `ToolAnnotations` at module level.** Those imports must live inside the version guard so they are never evaluated on older Core. If a version-agnostic return shape is needed, return the plain-JSON form that is still supported until 2027.11 — but see rule 3.
3. **Fully gate the feature at 2026.10 — decided.** **No degraded pre-2026.10 LLM mode.** On Core older than 2026.10 the integration registers nothing LLM-related and exposes no MCP option. Rejected the alternative of serving read tools with plain-JSON returns on older Core: it would double the contract surface, forfeit the annotation safety flags the control tools depend on, and require separate tests. Full gate, single contract shape.
4. **Prefer Option B (owned `llm.API`) partly for this reason.** With Option A, the `llm` integration **auto-discovers and imports** `<integration>/llm.py` on every request — including on 2025.10, where a module-level probatio or `ToolResult` import would raise. With Option B we register the API ourselves inside the version guard, so on older Core **the module is never imported at all**. This is a concrete, independent argument for Option B on top of the opt-in and endpoint reasons in §6.
5. **Guard registration; never fail setup.** In `async_setup_entry`, register the LLM API only when the version check passes. The Firewalla features are unaffected by the version, so a hard failure would be wrong.
6. **Hide the option where unsupported.** The options flow must not offer MCP settings on older Core — showing a toggle that cannot work is worse than absent. Omit the fields, or skip the step.
7. **Log once, do not raise a repair.** A repair entry for "Core too old for an optional feature you cannot enable" is noise. One log line, and only when the user had previously enabled the option.
8. **Keep the guard in one place.** A single helper and constant in `const.py`, compared against `homeassistant.const.MAJOR_VERSION` / `MINOR_VERSION`:

   ```python
   MIN_LLM_TOOLS_HA_VERSION: Final = (2026, 10)


   def llm_tools_supported() -> bool:
       """Return whether this Core version supports LLM tools."""
       return (MAJOR_VERSION, MINOR_VERSION) >= MIN_LLM_TOOLS_HA_VERSION
   ```

9. **Tell the user, in text — via a README asterisk (decided).** Because the feature is simply absent on older Core, its requirement must be documented where users look. **Agreed treatment: an asterisk on the Home Assistant requirement line, resolved by a footnote.** Target text:

   ```markdown
   * **Home Assistant:** Requires Home Assistant Core version 2025.10 or newer.\*
   * **Network:** Your Home Assistant instance must be able to reach the Firewalla's local LAN IP.

   \* MCP / AI assistant tool support requires Home Assistant Core 2026.10 or newer.
   ```

   The USER_GUIDE MCP section should state the same requirement in prose.

   **Timing — important: this footnote lands with the MCP implementation, not before.** The README currently contains **no** MCP or AI-assistant content, because the feature does not exist. Adding the footnote now would advertise a capability that is not present, and a user already on 2026.10 would search for a setting that does not exist — a worse outcome than the missing note. The footnote and the USER_GUIDE section are therefore **Phase 4 deliverables**, shipped in the same change as the feature. Recording the exact wording here means the edit is trivial when the time comes.
10. **Test both paths.** Assert registration is attempted on 2026.10+, and that setup **completes successfully** with no LLM API registered and no MCP options offered on a simulated older version. The second test is the important one: it protects existing users from a load-time failure.
11. **Consider a nightly CI job against the floor.** Because the failure mode is an `ImportError` at load time on 2025.10, a build that only ever runs on latest will not catch it. A single matrix leg on 2025.10 (or a guard-completeness test asserting no module-level probatio/`ToolResult` import exists) is the durable protection.

### 10.3 Version floor — resolved: **2025.10**

`hacs.json` already declares `"homeassistant": "2025.10"`, and **2025.10 is the decision**. `README.md` previously contradicted it by stating 2026.3.0; **it now reads 2025.10** so the two agree. HACS enforces `hacs.json`, so aligning the README to it is the correct direction rather than raising the manifest.

Note the consequence this choice creates and confirms the need for §10.2: with a 2025.10 floor, the LLM feature is unavailable for **2025.10 → 2026.9**, which is most of the install base at any moment. Graceful handling is therefore a requirement, not an edge case.

### 10.4 Deprecation timeline to design against

| Deprecated | Warning until | Stops working |
|---|---|---|
| Returning plain JSON from a tool | 2027.11 | after 2027.11 |
| `ToolResultContent.tool_result` / setting `tool_result` on a delta | 2027.11 | after 2027.11 |
| Tool without `integration` (custom integrations) | 2027.10 | after 2027.10 |
| Unprefixed tool names | 2027.3 | after 2027.3 |

These are far enough out not to change the design, but they fix the boundary: **do not build the pre-2026.10 shape.**

## 11. Open questions to resolve before implementation

- Should `get_runtime_inventory` / `get_host_inventory` be exposed as tools at all, given they enumerate every device and user? (Ties to the Phase 1 inventory-read decision.)
- Is a `meta.units` block ever needed, or does the field-name convention make it redundant?
- **Alarm tools — now answerable from Phase 2's verified work.** The alarm surface is known, so the question is no longer "does it introduce a tool" but "which tier". See §12.
- Do tool messages need translation, given every other user-facing surface is translation-backed?
- Does the field-name audit risk changing any field an existing consumer reads? Verify before editing response fields.
- Should the MCP section live inside `docs/SURFACE_INVENTORY.md` or as a sibling doc that reuses its format?

## 12. Alarm surface — tiering (added 2026-09-30, from Phase 2 verification)

Phase 2 confirmed the complete alarm read and write API (see `docs/REVERSE_ENGINEERING_WORKFLOW.md` Findings 26–32). That makes the tool tiering straightforward, and the §5.1 rule applies directly:

**Read (Tier A — read-only, default on):**

| Proposed tool | Backs onto |
|---|---|
| `firewalla_local__get_alarms` | the Phase 2 alarm service — most recent 10 by default, `count` to widen |

The **default page size of 10 matters more here than for the websocket service.** A tool response is not just a payload, it is context: 243 alarms with ~50 keys each would be an enormous token load and would likely crowd out the user's actual question. Default 10 is the right number for an LLM, and the tool description should say the cap can be raised rather than leaving the model to assume it has everything.

**Control — tiered by the existing rule:**

| Tool | Tier | Reasoning |
|---|---|---|
| `set_alarm_muted` (mute / unmute) | **A** | Reversible — `alarm:unallow` works, verified |
| `block_alarm_target` (block / unblock) | **A** | Reversible — `alarm:unblock` removes the created rule, verified |
| `archive_alarm` | **B** | **Not reversible.** Verified that `unallow`/`unblock` do *not* un-archive, and no un-archive command exists. The description must state that the alarm stays in the archive permanently |
| `delete_alarm` | **C — exclude** | Irreversible, as `delete_host` |
| `ignore_all_alarms` / `delete_all_alarms` | **C — exclude from MCP** | **These ship as services** (owner decision) — admin-gated with a confirmation parameter. They are excluded from **MCP only**, and the reason is channel-specific: a bulk command returns `{}` whether or not it succeeded, and MCP has no confirmation channel, so an agent could neither confirm intent beforehand nor detect success afterwards. The `confirm` parameter helps a human caller but is a thin guard when a model fills it in. Users still reach them from automations and the UI |

**A note on the service-versus-tool distinction.** "Excluded from MCP" no longer implies "not built" — the bulk commands exist as services and are simply not exposed as tools. Expect this pattern to recur: a capability can be right for the service surface and wrong for an agent, and the two decisions should be recorded separately rather than collapsed.

**Two caveats the mute tool must carry in its description**, both from Phase 2 findings:

- **Scope is mandatory.** The integration must require an explicit scope (device / user / network / all). A default of `matchAll: 1` silently mutes a target for every device — verified live. An LLM left to choose would likely pick the broadest option.
- **Durations are the app's three fixed values** (1 hour / today / always). State them as an enum rather than accepting free text.
