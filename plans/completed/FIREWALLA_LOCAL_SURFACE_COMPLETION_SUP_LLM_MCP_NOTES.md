# Supporting note: Verified LLM / MCP facts (Phase 4 input)

## Purpose

Capture the facts verified against Home Assistant Core and the official developer documentation during the surface review, so Phase 4 does not re-research them.

**This note contains facts, not design.** Phase 4 is an investigation phase; no design decision is made here. Anything marked *unverified* must be re-checked before it is relied on.

## Verified in the local Core tree

- **`mcp_server` exists in Core** (`homeassistant/components/mcp_server/`) and is a **thin adapter over the Assist LLM API**. Its config flow presents a selector of `llm.async_get_apis(hass)` and stores the selected API ids; at runtime it lists that API's tools, forwards calls, and exposes one resource (`assist_context_snapshot`).
- **`mcp` is a separate, opposite integration** (`homeassistant/components/mcp/`) — it consumes external MCP servers *into* HA as an LLM API via `llm.async_register_api`. Do not conflate the two.
- **`llm.API` requires keyword-only `hass`, `id`, `name`.** `async_get_api_instance(llm_context)` returns an `APIInstance(api, api_prompt, llm_context, tools, custom_serializer=None)`.
- **`llm.Tool`** has `name` (required), `title`, `description`, `parameters` (`probatio.Schema` on 2026.10+), `annotations`, `integration`, and `async_call(...) -> ToolResult | JsonObjectType`. Errors must raise `HomeAssistantError` or a subclass; response data must be JSON-serializable.
- **Build tool parameter schemas with `vol.Schema`, not `probatio`.** `Tool.parameters` is typed `probatio.Schema` on 2026.10+, and Core's own LLM platforms import `probatio` directly — but **`probatio` does not exist before 2026.10**, while this integration's floor is **2025.10**. A module-level `import probatio` would raise `ImportError` and stop the integration from loading for existing users. `vol.Schema` is the version-agnostic choice: real voluptuous on < 2026.10 and the shim on ≥ 2026.10. Verified: `probatio/_vol_shim/_surface.py` includes `Schema`, `Required`, `Optional`, `In` and `Marker`.
- **Per-field parameter descriptions reach the LLM.** Verified in the installed `probatio` package: `probatio/codecs/openapi.py` does `if facets.description: pval["description"] = facets.description`, so a `description=` on any `vol.Required`/`vol.Optional` marker is emitted into the OpenAPI schema. `mcp_server._format_tool` copies `inputSchema["properties"]`, so those descriptions survive to the client.
- **The codec always emits `required`, but `mcp_server` discards it.** The `to_openapi` docstring states `required` is always present; `_format_tool` rebuilds the schema as `{"type": "object", "properties": ...}` and drops it. Consequence: an MCP client cannot see which parameters are required. State requiredness in each field's `description=` text.
- **`mcp_server` sets no tool annotations.** `_format_tool` produces only `name`, `description` and `inputSchema` — there is no `readOnlyHint`/`destructiveHint`/`idempotentHint`. Destructive vs. read-only must be conveyed in the tool name and description.
- **Tool names must be domain-prefixed.** `llm/__init__.py::_async_report_unprefixed_tools` reports tools whose names lack the `<domain>__` prefix, and `TOOL_PREFIX_BREAKS_IN_HA_VERSION = "2027.3"`.
- **The platform hook's `api_id` gating is real.** `homeassistant/components/homeassistant/llm.py::async_get_tools` returns `None` when `api_id != LLM_API_ASSIST`, demonstrating the supported pattern for contributing tools to only one API.
- **`LLMTools` lives in `components/llm/__init__.py`**, not `helpers/llm.py`: `LLMTools(tools: list[Tool], prompt: str | None = None)`. The component-level `async_get_tools` iterates every registered platform (sorted by domain for stable order), joins non-empty prompts with `"\n"`, and swallows platform exceptions with a logged error.
- **`ActionTool` is not a shortcut.** A code comment states `_get_cached_action_parameters` only works for services that populate the service description cache, which is mainly scripts. Explicit `Tool` subclasses are the expected path and produce better tool calls than inferred schemas.
- **`ToolCall` response convention is `{"success": bool, "result": ...}`.** Used by `ActionTool`, `GetLiveContextTool` and relied on by `mcp_server.handle_read_resource`. The base `Tool` class does not enforce it — it is convention, not a contract.
- **Assist attribute exposure is restricted.** `components/homeassistant/llm.py` passes only a hardcoded allowlist of "interesting attributes" — approximately `temperature`, `current_temperature`, `temperature_unit`, `brightness`, `humidity`, `unit_of_measurement`, `device_class`, `current_position`, `percentage`, `volume_level`, `media_title`, `media_artist`, `media_album_name`. **Rich custom attributes (network usage, top talkers, alarm detail) do not reach an LLM through `GetLiveContext`.** This is why exposing services as tools matters more than exposing entities alone.
- **REST is unfiltered by contrast.** `homeassistant/core.py::State.attributes` is a full `ReadOnlyDict[str, Any]` serialized by `as_dict`, so the REST `/api/states` payload includes **all** attributes. Relevant to the surface-inventory documentation phase and to any external consumer reading HA directly.

## Verified from the official developer documentation

## Verified from the official developer documentation

### Version timeline (researched)

