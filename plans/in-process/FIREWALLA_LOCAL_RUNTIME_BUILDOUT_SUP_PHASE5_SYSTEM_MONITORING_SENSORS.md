# Support Note: Phase 5 system-monitoring sensors

## Initiative snapshot

- Initiative: Firewalla Local runtime buildout, Phase 5
- Focus: Add the first system-monitoring sensor surfaces from proven local payload data only
- Status: Complete
- Source of truth for payload evidence: `.artifacts/poc/20260323-174620/local_response_decrypted.json`

## Scope and non-goals

### In scope

- One main Firewalla system-status sensor attached to the existing box device
- One latest-speed-test sensor attached to the same device
- Typed normalization of the proven monitoring fields in `api/client.py` and `models.py`
- Translation-ready Home Assistant sensor entities with stable attribute contracts
- Focused tests for normalization, entity setup, attribute stability, and latest-result selection
- `bootingComplete` as the leading primary-state candidate for the main system-status sensor
- Switch-style Platinum conventions for constants, translation keys, and a translation-backed `purpose` attribute

### Non-goals

- Adding extra standalone CPU, memory, disk, uptime, load, or temperature sensors without direct payload proof
- Promoting `ddnsToken` or any other sensitive secret into runtime models, diagnostics, or entity attributes
- Building historical or statistics sensors for the entire speed-test list in this phase
- Refactoring device identity away from the existing license-anchored device model
- Expanding diagnostics scope unless the new monitoring data is intentionally needed there

## Open questions or external dependencies

1. Which additional monitoring values, if any, are worth promoting beyond attributes into first-class entities?
2. Should the speed-test sensor ignore failed results entirely, or surface a failure-oriented state when the latest entry is unsuccessful?
3. Which user-facing docs should introduce the new monitoring entities first: README, install docs, or both?

## Phase summary table

| Phase | Focus | Deliverable | Notes |
| --- | --- | --- | --- |
| 5A | Typed model expansion | New runtime snapshot structures for system status and speed test | Avoid raw dict use in platform code |
| 5B | API normalization | Payload-backed system and speed-test builders | Bound strictly to proven fields |
| 5C | Sensor platform | Main system sensor and latest speed-test sensor | Reuse existing device identity and coordinator |
| 5D | Validation and quality evidence | Focused tests and honest rule/status updates | Internal-only fixture-driven coverage |

## Per-phase details with checkboxes

### Phase 5A: Typed model expansion

- [x] Add a typed model for the main system-status sensor state in `custom_components/firewalla_local/models.py`.
- [x] Add a typed model for the latest speed-test result in `custom_components/firewalla_local/models.py`.
- [x] Extend `FirewallaRuntimeSnapshot` to carry both typed structures.
- [x] Keep `FirewallaSystemInfo` focused on durable identity and software metadata rather than live sensor state.
- [x] Add any new sensor-specific attribute keys, translation keys, entity suffixes, and purpose-state constants to `custom_components/firewalla_local/const.py` before platform work begins.
- [x] Avoid placeholder fields for metrics that are not yet proven in the decrypted payload.

### Phase 5B: API normalization

- [x] Update `custom_components/firewalla_local/api/client.py` to normalize the main system-status payload from proven top-level fields, using snapshot-backed availability semantics for the entity state and `bootingComplete` as an explicit attribute.
- [x] Exclude `ddnsToken` and any similarly sensitive values from all normalized monitoring models.
- [x] Normalize the latest successful entry from `internetSpeedtestResults` by timestamp.
- [x] Keep speed-test selection deterministic and document the rule in code and tests.
- [x] Treat missing or empty speed-test history as a valid no-data state.

### Phase 5C: Sensor platform

- [x] Add `custom_components/firewalla_local/sensor.py`.
- [x] Update `custom_components/firewalla_local/__init__.py` to forward the sensor platform.
- [x] Implement one main Firewalla system-status sensor tied to the existing device entry, with snapshot-backed availability as its state and `bootingComplete` exposed as an attribute.
- [x] Implement one latest-speed-test sensor with download throughput as the entity state.
- [x] Convert timestamps to Home Assistant-friendly datetime attributes and keep the attribute contract stable.
- [x] Add a `purpose` state attribute to the main system-status sensor that explains the entity exposes overall system availability and key box-health metadata.
- [x] Keep low-value or duplicative fields such as `groupName`, `cpuid`, `branch`, and `fanSpeed` out of the initial main-sensor attribute contract.
- [x] Add complete `translations/en.json` coverage for sensor names and state attributes, including purpose text, instead of inline user-facing strings.
- [x] Add translation keys, icons, and units only where the payload semantics are clear and testable.

