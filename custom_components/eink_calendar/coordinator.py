"""Coordinator: gathers calendar events and NOAA weather, decides when to publish."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BATTERY_EMPTY_V,
    BATTERY_FULL_V,
    CONF_CALENDARS,
    CONF_FIRST_WEEKDAY,
    CONF_HEIGHT,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_REFRESH_MINUTES,
    CONF_SHOW_END_TIME,
    CONF_TAGS,
    CONF_TEMP_UNIT,
    CONF_TITLE,
    CONF_WAKE_MINUTES,
    CONF_WASTE_CALENDAR,
    CONF_WEATHER_REDRAW_HOURS,
    CONF_WEEKS,
    CONF_WIDTH,
    DEFAULTS,
    DOMAIN,
    WEATHER_REFRESH_MINUTES,
    WEATHER_STALE_HOURS,
)
from .core.layout import grid_days, parse_ha_events
from .core.model import DayForecast, RenderConfig, RenderData
from .core.noaa import NoaaError, async_fetch_forecast, async_get_forecast_url
from .core.policy import Published, content_hash, next_sleep_seconds, should_publish, weather_hash
from .core.render import render_png

_LOGGER = logging.getLogger(__name__)


@dataclass
class Telemetry:
    battery_v: float | None = None
    battery_pct: int | None = None
    rssi: int | None = None
    last_checkin: datetime | None = None
    last_wake_reason: str | None = None
    next_wake: datetime | None = None
    last_redraw: datetime | None = None


def battery_percent(volts: float | None) -> int | None:
    if volts is None:
        return None
    pct = (volts - BATTERY_EMPTY_V) / (BATTERY_FULL_V - BATTERY_EMPTY_V) * 100
    return int(round(max(0.0, min(100.0, pct))))


def _parse_time(value: Any, fallback: str) -> time:
    try:
        return time.fromisoformat(str(value or fallback))
    except ValueError:
        return time.fromisoformat(fallback)


class EinkCalendarCoordinator(DataUpdateCoordinator[None]):
    """Owns the published image and the device's telemetry."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(minutes=int(self.opt_static(entry, CONF_REFRESH_MINUTES))),
        )
        self.forecast: dict[date, DayForecast] = {}
        self._forecast_url: str | None = None
        self._forecast_fetched: datetime | None = None
        self._forecast_ok: datetime | None = None
        self.published: Published | None = None
        self.png: bytes | None = None
        self.telemetry = Telemetry()
        self.stay_awake = False
        self._force_publish = False
        self._lock = asyncio.Lock()

    # ----- options ---------------------------------------------------------

    @staticmethod
    def opt_static(entry: ConfigEntry, key: str) -> Any:
        return entry.options.get(key, DEFAULTS.get(key))

    def opt(self, key: str) -> Any:
        return self.opt_static(self.config_entry, key)

    def render_config(self) -> RenderConfig:
        return RenderConfig(
            width=int(self.opt(CONF_WIDTH)),
            height=int(self.opt(CONF_HEIGHT)),
            weeks=int(self.opt(CONF_WEEKS)),
            first_weekday=0 if self.opt(CONF_FIRST_WEEKDAY) == "monday" else 6,
            show_end_time=bool(self.opt(CONF_SHOW_END_TIME)),
            temp_unit=str(self.opt(CONF_TEMP_UNIT)),
            title=str(self.opt(CONF_TITLE) or ""),
        )

    @property
    def image_hash(self) -> str:
        return self.published.image_hash if self.published else ""

    # ----- update cycle ----------------------------------------------------

    async def _async_update_data(self) -> None:
        async with self._lock:
            tz = dt_util.get_default_time_zone()
            now = dt_util.now()
            cfg = self.render_config()
            events = await self._fetch_events(now.date(), cfg, tz)
            await self._refresh_weather(now)
            today = now.date()
            data = RenderData(
                today=today,
                events=events,
                forecast={d: f for d, f in self.forecast.items() if d >= today},
                battery_pct=self.telemetry.battery_pct,
            )
            force, self._force_publish = self._force_publish, False
            await self._maybe_publish(data, cfg, now, force)

    async def _fetch_events(self, today: date, cfg: RenderConfig, tz: Any) -> list:
        calendars: list[str] = list(self.opt(CONF_CALENDARS) or [])
        waste: str | None = self.opt(CONF_WASTE_CALENDAR) or None
        wanted = calendars + ([waste] if waste and waste not in calendars else [])
        entity_ids = [e for e in wanted if self.hass.states.get(e) is not None]
        missing = set(wanted) - set(entity_ids)
        if missing:
            _LOGGER.debug("Calendars not loaded yet: %s", ", ".join(sorted(missing)))
        if not entity_ids:
            return []
        days = grid_days(today, cfg.weeks, cfg.first_weekday)
        start = datetime.combine(days[0][0], time.min, tz)
        end = datetime.combine(days[-1][-1] + timedelta(days=1), time.min, tz)
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {"entity_id": entity_ids, "start_date_time": start.isoformat(), "end_date_time": end.isoformat()},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            raise UpdateFailed(f"calendar.get_events failed: {err}") from err
        return parse_ha_events(response or {}, tz, dict(self.opt(CONF_TAGS) or {}), waste)

    async def _refresh_weather(self, now: datetime) -> None:
        if self._forecast_fetched and now - self._forecast_fetched < timedelta(minutes=WEATHER_REFRESH_MINUTES):
            return
        self._forecast_fetched = now
        lat = self.opt(CONF_LATITUDE)
        lon = self.opt(CONF_LONGITUDE)
        lat = float(lat) if lat not in (None, "") else self.hass.config.latitude
        lon = float(lon) if lon not in (None, "") else self.hass.config.longitude
        session = async_get_clientsession(self.hass)
        try:
            if not self._forecast_url:
                self._forecast_url = await async_get_forecast_url(session, lat, lon)
            self.forecast = await async_fetch_forecast(session, self._forecast_url, str(self.opt(CONF_TEMP_UNIT)))
            self._forecast_ok = now
        except (NoaaError, aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("NOAA forecast unavailable, keeping the previous one: %s", err)
            self._forecast_url = None  # re-resolve the grid point next time
            if self._forecast_ok and now - self._forecast_ok > timedelta(hours=WEATHER_STALE_HOURS):
                self.forecast = {}

    async def _maybe_publish(self, data: RenderData, cfg: RenderConfig, now: datetime, force: bool) -> None:
        ch = content_hash(data, cfg)
        wh = weather_hash(data)
        gate = timedelta(hours=float(self.opt(CONF_WEATHER_REDRAW_HOURS)))
        prev = self.published
        if not should_publish(prev, ch, wh, now, gate, force):
            return
        data.published_at = now
        self.png = await self.hass.async_add_executor_job(render_png, data, cfg)
        weather_at = now if prev is None or wh != prev.weather_hash else prev.weather_published_at
        self.published = Published(ch, wh, now, weather_at)
        _LOGGER.debug("Published calendar image %s (%d bytes)", self.image_hash, len(self.png))

    async def async_force_publish(self) -> None:
        self._force_publish = True
        await self.async_refresh()

    # ----- device check-in -------------------------------------------------

    async def async_handle_checkin(
        self, battery_v: float | None, rssi: int | None, shown_hash: str, wake: str
    ) -> dict[str, Any]:
        now = dt_util.now()
        t = self.telemetry
        if battery_v is not None and 2.5 < battery_v < 5.0:
            t.battery_v = round(battery_v, 3)
            t.battery_pct = battery_percent(battery_v)
        t.rssi = rssi
        t.last_checkin = now
        t.last_wake_reason = wake

        if wake == "button":
            # The green button means "show me the latest now": refresh and republish.
            await self.async_force_publish()

        current = self.image_hash
        redraw = bool(current) and shown_hash != current
        if redraw:
            t.last_redraw = now
        sleep_s = next_sleep_seconds(
            now,
            timedelta(minutes=float(self.opt(CONF_WAKE_MINUTES))),
            _parse_time(self.opt(CONF_QUIET_START), DEFAULTS[CONF_QUIET_START]),
            _parse_time(self.opt(CONF_QUIET_END), DEFAULTS[CONF_QUIET_END]),
        )
        t.next_wake = now + timedelta(seconds=sleep_s)
        self.async_update_listeners()
        return {"hash": current, "redraw": redraw, "sleep_s": sleep_s, "stay_awake": self.stay_awake}
