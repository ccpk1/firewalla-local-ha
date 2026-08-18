# Initiative: Host Device Delete Service (`delete_host`)

## 1. Initiative snapshot

- **Source:** Confirmed reverse-engineering finding (Finding 22) via live packet capture of the Firewalla iOS app deleting a host device. Reference artifact: `.tmp/delete_host_capture.pcap`.
- **Requested capability:** A Home Assistant service that deletes one or more host devices from the Firewalla box by sending the captured `cmd` mutation.
- **Protocol (CONFIRMED by capture, do not re-derive):**

```json
{
  "mtype": "cmd",
  "target": "0.0.0.0",
  "data": {
    "value": { "mac": "12:A9:78:EB:EA:02" },
    "item": "host:delete"
  }
}
```

- **Key facts:**
  - Plain `cmd` message (consistent with `wol:wake`, `runInternetSpeedtest`), NOT `set`.
  - `data.item = "host:delete"`.
  - `data.value = {"mac": "<MAC>"}` — the **only** field is the target host's MAC (no IP, hostname, or device type).
  - Outer `target = "0.0.0.0"` (box-level), like other `cmd` mutations.
  - The delete is a single message **per host**; the subsequent `batchAction` (appTimeUsage gets) and `init` requests are data refreshes, NOT part of the mutation. There is no captured multi-MAC batch delete.
- **Current state:** Finding 22 already recorded in `docs/REVERSE_ENGINEERING_WORKFLOW.md`. No code exists yet.

## 2. Scope and non-goals

**In scope**
- API client mutation method: `async_delete_host(host_mac)` in `api/client.py`.
- Manager method in `FirewallaIntegrationManager` (alongside existing host-scoped mutations) with validation and post-delete host-index effect.
- Service `firewalla_local.delete_host` supporting **one or many hosts**, a **required destructive-confirmation toggle**, **skip-on-unmatched**, and a **per-host result response**.
- `services.yaml` entry, translation keys (`SERVICE_*`, `SERVICE_FIELD_*`, `TRANS_KEY_*`) including a destructive-confirmation field key.
- Tests (client, manager, service success/error, multi-host, skip-on-unmatched, confirm gate, post-delete reconciliation).
- Docs (`docs/USER_GUIDE.md`) updates.

**Non-goals**
- Device-registry cleanup / entity purging of the deleted host's HA devices/entities (deferred; see §3 open item — the Firewalla host registry entry should remain available until a refresh naturally drops it).
- Deleting non-MAC-backed surfaces (VPN peers, groups, rules). Only the MAC-identified LAN host deletes are in scope.
- Undo/recovery flow. A required destructive-confirmation toggle guards the action; there is no server-side "undo".
- Changing extraction/redaction of the existing capture.

## 3. Open questions / external dependencies

- **Post-delete reconciliation (decide during Phase 2):** After the delete succeeds, the deleted MAC should be dropped from `FirewallaHostManager._host_index`. Two options:
  1. Manager triggers a coordinator refresh (`async_request_refresh`) immediately after the mutation so the next `handle_refresh` rebuilds the index (matches `refresh` service semantics today).
  2. Manager directly evicts the MAC from `_host_index` synchronously before returning.
  Design intent: the service already refreshes before deleting and reports `refreshed`. The minimal correct behavior is to also refresh **after** a successful delete so the index and entity set converge, then reassess. This requires no new write paths and keeps `handle_refresh` as the single index owner. Confirm the coordinator refresh is cheap enough on delete (host delete is rare) — accepted.
- **Delete of a non-existent host:** The capture does not show the Firewalla error shape for a non-existent MAC (it succeeded). Per spec, the service resolves each requested host against the current snapshot; **if an exact match is not found, that host is SKIPPED** (not sent to the box, not an error for the whole call) and reported in the per-host result envelope with a `not_found`/`skipped` result. Only requested hosts that resolve exactly are sent.
- **Destructive confirmation:** The service **requires** a confirmation toggle (e.g. `SERVICE_FIELD_CONFIRM`, `confirm: true`) that the caller must set to proceed. Without it (or `confirm: false`), the service aborts with a translation-ready validation error (`delete_host_confirm_required`). This is a hard gate, NOT optional, and follows the established high-quality pattern of destructive actions requiring explicit acknowledgement.
- **Multi-host cardinality:** The schema accepts a list of host identifiers (host selector supports multiple). Each is resolved and deleted independently; one `host:delete` cmd per resolved MAC (no captured multi-MAC batch delete). Unmatched targets are skipped per the rule above. The response is a per-host result envelope showing each host's success or failure.
- **Response envelope:** After completion, the service returns a structured response showing **each requested host's result** — success, failure, or skipped (not-found) — so callers know exactly what happened to each MAC.
- **Watched-device / device-tracker reconciliation post-delete:** If a deleted MAC is also in `CONF_WATCHED_DEVICES` / `CONF_DEVICE_TRACKERS` option lists, the host-manager choice maps simply no longer contain it (next refresh). We do NOT auto-mutate saved options. Document this.

