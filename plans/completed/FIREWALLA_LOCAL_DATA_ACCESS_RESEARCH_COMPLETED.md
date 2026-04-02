# Initiative Plan: Firewalla Local data access research

## Initiative snapshot

- Initiative: Firewalla Local data access research
- Status: Completed
- Primary outcome: The research confirmed that the Firewalla mobile app reuses the existing local Encipher transport, mixes full init-style snapshot pulls with narrower page-scoped commands, and also exposes live-stats stream behavior on port `8833` for some app surfaces.

## Completion summary

- Confirmed the active integration refresh path and practical payload size of the full runtime-init pull.
- Completed the overview, refresh, page-transition, and known-change capture workflow.
- Confirmed that the mobile app uses the same encrypted local Encipher transport family already used by the integration.
- Confirmed a hybrid local model rather than a pure full-snapshot-only model:
  - full init-style refreshes remain part of the app behavior
  - narrow encrypted commands exist for page-scoped actions
  - live-stats stream behavior is present on port `8833` for relevant app views
- Completed the intended research and documented the resulting findings in this plan and the reverse-engineering workflow.

## Final research conclusions

- The app does not rely on a completely separate obvious transport for its primary local behavior.
- The most important long-term takeaway is a hybrid model:
  - shared full snapshot baseline
  - narrower direct commands and reads for some page workflows
  - live streaming behavior for throughput-style views
- The research produced enough evidence to support multiple production service additions, including the now-completed host rename service.

## Deferred follow-up

- `get_wan_events` remains intentionally deferred.
- Deferred item:
  - compare the current `get_wan_events` service contract against Firewalla's published MSP Alarm model, especially Alarm type `15` Internet Connectivity Update, and decide whether the service should remain low-level WAN-health telemetry, grow an alarm-aligned projection, or split into separate telemetry and alarm-shaped surfaces

## Close-out note

- All other planned items are considered complete for this initiative.
- Any future work beyond the deferred `get_wan_events` comparison should start from a new initiative or a focused follow-up plan instead of reopening this research plan.
