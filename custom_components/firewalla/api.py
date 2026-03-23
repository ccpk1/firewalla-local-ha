"""API client scaffolding for Firewalla."""

from __future__ import annotations

from aiohttp import ClientSession

from .models import FirewallaSystemInfo


class FirewallaApiError(Exception):
    """Raise when the Firewalla API cannot be queried."""


class FirewallaApiClient:
    """Very small client scaffold for future Firewalla API work."""

    def __init__(self, session: ClientSession, host: str) -> None:
        """Initialize the client."""
        self._session = session
        self.host = host

    async def async_get_system_info(self) -> FirewallaSystemInfo:
        """Return placeholder system information.

        This intentionally avoids guessing the final Firewalla protocol. Replace
        this method first when wiring the real API.
        """
        return FirewallaSystemInfo(
            host=self.host,
            name="Firewalla",
            model=None,
            serial_number=None,
            software_version=None,
        )