## 4. Phase summary table

| Phase | Goal | Key output |
| --- | --- | --- |
| 1 | Client mutation | `async_delete_host(mac)` + constants + client unit test |
| 2 | Manager orchestration + host-index effect | `async_delete_host` on `FirewallaIntegrationManager` + post-delete refresh/index reconciliation + manager test |
| 3 | Service surface | `SERVICE_DELETE_HOST` + schema + handler + `services.yaml` + translation keys + service tests |
| 4 | Docs + validation | `USER_GUIDE` section, quality-scale note, full gate commands |

## 5. Per-phase details

### Phase 1 — API client mutation

- [ ] In `custom_components/firewalla_local/api/client.py`, add a module constant for the mutation item near the other `_COMMAND_*` constants:
  - `_COMMAND_DELETE_HOST: Final = "host:delete"`.
  - Reuse `_RAW_HOST_MAC_KEY` (`"mac"`) — already defined at line 150 — for the value key. No new value-key constant needed.
- [x] Add a method `async_delete_host(self, host_mac: str) -> dict[str, object]` following the existing `async_wake_host` / `async_run_internet_speed_test` `cmd` pattern:
  - `message_type=_COMMAND_MESSAGE_TYPE`,
  - `data={_COMMAND_ITEM_KEY: _COMMAND_DELETE_HOST, _COMMAND_VALUE_KEY: {_RAW_HOST_MAC_KEY: host_mac}}`,
  - `target=DEFAULT_INIT_TARGET` (i.e. `0.0.0.0`), confirming box-level target per Finding 22.
  - Docstring: "Delete one MAC-identified host device from the Firewalla inventory."
- [x] Add client unit test in `tests/components/firewalla_local/test_client.py` (model on `test_async_wake_host_sends_host_targeted_command`):
  - Patch `_async_send_local_message` (`AsyncMock`).
  - Assert returned response; assert `mock_send.await_args.kwargs == {"message_type": "cmd", "data": {"item": "host:delete", "value": {"mac": "00:AA:BB:CC:DD:26"}}, "target": "0.0.0.0"}`.
- Note: no translation/quality-scale changes in this phase.

### Phase 2 — Manager orchestration + host-index reconciliation

- [x] In `custom_components/firewalla_local/managers/integration_manager.py`, add `async_delete_host(self, host_mac: str) -> dict[str, object]` alongside `async_wake_host`:
  - Call `self.client.async_delete_host(host_mac)`.
  - On success, route the MAC through the host manager for index reconciliation (see next step) so the deleted host drops out of `_host_index` without waiting for the next periodic snapshots.
  - Return the raw command response (consistent with other mutations).
- [x] Register the client as the sole write path: the manager method must be the only caller of `client.async_delete_host` (respect the `ARCHITECTURE.md` "single write path" rule: services go through the manager, never straight to the API).
- [x] In `custom_components/firewalla_local/managers/host_manager.py`, add a public index-reconciliation hook wired from the integration manager, `def remove_host_from_index(self, mac: str) -> None` that drops the normalized MAC from `self._host_index`. This is a read-side index correction, NOT a new write path, and does not mutate config `options`.
- [x] In the integration manager's `async_delete_host`, after a successful client call, evict the MAC from the host index via `remove_host_from_index`. The manager mutation stays pure (send + index eviction); the service's standard `refresh` mechanism refreshes afterward. The coordinator is not triggered from the manager (matches current setter methods).
- [x] Manager unit test in `tests/components/firewalla_local/test_integration_manager.py`:
  - Mock `client.async_delete_host`.
  - Assert it is forwarded with a normalized MAC, and that the host-manager index no longer returns the deleted MAC after `remove_host_from_index`.
- Note: no translation changes in this phase.

