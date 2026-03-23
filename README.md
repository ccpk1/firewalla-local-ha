# Firewalla Home Assistant Scaffold

This repository is a private starter scaffold for a Firewalla Home Assistant
custom integration.

It is intentionally small. The goal is to start with the minimum structure that
keeps the codebase clean, typed, translation-ready, and easy to grow toward Home
Assistant platinum quality.

## What is in place

- Standalone custom component repository layout
- Separate VS Code workspace that opens this repo with Home Assistant Core
- Link target for `core/config/custom_components/firewalla`
- UI config flow scaffold
- Typed runtime data and coordinator scaffold
- Diagnostics scaffold
- English translations from day one
- Quality scale tracking file
- Minimal test scaffold

## What is not implemented yet

- Real Firewalla API communication
- Entities and platforms
- Reauthentication and options flow
- Integration-specific tests beyond scaffold coverage

## Repository layout

```text
custom_components/firewalla/
tests/components/firewalla/
firewalla-dev.code-workspace
pyproject.toml
```

## Local development

Use the workspace file:

```text
/workspaces/firewalla-ha/firewalla-dev.code-workspace
```

The workspace includes Home Assistant Core and an auto-link task for:

```text
/workspaces/core/config/custom_components/firewalla
```

## Suggested next implementation order

1. Replace the placeholder client in `api.py` with the real Firewalla transport
2. Add one platform, likely diagnostics-first sensors or device tracker data
3. Add config flow connection testing and reauthentication
4. Add integration tests around setup, diagnostics, and entity behavior
5. Tighten the quality scale checklist as features land