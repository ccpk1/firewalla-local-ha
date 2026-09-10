# Initiative: Internet Quality Monitoring (ping latency & packet loss)

## 1. Initiative snapshot

- **Source:** `ccpk1/firewalla-local-ha` issue #42 — *"[Feature]: Internet quality monitoring (ping latency & packet loss)"* (label: `enhancement`).
- **Requested capability:** Surface the Firewalla app's per-WAN **Internet Quality** view in Home Assistant — **ping latency** and **ping packet loss** measured against a ping target (Cloudflare `1.1.1.1` by default), sampled every 15 minutes.
- **Distinct from speed tests:** speed tests measure throughput on demand (`internetSpeedtestResults`, already integrated); Internet Quality is a continuous low-frequency health monitor.
- **Key semantics (confirmed via app + reverse-engineering):**
  - Per-WAN, per-15-minute samples of `ping_latency` (ms) and `ping packet loss` (%).
  - The app shows an hourly roll-up as **worst-value** (max) of its 4 sub-buckets — confirmed by examples (0.2% hour shown for `[0,0,0.2,0]`; 16% hour from a single 16% bucket; 46ms hour from `[41,41,41,46]`). **We will NOT reproduce this roll-up**; we surface raw 15-min samples.

## 2. Scope and non-goals

**In scope**
- **Live entity sensors** (per WAN): `ping_latency` (ms) and `ping_packet_loss` (%) from the **latest** 15-minute sample — mirroring the existing `FirewallaWanSpeedTest*Sensor`.
- **On-demand history service** (follow-up surface): `get_internet_quality_report` returning the sampled `ping_latency`/`ping_packet_loss` series over a requested begin/end interval — mirroring the existing report/usage-history services.
- New client methods to fetch the quality data from the local runtime.
- New typed models (`FirewallaInternetQualitySample`), normalization, and tests.
- Translations, const keys, and (if user-visible) README/doc notes.

### 2.1 Entity structure & naming (aligned with speed-test sensors)

Follow the established per-WAN sensor conventions from `FirewallaWanSpeedTestSensor` so quality sensors behave/name consistently:

- **One sensor class, parameterized by metric** — `FirewallaWanInternetQualitySensor(entry, wan_uuid, *, metric, translation_key)`, mirroring the speed-test sensor exactly (same base `FirewallaEntity` + `SensorEntity`, `_wan_uuid`, translation placeholders for the WAN name).
- **Unique ID:** `{entry_id}_internet_quality_<metric>_<wan_uuid>_sensor` — mirrors `speed_test_<metric>_<wan_uuid>`.
- **Entity names:** translation-key-driven with WAN name placeholder, **exactly matching the speed-test convention** (`_attr_has_entity_name = True` on `FirewallaEntity`, so the full name = device name + translation name). Speed-test uses `{wan_name} Speed test download`; quality should use `{wan_name} Ping latency` and `{wan_name} Ping packet loss` (translation keys `wan_internet_quality_latency` / `wan_internet_quality_packet_loss`).
- **Creation:** loop over `get_available_wans()` in `async_setup_entry`, creating the two sensors per WAN — **always on**, matching speed-test sensors (no option gate). Users can disable individual entities in HA.
- **Device class / units:** latency → `SensorDeviceClass.DURATION` with `UnitOfTime.MILLISECONDS` (matches `FirewallaWanSpeedTestLatencySensor`); packet loss → dimensionless `%` (no device class, like the speed-test packet-loss attribute). Confirm HA ids during implementation.

Each sensor's **attributes** should carry context beyond the single state value, mirroring how speed-test sensors attach rich attributes:

| Attribute | Source | Notes |
| --- | --- | --- |
| `ping_target` / `target` | quality payload (e.g. `1.1.1.1`) | the destination / host being pinged |
| `time_checked` / `sample_at` | sample timestamp (ISO) | when the 15-min reading was taken |
| `ping_latency` (ms) | sample latency | current value (the state) |
| `ping_packet_loss` (%) | sample loss | current loss % |
| `wan_name` / `wan_uuid` | inventory | identity context, like `ATTR_SPEED_TEST_WAN_NAME`/`_UUID` |
| (confirm from schema) | any extra fields in `networkMonitorData` | e.g. `sample_round`, `is_partial` if present |

Exact attribute keys are gated on the live schema pull; the intent is to always expose the **destination/target**, **time checked**, and the two metric values (plus WAN identity), mirroring how speed-test sensors expose server/latency/jitter/packet-loss details.

### 2.9 Gating decision

