"""Reading a service call's selector and matching it against runtime records.

Two jobs, in the order a service performs them.

**Reading the selection.** A scope -- a host, a group, or a user -- used to be
selected two different ways. Eleven services took a typed pair
(``host_mac``/``host_name``, ``group_id``/``group_name``, ...) while the two report
services took a ``scope_kind`` enum plus a free-text ``scope_target``. The reports
were the outliers, and the free-text field had a defect the typed ones do not: a
group and a user can share a name, and one string with a separate kind cannot tell
them apart. :func:`select_scope` owns that vocabulary and the rule the services
share -- exactly one scope is selected -- and :data:`SCOPE_SELECTOR_FIELDS` is the
single statement of which field belongs to which scope.

**Matching it.** Three service paths resolve a name-or-id selector the same way: an
exact identifier match first, then a case-folded name match across a set of name
fields, then exactly-one → resolved / more-than-one → ambiguous / none → not found.

They had grown into three separate implementations --
``_resolve_requested_host``, ``_resolve_membership_target`` and
``_resolve_usage_history_target``, about 322 lines between them -- so adding the
flow report as a fourth consumer would have made four.

**Only the matching is shared, not the resolution.** The three differ in ways that
matter and are not accidents:

- they match different name fields. The host resolver matches five
  (``host_name``, ``dns_hostname``, ``dhcp_name``, ``dns_fqdn``, watched choice)
  while the usage resolver matches two. ``llm_tools_read.py`` documents the
  intent -- ``host_name`` is *"the one to match a user's words against"* and
  ``dhcp_name`` is *"device-supplied and unreliable... never use it to identify a
  device"* -- so the narrower set is the one following the documented rule.
- they report ambiguity differently. The host and membership resolvers name the
  matches so a caller can choose; the usage resolver does not.
- their errors are translation-key ``ServiceValidationError`` instances, which
  ``ARCHITECTURE.md`` assigns to the *service* layer.

So this returns the raw outcome and leaves the error mapping, the match-list
formatting and the return type with each caller. A single unified resolver would
need injected translation keys and a per-type projection, which is an abstraction
over three real differences rather than a shared one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from .values import normalized_string

# Which fields select which scope. Each entry is the machine name of a selector, so
# these are the published `SERVICE_FIELD_*` values and stay in the machine register.
SCOPE_SELECTOR_FIELDS: Final[Mapping[str, tuple[str, ...]]] = {
    "host": ("host_id", "host_mac", "host_name"),
    "group": ("group_id", "group_name"),
    "user": ("user_id", "user_name"),
}

# Which fields name an identifier rather than a label. An identifier is assigned by
# the box and matched verbatim; a label is typed by a human and matched
# case-insensitively. A single free-text field could not make this distinction, which
# is why it could match a group id against a user's name; a typed pair does not.
SCOPE_IDENTIFIER_FIELDS: Final[frozenset[str]] = frozenset(
    {"host_id", "host_mac", "group_id", "user_id"}
)


@dataclass(slots=True, frozen=True)
class ScopeSelection:
    """The one scope a call selected, or why it did not select exactly one.

    ``is_selected`` is true only when exactly one selector field was supplied, which
    is the whole contract: no scope and two scopes are both errors, and a caller that
    supplies two fields of the *same* scope has still made an ambiguous request
    rather than stated a preference.
    """

    kind: str | None = None
    field: str | None = None
    value: str | None = None
    supplied: tuple[str, ...] = ()

    @property
    def is_selected(self) -> bool:
        """Return whether exactly one selector field was supplied."""
        return self.kind is not None

    @property
    def is_identified(self) -> bool:
        """Return whether the selected field carries an identifier, not a label."""
        return self.field in SCOPE_IDENTIFIER_FIELDS


def select_scope(
    values: Mapping[str, object],
    *,
    fields: Sequence[str] = (),
) -> ScopeSelection:
    """Return the scope one call selected from its typed selector fields.

    ``fields`` narrows the vocabulary to the selector fields this service actually
    accepts, and an empty ``fields`` means all of them. A field a service does not
    accept is not a selector it was given, so it is ignored rather than silently
    selecting a scope the service cannot resolve -- which is also why narrowing is
    expressed as fields and not as kinds: a report resolves a host by MAC or name and
    never by ``host_id``, so offering the kind would offer a selector it cannot use.
    """
    permitted = (
        frozenset(fields)
        if fields
        else frozenset(
            field for names in SCOPE_SELECTOR_FIELDS.values() for field in names
        )
    )
    supplied: list[tuple[str, str, str]] = []
    for kind, names in SCOPE_SELECTOR_FIELDS.items():
        for field in names:
            if field not in permitted:
                continue
            value = normalized_string(values.get(field))
            if value is not None:
                supplied.append((kind, field, value))

    if len(supplied) == 1:
        kind, field, value = supplied[0]
        return ScopeSelection(kind=kind, field=field, value=value)

    return ScopeSelection(supplied=tuple(field for _kind, field, _value in supplied))


@dataclass(slots=True, frozen=True)
class SelectorMatch:
    """The outcome of matching one selector against a set of records.

    ``exact`` is the identifier of a record whose id matched the selector
    verbatim. ``name_matches`` are the identifiers of every record whose name
    fields matched it case-insensitively; an exact hit does not also populate it,
    because an id match is decisive and listing names would invite a caller to
    treat a resolved case as ambiguous.
    """

    exact: str | None = None
    name_matches: tuple[str, ...] = ()

    @property
    def resolved(self) -> str | None:
        """Return the single matched identifier, or ``None`` when not resolvable.

        ``None`` covers both "nothing matched" and "more than one matched", which
        are different failures for a caller to report. Use :attr:`is_ambiguous`
        to tell them apart.
        """
        if self.exact is not None:
            return self.exact
        if len(self.name_matches) == 1:
            return self.name_matches[0]
        return None

    @property
    def is_ambiguous(self) -> bool:
        """Return whether several records matched a name selector."""
        return self.exact is None and len(self.name_matches) > 1

    @property
    def is_missing(self) -> bool:
        """Return whether nothing matched at all."""
        return self.exact is None and not self.name_matches


def match_selector(
    selector: str,
    candidates: Iterable[tuple[str, Sequence[str | None]]],
    *,
    normalize_identifier: Callable[[str], str | None] | None = None,
) -> SelectorMatch:
    """Match one selector against ``(identifier, names)`` pairs.

    The identifier is tried before any name, which is the order the three existing
    resolvers use: an identifier is assigned by the box and a name is typed by a
    human, so an identifier hit is decisive and must not be treated as one of
    several candidates.

    ``normalize_identifier`` exists because callers do not agree on identifier
    equality. A host is looked up by MAC and the box's MACs are matched
    case-insensitively, while a group id is compared verbatim. Passing the
    caller's own normalizer keeps that behaviour rather than flattening it.

    A caller that resolves its identifiers separately -- because a selector has a
    dedicated id parameter and a dedicated name parameter, as the host and
    membership resolvers do -- should use :func:`match_names` instead, or it would
    gain an identifier path its contract does not have.
    """
    # Materialised before the first pass: the identifier check and the name match
    # are two traversals, and a caller passing a generator would otherwise have it
    # exhausted by the first, silently matching nothing.
    materialised = tuple(candidates)

    wanted = selector
    if normalize_identifier is not None:
        wanted = normalize_identifier(selector) or selector

    for identifier, _names in materialised:
        if identifier == wanted:
            return SelectorMatch(exact=identifier)

    return SelectorMatch(name_matches=match_names(selector, materialised))


def match_names(
    selector: str,
    candidates: Iterable[tuple[str, Sequence[str | None]]],
) -> tuple[str, ...]:
    """Return the identifiers whose names match ``selector``, case-insensitively.

    A name is typed by a human, so the comparison is case-folded and a stored name
    is normalized first. The selector is compared as given, which is what the
    existing resolvers did.
    """
    folded = selector.casefold()
    return tuple(
        identifier
        for identifier, names in candidates
        if any(
            (name := normalized_string(candidate)) is not None
            and name.casefold() == folded
            for candidate in names
        )
    )
