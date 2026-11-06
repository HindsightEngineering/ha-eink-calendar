"""Republish button: re-render now; the display picks it up at its next wake."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EinkCalendarConfigEntry
from .entity import EinkEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EinkCalendarConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([EinkRepublish(entry.runtime_data, "republish")])


class EinkRepublish(EinkEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.coordinator.async_force_publish()
