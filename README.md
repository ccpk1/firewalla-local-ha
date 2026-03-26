[![HACS Custom](https://img.shields.io/static/v1?label=HACS&message=custom&color=1E88E5&labelColor=555)](https://github.com/custom-components/hacs)
[![License](https://img.shields.io/static/v1?label=License&message=GPL-3.0&color=1E88E5&labelColor=555)](https://github.com/ccpk1/firewalla-local-ha/blob/main/LICENSE)
[![Version](https://img.shields.io/github/v/release/ccpk1/firewalla-local-ha?include_prereleases&label=Version&color=1E88E5)](https://github.com/ccpk1/firewalla-local-ha/releases)
[![Stars](https://img.shields.io/github/stars/ccpk1/firewalla-local-ha)](https://github.com/ccpk1/firewalla-local-ha/stargazers)

![Firewalla Local](<docs/assets/3-1 Logo Rectangle.png>)

> ### *Local control. Zero latency. No subscription. Native Home Assistant.*

**Firewalla Local** is a high-performance, privacy-first Home Assistant integration designed for users who want to bridge the gap between their network security and their home automation—without the cloud middleman.

## Why this exists
I bought my Firewalla Gold a few years ago for the same reason many of you did: the promise of a powerful, prosumer, DIY-friendly firewall. While the hardware is world-class, the path to automating it has always felt "Cloud-Locked."

I spent years maintaining custom SSH scripts to pull system metrics and made some clunky connections to Home Assistant. I eventually reached a fork in the road: either reflash my hardware to a fully open-source OS or build the integration the community has wanted for years.

**I chose to build.**

This integration is for the users who don't want another cloud connection and subscription just to automate a "Kids' Bedtime" rule, and for those who believe that what happens on their LAN should stay on their LAN.

> *"I love the Firewalla hardware—it's some of the best on the market. I built this so I wouldn't have to choose between great hardware and a local-first DIY experience."*

## The "Platinum" Approach
This isn't just a wrapper for a few scripts. It was built from the ground up to meet Home Assistant’s "Platinum" quality standards:
*   **100% Local Data Plane:** After a one-time cloud-brokered pairing (matching the official app's security), all communication is direct to your box on your local network.
*   **Optimistic UI:** When you toggle a rule, Home Assistant updates immediately. No waiting for the next poll cycle to see if your command worked.
*   **UID-First Identity:** Your entities and devices are anchored to your hardware license. They stay stable even if your IP changes or you have to re-pair the device.
*   **Manager-Based Architecture:** Thin, efficient, and typed. Designed for stability and low CPU impact on your Home Assistant instance.

## What it enables
*   **Rule-Backed Switches:** Select your most-used rules (Internet Block, Social, Gaming, etc.) and expose them as simple switches for use in Dashboards or Automations.
*   **Real-time Monitoring:** Track system load, memory usage, disk health, and your latest Speed Test results natively in HA.
*   **Timed Pauses:** Use the `pause_rule` and `resume_rule` services to enable / disable a firewall rule (e.g., "Give the kids 30 more minutes of gaming") directly from a voice assistant or button.

## 🛡️ A Note on Security & Privacy
Connecting any external system to your firewall’s management layer requires a high degree of trust.
*   **Independence:** This project is not affiliated with, endorsed by, or supported by Firewalla Inc.
*   **Zero-Credential Storage:** This integration does not store your Firewalla account password. It uses an encrypted token exchange identical to the official Firewalla app.
*   **Full Control:** Because this uses the official "Additional Pairing" protocol, you are in total control. You can revoke this integration's access at any time by simply opening the Firewalla app and removing it from your paired devices.
*   **Responsibility:** Access to your firewall's control plane is powerful. By bridging your firewall to Home Assistant, you are inherently expanding your network's attack surface. If your Home Assistant instance is exposed or compromised, your network routing and firewall rules could be manipulated. By using this integration, you accept this risk and are solely responsible for locking down your Home Assistant environment (e.g., enforcing 2FA, securing remote access, and managing user permissions).

## **Design Philosophy & Scope**
**Firewalla Local** is built for the individual home user. My goal is to provide simple, responsive, and private control over your own local network.

*   **The Goal:** Enabling the "Common Person" to have the same level of local visibility and automation found in many other prosumer networking products.
*   **What this is NOT:** This integration is **not** a Managed Service Provider (MSP) tool. It does not provide multi-site management, fleet-wide reporting, or enterprise-grade monitoring.
*   **Respecting the Ecosystem:** Firewalla offers a robust MSP platform for professionals who need centralized cloud management. This integration does not aim to replicate or provide those services. It is strictly for local-to-local home automation—things like pausing the internet for your kids or checking your router’s CPU load from a dashboard.

## ❤️ Support the Project

Building and maintaining local control integrations takes countless hours of development, testing, and covering hardware and tool costs. If Firewalla Local is giving you the network control you've been hoping for, here is how you can help keep the project alive:

⭐ **Star this repository! (The Non-Negotiable)**
If you install this integration and get value out of it, clicking the Star button at the top of the page is the easiest—and free—way to say thanks. It takes two seconds, helps others discover the project, and shows me that the community is actively using it.

☕ **Sponsor or Tip (The Ultimate Motivator)**
While stars let me know the integration is alive, a sponsorship or tip is the absolute best way to affirm that the time and money spent building this tool is providing real value.

Financial support is **never required**, but it is the strongest motivation for me to keep fixing bugs, adding features, and maintaining this project long-term. If Firewalla Local makes your smart home better, consider showing your support!

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/ccpk1)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/ccpk1)

## Quick installation

### One-click HACS install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ccpk1&repository=firewalla-local-ha&category=integration)

### Manual HACS setup

1. Ensure HACS is installed.
2. In Home Assistant, open **HACS -> Integrations -> Custom repositories**.
3. Add `https://github.com/ccpk1/firewalla-local-ha` as an **Integration** repository.
4. Search for **Firewalla Local**, install it, and restart Home Assistant.
5. Open **Settings -> Devices & Services -> Add Integration**.
6. Choose **Firewalla Local** and complete the QR-based pairing flow.

## User guide

The minimal user-facing operating guide lives in `docs/USER_GUIDE.md`.

It covers:

- installation and removal
- pairing expectations
- refresh behavior
- the rule-backed switch surface
- runtime inventory, pause, and resume services

## Security and support posture

- Vulnerability reporting guidance lives in `SECURITY.md`
- The high-level security approach, trade-offs, and awareness notes live in `docs/ARCHITECTURE.md`
- This repository should not be treated as an official Firewalla integration or as a Firewalla support channel

## Disclaimer

This is an independent community project. It is not affiliated with, endorsed by,
or supported by Firewalla.

Use it at your own risk.

## Development and architecture docs

The durable project rules live in:

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_STANDARDS.md`
- `docs/QUALITY_REFERENCE.md`

Repository layout:

```text
custom_components/firewalla_local/
tests/components/firewalla_local/
docs/
firewalla-dev.code-workspace
pyproject.toml
```

## Community and contribution

- Issues and feature requests: https://github.com/ccpk1/firewalla-local-ha/issues
- Discussions: https://github.com/ccpk1/firewalla-local-ha/discussions
- Pull requests: https://github.com/ccpk1/firewalla-local-ha/pulls

## License

This project is licensed under the GPL-3.0 license. See `LICENSE`.


## ⚠️ Disclaimer and Liability

While I have put a significant amount of time and effort into engineering this integration properly, securely, and respectfully to the hardware, this is an unofficial, community-driven, open-source project.

**This software is provided "as is", without warranty of any kind, express or implied.** By installing and using Firewalla Local, you acknowledge and agree that you are using it entirely at your own risk. I make no guarantees regarding its functionality, stability, security, or ongoing compatibility with future Firewalla firmware updates. Under no circumstances shall the developer(s) or contributor(s) be held liable for any network lockouts, security breaches, internet outages, data loss, or any other damages arising from the use of this software.

Please proceed with caution, review your rules often, and always keep a backup of your Home Assistant configuration.