### Phase 3 — Service surface

- [x] **Constants** in `custom_components/firewalla_local/const.py`:
  - `SERVICE_DELETE_HOST: Final = "delete_host"` next to `SERVICE_WAKE_HOST`.
  - `SERVICE_FIELD_CONFIRM: Final = "confirm"` — new destructive-confirmation boolean field key (established high-quality pattern for destructive actions).
  - `TRANS_KEY_EXCEPTION_DELETE_HOST_FAILED: Final = "delete_host_failed"` in the exception key block.
  - `TRANS_KEY_EXCEPTION_DELETE_HOST_CONFIRM_REQUIRED: Final = "delete_host_confirm_required"` — validation error when the destructive confirmation toggle is not set.
- [x] **Schema** in `custom_components/firewalla_local/services.py`:
  - `DELETE_HOST_SCHEMA` uses a `host_mac` list (`cv.ensure_list_csv`) for one or many MACs **plus a required `confirm` boolean**. The handler rejects the call unless `confirm is True`.
- [x] **Handler** `_async_handle_delete_host(call: ServiceCall) -> JsonObjectType` modeled on `_async_handle_wake_host` but **multi-host**:
  - `_get_loaded_entry(...)`.
  - **Destructive gate:** read `confirm = bool(call.data[SERVICE_FIELD_CONFIRM])`; if not true, raise the confirmation validation error (`TRANS_KEY_EXCEPTION_DELETE_HOST_CONFIRM_REQUIRED`). This is the mandatory acknowledgement.
  - `refresh_requested = cast(bool, call.data[SERVICE_FIELD_REFRESH])`; if set, `_async_refresh_runtime_state(entry)` (refresh **before** resolving so the host list is current).
  - **Resolve each requested host** (the host selector may resolve one or many) via the existing host resolution/selector helpers.
  - **Skip-on-unmatched:** for each requested host identifier that does NOT resolve to an exact host in the current snapshot, record it in results as `skipped`/`not_found`, do NOT send it, and continue (do not abort the whole call).
  - For each **resolved** host, `try: command_response = await integration_manager.async_delete_host(host.mac)` except `FirewallaApiError` → record that host's result as `failed` (with the translated error), continue evaluating the remaining hosts.
  - **Per-host result response:** return a structured envelope listing, per requested host, its status — `success`, `failed` (+ error), or `skipped`/`not_found` — plus aggregate `config_entry_id`, `refreshed`, and `command` (`{"item": "host:delete"}`).
  - Choose `SupportsResponse.ONLY` (matches other host mutations).
- [x] **Register** the service in `SERVICE_HANDLERS` (or the equivalent registry tuple) near `WAKE_HOST`, with `DELETE_HOST_SCHEMA` and `_async_handle_delete_host`.
- [x] **`services.yaml`** entry `delete_host:` modeled on `wake_host:`:
  - name + description (explicit destructive wording: "Permanently delete one or more host devices"), fields `host_mac` (multi), `host_name`, `host_id`, `refresh`, `config_entry_id`, `config_entry_name`, and `confirm` (boolean, required, phrased as "I understand this permanently deletes the host").
- [x] **Translations** in `custom_components/firewalla_local/translations/en.json`:
  - Add service name/description keys under `services.delete_host` (if the integration localizes service names — follow the existing `services` translation block).
  - Add `delete_host_failed` ("The integration could not delete a host. Check the Firewalla connection and try again.") and `delete_host_confirm_required` ("Deleting a host is destructive. Set `confirm: true` to proceed.") as siblings of `set_host_name_failed` / `wake_host_failed` in the `exceptions` block.
  - Regenerate English translations before testing: `.venv/bin/python3 -m script.translations develop --integration firewalla_local` (per core AGENTS.md; run relative to the workspace that hosts the script).
- [x] **Service tests** in `tests/components/firewalla_local/test_services.py`, modeled on the `wake_host` suite:
  - **confirm gate:** calling without `confirm: true` raises `ServiceValidationError` with `delete_host_confirm_required` and does NOT call the manager.
  - **single-host success:** `host_mac` + `confirm: true`; asserts resolution + manager `async_delete_host` called with the MAC + per-host `success` result in the envelope.
  - **multi-host success:** multiple host MACs resolve and each is deleted; every target reports `success`.
  - **skip-on-unmatched:** one resolvable host + one non-existent MAC; the resolvable one is deleted and reported `success`, the non-existent one is reported `skipped`/`not_found`, and the call does NOT raise.
  - **partial failure:** a `FirewallaApiError` on one host records that host as `failed` (translated error) while others still succeed.
  - success via unique `host_name` and via full host label (duplicate_name snapshot for ambiguous-name error).
  - (optional) when `refresh` false does not call `async_request_refresh`.

