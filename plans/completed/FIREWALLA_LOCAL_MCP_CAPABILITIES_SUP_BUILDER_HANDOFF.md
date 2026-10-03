# Builder handoff: MCP capabilities — Phase 4.1 (foundation & older-Core safety)

**Target agent:** `Firewalla Builder`
**Plan:** `plans/completed/FIREWALLA_LOCAL_MCP_CAPABILITIES_COMPLETED.md` (initiative: MCP Capabilities / LLM tool surface)
**Spec:** `docs/MCP_TOOL_REFERENCE.md`

## Purpose

Implementation-ready handoff to **start the MCP capabilities initiative at Phase 4.1** — the LLM/MCP tool foundation and the older-Core safety proof. This handoff removes ambiguity, prevents architecture drift, and defines completion so it can be verified rather than inferred.

This handoff authorizes **Phase 4.1 only**. Phases 4.2–4.5 follow per the plan, handed off after 4.1 is done and validated. Do not start tool implementation (4.2+) in this pass.

## Step 0 — create the feature branch (do this FIRST)

Per `CONTRIBUTING.md`, work happens on a feature branch off `main`, merged back via PR to `main`.

```bash
git checkout main
git pull
git checkout -b feature/mcp-capabilities
```

Confirm the branch is created and checked out before touching any code. (Adjust the branch name only if a naming conflict exists; keep it descriptive and `feature/`-prefixed.)

## Scope — Phase 4.1

1. **Version guard** — split across two modules so `api/` stays clean:
   - `custom_components/firewalla_local/const.py`: `MIN_LLM_TOOLS_HA_VERSION: Final = (2026, 10)` **only** (a pure tuple — no `homeassistant` import; `const.py` is imported by `api/`).
   - `custom_components/firewalla_local/helpers/llm_support.py` (new): `llm_tools_supported() -> bool` comparing `(MAJOR_VERSION, MINOR_VERSION)` imported from `homeassistant.const`. `api/` must never import this module.
2. **`llm_api.py`** — the API class shell only (**no tools yet**). **NOT `llm.py`**: that filename is HA's integration-platform hook, auto-imported by the `llm` integration outside our guard (verified — `components/llm/__init__.py` registers the `"llm"` platform; `loader.platforms_exists()` discovers it by filename). `llm_api.py` is not auto-imported.
   - `FirewallaLocalAPI(llm.API)` with `async_get_api_instance` returning an empty tool list + the prompt placeholder.
   - API id strategy: bare `firewalla_local` for the sole entry; `firewalla_local-<slugified title>` beyond, `-<entry_id[:8]>` on slug collision; `name` stays the friendly entry title. Document the chosen id in a comment/docstring.
   - Keep every `homeassistant.helpers.llm` import **inside** `llm_api.py` (which is itself guard-loaded), so older Core never imports `ToolResult`/`ToolAnnotations`.
3. **Guarded registration + unload** in `__init__.py`:
   - Register the API in `async_setup_entry` **only inside the `llm_tools_supported()` guard**, importing `llm_api` lazily inside that branch.
   - `entry.async_on_unload(unsub)`; must unregister on unload and not leak across reloads.
   - Do **not** import `llm` or `llm_api` at module top level in `__init__.py`.
4. **Options toggle** — a single three-state select (Off / Read only *(default)* / Read and control), **hidden entirely when `llm_tools_supported()` is False**.
5. **Older-Core safety proof tests** (the gate that protects existing users):
   - Guard unit test at/below/above `(2026, 10)` — patch the **integration's** `MAJOR_VERSION`/`MINOR_VERSION` binding.
   - Mocked-helper wiring test: with `llm_tools_supported()` → `False`, setup **succeeds**, `async_register_api` is **not** called, and no MCP option is offered.
   - **Static AST test**: no module-level `import probatio` and no module-level `from homeassistant.helpers.llm import ...ToolResult/ToolAnnotations...` in any unconditionally-loaded module.

## Source of truth

If this handoff conflicts with these, **the plan and docs win**:

1. `docs/MCP_TOOL_REFERENCE.md` (spec — tool shapes, conventions)
2. `plans/completed/FIREWALLA_LOCAL_MCP_CAPABILITIES_COMPLETED.md` §4.1 (and §3 constraints)
3. `custom_components/firewalla_local/quality_scale.yaml`, `docs/DEVELOPMENT_STANDARDS.md`
4. this handoff

## Non-negotiable guardrails

- **Do NOT raise the integration's Home Assistant floor.** `hacs.json` stays `2025.10`. The LLM feature is simply absent on older Core.
- **Use `vol.Schema` / `vol.Required` / `vol.Optional` / `vol.In` everywhere** (resolves on both sides of the voluptuous→probatio migration). **Never `import probatio`** — it does not exist before 2026.10 and would break every existing user at load time.
- **No eager `llm` imports at module scope** in any unconditionally-loaded module, and **do not name the API module `llm.py`** (HA's integration-platform filename — auto-imported outside the guard). A module-level `ImportError` breaks the whole integration on 2025.10–2026.9 and a latest-only CI run will never catch it (hence the AST test).
- **Guard registration; never fail setup.** On unsupported Core, `async_setup_entry` completes normally with no LLM API registered and no option shown. One log line at most — **no repair issue**.
- **No tools in this pass** beyond the empty API shell. Tool implementation is Phase 4.2+.
- No production behavior change for existing users on any supported Core version.

## Required implementation order

1. `git checkout -b feature/mcp-capabilities` (Step 0).
2. Version constant in `const.py` + predicate in `helpers/llm_support.py`.
3. `llm_api.py` API shell (empty tools, lazy import).
4. Guarded registration + unload in `__init__.py`.
5. Options toggle (hidden when unsupported).
6. Older-Core safety tests (guard unit, mocked wiring, static AST).
7. Run validation; stop.

## Done criteria (Phase 4.1 complete only when all hold)

- [ ] Feature branch `feature/mcp-capabilities` created off `main`.
- [ ] `llm_tools_supported()` present in `helpers/llm_support.py` and correct at/below/above the boundary; `MIN_LLM_TOOLS_HA_VERSION` in `const.py` with no `homeassistant` import.
- [ ] `llm_api.py` API shell registers/deregisters cleanly; no tool implementation yet.
- [ ] Setup succeeds with **no** LLM API and **no** option on a simulated pre-2026.10 Core.
- [ ] Static AST test passes: no module-level `probatio` / `ToolResult` / `ToolAnnotations` import.
- [ ] Options toggle hidden when unsupported.
- [ ] Validation green (below).

## Validation

```bash
python -m ruff check .
python -m ruff format .
python -m mypy custom_components/firewalla_local
python -m pytest tests/ -v
```

Baseline before this work: **319 tests pass**, ruff/format/mypy clean. All Phase 4.1 tests are new coverage; nothing regresses.

## After Phase 4.1

Report back with results, then the initiative continues per the plan: **4.2 read tools → 4.3 control tools → 4.4 prompt + contract tests → 4.5 tests/docs/disclosure** (each handed off separately, built to `docs/MCP_TOOL_REFERENCE.md`). If any guardrail here would force a design change, stop and ask rather than deciding unilaterally.
