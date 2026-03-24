"""Runtime inventory helpers for Firewalla Local."""

from __future__ import annotations

from typing import Final, TypedDict

from custom_components.firewalla_local.managers.rule_manager import (
    build_rule_management_info,
    build_rule_review_reasons,
    build_rule_switch_candidate_ids,
    extract_raw_rule_extras,
)
from custom_components.firewalla_local.models import (
    FirewallaPolicyRule,
    format_policy_rule_label,
)

_RAW_POLICY_STATE_KEY: Final = "state"
_RAW_USERS_KEY: Final = "userTags"
_RAW_GROUPS_KEY: Final = "tags"
_RAW_GROUP_POLICY_KEY: Final = "policy"
_RAW_NAME_KEY: Final = "name"
_RAW_AFFILIATED_TAG_KEY: Final = "affiliatedTag"
_RAW_POLICY_RULES_KEY: Final = "policyRules"
_RAW_RULE_ID_KEY: Final = "pid"
_RAW_RULE_TAG_REFS_KEY: Final = "tag"
_RAW_HOSTS_KEY: Final = "hosts"
_RAW_NETWORK_PROFILES_KEY: Final = "networkProfiles"
_RAW_GROUP_USER_TAGS_KEY: Final = "userTags"

_RULE_MATCH_KIND_INTERNET_SCOPE: Final = "internet_scope"
_RULE_MATCH_KIND_TARGET_LIST: Final = "target_list"
_RULE_MATCH_KIND_DOMAIN: Final = "domain"
_RULE_MATCH_KIND_IP: Final = "ip"
_RULE_MATCH_KIND_REMOTE_PORT: Final = "remote_port"
_RULE_MATCH_KIND_LOCAL_PORT: Final = "local_port"
_RULE_MATCH_KIND_COUNTRY: Final = "country"
_RULE_MATCH_KIND_NETWORK: Final = "network"
_RULE_MATCH_KIND_CATEGORY: Final = "category"
_RULE_MATCH_KIND_OTHER: Final = "other"

_RULE_TARGET_LIST_PREFIX: Final = "TL-"
_RULE_TARGET_TAG: Final = "TAG"
_RULE_TARGET_TYPE_CATEGORY: Final = "category"
_RULE_TARGET_TYPE_COUNTRY: Final = "country"
_RULE_TARGET_TYPE_DNS: Final = "dns"
_RULE_TARGET_TYPE_IP: Final = "ip"
_RULE_TARGET_TYPE_LOCAL_PORT: Final = "localPort"
_RULE_TARGET_TYPE_MAC: Final = "mac"
_RULE_TARGET_TYPE_NETWORK: Final = "network"
_RULE_TARGET_TYPE_REMOTE_PORT: Final = "remotePort"

_RULE_PURPOSE_DAP: Final = "dap"
_RULE_PURPOSE_FAMILY: Final = "family"
_RULE_MANAGEMENT_CLASSIFICATION_SYSTEM: Final = "system_managed"
_RULE_MANAGEMENT_CLASSIFICATION_USER: Final = "user_managed"


class RuntimeUserRecord(TypedDict):
    """Normalized runtime user entry used inside inventory helpers."""

    id: str
    name: str | None
    affiliated_group_id: str | None


class RuntimeGroupRecord(TypedDict):
    """Normalized runtime group entry used inside inventory helpers."""

    id: str
    name: str | None
    policy: dict[str, object]
    user_ids: list[str]
    user_names: list[str]


class RuntimeUserInventoryRecord(RuntimeUserRecord):
    """Runtime user entry with resolved affiliated group name."""

    affiliated_group_name: str | None


class GroupPolicyControlRecord(TypedDict):
    """Flattened group policy control record for reporting."""

    group_id: object
    group_name: object
    policy_key: str
    value: bool | int | float | str
    user_names: list[str]


class RuleMatchingInfo(TypedDict):
    """Classified matching surface for one rule."""

    kind: str
    references_target_list: bool
    has_readable_target_name: bool


