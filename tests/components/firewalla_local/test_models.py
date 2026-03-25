"""Tests for Firewalla Local model helpers."""

from custom_components.firewalla_local.models import (
    FirewallaPolicyRule,
    format_policy_rule_name,
    supports_rule_switch,
)


def test_format_policy_rule_name_for_global_internet_rule() -> None:
    """Test TAG-backed firewall rules render as internet rules."""
    rule = FirewallaPolicyRule(
        rule_id="1",
        action="block",
        target="TAG",
        target_type="mac",
        direction="bidirection",
        enabled=True,
        purpose="firewall",
        scope=(),
    )

    assert format_policy_rule_name(rule) == "block internet"


def test_format_policy_rule_name_uses_prettified_category_name() -> None:
    """Test category names derived from underscore identifiers stay readable."""
    rule = FirewallaPolicyRule(
        rule_id="2",
        action="block",
        target="default_c",
        target_type="category",
        direction="bidirection",
        enabled=True,
        purpose=None,
        scope=(),
        target_name="default c",
    )

    assert format_policy_rule_name(rule) == "block category default c"


def test_format_policy_rule_name_hides_internal_network_uuid() -> None:
    """Test network labels avoid leaking raw UUIDs when a readable name exists."""
    rule = FirewallaPolicyRule(
        rule_id="4",
        action="block",
        target="5799d896-5e0f-40a5-a776-38a5d7746204",
        target_type="network",
        direction="bidirection",
        enabled=True,
        purpose=None,
        scope=(),
        target_name="bond0.10",
    )

    assert format_policy_rule_name(rule) == "block network bond0.10"


def test_format_policy_rule_name_hides_internal_qos_uuid() -> None:
    """Test QoS category labels avoid leaking raw UUIDs when a readable name exists."""
    rule = FirewallaPolicyRule(
        rule_id="5",
        action="qos",
        target="f6996818-a11e-4b93-88fb-fd94cedbc6d1",
        target_type="category",
        direction="outbound",
        enabled=True,
        purpose=None,
        scope=(),
        target_name="QoS Zoom",
    )

    assert format_policy_rule_name(rule) == "qos category QoS Zoom"


def test_supports_rule_switch_excludes_opaque_translation_list_categories() -> None:
    """Test TL category targets can back switches even without a resolved name."""
    rule = FirewallaPolicyRule(
        rule_id="3",
        action="allow",
        target="TL-56d856bb-efdc-4894-8e5f-c483555e09f6",
        target_type="category",
        direction="outbound",
        enabled=True,
        purpose=None,
        scope=(),
        target_name=None,
    )

    assert supports_rule_switch(rule) is True


def test_supports_rule_switch_accepts_ip_rules() -> None:
    """Test IP rules can back switches."""
    rule = FirewallaPolicyRule(
        rule_id="8",
        action="allow",
        target="192.168.200.124",
        target_type="ip",
        direction="outbound",
        enabled=True,
        purpose=None,
        scope=(),
        applies_to=("VLAN60 IOT",),
    )

    assert supports_rule_switch(rule) is True


def test_supports_rule_switch_accepts_remote_port_rules() -> None:
    """Test remote-port rules can back switches."""
    rule = FirewallaPolicyRule(
        rule_id="9",
        action="allow",
        target="20002",
        target_type="remotePort",
        direction="outbound",
        enabled=True,
        purpose=None,
        scope=(),
    )

    assert supports_rule_switch(rule) is True


def test_supports_rule_switch_accepts_network_rules_without_names() -> None:
    """Test network rules can back switches even without resolved names."""
    rule = FirewallaPolicyRule(
        rule_id="7",
        action="block",
        target="5799d896-5e0f-40a5-a776-38a5d7746204",
        target_type="network",
        direction="bidirection",
        enabled=True,
        purpose=None,
        scope=(),
        target_name=None,
    )

    assert supports_rule_switch(rule) is True


def test_supports_rule_switch_excludes_family_rules() -> None:
    """Test family-purpose category rules are not offered as switches."""
    rule = FirewallaPolicyRule(
        rule_id="6",
        action="block",
        target="porn",
        target_type="category",
        direction="outbound",
        enabled=True,
        purpose="family",
        scope=(),
        target_name="porn",
    )

    assert supports_rule_switch(rule) is False
