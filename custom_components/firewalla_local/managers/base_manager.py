"""Base manager primitives for Firewalla Local."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..api import FirewallaApiClient

if TYPE_CHECKING:
    from ..coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator


class FirewallaBaseManager:
    """Base class for entry-scoped manager objects."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        entry: FirewallaConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the manager."""
        self.coordinator = coordinator
        self.entry = entry
        self.client = client