def _flatten_policy(value: object) -> object:
    """Flatten nested Firewalla policy values into stable simple values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if _RAW_POLICY_STATE_KEY in value and isinstance(
            value[_RAW_POLICY_STATE_KEY], bool
        ):
            return value[_RAW_POLICY_STATE_KEY]
        return {
            key: flattened_value
            for key, nested_value in value.items()
            if (flattened_value := _flatten_policy(nested_value)) is not None
        }
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, (int, float, str)):
        return value
    return None


def _build_user_index(data: dict[str, object]) -> dict[str, RuntimeUserRecord]:
    """Build a typed user index from the raw init payload."""
    raw_user_tags = data.get(_RAW_USERS_KEY)
    if not isinstance(raw_user_tags, dict):
        return {}

    user_index: dict[str, RuntimeUserRecord] = {}
    for user_id, raw_user in raw_user_tags.items():
        if not isinstance(user_id, str) or not isinstance(raw_user, dict):
            continue

        user_name = raw_user.get(_RAW_NAME_KEY)
        affiliated_tag = raw_user.get(_RAW_AFFILIATED_TAG_KEY)
        user_index[user_id] = {
            "id": user_id,
            "name": user_name if isinstance(user_name, str) else None,
            "affiliated_group_id": (
                affiliated_tag if isinstance(affiliated_tag, str) else None
            ),
        }

    return user_index


def _build_group_inventory(data: dict[str, object]) -> list[RuntimeGroupRecord]:
    """Build a readable inventory of Firewalla groups."""
    raw_groups = data.get(_RAW_GROUPS_KEY)
    if not isinstance(raw_groups, dict):
        return []

    user_index = _build_user_index(data)
    groups: list[RuntimeGroupRecord] = []
    for group_id, raw_group in raw_groups.items():
        if not isinstance(group_id, str) or not isinstance(raw_group, dict):
            continue

        policy = raw_group.get(_RAW_GROUP_POLICY_KEY)
        flattened_policy = (
            {
                key: flattened_value
                for key, value in policy.items()
                if (flattened_value := _flatten_policy(value)) is not None
            }
            if isinstance(policy, dict)
            else {}
        )
        raw_group_user_ids = flattened_policy.get(_RAW_GROUP_USER_TAGS_KEY)
        group_user_id_values = (
            raw_group_user_ids if isinstance(raw_group_user_ids, list) else []
        )
        group_user_ids = [
            user_id for user_id in group_user_id_values if isinstance(user_id, str)
        ]
        group_user_names = [
            user_record["name"]
            for user_id in group_user_ids
            if (user_record := user_index.get(user_id)) and user_record["name"]
        ]

        group_name = raw_group.get(_RAW_NAME_KEY)
        groups.append(
            {
                "id": group_id,
                "name": group_name if isinstance(group_name, str) else None,
                "policy": flattened_policy,
                "user_ids": group_user_ids,
                "user_names": group_user_names,
            }
        )

    return sorted(groups, key=lambda group: (group["name"] or "", group["id"]))


def _build_user_inventory(
    data: dict[str, object],
) -> list[RuntimeUserInventoryRecord]:
    """Build a readable inventory of Firewalla users."""
    user_index = _build_user_index(data)
    group_names = {group["id"]: group["name"] for group in _build_group_inventory(data)}
    users: list[RuntimeUserInventoryRecord] = []
    for user in user_index.values():
        affiliated_group_id = user["affiliated_group_id"]
        users.append(
            {
                **user,
                "affiliated_group_name": (
                    group_names.get(affiliated_group_id)
                    if isinstance(affiliated_group_id, str)
                    else None
                ),
            }
        )
    return sorted(users, key=lambda user: (user["name"] or "", user["id"]))


def _build_group_policy_controls(
    groups: list[RuntimeGroupRecord],
) -> list[GroupPolicyControlRecord]:
    """Build a flattened list of group-backed policy controls."""
    controls: list[GroupPolicyControlRecord] = []
    for group in groups:
        policy = group["policy"]

        for policy_key, policy_value in sorted(policy.items()):
            if policy_key == _RAW_GROUP_USER_TAGS_KEY:
                continue
            if not isinstance(policy_value, (bool, int, float, str)):
                continue

            user_names = [name for name in group["user_names"] if isinstance(name, str)]

            controls.append(
                {
                    "group_id": group["id"],
                    "group_name": group["name"],
                    "policy_key": policy_key,
                    "value": policy_value,
                    "user_names": user_names,
                }
            )

    return controls


def _build_rule_matching_info(rule: FirewallaPolicyRule) -> RuleMatchingInfo:
    """Classify the matching object shape for one rule."""
    if rule.target_type == _RULE_TARGET_TYPE_MAC and rule.target == _RULE_TARGET_TAG:
        kind = _RULE_MATCH_KIND_INTERNET_SCOPE
    elif rule.target.startswith(_RULE_TARGET_LIST_PREFIX):
        kind = _RULE_MATCH_KIND_TARGET_LIST
    elif rule.target_type == _RULE_TARGET_TYPE_DNS:
        kind = _RULE_MATCH_KIND_DOMAIN
    elif rule.target_type == _RULE_TARGET_TYPE_IP:
        kind = _RULE_MATCH_KIND_IP
    elif rule.target_type == _RULE_TARGET_TYPE_REMOTE_PORT:
        kind = _RULE_MATCH_KIND_REMOTE_PORT
    elif rule.target_type == _RULE_TARGET_TYPE_LOCAL_PORT:
        kind = _RULE_MATCH_KIND_LOCAL_PORT
    elif rule.target_type == _RULE_TARGET_TYPE_COUNTRY:
        kind = _RULE_MATCH_KIND_COUNTRY
    elif rule.target_type == _RULE_TARGET_TYPE_NETWORK:
        kind = _RULE_MATCH_KIND_NETWORK
    elif rule.target_type == _RULE_TARGET_TYPE_CATEGORY:
        kind = _RULE_MATCH_KIND_CATEGORY
    else:
        kind = _RULE_MATCH_KIND_OTHER

    return {
        "kind": kind,
        "references_target_list": rule.target.startswith(_RULE_TARGET_LIST_PREFIX),
        "has_readable_target_name": rule.target_name is not None,
    }


def _build_target_list_references(
    rules: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Build an aggregated view of target-list-backed rules."""
    target_lists: dict[str, dict[str, object]] = {}

    for rule in rules:
        target = rule.get("target")
        if not isinstance(target, str):
            continue
        if not target.startswith(_RULE_TARGET_LIST_PREFIX):
            continue

        entry = target_lists.setdefault(
            target,
            {
                "target_list_id": target,
                "target_name": rule.get("target_name"),
                "has_readable_target_name": bool(rule.get("target_name")),
                "rule_count": 0,
                "rule_ids": [],
                "labels": [],
                "management_classifications": [],
            },
        )
        rule_count = entry.get("rule_count")
        entry["rule_count"] = rule_count + 1 if isinstance(rule_count, int) else 1
        cast_rule_ids = entry["rule_ids"]
        if isinstance(cast_rule_ids, list):
            cast_rule_ids.append(rule.get("rule_id"))
        cast_labels = entry["labels"]
        if isinstance(cast_labels, list):
            cast_labels.append(rule.get("label"))
        cast_management = entry["management_classifications"]
        management = rule.get("management")
        if isinstance(cast_management, list) and isinstance(management, dict):
            cast_management.append(management.get("classification"))

    for entry in target_lists.values():
        if isinstance(entry["rule_ids"], list):
            entry["rule_ids"] = sorted(
                {str(rule_id) for rule_id in entry["rule_ids"] if rule_id is not None}
            )
        if isinstance(entry["labels"], list):
            entry["labels"] = sorted(
                {str(label) for label in entry["labels"] if label is not None}
            )
        if isinstance(entry["management_classifications"], list):
            entry["management_classifications"] = sorted(
                {
                    str(classification)
                    for classification in entry["management_classifications"]
                    if classification is not None
                }
            )

    return sorted(target_lists.values(), key=lambda entry: str(entry["target_list_id"]))


