"""Client scaffolding for the Firewalla Local API boundary."""

from __future__ import annotations

from aiohttp import ClientSession

from ..models import FirewallaSystemInfo


class FirewallaApiClient:
    """Very small client scaffold for future Firewalla Local API work."""

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
            name="Firewalla Local",
            model=None,
            serial_number=None,
            software_version=None,
        )