**Decision: always create the quality sensors (no option gate), matching speed-test sensors.**

Rationale:

- Speed-test sensors are **always** created per WAN today (no toggle). Internet-quality sensors are the same kind of per-WAN surface, so they should behave consistently — no new option-flow toggle.
- Users who don't want them can disable the individual entities in Home Assistant (Settings → Devices & Services → entity → disable), which is the idiomatic per-entity control and requires no integration option.
- This avoids adding a `CONF_ENABLE_INTERNET_QUALITY_ENTITIES` toggle that would be inconsistent with the unconditional speed-test surface.

**Non-goals (until confirmed)**
- Reproducing the app's hourly worst-value roll-up — not needed; we expose raw 15-min samples.
- Any SSH/Linux-level pull of ping stats (modifies the Firewalla device; out of scope for this local-API integration).
- DNS/HTTP quality metrics (`dns_RTT`, `dns_lossrate`, `http_RTT`, `http_lossrate`) seen in the capture — out of scope unless explicitly requested.

## 3. Open questions / external dependencies

### Confirmed from capture + app observations

- **Request shape (captured):**
  - `mtype=get, item=networkMonitorData, value={}` — latency/loss measurements.
  - `mtype=get, item=events, value={filters:[{event_type:"action", sub_type:"ping_RTT"},{... sub_type:"ping_lossrate"}, ...]}` — the ping performance events.
- **Per-WAN scope:** config lives under `policy.network_monitor.wanConfs[<wan_uuid>].state=true`; per-WAN extrude the quality for that WAN.
- **Cadence:** 15-minute `sampleInterval: 900` (confirmed in `policy.network_monitor` config and app drill-down at 5:00 / 5:15 / 5:30 / 5:45).
- **Granularity:** loss is a percentage (e.g. `0.2`, `16`); latency in ms. App hourly view = worst (max) sub-bucket, not average.

### Confirmed (live pull, `utils/probe_internet_quality.py`)

- **`item=networkMonitorData` response shape (confirmed):**
  - Top-level dict keyed by `metric:monitor:raw:ping:<target>:<wan_uuid>` — **one key per WAN+target**, so a single call returns **all WANs** (no per-WAN fan-out).
  - Each value is a dict of **epoch-second buckets** (15-min cadence) → `{"stat": {"lossrate", "max", "mean", "median", "min"}}`.
  - **`lossrate` is a fraction** (0 = 0%, `0.0017` = 0.17%, `0.165` = 16.5%) — multiply by 100 for a `%` sensor.
  - **Latency is in ms** (`max: 73.7`, `mean: 22.2`, `median: 21`, `min: 19.2`).
  - **Returns ~24h of history** (98 samples in the probe) → Phase 3 history service is viable.
- **`events` ping feed (confirmed):** `action_type: ping_lossrate` (labels `lossrate`, `lossrateLimit`, `target`, `wan_intf_uuid`, `wan_intf_name`) and `action_type: ping_RTT` (labels `rtt`, `rttLimit`, ...). These are **threshold-crossing alerts** (only fire when loss/RTT exceeds the limit), not a continuous sample stream — so they are **not** the primary sensor source. Use `networkMonitorData` for the sensors; `events` is only relevant if we later surface alerting.
- **Naming fidelity:** the metric key embeds the target (`1.1.1.1`) and `wan_uuid`; the `stat` keys are `lossrate`/`max`/`mean`/`median`/`min`. No `ping_latency`/`ping_packet_loss` keys exist — those are our entity names, not payload keys.

### 3.1 Gaps and traps (review before implementation)