def build_runtime_inventory_report(
    payload: dict[str, object],
    policy_rules: tuple[FirewallaPolicyRule, ...],
) -> dict[str, object]:
    """Build a mapping report for groups, users, and normalized rules."""
    raw_policy_rules = payload.get(_RAW_POLICY_RULES_KEY)
    raw_rule_index: dict[str, dict[str, object]] = {}
    if isinstance(raw_policy_rules, list):
        raw_rule_index = {
            raw_rule[_RAW_RULE_ID_KEY]: raw_rule
            for raw_rule in raw_policy_rules
            if isinstance(raw_rule, dict) and isinstance(raw_rule.get("pid"), str)
        }
    groups = _build_group_inventory(payload)
    users = _build_user_inventory(payload)
    raw_hosts = payload.get(_RAW_HOSTS_KEY)
    raw_networks = payload.get(_RAW_NETWORK_PROFILES_KEY)
    host_count = len(raw_hosts) if isinstance(raw_hosts, list) else 0
    network_count = len(raw_networks) if isinstance(raw_networks, dict) else 0
    candidate_rule_ids = build_rule_switch_candidate_ids(payload, policy_rules)

    rules: list[dict[str, object]] = []
    rules_needing_review: list[dict[str, object]] = []
    rule_switch_candidates: list[dict[str, object]] = []
    system_managed_rules: list[dict[str, object]] = []
    user_managed_rules: list[dict[str, object]] = []
    visible_rules: list[dict[str, object]] = []
    visible_enabled_rules: list[dict[str, object]] = []
    dap_rules: list[dict[str, object]] = []
    family_rules: list[dict[str, object]] = []
    for rule in policy_rules:
        raw_rule = raw_rule_index.get(rule.rule_id, {})
        review_reasons = build_rule_review_reasons(rule, raw_rule)
        raw_extras = extract_raw_rule_extras(raw_rule)
        management = build_rule_management_info(raw_extras)
        matching = _build_rule_matching_info(rule)
        raw_tag_refs = raw_rule.get(_RAW_RULE_TAG_REFS_KEY)
        tag_refs = (
            [tag_ref for tag_ref in raw_tag_refs if isinstance(tag_ref, str)]
            if isinstance(raw_tag_refs, list)
            else []
        )
        rule_record: dict[str, object] = {
            "rule_id": rule.rule_id,
            "label": format_policy_rule_label(rule),
            "action": rule.action,
            "target": rule.target,
            "target_name": rule.target_name,
            "target_type": rule.target_type,
            "direction": rule.direction,
            "purpose": rule.purpose,
            "enabled": rule.enabled,
            "scope": list(rule.scope),
            "applies_to": list(rule.applies_to),
            "activated_time": rule.activated_time,
            "updated_time": rule.updated_time,
            "last_activated_time": rule.last_activated_time,
            "expire_seconds": rule.expire_seconds,
            "expires_at": rule.expires_at,
            "auto_delete_when_expires": rule.auto_delete_when_expires,
            "dnsmasq_only": rule.dnsmasq_only,
            "is_temporary": rule.is_temporary,
            "tag_refs": tag_refs,
            "raw_extras": raw_extras,
            "management": management,
            "matching": matching,
            "review_reasons": review_reasons,
        }
        rules.append(rule_record)
        if management["classification"] == _RULE_MANAGEMENT_CLASSIFICATION_SYSTEM:
            system_managed_rules.append(rule_record)
        else:
            user_managed_rules.append(rule_record)
        if rule.purpose == _RULE_PURPOSE_DAP:
            dap_rules.append(rule_record)
        elif rule.purpose == _RULE_PURPOSE_FAMILY:
            family_rules.append(rule_record)
        elif management["classification"] == _RULE_MANAGEMENT_CLASSIFICATION_USER:
            visible_rules.append(rule_record)
            if rule.enabled:
                visible_enabled_rules.append(rule_record)
        if rule.rule_id in candidate_rule_ids:
            rule_switch_candidates.append(rule_record)
        if review_reasons:
            rules_needing_review.append(rule_record)

    group_policy_controls = _build_group_policy_controls(groups)
    target_list_references = _build_target_list_references(rules)

    return {
        "summary": {
            "group_count": len(groups),
            "group_policy_control_count": len(group_policy_controls),
            "user_count": len(users),
            "policy_rule_count": len(rules),
            "dap_rule_count": len(dap_rules),
            "family_rule_count": len(family_rules),
            "user_managed_rule_count": len(user_managed_rules),
            "system_managed_rule_count": len(system_managed_rules),
            "visible_rule_count": len(visible_rules),
            "visible_enabled_rule_count": len(visible_enabled_rules),
            "rule_switch_candidate_count": len(rule_switch_candidates),
            "rules_needing_review_count": len(rules_needing_review),
            "target_list_reference_count": len(target_list_references),
            "host_count": host_count,
            "network_count": network_count,
        },
        "groups": groups,
        "group_policy_controls": group_policy_controls,
        "users": users,
        "rules": rules,
        "user_managed_rules": user_managed_rules,
        "system_managed_rules": system_managed_rules,
        "rule_switch_candidates": rule_switch_candidates,
        "rules_needing_review": rules_needing_review,
        "target_list_references": target_list_references,
    }


