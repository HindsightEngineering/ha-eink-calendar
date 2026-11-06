"""Keep-awake switch: holds the display awake at its next wake so it can take an OTA update."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EinkCalendarConfigEntry
from .entity import EinkEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EinkCalendarConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([EinkKeepAwake(entry.runtime_data, "keep_awake")])


class EinkKeepAwake(EinkEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return self.coordinator.stay_awake

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.stay_awake = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.stay_awake = False
        self.async_write_ha_state()