- **Schema is now confirmed** (see above). Remaining extraction care: `lossrate` is a **fraction** (×100 for `%`), latency is **ms**, and the top-level key embeds both `target` and `wan_uuid` — parse the key, don't guess.
- **Per-WAN scoping.** Quality is per-WAN (`policy.network_monitor.wanConfs[<wan_uuid>]`). The `networkMonitorData` key embeds `wan_uuid`; a WAN with monitoring disabled (`state=false`) simply yields no key for it. Ensure a missing key → no/empty samples rather than a crash or a stale value.
- **Multi-WAN / no-WAN edge cases.** `get_available_wans()` may return zero WANs (no entities) or multiple. The sensor must key by `wan_uuid` and resolve the WAN name via `_resolve_wan_name()` (fall back to uuid), exactly like speed-test sensors. Guard against a WAN disappearing from inventory (`available` should go False, mirroring `FirewallaWanSpeedTestSensor.available`).
- **Redaction (likely not needed).** The quality payload is fetched on demand and is not part of the init-payload diagnostics dump; it contains only a public ping target and numeric latency/loss. Only add redaction if the probe reveals a private IP/MAC in the response.
- **`has_entity_name` naming.** `FirewallaEntity` sets `_attr_has_entity_name = True`, so the full entity name = **device name + translation name**. Use `{wan_name} Ping latency` / `{wan_name} Ping packet loss` (NOT "Firewalla WAN ..."), matching `{wan_name} Speed test download`. Confirm the translation keys and placeholders (`TRANS_PLACEHOLDER_WAN_NAME`).
- **Units/device-class consistency.** Latency must use `SensorDeviceClass.DURATION` + `UnitOfTime.MILLISECONDS` (matches `FirewallaWanSpeedTestLatencySensor`). Packet loss is dimensionless `%` with no device class. Mismatched units would break HA history/statistics.
- **Refresh cadence vs. data cadence.** The integration polls on its own interval (default 3 min), but quality samples are 15-min. The sensor should reflect the **latest available sample** and not fabricate intermediate values; `sample_at` attribute makes the actual sample time explicit so users aren't misled by the poll time.
- **History service scope.** History is confirmed retrievable (~24h of 15-min buckets in one `networkMonitorData` call), so Phase 3 is viable. Keep it a thin read of the runtime's own history — do not build a local store.
- **`events` feed is alerting, not sampling.** The `events` `ping_RTT`/`ping_lossrate` entries are threshold-crossing alerts (only fire when loss/RTT exceeds the limit), not a continuous sample stream. Do **not** use them as the sensor source; use `networkMonitorData`. Only revisit `events` if we later surface alerting.
- **Data flow: separate fetch, not snapshot.** Quality data is NOT in the init-payload snapshot (unlike speed tests). It must be fetched via `async_refresh_internet_quality()` and cached in the manager (`_internet_quality_samples`), mirroring the network-usage pattern. Do not read it from `coordinator.data` — that path only carries snapshot data. The coordinator must call the refresh alongside `async_refresh_network_usage()`.
- **Don't reproduce the hourly roll-up.** We surface raw 15-min samples; do not add worst-value aggregation logic (the app's behavior) unless explicitly requested later.

## 4. Phase summary table

| Phase | Focus | Deliverables | Status |
|---|---|---|---|
| 1 | Data access + model | client fetch, typed `FirewallaInternetQualitySample` | ✅ done |
| 2 | Entity sensors | per-WAN `ping_latency` + `ping_packet_loss` sensors | ✅ done |
| 3 | History service | `get_internet_quality_report` interval service | ✅ done |
| 4 | Docs + tests + quality | translations, README, reverse-engineering finding, tests | ✅ done |

## 5. Per-phase details

### Phase 1 — Data access + model

