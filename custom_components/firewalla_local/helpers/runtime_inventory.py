"""Runtime inventory helpers for Firewalla Local."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, TypedDict

from custom_components.firewalla_local.managers.rule_manager import (
    RuleManagementInfo,
    build_switch_rule_evaluations,
)
from custom_components.firewalla_local.models import (
    FirewallaPolicyRule,
    format_policy_rule_label,
    format_policy_rule_name,
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
_RAW_UPDATE_CUSTOM_NAME_KEY: Final = "_name"
_RAW_UPDATE_NOTES_KEY: Final = "notes"
_RAW_UPDATE_IDLE_TS_KEY: Final = "idleTs"
_RAW_UPDATE_CRON_TIME_KEY: Final = "cronTime"
_RAW_UPDATE_APP_TIME_USAGE_KEY: Final = "appTimeUsage"
_RAW_UPDATE_APP_TIME_USED_KEY: Final = "appTimeUsed"
_RAW_UPDATE_LOCAL_PORT_KEY: Final = "localPort"
_RAW_UPDATE_PROTOCOL_KEY: Final = "protocol"
_RAW_UPDATE_TRUST_KEY: Final = "trust"
_RAW_UPDATE_USE_BF_KEY: Final = "useBf"
_RAW_UPDATE_UPNP_KEY: Final = "upnp"
_RAW_UPDATE_QDISC_KEY: Final = "qdisc"
_RAW_UPDATE_RATE_LIMIT_KEY: Final = "rateLimit"
_RAW_UPDATE_TRAFFIC_DIRECTION_KEY: Final = "trafficDirection"
_RAW_UPDATE_APP_NAME_KEY: Final = "app_name"
_RAW_UPDATE_APP_UID_KEY: Final = "app_uid"
_RAW_UPDATE_DISTURB_LEVEL_KEY: Final = "disturbLevel"
_RAW_UPDATE_DISTURB_METHOD_KEY: Final = "disturbMethod"
_RAW_UPDATE_DURATION_KEY: Final = "duration"
_RAW_UPDATE_AUTO_DELETE_WHEN_EXPIRES_KEY: Final = "autoDeleteWhenExpires"
_RAW_RULE_UPDATED_TIME_KEY: Final = "updatedTime"
_RAW_RULE_ACTIVATED_TIME_KEY: Final = "activatedTime"
_RAW_RULE_LAST_ACTIVATED_TIME_KEY: Final = "lastActivatedTime"
_RAW_RULE_EXPIRE_TS_KEY: Final = "expireTs"
_RAW_RULE_DNSMASQ_ONLY_KEY: Final = "dnsmasq_only"

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

_PROMOTED_RAW_EXTRA_KEYS: Final = frozenset(
    {
        _RAW_UPDATE_CUSTOM_NAME_KEY,
        _RAW_UPDATE_NOTES_KEY,
        _RAW_UPDATE_IDLE_TS_KEY,
        _RAW_UPDATE_CRON_TIME_KEY,
        _RAW_UPDATE_APP_TIME_USAGE_KEY,
        _RAW_UPDATE_APP_TIME_USED_KEY,
        _RAW_UPDATE_LOCAL_PORT_KEY,
        _RAW_UPDATE_PROTOCOL_KEY,
        _RAW_UPDATE_TRUST_KEY,
        _RAW_UPDATE_USE_BF_KEY,
        _RAW_UPDATE_UPNP_KEY,
        _RAW_UPDATE_QDISC_KEY,
        _RAW_UPDATE_RATE_LIMIT_KEY,
        _RAW_UPDATE_TRAFFIC_DIRECTION_KEY,
        _RAW_UPDATE_APP_NAME_KEY,
        _RAW_UPDATE_APP_UID_KEY,
        _RAW_UPDATE_DISTURB_LEVEL_KEY,
        _RAW_UPDATE_DISTURB_METHOD_KEY,
        _RAW_UPDATE_DURATION_KEY,
        _RAW_UPDATE_AUTO_DELETE_WHEN_EXPIRES_KEY,
        _RAW_RULE_UPDATED_TIME_KEY,
        _RAW_RULE_ACTIVATED_TIME_KEY,
        _RAW_RULE_LAST_ACTIVATED_TIME_KEY,
        _RAW_RULE_EXPIRE_TS_KEY,
        _RAW_RULE_DNSMASQ_ONLY_KEY,
    }
)


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


def _build_report_raw_extras(raw_extras: dict[str, object]) -> dict[str, object]:
    """Return only raw rule extras that are not already promoted elsewhere."""
    return {
        key: value
        for key, value in raw_extras.items()
        if key not in _PROMOTED_RAW_EXTRA_KEYS
    }


def _build_rule_record(
    rule: FirewallaPolicyRule,
    *,
    management: RuleManagementInfo,
    matching: RuleMatchingInfo,
    review_reasons: list[str],
    raw_extras: dict[str, object],
    tag_refs: list[str],
) -> dict[str, object]:
    """Build one normalized inventory rule record."""
    return {
        "rule_id": rule.rule_id,
        "name": format_policy_rule_name(rule),
        "custom_name": rule.custom_name,
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
        "notes": rule.notes,
        "is_paused": rule.is_paused,
        "pause_until": rule.pause_until,
        "pause_remaining_seconds": rule.pause_remaining_seconds,
        "active_time_schedule": rule.active_time_schedule,
        "app_time_period": rule.app_time_period,
        "app_time_quota": rule.app_time_quota,
        "app_time_used": rule.app_time_used,
        "local_port": rule.local_port,
        "protocol": rule.protocol,
        "trust": rule.trust,
        "use_bf": rule.use_bf,
        "upnp": rule.upnp,
        "qdisc": rule.qdisc,
        "rate_limit": rule.rate_limit,
        "traffic_direction": rule.traffic_direction,
        "app_name": rule.app_name,
        "app_uid": rule.app_uid,
        "disturb_level": rule.disturb_level,
        "disturb_method": rule.disturb_method,
        "duration": rule.duration,
        "raw_extras": _build_report_raw_extras(raw_extras),
        "management": management,
        "matching": matching,
        "review_reasons": review_reasons,
    }


def _append_optional_rule_detail(
    lines: list[str],
    *,
    label: str,
    value: object,
) -> None:
    """Append one optional rule detail line when a value is present."""
    if value in (None, "", [], {}):
        return
    lines.append(f"  - {label}: {value}")


def _append_rule_reference_section(
    lines: list[str],
    *,
    title: str,
    rules: object,
    suffix_builder: Callable[[dict[str, object]], str] | None = None,
) -> None:
    """Append a compact rule-reference section to the markdown report."""
    lines.extend(["", f"## {title}", ""])
    if not isinstance(rules, list) or not rules:
        lines.append("- none")
        return

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        line = f"- {rule.get('rule_id')}: {rule.get('name')}"
        if suffix_builder is not None:
            suffix = suffix_builder(rule)
            if suffix:
                line = f"{line} -> {suffix}"
        lines.append(line)


def _management_reasons_summary(rule: dict[str, object]) -> str:
    """Return a readable management-reasons summary for one rule record."""
    management = rule.get("management")
    if not isinstance(management, dict):
        return ""

    reasons = management.get("reasons")
    if not isinstance(reasons, list):
        return ""

    return ", ".join(str(reason) for reason in reasons)


def _review_reasons_summary(rule: dict[str, object]) -> str:
    """Return a readable review-reasons summary for one rule record."""
    review_reasons = rule.get("review_reasons")
    if not isinstance(review_reasons, list):
        return "unknown"

    return ", ".join(str(reason) for reason in review_reasons)


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
    switch_evaluations = build_switch_rule_evaluations(payload, policy_rules)

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
        evaluation = switch_evaluations[rule.rule_id]
        review_reasons = list(evaluation.review_reasons)
        raw_extras = evaluation.raw_extras
        management = evaluation.management
        matching = _build_rule_matching_info(rule)
        raw_rule = raw_rule_index.get(rule.rule_id, {})
        raw_tag_refs = raw_rule.get(_RAW_RULE_TAG_REFS_KEY)
        tag_refs = (
            [tag_ref for tag_ref in raw_tag_refs if isinstance(tag_ref, str)]
            if isinstance(raw_tag_refs, list)
            else []
        )
        rule_record = _build_rule_record(
            rule,
            management=management,
            matching=matching,
            review_reasons=review_reasons,
            raw_extras=raw_extras,
            tag_refs=tag_refs,
        )
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
        if evaluation.is_switch_rule:
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

    _append_rule_reference_section(
        lines,
        title="User-managed Rules",
        rules=user_managed_rules,
    )

    _append_rule_reference_section(
        lines,
        title="System-managed Rules",
        rules=system_managed_rules,
        suffix_builder=_management_reasons_summary,
    )

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
            _append_optional_rule_detail(
                lines,
                label="name",
                value=rule.get("name"),
            )
            _append_optional_rule_detail(
                lines,
                label="custom_name",
                value=rule.get("custom_name"),
            )
            _append_optional_rule_detail(
                lines,
                label="target",
                value=rule.get("target"),
            )
            _append_optional_rule_detail(
                lines,
                label="target_type",
                value=rule.get("target_type"),
            )
            _append_optional_rule_detail(
                lines,
                label="direction",
                value=rule.get("direction"),
            )
            _append_optional_rule_detail(
                lines,
                label="purpose",
                value=rule.get("purpose"),
            )
            _append_optional_rule_detail(
                lines,
                label="scope",
                value=rule.get("scope"),
            )
            _append_optional_rule_detail(
                lines,
                label="applies_to",
                value=rule.get("applies_to"),
            )
            _append_optional_rule_detail(
                lines,
                label="tag_refs",
                value=rule.get("tag_refs"),
            )
            _append_optional_rule_detail(
                lines,
                label="notes",
                value=rule.get("notes"),
            )
            _append_optional_rule_detail(
                lines,
                label="pause_until",
                value=rule.get("pause_until"),
            )
            _append_optional_rule_detail(
                lines,
                label="active_time_schedule",
                value=rule.get("active_time_schedule"),
            )
            _append_optional_rule_detail(
                lines,
                label="app_time_period",
                value=rule.get("app_time_period"),
            )
            _append_optional_rule_detail(
                lines,
                label="app_time_quota",
                value=rule.get("app_time_quota"),
            )
            _append_optional_rule_detail(
                lines,
                label="app_time_used",
                value=rule.get("app_time_used"),
            )
            _append_optional_rule_detail(
                lines,
                label="local_port",
                value=rule.get("local_port"),
            )
            _append_optional_rule_detail(
                lines,
                label="protocol",
                value=rule.get("protocol"),
            )
            _append_optional_rule_detail(
                lines,
                label="trust",
                value=rule.get("trust"),
            )
            _append_optional_rule_detail(
                lines,
                label="use_bf",
                value=rule.get("use_bf"),
            )
            _append_optional_rule_detail(
                lines,
                label="upnp",
                value=rule.get("upnp"),
            )
            _append_optional_rule_detail(
                lines,
                label="qdisc",
                value=rule.get("qdisc"),
            )
            _append_optional_rule_detail(
                lines,
                label="rate_limit",
                value=rule.get("rate_limit"),
            )
            _append_optional_rule_detail(
                lines,
                label="traffic_direction",
                value=rule.get("traffic_direction"),
            )
            _append_optional_rule_detail(
                lines,
                label="app_name",
                value=rule.get("app_name"),
            )
            _append_optional_rule_detail(
                lines,
                label="app_uid",
                value=rule.get("app_uid"),
            )
            _append_optional_rule_detail(
                lines,
                label="disturb_level",
                value=rule.get("disturb_level"),
            )
            _append_optional_rule_detail(
                lines,
                label="disturb_method",
                value=rule.get("disturb_method"),
            )
            _append_optional_rule_detail(
                lines,
                label="duration",
                value=rule.get("duration"),
            )
            management = rule.get("management")
            if isinstance(management, dict):
                _append_optional_rule_detail(
                    lines,
                    label="management_classification",
                    value=management.get("classification"),
                )
                _append_optional_rule_detail(
                    lines,
                    label="management_reasons",
                    value=management.get("reasons"),
                )
            _append_optional_rule_detail(
                lines,
                label="review_reasons",
                value=rule.get("review_reasons"),
            )
            _append_optional_rule_detail(
                lines,
                label="raw_extras",
                value=rule.get("raw_extras"),
            )
    else:
        lines.append("- none")

    _append_rule_reference_section(
        lines,
        title="Rule Switch Candidates",
        rules=rule_switch_candidates,
    )

    _append_rule_reference_section(
        lines,
        title="Rules Needing Review",
        rules=rules_needing_review,
        suffix_builder=_review_reasons_summary,
    )

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
