"""Tests for Firewalla Local diagnostics."""

from __future__ import annotations

import dataclasses
import json
import typing
from types import SimpleNamespace
from typing import Any, Final, cast

from homeassistant.core import HomeAssistant

from custom_components.firewalla_local.const import (
    CONF_AID,
    CONF_DEVICE_TRACKER_AWAY_WINDOW,
    CONF_DEVICE_TRACKERS,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_LLM_TOOL_MODE,
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    CONF_SYMMETRIC_KEY,
    CONF_WATCHED_DEVICES,
    CONF_WATCHED_USERS,
    DOMAIN,
)
from custom_components.firewalla_local.coordinator import FirewallaConfigEntry
from custom_components.firewalla_local.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.firewalla_local.models import (
    FirewallaAlarm,
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaGroupRuntime,
    FirewallaHostRuntime,
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
    FirewallaUserRuntime,
)


def _snapshot() -> FirewallaRuntimeSnapshot:
    """Return a representative runtime snapshot for diagnostics tests."""
    return FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Firewalla",
            device_name=None,
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="744",
                action="block",
                target="social",
                target_type="category",
                direction="bidirection",
                enabled=True,
                purpose=None,
                scope=(),
                tag_refs=("tag:17",),
                target_name="social",
            ),
        ),
        exception_rule_count=1,
    )