### Phase 4 — Docs + quality-scale + gate

- [x] **Docs** in `docs/USER_GUIDE.md`:
  - Add a `### Delete host` subsection under the host operator services (near "Wake host"), documenting: service name, **required `confirm: true` destructive gate**, support for one or many hosts, **skip-on-unmatched** behavior, and the **per-host result response**.
  - Add `firewalla_local.delete_host` to the "Services added after 1.0.0" list and the host-and-network operator actions list.
- [x] **Reverse-engineering doc:** Finding 22 is already complete (`docs/REVERSE_ENGINEERING_WORKFLOW.md` § Finding 22). No further changes needed (implementation matched the captured contract exactly).
- [x] **quality_scale.yaml:** the service ships with full test coverage; quality_scale.yaml tracks services via prose comments and does not enumerate per-service counts, so no change is required to stay honest.
- [ ] **Release notes:** optionally add a line to the next release notes doc (outside scope unless requested).

## 6. Validation strategy

Run all in the Firewalla repo root (`/workspaces/firewalla-local-ha`):

- `python -m ruff check .`
- `python -m ruff format .`
- `python -m mypy custom_components/firewalla_local`
- `python -m pytest tests/ -v` (focused scopes allowed during iteration — `tests/components/firewalla_local/test_client.py`, `test_integration_manager.py`, `test_services.py`; the final report states what was and was not run).

Additional checks:
- Regenerate English translations before running the service tests (service name/description + exception string) so the translated keys load from `translations/en.json`.
- Confirm root-level module drift is avoided (delete logic lives in `api/client.py` + `managers/integration_manager.py` + `services.py` only).
- Confirm `quality_scale.yaml` is honest.

## 7. References

- Finding 22 — `docs/REVERSE_ENGINEERING_WORKFLOW.md` (lines ~2098): confirmed `cmd`/`host:delete`/`{"mac"}` box-level contract.
- `api/client.py` — `_async_send_local_message`, `_COMMAND_*`, `async_wake_host`, `async_run_internet_speed_test`, `async_delete_rule` (mutation shape), `_RAW_HOST_MAC_KEY`.
- `managers/integration_manager.py` — existing `async_set_host_*`/`async_wake_host` orchestration.
- `managers/host_manager.py` — `_host_index`, `handle_refresh`, `get_host`, `remove_host_from_index` (new).
- `services.py` — `_HOST_TARGET_SCHEMA_FIELDS`, `WAKE_HOST_SCHEMA`, `_async_handle_wake_host`, `SERVICE_HANDLERS` registry, `_async_refresh_runtime_state`, `_resolve_requested_host`, `_raise_runtime_service_error`.
- `const.py` — `SERVICE_*`, `SERVICE_FIELD_*`, `TRANS_KEY_*` conventions.
- `services.yaml` — `wake_host:` block as template.
- `translations/en.json` — `set_host_name_failed`/`wake_host_failed` blocks as templates.
- Tests — `tests/components/firewalla_local/test_client.py`, `test_integration_manager.py`, `test_services.py` (wake_host patterns).
- `docs/USER_GUIDE.md` — host service sections + service catalog.

## 8. Follow-up / open assumptions (flagged)

- **Deletion mirrors the capture's ack** — a valid capture succeeded; a `FirewallaApiError` (box unreachable, etc.) is handled per host as a `failed` result rather than aborting the multi-host call.
- **Confirmation gate hardening** — `confirm: true` is enforced in the handler before any host is resolved or sent. This is the destructive-action acknowledgement.
- **Skip-on-unmatched** — a requested host that does not resolve in the current snapshot is skipped and reported `skipped`/`not_found`, never fatal to the whole call.
- **Post-delete refresh semantics** — refresh before resolving so the host list is current; the next coordinator refresh re-converges the index and entity set after delete. No post-delete `init` needed from the service.
- **Hard ties to apply:** Do not auto-edit `CONF_WATCHED_DEVICES`/`CONF_DEVICE_TRACKERS`; just document that a deleted host stops appearing in those choice maps after refresh.