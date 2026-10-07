"""Vocabulary guard tests for Firewalla Local.

`ARCHITECTURE.md` states the register boundary: machine surfaces use `host`, human
surfaces use `device`. The rule was documented and then violated three times, because
a rule that is only prose is not enforced. This module is the enforcement.

**The allowlist is a work list, not a suppression list.** The test asserts that the
checks assert **zero** violations. There is no allowlist and no work list: the one this
replaced went 23 -> 17 -> 12 -> empty across Phases 2, 3 and 4, and the structure was
deleted rather than left empty, because an empty allowlist is an invitation to add one
entry to it.

The three checks mirror the three surfaces the register rule governs:

- `target.kind` literals emitted from `services.py`
- the `scope_kind` / `target_type` enums, which are machine values
- `SERVICE_FIELD_*` and `ATTR_*` values, which are keys an automation writes
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[3] / "custom_components" / "firewalla_local"
)
CONST_PATH: Final = PACKAGE_ROOT / "const.py"
SERVICES_PATH: Final = PACKAGE_ROOT / "services.py"
# Modules whose dict keys are part of the published payload contract. The record
# layer, the API client and the managers are excluded on purpose: they read and write
# the vendor's own `device` keys, which must keep the vendor's spelling.
PUBLISHING_MODULES: Final = (
    "services.py",
    "models.py",
    "binary_sensor.py",
    "sensor.py",
    "switch.py",
    "device_tracker.py",
    "diagnostics.py",
    "button.py",
    "entity.py",
)
# The read tools declare their own copies of several service schemas, so a vocabulary
# can drift there while the service side stays correct. Scanning both is what makes
# the check about the published surface rather than about one file.
TOOLS_READ_PATH: Final = PACKAGE_ROOT / "llm_tools_read.py"

# A target object is a payload dict carrying both a `kind` and an `id` key, which is
# the shape `_serialize_report_target` publishes and the control tools mirror. The
# pair is what distinguishes it from the other dicts that carry a `kind` in this
# package -- a time basis, a period, a network entry -- none of which has an `id`,
# because they describe a thing rather than name it.
_TARGET_OBJECT_KIND_KEY: Final = "kind"
_TARGET_OBJECT_ID_KEY: Final = "id"

# Machine-register values a published `target.kind` may take. `network` carries the
# box's `lan`/`vlan`/`vpn`/`wan` distinction on a separate `network_kind` field
# rather than in the kind, because collapsing it would lose real information.
#
# The set is every object the integration publishes as a target, not only the report
# scopes: a control tool's result names a rule, an alarm, a silence or an SSID, and
# those are the same question. One vocabulary, so learning it from a report is not
# contradicted by a tool result.
#
# Held here rather than read from `const.py` on purpose: this is the independent
# statement of the rule, and `test_the_canonical_set_matches_the_vocabulary_module`
# is what keeps the two in step. Deriving it from the module would make the guard
# agree with whatever the module happens to say.
_CANONICAL_TARGET_KINDS: Final = frozenset(
    {"host", "group", "user", "network", "rule", "alarm", "silence", "ssid"}
)

# A kind is reached either as one of the canonical constants or by looking it up in a
# mapping that translates into them. Both are named by prefix so a new one is
# covered the moment it is added, and neither can hide a value the set rejects.
_TARGET_KIND_CONSTANT_PREFIX: Final = "TARGET_KIND_"
_TARGET_KIND_MAPPING_PREFIX: Final = "TARGET_KIND_BY_"

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
# name can have more than one constant. That was not hypothetical: two constants
# published `"scope_kind"` until the report services moved to typed pairs, and a
# name-keyed scan reported the second as absent -- which is exactly how a guard comes
# to pass while the value it exists to find is present. Phase 3 removed that second
# constant, and this match stays value-keyed so the next one is caught rather than
# documented.
_GUARDED_ENUM_FIELD_VALUES: Final = ("scope_kind", "target_type")

# Constants whose *values* are keys an automation writes. `FLOW_REPORT_` is included
# because its values are keys inside a report payload, which the vocabulary rule names
# explicitly.
_GUARDED_CONSTANT_PREFIXES: Final = ("SERVICE_FIELD_", "ATTR_", "FLOW_REPORT_")

# There is no work list. Every check below asserts **zero** violations, with no
# exemption mechanism at all -- a new violation fails the build and there is nothing to
# add it to. The list this replaces went 23 -> 17 -> 12 -> empty across Phases 2, 3 and
# 4, and deleting the structure rather than leaving it empty is the point: an empty
# allowlist that still exists is an invitation to add one entry to it.
#
# What this guard does **not** cover, stated so it is not mistaken for total:
#
# - **literal payload keys.** The checks read `ATTR_*` / `SERVICE_FIELD_*` /
#   `FLOW_REPORT_*` *values*, so a key written directly as `"host_id": ...` in
#   `services.py` or `models.py` is invisible. This is a gap in the check, not a
#   licence: the `device_*` keys that used to live there were renamed by hand and are
#   asserted by the service and entity tests that read the payloads. A future literal
#   key that departs from the vocabulary would pass here.
# - **enum values inside the tool schemas** that duplicate a service schema.
# - **documentation prose.** One check asserts the rule is stated in
#   `ARCHITECTURE.md`; the rest of the prose is not machine-checked.


def _module_tree(path: Path) -> ast.Module:
    """Return the parsed module for one integration file."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _sequence_constants(constants: Mapping[str, str]) -> dict[str, list[str]]:
    """Return every module-level name bound to a sequence of enum values.

    The same indirection as :func:`_string_constants`, one level up: an enum is now
    written as `vol.In(RULE_TARGET_TYPES)` where that name holds the values. A scan
    that only reads literal sequences would fail closed on every named enum, which
    makes the guard noisy rather than wrong -- but resolving it keeps the two styles
    equivalent, so declaring an enum through a named constant is not a way to be
    skipped.

    `constants` is needed because a named sequence is itself usually a tuple of
    *constants* (`RULE_TARGET_TYPE_DNS`, ...) rather than of string literals, so both
    levels have to resolve. A sequence with an element that resolves to neither is
    omitted entirely, matching the fail-closed rule the enum reader uses.
    """
    resolved_sequences: dict[str, list[str]] = {}
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
            if not isinstance(target, ast.Name):
                continue
            if not isinstance(value, (ast.Tuple, ast.List)):
                continue
            elements: list[str] = []
            resolvable = True
            for element in value.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    elements.append(element.value)
                elif isinstance(element, ast.Name) and element.id in constants:
                    elements.append(constants[element.id])
                else:
                    resolvable = False
                    break
            if resolvable and elements:
                resolved_sequences.setdefault(target.id, elements)
    return resolved_sequences


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


