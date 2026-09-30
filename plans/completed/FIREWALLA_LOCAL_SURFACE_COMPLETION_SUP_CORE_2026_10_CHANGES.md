# Supporting note: Core 2026.10 platform changes affecting Firewalla Local

## Purpose

Record what changed in the Home Assistant Core update and what it means for this repository.

**Status: verified — no regressions from the Core 2026.10 update.** Ruff, mypy and pytest all pass on the updated Core. See §6 for exactly what was run and what the result does and does not establish.

This note was originally written from source inspection alone (terminal execution was unavailable at the time); §6 now carries the confirmed results.

## 1. Core version confirmed

`homeassistant/const.py`:

- `MAJOR_VERSION = 2026`, `MINOR_VERSION = 10`, `PATCH_VERSION = "0.dev0"` → **2026.10.0.dev0**
- `REQUIRED_PYTHON_VER = (3, 14, 2)`

So the updated tree **is** the 2026.10 dev line, and it now matches the developer blog posts consulted earlier.

## 2. The 2026.10 LLM tool APIs are now present

Previously the checkout predated these; they now exist in `homeassistant/helpers/llm.py`:

| Symbol | Detail |
|---|---|
| `llm.ToolResult` | `@dataclass(slots=True)`; `data: JsonObjectType`, `error: bool = False` |
| `llm.ToolAnnotations` | `@dataclass(frozen=True, slots=True, kw_only=True)`; `read_only=False`, `destructive=True`, `idempotent=False`, `open_world=True` |
| `Tool.title` | `str \| None = None` |
| `Tool.annotations` | `ToolAnnotations` |
| `Tool.integration` | `str \| None = None` |
| `Tool.parameters` | **`probatio.Schema`** (was `vol.Schema` in the earlier checkout) |
| `Tool.async_call` | Returns `ToolResult \| JsonObjectType` |
| `TOOL_INTEGRATION_BREAKS_IN_HA_VERSION` | `"2027.10"` |

The `ToolAnnotations` docstring confirms the default-safety rule verbatim: *"The defaults describe the least safe case, so a tool that declares nothing is taken to write, to be destructive, and to reach outside Home Assistant."*

## 3. `mcp_server` now serves title, annotations and `required`

`homeassistant/components/mcp_server/server.py::_format_tool` now:

- calls `probatio.to_openapi(..., openapi_version="3.1.0")`
- sets `name`, **`title`**, `description`
- **preserves `required`**: `if required := input_schema.get("required"): mcp_schema["required"] = required`
- maps all four annotation flags to MCP: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`

**Three earlier findings are superseded:** annotations *are* available; `required` *is* machine-visible; and `title` is served. The safety design no longer depends on prose alone, and parameter requiredness need not be restated as text.

## 4. Voluptuous → probatio migration (the notable platform change)

Home Assistant has **replaced voluptuous with probatio** as its validation engine.

- `requirements.txt` lists **`probatio==0.12.4`** and **no voluptuous**.
- `voluptuous` is **not installed** in the venv.
- `homeassistant/helpers/typing.py`: `type VolSchemaType = probatio.Schema | probatio.All | probatio.Any`.
- `homeassistant/helpers/service.py` imports `probatio`, not `voluptuous`, and uses `probatio.Schema({}, extra=probatio.PREVENT_EXTRA)`.

### Why our code still works

`homeassistant/__init__.py` performs the alias before anything imports voluptuous:

```python
from probatio.compat import install_as_voluptuous

