"""Typed models for Firewalla Local."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FirewallaSystemInfo:
    """Basic system information for a Firewalla appliance."""

    host: str
    name: str
    model: str | None
    serial_number: str | None
    software_version: str | None


@dataclass(slots=True, frozen=True)
class FirewallaPolicyRule:
    """Normalized local policy rule data from the Firewalla init payload."""

    rule_id: str
    action: str
    target: str
    target_type: str
    direction: str | None
    enabled: bool
    purpose: str | None
    scope: tuple[str, ...]
    target_name: str | None = None
    applies_to: tuple[str, ...] = ()
    activated_time: float | None = None
    updated_time: float | None = None
    last_activated_time: float | None = None
    expire_seconds: int | None = None
    expires_at: float | None = None
    auto_delete_when_expires: bool | None = None
    dnsmasq_only: bool | None = None

    @property
    def is_temporary(self) -> bool:
        """Return whether this rule currently behaves like a temporary rule."""
        return self.expire_seconds is not None and self.auto_delete_when_expires is True


@dataclass(slots=True)
class FirewallaRuntimeSnapshot:
    """Coordinator-ready runtime snapshot fetched from the local API."""

    system_info: FirewallaSystemInfo
    policy_rules: tuple[FirewallaPolicyRule, ...]
    exception_rule_count: int


def format_policy_rule_label(rule: FirewallaPolicyRule) -> str:
    """Build a readable label for one normalized Firewalla policy rule."""
    status = "enabled" if rule.enabled else "disabled"
    applicability = f" for {', '.join(rule.applies_to)}" if rule.applies_to else ""

    if rule.target_type == "mac" and rule.target == "TAG" and rule.target_name:
        return f"{rule.action} internet for {rule.target_name} ({status})"

    display_target = rule.target
    if rule.target_name and rule.target_name != rule.target:
        display_target = f"{rule.target_name} [{rule.target}]"

    if (
        applicability
        and rule.target_name
        and applicability == f" for {rule.target_name}"
    ):
        applicability = ""

    return (
        f"{rule.action} {rule.target_type} "
        f"{display_target}{applicability} ({status})"
    )
