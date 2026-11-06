#!/usr/bin/env python3
"""Render the calendar offline with sample data (or a live NOAA forecast).

    python3 tools/preview.py                         # sample events + sample weather
    python3 tools/preview.py --noaa 33.20,-117.24    # sample events + live NOAA forecast
    python3 tools/preview.py --out my.png --today 2026-11-06

Only Pillow is required (plus aiohttp for --noaa). Useful for tuning the
layout on a laptop before flashing anything.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "eink_calendar"))

from core.model import CalEvent, DayForecast, RenderConfig, RenderData  # noqa: E402
from core.render import render_calendar  # noqa: E402

TZ = ZoneInfo("America/Los_Angeles")


def _at(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm), TZ)


def sample_events(today: date) -> list[CalEvent]:
    start = today - timedelta(days=(today.weekday() + 1) % 7)  # Sunday of this week
    ev: list[CalEvent] = []

    def timed(offset: int, hh: int, mm: int, mins: int, text: str, tag: str = "") -> None:
        d = start + timedelta(days=offset)
        ev.append(CalEvent(text, _at(d, hh, mm), _at(d, hh, mm) + timedelta(minutes=mins), False, tag))

    def allday(offset: int, days: int, text: str, tag: str = "", bin_icon: str | None = None) -> None:
        d = start + timedelta(days=offset)
        ev.append(CalEvent(text, d, d + timedelta(days=days), True, tag, bin_icon=bin_icon))

    for week in range(5):
        base = week * 7
        timed(base + 1, 18, 30, 60, "Yoga", "K")
        timed(base + 2, 16, 0, 45, "Piano lesson", "S")
        timed(base + 2, 18, 0, 90, "Hockey practice", "S")
        allday(base + 4, 1, "Trash", bin_icon="trash")
        if week % 2 == 0:
            allday(base + 4, 1, "Recycling", bin_icon="recycle")
        timed(base + 5, 18, 30, 60, "Pizza night")
    timed(0, 10, 0, 90, "Farmers market")
    timed(0, 17, 0, 90, "Meal prep")
    timed(3, 9, 0, 60, "Oil change")
    timed(3, 12, 0, 60, "Team lunch", "K")
    timed(4, 15, 30, 30, "Parent-teacher conference")
    timed(4, 19, 0, 120, "Book club", "P")
    timed(6, 9, 0, 75, "Soccer game", "S")
    timed(6, 18, 30, 150, "Dinner with friends")
    timed(6, 19, 0, 60, "Movie night")
    timed(9, 13, 0, 45, "Haircut", "P")
    timed(10, 10, 0, 45, "Vet: shots")
    timed(11, 19, 30, 60, "Curling", "K")
    allday(12, 4, "Family trip to Banff")
    allday(13, 1, "Veterans Day observed")
    timed(17, 9, 0, 120, "Furnace service")
    timed(20, 14, 0, 120, "Holiday market")
    allday(25, 2, "Thanksgiving break", "S")
    timed(26, 11, 0, 90, "Brunch")
    timed(27, 13, 30, 120, "New Year countdown planning meeting with the extended family")
    return ev


def sample_forecast(today: date) -> dict[date, DayForecast]:
    data = [
        ("Sunny", "sun", 74, 52, None),
        ("Partly Cloudy", "partly", 71, 53, 10),
        ("Mostly Cloudy", "cloudy", 66, 54, 20),
        ("Chance Rain Showers", "rain", 62, 51, 60),
        ("Patchy Fog then Sunny", "fog", 68, 50, None),
        ("Breezy", "wind", 70, 49, None),
        ("Slight Chance Thunderstorms", "thunder", 64, 50, 30),
    ]
    return {
        today + timedelta(days=i): DayForecast(today + timedelta(days=i), hi, lo, icon, short, pop)
        for i, (short, icon, hi, lo, pop) in enumerate(data)
    }


async def live_forecast(latlon: str) -> dict[date, DayForecast]:
    import aiohttp

    from core.noaa import async_fetch_forecast, async_get_forecast_url

    lat, lon = (float(x) for x in latlon.split(","))
    async with aiohttp.ClientSession() as session:
        url = await async_get_forecast_url(session, lat, lon)
        return await async_fetch_forecast(session, url)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="preview.png")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--noaa", default=None, help="lat,lon for a live NWS forecast")
    ap.add_argument("--battery", type=int, default=82)
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else datetime.now(TZ).date()
    forecast = asyncio.run(live_forecast(args.noaa)) if args.noaa else sample_forecast(today)
    data = RenderData(
        today=today,
        events=sample_events(today),
        forecast=forecast,
        battery_pct=args.battery,
        published_at=_at(today, 8, 15),
    )
    img = render_calendar(data, RenderConfig())
    img.save(args.out)
    print(f"wrote {args.out} ({img.width}x{img.height}, {len(set(img.tobytes()))} gray levels)")


if __name__ == "__main__":
    main()
