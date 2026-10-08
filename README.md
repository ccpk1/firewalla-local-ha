[![Quality Scale: Platinum](https://img.shields.io/badge/Quality%20Scale-platinum-platinum.svg)](https://github.com/ccpk1/firewalla-local-ha)
[![Quality Gates](https://img.shields.io/github/actions/workflow/status/ccpk1/firewalla-local-ha/lint-validation.yaml?branch=main&label=Quality%20Gates)](https://github.com/ccpk1/firewalla-local-ha/actions/workflows/lint-validation.yaml)
[![License](https://img.shields.io/static/v1?label=License&message=GPL-3.0&color=1E88E5&labelColor=555)](https://github.com/ccpk1/firewalla-local-ha/blob/main/LICENSE)
[![HACS Custom](https://img.shields.io/static/v1?label=HACS&message=custom&color=1E88E5&labelColor=555)](https://github.com/custom-components/hacs) <br>
[![Version](https://img.shields.io/github/v/release/ccpk1/firewalla-local-ha?include_prereleases&label=Version&color=1E88E5)](https://github.com/ccpk1/firewalla-local-ha/releases)
[![Stars](https://img.shields.io/github/stars/ccpk1/firewalla-local-ha)](https://github.com/ccpk1/firewalla-local-ha/stargazers)

![Firewalla Local](https://github.com/ccpk1/firewalla-local-ha/blob/main/docs/assets/3-1%20Logo%20Rectangle.png)

> ### **Local control. Zero latency. No subscription. Native Home Assistant.**

**Firewalla Local** is a high-performance, privacy-first Home Assistant integration designed for users who want to bridge the gap between their network security and their home automation—without the cloud middleman.

## 💡 **Why this exists**
I bought my Firewalla Gold a few years ago for the same reason many of you did: the promise of a powerful, prosumer, DIY-friendly firewall. To be fair, I actually really like the Firewalla app—it does an incredible job of making complex networking accessible.

However, relying solely on it means the ecosystem is not only "Cloud-Locked," but also "App-Locked." Opening an app on your phone is perfectly fine for configuring a VLAN or tweaking a setting every few months. But it becomes a significant handicap when you want to dynamically orchestrate day-to-day routines or leverage rich network data alongside the rest of your homelab services.

After years of maintaining custom SSH scripts to pull system metrics and wiring up clunky workarounds, I eventually reached a fork in the road: either reflash my hardware to a fully open-source OS, or finally build the native Home Assistant integration the community has been asking for.

**I chose to build.**

This integration is for the users who don't want another cloud dependency just to automate a "Kids' Bedtime" rule. It’s for the homelabbers who want network insights displayed right next to their server stats. It's for anyone who wants dynamic, condition-based control over their firewall, and for those who fundamentally believe that what happens on your LAN should stay on your LAN.

> *"I love the Firewalla hardware—it's some of the best on the market. I built this so I wouldn't have to choose between great hardware and a local-first DIY experience."*

## 📑 **Table of Contents**
- [Why this exists](#why-this-exists)
- [The "Platinum" Approach](#the-platinum-approach)
- [What it Enables](#what-it-enables)
- [Supported Hardware & Prerequisites](#supported-hardware--prerequisites)
- [A Note on Security & Privacy](#a-note-on-security--privacy)
- [Design Philosophy & Scope](#design-philosophy--scope)
- [Support the Project](#support-the-project)
- [Quick Installation](#quick-installation)
- [User Guide](#user-guide)
- [Development & Architecture Docs](#development--architecture-docs)
- [Community and Contribution](#community-and-contribution)
- [Security and Support Posture](#security-and-support-posture)
- [Disclaimer and Liability](#disclaimer-and-liability)
- [License](#license)

## 🏆 **The "Platinum" Approach**
This isn't just a wrapper for a few scripts. It was built from the ground up to meet Home Assistant’s "Platinum" quality standards:
*   **100% Local Data Plane:** After a one-time cloud-brokered pairing (matching the official app's security), all communication is direct to your box on your local network.
*   **Optimistic UI:** When you toggle a rule, Home Assistant updates immediately. No waiting for the next poll cycle to see if your command worked.
*   **UID-First Identity:** Your entities and devices are anchored to your hardware license. They stay stable even if your IP changes or you have to re-pair the box.
*   **Manager-Based Architecture:** Thin, efficient, and typed. Designed for stability and low CPU impact on your Home Assistant instance.

## ✨ **What it Enables**
Firewalla Local has evolved beyond simple monitoring into a comprehensive **local operator toolkit**.

### **Your Data, Native to Home Assistant**
Everything Firewalla Local exposes is a standard Home Assistant entity, so it works with the tools you already use: dashboards, automations, history and statistics, Assist, and the REST and WebSocket APIs. No cloud hop, no subscription, no separate app to check.

It also makes Home Assistant the hub your *other* tools read from. Because everything is served over standard REST and WebSocket APIs, anything on your network can pull Firewalla data straight out of Home Assistant — a Grafana chart, a wall display, a status page, a Node-RED flow, a script on another machine. Rather than every tool learning Firewalla's API or signing up for yet another cloud service, they all read from one place you already run, secure, and back up.

You can read state or call services this way, and both return structured data your tools can consume. The [User Guide](https://github.com/ccpk1/firewalla-local-ha/blob/main/docs/USER_GUIDE.md) has worked examples.

### **Dynamic Network Control**
* **Rule-Backed Switches & Timed Pauses:** Toggle your most-used rules (Internet Block, Social, Gaming) instantly, or grant duration-based access from any automation — "give the kids 30 more minutes of gaming" by voice. Rules can be paused and resumed reversibly, or removed permanently when they are no longer wanted.
* **Host Operator Actions:** Act as the network admin directly from Home Assistant. Wake hosts over the network, rename them, set or clear DHCP reservations, and turn "notify when online/offline" settings on and off — all without opening the Firewalla app.

### **Alarm Monitoring & Triage**
* **Native Alarm Entities:** See at a glance whether the box has active alarms through a dedicated binary sensor plus an active-alarm count sensor. Both carry a bounded per-category summary so automations can gate on "any gaming alarms?" without a service call, and a completeness flag tells you when the box's 50-record snapshot limit means the summary is partial rather than empty.
* **Alarm Triage:** Query recent active and archived alarms with optional per-alarm detail, archive them, delete them permanently, and create or remove scoped silences — all admin-gated, with explicit confirmation required for anything irreversible.
* **Blocks Stay Rules:** A Firewalla "block" action on an alarm is ordinary policy-rule creation, so a blocked target appears in the normal rule inventory and is removed with the rule it created. Enforcement stays in one place, and any block can be undone without hunting through the app.

### **Presence & Usage Tracking**
* **Router-Based Device Trackers:** Expose highly reliable Home Assistant `device_tracker` entities for your MAC-backed LAN clients for rock-solid "Home/Away" presence automations.
* **Watched-User Monitoring:** Select household members to track their daily total internet usage, unique-usage, associated hosts, and positive-only per-app usage based on real-time host joins.
* **Watched-Device Monitoring:** Expose critical endpoints as connectivity sensors with stable activity attributes to ensure your vital hardware stays online.

### **Appliance & Data Visibility**
* **Appliance Monitoring:** Track Firewalla system status, WAN IP details, uptime, memory/disk usage, per-port link/speed/MAC, Bluetooth MAC, box time zone, and the latest successful Speed Test natively. Includes a diagnostic `Sync runtime` button to force an immediate local data refresh.
* **Internet Quality Monitoring:** Expose per-WAN ping latency and packet-loss sensors from the box's continuous Internet Quality monitor (15-minute samples), with recent history available as a report.
* **Per-Network Entities:** Expose every Firewalla network (LAN, VLAN, VPN, WAN) as a native binary sensor carrying kind, VLAN ID, ports, IPv4/IPv6 + DHCP, host count, advanced options (mDNS/SSDP Relay, Block ICMP), and usage — including current-month WAN usage.
* **Per-SSID Wireless Entities (AP7):** When Firewalla AP7 access points are present, expose every wireless network (SSID) as a native binary sensor (status + band, encryption, WPA3, VLAN, interface) and a toggle switch to pause/resume it — all under the Firewalla box device.
* **Per-AP Device Monitoring (AP7):** Each Firewalla AP7 access point becomes its own Home Assistant device (linked to the box), with a system-status binary sensor exposing channel, LED, TX power, country, mesh mode, timezone, pause-WiFi/ACL state, and live client count.
* **Rich Local Reporting:** Over 30 native Home Assistant services cover host identity records, per-network configuration and usage, time usage history, WAN data, WAN event timelines, and current or archived alarms with their silences — all pulled directly from the local data plane without touching the cloud.

### **AI Assistant & MCP Access**
> **Requires Home Assistant Core 2026.10 or newer.** On older Core the integration works normally; the AI tools are simply not offered.

* **Ask your network questions:** The integration registers its own MCP tool surface, so an AI assistant can answer questions like "how many hosts are online?", "did my internet drop this week?", or "which hosts on my guest network used the most bandwidth in the last hour?" — using real local data, with no sidecar and no cloud subscription.
* **Use it from almost any AI client:** This is a standard MCP server, not an Assist-only feature. Home Assistant's native [Model Context Protocol Server](https://next.home-assistant.io/integrations/mcp_server/) serves these tools to **any MCP client** — ChatGPT, VS Code and other editors, Claude Desktop, or a custom agent — so you can query your network from whichever assistant you already use, and one integration reaches all of them. Requires enabling the MCP Server integration in Home Assistant.
* **Multiple boxes appear as separate tool sets:** Each Firewalla box is registered as its own MCP API with its own URL, so you can point a client at one box or at several. Merged, Home Assistant namespaces each box's tools by the name you gave that entry, so the assistant always knows which box it is acting on.
* **Graduated access, privacy-first default:** Five settings control what the assistant can reach. **Off** registers no tools at all. The default, **Summary only**, answers general questions using counts, network names, and performance metrics — **no host addresses, hardware identifiers, group or user names, or public IP**. Raise it to **Read only** for host names and addresses, then **Read and control** for reversible actions, and finally **Full** for destructive ones.
* **Read access is useful, and it is a real trade:** Anything above Summary only sends actual network detail to whichever LLM provider the assistant talks to — host names, IP and MAC addresses, rule and alarm detail (including remote endpoints and, for some alarms, approximate location), and your public IP. That is enough to build a detailed picture of a household, so consider who operates the model you are using, and raise the setting only as far as you need it, for as long as you need it.
* **Structural safeguards:** In Summary only the other tools are not registered at all, so there is no sensitive field to filter out and nothing to leak. Every control action is admin-gated, so a non-admin user can never change your network through the assistant, and credentials, pairing keys, and symmetric keys cannot appear in tool output at all.
* **It ships a domain model, not just data access:** Exposing 39 tools is the easy part. The hard part is that an assistant which can *call* the tools but does not understand *this* network will answer plausibly and wrongly — invent an address it was never given, assume a host's own rules still apply after a group change, report a window the box quietly shortened as the one it asked for, or call a permanent deletion reversible. So the surface carries roughly **40,000 characters of curated context**: a written model of how Firewalla behaves, injected into every tool description, plus a per-tool contract for each of the 39 tools and four annotation profiles that tell the client which calls read, write, or destroy. It reaches the model on three channels because no single one is universal — see the [User Guide](https://github.com/ccpk1/firewalla-local-ha/blob/main/docs/USER_GUIDE.md#the-domain-model-the-assistant-receives).

## 📡 **Supported Hardware & Prerequisites**
* **Firewalla Hardware:** Developed and actively tested on Firewalla Gold. Confirmed working on the following models running the Firewalla Box software that supports the local API:
   * Gold
   * Gold Plus
   * Gold SE
   * Purple
* **Home Assistant:** Requires Home Assistant Core version 2025.10 or newer.
* **Network:** Your Home Assistant instance must be able to reach the Firewalla's local LAN IP.

The AI assistant and MCP tools need a newer Core; see the note at the top of the [AI Assistant & MCP Access](#ai-assistant--mcp-access) section.

## 🛡️ **A Note on Security & Privacy**
Connecting any external system to your firewall’s management layer requires a high degree of trust.
*   **Independence:** This project is not affiliated with, endorsed by, or supported by Firewalla Inc.
*   **Zero-Credential Storage:** This integration does not store your Firewalla account password. It uses an encrypted token exchange identical to the official Firewalla app.
*   **Local credential persistence:** Testing indicates Firewalla may return a stable local credential bundle for the box during Additional Pairing. Removing the paired-device entry in the Firewalla app should not be treated as a guaranteed revocation of already-cached local access.
*   **Responsibility:** Access to your firewall's control plane is powerful. By bridging your firewall to Home Assistant, you are inherently expanding your network's attack surface. If your Home Assistant instance is exposed or compromised, your network routing and firewall rules could be manipulated. By using this integration, you accept this risk and are solely responsible for locking down your Home Assistant environment (e.g., enforcing 2FA, securing remote access, and managing user permissions).

## 🧭 **Design Philosophy & Scope**
**Firewalla Local** is built for the individual home user. My goal is to provide simple, responsive, and private control over your own local network.

*   **The Goal:** Enabling the "Common Person" to have the same level of local visibility and automation found in many other prosumer networking products.
*   **What this is NOT:** This integration is **not** a Managed Service Provider (MSP) tool. It does not provide multi-site management, fleet-wide reporting, or enterprise-grade monitoring.
*   **Respecting the Ecosystem:** Firewalla offers a robust MSP platform for professionals who need centralized cloud management. This integration does not aim to replicate or provide those services. It is strictly for local-to-local home automation—things like pausing the internet for your kids or checking your router’s CPU load from a dashboard.

## ❤️ **Support the Project**

Building and maintaining local control integrations takes countless hours of development, testing, and covering hardware and tool costs. If Firewalla Local is giving you the network control you've been hoping for, here is how you can help keep the project alive:

⭐ **Star this repository! (The Non-Negotiable)**
If you install this integration and get value out of it, clicking the Star button at the top of the page is the easiest—and free—way to say thanks. It takes two seconds, helps others discover the project, and shows me that the community is actively using it.

☕ **Sponsor or Tip (The Ultimate Motivator)**
While stars let me know the integration is alive, a sponsorship or tip is the absolute best way to affirm that the time and money spent building this tool is providing real value.

Financial support is **never required**, but it is the strongest motivation for me to keep fixing bugs, adding features, and maintaining this project long-term. If Firewalla Local makes your smart home better, consider showing your support!

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/ccpk1)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/ccpk1)

## ⚡ **Quick Installation**

### One-click HACS install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ccpk1&repository=firewalla-local-ha&category=integration)

### Manual HACS setup

1. Ensure HACS is installed.
2. In Home Assistant, open **HACS -> Integrations -> Custom repositories**.
3. Add `https://github.com/ccpk1/firewalla-local-ha` as an **Integration** repository.
4. Search for **Firewalla Local**, install it, and restart Home Assistant.
5. Open **Settings -> Devices & Services -> Add Integration**.
6. Choose **Firewalla Local** and complete the QR-based pairing flow.

## 📖 **User Guide**

The operating guide lives here: [docs/USER_GUIDE.md](https://github.com/ccpk1/firewalla-local-ha/blob/main/docs/USER_GUIDE.md).

It is organized around the jobs you can do with the integration:

- **Install and pair** — HACS installation, the QR-based pairing flow, and removal
- **Use the data** — dashboards, automations, history, voice, and reading it over the
  REST and WebSocket APIs
- **Choose your surfaces** — the options flow, and what each monitoring surface adds
- **Monitor** — the appliance, your networks, wireless, hosts, users, and alarms
- **Operate** — host actions, rule control, alarm triage, and the report services
- **Reference** — every service with its arguments, which actions require an
  administrator, and a vocabulary section for the terms this integration uses

A separate [MCP tool reference](https://github.com/ccpk1/firewalla-local-ha/blob/main/docs/MCP_TOOL_REFERENCE.md)
covers the AI tool surface.

## 🏗️ **Development & Architecture Docs**

Durable project rules live in `docs/`:

- `ARCHITECTURE.md` — how the integration is put together, and the trade-offs behind it
- `DEVELOPMENT_STANDARDS.md` — the standards code here is held to
- `QUALITY_REFERENCE.md` — where the integration stands against the Home Assistant
  quality scale
- `RULE_MODEL.md` — how Firewalla rules are modelled
- `MCP_TOOL_REFERENCE.md` — the AI tool surface, tool by tool
- `RELEASE_CHECKLIST.md` — the steps to work through for every release

Repository layout:

```text
├── README.md
├── custom_components/
│   └── firewalla_local/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT_STANDARDS.md
│   ├── MCP_TOOL_REFERENCE.md
│   ├── QUALITY_REFERENCE.md
│   ├── RELEASE_CHECKLIST.md
│   ├── RULE_MODEL.md
│   └── USER_GUIDE.md
└── tests/
    └── components/
        └── firewalla_local/
```

## 🤝 **Community and Contribution**

- Issues and feature requests: https://github.com/ccpk1/firewalla-local-ha/issues
- Discussions: https://github.com/ccpk1/firewalla-local-ha/discussions
- Pull requests: https://github.com/ccpk1/firewalla-local-ha/pulls

## 🔒 **Security and Support Posture**

- Vulnerability reporting guidance lives in `SECURITY.md`
- The high-level security approach, trade-offs, and awareness notes live in `docs/ARCHITECTURE.md`
- This repository should not be treated as an official Firewalla integration or as a Firewalla support channel

## ⚠️ **Disclaimer and Liability**

While I have put a significant amount of time and effort into engineering this integration properly, securely, and respectfully to the hardware, this is an unofficial, community-driven, open-source project.

**This software is provided "as is", without warranty of any kind, express or implied.** By installing and using Firewalla Local, you acknowledge and agree that you are using it entirely at your own risk. I make no guarantees regarding its functionality, stability, security, or ongoing compatibility with future Firewalla firmware updates. Under no circumstances shall the developer(s) or contributor(s) be held liable for any network lockouts, security breaches, internet outages, data loss, or any other damages arising from the use of this software.

Please proceed with caution, review your system often, and always keep a backup of your Home Assistant configuration.

AI-Assisted Development: In today’s age, leveraging AI is one of the few ways a maintainer can realistically build, thoroughly test, and actively support a truly complex, high-quality open-source project. But to be clear, this integration isn't just blindly "vibe coded." While AI acts as a significant force multiplier for the workflow, human oversight dictates the architecture. Every commit is strictly audited, backed by extensive tests, and measured against rigorous Home Assistant development standards to ensure long-term stability.

## 📄 **License**

This project is licensed under the GPL-3.0 license. See `LICENSE`.

