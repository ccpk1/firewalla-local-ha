"""Tests for Firewalla runtime inventory reporting."""

from __future__ import annotations

from custom_components.firewalla_local.helpers.runtime_inventory import (
    build_runtime_inventory_report,
    render_runtime_inventory_markdown,
)
from custom_components.firewalla_local.models import FirewallaPolicyRule


def test_build_runtime_inventory_report() -> None:
    """Test the runtime inventory report captures groups, users, and review gaps."""
    payload = {
        "hosts": [{"mac": "00:08:9B:FB:01:D9", "name": "Kitchen speaker"}],
        "networkProfiles": {"net-1": {"intf": "bond0.10"}},
        "tags": {
            "10": {
                "name": "KADEN's Devices",
                "policy": {
                    "family": True,
                    "safeSearch": {"state": False},
                    "userTags": ["21"],
                },
            },
            "17": {"name": "AV_SMART_TV", "policy": {"adblock": False}},
        },
        "userTags": {"21": {"name": "KADEN", "affiliatedTag": "10"}},
        "policyRules": [
            {
                "pid": "736",
                "action": "block",
                "target": "TAG",
                "type": "mac",
                "tag": ["tag:10"],
                "expireTs": 1_700_000_000,
            },
            {
                "pid": "737",
                "action": "allow",
                "target": "TL-deadbeef",
                "type": "category",
            },
            {
                "pid": "738",
                "action": "block",
                "target": "bad.example",
                "type": "dns",
                "method": "auto",
                "alarm_type": "ALARM_INTEL",
                "reason": "ALARM_INTEL",
                "blockby": "fastdns",
                "category": "intel",
            },
        ],
    }
    rules = (
        FirewallaPolicyRule(
            rule_id="736",
            action="block",
            target="TAG",
            target_type="mac",
            direction="bidirection",
            enabled=True,
            purpose=None,
            scope=(),
            target_name="KADEN's Devices (KADEN)",
            activated_time=1_700_000_000.0,
            expire_seconds=3600,
            expires_at=1_700_003_600.0,
            auto_delete_when_expires=True,
            dnsmasq_only=False,
        ),
        FirewallaPolicyRule(
            rule_id="737",
            action="allow",
            target="TL-deadbeef",
            target_type="category",
            direction="outbound",
            enabled=True,
            purpose=None,
            scope=(),
            target_name=None,
        ),
        FirewallaPolicyRule(
            rule_id="738",
            action="block",
            target="bad.example",
            target_type="dns",
            direction="bidirection",
            enabled=True,
            purpose=None,
            scope=(),
            target_name="bad.example",
            dnsmasq_only=True,
        ),
    )

    report = build_runtime_inventory_report(payload, rules)

    assert report["summary"]["group_count"] == 2
    assert report["summary"]["group_policy_control_count"] == 3
    assert report["summary"]["user_count"] == 1
    assert report["summary"]["policy_rule_count"] == 3
    assert report["summary"]["dap_rule_count"] == 0
    assert report["summary"]["family_rule_count"] == 0
    assert report["summary"]["user_managed_rule_count"] == 2
    assert report["summary"]["system_managed_rule_count"] == 1
    assert report["summary"]["visible_rule_count"] == 2
    assert report["summary"]["visible_enabled_rule_count"] == 2
    assert report["summary"]["rule_switch_candidate_count"] == 1
    assert report["summary"]["rules_needing_review_count"] == 1
    assert report["summary"]["target_list_reference_count"] == 1
    assert report["groups"][0]["name"] == "AV_SMART_TV"
    assert report["groups"][1]["name"] == "KADEN's Devices"
    assert report["groups"][1]["policy"] == {
        "family": True,
        "safeSearch": False,
        "userTags": ["21"],
    }
    assert report["groups"][1]["user_names"] == ["KADEN"]
    assert report["group_policy_controls"] == [
        {
            "group_id": "17",
            "group_name": "AV_SMART_TV",
            "policy_key": "adblock",
            "user_names": [],
            "value": False,
        },
        {
            "group_id": "10",
            "group_name": "KADEN's Devices",
            "policy_key": "family",
            "user_names": ["KADEN"],
            "value": True,
        },
        {
            "group_id": "10",
            "group_name": "KADEN's Devices",
            "policy_key": "safeSearch",
            "user_names": ["KADEN"],
            "value": False,
        },
    ]
    assert report["users"] == [
        {
            "affiliated_group_id": "10",
            "affiliated_group_name": "KADEN",
            "id": "21",
            "name": "KADEN",
        }
    ]
    assert report["rules"][0]["label"] == (
        "block internet for KADEN's Devices (KADEN) (enabled)"
    )
    assert report["rule_switch_candidates"] == [
        {
            "action": "allow",
            "active_time_schedule": None,
            "applies_to": [],
            "app_name": None,
            "direction": "outbound",
            "app_time_period": None,
            "app_time_quota": None,
            "app_time_used": None,
            "app_uid": None,
            "enabled": True,
            "expire_seconds": None,
            "expires_at": None,
            "activated_time": None,
            "updated_time": None,
            "last_activated_time": None,
            "auto_delete_when_expires": None,
            "custom_name": None,
            "dnsmasq_only": None,
            "disturb_level": None,
            "disturb_method": None,
            "duration": None,
            "is_temporary": False,
            "is_paused": False,
            "label": "allow category TL-deadbeef (enabled)",
            "local_port": None,
            "name": "allow category TL-deadbeef",
            "management": {
                "classification": "user_managed",
                "reasons": [],
            },
            "matching": {
                "has_readable_target_name": False,
                "kind": "target_list",
                "references_target_list": True,
            },
            "notes": None,
            "pause_remaining_seconds": None,
            "pause_until": None,
            "protocol": None,
            "purpose": None,
            "raw_extras": {},
            "qdisc": None,
            "rate_limit": None,
            "review_reasons": [
                "missing_readable_target_name",
                "target_list_reference",
                "missing_target_list_name",
            ],
            "rule_id": "737",
            "scope": [],
            "tag_refs": [],
            "target": "TL-deadbeef",
            "target_name": None,
            "target_type": "category",
            "traffic_direction": None,
            "trust": None,
            "upnp": None,
            "use_bf": None,
        }
    ]
    assert report["user_managed_rules"] == [
        {
            "action": "block",
            "active_time_schedule": None,
            "applies_to": [],
            "app_name": None,
            "direction": "bidirection",
            "app_time_period": None,
            "app_time_quota": None,
            "app_time_used": None,
            "app_uid": None,
            "enabled": True,
            "expire_seconds": 3600,
            "expires_at": 1_700_003_600.0,
            "activated_time": 1_700_000_000.0,
            "updated_time": None,
            "last_activated_time": None,
            "auto_delete_when_expires": True,
            "custom_name": None,
            "dnsmasq_only": False,
            "disturb_level": None,
            "disturb_method": None,
            "duration": None,
            "is_temporary": True,
            "is_paused": False,
            "label": "block internet for KADEN's Devices (KADEN) (enabled)",
            "local_port": None,
            "name": "block internet for KADEN's Devices (KADEN)",
            "management": {
                "classification": "user_managed",
                "reasons": [],
            },
            "matching": {
                "has_readable_target_name": True,
                "kind": "internet_scope",
                "references_target_list": False,
            },
            "notes": None,
            "pause_remaining_seconds": None,
            "pause_until": None,
            "protocol": None,
            "purpose": None,
            "raw_extras": {},
            "qdisc": None,
            "rate_limit": None,
            "review_reasons": [],
            "rule_id": "736",
            "scope": [],
            "tag_refs": ["tag:10"],
            "target": "TAG",
            "target_name": "KADEN's Devices (KADEN)",
            "target_type": "mac",
            "traffic_direction": None,
            "trust": None,
            "upnp": None,
            "use_bf": None,
        },
        {
            "action": "allow",
            "active_time_schedule": None,
            "applies_to": [],
            "app_name": None,
            "direction": "outbound",
            "app_time_period": None,
            "app_time_quota": None,
            "app_time_used": None,
            "app_uid": None,
            "enabled": True,
            "expire_seconds": None,
            "expires_at": None,
            "activated_time": None,
            "updated_time": None,
            "last_activated_time": None,
            "auto_delete_when_expires": None,
            "custom_name": None,
            "dnsmasq_only": None,
            "disturb_level": None,
            "disturb_method": None,
            "duration": None,
            "is_temporary": False,
            "is_paused": False,
            "label": "allow category TL-deadbeef (enabled)",
            "local_port": None,
            "name": "allow category TL-deadbeef",
            "management": {
                "classification": "user_managed",
                "reasons": [],
            },
            "matching": {
                "has_readable_target_name": False,
                "kind": "target_list",
                "references_target_list": True,
            },
            "notes": None,
            "pause_remaining_seconds": None,
            "pause_until": None,
            "protocol": None,
            "purpose": None,
            "raw_extras": {},
            "qdisc": None,
            "rate_limit": None,
            "review_reasons": [
                "missing_readable_target_name",
                "target_list_reference",
                "missing_target_list_name",
            ],
            "rule_id": "737",
            "scope": [],
            "tag_refs": [],
            "target": "TL-deadbeef",
            "target_name": None,
            "target_type": "category",
            "traffic_direction": None,
            "trust": None,
            "upnp": None,
            "use_bf": None,
        },
    ]
    assert report["system_managed_rules"] == [
        {
            "action": "block",
            "active_time_schedule": None,
            "applies_to": [],
            "app_name": None,
            "direction": "bidirection",
            "app_time_period": None,
            "app_time_quota": None,
            "app_time_used": None,
            "app_uid": None,
            "enabled": True,
            "expire_seconds": None,
            "expires_at": None,
            "activated_time": None,
            "updated_time": None,
            "last_activated_time": None,
            "auto_delete_when_expires": None,
            "custom_name": None,
            "dnsmasq_only": True,
            "disturb_level": None,
            "disturb_method": None,
            "duration": None,
            "is_temporary": False,
            "is_paused": False,
            "label": "block dns bad.example (enabled)",
            "local_port": None,
            "name": "block dns bad.example",
            "management": {
                "classification": "system_managed",
                "reasons": [
                    "method_auto",
                    "alarm_backed_rule",
                    "security_engine_managed",
                    "alarm_intel_reason",
                    "intel_category",
                ],
            },
            "matching": {
                "has_readable_target_name": True,
                "kind": "domain",
                "references_target_list": False,
            },
            "notes": None,
            "pause_remaining_seconds": None,
            "pause_until": None,
            "protocol": None,
            "purpose": None,
            "raw_extras": {
                "alarm_type": "ALARM_INTEL",
                "blockby": "fastdns",
                "category": "intel",
                "method": "auto",
                "reason": "ALARM_INTEL",
            },
            "qdisc": None,
            "rate_limit": None,
            "review_reasons": [],
            "rule_id": "738",
            "scope": [],
            "tag_refs": [],
            "target": "bad.example",
            "target_name": "bad.example",
            "target_type": "dns",
            "traffic_direction": None,
            "trust": None,
            "upnp": None,
            "use_bf": None,
        }
    ]

    markdown = render_runtime_inventory_markdown(report)
    assert (
        markdown.count("block internet for KADEN's Devices (KADEN) (enabled) [id: 736]")
        == 1
    )
    assert "- 736: block internet for KADEN's Devices (KADEN)" in markdown
    assert (
        "- 738: block dns bad.example -> method_auto, alarm_backed_rule, "
        "security_engine_managed, alarm_intel_reason, intel_category" in markdown
    )


