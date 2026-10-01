"""Tests for Firewalla Local model helpers."""

from custom_components.firewalla_local.models import (
    FirewallaAlarm,
    FirewallaNetworkKind,
    FirewallaNetworkSegment,
    FirewallaNetworkSegmentView,
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    format_policy_rule_name,
    supports_rule_switch,
)


def _alarm(
    *,
    alarm_id: str = "1728",
    remote_host: str | None = "vimeo.com",
    remote_ip: str | None = "162.159.128.61",
    device_mac: str | None = "0C:85:E1:B0:1D:1C",
) -> FirewallaAlarm:
    """Return one normalized alarm for block-template tests."""
    return FirewallaAlarm(
        alarm_id=alarm_id,
        alarm_type="ALARM_VIDEO",
        device_name="Kids-iPad",
        message=None,
        state="active",
        is_archived=False,
        fired_at=None,
        remote_category=None,
        remote_host=remote_host,
        remote_ip=remote_ip,
        remote_app=None,
        remote_region=None,
        remote_latitude=None,
        remote_longitude=None,
        interface_name=None,
        protocol=None,
        severity=None,
        raw_payload={"p.device.mac": device_mac},
    )


def test_rule_template_from_alarm_uses_domain_and_device_scope() -> None:
    """Test an alarm block template blocks the domain scoped to the device."""
    template = FirewallaRuleTemplate.from_alarm(_alarm())

    assert template is not None
    assert template.action == "block"
    assert template.target == "vimeo.com"
    assert template.target_type == "dns"
    assert template.scope == ("0C:85:E1:B0:1D:1C",)
    assert template.dnsmasq_only is True
    assert template.alarm_id == "1728"


def test_rule_template_from_alarm_falls_back_to_ip() -> None:
    """Test the template blocks the remote IP when no domain is present."""
    template = FirewallaRuleTemplate.from_alarm(
        _alarm(remote_host=None, remote_ip="203.0.113.7")
    )

    assert template is not None
    assert template.target == "203.0.113.7"
    assert template.target_type == "ip"
    assert template.dnsmasq_only is None


def test_rule_template_from_alarm_requires_device_scope() -> None:
    """Test an alarm without a device MAC cannot produce a block template."""
    assert FirewallaRuleTemplate.from_alarm(_alarm(device_mac=None)) is None


def test_rule_template_roundtrip_preserves_alarm_id() -> None:
    """Test the alarm reference survives option serialization."""
    template = FirewallaRuleTemplate.from_alarm(_alarm())
    assert template is not None

    restored = FirewallaRuleTemplate.from_dict(template.to_dict())

    assert restored is not None
    assert restored.alarm_id == "1728"
    assert restored.target == template.target


def test_rule_template_serialization_omits_absent_alarm_id() -> None:
    """Test an ordinary template keeps its prior stored shape (no alarm_id key)."""
    template = FirewallaRuleTemplate(
        source_rule_id="744",
        name="block category social for AV_SMART_TV",
        action="block",
        target="social",
        target_type="category",
    )

    assert "alarm_id" not in template.to_dict()


def test_rule_template_create_value_includes_alarm_id_when_set() -> None:
    """Test the created payload records the alarm back-reference when present."""
    template = FirewallaRuleTemplate.from_alarm(_alarm())
    assert template is not None

    payload = template.build_create_value(updated_time=1.0)

    assert payload["aid"] == "1728"


def test_network_kind_display_name_uses_acronyms() -> None:
    """Test the network-kind display name uses acronyms, not lowercased values."""
    assert FirewallaNetworkKind.LAN.display_name == "LAN"
    assert FirewallaNetworkKind.VLAN.display_name == "VLAN"
    assert FirewallaNetworkKind.VPN.display_name == "VPN"
    assert FirewallaNetworkKind.WAN.display_name == "WAN"
    assert FirewallaNetworkKind.VLAN.value == "vlan"


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


def test_format_policy_rule_name_hides_app_category_target_slug() -> None:
    """Test app-backed category labels avoid leaking raw TLX target slugs."""
    rule = FirewallaPolicyRule(
        rule_id="5a",
        action="block",
        target="TLX-fw-instagram",
        target_type="category",
        direction="outbound",
        enabled=True,
        purpose=None,
        scope=(),
        applies_to=("PAYTONS_PHONE",),
        target_name="Instagram",
    )

    assert format_policy_rule_name(rule) == "block category Instagram for PAYTONS_PHONE"


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