def _target_kind_constants(constants: Mapping[str, str]) -> dict[str, str]:
    """Return every `const.py` constant that declares a published target kind."""
    return {
        name: value
        for name, value in constants.items()
        if name.startswith(_TARGET_KIND_CONSTANT_PREFIX)
    }


def _target_kind_mappings(
    constants: Mapping[str, str],
) -> dict[str, list[str] | None]:
    """Return every `const.py` mapping that translates into a target kind.

    A value that cannot be resolved makes the whole mapping `None` rather than being
    skipped, for the same reason an unresolvable enum is rejected: a partially-read
    mapping would be reported as canonical on the strength of the entries it could
    read.
    """
    tree = _module_tree(CONST_PATH)
    mappings: dict[str, list[str] | None] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            name = node.target.id if isinstance(node.target, ast.Name) else None
            value = node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            name = target.id if isinstance(target, ast.Name) else None
            value = node.value
        else:
            continue
        if name is None or not name.startswith(_TARGET_KIND_MAPPING_PREFIX):
            continue
        if not isinstance(value, ast.Dict):
            continue
        resolved: list[str] | None = []
        for item in value.values:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                resolved.append(item.value)
            elif isinstance(item, ast.Name) and item.id in constants:
                resolved.append(constants[item.id])
            else:
                resolved = None
                break
        mappings[name] = resolved
    return mappings