def test_build_runtime_inventory_report_exposes_custom_name() -> None:
    """Test the runtime inventory surfaces the raw custom rule name."""
    payload = {
        "policyRules": [
            {
                "pid": "772",
                "action": "allow",
                "target": "choreops.com",
                "type": "dns",
                "direction": "bidirection",
                "disabled": 0,
                "_name": "ChoreOps Custom Allow",
            }
        ]
    }
    rules = (
        FirewallaPolicyRule(
            rule_id="772",
            action="allow",
            target="choreops.com",
            target_type="dns",
            direction="bidirection",
            enabled=True,
            purpose=None,
            scope=(),
            raw_update_payload={
                "pid": "772",
                "action": "allow",
                "target": "choreops.com",
                "type": "dns",
                "_name": "ChoreOps Custom Allow",
                "disabled": 0,
            },
        ),
    )

    report = build_runtime_inventory_report(payload, rules)

    assert report["rules"][0]["name"] == "ChoreOps Custom Allow"
    assert report["rules"][0]["custom_name"] == "ChoreOps Custom Allow"


def test_build_runtime_inventory_report_promotes_rule_metadata() -> None:
    """Test the runtime inventory promotes known rule metadata and slims raw extras."""
    payload = {
        "policyRules": [
            {
                "pid": "399",
                "action": "allow",
                "target": "US",
                "type": "country",
                "direction": "inbound",
                "purpose": "port_forwarding",
                "disabled": 1,
                "localPort": "7777",
                "useBf": "",
                "protocol": "tcp",
                "updatedTime": "1774486668.472",
                "dnsmasq_only": False,
                "trust": False,
                "targetList": "0",
                "upnp": False,
                "timestamp": "1745623964.006",
                "hitCount": "16047",
                "lastHitTs": "1774485536.627",
                "lastActivatedTime": "1745623964.087",
                "idleTs": "1774488468",
            }
        ]
    }
    rules = (
        FirewallaPolicyRule(
            rule_id="399",
            action="allow",
            target="US",
            target_type="country",
            direction="inbound",
            enabled=False,
            purpose="port_forwarding",
            scope=("00:AA:BB:CC:62:53",),
            updated_time=1_774_486_668.472,
            last_activated_time=1_745_623_964.087,
            dnsmasq_only=False,
            raw_update_payload={
                "pid": "399",
                "action": "allow",
                "target": "US",
                "type": "country",
                "disabled": 1,
                "localPort": "7777",
                "useBf": "",
                "protocol": "tcp",
                "updatedTime": "1774486668.472",
                "dnsmasq_only": False,
                "trust": False,
                "targetList": "0",
                "upnp": False,
                "timestamp": "1745623964.006",
                "hitCount": "16047",
                "lastHitTs": "1774485536.627",
                "lastActivatedTime": "1745623964.087",
                "idleTs": "1774488468",
            },
        ),
    )

    report = build_runtime_inventory_report(payload, rules)

    rule = report["rules"][0]
    assert rule["local_port"] == "7777"
    assert rule["protocol"] == "tcp"
    assert rule["trust"] is False
    assert rule["use_bf"] is None
    assert rule["upnp"] is False
    assert rule["pause_until"] == 1_774_488_468.0
    assert rule["raw_extras"] == {
        "targetList": "0",
        "timestamp": "1745623964.006",
        "hitCount": "16047",
        "lastHitTs": "1774485536.627",
    }


