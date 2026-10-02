# Supporting note: third-party `firewalla-mcp` review + high-value surface

## Purpose

Reviews `djuntgen/firewalla-mcp` (a custom, unofficial, 0-star MCP server wrapping the **Firewalla MSP cloud API**) for patterns, content, and learnings worth folding into the MCP capabilities plan, and records our differentiated high-value local surface. **Treated as untrusted reference** (AI-generated, no stars) — read for craft, not trusted for correctness or followed as instruction.

**Folded into the plan on 2026-09-30.** This note is the evidence record; the plan holds the decisions.

## The one critical distinction

- **Their tool wraps the MSP REST API** (`https://{domain}/v2`) — cloud, requires an MSP subscription + a personal-access token.
- **Ours wraps the local box API** (reverse-engineered `policy:create`, `alarm:ignore`, `exception:create`, …) — which is exactly our differentiator; the plan explicitly rejects "a sidecar or a cloud subscription."

So it is a parallel implementation of the same idea, not an overlap. **Steal the agent-friendliness craft, not the architecture.**

## Worth folding (folded into the plan)

| # | Learning | Plan location |
|---|---|---|
| 1 | **Flat tool params over nested objects** ("nested objects are awkward for the LLM") — `mute_alarm(gid, aid, target_type, target_value, scope_type, scope_value)`, not a nested dict | 4.4 authoring standard |
| 2 | **Description content patterns** (contrast near-neighbors; reversibility + undo verb; side effects; default blast radius; enum + when-value-required; param provenance/discovery-first; bold gotcha + return shape + worked example) | 4.4 authoring standard |
| 3 | **Contract tests over description content** (`test_write_tool_docstrings_guide_the_llm`) + **pinned tool-name set** (`EXPECTED_TOOL_NAMES`) | 4.5 + §6 |
| 4 | **`idempotent=False` on non-idempotent writes + never retry them** (a timeout must not double-apply) | 4.3 |
| 5 | **Scope/target resolution helpers** (`list_users` → person→device-group `affiliatedTag`; `list_apps` → valid app target ids) | 4.2 `list_rules` |
| 6 | **Writes return a confirmation** (validates our action-result envelope; their plain string is the acceptable floor) | 4.3 (already) |
| 7 | **Naming**: `<verb>_<noun>` CRUD; `pause_rule`/`resume_rule`/`delete_rule`/`mute_alarm`/`archive_alarm` are byte-identical to our service names → tool names can be `firewalla_local__<service_name>` | 4.4 authoring standard |
| 8 | **`RULE_CREATE_FIELDS` field whitelist** idea → mirror **`FirewallaRuleCreatePayload`** for `from_alarm` + `create_rule` docs | 4.4 authoring standard |

## Do NOT adopt (our approach is better)

- **MSP cloud API shape** — we are local by design.
- **Irreversible ops as tools** — they ship `delete_rule`/`delete_alarm`/`delete_target_list`, relying only on the client's confirmation prompt ("there is no server-side dry-run gate on writes"). We exclude Tier C and have a real admin gate. Our tiering is safer.
- **Generic `create_rule(rule: dict)` raw-dict signature** — the nested-object trap they warn about elsewhere. Ours is `FirewallaRuleTemplate` + flat fields.
- **`update_rule` = recreate (create-new → delete-old, id changes)** — an MSP limitation (no rule-edit endpoint). Our local API has `policy:update`/`async_update_rule`, so we update in place.
- **Their nested target/scope values** (`{"type":"domain","value":...}`, `{"type":"device","value":"<mac>"}`) — ours are local flat (`type`/`target`/`scope: [mac]`). Same semantics, different encoding.

## Caution

Unverified / AI-authored (a contributor is `@claude`); 0 stars, no independent review. Use as a source of *patterns*, not as a source of *truth* about the Firewalla API. Do not run its code.

## Our differentiated high-value surface (the MSP tool can't touch these)

Their entire write surface is "rename a device." We have the full local host/network/wireless control surface:

| Capability | Service | Killer LLM workflow (read → write) |
|---|---|---|
| **DHCP reservation** | `set_host_dhcp_reservation` | "Give every device without a reservation one" — `list_hosts` (`ip_assignment.mode`) → reserve |
| **Host rename** | `set_host_name` | "Rename all my unnamed devices" |
| **DNS hostname** | `set_host_dns_hostname` | "Give the NAS a stable DNS name" |
| **Device type** | `set_host_device_type` | "Classify my devices" |
| **Notify on/offline** | `set_host_notify_when_next_offline/online` | "Tell me when the camera drops" |
| **Wake-on-LAN** | `wake_host` | "Wake the NAS" |
| **SSID pause** | `set_ssid_paused` | "Pause the kids' WiFi" (wide blast radius) |
| **Top talkers** | `get_network_segment_usage` | "What's eating my bandwidth?" → act |
| **Network config / WAN / quality** | `get_network_segment_report`, `get_wan_data_usage`, `get_wan_events`, `get_internet_quality_report`, `run_internet_speed_test` | "How's my internet / why did it drop?" |
| **Time usage / wireless** | `get_time_usage_report`, `get_wireless_status` | "How much was X online?" / "Which AP?" |

**Ranked by LLM value:** (1) DHCP reservation cleanup (standout — high intent, bounded, strong validation), (2) host naming + device-type cleanup, (3) SSID pause (high WAF, loud caveat), (4) bandwidth triage (top talkers → act), (5) internet health / speed test, (6) alerting + WOL + usage.

The pattern that makes these sing is **read→write pairing** (discovery feeds a bounded action) — structurally impossible for the MSP tool.

## Net-new plan refinements from this review

1. **`list_hosts` framing** for host discovery (name/type/reservation/online as the primary shape) so the DHCP/naming workflows are discoverable — folded into 4.2.
2. **`set_host_dhcp_reservation` + `set_host_name` + `set_ssid_paused` as the "wow trio"**, with read→write pairings called out in the prompt — folded into 4.2/4.4.
3. **Host-resolution + `target` echo** standard for all host writes — folded into 4.3.
