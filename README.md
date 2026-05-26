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
*   **UID-First Identity:** Your entities and devices are anchored to your hardware license. They stay stable even if your IP changes or you have to re-pair the device.
*   **Manager-Based Architecture:** Thin, efficient, and typed. Designed for stability and low CPU impact on your Home Assistant instance.

## ✨ **What it Enables**
Firewalla Local has evolved beyond simple monitoring into a comprehensive **local operator toolkit**.

### **Dynamic Network Control**
* **Rule-Backed Switches & Timed Pauses:** Toggle your most-used rules (Internet Block, Social, Gaming) instantly. Use the `pause_rule` and `resume_rule` services to grant duration-based access (e.g., "Give the kids 30 more minutes of gaming") via any HA automation or voice assistant.
* **Host Operator Actions:** Act as the network admin directly from Home Assistant. Wake devices (WOL), rename hosts, set/clear DHCP reservations, and toggle "notify when online/offline" settings seamlessly via actions (services).

### **Presence & Usage Tracking**
* **Router-Based Device Trackers:** Expose highly reliable Home Assistant `device_tracker` entities for your MAC-backed LAN clients for rock-solid "Home/Away" presence automations.
* **Watched-User Monitoring:** Select household members to track their daily total internet usage, unique-usage, associated devices, and positive-only per-app usage based on real-time host joins.
* **Watched-Device Monitoring:** Expose critical endpoints as connectivity sensors with stable activity attributes to ensure your vital hardware stays online.

### **Appliance & Data Visibility**
* **Appliance Monitoring:** Track Firewalla system status, WAN IP details, uptime, memory/disk usage, and the latest successful Speed Test natively. Includes a diagnostic `Sync runtime` button to force an immediate local data refresh.
* **Rich Local Reporting:** Leverage over a dozen native Home Assistant services to query host identity records, network segment usage, time usage history, WAN data, and WAN event timelines—all pulled directly from the local data plane without touching the cloud.

## **Supported Hardware & Prerequisites**
* **Firewalla Hardware:** Developed and actively tested on Firewalla Gold. It should be compatible with the Purple, Gold Pro, and any other series running the Firewalla Box software that supports the local API.
    * 🗣️ Community Feedback Needed: If you successfully run this on a non-Gold model, please drop a note in the Discussions tab so I can officially update this supported list!
    * Updated April 20th, 2026 - User reports confirm working for models:
       * Gold
       * Gold Plus
       * Purple
* **Home Assistant:** Requires Home Assistant Core version 2026.3.0 or newer.
* **Network:** Your Home Assistant instance must be able to reach the Firewalla's local LAN IP.

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

It covers:

- installation and removal
- pairing expectations
- options-flow management for rule switches, watched devices, device trackers, watched users, and polling
- refresh behavior
- appliance monitoring, watched-device monitoring, device-tracker monitoring, and watched-user monitoring
- runtime inventory, network, time-usage, speed-test, and WAN report services
- host operator actions including Wake-on-LAN, rename, notification toggles, and DHCP reservations
- pause and resume services

## 🏗️ **Development & Architecture Docs**

The durable project rules live in:

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/QUALITY_REFERENCE.md`

Repository layout:

```text
├── custom_components/
│   └── firewalla_local/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT_STANDARDS.md
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

