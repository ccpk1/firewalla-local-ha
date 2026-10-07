"""Tests for the shared selector matching core.

The matching rules these pin were previously implemented three times, so the point
of most of these is that the extraction did not quietly change any of them.
"""

from __future__ import annotations

import pytest

from custom_components.firewalla_local.utils.mac import normalize_mac_address
from custom_components.firewalla_local.utils.selectors import (
    SelectorMatch,
    match_names,
    match_selector,
)

_HOSTS = (
    ("CC:28:AA:11:06:B7", ("Kaden's PC", None)),
    ("4C:1D:96:E3:3A:96", ("Living Room TV", "tv.lan")),
    ("00:AA:BB:CC:DD:26", ("kid-ipad", None)),
)


def test_an_identifier_match_wins_and_is_not_treated_as_a_candidate() -> None:
    """Test an identifier hit is decisive.

    An identifier is assigned by the box and a name is typed by a human, so an
    identifier hit must resolve rather than joining the ambiguity count.
    """
    match = match_selector("4C:1D:96:E3:3A:96", _HOSTS)

    assert match.exact == "4C:1D:96:E3:3A:96"
    assert match.name_matches == ()
    assert match.resolved == "4C:1D:96:E3:3A:96"
    assert match.is_ambiguous is False


def test_a_name_match_is_case_insensitive() -> None:
    """Test a human-typed name matches regardless of case."""
    assert match_selector("living room tv", _HOSTS).resolved == "4C:1D:96:E3:3A:96"
    assert match_selector("LIVING ROOM TV", _HOSTS).resolved == "4C:1D:96:E3:3A:96"


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        pytest.param("tv.lan", "4C:1D:96:E3:3A:96", id="second_name_field"),
        pytest.param("kaden's pc", "CC:28:AA:11:06:B7", id="first_name_field"),
    ],
)
def test_any_supplied_name_field_can_match(selector: str, expected: str) -> None:
    """Test a record's full name set is searched, not just the first field."""
    assert match_selector(selector, _HOSTS).resolved == expected


def test_a_records_name_is_trimmed_but_the_selector_is_not() -> None:
    """Test the asymmetry in whitespace handling, which is existing behaviour.

    A stored name is normalized before comparison, but a caller-supplied selector
    is compared as given. So a name with stray whitespace still matches, while a
    selector with stray whitespace does not -- which means ``"  kid-ipad  "``
    reports "not found" rather than resolving.

    This is pinned rather than fixed: it is what the three resolvers did before
    the matching was shared, and trimming the selector would be a behaviour change
    to two shipped services rather than part of an extraction. It is a plausible
    improvement, and it would need to be a deliberate one.
    """
    padded_name = (("mac-1", ("  padded name  ",)),)

    assert match_selector("padded name", padded_name).resolved == "mac-1"
    assert match_selector("  kid-ipad  ", _HOSTS).is_missing is True


def test_a_blank_name_field_is_ignored_rather_than_matching_an_empty_selector() -> None:
    """Test unset name fields do not make every record a candidate.

    A caller passes a record's whole name set, most of which is usually unset, so
    a blank must be skipped rather than compared.
    """
    match = match_selector("", _HOSTS)

    assert match.is_missing is True
    assert match.resolved is None


def test_several_name_matches_are_reported_as_ambiguous() -> None:
    """Test more than one match is distinguishable from no match.

    The two are different failures for a caller to report, so `resolved` is None
    for both and `is_ambiguous` tells them apart.
    """
    duplicated = (
        ("mac-1", ("Same Name",)),
        ("mac-2", ("same name",)),
    )
    match = match_selector("Same Name", duplicated)

    assert match.resolved is None
    assert match.is_ambiguous is True
    assert match.is_missing is False
    assert match.name_matches == ("mac-1", "mac-2")


def test_no_match_at_all_is_reported_as_missing() -> None:
    """Test a selector that matches nothing is not reported as ambiguous."""
    match = match_selector("Nothing Here", _HOSTS)

    assert match.resolved is None
    assert match.is_ambiguous is False
    assert match.is_missing is True


def test_a_caller_can_normalize_the_identifier_before_comparing() -> None:
    """Test the caller's identifier convention is preserved.

    A host is looked up by MAC and the box's MACs are matched case-insensitively,
    while a group id is compared verbatim. Flattening that would change which
    selectors resolve.
    """
    lowercase = ((normalize_mac_address("aa:bb:cc:dd:ee:ff") or "", ("Router",)),)

    assert (
        match_selector(
            "aa:bb:cc:dd:ee:ff", lowercase, normalize_identifier=normalize_mac_address
        ).exact
        == "AA:BB:CC:DD:EE:FF"
    )
    # Without the normalizer the same selector does not match the stored form.
    assert match_selector("aa:bb:cc:dd:ee:ff", lowercase).is_missing is True


def test_a_normalizer_that_declines_the_selector_falls_back_to_the_raw_value() -> None:
    """Test a name-shaped selector is not destroyed by a MAC normalizer.

    The host resolver normalizes before comparing, and a name is not a MAC, so the
    raw selector still has to be tried rather than becoming the normalized nothing.
    """
    match = match_selector(
        "Living Room TV", _HOSTS, normalize_identifier=normalize_mac_address
    )

    assert match.resolved == "4C:1D:96:E3:3A:96"


def test_matching_an_empty_candidate_set_resolves_nothing() -> None:
    """Test an empty inventory is missing rather than an error."""
    match = match_selector("anything", ())

    assert match.is_missing is True
    assert match.resolved is None


def test_a_blank_selector_does_not_match_a_record_with_no_names() -> None:
    """Test a nameless record is not matched by a blank selector."""
    match = match_selector("", (("mac-1", (None,)),))

    assert match.is_missing is True


def test_the_outcome_defaults_to_nothing_matched() -> None:
    """Test an unpopulated outcome reads as missing rather than resolved."""
    match = SelectorMatch()

    assert match.resolved is None
    assert match.is_missing is True
    assert match.is_ambiguous is False


def test_a_lazy_candidate_sequence_is_still_searched_by_name() -> None:
    """Test a generator of candidates is not exhausted by the identifier pass.

    The identifier check and the name match are two traversals. A caller passing a
    generator would otherwise have it consumed by the first, silently matching
    nothing -- which is exactly what happened when this helper was split, and it
    took four service tests down with it.
    """
    lazy = ((mac, names) for mac, names in _HOSTS)

    match = match_selector("Living Room TV", lazy)

    assert match.resolved == "4C:1D:96:E3:3A:96"


def test_match_names_answers_every_match_for_a_lazy_sequence() -> None:
    """Test the name-only matcher materialises nothing it does not need to."""
    lazy = ((mac, names) for mac, names in _HOSTS)

    assert match_names("kid-ipad", lazy) == ("00:AA:BB:CC:DD:26",)
    assert match_names("nothing here", lazy) == ()
