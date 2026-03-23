# Firewalla Local development standards

## Purpose

This document defines the prescriptive coding standards for the Firewalla Local integration.

The goal is to keep the implementation strict, maintainable, Home Assistant-friendly, and aligned with the architecture contract.

## Naming baseline

- Product name: `Firewalla Local`
- Integration domain: `firewalla_local`
- Pure protocol boundary: `custom_components/firewalla_local/api/`

## General rules

- Prefer the smallest coherent change that solves the real problem
- Keep typing explicit and complete
- Keep user-facing behavior translation-ready from day one
- Do not mix protocol work with Home Assistant orchestration
- Do not add fallback identity schemes or fallback crypto libraries

## Constants taxonomy

Use explicit constants instead of scattered literals.

Approved constant families:

- `DOMAIN`
- `CONF_*`
- `DEFAULT_*`
- `ATTR_*`
- `SERVICE_*`
- `SERVICE_FIELD_*`
- `TRANS_KEY_*`
- flow step constants once flow complexity justifies them

## Type system

- All public and internal functions must be type hinted
- Use modern Python typing syntax
- Prefer narrow exception types
- Use dataclasses, enums, and `TypedDict` when they clarify structure
- Avoid untyped dictionaries for stable protocol or config shapes when a stronger type is available

## Module boundaries

### Integration root

Files in `custom_components/firewalla_local/` own:

- Home Assistant config entry behavior
- flows and reauth
- coordinator logic
- entity definitions
- diagnostics integration
- translation-aware user-facing exceptions

### Pure API submodule

Files in `custom_components/firewalla_local/api/` own:

- cryptography
- signing
- HTTP transport
- protocol parsing
- API-specific exception types

Rules:

- nothing inside `api/` may import `homeassistant.*`
- `api/` must not become a single-file monolith
- separate crypto, auth, client, and transport concerns when implementation begins

## Async and event loop rules

- All network requests in `custom_components/firewalla_local/api/` must use `aiohttp`
- The `requests` library is strictly forbidden
- Do not perform blocking I/O in the Home Assistant event loop
- Cryptographic operations that are CPU-bound, including RSA key generation and PKCS#8 or SPKI serialization through `cryptography`, must be offloaded with `hass.async_add_executor_job()` when triggered from async Home Assistant code such as config flows
- Keep executor usage tightly scoped to the CPU-bound cryptographic work; normal integration orchestration remains async-native

## Identity and device registry rules

- The Home Assistant device registry identity must use the immutable `license` value from the QR payload
- `gid` must never be used as the device registry identifier
- IP addresses and hostnames must never be used as unique IDs
- Entity unique IDs must remain stable under re-pairing and network changes
- No floating entities: all entities must attach to the correct Firewalla device registry entry derived from `license`

## Entity naming standards

- All entities must set `_attr_has_entity_name = True`
- Entity names must never embed the device name
- Home Assistant handles device-name concatenation in the frontend, so entity names should contain only the entity-specific label
- Example: use `Block YouTube`, not `Firewalla Block YouTube`

## Exception handling rules

- The API layer must translate transport, auth, and protocol failures into custom integration exceptions
- Raw `aiohttp` tracebacks must not leak past the API boundary as user-visible failure modes
- Use a dedicated auth exception such as `FirewallaAuthError` for invalid or revoked credentials
- The Home Assistant layer must map persistent auth failure into `ConfigEntryAuthFailed`
- Timeouts and upstream availability failures must be represented separately from auth failures

## Authentication and retry rules

- A persistent auth failure is defined as two consecutive `401 Unauthorized` responses
- The client may perform one immediate retry after the first `401`
- If the second response is also `401`, raise `FirewallaAuthError`
- Do not implement long retry windows for `401` responses
- Use normal backoff and retry handling for timeouts and `5xx` conditions only where appropriate

## Logging rules

- Use structured, lazy logging
- Never log QR payloads, PEM material, tokens, signatures, or decrypted sensitive payload data
- Keep logs useful for debugging without exposing secrets or personal data
- Avoid repetitive coordinator error spam for persistent auth failure; reauth should take over

## Localization rules

- Do not hardcode user-facing production strings in Python modules when translation keys are appropriate
- English translation files are the only manually edited source for translated integration text
- Reauth, repair, and config-flow errors must be translation-ready

## Diagnostics rules

- `diagnostics.py` must use Home Assistant redaction helpers such as `async_redact_data`
- Diagnostics output must scrub PII, secrets, tokens, PEM material, host-specific sensitive values, and any sensitive Firewalla JSON payload fields
- Diagnostics should expose enough structure to debug integration problems without exposing account or network secrets

## Security rules

- Handle QR payloads as sensitive input
- Prefer in-memory key generation during normal Home Assistant operation
- Store only the minimum durable secret material required for reconnect and reauth
- Never expose secret material in logs, exceptions, diagnostics, or entity attributes

## Dependency management

- The integration must depend on `cryptography`
- Declare the dependency in `manifest.json`
- Do not introduce alternative crypto implementations
- Keep tests and types aligned with the chosen dependency

## Validation workflow

Run these commands for relevant changes:

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/firewalla_local`
- `python -m pytest tests/ -v`

Documentation and translations must be updated when behavior changes require them.