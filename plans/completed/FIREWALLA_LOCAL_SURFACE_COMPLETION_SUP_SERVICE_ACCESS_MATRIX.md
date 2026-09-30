# Supporting note: Service access matrix (Phase 1 reference)

## Purpose

Provide the complete classification of Firewalla Local services for Phase 1 of `FIREWALLA_LOCAL_SURFACE_COMPLETION_COMPLETED.md`, and record the gating decision and its rationale in one place so the gate is declared rather than implied.

Source of truth for the live catalog: `_SERVICE_REGISTRATIONS` in `custom_components/firewalla_local/services.py` (22 services at time of writing). Verify the count before implementing — do not treat this table as authoritative if the registry differs.

## Why gating is safe (verified)

`homeassistant/helpers/service.py::_async_admin_handler` enforces the admin check **only when `call.context.user_id` is set**:

- **No user context** (automations, scripts, other integrations) → check skipped → call proceeds. **Existing automations are unaffected.**
- **Admin user context** → call proceeds.
- **Non-admin user context** → `Unauthorized` is raised.

`async_register_admin_service` accepts `schema`, `supports_response` and `description_placeholders`, so it is a drop-in for the existing registrations. This is what makes the change non-breaking in practice — and it is the one behaviour that must be asserted in tests rather than assumed.

## Category 1 — Read/report (leave open, except the two flagged)

All are `SupportsResponse.ONLY`.

| Service | Gate | Note |
|---|---|---|
| `get_network_segment_report` | open | selector-based over registry-resolved data |
| `get_network_segment_usage` | open | includes top talkers/apps — feeds dashboards |
| `get_speed_test_results` | open | historical read |
| `get_internet_quality_report` | open | historical read |
| `get_time_usage_report` | open | watched-user usage history |
| `get_wan_data_usage` | open | usage history |
| `get_wan_events` | open | WAN event timeline |
| `get_wireless_status` | open | SSID/AP inventory |
| `get_runtime_inventory` | **ADMIN** | returns the full rule/group/user inventory |
| `get_host_name_mapping` | **open (decided)** | host identity records are already effectively public through exposed entities; gating would break dashboards and LLM/display consumers for no real gain |

**Decision (resolved):** gate **`get_runtime_inventory`**, do **not** gate **`get_host_name_mapping`**. The asymmetry is deliberate — the first returns the complete rule/group/user inventory, the second returns host identity records that already surface through entities. Record the rationale in `docs/USER_GUIDE.md` so it does not read as an oversight.

**Consequence for Phase 4:** `get_runtime_inventory` will require admin at the service layer, so its LLM tool can only succeed for an admin caller. State that in the tool description rather than treating it as a defect.

## Category 2 — Network/device configuration (gate: admin)

| Service | Why |
|---|---|
| `set_host_name` | mutates box configuration |
| `set_host_dns_hostname` | mutates box configuration |
| `set_host_device_type` | mutates box configuration |
| `set_host_notify_when_next_online` | mutates box configuration |
| `set_host_notify_when_next_offline` | mutates box configuration |
| `set_host_dhcp_reservation` | mutates DHCP reservations |
| `delete_host` | **destructive** — already requires `confirm: true`; admin is additive |
| `wake_host` | sends a network packet on demand |

## Category 3 — Policy and radio control (gate: admin)

| Service | Why |
|---|---|
| `pause_rule` | changes firewall policy enforcement |
| `resume_rule` | changes firewall policy enforcement |
| `set_ssid_paused` | disables wireless |

## Category 4 — Resource-consuming (gate: admin)

| Service | Why |
|---|---|
| `run_internet_speed_test` | saturates the WAN on demand; can be triggered repeatedly |

## Summary

| Category | Count | Gate |
|---|---|---|
| Read/report | 10 | `get_runtime_inventory` is **admin**; the other 9 stay open |
| Mutating | 12 | admin |

**Total admin-gated: 13.**

## Implementation shape

Extend the registration table so the gate is data, not scattered logic:

- add `admin: bool` to the `FirewallaServiceRegistration` tuple type alias
- add the field to all entries in `_SERVICE_REGISTRATIONS`
- have `_async_register_service` branch on it: `async_register_admin_service` when true, `hass.services.async_register` when false
- leave the `hass.services.has_service` idempotency guard and `async_remove_services` unchanged — neither depends on which path registered the service

## Tests (required)

Cover all three call contexts for at least one gated service:

1. admin user context → succeeds
2. non-admin user context → `Unauthorized`
3. **no user context (automation-style) → succeeds** — this is the regression guard for existing automations
