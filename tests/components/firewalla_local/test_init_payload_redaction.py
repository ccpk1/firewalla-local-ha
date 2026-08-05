"""Tests for the best-effort runtime init payload redaction."""

from __future__ import annotations

from custom_components.firewalla_local.helpers.init_payload_redaction import (
    redact_runtime_init_payload,
)


def test_redact_top_level_sensitive_fields() -> None:
    """Test top-level sensitive fields are redacted."""
    payload = {
        "jwt": "eyJhbGciOiJSUzI1NiJ9.eyJpZCI6ImFiYyJ9.signature",
        "ddnsToken": "87f9e379-1e1b-4fed-8af8-f8e3034783ea",
        "btMac": "20:6D:31:FC:1C:56",
        "cpuid": "20:6D:31:01:5E:DF",
        "publicIp": "23.245.207.179",
        "ddns": "drl6jun7zg.d.firewalla.org",
        "localDomainSuffix": "int.ccpk.us",
        "license": "license-123",
        "groupName": "Firewalla",
        "model": "gold",
    }

    redacted = redact_runtime_init_payload(payload)

    assert redacted["jwt"] == "**REDACTED**"
    assert redacted["ddnsToken"] == "**REDACTED**"
    assert redacted["btMac"] == "**REDACTED**"
    assert redacted["cpuid"] == "**REDACTED**"
    assert redacted["publicIp"] == "**REDACTED**"
    assert redacted["ddns"] == "**REDACTED**"
    assert redacted["localDomainSuffix"] == "**REDACTED**"
    assert redacted["license"] == "**REDACTED**"
    # Non-sensitive fields are preserved.
    assert redacted["groupName"] == "Firewalla"
    assert redacted["model"] == "gold"


def test_redact_host_sensitive_fields() -> None:
    """Test host records redact identifying fields but keep structure."""
    payload = {
        "hosts": [
            {
                "mac": "0C:85:E1:B0:1D:1C",
                "ip": "192.168.202.226",
                "name": "kadens-phone",
                "bname": "FBISurvlanceVan",
                "dhcpName": "FBISurvlanceVan",
                "localDomain": "kadens-phone",
                "macVendor": "Apple, Inc.",
                "devId": "hosts:0C:85:E1:B0:1D:1C",
                "stale": False,
                "policy": {"monitor": True},
            }
        ]
    }

    redacted = redact_runtime_init_payload(payload)
    host = redacted["hosts"][0]

    assert host["mac"] == "**REDACTED**"
    assert host["ip"] == "**REDACTED**"
    assert host["name"] == "**REDACTED**"
    assert host["bname"] == "**REDACTED**"
    assert host["dhcpName"] == "**REDACTED**"
    assert host["localDomain"] == "**REDACTED**"
    assert host["macVendor"] == "**REDACTED**"
    assert host["devId"] == "**REDACTED**"
    # Non-sensitive host fields are preserved.
    assert host["stale"] is False
    assert host["policy"] == {"monitor": True}


def test_redact_wg_peer_sensitive_fields() -> None:
    """Test WireGuard peer records redact keys and names."""
    payload = {
        "wgPeers": [
            {
                "publicKey": "1Jit10BZ8PFUYHIRFYQSHbdKVYoMdz9803pmITpJGjw=",
                "name": "kadens-chromebook-wgvpn",
                "allowedIPs": ["192.168.250.79/32"],
                "uid": "peer-1",
                "devId": "wg:peer-1",
                "rxBytes": 100,
            }
        ]
    }

    redacted = redact_runtime_init_payload(payload)
    peer = redacted["wgPeers"][0]

    assert peer["publicKey"] == "**REDACTED**"
    assert peer["name"] == "**REDACTED**"
    assert peer["allowedIPs"] == "**REDACTED**"
    assert peer["uid"] == "**REDACTED**"
    assert peer["devId"] == "**REDACTED**"
    assert peer["rxBytes"] == 100


def test_redact_wireless_mesh_key() -> None:
    """Test the AP controller mesh key and SSID are redacted."""
    payload = {
        "networkConfig": {
            "apc": {
                "assets_template": {
                    "ap_default": {
                        "mesh": {
                            "key": "K6wXvSUw",
                            "encryption": "psk2+ccmp",
                            "ssid": "FWAP-UbWBK",
                        }
                    }
                }
            }
        }
    }

    redacted = redact_runtime_init_payload(payload)
    mesh = redacted["networkConfig"]["apc"]["assets_template"]["ap_default"]["mesh"]

    assert mesh["key"] == "**REDACTED**"
    assert mesh["ssid"] == "**REDACTED**"
    assert mesh["encryption"] == "psk2+ccmp"


