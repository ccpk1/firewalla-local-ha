"""Matching a user-supplied selector against runtime inventory records.

Three service paths resolve a name-or-id selector the same way: an exact
identifier match first, then a case-folded name match across a set of name fields,
then exactly-one → resolved / more-than-one → ambiguous / none → not found.

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

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from .values import normalized_string


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

    The identifier is compared before any name, which is the order the three
    existing resolvers use: an identifier is assigned by the box and a name is
    typed by a human, so an identifier hit is decisive and must not be treated as
    one of several candidates.

    ``normalize_identifier`` exists because callers do not agree on identifier
    equality. A host is looked up by MAC and the box's MACs are matched
    case-insensitively, while a group id is compared verbatim. Passing the
    caller's own normalizer keeps that behaviour rather than flattening it.

    Blank entries in ``names`` are ignored, so a caller can pass a record's full
    set of name fields without filtering the unset ones first.
    """
    wanted = selector
    if normalize_identifier is not None:
        wanted = normalize_identifier(selector) or selector

    folded = selector.casefold()
    name_matches: list[str] = []

    for identifier, names in candidates:
        if identifier == wanted:
            return SelectorMatch(exact=identifier)
        if any(
            (name := normalized_string(candidate)) is not None
            and name.casefold() == folded
            for candidate in names
        ):
            name_matches.append(identifier)

    return SelectorMatch(name_matches=tuple(name_matches))