async def test_get_config_entry_diagnostics_redacts_entry_data(
    hass: HomeAssistant,
) -> None:
    """Test diagnostics redact sensitive config entry values."""
    entry = cast(
        FirewallaConfigEntry,
        SimpleNamespace(
            domain=DOMAIN,
            title="Firewalla",
            data={
                CONF_LICENSE: "license-123",
                CONF_HOST: "192.168.200.1",
                CONF_GID: "gid-123",
                CONF_EID: "eid-123",
                CONF_AID: "aid-123",
                CONF_SYMMETRIC_KEY: "symmetric-key",
            },
            options={
                CONF_SELECTED_RULE_IDS: ["744"],
                CONF_SELECTED_RULE_TEMPLATES: [
                    {
                        "source_rule_id": "744",
                        "name": "block social",
                        "action": "block",
                        "target": "social",
                        "target_type": "category",
                        "scope": [],
                        "tag_refs": ["tag:17"],
                        "dnsmasq_only": None,
                        "use_bf": False,
                    }
                ],
            },
            runtime_data=SimpleNamespace(
                coordinator=SimpleNamespace(
                    data=_snapshot(),
                    last_init_payload={
                        "networkProfiles": {
                            "net-1": {"name": "Universe", "intf": "eth0"}
                        },
                        "hosts": [],
                    },
                )
            ),
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    entry_data = cast(dict[str, str], diagnostics["entry_data"])

    assert entry_data == {
        CONF_LICENSE: "**REDACTED**",
        CONF_HOST: "**REDACTED**",
        CONF_GID: "**REDACTED**",
        CONF_EID: "**REDACTED**",
        CONF_AID: "**REDACTED**",
        CONF_SYMMETRIC_KEY: "**REDACTED**",
    }
    assert diagnostics["entry_options"] == {
        CONF_SELECTED_RULE_IDS: ["744"],
        CONF_SELECTED_RULE_TEMPLATES: [
            {
                "source_rule_id": "744",
                "name": "block social",
                "action": "block",
                "target": "social",
                "target_type": "category",
                "scope": [],
                "tag_refs": ["tag:17"],
                "dnsmasq_only": None,
                "use_bf": False,
            }
        ],
    }
    assert diagnostics["runtime_snapshot"] is not None
    assert diagnostics["runtime_init_payload"] == {
        "networkProfiles": {"net-1": {"name": "Universe", "intf": "eth0"}},
        "hosts": [],
    }


async def test_get_config_entry_diagnostics_redacts_selected_hosts(
    hass: HomeAssistant,
) -> None:
    """Test the option lists that name devices and people are redacted.

    The options are not credentials, but `device_trackers`, `watched_devices` and
    `watched_users` are lists of MAC addresses and user ids — the household's
    devices and people by another name. The non-identifying options are kept, so a
    report still shows how it was configured.
    """
    entry = cast(
        FirewallaConfigEntry,
        SimpleNamespace(
            domain=DOMAIN,
            title="Firewalla",
            data={CONF_LICENSE: "license-123"},
            options={
                CONF_DEVICE_TRACKERS: ["AA:BB:CC:DD:EE:FF"],
                CONF_WATCHED_DEVICES: ["Kaden Phone"],
                CONF_WATCHED_USERS: ["u-1"],
                CONF_DEVICE_TRACKER_AWAY_WINDOW: 15,
                CONF_LLM_TOOL_MODE: "off",
            },
            runtime_data=SimpleNamespace(
                coordinator=SimpleNamespace(data=None, last_init_payload=None)
            ),
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    options = cast(dict[str, Any], diagnostics["entry_options"])

    assert options[CONF_DEVICE_TRACKERS] == "**REDACTED**"
    assert options[CONF_WATCHED_DEVICES] == "**REDACTED**"
    assert options[CONF_WATCHED_USERS] == "**REDACTED**"
    # Configuration that names nothing is still readable.
    assert options[CONF_DEVICE_TRACKER_AWAY_WINDOW] == 15
    assert options[CONF_LLM_TOOL_MODE] == "off"

    serialized = json.dumps(diagnostics, default=str)
    assert "AA:BB:CC:DD:EE:FF" not in serialized
    assert "Kaden Phone" not in serialized


async def test_get_config_entry_diagnostics_handles_missing_snapshot(
    hass: HomeAssistant,
) -> None:
    """Test diagnostics return a null runtime snapshot when unavailable."""
    entry = cast(
        FirewallaConfigEntry,
        SimpleNamespace(
            domain=DOMAIN,
            title="Firewalla",
            data={CONF_LICENSE: "license-123"},
            options={},
            runtime_data=SimpleNamespace(
                coordinator=SimpleNamespace(data=None, last_init_payload=None)
            ),
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    entry_data = cast(dict[str, str], diagnostics["entry_data"])

    assert entry_data[CONF_LICENSE] == "**REDACTED**"
    assert diagnostics["entry_options"] == {}
    assert diagnostics["runtime_snapshot"] is None
    assert diagnostics["runtime_init_payload"] is None


# Every value below is something a user must not publish by pasting a report.
_SENSITIVE_VALUES = (
    "Kaden Phone",
    "KADEN",
    "kid.example.com",
    "kaden-phone",
    "kaden.example.com",
    "AA:BB:CC:DD:EE:FF",
    "192.168.200.25",
    "serial-abc123",
    "abc.ddns.net",
    "203.0.113.7",
    "Example ISP",
    "speed.example.net",
    "vimeo.com",
    # An alarm's message is prose, so only the key-name pass can catch it.
    "Kaden-PhoneMarker watched",
    # A public address reported as a mapping is redacted by key, not by pattern;
    # an IPv6 one only the pattern can reach.
    "2001:db8::1",
)


def _sensitive_snapshot() -> FirewallaRuntimeSnapshot:
    """Return a snapshot carrying every identifying field the model exposes."""
    return FirewallaRuntimeSnapshot(
        appliance_identity=FirewallaApplianceIdentityInput(
            host="192.168.200.1",
            group_name="Home",
            device_name="Living Room Gold",
            model="gold",
            serial_number="serial-abc123",
            software_version="1.0.0",
        ),
        appliance_runtime=FirewallaApplianceRuntimeInput(
            ddns="abc.ddns.net",
            timezone_name="America/New_York",
            public_ip="203.0.113.7",
            public_ips={"wan": "203.0.113.7", "wan6": "2001:db8::1"},
        ),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="744",
                action="block",
                target="vimeo.com",
                target_type="dns",
                direction="bidirection",
                enabled=True,
                purpose=None,
                scope=("AA:BB:CC:DD:EE:FF",),
                tag_refs=("tag:17",),
                target_name="Vimeo",
                raw_update_payload={
                    "target": "vimeo.com",
                    "p.device.mac": "AA:BB:CC:DD:EE:FF",
                    "disturbLevel": 2,
                },
            ),
        ),
        exception_rule_count=1,
        hosts=(
            FirewallaHostRuntime(
                mac="AA:BB:CC:DD:EE:FF",
                host_name="Kaden Phone",
                ip_address="192.168.200.25",
                group_name="KADEN",
                network_name="VLAN10 CORE",
                connection_type="phone",
                last_active=1774285600.0,
                download_bytes=1,
                upload_bytes=2,
                stale=False,
                dns_hostname="kaden-phone",
                dns_fqdn="kaden.example.com",
                dhcp_name="kid.example.com",
            ),
        ),
        groups=(
            FirewallaGroupRuntime(
                group_id="17",
                name="KADEN",
                kind=cast(Any, "group"),
            ),
        ),
        users=(
            FirewallaUserRuntime(
                user_id="u-1",
                name="Kaden",
                affiliated_group_id="17",
                affiliated_group_name="KADEN",
                total_minutes_today=60,
                unique_minutes_today=30,
            ),
        ),
        speed_tests=(
            FirewallaSpeedTestRecord(
                tested_at_timestamp=1774285600.0,
                download_mbps=900.0,
                upload_mbps=800.0,
                latency_ms=5.0,
                jitter_ms=1.0,
                packet_loss_percent=0.0,
                download_megabytes=100.0,
                upload_megabytes=50.0,
                isp="Example ISP",
                public_ip="203.0.113.7",
                server_country="US",
                server_host="speed.example.net",
                server_id="srv-1",
                server_location="New York",
                server_sponsor="Example Sponsor",
                manual=False,
                success=True,
                vendor="ookla",
            ),
        ),
        # An alarm names its host in `message` as well as in `device_name`, and the
        # message is prose, so a key-name pass is the only thing that catches it.
        alarms=(
            FirewallaAlarm(
                alarm_id="1728",
                alarm_type="ALARM_INTEL",
                device_name="Kaden Phone",
                message="Kaden-PhoneMarker watched vimeo.com",
                state="active",
                is_archived=False,
                fired_at=1774285600.0,
                remote_category=None,
                remote_host="vimeo.com",
                remote_ip="203.0.113.7",
                remote_app=None,
                remote_region=None,
                remote_latitude=None,
                remote_longitude=None,
                interface_name="bond0.60",
                protocol="tcp",
                severity="minor",
            ),
        ),
    )


async def test_get_config_entry_diagnostics_leaks_no_identifying_value(
    hass: HomeAssistant,
) -> None:
    """Test no personal value survives anywhere in the diagnostics payload.

    Diagnostics get pasted into public issues, so this asserts over the whole
    serialized payload rather than field by field: a new model field that carries
    a name or an address fails here instead of in an issue thread.
    """
    entry = cast(
        FirewallaConfigEntry,
        SimpleNamespace(
            domain=DOMAIN,
            title="Firewalla",
            data={CONF_LICENSE: "license-123"},
            options={},
            runtime_data=SimpleNamespace(
                coordinator=SimpleNamespace(
                    data=_sensitive_snapshot(),
                    last_init_payload={"hosts": []},
                )
            ),
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    serialized = json.dumps(diagnostics, default=str)

    leaked = [value for value in _SENSITIVE_VALUES if value in serialized]
    assert leaked == [], f"identifying values published in diagnostics: {leaked}"

    # The payload is redacted, not gutted: the counts and the box's own object
    # ids are what make a report diagnosable.
    snapshot = cast(dict[str, Any], diagnostics["runtime_snapshot"])
    assert snapshot["exception_rule_count"] == 1
    assert snapshot["policy_rules"][0]["rule_id"] == "744"
    assert snapshot["appliance_runtime"]["timezone_name"] == "America/New_York"
    assert snapshot["hosts"][0]["last_active"] == 1774285600.0
    assert snapshot["speed_tests"][0]["download_mbps"] == 900.0
    assert snapshot["users"][0]["total_minutes_today"] == 60

    # Raw protocol records are omitted rather than redacted: they duplicate the
    # normalized fields beside them and are large. The marker keeps the fact that
    # something was withheld, so a reader is not misled into thinking it is empty.
    assert snapshot["policy_rules"][0]["raw_update_payload"] == (
        "**OMITTED** (3 raw protocol keys)"
    )


# Fields that are published verbatim on purpose: they classify a device or the
# appliance rather than name one, so they carry no household data. Anything not
# listed here must be redacted, which is what makes a newly added field fail this
# test until someone decides which it is.
_SNAPSHOT_FIELDS_PUBLISHED_VERBATIM: Final = frozenset(
    {
        "alarm_type",
        "blocked_by_rule_id",
        "category",
        "cloud_connected",
        "connection_type",
        "destination_kind",
        "direction",
        "dist_codename",
        "enabled",
        "firmware_release_type",
        "host_device_type",
        "interface_name",
        "is_archived",
        "kind",
        "membership_kind",
        "model",
        "protocol",
        "remote_app",
        "remote_category",
        "remote_region",
        "severity",
        "software_version",
        "state",
        "timezone_name",
        "vendor",
    }
)


def _is_string_annotation(annotation: object) -> bool:
    """Return whether a resolved annotation is `str` or `str | None`."""
    if annotation is str:
        return True
    return typing.get_origin(annotation) is typing.Union and str in (
        typing.get_args(annotation) or ()
    )


def _reachable_string_fields(root: type) -> dict[str, type]:
    """Return every reachable string-typed field, keyed by field name."""
    found: dict[str, type] = {}
    pending, seen = [root], set()
    while pending:
        cls = pending.pop()
        if cls in seen or not dataclasses.is_dataclass(cls):
            continue
        seen.add(cls)
        try:
            hints = typing.get_type_hints(cls)
        except Exception:
            hints = {}
        for field_info in dataclasses.fields(cls):
            annotation = hints.get(field_info.name, field_info.type)
            if _is_string_annotation(annotation):
                found[field_info.name] = cls
            # Follow containers and nested dataclasses either way, since a string
            # field can live inside a tuple of records.
            for argument in typing.get_args(annotation) or (annotation,):
                for inner in typing.get_args(argument) or (argument,):
                    if dataclasses.is_dataclass(inner):
                        pending.append(inner)
    return found


def test_the_verbatim_field_list_is_not_stale() -> None:
    """Every declared-verbatim field still exists, so the list cannot rot silently.

    Checked against every reachable field rather than only the string ones: the
    list also exempts non-string fields, which are skipped by the redaction guard
    but must not linger after a rename.
    """
    known: set[str] = set()
    pending, seen = [FirewallaRuntimeSnapshot], set()
    while pending:
        cls = pending.pop()
        if cls in seen or not dataclasses.is_dataclass(cls):
            continue
        seen.add(cls)
        for field_info in dataclasses.fields(cls):
            known.add(field_info.name)
            try:
                annotation = typing.get_type_hints(cls).get(
                    field_info.name, field_info.type
                )
            except Exception:
                continue
            for argument in typing.get_args(annotation) or (annotation,):
                for inner in typing.get_args(argument) or (argument,):
                    if dataclasses.is_dataclass(inner):
                        pending.append(inner)

    renamed = sorted(_SNAPSHOT_FIELDS_PUBLISHED_VERBATIM - known)
    assert renamed == [], f"declared verbatim but no longer in the snapshot: {renamed}"
