"""Data model shared by the renderer, the policy and the Home Assistant glue."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

# Icon keys understood by core.icons.draw_weather_icon
WEATHER_ICONS = ("sun", "partly", "cloudy", "rain", "thunder", "snow", "fog", "wind")
# Icon keys understood by core.icons.draw_bin_icon
BIN_ICONS = ("trash", "recycle", "green")


@dataclass(frozen=True)
class CalEvent:
    """One calendar event, normalised to local time.

    For all-day events ``start``/``end`` are dates and ``end`` is exclusive
    (as in iCalendar and Home Assistant). For timed events they are aware
    datetimes in the display's local time zone.
    """

    summary: str
    start: date | datetime
    end: date | datetime
    all_day: bool
    tag: str = ""  # short per-calendar label drawn as a chip, e.g. "K"
    calendar: str = ""  # source entity id, informational
    bin_icon: str | None = None  # set for waste-collection events

    @property
    def start_date(self) -> date:
        return self.start if self.all_day else self.start.date()  # type: ignore[union-attr]

    @property
    def last_date(self) -> date:
        """Last calendar day the event occupies (inclusive)."""
        if self.all_day:
            return self.end - timedelta(days=1)  # type: ignore[operator]
        end: datetime = self.end  # type: ignore[assignment]
        # An event ending exactly at midnight does not occupy the next day.
        return (end - timedelta(microseconds=1)).date() if end > self.start else end.date()

    @property
    def is_bar(self) -> bool:
        """Drawn as a horizontal bar: all-day events and timed events of 24 h or more."""
        if self.all_day:
            return True
        return (self.end - self.start) >= timedelta(hours=24)  # type: ignore[operator]

    def fingerprint(self) -> tuple[Any, ...]:
        return (
            self.summary,
            self.start.isoformat(),
            self.end.isoformat(),
            self.all_day,
            self.tag,
            self.bin_icon,
        )


@dataclass(frozen=True)
class DayForecast:
    """NOAA forecast for one local calendar day."""

    day: date
    high: int | None = None
    low: int | None = None
    icon: str | None = None
    short: str = ""
    pop: int | None = None  # max probability of precipitation, percent

    def fingerprint(self) -> tuple[Any, ...]:
        return (self.day.isoformat(), self.high, self.low, self.icon, self.pop)


@dataclass
class RenderConfig:
    width: int = 1872
    height: int = 1404
    weeks: int = 5
    first_weekday: int = 6  # 6 = Sunday, 0 = Monday (Python weekday numbering)
    show_end_time: bool = False
    temp_unit: str = "F"
    title: str = ""  # optional text drawn after the date in the header

    def fingerprint(self) -> tuple[Any, ...]:
        return (
            self.width,
            self.height,
            self.weeks,
            self.first_weekday,
            self.show_end_time,
            self.temp_unit,
            self.title,
        )


@dataclass
class RenderData:
    today: date
    events: list[CalEvent] = field(default_factory=list)
    forecast: dict[date, DayForecast] = field(default_factory=dict)
    battery_pct: int | None = None
    published_at: datetime | None = None
