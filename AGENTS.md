# Firewalla HA Agent Guide

This repository is a standalone Home Assistant custom integration for Firewalla.

## Mission

- Keep the repo standalone. Do not move logic into other repositories.
- Keep the architecture minimal, typed, and translation-ready.
- Aim for Home Assistant platinum-quality patterns without importing ChoreOps complexity unless the codebase actually needs it.
- Use Home Assistant Core in the workspace for runtime validation only. Do not make unrelated changes under `/workspaces/core`.

## First files to inspect

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `pyproject.toml`
- `custom_components/firewalla_local/manifest.json`
- `custom_components/firewalla_local/config_flow.py`
- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/api/`
- `custom_components/firewalla_local/quality_scale.yaml`
- `tests/conftest.py`

## Source map

- Integration code: `custom_components/firewalla_local/`
- Tests: `tests/components/firewalla_local/`
- Shared pytest setup: `tests/conftest.py`
- Translations: `custom_components/firewalla_local/translations/en.json`
- Quality tracking: `custom_components/firewalla_local/quality_scale.yaml`
- Plans: `plans/in-process/`

## Implementation rules

- Prefer the smallest change that solves the real problem.
- Keep runtime typing clean and explicit.
- Keep user-facing strings translation-ready from day one.
- Extend the scaffold in-place before introducing new layers or helper modules.
- Be honest in `quality_scale.yaml`; mark `todo` or `exempt` until behavior actually exists.
- Do not guess the Firewalla protocol. Confirm the transport, authentication, and response contract first.

## Validation commands

Run these in this repository unless the task clearly does not affect code:

```bash
python -m ruff check .
python -m ruff format .
python -m mypy custom_components/firewalla_local
python -m pytest tests/ -v
```

For focused work, narrower pytest scopes are allowed during iteration, but the final report should say what was and was not run.

## Planning convention

- Main plans live in `plans/in-process/`.
- Main plan name: `INITIATIVE_NAME_IN-PROCESS.md`
- Supporting notes: `INITIATIVE_NAME_SUP_[DESCRIPTOR].md`
- Plans should be executable, phase-based, and reference concrete files.
- Durable architecture and standards guidance belongs in `docs/`, not inside planning files.

## Definition of done

- Code is minimal and coherent with existing scaffold patterns.
- Typing remains strict.
- Translations stay ready.
- Validation results are reported clearly.
- Any open protocol assumptions, auth gaps, or follow-up work are called out explicitly.