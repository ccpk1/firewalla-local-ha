# Supporting Note: Unified Network Model — Reverse-Engineering Field Mapping

**Initiative:** `NETWORK_MODEL_COMPLETED.md` (issue #34)
**Status:** Completed — confirmed vs. intended field mappings. Update as protocol evidence lands.

## Purpose

This note tracks the mapping between the **Firewalla app's unified Network concept**, the **raw local runtime fields**, and the **proposed normalized model / entity attributes**. It is the source of truth for the `docs/REVERSE_ENGINEERING_WORKFLOW.md` section that Phase 3 must add.

## Confirmed discovery (2026-08-25, live box pull)

A live runtime pull (`.artifacts/runtime-pull/20260825-145011/runtime_init.json`) from the maintainer's Firewalla Gold confirmed the **unified network registry** lives in `networkConfig.interface`, keyed by **category** (`phy`, `bond`, `vlan`, `wireguard`, `amneziawg`, `openvpn`). Each entry carries a `meta` block with `name`, `type`, and `uuid`, plus kind-specific fields (`vid`, `intf`, `ipv4`, `enabled`).

Observed live inventory (9 networks):

| Interface | Name | `meta.type` | Category | VLAN ID | Notes |
| --- | --- | --- | --- | --- | --- |
| `eth0` | WAN-ONE | `wan` | `phy` | — | active WAN |
| `eth1`/`eth2`/`eth3` | (unnamed) | — | `phy` | — | physical ports |
| `bond0` | LAN-MGMT | `lan` | `bond` | — | bond of `eth2`+`eth3` |
| `bond0.10` | VLAN10 CORE | `lan` | `vlan` | 10 | |
| `bond0.20` | VLAN20 CORE-AUX | `lan` | `vlan` | 20 | |
| `bond0.60` | VLAN60 IOT | `lan` | `vlan` | 60 | |
| `bond0.70` | VLAN70 IOT-AUX | `lan` | `vlan` | 70 | |
| `bond0.90` | VLAN90 GUEST/DMZ | `lan` | `vlan` | 90 | |
| `wg0` | WireGuard | `lan` | `wireguard` | — | VPN server |
| `awg0` | AmneziaWG | `lan` | `amneziawg` | — | VPN server |
| `tun_fwvpn` | OpenVPN | `lan` | `openvpn` | — | VPN server (disabled) |

**Key findings:**

- **VPN networks ARE in `networkConfig.interface`** under `wireguard`/`amneziawg`/`openvpn` categories, each with a `meta` block (`name`, `uuid`, `type`). The app's "AmneziaWG" network = `networkConfig.interface.amneziawg.awg0.meta` (uuid `876e3889-...`). This **resolves the VPN question** — VPN networks are first-class in the same unified structure as LAN/VLAN/WAN.
- **`meta.type` is the kind discriminator**, but it is `lan` for LAN/VLAN/VPN and `wan` for WAN. The **category key** (`phy`/`bond`/`vlan`/`wireguard`/`amneziawg`/`openvpn`) is the reliable kind signal for LAN vs VLAN vs VPN.
- **`networkProfiles[uuid]`** carries per-network addressing (`intf`, `ipv4`, `ipv4Subnet`, `ipv4Subnets`, `gateway`, `dns`) and is keyed by the same `uuid` as `networkConfig.interface...meta.uuid`. It is the identity/name/address source that ties everything together.
- **Advanced options are confirmed in `networkConfig`:** `mdns_reflector[<intf>].enabled` (mDNS Relay) and `icmp[<intf>].echoRequest` (Block ICMP). SSDP relay not yet located (likely `networkConfig` elsewhere or `item=intf`).
- **`networkConfig.app.bond`** = `[["eth2","eth3"]]` confirms the WAN LAG; `nicStates` gives per-port link state.
- **`wgPeers`/`awgPeers`** are per-peer endpoint hosts (e.g. `chads-phone-awgvpn`), NOT the VPN network. The VPN **network** is `networkConfig.interface.<vpncategory>.<intf>.meta`.

## App screen → raw field → normalized model → entity attribute

### Network list (main Network screen)

| App column | Raw source | Normalized model | Entity attribute |
| --- | --- | --- | --- |
| Network name | `networkConfig.interface.<cat>.<name>.meta.name` / `networkProfiles[uuid]` | `FirewallaNetwork.name` | entity name placeholder |
| Type (LAN/VLAN/VPN/WAN) | `networkConfig.interface` **category key** (`phy`/`bond`/`vlan`/`wireguard`/`amneziawg`/`openvpn`) | `FirewallaNetwork.kind` | `network_kind` |
| Associated ports | `networkConfig.interface.bond.<name>.intf` (e.g. `["eth2","eth3"]`) / `nicStates` | `FirewallaNetwork.ports` | `ports` |
| IP range | `networkProfiles[uuid].ipv4Subnet`/`ipv4Subnets` | `FirewallaNetwork.ipv4_subnets` | `ipv4_subnets` |

### Network detail page

| App | Raw field | Normalized | Entity attribute |
| --- | --- | --- | --- |
| VLAN ID | `networkConfig.interface.vlan.<name>.vid` | `FirewallaNetwork.vlan_id` | `vlan_id` |
| Ethernet ports / LAG | `networkConfig.interface.<cat>.<name>` — `phy` WAN = the device itself; `bond` = `intf` member list; `vlan` = `intf` parent (dereference to its members); VPN = none | `FirewallaNetwork.ports` | `ports` |
| IPv4 address | `networkProfiles[uuid].ipv4` / `item=intf` `ipv4`/`ipv4s` | `FirewallaNetwork.ipv4_addresses` | `ipv4_addresses` |
| IPv4 subnet | `networkProfiles[uuid].ipv4Subnet`/`ipv4Subnets` | `FirewallaNetwork.ipv4_subnets` | `ipv4_subnets` |
| DHCP (mode/range/lease) | `networkConfig.dhcp[<intf>]` | `FirewallaNetwork.dhcp` | `dhcp` summary |
| IPv6 address | `item=intf` → `ipv6`/`ipv6s` | `FirewallaNetwork.ipv6_addresses` | `ipv6_addresses` |
| IPv6 subnet | `item=intf` → `ipv6Subnets` | `FirewallaNetwork.ipv6_subnets` | `ipv6_subnets` |
| mDNS Relay | **CONFIRMED** `networkConfig.mdns_reflector[<intf>].enabled` | `FirewallaNetwork.mdns_relay` | `mdns_relay` |
| SSDP Relay | **CONFIRMED** `networkConfig.mroute[<intf>].routes[]` with `cidr: 239.255.255.250` (only VLAN90 in live pull); relay on = the SSDP-multicast route is present, `oifs` = target networks | `FirewallaNetwork.ssdp_relay` | `ssdp_relay` |
| Block ICMP | **CONFIRMED** `networkConfig.icmp[<intf>].echoRequest` — **inverted**: `echoRequest` means "respond to ICMP echo (ping)"; the box clears it when Block ICMP is on, so `block_icmp = not echoRequest`. Live 2026-08-25: VLAN90 GUEST/DMZ (Block ICMP On in app) → `echoRequest=false` → `block_icmp=True`; all others `echoRequest=true` → `block_icmp=False`. | `FirewallaNetwork.block_icmp` | `block_icmp` |

### Network detail / usage view

| App | Raw field | Normalized | Entity attribute |
| --- | --- | --- | --- |
| Device count | `item=intf` → `hosts` count | `FirewallaNetwork.device_host_count` | `device_count` |
| Data usage (compiled) | **CONFIRMED (non-WAN)** `item=intf` → `newLast24`/`last30`/`last60`/`last12Months` `totalDownload`/`totalUpload`; **WAN excluded** — no per-WAN windowed source (WAN `item=intf` windows are zero; box-wide init windows are aggregate, not per-WAN; the WAN usage screen only fetches `monthlyDataUsageOnWans` + `last12monthlyDataUsageOnWans`) | `FirewallaNetwork.usage` | `network_usage` |
| Related rules | `policyRules` scoped to `intf:<uuid>` | `FirewallaNetwork.rule_ids` | `network_rules` |

## Confirmed vs. intended

| Field | Status | Notes |
| --- | --- | --- |
| Network identities (LAN/VLAN/VPN/WAN) | **Confirmed** | `networkConfig.interface` categories + `networkProfiles` |
| Network kind (LAN/VLAN/VPN/WAN) | **Confirmed** | `networkConfig.interface` category key |
| Per-network addressing/DNS/DHCP | **Confirmed** | `networkProfiles` + `networkConfig.dhcp` |
| WAN interface status | **Confirmed** | `networkMonitorData...wanStatus` |
| mDNS Relay | **Confirmed** | `networkConfig.mdns_reflector[<intf>].enabled` |
| Block ICMP | **Confirmed** | `networkConfig.icmp[<intf>].echoRequest`, inverted (`block_icmp = not echoRequest`) |
| SSDP Relay | **Confirmed** | `networkConfig.mroute[<intf>].routes[]` SSDP multicast `239.255.255.250` |
| VPN first-class model | **Confirmed** | `networkConfig.interface.wireguard/amneziawg/openvpn` |
| Compiled non-WAN usage | **Confirmed** | `item=intf` (`async_get_network_interface_payload`) per-network windows `newLast24`/`last30`/`last60`/`last12Months` with `totalDownload`/`totalUpload`; exposed as `FirewallaNetwork.usage` → `network_usage`. OpenVPN can return 500 for `item=intf` (handled resiliently). |
| WAN usage windows | **Excluded** | WAN `item=intf` windows are all zero; the box-wide init-payload `newLast24`/`last60`/`last30`/`last12Months` are aggregate box traffic (bucket = WAN-ONE only on a single-WAN box), and the WAN data-usage screen captures show only `monthlyDataUsageOnWans` + `last12monthlyDataUsageOnWans`. No confirmed per-WAN windowed usage path → WAN `network_usage` left empty. |
| Port / LAG bond mapping | **Confirmed** | `networkConfig.interface.bond.<name>.bond` + `networkConfig.app.bond` |

## Update rule

Every time Phase 3 confirms a field, move it from **Intended** to **Confirmed** here and in `docs/REVERSE_ENGINEERING_WORKFLOW.md`. Do not expose an entity attribute from an **Intended** row until it is **Confirmed**.