| Capability | Version | Source |
|---|---|---|
| `llm.async_register_api`, LLM APIs, `llm.Tool`, `llm.APIInstance` | **2024.6** | Blog, May 20 2024 — *"Exposing Home Assistant API to LLMs"* |
| `mcp_server` integration | **2025.2** | Integration docs page states it was introduced in 2025.2 |
| `llm.ToolResult`, `llm.ToolAnnotations`, `Tool.title`, `Tool.integration`; MCP serves title + annotations | **2026.10** | Blog, Sept 26 2026 — *"LLM tools return a ToolResult and declare their integration"* |
| `LLMTools` + the `llm.py` platform hook (`async_get_tools`) | **not pinned** — no developer blog post found | — |
| Per-API MCP endpoints `/api/mcp/<api_id>` | **not pinned** — documented without a version | — |

**Important caveat about the local checkout — now resolved.** The earlier reading of this tree predated the 2026.10 merge, so it did **not** contain `ToolResult`, `ToolAnnotations`, `title` or `integration`. Core has since been updated to **2026.10.0.dev0**, and all of those now exist. The tree and the blog now agree. Details and evidence: `FIREWALLA_LOCAL_SURFACE_COMPLETION_SUP_CORE_2026_10_CHANGES.md`.

### Tool contract (Core 2026.10+)

- `async_call` returns **`llm.ToolResult(data=..., error=...)`**. Returning plain JSON is **deprecated** — works with a warning for custom integrations until **2027.11**, stops after.
- `ToolResultContent.tool_result` is replaced by `ToolResultContent.result`; setting `tool_result` on a delta is also deprecated on the same timeline.
- `Tool` gains **`title`** (human-readable), **`annotations`**, and **`integration`**.
- `llm.ToolAnnotations` has four flags: `read_only`, `destructive`, `idempotent`, `open_world`. **"The defaults describe the least safe case, so a tool that declares nothing is taken to write, to be destructive, and to reach outside Home Assistant."**
- **"The MCP Server integration serves the title and the annotations to MCP clients."** Confirmed in the updated tree: `_format_tool` maps all four flags to MCP `readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`, and preserves `inputSchema["required"]`.
- **Tool schemas must use `vol.Schema`, not `probatio`.** Core's LLM platforms use `probatio` internally, and `Tool.parameters` is typed `probatio.Schema` on 2026.10+. But **`probatio` does not exist before 2026.10**, so a module-level `import probatio` in a custom integration would raise `ImportError` and stop the integration from loading on older Core. `vol.Schema` is the version-agnostic choice: real voluptuous on < 2026.10, and the probatio shim on ≥ 2026.10 (`homeassistant/__init__.py` calls `install_as_voluptuous()`). Verified: the shim's top-level surface includes `Schema`, `Required`, `Optional`, `In` and `Marker`.
- A tool created without `integration` is deprecated: a **custom integration gets a warning until 2027.10** and stops working after.
- Tool names must be `<domain>__`-prefixed (`TOOL_PREFIX_BREAKS_IN_HA_VERSION = "2027.3"`).

### Integration mechanics

- **Two supported ways to contribute LLM functionality:**
  - **Option A — `llm.py` platform hook.** An integration ships `<integration>/llm.py` exposing `async_get_tools(hass, llm_context, api_id) -> llm.LLMTools | None`. The `llm` integration discovers it lazily and calls it **per request**; it returns tools plus an optional prompt fragment, or `None` when the integration contributes nothing. The integration does not own an API, does not touch the config flow, and does not depend on `llm` at import time.
  - **Option B — owned API.** Register via `llm.async_register_api(hass, MyAPI(hass=..., id=..., name=...))` and unregister with `entry.async_on_unload(...)`. Gives a separately selectable API with its own prompt.
- **MCP exposure is automatic and requires no extra work:** *"You do not need to do anything special to make your API available over MCP. Once the user sets up the MCP Server integration, every registered LLM API is automatically served over MCP."* Each API is served at `/api/mcp/<API ID>`.
- **Auth is supplied by HA:** per-API MCP endpoints **require an admin access token, except for the Assist API**. The MCP Server integration also exposes a single configured API at `/api/mcp` for clients that do not target an API by id.
- **API enumeration:** `llm/api/list` over the WebSocket API returns every registered API's `id` and `name`, in registration order, and **requires an admin user**.
- **The built-in Assist API performs no administrative tasks** and mirrors the capabilities of the built-in conversation agent.

## Corrections to earlier analysis (do not repeat these mistakes)

- **`zwave_js` and `matter` are not LLM API precedents.** Both define their own local `async_register_api(hass)` that registers **websocket commands**, unrelated to LLMs. A name-collision grep artifact. Only `llm` and `mcp` call `llm.async_register_api` in Core.
- **ID/path-traversal validation does not transfer from the MCP server.** That project validates ids because MSP is REST with ids in **URL paths**. Our transport is `http://{host}:8833/v1/encipher/message/{gid}`, where `{gid}` comes from pairing credentials and never from user input, and every other value travels in an encrypted JSON body. There is no user-controlled path segment to protect.

## Open questions carried into implementation

The Phase 4 investigation is complete; decisions and the remaining open questions live in `FIREWALLA_LOCAL_SURFACE_COMPLETION_SUP_LLM_MCP_INVESTIGATION.md` §11. This note stays a facts-only reference.
- What translation and error-message coverage do tools need to match the rest of the integration?