- [x] **Blocking (done):** ran `utils/probe_internet_quality.py` on the connected dev box; confirmed the `item=networkMonitorData` response schema (see "Confirmed" above): keyed by `metric:monitor:raw:ping:<target>:<wan_uuid>`, 15-min epoch buckets with `stat {lossrate, max, mean, median, min}`, loss as a fraction, latency in ms, ~24h history, all WANs in one call.
- [x] Add raw keys/constants in `api/client.py`: `networkMonitorData`, `events`, `ping_RTT`, `ping_lossrate` (confirmed names).
- [x] Add `async_get_internet_quality_payload(...)` in `api/client.py` using `GET item=networkMonitorData` — mirror `async_get_network_interface_payload`. **Optimization:** this is a **single call returning all WANs**, so it needs no per-WAN fan-out. Fetch it once per coordinator refresh, in parallel with `async_refresh_network_usage()` (via `asyncio.gather`), rather than as a separate sequential call.
- [x] Add `FirewallaInternetQualitySample` (fields: `wan_uuid`, `target`, `timestamp`, `ping_latency_ms`, `ping_packet_loss_percent`) to `models.py`.
- [x] Add a client `_extract_internet_quality_samples(...)` mirroring `_extract_speed_test_records` — parse the `metric:monitor:raw:ping:<target>:<wan_uuid>` key, multiply `lossrate` by 100, keep latency in ms.
- [x] **Manager caching (data flow — NOT the snapshot path).** Quality data comes from a **separate fetch**, not the init-payload snapshot. Mirror the **network-usage** pattern, not `get_speed_test_results`:
  - Add `self._internet_quality_samples: tuple[FirewallaInternetQualitySample, ...] = ()` in `__init__` (like `_network_usage_by_uuid`).
  - Add `async_refresh_internet_quality()` that calls `async_get_internet_quality_payload()` once and stores the extracted samples.
  - Add `get_internet_quality_samples(*, wan_uuid: str | None = None, limit: int | None = None) -> tuple[FirewallaInternetQualitySample, ...]` that filters the cached samples by `wan_uuid` and applies `limit` (mirror `get_speed_test_results`'s *signature*, but read from the cache, not `coordinator.data`).
  - In `coordinator.py`, call `await self.integration_manager.async_refresh_internet_quality()` alongside `async_refresh_network_usage()` (both in the `integration_manager` block, ideally via `asyncio.gather`).
- **Redaction:** NOT required — the quality payload is fetched on demand (not part of the init-payload diagnostics dump) and contains only public ping targets + numeric latency/loss. Confirmed by the probe (no private IP/MAC in the response).

### Phase 2 — Entity sensors (per WAN)

- [x] In `sensor.py`, add a single parameterized `FirewallaWanInternetQualitySensor(entry, wan_uuid, *, metric, translation_key)` mirroring `FirewallaWanSpeedTestSensor` — two instances per WAN (`ping_latency`, `ping_packet_loss`).
- [x] Key each by `wan_uuid` + metric: unique_id `internet_quality_<metric>_<wan_uuid>` (mirror `speed_test_<metric>_<wan_uuid>`).
- [x] Wire state to the **latest** sample via the manager getter `get_internet_quality_samples(wan_uuid=...)` (cache-backed, populated by `async_refresh_internet_quality()`).
- [x] Add **attributes** (mirroring speed-test sensor `extra_state_attributes`): `ping_target` (destination, e.g. `1.1.1.1`), `sample_at` (time checked, ISO), the metric value(s), and `wan_name`/`wan_uuid`. Also expose the full `stat` set: `ping_latency_max`, `ping_latency_median`, `ping_latency_min` (state remains the `mean`).
- [x] `async_setup_entry` loops `get_available_wans()`, creating both sensors per WAN — **always on** (no option gate), matching speed-test sensors.
- [x] Add translation keys + device class/units (latency `ms`, loss `%`); update `icons.json` if useful.

### Phase 3 — History service (history confirmed viable)

Mirror the existing **speed-test results** service (`SERVICE_GET_SPEED_TEST_RESULTS`) end-to-end, not the report-service pattern (which is heavier). The speed-test service is the closest analog: same WAN resolution, same `refresh`/`limit` semantics, same `SupportsResponse.ONLY` registration.

- [ ] **Schema** — `GET_INTERNET_QUALITY_REPORT_SCHEMA` mirroring `GET_SPEED_TEST_RESULTS_SCHEMA`:
  ```python
  vol.Schema(
      {
          vol.Optional(SERVICE_FIELD_WAN_UUID): cv.string,
          vol.Optional(SERVICE_FIELD_WAN_NAME): cv.string,
          vol.Optional(SERVICE_FIELD_LIMIT, default=1): cv.positive_int,
          vol.Optional(SERVICE_FIELD_REFRESH, default=True): cv.boolean,
          vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): cv.string,
          vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
      }
  )
  ```
  (Reuse the existing `SERVICE_FIELD_*` constants; no new `start`/`end` fields — the runtime returns ~24h of history in one call, so `limit` covers the interval.)
- [x] **Handler** — `_async_handle_get_internet_quality_report(call)` mirroring `_async_handle_get_speed_test_results`:
  1. `_get_loaded_entry(...)` via `SERVICE_FIELD_CONFIG_ENTRY_ID`/`_NAME`.
  2. If `SERVICE_FIELD_REFRESH` truthy → `await _async_refresh_runtime_state(entry)`.
  3. `_resolve_requested_wan(entry, wan_uuid=..., wan_name=..., required=False)`.
  4. `entry.runtime_data.integration_manager.get_internet_quality_samples(wan_uuid=..., limit=...)`.
  5. Serialize each sample via `_serialize_internet_quality_sample(...)`.
  6. Return `{"config_entry_id", "refreshed", "wan": _serialize_wan_interface(wan) if wan else None, "count", "latest", "samples"}` — same envelope as speed tests.
- [x] **Manager method** — `get_internet_quality_samples(*, wan_uuid: str | None = None, limit: int | None = None) -> tuple[FirewallaInternetQualitySample, ...]` mirroring `get_speed_test_results`'s **signature**, but reading from the **manager cache** (`self._internet_quality_samples`, populated by `async_refresh_internet_quality()`), NOT `coordinator.data` — the quality data is a separate fetch, not part of the init-payload snapshot. Filter by `wan_uuid`, apply `limit`.
- [x] **Serializer** — `_serialize_internet_quality_sample(sample)` mirroring `_serialize_speed_test_result`:
  ```python
  {
      "sampled_at": datetime.fromtimestamp(sample.timestamp, UTC).isoformat(),
      "sampled_at_timestamp": sample.timestamp,
      "ping_target": sample.target,
      "ping_latency_ms": sample.ping_latency_ms,
      "ping_latency_max_ms": sample.ping_latency_max_ms,
      "ping_latency_median_ms": sample.ping_latency_median_ms,
      "ping_latency_min_ms": sample.ping_latency_min_ms,
      "ping_packet_loss_percent": sample.ping_packet_loss_percent,
      "wan_uuid": sample.wan_uuid,
      "wan_name": sample.wan_name,
  }
  ```
- [x] **Registration** — add `(SERVICE_GET_INTERNET_QUALITY_REPORT, _async_handle_get_internet_quality_report, GET_INTERNET_QUALITY_REPORT_SCHEMA, SupportsResponse.ONLY)` to `_SERVICE_REGISTRATIONS` (mirrors the speed-test entry).
- [x] **Constants** — add `SERVICE_GET_INTERNET_QUALITY_REPORT` in `const.py`. **Note:** the WAN-resolution exception keys are NOT duplicated — `_resolve_requested_wan` is shared and already uses the speed-test keys (`..._WAN_REQUIRED`, `..._WAN_NOT_FOUND`, `..._WAN_SELECTOR_CONFLICT`, `..._WAN_NAME_AMBIGUOUS`), whose messages are generic enough for both services.
- [x] **services.yaml** — add the `get_internet_quality_report` service definition mirroring `get_speed_test_results` (fields: `config_entry_id`, `config_entry_name`, `wan_uuid`, `wan_name`, `limit`, `refresh`).

### Phase 4 — Docs + tests + update

- [x] `docs/REVERSE_ENGINEERING_WORKFLOW.md`: add an Internet Quality section / Finding documenting `networkMonitorData` + `events` `ping_RTT`/`ping_lossrate`, value granularity, and worst-value-hour note.
- [x] `docs/USER_GUIDE.md`: document the new sensors and the report service.
- [x] README bullet under Appliance & visibility.
- [x] Tests: `test_client.py` (extraction), `test_sensor.py` (entity states), `test_integration_manager.py` (manager getters + cache refresh), `test_services.py` (report service). (No `test_coordinator.py` exists; the coordinator refresh wiring is covered indirectly by the existing `test_init.py`/`test_services.py` setup paths.)
- [x] `quality_scale.yaml`: the feature is fully implemented, tested, and documented, so the existing `done` statuses remain accurate — no `todo`/`exempt` change is required.

### Phase 4.1 — Service metadata remediation (done)

- [x] `services.yaml`: added `name`/`description` to `config_entry_id`/`config_entry_name` for all services that expose them; added the fields to `pause_rule`/`resume_rule` (their schemas/handlers already supported multi-entry targeting via `_get_loaded_entry`).
- [x] `translations/en.json`: added the `get_internet_quality_report` service translation (name, description, all field translations).
- [x] Verified via a systematic cross-check that every service in `services.yaml` has a matching `en.json` entry and every field has a translation.

## 6. Validation strategy

- `python -m ruff check .` && `python -m ruff format .`
- `python -m mypy custom_components/firewalla_local`
- `python -m pytest tests/ -v`
- Live pull on the connected dev box to (a) confirm the response schema (Phase 1 gating) and (b) sanity-check sample values / cadence after implementation.

## 7. References

- `docs/REVERSE_ENGINEERING_WORKFLOW.md` — runtime data model (`internalSpeedtestResults`), `networkMonitorData.wanStatus` usage.
- `plans/completed/NETWORK_MODEL_COMPLETED.md` — WAN interface status source.
- `custom_components/firewalla_local/api/client.py` — `_extract_speed_test_records`, `async_run_internet_speed_test`, `async_get_wan_events_payload`, `_async_send_local_message_data`.
- `custom_components/firewalla_local/sensor.py` — `FirewallaWanSpeedTestSensor` per-WAN pattern.
- `custom_components/firewalla_local/managers/integration_manager.py` — `get_speed_test_results`.
- `.tmp/firewalla_protocol_capture.decoded.txt` — the `networkMonitorData` and `events` `ping_RTT`/`ping_lossrate` request captures.
- Issue #42.