install_as_voluptuous()
```

with the comment: *"Custom integrations and a few dependencies still import voluptuous directly, so alias it to probatio in sys.modules before anything imports it."*

`probatio._vol_shim` documents the same: it registers the shim modules in `sys.modules` under the `voluptuous` name.

### Impact on this repository

Two files import voluptuous: `config_flow.py` and `services.py`, both `import voluptuous as vol`. Symbols used: `vol.Schema`, `vol.Required`, `vol.Optional`, `vol.In`, `vol.All`, `vol.Marker` — all top-level voluptuous surface, which the shim re-exports. **Conclusion: no breakage.**

### Guidance going forward

- **Existing service and config-flow schemas: keep `vol.Schema`.** It resolves through the shim and changing it is unnecessary churn.
- **New LLM tool schemas: also use `vol.Schema`.** *(Corrected — an earlier version of this note said to use `probatio`.)* `probatio` **does not exist before Core 2026.10**, so importing it in a custom integration raises `ImportError` and prevents the integration from loading on older Core — where the floor is 2025.10. `vol.Schema` / `vol.Required` / `vol.Optional` / `vol.In` work on **both** sides of the migration: real voluptuous on < 2026.10, and the shim on ≥ 2026.10. Verified: `probatio/_vol_shim/_surface.py` includes `Schema`, `Required`, `Optional`, `In` and `Marker` in its top-level surface.
- **Never import `probatio` anywhere in this integration.** The only safe variable name is `vol`.
- **Watch for a future removal of the alias.** The shim exists for compatibility; if it is withdrawn, the two `import voluptuous as vol` lines become the migration work. Worth a periodic check rather than action today.

## 5. Other imports verified against the updated Core

Checked because the integration depends on them:

| Import | Status |
|---|---|
| `async_register_admin_service` (`homeassistant.helpers.service`) | present (line 992) — **Phase 1 depends on this** |
| `ServiceResponse`, `EntityServiceResponse`, `SupportsResponse` (`homeassistant.core`) | present |
| `JsonObjectType`, `JsonValueType` (`homeassistant.util.json`) | present |
| `HAView.context()` → `Context(user_id=...)` | unchanged; the admin-gate chain still holds |

## 6. Verification — complete and passing

**All checks pass on the updated Core (2026.10.0.dev0). Result: 290 passed.**

| Check | Command | Result |
|---|---|---|
| Lint | `python -m ruff check .` | ✅ pass |
| Format | `python -m ruff format .` | ✅ pass |
| Types | `python -m mypy custom_components/firewalla_local` | ✅ pass |
| Tests | `python -m pytest tests/ -v` | ✅ **290 passed** |

### What this establishes

- **The probatio shim works at runtime, not just statically.** The open question in the previous version of this note was whether `vol.Schema` semantics were preserved under the shim — defaults, `vol.All` chaining, `vol.In` with tuples, and error shapes. The suite exercises every service schema in `services.py` and the config-flow schemas in `config_flow.py`, and all pass. **The shim is sufficient; no schema migration is required.**
- **No regressions from the Core update.** 290 tests passing on 2026.10.0.dev0 means the update is safe to build on.
- **The Phase 1 dependency is sound.** `async_register_admin_service` is present and intact on the updated Core.

### What this does not establish

- **No LLM-tool code exists yet**, so nothing here validates `ToolResult`, `ToolAnnotations`, `probatio.Schema` tool parameters, or version gating. Those remain unproven until Phase 4 implementation, and its tests must cover them.
- **Static pass ≠ semantic equivalence in general.** The suite covers the schemas we actually use; it does not prove every voluptuous behaviour is identical under probatio. New schema constructs introduced later should be assumed to need their own test coverage.

## 7. Recommended follow-up

1. ~~**Run the four commands above** and report results.~~ **Done — 290 passed (§6).**
2. ~~**Fix the version-floor inconsistency.**~~ **Resolved — the floor is 2025.10**, and `README.md` now matches `hacs.json`.
3. **Adopt the 2026.10 tool contract in Phase 4** — `ToolResult`, `ToolAnnotations`, `title`, `integration`, with **`vol.Schema`** for parameters.
4. **Never import `probatio` or `ToolResult`/`ToolAnnotations` at module level.** The floor is 2025.10, and `probatio` does not exist before 2026.10, so a module-level import would stop the integration from loading. See §10.2 of the investigation note.