def test_build_runtime_inventory_report_promotes_disturb_method() -> None:
    """Test the runtime inventory promotes disturb-method metadata."""
    payload = {
        "policyRules": [
            {
                "pid": "776",
                "action": "disturb",
                "target": "TAG",
                "type": "mac",
                "tag": ["tag:10"],
                "disabled": 1,
                "disturbMethod": {
                    "dropPacketRate": 10,
                    "rateLimit": 0.512,
                    "increaseLatency": 300,
                },
                "duration": "36000",
                "autoDeleteWhenExpires": "1",
                "targetList": "0",
                "timestamp": "1774488597.135",
                "hitCount": "276",
                "lastHitTs": "1774491240.247",
                "idleTs": "1774493122.164565",
                "cronTime": "0 21 * * *",
                "trust": False,
                "upnp": False,
            }
        ]
    }
    rules = (
        FirewallaPolicyRule(
            rule_id="776",
            action="disturb",
            target="TAG",
            target_type="mac",
            direction="bidirection",
            enabled=False,
            purpose=None,
            scope=(),
            tag_refs=("tag:10",),
            target_name="KADEN's Devices (KADEN)",
            applies_to=("KADEN's Devices (KADEN)",),
            updated_time=1_774_491_322.284,
            last_activated_time=1_774_488_597.305,
            auto_delete_when_expires=True,
            dnsmasq_only=False,
            raw_update_payload={
                "pid": "776",
                "action": "disturb",
                "target": "TAG",
                "type": "mac",
                "tag": ["tag:10"],
                "disabled": 1,
                "disturbMethod": {
                    "dropPacketRate": 10,
                    "rateLimit": 0.512,
                    "increaseLatency": 300,
                },
                "duration": "36000",
                "autoDeleteWhenExpires": "1",
                "targetList": "0",
                "timestamp": "1774488597.135",
                "hitCount": "276",
                "lastHitTs": "1774491240.247",
                "idleTs": "1774493122.164565",
                "cronTime": "0 21 * * *",
                "trust": False,
                "upnp": False,
            },
        ),
    )

    report = build_runtime_inventory_report(payload, rules)

    rule = report["rules"][0]
    assert rule["disturb_level"] is None
    assert rule["disturb_method"] == {
        "dropPacketRate": 10,
        "rateLimit": 0.512,
        "increaseLatency": 300,
    }
    assert rule["duration"] == "36000"
    assert rule["raw_extras"] == {
        "targetList": "0",
        "timestamp": "1774488597.135",
        "hitCount": "276",
        "lastHitTs": "1774491240.247",
    }

    markdown = render_runtime_inventory_markdown(report)
    assert (
        "  - disturb_method: {'dropPacketRate': 10, 'rateLimit': 0.512, "
        "'increaseLatency': 300}" in markdown
    )
    assert "  - duration: 36000" in markdown
