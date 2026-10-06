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
_BASIS_REFERENCE_KEYS: Final = ("as_of", "as_of_timestamp")
_BASIS_WINDOW_KEYS: Final = ("online_window_seconds",)

# The epoch form of a host's last activity. Accepts either name so the guard holds
# through the planned `last_active` -> `last_active_at` + `last_active_timestamp`
# rename rather than only before or only after it.
_HOST_ACTIVITY_KEYS: Final = ("last_active_timestamp", "last_active")


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

    Every instant appears twice: an ISO form to read (`<name>_at`) and an epoch form
    to compute with (`<name>_timestamp`). Publishing only the ISO form forces a caller
    to parse a string to compare two times; publishing only the epoch form is the
    Class A defect, where a reader has a number and no date.

    `build_rule_hit_attributes` already does this correctly with `at` + `timestamp`,
    and is the reference the rest of the surface is being brought to.

    **Known limitation, stated so it is not mistaken for total:** this check is
    suffix-based, so a key that *predates* the convention is invisible to it --
    `last_active` marks an instant without using `_at`. That is what the approved
    `last_active` -> `last_active_at` rename fixes; once renamed, this guard covers
    it. The guard enforces the convention for every key that follows it, and the
    rename is what brings the last straggler inside the rule.
    """
    violations = _find_unpaired_instants()

    assert violations == {}, (
        "these published instants have no epoch twin, so a caller must parse a "
        "string to do arithmetic -- or, on the entity side, has a raw number and no "
        f"date: {violations}"
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


@pytest.mark.parametrize(
    "service",
    [
        pytest.param(
            SERVICE_GET_HOSTS,
            id="get_hosts",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "Resolved by Phase 2, which publishes `as_of`, "
                    "`as_of_timestamp` and `online_window_seconds`. strict=True so "
                    "the marker cannot outlive the work: once the basis is "
                    "published the recomputation matches and the marker fails the "
                    "suite until removed."
                ),
            ),
        ),
        pytest.param(
            SERVICE_GET_SYSTEM_OVERVIEW,
            id="get_system_overview",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "Resolved by Phase 2, which publishes the basis on this "
                    "response envelope alongside the counts it summarises. "
                    "strict=True so the marker cannot outlive the work."
                ),
            ),
        ),
    ],
)
async def test_a_windowed_boolean_publishes_its_basis(
    hass: HomeAssistant, service: str
) -> None:
    """Test `online` can be checked by a caller who has only the payload.

    `online` is derived: `reference_activity - last_active <= online_window_seconds`.
    All three inputs were unpublished, which made the value unexplainable without
    reading the source -- and produced a live contradiction where the same five VPN
    peers were simultaneously "1 online" in one tool and "0 online" in another.

    So the response must carry the reference instant it measured from and the window
    it applied, and every published boolean must agree with the arithmetic. With those
    two published, a reader can reproduce the answer; without them, they cannot, and
    the value is a claim rather than data.

    This is the acceptance test for the whole initiative: a caller recomputing
    `online` from the payload alone and getting the published answer.
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
        response = await _call(hass, service, entry)

    assert response is not None

    missing = [key for key in _BASIS_REFERENCE_KEYS if key not in response]
    missing += [key for key in _BASIS_WINDOW_KEYS if key not in response]
    assert missing == [], (
        f"{service} publishes a windowed boolean without its basis, so a caller "
        f"cannot reproduce it: {missing} absent. `online` is "
        "`as_of - last_active <= online_window_seconds`, and all three inputs were "
        "unpublished -- which is how the same peers read online in one tool and "
        "offline in another."
    )

    reference = response["as_of_timestamp"]
    window = response["online_window_seconds"]
    rows = response.get("hosts")
    assert isinstance(rows, list), f"{service} published no host rows to check"

    for row in rows:
        activity = next(
            (row[key] for key in _HOST_ACTIVITY_KEYS if row.get(key) is not None),
            None,
        )
        if activity is None:
            continue
        recomputed = (reference - activity) <= window
        assert row["online"] is recomputed, (
            f"{service}: host {row.get('host_name')!r} published "
            f"online={row['online']!r} but the published basis says {recomputed} "
            f"(as_of={reference}, last_active={activity}, window={window})"
        )
