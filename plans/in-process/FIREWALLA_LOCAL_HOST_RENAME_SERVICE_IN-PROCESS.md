# Firewalla Local host rename service

## Initiative snapshot

Prepare the repository for a future host rename service that follows the existing host-scoped service pattern used by Wake-on-LAN, notification toggles, and DHCP reservation updates. This is planning only. Implementation must not begin until the Firewalla rename command path is captured and confirmed from real traffic.

## Scope and non-goals

Scope:

- capture and verify the rename mutation path for one host
- decide whether rename belongs on the existing host policy path or a distinct command path
- define a stable Home Assistant service contract that reuses the current host selectors
- define the test and validation approach needed before implementation

Non-goals:

- shipping the service implementation
- adding new host entities or options-flow surfaces
- assuming the rename payload shape without captured evidence
- broad refactors in [custom_components/firewalla_local/services.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/services.py)

## Open questions or external dependencies

- Is host rename sent through `policy`, a dedicated `host:update`-style command, or another mutation envelope?
- Which host identifier is authoritative for rename writes: MAC, Firewalla host ID, or another internal key?
- Does the write require a pre-read or version token to avoid clobbering concurrent app changes?
- What response payload confirms success, and does the new name appear immediately in the normal runtime refresh?
- Does Firewalla apply rename to pseudo-hosts or only MAC-backed LAN hosts?

## Phase summary table

| Phase | Goal | Exit gate |
| --- | --- | --- |
| 1 | Capture rename evidence | At least one clean request and response pair is saved and mapped to a specific user action |
| 2 | Validate protocol contract | Request path, identifier, payload fields, and post-write read behavior are confirmed |
| 3 | Design service contract | Service inputs, error model, and response envelope are stable enough to implement |
| 4 | Lock test strategy | Mock shapes, coverage targets, and validation commands are agreed |
| 5 | Final decision gate | Proceed to `Firewalla Builder` only if the mutation path is proven and low-ambiguity |

## Per-phase details with checkboxes

### Phase 1. Capture rename evidence

- [ ] Follow [docs/REVERSE_ENGINEERING_WORKFLOW.md](/workspaces/firewalla-local-ha/docs/REVERSE_ENGINEERING_WORKFLOW.md) and capture one host rename from the official app with the target host clearly identified before and after the change.
- [ ] Save the raw request and response artifacts in the existing research track, cross-linking the result from [plans/in-process/FIREWALLA_LOCAL_DATA_ACCESS_RESEARCH_IN-PROCESS.md](/workspaces/firewalla-local-ha/plans/in-process/FIREWALLA_LOCAL_DATA_ACCESS_RESEARCH_IN-PROCESS.md).
- [ ] Record whether the app resolves the target by MAC, host ID, name, or another key, and whether the rename surface is limited to MAC-backed hosts.
- [ ] Re-run the same rename flow once more to check whether the command path and payload are stable across repeated edits.

### Phase 2. Validate protocol contract

- [ ] Trace the captured mutation to the owning client boundary in [custom_components/firewalla_local/api/](/workspaces/firewalla-local-ha/custom_components/firewalla_local/api/) and determine whether the write fits an existing client mutation pattern or needs a dedicated client method.
- [ ] Confirm the minimum required payload fields, any normalization rules for empty or unchanged names, and the exact success and failure shapes.
- [ ] Verify whether a standard runtime refresh reflects the new host name, or whether an immediate optimistic response would risk stale state.
- [ ] Stop here if the write path is inconsistent, hidden behind unrelated policy writes, or cannot be reproduced cleanly.

### Phase 3. Design service contract

