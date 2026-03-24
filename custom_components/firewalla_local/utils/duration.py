"""Duration parsing helpers for Firewalla Local."""

from __future__ import annotations

import re
from typing import Final

_DURATION_PART: Final = re.compile(r"(\d+)\s*([smhd])", re.IGNORECASE)
_UNIT_SECONDS: Final = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}
_ERROR_DURATION_EMPTY: Final = "Duration cannot be empty"
_ERROR_DURATION_UNSUPPORTED_TEXT: Final = "Duration contains unsupported text"
_ERROR_DURATION_NON_POSITIVE: Final = "Duration must be greater than zero"


def parse_duration_to_seconds(duration: str) -> int:
    """Parse a user-facing duration string into whole seconds."""
    normalized = duration.strip().lower()
    if not normalized:
        raise ValueError(_ERROR_DURATION_EMPTY)

    position = 0
    total_seconds = 0
    for match in _DURATION_PART.finditer(normalized):
        if normalized[position : match.start()].strip():
            raise ValueError(_ERROR_DURATION_UNSUPPORTED_TEXT)

        value = int(match.group(1))
        unit = match.group(2)
        total_seconds += value * _UNIT_SECONDS[unit]
        position = match.end()

    if normalized[position:].strip():
        raise ValueError(_ERROR_DURATION_UNSUPPORTED_TEXT)
    if total_seconds <= 0:
        raise ValueError(_ERROR_DURATION_NON_POSITIVE)

    return total_seconds