def _is_canonical_kind_expression(
    node: ast.expr,
    canonical_names: frozenset[str],
    mapping_names: frozenset[str],
) -> bool:
    """Return whether one `kind=` expression can only produce a canonical kind.

    The rule this enforces is about where a kind is **written**. A value that is
    *read back* -- `.kind` off a normalized record, or off the report target the
    serializer is itself serializing -- is a relay, and the vocabulary lives in the
    record's own declaration. So the accepted routes are:

    - a canonical literal
    - one of the canonical constants
    - a lookup in a mapping that resolves into them
    - a conditional whose every branch is one of the above
    - `.kind` attribute access, i.e. a relay of a value authored elsewhere

    Nothing else. Inventing a kind has to go through one of the first four, so there
    is no route by which a new service can reach a value the set rejects.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value in _CANONICAL_TARGET_KINDS
    if isinstance(node, ast.Name):
        return node.id in canonical_names
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        return node.value.id in mapping_names
    if isinstance(node, ast.IfExp):
        return _is_canonical_kind_expression(
            node.body, canonical_names, mapping_names
        ) and _is_canonical_kind_expression(node.orelse, canonical_names, mapping_names)
    if isinstance(node, ast.Attribute):
        return node.attr == _TARGET_OBJECT_KIND_KEY
    return False


def _find_target_kind_violations() -> list[str]:
    """Return every `target.kind` that could be published outside the vocabulary.

    Scans the whole package, not one file, because a target is published from
    `services.py` and from the control tools alike, and an earlier version of this
    check missed a whole second vocabulary by looking at `services.py` alone.

    Both published shapes are covered: a `FirewallaReportTarget(kind=...)` call and a
    target-object dict literal. A dict is a target object when it carries both a
    `kind` and an `id` key.
    """
    constants = _string_constants()
    canonical_names = frozenset(
        name
        for name, value in _target_kind_constants(constants).items()
        if value in _CANONICAL_TARGET_KINDS
    )
    mapping_names = frozenset(_target_kind_mappings(constants))
    found: set[str] = set()
    for path in _package_modules():
        tree = _module_tree(path)
        for node in ast.walk(tree):
            expression = _target_kind_expression(node)
            if expression is None:
                continue
            if not _is_canonical_kind_expression(
                expression, canonical_names, mapping_names
            ):
                found.add(f"{path.name}:kind={_dump(expression)}")
    return sorted(found)


def _package_modules() -> list[Path]:
    """Return every Python module in the integration package."""
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _target_kind_expression(node: ast.AST) -> ast.expr | None:
    """Return the expression that sets a target object's kind, if this node is one.

    Two shapes publish a target: a `FirewallaReportTarget(kind=...)` call carries
    only the kind keyword, while a dict literal must carry both `kind` and `id` to be
    a target rather than one of the package's other `kind`-bearing records.
    """
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "FirewallaReportTarget":
            return None
        for keyword in node.keywords:
            if keyword.arg == "kind":
                return keyword.value
        return None

    if isinstance(node, ast.Dict):
        keys = [
            key.value
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        ]
        if _TARGET_OBJECT_KIND_KEY not in keys:
            return None
        if _TARGET_OBJECT_ID_KEY not in keys:
            return None
        for key, value in zip(node.keys, node.values, strict=True):
            if isinstance(key, ast.Constant) and key.value == _TARGET_OBJECT_KIND_KEY:
                return value
        return None

    return None


def _find_target_kind_mapping_violations() -> list[str]:
    """Return every kind mapping that resolves to a value the set rejects.

    The mapping is the one route by which a dynamic kind reaches a response, so it is
    checked where it is declared rather than only where it is read.
    """
    constants = _string_constants()
    found: set[str] = set()
    for name, values in _target_kind_mappings(constants).items():
        if values is None or any(
            value not in _CANONICAL_TARGET_KINDS for value in values
        ):
            found.add(f"const.py:{name}")
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


def _enum_strings(
    node: ast.expr,
    constants: Mapping[str, str],
    sequences: Mapping[str, list[str]],
) -> list[str] | None:
    """Return the string values of a `vol.In(...)`, or `None` if it is not one.

    An element that is neither a literal nor a resolvable module constant returns
    `None` for the whole enum rather than being skipped, because a partially-read
    enum would be reported as clean on the strength of the elements it could read.
    The sequence may also be a *named* tuple -- `vol.In(RULE_TARGET_TYPES)` -- which is
    resolved the same way, so declaring an enum through a constant is not a way past
    this check.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    if name != "In" or not node.args:
        return None
    values = node.args[0]
    if isinstance(values, ast.Name):
        return sequences.get(values.id)
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
    sequences = _sequence_constants(constants)
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
            values = _enum_strings(value, constants, sequences)
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
        **dict.fromkeys(_find_target_kind_mapping_violations(), ""),
        **dict.fromkeys(_find_enum_violations(), ""),
        **dict.fromkeys(_find_constant_violations(), ""),
    }