### Phase 5D: Validation and quality evidence

- [x] Add focused normalization tests, likely in `tests/components/firewalla_local/test_client.py` and `tests/components/firewalla_local/test_models.py`.
- [x] Add focused sensor-entity tests in a new `tests/components/firewalla_local/test_sensor.py`.
- [x] Verify empty-state behavior when no speed-test history is present.
- [x] Verify the latest successful speed-test selection rule against more than one payload item.
- [x] Verify the main sensor exposes the expected constants-backed purpose attribute and that translation-backed metadata resolves through `en.json`.
- [x] Update `custom_components/firewalla_local/quality_scale.yaml` and any affected plan or doc notes to reflect the new sensor platform honestly.

## Validation strategy

- Plan-only updates do not require lint, type, or test runs.
- Implementation validation for this phase should include at minimum:
  - `python -m ruff check .`
  - `python -m mypy custom_components/firewalla_local`
  - focused pytest for the touched Firewalla Local modules
- All tests for this phase must remain internal-only and fixture-driven.
- The captured decrypted payload should be treated as the reference fixture for proven field presence, but test fixtures should be minimized to the fields each test actually needs.

Implementation outcome:

- Delivered a typed `system_status` and `latest_speed_test` slice on `FirewallaRuntimeSnapshot`.
- Added API-side normalization for the proven top-level system fields and deterministic latest-successful speed-test selection.
- Shipped a new sensor platform with a translation-backed availability-style system-status sensor and a latest-speed-test download measurement sensor.
- Extended the system-status attributes with proven WAN IP, CPU load, memory usage, free memory, and filtered disk-usage-by-mount details without adding extra standalone sensors.
- Kept `ddnsToken`, uptime, and thermal metrics out of scope pending stronger payload proof.
- Validated the slice with internal-only Ruff, MyPy, and full pytest runs.

## References

- `plans/in-process/FIREWALLA_LOCAL_RUNTIME_BUILDOUT_IN-PROCESS.md`
- `docs/ARCHITECTURE.md`
- `custom_components/firewalla_local/models.py`
- `custom_components/firewalla_local/api/client.py`
- `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla_local/managers/integration_manager.py`
- `custom_components/firewalla_local/__init__.py`
- `custom_components/firewalla_local/quality_scale.yaml`
- `tests/components/firewalla_local/test_client.py`
- `tests/components/firewalla_local/test_models.py`
- `.artifacts/poc/20260323-174620/local_response_decrypted.json`

## Proven payload-backed field inventory

Confirmed box-level fields already observed in the decrypted payload:

- `cloudConnected`
- `bootingComplete`
- `ddns`
- `firmwareReleaseType`
- `publicIp`
- `publicIps`
- `sysMetrics.load5`
- `sysMetrics.memUsage`
- `sysMetrics.totalMem`
- `sysMetrics.diskInfo`

Recommended initial main-system-sensor contract:

- State:
  - snapshot-backed availability
- High-value candidate attributes:
  - `purpose`
  - `bootingComplete`
  - `cloudConnected`
  - `ddns`
  - `firmwareReleaseType`
  - `wan_ip`
  - `wan_ips`
  - `cpu_load_5m`
  - `memory_usage_percent`
  - `memory_free_mb`
  - `disk_usage_percent_by_mount`

Required presentation pattern for the initial main-system sensor:

- define the sensor attribute keys in `custom_components/firewalla_local/const.py`
- define the sensor translation keys and any purpose-state values in `custom_components/firewalla_local/const.py`
- add the sensor name and state-attribute translations to `custom_components/firewalla_local/translations/en.json`
- use the same translation-backed `purpose` pattern already used by the switch platform so the sensor explains what its boolean state means

Proven but intentionally excluded from the initial main-system-sensor surface because they are low-value, duplicative, or not user-helpful:

- `groupName`
- `branch`
- `cpuid`
- `fanSpeed`

Confirmed latest-speed-test candidate fields already observed in `internetSpeedtestResults`:

- `timestamp`
- `manual`
- `success`
- `vendor`
- `client.isp`
- `client.publicIp`
- `result.download`
- `result.upload`
- `result.latency`
- `result.jitter`
- `result.ploss`
- `result.dlMbytes`
- `result.ulMbytes`
- `server.id`
- `server.host`
- `server.location`
- `server.country`
- `server.sponsor`

Fields explicitly excluded from the Phase 5 contract unless later evidence changes the decision:

- `ddnsToken`
- CPU percent or process-level CPU breakdowns beyond `cpu_load_5m`
- memory breakdowns beyond overall usage percent and free memory
- raw all-mount disk dumps beyond the filtered operational mount map
- any inferred uptime metrics
- any inferred thermal metrics