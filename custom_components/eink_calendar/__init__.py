"""E-Ink Calendar: renders Home Assistant calendars + NOAA weather for a battery e-paper display."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import EinkCalendarCoordinator
from .views import async_register_views

type EinkCalendarConfigEntry = ConfigEntry[EinkCalendarCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EinkCalendarConfigEntry) -> bool:
    coordinator = EinkCalendarCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    async_register_views(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EinkCalendarConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: EinkCalendarConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


__all__ = ["DOMAIN"]
