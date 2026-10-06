"""Time and derived-state contract guards for Firewalla Local.

Two defects were found on the live box, and they are the same defect: **a published
value the reader cannot reproduce from the payload.**

- **An unreadable instant.** `list_hosts` published `last_active: 1791258075.36`.
  There is no date, so an agent has nothing to show a user and ends up comparing
  floats by eye.
- **A derived value whose inputs are unpublished.** `online` is not a fact about a
  host; it is `reference - last_active <= window`, and none of the three inputs was
  published. That produced a live contradiction: `get_system_overview` reported
  `vpn_hosts: {total: 5, online: 1}` while `list_hosts` reported all five peers
  offline, seconds apart, from the same box.

The rule these guards enforce, stated once:

    Every published value is either a raw fact, or reproducible from other
    published fields.

**Why this module exists separately from `test_vocabulary.py`.** That guard checks
*names* -- is this called `host` or `device`. Every check there is a value or key
comparison, so it cannot see a correctly-named field holding a wrong number, and it
has no way to notice that three inputs drive one output. The `vpn_hosts` defect
survived two prior normalization passes because it is a *semantic* problem sitting in
a *lexical* guard's blind spot. This module asserts facts instead.

**Both guards are required to fail before the change that satisfies them.** A guard
that has never failed is not evidence -- the repository has already had a guard pass
while the value it existed to find was present.
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Final
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_services import _runtime_payload, _snapshot
from test_vocabulary import (
    PACKAGE_ROOT,
    PUBLISHING_MODULES,
    _module_tree,
    _string_constants,
)

from custom_components.firewalla_local.const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_SYMMETRIC_KEY,
    DOMAIN,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_GET_HOSTS,
    SERVICE_GET_RUNTIME_INVENTORY,
    SERVICE_GET_SYSTEM_OVERVIEW,
)

# Suffixes that mark a published key as holding an **instant**, and therefore
# requiring an epoch twin so a caller can do arithmetic on it. `_at` is a point in
# time; `_until` is a deadline, which is also a point.
#
# `_start` and `_end` are deliberately absent: a schedule window boundary reads
# naturally as-is, and `schedule_next_start_at` is worse without buying anything
# (plan Q3).
_INSTANT_SUFFIXES: Final = ("_at", "_until")

# The epoch twin's suffix. `_timestamp`, never `_epoch` or `_seconds` -- a duration in
# seconds and an instant in seconds are different quantities, and `uptime_seconds`
# beside `uptime` is the duration pair the standard cites.
_TWIN_SUFFIX: Final = "_timestamp"

# Modules whose published keys are part of the contract. The read tools declare their
# own copies of several service schemas, so a vocabulary can drift there while the
# service side stays correct.
_CONTRACT_MODULES: Final = (*PUBLISHING_MODULES, "llm_tools_read.py")

# Fields a caller needs in order to reproduce a published windowed boolean. Until
# these exist the boolean is unexplainable from the payload, which is the Class B
# defect this module exists to catch.
#
# `activity_reference_at` rather than the `as_of` this started as, because `as_of`
# takes none of the closed suffix set and would have been the first published
# temporal field to opt out of the convention it introduces. `measured_at` was
# rejected for being actively misleading: it reads as "when the snapshot was
# taken", and a caller computing `now - last_active` from it gets a different
# answer than the published `online`, which is the exact defect this guards.
_BASIS_REFERENCE_KEYS: Final = (
    "activity_reference_at",
    "activity_reference_at_timestamp",
)
_BASIS_WINDOW_KEYS: Final = ("online_window_seconds",)

# The epoch form of a host's last activity. Accepts either name so the guard holds
# through the planned `last_active` -> `last_active_at` + `last_active_timestamp`
# rename rather than only before or only after it.
_HOST_ACTIVITY_KEYS: Final = ("last_active_timestamp", "last_active")

# Bare key names that mark an instant without saying what it is an instant *of*. They
# are only unambiguous when the parent key supplies the concept, which is why they are
# permitted inside a nested response and wrong as a flat entity attribute.
#
# The suffix check in this module cannot see them: it tests `endswith("_at")`, and
# `"at"` does not end in `"_at"`. That is how the one instant shape the standard does
# not permit escaped a guard built to find exactly it.
_BARE_INSTANT_KEYS: Final = ("at", "timestamp")

# Modules whose published keys reach an entity attribute, directly or through a shared
# builder. `models.py` is here deliberately: `build_rule_hit_attributes` is called by
# the rule service payload *and* by the rule switch, so a bare key defined there is a
# bare key on an entity however the service half reads it.
_ENTITY_PUBLISHING_MODULES: Final = (
    "binary_sensor.py",
    "sensor.py",
    "switch.py",
    "device_tracker.py",
    "button.py",
    "diagnostics.py",
    "entity.py",
    "models.py",
)


def _published_time_keys(module_name: str, constants: dict[str, str]) -> set[str]:
    """Return every time-ish published key one module contributes.

    Three shapes have to be read, and reading fewer is how a check like this passes
    while the thing it looks for is present:

    - a **literal** key in a dict, `"last_active": ...`
    - an **`ATTR_*` name** as a dict key, `ATTR_WATCHED_DEVICE_LAST_ACTIVE: ...`
    - a **subscript assignment**, `attributes[ATTR_RULE_PAUSE_UNTIL] = ...`, which is
      how most entity attributes are added after the initial dict is built

    The second and third are the whole entity surface, and they resolve to a string
    only through `const.py`. A scan that read dict literals alone saw ten keys in
    `switch.py` and missed every rule attribute.
    """
    keys: set[str] = set()

    def _record(node: ast.expr) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            keys.add(node.value)
        elif isinstance(node, ast.Name) and node.id in constants:
            keys.add(constants[node.id])

    for node in ast.walk(_module_tree(PACKAGE_ROOT / module_name)):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None:
                    _record(key)
        elif isinstance(node, ast.Subscript):
            _record(node.slice)
    return keys


def _find_unpaired_instants() -> dict[str, list[str]]:
    """Return each module's instants that publish no epoch twin.

    Per module, not globally. The same concept is published on several surfaces, and
    a union would hide the defect that matters: `fired_at` has an epoch twin on the
    *service* and none on the *entity*, so one name means an ISO string in one place
    and a raw float in another. Checking per module is what keeps the two apart.
    """
    constants = _string_constants()
    violations: dict[str, list[str]] = {}
    for module_name in _CONTRACT_MODULES:
        keys = _published_time_keys(module_name, constants)
        missing = sorted(
            f"{key} has no {key}{_TWIN_SUFFIX}"
            for key in keys
            if key.endswith(_INSTANT_SUFFIXES) and f"{key}{_TWIN_SUFFIX}" not in keys
        )
        if missing:
            violations[module_name] = missing
    return violations


def _find_bare_instant_keys() -> dict[str, list[str]]:
    """Return each entity surface publishing an instant that does not name its concept.

    The decision this encodes: nesting is allowed, so a service or tool response may
    scope an instant under a parent key that supplies the concept. An entity attribute
    is flat and has no parent, so `at` and `timestamp` there are incomplete names
    rather than shorthand -- `fired_at` says what happened, `at` says only that
    something happened at some point in the enclosing object.
    """
    constants = _string_constants()
    violations: dict[str, list[str]] = {}
    for module_name in _ENTITY_PUBLISHING_MODULES:
        keys = _published_time_keys(module_name, constants)
        found = sorted(key for key in keys if key in _BARE_INSTANT_KEYS)
        if found:
            violations[module_name] = found
    return violations


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Phase 3 pairs the service instants and Phase 4 the entity ones. "
        "strict=True so this marker cannot outlive the work: the moment both phases "
        "land, the test passes and the marker itself fails the suite until removed. "
        "Measured gaps at the time of writing, all real: "
        "services.py `pause_until`; switch.py `pause_until`; binary_sensor.py "
        "`fired_at` and `runtime_data_updated_at`; sensor.py `sampled_at` and "
        "`tested_at`."
    ),
)
def test_every_published_instant_has_an_epoch_twin() -> None:
    """Test an instant and its arithmetic form are published together.

    Every instant appears twice: an ISO form to read (`<name>_at` or `_until`) and an
    epoch form to compute with (`<name>_timestamp`). Publishing only the ISO form
    forces a caller to parse a string to compare two times; publishing only the epoch
    form is the Class A defect, where a reader has a number and no date.

    **Known limitations, stated so this is not mistaken for total.** Two, and both are
    the reason the companion guard below exists rather than this one being widened:

    - The check is suffix-based, so a key that *predates* the convention is invisible
      to it -- `last_active` marks an instant without using `_at`. The approved
      `last_active` -> `last_active_at` rename is what brings that straggler inside
      the rule.
    - It requires `endswith("_at")`, which does not match a bare `at` or `timestamp`.
      Scoped names therefore pass unseen, which is how `build_rule_hit_attributes`
      came to be cited here as the correct reference while using names this standard
      does not permit. That is `test_entity_instants_name_their_concept`'s job.
    """
    violations = _find_unpaired_instants()

    assert violations == {}, (
        "these published instants have no epoch twin, so a caller must parse a "
        "string to do arithmetic -- or, on the entity side, has a raw number and no "
        f"date: {violations}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Phase 3 resolves the one shared builder that publishes bare keys. "
        "`build_rule_hit_attributes` serves the rule service payload *and* the rule "
        "switch, so its `at`/`timestamp` land on an entity attribute as well as in a "
        "nested response, and the two rules this decision draws apart disagree there. "
        "strict=True so the marker cannot outlive the work."
    ),
)
def test_entity_instants_name_their_concept() -> None:
    """Test no entity surface publishes an instant that does not name its concept.

    Nesting is permitted: a service or tool response may scope an instant under a
    parent key, where the parent supplies the concept. An entity attribute is flat and
    has no parent, so `at` and `timestamp` there are incomplete names rather than
    shorthand -- `fired_at` says what happened, `at` says only that something happened
    at some point inside the enclosing object.

    `models.py` is scanned as an entity surface on purpose. `build_rule_hit_attributes`
    is called by the rule service payload *and* by the rule switch, so a bare key
    defined there is a bare key on an entity however the service half reads it, and
    attributing it to the service half would be the attribution error that puts the
    defect back out of sight.
    """
    violations = _find_bare_instant_keys()

    assert violations == {}, (
        "these entity surfaces publish an instant that does not name its concept, so "
        "a reader has a bare `at`/`timestamp` with nothing to say what it is an "
        f"instant of: {violations}"
    )


def test_the_pairing_check_reads_real_keys() -> None:
    """Test the scan found published keys, so a pass above means something.

    Without this, a scan that silently walked nothing -- a renamed module, a changed
    import, an `ATTR_*` indirection it stopped resolving -- would report zero
    violations and look identical to a clean package.
    """
    constants = _string_constants()
    found = {
        module_name: _published_time_keys(module_name, constants)
        for module_name in _CONTRACT_MODULES
    }
    total = sum(len(keys) for keys in found.values())

    # `pause_until` is an entity attribute reached only by resolving an `ATTR_*`
    # name, so finding it proves the indirection resolution works rather than the
    # scan merely seeing literals.
    assert "pause_until" in found["switch.py"], (
        "the scan did not resolve an ATTR_* name to its published value, so it is "
        f"only reading literals: {sorted(found['switch.py'])[:12]}"
    )
    assert total > 100, (
        f"the scan found only {total} published keys across the contract modules, "
        "far fewer than they define; it is not reading them"
    )


def _entry() -> MockConfigEntry:
    """Return a config entry for the service guards."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )


