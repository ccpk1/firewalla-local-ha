"""Tests for the shared value coercion policy.

The values used here are the ones actually observed on the wire, taken from a
live init payload and a live flow page, so the policy is pinned to what the box
sends rather than to what a JSON schema would suggest.
"""

from __future__ import annotations

import pytest

from custom_components.firewalla_local.utils.values import (
    normalized_bool,
    normalized_float,
    normalized_int,
    normalized_number,
    normalized_string,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(True, True, id="bool_true"),
        pytest.param(False, False, id="bool_false"),
        pytest.param(1, True, id="int_one"),
        pytest.param(0, False, id="int_zero"),
        pytest.param("1", True, id="str_one"),
        pytest.param("0", False, id="str_zero"),
        pytest.param("true", True, id="str_true"),
        pytest.param("false", False, id="str_false"),
        pytest.param("TRUE", True, id="str_true_uppercase"),
        pytest.param("yes", True, id="str_yes"),
        pytest.param("no", False, id="str_no"),
        pytest.param(" 1 ", True, id="str_padded"),
        pytest.param(None, None, id="none"),
        pytest.param("maybe", None, id="unknown_string"),
        pytest.param(2, True, id="int_other_truthy"),
    ],
)
def test_all_four_wire_encodings_of_a_boolean_are_read(
    value: object,
    expected: bool | None,
) -> None:
    """The box sends bool, int, "1"/"0", and "true"/"false" for one flag."""
    assert normalized_bool(value) is expected


def test_an_empty_string_is_not_a_boolean() -> None:
    """An empty string is an opaque marker, not a false value.

    `useBf` sends "" on 36 DNS-only rules where the flag is *set*. Reading it as
    False would invert the flag when a rule template is created from one of them,
    so the policy deliberately declines rather than answering.
    """
    assert normalized_bool("") is None


def test_the_rule_hit_count_field_reads_as_a_number_when_wrapped_in_quotes() -> None:
    """`hitCount` arrives as a numeric string.

    Real values from the live pull: `"54"` on a rule that has fired and `"0"` on
    one that has not.
    """
    assert normalized_int("54") == 54
    assert normalized_int("0") == 0


def test_a_rule_state_flag_encoded_as_text_is_read() -> None:
    """`autoDeleteWhenExpires` is only ever "0"/"1" on the wire.

    A string-only coercer that accepts just "true"/"false" reads every one of
    these as absent, which is the defect the union policy removes.
    """
    assert normalized_bool("1") is True
    assert normalized_bool("0") is False


def test_boolean_fields_are_not_read_as_numbers_and_vice_versa() -> None:
    """`True` is not a count.

    Python makes `True == 1`, so a payload sending `true` where a measurement
    belongs would read as 1 -- a wrong number rather than a missing one, which
    nothing downstream can tell apart from real data.
    """
    assert normalized_int(True) is None
    assert normalized_number(True) is None
    assert normalized_float(True) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(54, 54, id="int"),
        pytest.param("54", 54, id="str"),
        pytest.param(" 54 ", 54, id="padded_str"),
        pytest.param(54.0, 54, id="float_truncated"),
        pytest.param("12.5", None, id="fractional_str_not_an_int"),
        pytest.param("", None, id="empty_str"),
        pytest.param(None, None, id="none"),
        pytest.param("abc", None, id="non_numeric"),
    ],
)
def test_integers_read_from_the_encodings_the_box_uses(
    value: object,
    expected: int | None,
) -> None:
    """Counts, byte totals, and epoch timestamps all come back as these."""
    assert normalized_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(54, 54, id="int_stays_int"),
        pytest.param(54.5, 54.5, id="float_stays_float"),
        pytest.param("54", 54, id="str_int"),
        pytest.param("54.5", 54.5, id="str_float"),
        pytest.param("abc", None, id="non_numeric"),
    ],
)
def test_numbers_keep_the_distinction_between_a_count_and_a_measurement(
    value: object,
    expected: int | float | None,
) -> None:
    """A count must not silently become a fractional measurement."""
    assert normalized_number(value) == expected


def test_a_fractional_string_is_accepted_where_a_measurement_is_expected() -> None:
    """Event timestamps arrive as fractional seconds."""
    assert normalized_float("1791035437.587") == 1791035437.587


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("catalog.gamepass.com", "catalog.gamepass.com", id="plain"),
        pytest.param("  spaced.example  ", "spaced.example", id="stripped"),
        pytest.param("", None, id="empty_is_absent"),
        pytest.param("   ", None, id="whitespace_is_absent"),
        pytest.param(42, None, id="non_string"),
        pytest.param(None, None, id="none"),
    ],
)
def test_strings_are_stripped_and_blanks_read_as_absent(
    value: object,
    expected: str | None,
) -> None:
    """An empty destination is absent, never an empty-named destination."""
    assert normalized_string(value) == expected
