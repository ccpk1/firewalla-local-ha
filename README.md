[![HACS Custom](https://img.shields.io/static/v1?label=HACS&message=custom&color=1E88E5&labelColor=555)](https://github.com/custom-components/hacs)
[![License](https://img.shields.io/static/v1?label=License&message=GPL-3.0&color=1E88E5&labelColor=555)](https://github.com/ccpk1/firewalla-local-ha/blob/main/LICENSE)
[![Version](https://img.shields.io/github/v/release/ccpk1/firewalla-local-ha?include_prereleases&label=Version&color=1E88E5)](https://github.com/ccpk1/firewalla-local-ha/releases)
[![Stars](https://img.shields.io/github/stars/ccpk1/firewalla-local-ha)](https://github.com/ccpk1/firewalla-local-ha/stargazers)

![Firewalla Local](docs/assets/logo.png)

# Firewalla Local

Firewalla Local is a standalone Home Assistant custom integration for Firewalla.

It pairs with your Firewalla box using the Firewalla app QR payload, connects to
the local box over the verified local protocol, and exposes a deliberately small
set of Home Assistant surfaces built around proven runtime behavior.

## What it supports today

- UI config flow with local runtime validation before entry creation
- Reauthentication flow with fresh QR input
- Reconfigure flow for host updates
- Options flow for selected rule-backed switches
- Rule-backed switch platform for the currently supported rule subset
- Runtime inventory, pause, and resume services
- Diagnostics with redaction coverage
- English translations and typed runtime data from day one

## Current boundaries

- Only a supported subset of Firewalla rules can be exposed as Home Assistant switches
- Broader rule-family mutation support beyond the current switch-backed slice is not implemented yet
- Discovery is not implemented yet
- This integration does not attempt speculative fallback behavior outside the proven local protocol path

## ❤️ Support the Project

If Firewalla Local provides value to you, here are a few ways you can fuel its development and prevent open-source burnout!

⭐ **Star this repository!**
If you like this integration, the best (and free!) thing you can do is click the Star button at the top of this page. It helps other users discover the project and builds trust as we grow.

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/ccpk1)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/ccpk1)


## Quick installation

### One-click HACS install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ccpk1&repository=firewalla-local-ha&category=integration)

### Manual HACS setup

1. Ensure HACS is installed.
2. In Home Assistant, open **HACS -> Integrations -> Custom repositories**.
3. Add `https://github.com/ccpk1/firewalla-local-ha` as an **Integration** repository.
4. Search for **Firewalla Local**, install it, and restart Home Assistant.
5. Open **Settings -> Devices & Services -> Add Integration**.
6. Choose **Firewalla Local** and complete the QR-based pairing flow.

## User guide

The minimal user-facing operating guide lives in `docs/USER_GUIDE.md`.

It covers:

- installation and removal
- pairing expectations
- refresh behavior
- the rule-backed switch surface
- runtime inventory, pause, and resume services

## Security and support posture

- Vulnerability reporting guidance lives in `SECURITY.md`
- The high-level security approach, trade-offs, and awareness notes live in `docs/ARCHITECTURE.md`
- This repository should not be treated as an official Firewalla integration or as a Firewalla support channel

## Disclaimer

This is an independent community project. It is not affiliated with, endorsed by,
or supported by Firewalla.

Use it at your own risk.

## Development and architecture docs

The durable project rules live in:

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/QUALITY_REFERENCE.md`

Repository layout:

```text
custom_components/firewalla_local/
tests/components/firewalla_local/
docs/
firewalla-dev.code-workspace
pyproject.toml
```

## Community and contribution

- Issues and feature requests: https://github.com/ccpk1/firewalla-local-ha/issues
- Discussions: https://github.com/ccpk1/firewalla-local-ha/discussions
- Pull requests: https://github.com/ccpk1/firewalla-local-ha/pulls

## License

This project is licensed under the GPL-3.0 license. See `LICENSE`.