async def _call(hass: HomeAssistant, service: str, entry: MockConfigEntry):
    """Call one read service against the fixture snapshot and return the response.

    `refresh` is not passed: not every read service accepts it (`get_system_overview`
    does not), and the client is patched anyway, so asking for a poll would change
    nothing but would reject the call.
    """
    return await hass.services.async_call(
        DOMAIN,
        service,
        {SERVICE_FIELD_CONFIG_ENTRY_ID: entry.entry_id},
        blocking=True,
        return_response=True,
    )


@asynccontextmanager
async def _loaded_entry(hass: HomeAssistant) -> AsyncIterator[MockConfigEntry]:
    """Yield an entry loaded against a snapshot holding one active and one quiet host.

    Both are appended, so a recomputation always has an online and an offline row
    to disagree about. A fixture where everything is online would satisfy an
    `online is True` assertion that was only ever measuring the fixture.
    """
    entry = _entry()
    entry.add_to_hass(hass)

    base = _snapshot()
    template = base.hosts[0]
    active_host = replace(
        template,
        mac="11:22:33:44:55:66",
        host_name="ftv-lr",
        connection_type=None,
        last_active=1_700_000_000.0,
    )
    quiet_host = replace(
        template,
        mac="11:22:33:44:55:77",
        host_name="kadens-camera",
        connection_type=None,
        last_active=1_700_000_000.0 - (86_400 * 30),
    )
    snapshot = replace(base, hosts=(*base.hosts, active_host, quiet_host))

    with (
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "async_get_runtime_init_payload",
            new=AsyncMock(return_value=_runtime_payload()),
        ),
        patch(
            "custom_components.firewalla_local.api.client.FirewallaApiClient."
            "build_runtime_snapshot",
            return_value=snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry


def _assert_basis_published(service: str, envelope: object) -> None:
    """Assert one response states the frame its connectivity values are in.

    Shared by the three surfaces rather than restated, because a basis check that
    drifts per surface is the defect it exists to catch.
    """
    assert isinstance(envelope, dict)
    missing = [
        key
        for key in (*_BASIS_REFERENCE_KEYS, *_BASIS_WINDOW_KEYS)
        if key not in envelope
    ]
    assert missing == [], (
        f"{service} publishes a windowed value without its basis, so a caller "
        f"cannot reproduce it: {missing} absent. Connectivity is "
        "`activity_reference - last_active <= online_window_seconds`, and all "
        "three inputs were unpublished -- which is how the same five peers read "
        "online in one tool and offline in another."
    )


async def test_get_hosts_publishes_the_basis_its_rows_are_measured_in(
    hass: HomeAssistant,
) -> None:
    """Test `online` can be checked by a caller who has only the payload.

    `online` is derived: `activity_reference - last_active <=
    online_window_seconds`, and both halves of that have to be published for the
    value to be data rather than a claim. This is the acceptance test for the
    initiative: a caller recomputing `online` from the payload alone and getting
    the published answer.

    `stale` is part of the recomputation because it is part of the rule: a host
    the box has not seen in about a week is offline however recent its last
    activity stamp looks, so a payload without `stale` cannot explain a `False`
    the basis says should be `True`.
    """
    async with _loaded_entry(hass) as entry:
        response = await _call(hass, SERVICE_GET_HOSTS, entry)

    _assert_basis_published(SERVICE_GET_HOSTS, response)

    reference = response["activity_reference_at_timestamp"]
    window = response["online_window_seconds"]
    rows = response["hosts"]
    assert isinstance(rows, list)

    checked = 0
    for row in rows:
        activity = next(
            (row[key] for key in _HOST_ACTIVITY_KEYS if row.get(key) is not None),
            None,
        )
        if activity is None:
            continue
        checked += 1
        recomputed = row["stale"] is not True and (reference - activity) <= window
        assert row["online"] is recomputed, (
            f"{SERVICE_GET_HOSTS}: host {row.get('host_name')!r} published "
            f"online={row['online']!r} but the published basis says {recomputed} "
            f"(activity_reference={reference}, last_active={activity}, "
            f"stale={row['stale']}, window={window})"
        )

    assert checked >= 2, (
        "the fixture published fewer than two measurable rows, so a passing loop "
        "above proves nothing"
    )


async def test_get_system_overview_publishes_the_basis_its_counts_are_measured_in(
    hass: HomeAssistant,
) -> None:
    """Test the overview's counts and the host list agree on the same box.

    The counts cannot be recomputed from the overview alone -- it publishes totals,
    not rows -- so agreement is checked against `get_hosts` instead. That is the
    stronger assertion anyway, because it is the one the live defect failed: the
    overview reported one connected VPN peer while the host list reported all five
    offline, seconds apart, because the count was measured against the freshest
    *peer* rather than against the appliance.
    """
    async with _loaded_entry(hass) as entry:
        overview = await _call(hass, SERVICE_GET_SYSTEM_OVERVIEW, entry)
        listed = await _call(hass, SERVICE_GET_HOSTS, entry)

    _assert_basis_published(SERVICE_GET_SYSTEM_OVERVIEW, overview)

    rows = listed["hosts"]
    assert isinstance(rows, list)

    assert overview["hosts"] == {
        "total": len(rows),
        "online": sum(1 for row in rows if row["online"] is True),
        "offline": sum(1 for row in rows if row["online"] is not True),
    }, "the overview's device counts disagree with the host list's own rows"

    peers = [row for row in rows if row["kind"] == "pseudo_host"]
    assert overview["vpn_hosts"] == {
        "total": len(peers),
        "online": sum(1 for row in peers if row["online"] is True),
        "offline": sum(1 for row in peers if row["online"] is not True),
    }, "the overview's VPN peer counts disagree with the peer rows it also lists"


async def test_get_runtime_inventory_publishes_the_basis_its_counts_are_measured_in(
    hass: HomeAssistant,
) -> None:
    """Test the inventory report states the frame its host counts were taken in.

    The counts sit in `summary` beside the basis rather than at the top level,
    because that is where the counts they explain live. This path derives the
    reference from the snapshot it just polled rather than from the coordinator's
    cached one, so publishing it is what lets a reader confirm it describes the
    same inventory the counts were taken over.
    """
    async with _loaded_entry(hass) as entry:
        response = await _call(hass, SERVICE_GET_RUNTIME_INVENTORY, entry)

    inventory = response["inventory"]
    assert isinstance(inventory, dict)
    _assert_basis_published(SERVICE_GET_RUNTIME_INVENTORY, inventory["summary"])