def render_runtime_inventory_markdown(report: dict[str, object]) -> str:
    """Render a markdown view of the runtime inventory report."""
    summary = report.get("summary")
    groups = report.get("groups")
    group_policy_controls = report.get("group_policy_controls")
    users = report.get("users")
    rules = report.get("rules")
    user_managed_rules = report.get("user_managed_rules")
    system_managed_rules = report.get("system_managed_rules")
    rule_switch_candidates = report.get("rule_switch_candidates")
    rules_needing_review = report.get("rules_needing_review")
    target_list_references = report.get("target_list_references")

    lines = ["# Firewalla runtime inventory", "", "## Summary", ""]

    if isinstance(summary, dict):
        for key in (
            "group_count",
            "group_policy_control_count",
            "user_count",
            "policy_rule_count",
            "dap_rule_count",
            "family_rule_count",
            "user_managed_rule_count",
            "system_managed_rule_count",
            "visible_rule_count",
            "visible_enabled_rule_count",
            "rule_switch_candidate_count",
            "rules_needing_review_count",
            "target_list_reference_count",
            "host_count",
            "network_count",
        ):
            lines.append(f"- {key}: {summary.get(key)}")

    lines.extend(["", "## Groups", ""])
    if isinstance(groups, list) and groups:
        for group in groups:
            if not isinstance(group, dict):
                continue

            lines.append(
                f"- {group.get('name') or group.get('id')} (id: {group.get('id')})"
            )
            user_names = group.get("user_names")
            if isinstance(user_names, list) and user_names:
                joined_user_names = ", ".join(str(name) for name in user_names)
                lines.append(f"  - users: {joined_user_names}")

            policy = group.get("policy")
            if isinstance(policy, dict) and policy:
                lines.append("  - policy:")
                for policy_key, policy_value in sorted(policy.items()):
                    lines.append(f"    - {policy_key}: {policy_value}")
    else:
        lines.append("- none")

    lines.extend(["", "## User-managed Rules", ""])
    if isinstance(user_managed_rules, list) and user_managed_rules:
        for rule in user_managed_rules:
            if not isinstance(rule, dict):
                continue
            lines.append(f"- {rule.get('label')} [id: {rule.get('rule_id')}]")
    else:
        lines.append("- none")

    lines.extend(["", "## System-managed Rules", ""])
    if isinstance(system_managed_rules, list) and system_managed_rules:
        for rule in system_managed_rules:
            if not isinstance(rule, dict):
                continue
            management = rule.get("management")
            management_reasons = (
                ", ".join(str(reason) for reason in management.get("reasons", []))
                if isinstance(management, dict)
                else "unknown"
            )
            lines.append(
                f"- {rule.get('label')} [id: {rule.get('rule_id')}] -> "
                f"{management_reasons}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Group Policy Controls", ""])
    if isinstance(group_policy_controls, list) and group_policy_controls:
        for control in group_policy_controls:
            if not isinstance(control, dict):
                continue
            user_names = control.get("user_names")
            scope_suffix = ""
            if isinstance(user_names, list) and user_names:
                scope_suffix = f" ({', '.join(str(name) for name in user_names)})"
            lines.append(
                f"- {control.get('group_name') or control.get('group_id')}: "
                f"{control.get('policy_key')} = {control.get('value')}"
                f"{scope_suffix}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Users", ""])
    if isinstance(users, list) and users:
        for user in users:
            if not isinstance(user, dict):
                continue
            affiliated_group = user.get("affiliated_group_name") or user.get(
                "affiliated_group_id"
            )
            lines.append(
                f"- {user.get('name') or user.get('id')} -> {affiliated_group}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Rules", ""])
    if isinstance(rules, list) and rules:
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            lines.append(f"- {rule.get('label')} [id: {rule.get('rule_id')}]")
    else:
        lines.append("- none")

    lines.extend(["", "## Rule Switch Candidates", ""])
    if isinstance(rule_switch_candidates, list) and rule_switch_candidates:
        for rule in rule_switch_candidates:
            if not isinstance(rule, dict):
                continue
            lines.append(f"- {rule.get('label')} [id: {rule.get('rule_id')}]")
    else:
        lines.append("- none")

    lines.extend(["", "## Rules Needing Review", ""])
    if isinstance(rules_needing_review, list) and rules_needing_review:
        for rule in rules_needing_review:
            if not isinstance(rule, dict):
                continue
            review_reasons = rule.get("review_reasons")
            joined_reasons = (
                ", ".join(str(reason) for reason in review_reasons)
                if isinstance(review_reasons, list)
                else "unknown"
            )
            lines.append(
                f"- {rule.get('label')} [id: {rule.get('rule_id')}] -> {joined_reasons}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Target List References", ""])
    if isinstance(target_list_references, list) and target_list_references:
        for target_list in target_list_references:
            if not isinstance(target_list, dict):
                continue
            target_list_name = target_list.get("target_name") or target_list.get(
                "target_list_id"
            )
            lines.append(
                f"- {target_list_name} [rules: {target_list.get('rule_count')}]"
            )
    else:
        lines.append("- none")

    return "\n".join(lines)
