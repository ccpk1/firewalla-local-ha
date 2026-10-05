"""Vocabulary guard tests for Firewalla Local.

`ARCHITECTURE.md` states the register boundary: machine surfaces use `host`, human
surfaces use `device`. The rule was documented and then violated three times, because
a rule that is only prose is not enforced. This module is the enforcement.

**The allowlist is a work list, not a suppression list.** The test asserts that the
violations found in the tree are *exactly* the entries in `_KNOWN_VIOLATIONS`. That
equality is the point: fixing a violation without removing its entry fails the test,
and adding a violation fails the test, so the list cannot silently drift out of step
with reality in either direction. An entry with no removing phase is a planning
failure, not an approved exemption.

The three checks mirror the three surfaces the register rule governs:

- `target.kind` literals emitted from `services.py`
- the `scope_kind` / `target_type` enums, which are machine values
- `SERVICE_FIELD_*` and `ATTR_*` values, which are keys an automation writes
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path
from typing import Final

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[3] / "custom_components" / "firewalla_local"
)
CONST_PATH: Final = PACKAGE_ROOT / "const.py"
SERVICES_PATH: Final = PACKAGE_ROOT / "services.py"

# Machine-register values a published `target.kind` may take. `network` carries the
# box's `lan`/`vlan`/`vpn`/`wan` distinction on a separate `network_kind` field
# rather than in the kind, because collapsing it would lose real information.
_CANONICAL_TARGET_KINDS: Final = frozenset({"host", "group", "user", "network"})

# The machine word for an endpoint. `device` is the human word and must not appear
# as a machine value.
_HUMAN_WORD_TOKENS: Final = frozenset({"device", "devices"})

# A compound that legitimately contains the human word is exempt when the token
# before it is `host`: `host_device_type` names a host's own classification, not the
# host. Every other use of the word in a machine value means the host itself, which
# is what the rule forbids.
_EXEMPT_PRECEDING_TOKEN: Final = "host"

# Enums that are machine values and therefore must not carry the human word.
#
# Matched on the **published value**, not the constant name, because one published
# name can have more than one constant: `SERVICE_FIELD_SCOPE_KIND` and
# `SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND` both have the value `"scope_kind"`. Keying
# on the constant name is how a guard comes to pass while the value it exists to find
# is present.
_GUARDED_ENUM_FIELD_VALUES: Final = ("scope_kind", "target_type")

# Constants whose *values* are machine keys an automation writes.
_GUARDED_CONSTANT_PREFIXES: Final = ("SERVICE_FIELD_", "ATTR_")

# ---------------------------------------------------------------------------
# The work list. Every entry is a current violation with the phase that removes it.
# Phase 4.4 deletes this mapping outright; if it cannot be deleted, the initiative
# is not finished.
# ---------------------------------------------------------------------------

_TARGET_KIND_VIOLATIONS: Final = {
    "services.py:kind='network_segment'": (
        "Phase 2 — `network_segment` retires for `network`"
    ),
    "services.py:kind=network.kind.value": "Phase 2 — sub-kind moves to `network_kind`",
    "services.py:kind='wan'": "Phase 2 — a WAN is a network with a sub-kind (Q3)",
    "services.py:kind=target_kind": "Phase 2 — emits `wan`/`wan_collection` (Q3)",
    "services.py:kind=view.target.scope_kind": (
        "Phase 2 — emits `device`; becomes `host`"
    ),
    "services.py:kind=target.scope_kind": ("Phase 2 — emits `device`; becomes `host`"),
}

# Phase 3 deletes `scope_kind` for typed pairs (Q4) and gives `target_type` a real
# vocabulary (Q5). Two constants share the value "scope_kind" —
# `SERVICE_FIELD_SCOPE_KIND` and `SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND` — which is
# why the guard matches on the published value rather than the constant name.
_ENUM_VIOLATIONS: Final = {
    "GET_FLOW_REPORT_SCHEMA.SERVICE_FIELD_SCOPE_KIND": (
        "Phase 3 — `scope_kind` deleted for typed pairs (Q4)"
    ),
    "GET_TIME_USAGE_REPORT_SCHEMA.SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND": (
        "Phase 3 — `scope_kind` deleted for typed pairs (Q4)"
    ),
    "CREATE_RULE_SCHEMA.SERVICE_FIELD_SCOPE_KIND": (
        "Phase 3 — `scope_kind` deleted for typed pairs (Q4)"
    ),
    "_ALARM_SCOPE_SCHEMA_FIELDS.SERVICE_FIELD_SCOPE_KIND": (
        "Phase 3 — `scope_kind` deleted for typed pairs (Q4)"
    ),
    "GET_RULES_SCHEMA.SERVICE_FIELD_TARGET_TYPE": (
        "Phase 3 — unvalidated `cv.string`; needs a vocabulary (Q5)"
    ),
}

_CONSTANT_VIOLATIONS: Final = {
    "ATTR_SYSTEM_DEVICES_ONLINE": "Phase 4 — becomes `hosts_online`",
    "ATTR_SYSTEM_DEVICES_OFFLINE": "Phase 4 — becomes `hosts_offline`",
    "ATTR_SYSTEM_DEVICES_TOTAL": "Phase 4 — becomes `hosts_total`",
    "ATTR_SYSTEM_VPN_DEVICES_ONLINE": "Phase 4 — becomes `vpn_hosts_online`",
    "ATTR_SYSTEM_VPN_DEVICES_OFFLINE": "Phase 4 — becomes `vpn_hosts_offline`",
    "ATTR_SYSTEM_VPN_DEVICES_TOTAL": "Phase 4 — becomes `vpn_hosts_total`",
    "ATTR_NETWORK_DEVICE_COUNT": "Phase 4 — becomes `host_count`",
    "ATTR_WATCHED_USER_ASSOCIATED_DEVICES": "Phase 4 — becomes `associated_hosts`",
    "ATTR_WATCHED_USER_ASSOCIATED_DEVICE_COUNT": (
        "Phase 4 — becomes `associated_host_count`"
    ),
    "ATTR_WATCHED_USER_ASSOCIATED_DEVICE_GROUP": (
        "Phase 4 — becomes `associated_host_group`"
    ),
    "ATTR_WATCHED_DEVICE_DEVICE_GROUP": "Phase 4 — becomes `host_group`",
    "ATTR_ALARM_DEVICE_NAME": "Phase 4 — becomes `host_name`",
}

_KNOWN_VIOLATIONS: Final = (
    _TARGET_KIND_VIOLATIONS | _ENUM_VIOLATIONS | _CONSTANT_VIOLATIONS
)


def _module_tree(path: Path) -> ast.Module:
    """Return the parsed module for one integration file."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _string_constants() -> dict[str, str]:
    """Return every module-level name bound to a string literal.

    Enum values are routinely indirected through a constant -- `scope_kind` lists
    `_REPORT_SCOPE_DEVICE` rather than `"device"` -- so a scan that reads only
    literals sees an empty tuple and reports the enum as clean. **That is exactly
    where the violation hid**, so resolving the indirection is not a refinement; it
    is the difference between a guard that works and one that passes while the value
    it exists to find is present.
    """
    constants: dict[str, str] = {}
    for path in (SERVICES_PATH, CONST_PATH):
        for node in ast.walk(_module_tree(path)):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                target = node.target
                value = node.value
            else:
                continue
            if (
                isinstance(target, ast.Name)
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                constants.setdefault(target.id, value.value)
    return constants


def _dump(node: ast.expr) -> str:
    """Return a compact source form for one expression.

    Used to key a violation by the expression that produces it rather than by line
    number, so an unrelated insertion above it does not churn the work list.
    """
    return ast.unparse(node)


def _enclosing_schema_name(tree: ast.Module, target: ast.AST) -> str:
    """Return the name of the assignment a node belongs to, or `<module>`.

    An enum lives inside a schema assignment; the assignment name is what a reader
    needs in order to find it, and it survives unrelated reflow. Both `Assign` and
    `AnnAssign` are handled, because a shared schema fragment such as
    `_ALARM_SCOPE_SCHEMA_FIELDS` is annotated and would otherwise be reported as
    belonging to the module rather than to a named schema.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = node.value
            targets: list[ast.expr] = list(node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            value = node.value
            targets = [node.target]
        else:
            continue
        if not any(inner is target for inner in ast.walk(value)):
            continue
        for assign_target in targets:
            if isinstance(assign_target, ast.Name):
                return assign_target.id
    return "<module>"


def _find_target_kind_violations() -> list[str]:
    """Return every non-canonical `target.kind` emitted from `services.py`."""
    tree = _module_tree(SERVICES_PATH)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "FirewallaReportTarget":
            continue
        for keyword in node.keywords:
            if keyword.arg != "kind":
                continue
            value = keyword.value
            is_canonical = (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.value in _CANONICAL_TARGET_KINDS
            )
            if not is_canonical:
                found.add(f"services.py:kind={_dump(value)}")
    return sorted(found)


def _declared_field_name(key: ast.expr) -> str | None:
    """Return the `SERVICE_FIELD_*` name one schema dict key declares.

    A key is `vol.Optional(SERVICE_FIELD_X)` / `vol.Required(SERVICE_FIELD_X)`, so
    the field name is the argument inside the wrapper.
    """
    if isinstance(key, ast.Call) and key.args:
        argument = key.args[0]
        if isinstance(argument, ast.Name):
            return argument.id
    return None


def _enum_strings(node: ast.expr, constants: Mapping[str, str]) -> list[str] | None:
    """Return the string values of a `vol.In(...)`, or `None` if it is not one.

    An element that is neither a literal nor a resolvable module constant returns
    `None` for the whole enum rather than being skipped, because a partially-read
    enum would be reported as clean on the strength of the elements it could read.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    if name != "In" or not node.args:
        return None
    values = node.args[0]
    if not isinstance(values, (ast.Tuple, ast.List)):
        return None
    resolved: list[str] = []
    for element in values.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            resolved.append(element.value)
        elif isinstance(element, ast.Name) and element.id in constants:
            resolved.append(constants[element.id])
        else:
            return None
    return resolved


def _uses_human_word(value: str) -> bool:
    """Return whether a machine value names a host with the human word.

    Tokenised rather than substring-matched, because `host_device_type` contains the
    human word while meaning a host's own classification. The exemption is narrow and
    positional: the token immediately before must be `host`.
    """
    tokens = value.split("_")
    for index, token in enumerate(tokens):
        if token not in _HUMAN_WORD_TOKENS:
            continue
        if index > 0 and tokens[index - 1] == _EXEMPT_PRECEDING_TOKEN:
            continue
        return True
    return False


def _find_enum_violations() -> list[str]:
    """Return every guarded machine field that is unvalidated or uses the human word.

    Two findings share this surface and are reported the same way: a guarded enum
    containing `device`, and a guarded field declared as a bare string where the same
    field name is validated elsewhere. The second is the worse of the two — a typo
    silently filters to nothing instead of failing — so one guard covers both.

    **This does not check the `target_type` name collision.** `mute_alarm` carries a
    different vocabulary under the same field name, which is a collision rather than
    a register violation: neither vocabulary contains the human word. That finding is
    tracked in the inventory note and resolved in Phase 3.2, because detecting "one
    name, two vocabularies" mechanically needs the semantics of each enum, not its
    spelling.
    """
    tree = _module_tree(SERVICES_PATH)
    constants = _string_constants()
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            field_name = _declared_field_name(key) if key is not None else None
            if field_name is None:
                continue
            if constants.get(field_name) not in _GUARDED_ENUM_FIELD_VALUES:
                continue
            schema = _enclosing_schema_name(tree, node)
            entry = f"{schema}.{field_name}"
            values = _enum_strings(value, constants)
            if values is None or any(_uses_human_word(item) for item in values):
                found.add(entry)
    return sorted(found)


def _find_constant_violations() -> list[str]:
    """Return every guarded constant whose value uses the human word for a host."""
    tree = _module_tree(CONST_PATH)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        name = node.target.id
        if not name.startswith(_GUARDED_CONSTANT_PREFIXES):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(
            node.value.value, str
        ):
            continue
        if _uses_human_word(node.value.value):
            found.add(name)
    return sorted(found)


def _found_violations() -> dict[str, str]:
    """Return every current violation, keyed as the work list is.

    The value is deliberately not a reason — reasons live in the work list, which is
    what the equality assertion compares against.
    """
    return {
        **dict.fromkeys(_find_target_kind_violations(), ""),
        **dict.fromkeys(_find_enum_violations(), ""),
        **dict.fromkeys(_find_constant_violations(), ""),
    }


def test_violations_match_the_work_list_exactly() -> None:
    """Test the register boundary holds wherever it is not a recorded exception.

    The equality is the guard. A violation that is added fails here; a violation that
    is fixed without removing its entry also fails here, so the work list cannot
    drift out of step with the tree in either direction.
    """
    found = set(_found_violations())
    known = set(_KNOWN_VIOLATIONS)

    added = sorted(found - known)
    assert added == [], (
        "new violations of the register boundary; either fix them or add them to "
        f"the work list with the phase that removes them: {added}"
    )

    resolved = sorted(known - found)
    assert resolved == [], (
        "these are fixed but still listed as violations; remove their work-list "
        f"entries so the list stays a work list: {resolved}"
    )


def test_every_work_list_entry_names_the_phase_that_removes_it() -> None:
    """Test no entry is an exemption without an owner or a reason.

    An entry with no phase is an exemption, which is the thing this list must never
    become. The check is on the value rather than the key because the value is where
    the owner and the reason live.
    """
    unowned = sorted(
        key for key, reason in _KNOWN_VIOLATIONS.items() if "Phase " not in reason
    )
    assert unowned == [], f"work-list entries with no owning phase: {unowned}"


def test_the_canonical_set_matches_the_documented_one() -> None:
    """Test the guard's canonical set is the set the architecture states.

    A guard whose canonical set drifts from the document would enforce a rule nobody
    agreed to, and the drift would be invisible because both would still pass their
    own check.
    """
    architecture = (
        Path(__file__).resolve().parents[3] / "docs" / "ARCHITECTURE.md"
    ).read_text(encoding="utf-8")

    for kind in _CANONICAL_TARGET_KINDS:
        assert f"`{kind}`" in architecture, (
            f"`{kind}` is enforced as a canonical target kind but is not stated in "
            "ARCHITECTURE.md; the document and the guard must agree"
        )

    # The human word must be documented as belonging to the other register, or the
    # rule reads as "never say device" rather than "say device in prose".
    assert "Register boundary" in architecture
    assert "human" in architecture.lower()
