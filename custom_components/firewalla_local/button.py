"""Button platform for Firewalla Local device actions."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ENTITY_SUFFIX_BUTTON,
    LOGGER,
    TRANS_KEY_ENTITY_BUTTON_SYNC_RUNTIME,
    TRANS_KEY_PURPOSE_RUNTIME_SYNC_BUTTON,
)
from .coordinator import FirewallaConfigEntry
from .entity import FirewallaEntity

PARALLEL_UPDATES = 0

_SYNC_RUNTIME_OBJECT_ID = "sync_runtime"


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: FirewallaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Firewalla Local buttons from a config entry."""
    del _hass
    async_add_entities([FirewallaSyncRuntimeButton(entry)])


class FirewallaSyncRuntimeButton(FirewallaEntity, ButtonEntity):
    """Allow users to refresh Firewalla runtime data on demand."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = TRANS_KEY_ENTITY_BUTTON_SYNC_RUNTIME

    def press(self) -> None:
        """Provide the sync fallback required by the button entity contract."""
        raise NotImplementedError

    def __init__(self, entry: FirewallaConfigEntry) -> None:
        """Initialize the runtime sync button."""
        super().__init__(entry, entry.runtime_data.coordinator)
        self._attr_unique_id = self.integration_manager.build_entity_unique_id(
            object_id=_SYNC_RUNTIME_OBJECT_ID,
            suffix=ENTITY_SUFFIX_BUTTON,
        )

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return bounded button metadata attributes."""
        return self.build_state_attributes(TRANS_KEY_PURPOSE_RUNTIME_SYNC_BUTTON)

    async def async_press(self) -> None:
        """Request an immediate coordinator refresh."""
        LOGGER.info("Manual runtime sync requested for %s", self._entry.title)
        await self.coordinator.async_request_refresh()
        LOGGER.info(
            "Manual runtime sync completed for %s at %s",
            self._entry.title,
            self.coordinator.last_runtime_data_updated_at.isoformat()
            if self.coordinator.last_runtime_data_updated_at is not None
            else "unknown",
        )
