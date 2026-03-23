"""Pure API boundary for Firewalla Local."""

from .client import FirewallaApiClient
from .exceptions import FirewallaApiError

__all__ = ["FirewallaApiClient", "FirewallaApiError"]
