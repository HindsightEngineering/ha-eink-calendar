"""NOAA / National Weather Service forecast client (api.weather.gov).

The NWS API needs no key but does require a User-Agent that identifies the
application. The flow is two requests:

1. ``GET /points/{lat},{lon}`` returns the forecast office grid and the URL of
   the 12-hour period forecast for that point (cached; it rarely changes).
2. ``GET {forecast url}`` returns ~14 alternating day/night periods (about
   seven days), which ``parse_periods`` folds into one ``DayForecast`` per
   local calendar day.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from .model import DayForecast

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.weather.gov"
USER_AGENT = "ha-eink-calendar (https://github.com/HindsightEngineering/ha-eink-calendar)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}

# Order matters: the first pattern that matches the NWS shortForecast wins.
_ICON_RULES: list[tuple[str, str]] = [
    (r"thunder|t-storm", "thunder"),
    (r"snow|flurr|sleet|blizzard|ice pellets|freezing", "snow"),
    (r"rain|shower|drizzle", "rain"),
    (r"fog|haze|smoke|dust|mist", "fog"),
    (r"partly|mostly sunny|mostly clear|few clouds|scattered clouds", "partly"),
    (r"cloud|overcast", "cloudy"),
    (r"wind|breezy|blustery|gust", "wind"),
    (r"sunny|clear|fair|hot", "sun"),
]


class NoaaError(Exception):
    """Raised when the NWS API returns an unusable response."""


def icon_for(short_forecast: str) -> str:
    text = (short_forecast or "").lower()
    for pattern, icon in _ICON_RULES:
        if re.search(pattern, text):
            return icon
    return "cloudy"


def _to_unit(value: float | int | None, from_unit: str, to_unit: str) -> int | None:
    if value is None:
        return None
    if from_unit == to_unit:
        return round(value)
    if from_unit == "F" and to_unit == "C":
        return round((value - 32) * 5 / 9)
    if from_unit == "C" and to_unit == "F":
        return round(value * 9 / 5 + 32)
    return round(value)


def parse_periods(periods: list[dict[str, Any]], unit: str = "F") -> dict[date, DayForecast]:
    """Fold NWS 12-hour periods into one forecast per local day.

    * Daytime period on day D -> high, icon and short text for D.
    * Night period starting on day D -> low for D (the night that follows D).
    * When the forecast is fetched in the evening the first period is
      "Tonight", so today gets a low but no high; the icon then comes from the
      night period.
    * Precipitation chance is the max of the day's periods.
    """
    days: dict[date, dict[str, Any]] = {}
    for period in periods:
        try:
            start = datetime.fromisoformat(period["startTime"])
        except (KeyError, ValueError):
            continue
        day = start.date()
        rec = days.setdefault(day, {"high": None, "low": None, "icon": None, "short": "", "pop": None})
        temp = _to_unit(period.get("temperature"), period.get("temperatureUnit", "F"), unit)
        short = period.get("shortForecast") or ""
        pop_obj = period.get("probabilityOfPrecipitation") or {}
        pop = pop_obj.get("value") if isinstance(pop_obj, dict) else None
        if pop is not None:
            rec["pop"] = max(rec["pop"] or 0, int(pop))
        if period.get("isDaytime", True):
            rec["high"] = temp
            rec["icon"] = icon_for(short)
            rec["short"] = short
        else:
            rec["low"] = temp
            if rec["icon"] is None:
                rec["icon"] = icon_for(short)
                rec["short"] = short
    return {
        day: DayForecast(day=day, high=r["high"], low=r["low"], icon=r["icon"], short=r["short"], pop=r["pop"])
        for day, r in sorted(days.items())
    }


async def _get_json(session: Any, url: str) -> dict[str, Any]:
    async with session.get(url, headers=HEADERS, timeout=20) as resp:
        if resp.status != 200:
            raise NoaaError(f"NWS {url} returned HTTP {resp.status}")
        return await resp.json(content_type=None)


async def async_get_forecast_url(session: Any, latitude: float, longitude: float) -> str:
    data = await _get_json(session, f"{API_BASE}/points/{latitude:.4f},{longitude:.4f}")
    try:
        return data["properties"]["forecast"]
    except (KeyError, TypeError) as err:
        raise NoaaError("NWS /points response had no forecast URL (location outside the US?)") from err


async def async_fetch_forecast(session: Any, forecast_url: str, unit: str = "F") -> dict[date, DayForecast]:
    data = await _get_json(session, forecast_url)
    try:
        periods = data["properties"]["periods"]
    except (KeyError, TypeError) as err:
        raise NoaaError("NWS forecast response had no periods") from err
    return parse_periods(periods, unit)
