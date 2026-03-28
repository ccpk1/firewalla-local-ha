"""Tests for Firewalla Local model helpers."""

from custom_components.firewalla_local.models import (
    FirewallaNetworkSegment,
    FirewallaNetworkSegmentView,
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


def test_format_policy_rule_name_prefers_custom_name() -> None:
    """Test a user-defined custom rule name overrides generated labels."""
    rule = FirewallaPolicyRule(
        rule_id="10",
        action="allow",
        target="choreops.com",
        target_type="dns",
        direction="bidirection",
        enabled=True,
        purpose=None,
        scope=(),
        applies_to=("AV_SMART_TV",),
        raw_update_payload={"_name": "ChoreOps Custom Allow"},
    )

    assert format_policy_rule_name(rule) == "ChoreOps Custom Allow"


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


def test_supports_rule_switch_accepts_qos_rules() -> None:
    """Test QoS rules can back switches."""
    rule = FirewallaPolicyRule(
        rule_id="11",
        action="qos",
        target="QoS Zoom",
        target_type="category",
        direction="bidirection",
        enabled=True,
        purpose=None,
        scope=(),
        target_name="QoS Zoom",
    )

    assert supports_rule_switch(rule) is True


def test_supports_rule_switch_accepts_disturb_rules() -> None:
    """Test disturb rules can back switches."""
    rule = FirewallaPolicyRule(
        rule_id="12",
        action="disturb",
        target="games",
        target_type="category",
        direction="bidirection",
        enabled=True,
        purpose=None,
        scope=(),
        target_name="games",
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


def test_supports_rule_switch_excludes_dap_rules() -> None:
    """Test Device Active Protect rules are not offered as switches."""
    rule = FirewallaPolicyRule(
        rule_id="13",
        action="allow",
        target="dap_08f9e076ca6f",
        target_type="category",
        direction="outbound",
        enabled=False,
        purpose="dap",
        scope=("08:F9:E0:76:CA:6F",),
        target_name="DAP - 08:F9:E0:76:CA:6F",
    )

    assert supports_rule_switch(rule) is False


def test_supports_rule_switch_accepts_port_forwarding_rules() -> None:
    """Test port-forwarding rules are offered as switches."""
    rule = FirewallaPolicyRule(
        rule_id="14",
        action="allow",
        target="US",
        target_type="country",
        direction="inbound",
        enabled=True,
        purpose="port_forwarding",
        scope=("00:AA:BB:CC:62:53",),
        target_name=None,
    )

    assert supports_rule_switch(rule) is True


def test_supports_rule_switch_excludes_unknown_non_null_purposes() -> None:
    """Test unknown product purposes stay out of the switch surface."""
    rule = FirewallaPolicyRule(
        rule_id="15",
        action="block",
        target="TAG",
        target_type="mac",
        direction="bidirection",
        enabled=True,
        purpose="new_product_surface",
        scope=(),
    )

    assert supports_rule_switch(rule) is False


def test_network_segment_view_host_count_tracks_normalized_hosts() -> None:
    """Test network summary views expose a stable derived host count."""
    view = FirewallaNetworkSegmentView(
        target=FirewallaNetworkSegment(
            uuid="5799d896-5e0f-40a5-a776-38a5d7746204",
            name="VLAN10 CORE",
        ),
    )

    assert view.host_count == 0


def test_supports_rule_switch_excludes_firewall_rules() -> None:
    """Test firewall-purpose rules are not offered as switches."""
    rule = FirewallaPolicyRule(
        rule_id="16",
        action="block",
        target="TAG",
        target_type="mac",
        direction="bidirection",
        enabled=True,
        purpose="firewall",
        scope=(),
    )

    assert supports_rule_switch(rule) is False