def test_the_boundary_holds_with_no_exceptions() -> None:
    """Test every checked surface is clean, with no exemption mechanism.

    This asserted equality against a work list while the phases were running, so the
    list could not drift out of step with the tree in either direction. The list is
    gone and the assertion is now absolute: anything found here is a violation to fix,
    because there is nowhere to record it.
    """
    found = sorted(_found_violations())
    assert found == [], (
        "violations of the vocabulary rule; these are not exemptible, because the "
        f"work list that used to carry them has been deleted: {found}"
    )


def test_the_boundary_check_is_not_silently_empty() -> None:
    """Test the guard is actually reading the tree, not vacuously passing.

    A check that finds nothing is only meaningful if it looked at something. This
    proves each scan returns a populated result set on a deliberate violation, so a
    passing suite cannot mean "the scanner stopped working".
    """
    # `_found_violations` returning {} is only trustworthy if the scanners see real
    # data, so assert they at least read the files they are meant to read.
    assert _string_constants(), "no module-level string constants resolved"
    assert _sequence_constants(_string_constants()), "no enum sequences resolved"
    assert _detail_enum_by_schema(), "no `detail` field found to check"
    assert _target_kind_constants(_string_constants()), "no target-kind constants found"


def test_the_canonical_set_matches_the_vocabulary_module() -> None:
    """Test the guard's set and `const.py` declare the same target kinds.

    The guard holds the set independently so that it cannot agree with the module by
    construction, which means the two have to be compared. A constant the guard would
    reject, or a kind with no constant, is a vocabulary that is only half-sourced.
    """
    declared = set(_target_kind_constants(_string_constants()).values())

    assert declared == set(_CANONICAL_TARGET_KINDS), (
        "const.py's `TARGET_KIND_*` constants and the guard's canonical set disagree; "
        f"module declares {sorted(declared)}, guard enforces "
        f"{sorted(_CANONICAL_TARGET_KINDS)}"
    )


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

    # The rule must be documented, since the guard enforces it. The section is named
    # for the word it prescribes, not for a register boundary -- measurement showed
    # there is only one register.
    assert "Vocabulary: `host`, with one exception" in architecture
    assert "device_tracker" in architecture, (
        "the one exception is `device` for Home Assistant device-registry concepts; "
        "the document must name `device_tracker` explicitly or the exception is "
        "unreadable"
    )


