"""Pure value coercion for Firewalla payloads.

Firewalla payloads are loosely typed. The same logical field arrives as an
``int``, a ``float``, or a string depending on the endpoint and the box's
firmware version: rule hit counts come back as either ``54`` or ``"54"``, byte
totals as JSON numbers, an event ``ts`` as a fractional ``1791035437.587``, and
a VLAN id as ``"20"``.

Seven near-identical integer coercers had accumulated across the client, the
integration manager, the services module, and the network utilities, and they
disagreed on three inputs: whether ``True`` is ``1`` or absent, whether a
``float`` is accepted, and whether surrounding whitespace is stripped. Those
disagreements were invisible at the call site -- ``self._optional_int(...)`` and
``_normalized_int(...)`` look like the same operation and were not.

There are two policies here, chosen deliberately rather than by averaging:

- :func:`normalized_int` for counts, byte totals, and timestamps.
- :func:`normalized_number` for measurements that are genuinely fractional,
  such as event state values.

Both reject ``bool``. Python makes ``True`` an ``int``, so a payload sending
``true`` where a count belongs would otherwise be read as ``1`` -- a wrong
number rather than a missing one, which is the worse failure for a measurement
because nothing downstream can tell it apart from real data.

Both accept ``float`` and truncate it for :func:`normalized_int`. These payloads
carry epoch timestamps as fractional seconds, so rejecting floats would silently
drop real values.

Both strip strings before conversion, so ``" 443"`` and ``"443"`` read the same.

A value that cannot be converted is not an error. These are optional protocol
fields, and ``None`` is how the rest of the integration represents absent data;
raising would turn a cosmetic payload change into an unavailable entity.
"""

from __future__ import annotations

from typing import Final

# Representations of a boolean the box actually puts on the wire. Measured
# across 259 rules and the network and host inventories.
_BOOL_TRUE_STRINGS: Final = frozenset({"1", "true", "yes"})
_BOOL_FALSE_STRINGS: Final = frozenset({"0", "false", "no"})


def normalized_int(value: object) -> int | None:
    """Return an integer when one can be honestly derived.

    Accepts an ``int``, a ``float`` (truncated), or a numeric string. Rejects
    ``bool`` so a payload's ``true`` is absent rather than ``1``.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped_value = value.strip()
        if not stripped_value:
            return None
        try:
            return int(stripped_value)
        except ValueError:
            return None
    return None


def normalized_number(value: object) -> int | float | None:
    """Return an ``int`` or ``float`` when one can be honestly derived.

    An integral value stays an ``int`` and a fractional one stays a ``float``,
    so callers can tell a count from a measurement. Rejects ``bool`` for the
    same reason as :func:`normalized_int`.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        stripped_value = value.strip()
        if not stripped_value:
            return None
        try:
            return int(stripped_value)
        except ValueError:
            try:
                return float(stripped_value)
            except ValueError:
                return None
    return None


def normalized_float(value: object) -> float | None:
    """Return a float when one can be honestly derived.

    Every accepted numeric input becomes a ``float``, including an ``int``, so
    the return type is uniform for callers doing fractional arithmetic.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped_value = value.strip()
        if not stripped_value:
            return None
        try:
            return float(stripped_value)
        except ValueError:
            return None
    return None


def normalized_string(value: object) -> str | None:
    """Return a non-empty stripped string when one is present.

    Four identical copies of this existed across the integration manager, the
    services module, and the network utilities under three different names.
    """
    if not isinstance(value, str):
        return None
    stripped_value = value.strip()
    return stripped_value or None


def normalized_bool(value: object) -> bool | None:
    """Return a boolean when one can be honestly derived.

    The box encodes a boolean four different ways, all observed live:

    - a real JSON ``bool``
    - an integer ``0`` / ``1``
    - a string ``"1"`` / ``"0"`` (``autoDeleteWhenExpires``)
    - a string ``"true"`` / ``"false"``

    so all four are accepted. Six separate helpers previously handled this, and
    they split into two camps that each read only one of those encodings: three
    accepted integers and no strings, three accepted ``"true"`` / ``"false"``
    and no integers. A field was therefore readable by whichever camp happened
    to be wired to it, not by what the box sent.

    **An empty string is not a representation of a boolean** and returns
    ``None``. It is an opaque marker whose meaning is per-field: on ``useBf`` it
    marks a DNS-only rule where the flag is *set*, so reading it as ``False``
    would invert the flag on rule creation. A caller that needs to know whether
    a field was present should test for the empty string itself.

    A value that is not one of the four encodings returns ``None`` rather than
    raising, matching how the rest of the integration represents absent data.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in _BOOL_TRUE_STRINGS:
            return True
        if lowered in _BOOL_FALSE_STRINGS:
            return False
    return None
