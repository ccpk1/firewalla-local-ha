# Firewalla Local Home Assistant integration

This repository is a standalone Home Assistant custom integration project for
Firewalla.

It is an independent community project. It is not affiliated with, endorsed
by, or supported by Firewalla.

Use it at your own risk.

It is intentionally small. The goal is to start with the minimum structure that
keeps the codebase clean, typed, translation-ready, and easy to grow toward Home
Assistant platinum quality.

The durable project rules now live in:

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`

## Security and support posture

- Vulnerability reporting guidance lives in `SECURITY.md`
- The high-level security approach, trade-offs, and awareness notes live in
	`docs/ARCHITECTURE.md`
- This repository should not be treated as an official Firewalla integration
	or as a Firewalla support channel

## What is in place

- Standalone custom component repository layout
- Separate VS Code workspace that opens this repo with Home Assistant Core
- Link target for `core/config/custom_components/firewalla_local`
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
custom_components/firewalla_local/
tests/components/firewalla_local/
docs/ARCHITECTURE.md
docs/DEVELOPMENT_STANDARDS.md
firewalla-dev.code-workspace
pyproject.toml
```

## Local development

Use the workspace file:

```text
/workspaces/firewalla-local-ha/firewalla-dev.code-workspace
```

The workspace includes Home Assistant Core and an auto-link task for:

```text
/workspaces/core/config/custom_components/firewalla_local
```

## Suggested next implementation order

1. Replace the placeholder client with the pure `api/` submodule and real local transport
2. Add initial pairing, options flow, and reauthentication behavior
3. Add rule-backed entities and coordinator-driven state updates
4. Add timed rule pause service support
5. Expand integration tests around setup, diagnostics, reauth, services, and entity behavior