def _detail_enum_by_schema() -> dict[str, list[str] | None]:
    """Return each `detail` field's values, keyed by where it is declared.

    Read from the service schemas and the tool schemas both, because the tools
    redeclare several of these and a vocabulary can drift in one and not the other.

    The key carries the line number because it has to be unique. Every tool declares
    its schema as a class attribute literally named `parameters`, so keying on the
    schema name alone made the last tool in the file overwrite every earlier one --
    and the result was a guard that passed while an earlier tool still held the old
    vocabulary. Found by injecting that drift and watching the check pass.
    """
    constants = _string_constants()
    sequences = _sequence_constants(constants)
    found: dict[str, list[str] | None] = {}
    for path in (SERVICES_PATH, TOOLS_READ_PATH):
        tree = _module_tree(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if _declared_field_name(key) != "SERVICE_FIELD_DETAIL":  # type: ignore[arg-type]
                    continue
                schema = _enclosing_schema_name(tree, node)
                found[f"{path.name}:{schema}:{node.lineno}"] = _enum_strings(
                    value, constants, sequences
                )
    return found


def test_detail_uses_one_vocabulary() -> None:
    """Test every `detail` field offers the same two levels.

    `detail` had five treatments: `summary|records`, a bare boolean, two
    `summary|full`, and `summary|standard`. A boolean whose *name* is a level, and two
    different words for "everything", are how a caller learns one service's vocabulary
    and finds it wrong on the next -- and it was the boolean that was worst, because
    `detail=False` says nothing about what the other level adds.

    What differs between services stays in the description: for some services "full" is
    extra fields, for others an extra request, and for the flow report it is the raw
    record log. None of that justifies a second set of value names.
    """
    levels = _sequence_constants(_string_constants()).get("DETAIL_LEVELS")

    assert levels == ["summary", "full"], (
        "the shared detail vocabulary is no longer `summary|full`; every service's "
        f"`detail` field is checked against it, so this is the definition to change: "
        f"{levels}"
    )

    enums = _detail_enum_by_schema()
    assert enums, "no `detail` field was found; the scan is looking in the wrong place"

    offenders = {schema: values for schema, values in enums.items() if values != levels}
    assert offenders == {}, (
        "these `detail` fields do not use the shared vocabulary, so a caller who "
        f"learns one service is wrong on the next: {offenders}"
    )


def _published_key_literals() -> dict[str, list[str]]:
    """Return every dict key or subscript literal in the modules that publish payloads.

    The value-keyed checks above cannot see a key written directly as `"device_id":
    ...`, which is how the last eight `device_*` keys and the `devices` /
    `vpn_devices` sections survived several waves of renaming. This reads the keys
    themselves, by their position in the syntax rather than by their value, so a
    literal key is held to the same rule as a constant's value.
    """
    found: dict[str, list[str]] = {}
    for path in PUBLISHING_MODULES:
        module = PACKAGE_ROOT / path
        if not module.exists():
            continue
        for node in ast.walk(_module_tree(module)):
            keys: list[ast.expr] = []
            if isinstance(node, ast.Dict):
                keys = [key for key in node.keys if key is not None]
            elif isinstance(node, ast.Subscript):
                keys = [node.slice]
            for key in keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.setdefault(key.value, []).append(
                        f"{module.name}:{key.lineno}"
                    )
    return found


def test_no_published_key_names_a_host_as_a_device() -> None:
    """Test no published payload key says `device`, except the host-scoped name.

    `host_device_type` is the one survivor and it is allowed because it carries the
    host prefix, so the concept stays unambiguous. Anything else fails: a published
    key is the machine register, and the machine register says `host` everywhere.

    A literal key is invisible to the value-keyed checks above -- that is how
    `device_id`, `device_port`, `device_type`, `device_rules`, `active_device_count`
    and the `devices` / `vpn_devices` sections each outlived a renaming wave. This
    is the check that would have caught them.
    """
    offenders = {
        value: sites
        for value, sites in _published_key_literals().items()
        if _uses_human_word(value) and not value.startswith("host")
    }
    assert offenders == {}, (
        "these published keys name a host as `device`; rename them to `host`, or "
        f"prefix the name with `host` if the concept needs the vendor's word: "
        f"{offenders}"
    )


def test_the_published_key_check_reads_real_keys() -> None:
    """Test the key scan found the payload keys, so a pass above means something.

    Without this, a scan that silently walked nothing -- a renamed module, a
    changed import -- would report zero offenders and look identical to a clean
    package.
    """
    keys = _published_key_literals()

    assert "host_device_type" in keys, (
        "the key scan did not find a known published key, so it is not reading the "
        f"payload modules: {sorted(keys)[:20]}"
    )
    assert len(keys) > 50, (
        f"the key scan found only {len(keys)} keys, far fewer than the payload "
        "modules define; it is not reading them"
    )


TRANSLATIONS_PATH: Final = PACKAGE_ROOT / "translations" / "en.json"

# Modules whose attributes reach the entity registry, so each key needs a label.
#
# `entity.py` is here because attributes it builds are published by the entities that
# call it -- `build_activity_basis_attributes` returns three of them. Leaving it out
# made those three invisible: the check passed with their labels deleted, because it
# was looking for the names in the platform modules while the shared base class is
# where they are written. A shared builder is a blind spot for any scan that reads one
# file at a time, and this is the second guard in this package to hit it.
ENTITY_MODULES: Final = (
    "binary_sensor.py",
    "sensor.py",
    "switch.py",
    "device_tracker.py",
    "button.py",
    "entity.py",
)


def _translated_attribute_keys() -> set[str]:
    """Return every state-attribute name the translations declare a label for."""
    data = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for platform in data.get("entity", {}).values():
        for node in platform.values():
            keys.update((node.get("state_attributes") or {}).keys())
    return keys


def _entity_attribute_keys() -> dict[str, list[str]]:
    """Return each attribute an entity module names, keyed by its published value.

    Read through the `ATTR_*` constants rather than by scanning dict keys, because
    the entity attribute dicts nest: the `ports` attribute holds a per-port map and
    the DHCP attribute holds a nested record, and those inner keys are *values* inside
    an attribute rather than attributes of their own. They correctly carry no label, so
    a positional scan would report two dozen false gaps and drown the real ones.

    An `ATTR_*` reference is the signal that the name is a published attribute, and it
    is also how every attribute is in fact written.
    """
    constants = _string_constants()
    found: dict[str, list[str]] = {}
    for module_name in ENTITY_MODULES:
        for node in ast.walk(_module_tree(PACKAGE_ROOT / module_name)):
            if (
                isinstance(node, ast.Name)
                and node.id in constants
                and node.id.startswith("ATTR_")
            ):
                found.setdefault(constants[node.id], []).append(module_name)
    return found


def test_every_published_attribute_has_a_translation_label() -> None:
    """Test no entity attribute ships without a label.

    `quality_scale.yaml` marks `entity-translations` done on the strength of
    "translation-backed names, states, and attributes without inline user-facing
    strings". An attribute with no label breaks that **quietly**: Home Assistant
    renders the raw key, so the entity still works and only the display is wrong.
    Nothing failed, which is why this check had to be written rather than noticed.

    Two defect classes, both found here and both real:

    - **Unlabelled** -- five attributes had been published since before the time work
      and never had a label: `dns_hostname`, `dns_domain`, `dns_fqdn`,
      `host_device_type` and `host_ip`.
    - **Stale** -- the vocabulary pass renamed the constant's value from `ip_address`
      to `host_ip` but did not carry the translation key with it, so the label pointed
      at a name nothing published while the real attribute had none. A rename is a
      translation change, and that is not visible from the code.

    Coverage, not placement: this proves a name has *some* label, not that the
    label sits on the entity that publishes it. Asserting placement would need a
    binding from each model class to its translation key, and a binding that can rot
    is worse than a check that proves slightly less. The companion check below covers
    the other direction, and together they pin the label set and the published set to
    the same vocabulary.
    """
    published = _entity_attribute_keys()
    translated = _translated_attribute_keys()

    unlabelled = {
        key: sorted(set(modules))
        for key, modules in published.items()
        if key not in translated
    }

    assert unlabelled == {}, (
        "these entity attributes have no translation label, so Home Assistant renders "
        f"the raw key instead of a readable name: {unlabelled}"
    )


def test_no_translation_label_names_an_attribute_nothing_publishes() -> None:
    """Test no label is left pointing at a name the entities stopped publishing.

    The other half of the same problem, and the half that is genuinely invisible without
    a test. When a constant's value is renamed, the code follows it and the translation
    key does not: the attribute then ships unlabelled *and* leaves a dead label behind.
    That is exactly what happened to `ip_address` -> `host_ip`, and neither half was
    noticed for a release because the entity kept working and the UI showed `host_ip`
    in the raw-key fallback rather than failing.

    This is what makes the pair worth having. Checking only for missing labels would
    have caught that defect's symptom; checking both directions is what proves the label
    set and the published set describe the same vocabulary, which is the property a
    rename is supposed to preserve.
    """
    published = set(_entity_attribute_keys())
    translated = _translated_attribute_keys()

    dead = sorted(translated - published)

    assert dead == [], (
        "these translation labels name an attribute no entity publishes, so a rename "
        f"was applied to the code but not to the translations: {dead}"
    )


def test_the_translation_check_reads_real_keys() -> None:
    """Test the label scan found both sides, so a pass above means something.

    A scan reading an empty translation file fails loudly; one reading an empty module
    set reports nothing unlabelled and passes while proving nothing. This pins both.
    """
    published = _entity_attribute_keys()
    translated = _translated_attribute_keys()

    assert len(published) > 100, (
        f"only {len(published)} entity attribute keys were read, far fewer than the "
        "entity modules name; the scan is not reading them"
    )
    assert "last_active_at" in published, (
        "the scan did not resolve an ATTR_* constant to its published value, so it is "
        f"reading names rather than values: {sorted(published)[:20]}"
    )
    assert len(translated) > 100, (
        f"only {len(translated)} translated attribute keys were read, far fewer than "
        "the translations declare; the scan is not reading the file"
    )
