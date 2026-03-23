# Supporting note: documentation target outlines

## Purpose

This note defines the intended shape of the first durable documentation set so implementation stays concise and does not overfit the current scaffold.

## Proposed `docs/ARCHITECTURE.md` outline

1. Purpose and quality target
2. Repository terminology contract
3. Current component map
4. Runtime lifecycle overview
5. Configuration boundaries
6. Module boundaries and allowed dependencies
7. Localization architecture
8. Testing and validation architecture
9. Evolution rules for future extraction
10. Open decisions reserved for the next architecture plan

## Proposed `docs/DEVELOPMENT_STANDARDS.md` outline

1. Purpose and audience
2. Constants and naming standards
3. Localization and translation standards
4. Typing standards
5. Async, I/O, and blocking-work rules
6. Logging and exception rules
7. Config flow standards
8. Entity and diagnostics standards
9. Validation commands and definition of done

## Architecture posture for the first docs pass

- Keep the documented runtime architecture minimal.
- Treat the coordinator and API client as the center of the current scaffold.
- Allow future extraction into `helpers/`, `utils/`, or additional modules, but only document those as optional patterns until the codebase justifies them.
- Reserve any event-driven or manager-style coordination patterns for a later planning cycle if real complexity appears.

## Non-negotiable standards to establish immediately

- All production code is fully typed.
- User-facing strings are translation-ready from day one.
- Constants are the source of truth for repeated identifiers and stable keys.
- Future pure modules must not import `homeassistant.*`.
- Logging must use lazy formatting.
- Exception types must be specific and Home Assistant-appropriate.

## Decisions to defer intentionally

- Exact runtime module count beyond the current scaffold.
- Whether future business logic warrants a dedicated pure-logic layer.
- Any storage design beyond config entry data and runtime data.
- Any protocol-specific architecture decisions until Firewalla transport and auth are verified.