# Initiative: Unified Network Model & Interface Entities (Feature Request #34)

## 1. Initiative snapshot

- **Source:** `ccpk1/firewalla-local-ha` issue #34 — *"[Feature]: LAN Interface Details"* (label: `enhancement`).
- **Requested capability:** A Home Assistant dashboard surface showing per-interface detail for **every network kind on the box** — LAN, VLAN, VPN, and WAN — including type, associated ports/VLAN, IPv4/IPv6 addressing, DHCP, traffic/usage, and (once protocol-confirmed) advanced options (mDNS Relay, SSDP Relay, Block ICMP).
- **Current state (2026-08-26):** Initiative **complete**. Delivered across three commits on `ccpk1/issue34`:
  - `c73b2f0` — unified network inventory + model + per-network status entities (Phases 1-4 + 5A).
  - `3ccb541` — `get_network_segment_report` folds the unified detail (kind, VLAN ID, ports, advanced options, device count, windowed usage) into one report (Phase 5B).
  - `49b760d` — WAN network entities surface confirmed current-month usage under a distinct `monthly` key.
  No separate `get_network_report`/`get_network_usage` services were added. Per-host windowed usage was investigated and intentionally **not** surfaced (the `item=intf`/`flowsummary` sources are raw scalars with an unspecified time basis; the app's per-device 30d/24h/60m windows come from an unconfirmed endpoint).
- **Branch context:** `ccpk1/issue34`; manifest version `1.3.0-beta.1` (target release).

## 2. Scope and non-goals

**In scope**
- Introduce a **unified `FirewallaNetwork` model** (one abstraction for LAN, VLAN, VPN, WAN) that mirrors the manufacturer's intended organization shown in the app.
- Refactor the two parallel network-inventory walkers (`_collect_wan_interfaces` and `_build_network_lookup`) into one common collector with a type discriminator.
- Expose per-network **read surfaces** (sensors/binary sensors) attached to the box device, covering: name, network kind, VLAN ID (when VLAN), associated ports (bond/ethernet), IPv4 and IPv6 addressing, DHCP, host/device count, traffic, and (protocol-confirmed) hosted counters/usage windows.
- Surface a **network usage** view mirroring the existing WAN usage pattern (`get_current_wan_usage_summaries` / `async_get_wan_data_usage_reports`), applied per-network for compiled (non-live) usage (e.g. last hour / last 24 hours).
- Add an **options toggle** to enable/disable creation of these entities (mirrors the existing `watched_devices` / `selected_rule_ids` optional patterns, so users without interest can opt out).
- **Confirm services are updated** to use the new unified model, and evaluate **complementary services** as an alternative surface for these features (see Phase 5).
- Keep everything translation-ready and quality-scale-tracked; update `docs/REVERSE_ENGINEERING_WORKFLOW.md` once mappings are confirmed.

**Non-goals (until evidence exists)**
- Creating LAN/VLAN/VPN entity surfaces from guessed fields. No surface is created until the mapping is confirmed (per the repo's reverse-engineering workflow).
- IPv6-only naming baked into entity object-ids or translation keys; use kind-agnostic names (we drop the earlier `ipv4` naming proposal).
- Any cloud-only control path; this integration stays local-first.
- Live streaming traffic per-device; only compiled usage windows mirror the WAN usage pattern.

## 3. Open questions / external dependencies

### Confirmed from the app + repo evidence

- **App organization (CONFIRMED from the app):** The main Network screen lists LAN (`LAN-MGMT`), VLAN (`VLAN60 IOT`), VPN (`AmneziaWG`), and WAN (`WAN-ONE`) together, each with **Type**, **associated ports** (`None` for VPNs), and **IP range**. Clicking any network shows a shared detail page: name, type, VLAN ID (if VLAN), ethernet ports (e.g. `LAG 1` = bond of `eth0`+`eth1`; `eth3` for WAN), IPv4/subnet/DHCP (mode, range, lease), IPv6, **mDNS Relay**, **SSDP Relay**, **Block ICMP**, plus a **network detail / usage** view (device count + data usage) and a link to related rules.
- **Raw sources (CONFIRMED in repo + live box pull 2026-08-25):**
  - **`networkConfig.interface` is the unified network registry**, keyed by category (`phy`, `bond`, `vlan`, `wireguard`, `amneziawg`, `openvpn`). Each entry has a `meta` block (`name`, `type`, `uuid`) plus kind-specific fields (`vid`, `intf`, `ipv4`, `enabled`). This single structure covers LAN, VLAN, VPN, and WAN.
  - `networkProfiles[uuid]` → per-network addressing (`intf`, `ipv4`, `ipv4Subnet`, `ipv4Subnets`, `gateway`, `dns`), keyed by the same `uuid` as `networkConfig.interface...meta.uuid`.
  - `networkConfig.dhcp[<intf>]` → gateway, subnet mask, lease, range, nameservers, searchDomain.
  - `networkConfig.mdns_reflector[<intf>].enabled` → **mDNS Relay (CONFIRMED)**; `networkConfig.icmp[<intf>].echoRequest` → **Block ICMP (CONFIRMED)**; `networkConfig.mroute[<intf>].routes[]` with `cidr: 239.255.255.250` → **SSDP Relay (CONFIRMED 2026-08-25)**.
  - `networkConfig.app.bond` + `networkConfig.interface.bond.<name>.intf` → **port/LAG bond mapping (confirmed)**; `nicStates` → per-port link state.
  - `networkMonitorData...wanStatus.{eth0: WAN-ONE, eth1: WAN-TWO}` → per-WAN interface status.
  - `wgPeers` / `awgPeers` → per-peer endpoint hosts (e.g. `chads-phone-awgvpn`), **NOT** the VPN network. The VPN **network** is `networkConfig.interface.wireguard/amneziawg/openvpn.<intf>.meta`.
- **Common unification opportunity (CONFIRMED):** `_collect_wan_interfaces` and `_build_network_lookup` are near-identical recursive "discover uuid+name from raw payload" walkers. Fold them into one `_collect_networks()` producing `tuple[FirewallaNetwork, ...]` with a kind discriminator derived from the `networkConfig.interface` category key.

### Open questions / assumptions

- **mDNS Relay / SSDP Relay / Block ICMP contract (ALL RESOLVED):** mDNS Relay = `networkConfig.mdns_reflector[<intf>].enabled`; Block ICMP = `networkConfig.icmp[<intf>].echoRequest`; SSDP Relay = `networkConfig.mroute[<intf>].routes[]` with SSDP multicast `239.255.255.250` (confirmed via live toggle on VLAN90). All three confirmed in live pulls.
- **VPN first-class model (RESOLVED):** VPN networks ARE in `networkConfig.interface` under `wireguard`/`amneziawg`/`openvpn` categories, each with a `meta` block. The app's "AmneziaWG" = `networkConfig.interface.amneziawg.awg0.meta` (uuid `876e3889-...`). `wgPeers`/`awgPeers` are per-peer endpoints, not the VPN network. VPN networks are now first-class in the unified model.
- **Compiled usage windows for non-WAN (RESOLVED, non-WAN only):** the `item=intf` payload returns per-network windows (`newLast24`/`last30`/`last60`/`last12Months`) for **non-WAN** kinds (LAN/VLAN/VPN). WAN has **no** per-WAN windowed source: its `item=intf` windows are all zero, the box-wide windows are aggregate (not per-WAN), and the WAN usage screen capture only fetches `monthlyDataUsageOnWans` + `last12monthlyDataUsageOnWans`. WAN windowed usage is deliberately not surfaced (see Per-network data usage).
- **Ethernet port / bond topology (RESOLVED):** `_enrich_network_ports` resolves per-kind ports from `networkConfig.interface`: a `phy` WAN is its device name (`eth0`); a bond uses its `intf` members (`['eth2','eth3']`); a VLAN dereferences its `intf` parent to the member ports; VPNs have none. Confirmed in live pulls (2026-08-25).
- **Entity volume / option default (ASSUMED):** A Gold with 6 VLANs + 1 LAN + 2 WAN + 2 VPN ≈ 11 networks × 2-3 entities ≈ ~30 entities. Private is acceptable but the **options toggle should default to create them** (user asked explicitly) while letting others opt out.

## 4. Phase summary table

| Phase | Goal | Key output |
| --- | --- | --- |
| 1 | Unified network inventory refactor | Single `_collect_networks()` + `get_networks()` with kind discriminator; remove duplicate walkers |
| 2 | Unified model + read surface | `FirewallaNetwork` model; per-interface entities (IPv4/IPv6/usage/device-count) attached to the box; translation-ready |
| 3 | Reverse-engineering + advanced options | Confirm `policy` fields (mDNS/SSDP/Block ICMP), ports/`LAG` mapping, compiled network usage path; update `REVERSE_ENGINEERING_WORKFLOW.md` |
| 4 | Options toggle + hardening | Options toggle for entity creation; orphan/reconcile patterns; tests + quality-scale updates |
| 5 | Service unification + complementary services | Update existing services to the unified model; add complementary network services; unify WAN/network resolution |

## 5. Per-phase details

### Phase 1 — Unified network inventory collector

- [x] Add a single `_collect_networks(data) -> tuple[FirewallaNetwork, ...]` in `managers/integration_manager.py` that walks the raw init payload for network identities **once**, covering LAN, VLAN, VPN, and WAN from `networkConfig.interface` (category-keyed: `phy`/`bond`/`vlan`/`wireguard`/`amneziawg`/`openvpn`) + `networkProfiles` + `networkMonitorData.wanStatus`. **Implemented** as a thin delegation to the shared pure `build_network_inventory` in `utils/network.py` (Option B — approved 2026-08-25).
- [x] Replace `_collect_wan_interfaces` and the `_build_network_lookup` logic with the unified collector, preserving existing behaviors (`get_available_wans`, `get_available_networks`) as thin wrappers so no existing surface breaks. **Implemented** — old walkers removed after differential tests passed.
- [x] Add a `network_kind` (lan/vlan/vpn/wan) discriminator to the model, derived from the `networkConfig.interface` **category key** (`phy`→wan, `bond`/`vlan`→lan/vlan, `wireguard`/`amneziawg`/`openvpn`→vpn), so downstream does not re-sniff the type. **Implemented** — `FirewallaNetworkKind` + `FirewallaNetwork` in `models.py`.
- [x] Add tests in `tests/components/firewalla_local/` asserting the unified collector returns the same LAN/VLAN/WAN identities the two old walkers produced separately (no regressions). **Implemented** — kind + differential + speed-test-fallback tests in `test_integration_manager.py`.
- [x] Update `helpers/runtime_inventory.py` (or a related helper) to report the unified network inventory in `get_runtime_inventory`. **Implemented** — additive `networks` list (uuid/name/kind) + markdown section; `network_count` preserved.
- [x] **Decision gate:** `get_networks()` returns a shared identity list for all network kinds; existing `get_available_wans()`/`get_available_networks()` return the same subsets as before. **Passed** — 245 tests green.
- [x] Note: translations and quality-scale updated only where behavior actually lands. **No translation/quality-scale change** — Phase 1 is identity-only, no user-facing surface.

### Phase 2 — Unified model + entity read surface

**Confirmed design (2026-08-25):**
- **One binary sensor per network** (`binary_sensor.<box>_<network_slug>`), modeled on the existing System Status binary sensor pattern: `is_on` = **network is configured/enabled** (`networkConfig.interface.<cat>.<name>.enabled`), consistent across LAN/VLAN/VPN/WAN, no extra live fetch. It will essentially always be on — acceptable.
- **All detail as attributes** on that single binary sensor: `network_kind`, `vlan_id`, `ports` (configured ports only, e.g. `["eth2","eth3"]` for the bond, `["eth0"]` for WAN, `[]`/`None` for VPNs — **not** up/down state), `ipv4_addresses`, `ipv4_subnets`, `ipv6_addresses`, `ipv6_subnets`, `gateway`, `dns`, `dhcp` summary, `device_count`, `mdns_relay`, `ssdp_relay`, `block_icmp`, `enabled`.
- **Port up/down stays at the box level:** the existing System Status binary sensor gains a single `ports` dict attribute (`{"eth0": "up", "eth1": "down", ...}`) from `nicStates[<port>].carrier` — a fixed, structured attribute (not dynamic per-port attributes), consistent with the existing `current_wan_usage`/`disk_usage_percent_by_mount` dict attributes.
- **No new platform** — extend `binary_sensor.py`. No `sensor.py` changes in Phase 2.
- **Options toggle**: default ON, opt-out (Phase 4); Phase 2 wires creation gated behind it.

- [x] Extend `FirewallaNetwork` in `models.py` with the confirmed geometry: `interface_name`, `vlan_id`, `ports`, `ipv4_addresses`/`ipv4_subnets`, `ipv6_addresses`/`ipv6_subnets`, `gateway`, `dns`, `dhcp` config, `device_host_count`, `enabled`, `mdns_relay`, `ssdp_relay`, `block_icmp`. **Implemented**.
- [x] Extend `build_network_inventory` (in `utils/network.py`) to populate the geometry from `networkConfig.interface` + `networkProfiles` + `networkConfig.dhcp` + `networkConfig.mdns_reflector` + `networkConfig.icmp` + `networkConfig.mroute` (SSDP). **Implemented**.
- [x] Add a `get_network_details()` (or extend `get_networks()`) manager surface returning the full per-network view; keep `get_networks()` as the identity list. **Implemented** — `get_networks()` now returns the enriched `FirewallaNetwork`.
- [x] Add a `FirewallaNetworkBinarySensor` in `binary_sensor.py` (one per network), `is_on` = `enabled`, attributes = full detail, attached to the box device via `build_device_info()`. **Implemented**.
- [x] Add the `ports` dict attribute to the existing System Status binary sensor from `nicStates`. **Implemented**.
- [ ] Add entity creation keyed by network identity, mirroring the existing per-WAN reconcile pattern (`async_reconcile_*_entities`), gated by the Phase 4 options toggle. **Partially implemented** — creation is keyed by network identity in `async_setup_entry`; the Phase 4 options-toggle gate is deferred to Phase 4.
- [x] New entity naming must be **kind-agnostic** — do NOT bake `ipv4`/`ipv6` into the unique-id object-id or translation keys. Use `TRANS_KEY_ENTITY_BINARY_SENSOR_NETWORK` + `TRANS_PLACEHOLDER_NETWORK_KIND` + `TRANS_PLACEHOLDER_NETWORK_NAME`; entity id uses the network slug (`vlan60_iot`, `lan_mgmt`, `wan_one`, `amnezia_wg`). **Implemented** — unique-id uses the network uuid; translation placeholders for kind + name; kind rendered as acronym and name suffix `Status` (see UX refinement).
- [x] Per-network entities attach to the existing box device (`build_device_info()`) — confirmed by the maintainer. **Implemented**.
- [x] Entity attributes carry: `network_kind`, `vlan_id`, `ports` (configured only), `ipv4_addresses`, `ipv6_addresses`, `dhcp` summary, `device_count`, `mdns_relay`, `ssdp_relay`, `block_icmp`, `enabled`. **Implemented.** `device_count` definition (confirmed 2026-08-25): count of non-Firewalla-vendor client hosts whose `host.intf` (network UUID) matches the network uuid; the Firewalla box is **excluded** (gateway device, not a client; its raw `intf` is volatile), and `Unknown` intf hosts are left uncounted. Recomputed each refresh via `get_networks()`.
- [ ] Entity count is gated/optional (see Phase 4); only surface entities when the option is on. **Deferred to Phase 4** (options toggle).
- [x] Update `translations/en.json` for new entities and attributes; regenerate `translations/en.json` via the develop script before tests. **Implemented** — added `network` entity + `ports` attribute translations directly to `en.json`.
- [x] Add tests for entity state/attributes/availability and for entry-scoped unique-IDs. **Implemented** — 3 new tests (network state+attrs, network name, system ports).
**Post-review bug fixes (landed 2026-08-25, validated live):**
On the running box the unified collector surfaced phantom WAN/parent-interface items (`binary_sensor.firewalla_wan_eth1/2/3` and `sensor.firewalla_eth1/2/3_speed_test_*`) and duplicated IPv4 fields. Root cause was traced from the live entity registry + captured init payload, then fixed at the single source of truth (`build_network_inventory`):
- **Phantom WANs:** the entire `phy` category was mapped to `FirewallaNetworkKind.WAN`, and the "skip unnamed ports" guard only checked for a missing `meta.uuid`. The live `phy.eth1/2/3` carry a `meta.uuid` but **no `meta.name`/`meta.type`**, so they slipped through as WAN networks. Fix: a `phy` entry is only a WAN network when the box marks `meta.type == "wan"`. Real networks always carry both `meta.name` and `meta.type`; unnamed physical ports are hardware, not user-facing networks.
- **IPv4 duplication (`ipv4_addresses == ipv4_subnets`) + null gateway:** `_collect_network_interface_entries` seeded `ipv4_addresses` from `networkConfig.interface.ipv4`, which is a **CIDR** (`192.168.254.1/27`), and `_enrich_network_addressing` only replaced it when empty — so the CIDR won and duplicated the subnet. Fix: prefer the bare `networkProfiles.ipv4` address, leaving CIDRs to `ipv4_subnets`; `gateway` now falls back to `networkConfig.dhcp[<intf>].gateway` (LANs expose the real gateway in dhcp, not in `networkProfiles.gateway`).
- **Removed redundant speed-test fallback in `get_available_wans()`:** it re-added phantom WAN identities from stale `internetSpeedtestResults` UUIDs. `get_networks()` is now authoritative.
- **Tests:** updated the two fallback tests to assert fallback removal, and added regression tests for unnamed-`phy` exclusion and bare-address/CIDR-subnet/dhcp-gateway addressing. **Validated:** ruff clean, mypy clean, 250 tests pass, and `build_network_inventory` on the live 2026-08-25 capture now yields exactly 10 user-facing networks with correct addressing.

### UX refinement (landed 2026-08-25, per maintainer review)

- **Entity naming:** the network binary-sensor display name now uses the kind **acronym** (`LAN`/`VLAN`/`VPN`/`WAN`, via `FirewallaNetworkKind.display_name`) instead of the raw lowercase value, and appends **"Status"** (name template `{network_kind} {network_name} Status`). Example: `Firewalla VLAN VLAN10 CORE Status`, entity_id `binary_sensor.firewalla_vlan_vlan10_core_status`. `unique_id` still uses the network uuid (`network_<uuid>_binary_sensor`) so identity is unchanged; only the object-id slug and display name gain the `_status` suffix.
- **SSDP default:** `ssdp_relay` now defaults to `False` instead of remaining `None`/unknown. Rationale: SSDP Relay is an explicit app toggle and the box only emits an `mroute` entry for interfaces carrying the SSDP multicast route, so an absent entry means the relay is off. `mdns_relay` and `block_icmp` already resolved to booleans because `mdns_reflector`/`icmp` list every interface. Live-validated: only `VLAN90 GUEST/DMZ` is `True`, all others `False`.
- **Block ICMP inversion:** the raw `networkConfig.icmp[<intf>].echoRequest` is the **inverse** of Block ICMP. `echoRequest` literally means "respond to ICMP echo (ping)"; the box clears it when the app's Block ICMP toggle is **on**. The code previously assigned `echoRequest` directly to `block_icmp`, so a network with Block ICMP On showed `False`. Fix: `block_icmp = not echoRequest`. Live-validated 2026-08-25: VLAN90 GUEST/DMZ (app shows Block ICMP On) → `echoRequest=false` → `block_icmp=True`; all other networks → `True`/`False` matching the app.
- **Port resolution (`ports` attribute):** previously `ports` was copied raw from `networkConfig.interface...intf`, so a WAN on a direct physical port (`phy/eth0`, no `intf`) reported `[]`, and VLANs reported their parent ref (`bond0`) instead of the members. Added `_enrich_network_ports` in `utils/network.py`, which resolves per kind: a `phy` WAN is itself the port (`eth0`); a bond lists its `intf` members (`['eth2','eth3']`); a VLAN dereferences its `intf` parent (a bond/phy) to the member ports; VPNs have none. Live-validated 2026-08-25: WAN-ONE→`['eth0']`, LAN-MGMT/VLANs→`['eth2','eth3']`, VPNs→`[]`.
- **IPv4 labels:** `ipv4_addresses`/`ipv4_subnets` stay plural — the model and attributes already carry `tuple[str, ...]`/lists and support multiple addresses per network (e.g. a WAN with several public IPs). No change needed.
- **Tests:** updated name/SSDP assertions, added `display_name` unit tests. **Validated:** ruff clean, mypy clean, 251 tests pass.
- **Naming rationale (`network_kind` vs `network_type`):** the attribute and placeholder stay `network_kind` because the value is the **derived granular discriminator** (`lan`/`vlan`/`vpn`/`wan`) from the `networkConfig.interface` **category key**, not the box's raw device `type` field. The raw `meta.type` / `item=intf` `type` is only `lan` or `wan` (every VLAN, VPN, and the LAN bond report `type='lan'`), so `network_type` would collide conceptually with that coarse raw field (also already used on `FirewallaNetworkSegmentView.network_type`). Display label reads "Network kind". If the maintainer prefers "Network type", only the label changes (not the key).

### Per-network data usage (landed 2026-08-25)

Per-network compiled usage is **confirmed for non-WAN networks** and surfaced on their binary sensors via a **single logic path** shared with the services:
- **Source (CONFIRMED 2026-08-25 live probes):** the `item=intf` payload (`async_get_network_interface_payload`) returns per-network usage windows for **non-WAN** kinds (LAN/VLAN/VPN): `newLast24`, `last30`, `last60`, `last12Months`, each with `totalDownload`/`totalUpload` scalars, plus `flows.download/upload` per-host rankings and per-host `hosts` byte totals. This is already normalized by `_build_network_segment_view` / `async_get_network_interfaces()` (used by `get_network_segment_usage`).
- **WAN deliberately excluded (CONFIRMED 2026-08-25):** the WAN's `item=intf` windows are **all zero**, and the app's WAN data-usage capture shows it only fetches `monthlyDataUsageOnWans` + `last12monthlyDataUsageOnWans` — there is **no per-WAN windowed usage source**. The box-wide init-payload windows (`newLast24`/`last60`/`last30`/`last12Months`) aggregate **all** box traffic; they equal WAN-ONE only because the live box has a single WAN, so attributing them to a WAN would be wrong on a multi-WAN box. WAN `network_usage` is therefore left empty rather than showing a potentially-incorrect aggregate (per the plan's "don't invent a surface without confirmation" rule). WAN monthly totals remain available via the existing System Status `current_wan_usage` / `get_wan_data_usage`.
- **Single logic path:** `FirewallaNetwork` gained a `usage: FirewallaNetworkUsageSummary | None` (`last_24h`/`last_60m`/`last_30d`/`last_12m` each with download/upload bytes). The integration manager owns a cached per-uuid usage map (`_network_usage_by_uuid`), populated by `async_refresh_network_usage()` — a resilient `asyncio.gather(..., return_exceptions=True)` over `item=intf` for non-WAN networks — and the coordinator calls it each poll alongside `handle_refresh`. Entities and services both consume manager views; no duplicate parsing.
- **Resilience:** per-network fetch failures are caught (live probe: **OpenVPN returns a 500** for `item=intf`; AmneziaWG/LAN/VLAN/WAN work). A failing network keeps its previous usage rather than breaking the batch.
- **Entity attribute:** `network_usage` = `{last_24h, last_60m, last_30d, last_12m}` each `{download_bytes, upload_bytes}` (bounded; per-host/app breakdowns stay on the service surface). Translation-ready (`network_usage`).
- **Tests:** manager unit tests (totals merge, per-network failure resilience, WAN exclusion) + binary-sensor attribute tests. **Validated:** ruff clean, mypy clean, 255 tests pass, live probe confirms non-WAN networks populate all four windows and WAN stays empty.

### Phase 3 — Reverse-engineering confirmation + advanced protocol

- [x] Confirm the field path for **SSDP Relay** (mDNS Relay = `networkConfig.mdns_reflector[<intf>].enabled`, Block ICMP = `networkConfig.icmp[<intf>].echoRequest`, SSDP Relay = `networkConfig.mroute[<intf>].routes[]` SSDP multicast `239.255.255.250` — all **confirmed**); record with a field-mapping table in `docs/REVERSE_ENGINEERING_WORKFLOW.md` (new section requested by the maintainer).
- [x] Confirm **Ethernet ports / bond → LAG mapping** (associated ports for LAN/VLAN = `LAG 1` / `eth3` for WAN, `None` for VPN) from raw `networkConfig.interface.bond.<name>.intf` + `networkConfig.app.bond`. Resolve the bond→member-port map. **Resolved** — `_enrich_network_ports` (see UX refinement).
- [x] Confirm **compiled device/data usage windows (UNKNOWN)** reachable for networks in the local runtime, mirroring the existing WAN usage pattern (`monthlyDataUsageOnWans` in init payload and the `monthly`/`total` fetch). If only WAN has compiled usage, record that and scope network usage to WAN reusing the existing WAN usage. Do not invent a network usage surface without confirmation. **Resolved** — `item=intf` provides per-network windows for **non-WAN** kinds; surfaced via `network_usage` attribute. WAN windowed usage has **no confirmed per-WAN source** (its `item=intf` is zero; the box-wide windows are aggregate) and is deliberately excluded (see Per-network data usage).
- [x] Confirm `polling`/write for advanced options only if the app exposes toggles and we want them reflected; otherwise read-only for now. **Resolved** — read-only surface; no write path added.
- [x] Update `docs/REVERSE_ENGINEERING_WORKFLOW.md` with a **new section** documenting the unified Network mapping: app screen → raw field → normalized model → entity attribute. The maintainer explicitly requested this step. **Implemented** — added `## Unified Network model` under `## Confirmed protocol baseline` (network identity/kind, detail fields, advanced options, data usage, design notes); verified against live captures and re-read the surrounding sections.
- [x] If the VPN first-class model is confirmed, document `networkConfig.interface.wireguard/amneziawg/openvpn`; otherwise record as an open question. Do not guess. **Done** — VPN categories documented in the REVERSE_ENGINEERING_WORKFLOW section.

### Phase 4 — Options toggle + hardening

- [x] Add a **general options toggle** (`enable_network_entities` in the Config Flow system settings) controlling whether network/interface entities are created. Default ON (confirmed 2026-08-25), opt-out for users who don't want ~11 binary sensors (one per network). **Implemented** — `CONF_ENABLE_NETWORK_ENTITIES` + `DEFAULT_ENABLE_NETWORK_ENTITIES=True`; boolean in the System Settings form; translation label + description.
- [x] Wire the toggle into `coordinator.async_handle_entry_reload_requested` + `integration_manager` so toggling/reload reconciles (creates / orphans / removes) network entities using the existing `ORPHAN_POLICY_RETAIN_UNAVAILABLE_UNTIL_DESELECTED` pattern (borrow the WAN speed-test sensor reconcile). **Implemented** — `binary_sensor.async_setup_entry` gates network-entity creation on `get_enabled_network_entities(entry.options)`; `integration_manager.async_reconcile_network_entities` removes registry entries for hidden networks; the coordinator tracks the prior toggle value and reloads the entry when it changes so a toggle takes effect. On disable, `__init__` reconcile passes no expected networks → network entities are **removed from the registry** (clean, not orphaned).
- [x] Keep per-network entities stale when de-selected (consistent with existing watched/selected surfaces). **Amended to platinum** — instead of orphaning/unavailable, disabling the toggle reconciles: `async_reconcile_network_entities(())` **removes** the network entities from the entity registry, matching the existing `async_reconcile_speed_test_sensor_entities`/`async_reconcile_rule_switch_entities` cleanup pattern.
- [x] Add tests for toggle on/off and reconcile (create-on-enable, remove-on-disable, no collisions). **Implemented** — create-on-enable (3 network entities), not-created-on-disable (0), and reconcile removes stale entries in `test_binary_sensor.py`; reload-on-toggle-trigger in `test_init.py`.
- [ ] Update `quality_scale.yaml` honestly (`todo`/`exempt` until behavior exists) and release notes for the new surface.

### Phase 5 — Service unification, complementary services, and post-refactor cleanup

**Phase 5A — Post-refactor orphan/duplication cleanup (2026-08-25 audit):** The unified-network refactor left some parallel code behind. Audit (verified via usage reads) found:
- [x] **`_resolve_network_display_name` duplicated** — byte-identical in `api/client.py` (method) and `utils/network.py` (module). Delete the client method; import the module function. Low risk. **Done** — client method removed; client now imports and calls the shared module function.
- [x] **`_build_network_lookup` + `_merge_network_config_lookup` (client.py) duplicate `build_network_inventory`** — both discover network uuid→name from `networkProfiles` + `networkConfig.interface`. This is the exact parallel walker the refactor was meant to remove but is still live for host/rule name resolution. **Done** — `_build_network_lookup` is now a thin adapter over `build_network_inventory`, mapping both `network.uuid → name` and `interface_name → name` (the latter preserves VPN-peer names keyed by intf, e.g. `awg0`). Removed `_merge_network_config_lookup` and the client `_resolve_network_display_name` method, plus orphaned `_RAW_INTERFACE_KEY`/`_RAW_META_KEY` constants. Fixed an awg test fixture that used the wrong category key (`amnezia` → real `amneziawg`) and the loose name (`Amnezia` → real `AmneziaWG`).
- [x] **Integer normalization triplicated** — audited and **intentionally distinct**, do NOT merge. `_normalized_int_value` (im) accepts `float`; `_normalized_int` module (network.py) does not — merging would change float handling for usage windows. `_optional_int` (bool→int) vs the bool→None family differ on purpose (usage totals vs byte counts). Kept local and correct rather than forcing cross-module coupling.
- [x] **`_normalized_dict` duplicated** — audited and **intentionally distinct**: `utils/network.py` returns `dict or None` (shallow), while `services.py` does field-by-field type-filtered normalization. Not safe to merge; kept separate.
- [x] **Raw-key constants triplicated** — **partially done**: removed orphaned `_RAW_INTERFACE_KEY`/`_RAW_META_KEY` from `api/client.py` after the lookup adapter (they had no remaining uses). The remaining raw-key literals are independently referenced by each file (not orphaned), so a full single-source move would add cross-module coupling with little behavioral gain; left as-is.
- [x] **Verified NOT orphaned (no action):** `FirewallaNetworkSegment(View)`, `FirewallaNetworkUsageWindow/Summary` fields, speed-test fallback helpers (already removed), no unused imports, no dead model fields. **Phase 5A complete** — the one substantive parallel walker is eliminated; remaining private helpers are verified distinct (not duplicated) and left in place on purpose.

**Phase 5B — Service surface completes the unified network detail (implemented 2026-08-26):**

The review decision was to **not** add separate `get_network_report`/`get_network_usage`
services. `get_network_segment_report` is the single network-detail report; it now
folds in the remaining unified `FirewallaNetwork` fields so everything is in one place.

- [x] **Fold the unified network fields into `get_network_segment_report`** so one call
  returns the full detail: `target.kind` now uses the granular `network.kind`, and the
  `summary`/`configuration`/`usage` sections gain the fields the old report was missing —
  `device_host_count`, `kind`, `vlan_id`, `ports`, `enabled`, `mdns_relay`, `ssdp_relay`,
  `block_icmp`, and a compact `sections.usage` window summary (`last_24h`/`last_60m`/
  `last_30d`/`last_12m`, from the same cached `FirewallaNetwork.usage` that feeds the
  entity attribute). The handler already resolves a `FirewallaNetwork`, so no extra
  protocol calls are added.
- [x] **Do NOT add `get_network_report` / `get_network_usage`.** The segment report now
  carries the overview + summary usage; `get_network_segment_usage` remains the deep
  per-device/app/series drill-down. No new service names, schemas, or envelope shapes.
- [x] **Honest protocol usage:** `sections.usage` stays empty (null windows) when the
  poll has no per-network usage (e.g. WAN, or before `async_refresh_network_usage` runs),
  with a provenance entry documenting the `item=intf` source. Fields are always present
  (stable schema), never fabricated.
- [x] **Tests:** updated `test_get_network_segment_report_service_returns_configuration_report`
  to assert the new `kind`, `summary.device_host_count`, folded `configuration` fields,
  the `sections.usage` shape, and the `usage` provenance entry.
- [x] **Docs:** updated `USER_GUIDE.md` (report returns full detail; usage is the drill-down)
  and `REVERSE_ENGINEERING_WORKFLOW.md` (single-logic-path now includes the report usage
  section). `services.yaml` unchanged (input-field-focused).
- [x] **Validated:** ruff, mypy, and full pytest pass.

## 6. Validation strategy

- Run `python -m ruff check .` and `python -m ruff format .`.
- Run `python -m mypy custom_components/firewalla_local`.
- Run `python -m pytest tests/ -v` (focused scopes allowed during iteration; final report states what was/wasn't run).
- Confirm no root-level module drift (network logic lives in an owned manager/helper, never root-level).
- Confirm translations regenerated and quality-scale honest; reverse-engineering chapter updated for every newly confirmed field mapping.
- Confirm entity surface is kind-agnostic (no `ipv4`/`ipv6` baked into ids).
- Confirm existing services still resolve the same WAN/network identities after the unified selector refactor (no regressions).

## 6a. Review findings (traps & opportunities to address before handoff)

- **Trap — service selector duplication:** `_resolve_requested_wan` and `_resolve_requested_network` duplicate the same uuid/name + conflict/ambiguous/not-found logic. Unify them (Phase 5) or the new unified model will leave two parallel resolvers.
- **Trap — WAN vs network service split:** `get_wan_data_usage`, `get_network_segment_report`, `get_network_segment_usage`, `get_speed_test_results`, `get_wan_events` all target a single kind. The unified model should let any service target any network kind, or we keep a fragmented service surface.
- **Trap — entity volume:** ~30 entities on a Gold. The options toggle (Phase 4) must default ON but be easy to opt out; reconcile must not leave stale entities when toggled off.
- **Trap — protocol unknowns:** non-WAN compiled usage and any unobserved `networkConfig.interface` categories (beyond `phy`/`bond`/`vlan`/`wireguard`/`amneziawg`/`openvpn`) remain. Do not expose these as entities/attributes/services until Phase 3 confirms them (per the repo's reverse-engineering workflow). mDNS Relay, SSDP Relay, Block ICMP, VPN networks, and port/LAG mapping are all confirmed (2026-08-25 live pulls).
- **Trap — `policy` passthrough:** `FirewallaNetworkSegmentView.policy` is currently raw. If we expose it as an attribute before parsing, we leak unnormalized data. Parse confirmed fields (mDNS/SSDP/ICMP) in Phase 3 before surfacing.
- **Opportunity — unified selector:** Folding `_resolve_requested_wan`/`_resolve_requested_network` into one resolver lets services target any network kind uniformly and removes duplicate code.
- **Opportunity — complementary services (RESOLVED — not added):** A separate `get_network_report`/`get_network_usage` was considered and rejected. `get_network_segment_report` already covers the app's network-detail page (kind, ports, advanced options, device count, usage); adding parallel unified services would duplicate it. The overview + summary usage lives in the report; `get_network_segment_usage` stays the drill-down.
- **Opportunity — reuse WAN usage pattern:** The existing `get_current_wan_usage_summaries`/`async_get_wan_data_usage_reports` pattern is the template for any confirmed non-WAN compiled usage; reuse it rather than inventing a new shape.
- **Opportunity — reconcile pattern reuse:** The existing `async_reconcile_*_entities` (WAN speed-test, device-tracker, rule-switch) is the template for network-entity lifecycle; reuse it for the options toggle.

## 7. References

- Issue: `ccpk1/firewalla-local-h#34` — *"LAN Interface Details"* (unified/reworked).
- App evidence: Network screen listing LAN/VLAN/VPN/WAN each with type + ports + IP range; network detail page (name, type, VLAN ID, ports, IPv4/IPv6/DHCP, mDNS Relay, SSDP Relay, Block ICMP, network usage + device count + related-rules link).
- `docs/REVERSE_ENGINEERING_WORKFLOW.md` — finding + capture workflow + the new unified Network mapping section.
- `custom_components/firewalla_local/models.py` — `FirewallaNetworkSegment`, `FirewallaNetworkSegmentView`, `FirewallaWanDataUsage*`.
- `custom_components/firewalla_local/managers/integration_manager.py` — `_collect_wan_interfaces`, `_build_network_lookup`, `get_available_wans`, `get_available_networks`, `async_get_network_interfaces`, `async_get_wan_data_usage_reports`, `get_current_wan_usage_summaries`.
- `custom_components/firewalla_local/api/client.py` — `async_get_network_interface_payload` (`item=intf`), `_build_network_lookup`, `async_get_monthly_wan_usage_payload`, `async_get_last12_monthly_wan_usage_payload`.
- `custom_components/firewalla_local/services.py` — existing network-segment report/usage helpers (as reference for the usage surface); WAN/network service handlers + `_resolve_requested_wan`/`_resolve_requested_network` selectors (Phase 5 targets).
- `custom_components/firewalla_local/config_flow.py` / `coordinator.py` — options flow + reconcile/orphan patterns (Phase 4).
- `plans/completed/NETWORK_MODEL_SUP_REVERSE_ENGINEERING.md` — supporting note for confirmed vs intended field mapping.