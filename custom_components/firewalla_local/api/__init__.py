"""Pure API boundary for Firewalla Local."""

from . import auth, crypto
from .client import FirewallaApiClient
from .exceptions import (
    FirewallaApiError,
    FirewallaAuthError,
    FirewallaConnectionError,
    FirewallaProtocolError,
    FirewallaValidationError,
)

async_provision_firewalla_credentials = auth.async_provision_firewalla_credentials
generate_firewalla_keys = crypto.generate_firewalla_keys
load_qr_json = auth.load_qr_json

__all__ = [
    "FirewallaApiClient",
    "FirewallaApiError",
    "FirewallaAuthError",
    "FirewallaConnectionError",
    "FirewallaProtocolError",
    "FirewallaValidationError",
    "async_provision_firewalla_credentials",
    "generate_firewalla_keys",
    "load_qr_json",
]