def test_redact_patterns_in_scalars_and_keys() -> None:
    """Test MAC/IP/email/JWT patterns are redacted in values and dict keys."""
    payload = {
        "appConfs": {
            "youtube": {
                "devices": {
                    "4C:1D:96:E3:3A:96": {"totalMins": 33},
                    "E4:5E:37:00:D6:74": {"totalMins": 2},
                }
            }
        },
        "countryMapping": {
            "162.253.220.213": ["US"],
            "104.22.62.28": ["US"],
        },
        "eMembers": [{"name": "chadandcaren@gmail.com"}],
        "note": "contact chad.shilling@outlook.com for details",
    }

    redacted = redact_runtime_init_payload(payload)

    # MAC keys redacted (duplicate redacted keys collapse in a dict).
    devices = redacted["appConfs"]["youtube"]["devices"]
    assert list(devices.keys()) == ["**REDACTED**"]
    # IP keys redacted (duplicate redacted keys collapse in a dict).
    mapping = redacted["countryMapping"]
    assert list(mapping.keys()) == ["**REDACTED**"]
    # Email redacted in values.
    assert redacted["eMembers"][0]["name"] == "**REDACTED**"
    assert redacted["note"] == "contact **REDACTED** for details"


def test_redact_preserves_non_sensitive_structure() -> None:
    """Test non-sensitive data is preserved."""
    payload = {
        "policyRuleNumber": 292,
        "activeAlarmCount": 0,
        "bootingComplete": True,
        "versionStr": "1.983",
        "network": {"name": "eth0"},
    }

    redacted = redact_runtime_init_payload(payload)

    assert redacted["policyRuleNumber"] == 292
    assert redacted["activeAlarmCount"] == 0
    assert redacted["bootingComplete"] is True
    assert redacted["versionStr"] == "1.983"
    assert redacted["network"] == {"name": "eth0"}


def test_exclude_non_wireless_sections() -> None:
    """Test large non-wireless sections are dropped from the export."""
    payload = {
        "userTags": {"30": {"name": "KADENS_PHONE"}},
        "internetSpeedtestResults": [{"client": {"publicIp": "1.2.3.4"}}],
        "systemFlows": {"flows": ["imap.gmail.com"]},
        "last60": {"data": "usage"},
        "newAlarms": [{"device": "kadens-phone-wgvpn"}],
        "customizedCategories": {"dap_1": {"name": "DAP - 00:11:22:33:44:55"}},
        "tags": {"17": {"name": "SVR_PVE"}},
        "networkConfig": {"apc": {"assets_template": {}}},
        "hosts": [{"mac": "0C:85:E1:B0:1D:1C", "name": "kadens-phone"}],
    }

    redacted = redact_runtime_init_payload(payload)

    # Excluded sections are dropped entirely.
    for key in (
        "userTags",
        "internetSpeedtestResults",
        "systemFlows",
        "last60",
        "newAlarms",
        "customizedCategories",
        "tags",
    ):
        assert key not in redacted
    # Kept sections remain.
    assert "networkConfig" in redacted
    assert "hosts" in redacted


def test_redact_internal_domain_suffix() -> None:
    """Test internal domain suffixes and their subdomains are redacted."""
    payload = {
        "networkConfig": {
            "dhcp": {
                "bond0": {"searchDomain": ["int.ccpk.us"]},
            }
        },
        "policyRules": [
            {
                "appHosts": ["ha.ccpk.us"],
                "domain": "www.googleapis.com.int.ccpk.us",
            }
        ],
        "countryMapping": {"auth.ccpk.us": ["US"]},
    }

    redacted = redact_runtime_init_payload(payload)

    assert redacted["networkConfig"]["dhcp"]["bond0"]["searchDomain"] == [
        "**REDACTED**"
    ]
    assert redacted["policyRules"][0]["appHosts"] == ["**REDACTED**"]
    assert redacted["policyRules"][0]["domain"] == "**REDACTED**"
    assert list(redacted["countryMapping"].keys()) == ["**REDACTED**"]
