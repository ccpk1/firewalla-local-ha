"""Custom API exceptions for Firewalla Local."""

from __future__ import annotations


class FirewallaApiError(Exception):
    """Base error for Firewalla Local API failures."""


class FirewallaAuthError(FirewallaApiError):
    """Raise when Firewalla authentication fails."""


class FirewallaConnectionError(FirewallaApiError):
    """Raise when Firewalla cannot be reached over the network."""


class FirewallaProtocolError(FirewallaApiError):
    """Raise when Firewalla returns an unexpected protocol payload."""


class FirewallaPairingTimeoutError(FirewallaProtocolError):
    """Raise when cloud pairing does not surface credentials before timing out."""


class FirewallaValidationError(FirewallaApiError):
    """Raise when user-supplied Firewalla input is invalid."""
