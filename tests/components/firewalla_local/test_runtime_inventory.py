"""Tests for Firewalla runtime inventory reporting."""

from __future__ import annotations

from custom_components.firewalla_local.helpers.runtime_inventory import (
    build_runtime_inventory_report,
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
    assert report["summary"]["rule_switch_candidate_count"] == 0
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
            "affiliated_group_name": "KADEN's Devices",
            "id": "21",
            "name": "KADEN",
        }
    ]
    assert report["rules"][0]["label"] == (
        "block internet for KADEN's Devices (KADEN) (enabled)"
    )
    assert not report["rule_switch_candidates"]
    assert report["user_managed_rules"] == [
        {
            "action": "block",
            "applies_to": [],
            "direction": "bidirection",
            "enabled": True,
            "expire_seconds": 3600,
            "expires_at": 1_700_003_600.0,
            "activated_time": 1_700_000_000.0,
            "updated_time": None,
            "last_activated_time": None,
            "auto_delete_when_expires": True,
            "dnsmasq_only": False,
            "is_temporary": True,
            "label": "block internet for KADEN's Devices (KADEN) (enabled)",
            "management": {
                "classification": "user_managed",
                "reasons": [],
            },
            "matching": {
                "has_readable_target_name": True,
                "kind": "internet_scope",
                "references_target_list": False,
            },
            "purpose": None,
            "raw_extras": {"expireTs": 1_700_000_000},
            "review_reasons": [],
            "rule_id": "736",
            "scope": [],
            "tag_refs": ["tag:10"],
            "target": "TAG",
            "target_name": "KADEN's Devices (KADEN)",
            "target_type": "mac",
        },
        {
            "action": "allow",
            "applies_to": [],
            "direction": "outbound",
            "enabled": True,
            "expire_seconds": None,
            "expires_at": None,
            "activated_time": None,
            "updated_time": None,
            "last_activated_time": None,
            "auto_delete_when_expires": None,
            "dnsmasq_only": None,
            "is_temporary": False,
            "label": "allow category TL-deadbeef (enabled)",
            "management": {
                "classification": "user_managed",
                "reasons": [],
            },
            "matching": {
                "has_readable_target_name": False,
                "kind": "target_list",
                "references_target_list": True,
            },
            "purpose": None,
            "raw_extras": {},
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
        },
    ]
    assert report["system_managed_rules"] == [
        {
            "action": "block",
            "applies_to": [],
            "direction": "bidirection",
            "enabled": True,
            "expire_seconds": None,
            "expires_at": None,
            "activated_time": None,
            "updated_time": None,
            "last_activated_time": None,
            "auto_delete_when_expires": None,
            "dnsmasq_only": True,
            "is_temporary": False,
            "label": "block dns bad.example (enabled)",
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
            "purpose": None,
            "raw_extras": {
                "alarm_type": "ALARM_INTEL",
                "blockby": "fastdns",
                "category": "intel",
                "method": "auto",
                "reason": "ALARM_INTEL",
            },
            "review_reasons": [],
            "rule_id": "738",
            "scope": [],
            "tag_refs": [],
            "target": "bad.example",
            "target_name": "bad.example",
            "target_type": "dns",
        }
    ]
    assert report["rules_needing_review"] == [
        {
            "action": "allow",
            "applies_to": [],
            "direction": "outbound",
            "enabled": True,
            "expire_seconds": None,
            "expires_at": None,
            "activated_time": None,
            "updated_time": None,
            "last_activated_time": None,
            "auto_delete_when_expires": None,
            "dnsmasq_only": None,
            "is_temporary": False,
            "label": "allow category TL-deadbeef (enabled)",
            "management": {
                "classification": "user_managed",
                "reasons": [],
            },
            "matching": {
                "has_readable_target_name": False,
                "kind": "target_list",
                "references_target_list": True,
            },
            "purpose": None,
            "raw_extras": {},
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
        }
    ]
    assert report["target_list_references"] == [
        {
            "has_readable_target_name": False,
            "labels": ["allow category TL-deadbeef (enabled)"],
            "management_classifications": ["user_managed"],
            "rule_count": 1,
            "rule_ids": ["737"],
            "target_list_id": "TL-deadbeef",
            "target_name": None,
        }
    ]
