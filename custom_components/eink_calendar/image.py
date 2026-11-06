"""Image entity: the published calendar, for previewing on a dashboard."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EinkCalendarConfigEntry
from .coordinator import EinkCalendarCoordinator
from .entity import EinkEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EinkCalendarConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([EinkCalendarImage(hass, entry.runtime_data)])


class EinkCalendarImage(EinkEntity, ImageEntity):
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, coordinator: EinkCalendarCoordinator) -> None:
        EinkEntity.__init__(self, coordinator, "calendar_image")
        ImageEntity.__init__(self, hass)
        self._sync()

    def _sync(self) -> None:
        pub = self.coordinator.published
        self._attr_image_last_updated = pub.published_at if pub else None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        return self.coordinator.png
