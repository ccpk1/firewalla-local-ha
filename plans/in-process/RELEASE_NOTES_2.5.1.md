# Firewalla Local 2.5.1

## Summary

2.5.1 is a maintenance release. No service, entity, attribute, MCP tool, or config-flow
behaviour differs from 2.5.0, so upgrading needs no config entry change, no re-pairing,
and nothing checked first. Three internal changes landed:

- a test that pins the contract every assistant tool's `parameters` must satisfy
- a rename of the validation import in the two assistant tool modules
- the `ai-humanizer` writing skill, as repository tooling

## A guard for the assistant tool schemas

Every LLM tool declares its inputs as a `parameters` schema. Home Assistant renders a
tool by reading that schema's field mapping, and the Google Generative AI agent reads it
on every turn. Only a schema object has that attribute, so composing a cross-field rule
*around* the schema rather than inside it produces a tool that raises before the model is
called, for every conversation rather than for the one tool.

A sibling integration hit that failure. Firewalla Local was audited and is not affected:
all 39 tools declare `vol.Schema({...})`, none composes a rule at the top level, and none
casts the type. That audit is now a test,
`test_every_tool_parameters_expose_a_field_mapping`, which asserts that each registered
tool's `parameters` exposes the field mapping. It rejects a rule composed around the
schema, and it also rejects a schema nested in another schema, since the second looks
right but reports a schema where a mapping is expected. No tool needed changing to
satisfy it.

## Import renamed in the two assistant tool modules

`llm_tools_read.py` and `llm_tools_control.py` now import `probatio` directly. Home
Assistant aliases `voluptuous` to probatio when it loads, so the two names were already
the same object and runtime behaviour is unchanged. The source now names the type
`Tool.parameters` is annotated with.

The config-flow and service modules keep `voluptuous` on purpose. They are imported on
every Home Assistant version, including releases before 2026.10 that predate probatio,
whereas the two renamed modules load only from 2026.10 onwards.

## Repository tooling

The `ai-humanizer` skill is committed under `.claude/skills/ai-humanizer/`, with its
pattern catalogue in `references/patterns.md`. It rewrites developer prose that reads as
machine-written without changing a fact, and applies to the text this repository
produces: release notes, pull request descriptions, and commit messages. It is tooling
for the repository and does not touch the integration.

## Validation

Run on this release commit:

```bash
bash ./utils/quick_lint.sh
python -m mypy custom_components/firewalla_local
python -m pytest tests/ -v
```

- Ruff lint and format: clean.
- MyPy, strict: no issues in 46 source files.
- Pytest: 829 passed.

Not run, and deferred to the release process in `docs/RELEASE_CHECKLIST.md`: hassfest and
the HACS validator.

### ❤️ **Support the Project**

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/ccpk1)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/ccpk1)

## Upgrading

Install version **2.5.1** from HACS, then restart Home Assistant. Nothing else is needed
and no re-pairing is required.

If you use the AI assistant tools, they still need Home Assistant Core 2026.10 or newer.
On older Core the integration works exactly as before and the setting stays hidden.