- [ ] Reuse the existing shared host selector pattern from [custom_components/firewalla_local/services.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/services.py), [custom_components/firewalla_local/services.yaml](/workspaces/firewalla-local-ha/custom_components/firewalla_local/services.yaml), and [custom_components/firewalla_local/const.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/const.py) with `host_id`, `host_mac`, `host_name`, `refresh`, and config-entry selectors.
- [ ] Define one rename-specific input field such as `new_name`, including length, blank-value, and no-op behavior only if those rules are proven by evidence.
- [ ] Choose the response envelope shape to match current host-scoped services: resolved target, original query, normalized rename payload summary, and raw command acknowledgement.
- [ ] Define translation-ready validation and failure cases in [custom_components/firewalla_local/translations/en.json](/workspaces/firewalla-local-ha/custom_components/firewalla_local/translations/en.json) for missing host, ambiguous host, invalid rename input, unsupported host type, and backend rejection.

### Phase 4. Lock test strategy

- [ ] Add service tests in [tests/components/firewalla_local/test_services.py](/workspaces/firewalla-local-ha/tests/components/firewalla_local/test_services.py) that mirror current host-scoped patterns: success by MAC, success by name, ambiguous-name rejection, unsupported-host rejection if applicable, and backend failure mapping.
- [ ] Add client or manager tests only if the final mutation path introduces new parsing or shaping logic outside the current service layer.
- [ ] Plan one focused runtime-refresh assertion to confirm the renamed host label is reflected after the write without inventing optimistic rename state.
- [ ] Validate implementation later with `python -m ruff check .`, `python -m mypy custom_components/firewalla_local`, and a focused `python -m pytest tests/components/firewalla_local/test_services.py -v` run before any full-suite pass.

### Phase 5. Final decision gate

- [ ] Proceed only if the rename command path is captured twice, the target identifier is unambiguous, and the post-write read path reliably surfaces the updated name.
- [ ] Block implementation if rename works only through a brittle UI-only sequence, depends on unmodeled ephemeral tokens, or mutates host records in a way that current selectors cannot target safely.
- [ ] If the gate passes, hand off to `Firewalla Builder` with the captured payload example, agreed service contract, and exact file list below.

## Validation strategy

- Treat evidence capture as the primary validation gate; do not implement against inferred payloads.
- Mirror the existing host-service rollout pattern: deterministic host resolution first, mutation call second, response-envelope assertions third.
- Prefer narrow service-level tests first, then add lower-layer coverage only where the captured protocol shape forces it.

## References

- [plans/in-process/FIREWALLA_LOCAL_DATA_ACCESS_RESEARCH_IN-PROCESS.md](/workspaces/firewalla-local-ha/plans/in-process/FIREWALLA_LOCAL_DATA_ACCESS_RESEARCH_IN-PROCESS.md)
- [docs/REVERSE_ENGINEERING_WORKFLOW.md](/workspaces/firewalla-local-ha/docs/REVERSE_ENGINEERING_WORKFLOW.md)
- [custom_components/firewalla_local/services.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/services.py)
- [custom_components/firewalla_local/services.yaml](/workspaces/firewalla-local-ha/custom_components/firewalla_local/services.yaml)
- [custom_components/firewalla_local/const.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/const.py)
- [custom_components/firewalla_local/managers/integration_manager.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/managers/integration_manager.py)
- [custom_components/firewalla_local/translations/en.json](/workspaces/firewalla-local-ha/custom_components/firewalla_local/translations/en.json)
- [tests/components/firewalla_local/test_services.py](/workspaces/firewalla-local-ha/tests/components/firewalla_local/test_services.py)

## Recommended implementation file touch list

- [custom_components/firewalla_local/api/client.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/api/client.py)
- [custom_components/firewalla_local/managers/integration_manager.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/managers/integration_manager.py)
- [custom_components/firewalla_local/services.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/services.py)
- [custom_components/firewalla_local/services.yaml](/workspaces/firewalla-local-ha/custom_components/firewalla_local/services.yaml)
- [custom_components/firewalla_local/const.py](/workspaces/firewalla-local-ha/custom_components/firewalla_local/const.py)
- [custom_components/firewalla_local/translations/en.json](/workspaces/firewalla-local-ha/custom_components/firewalla_local/translations/en.json)
- [tests/components/firewalla_local/test_services.py](/workspaces/firewalla-local-ha/tests/components/firewalla_local/test_services.py)