"""Pure layout helpers: the rolling week grid, bar lanes, event parsing and labels."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Iterable

from .model import CalEvent

_BIN_RULES: list[tuple[str, str]] = [
    (r"recycl", "recycle"),
    (r"yard|green\s*waste|organics|compost|leaf", "green"),
    (r"trash|garbage|refuse|rubbish|bin", "trash"),
]


def grid_start(today: date, first_weekday: int = 6) -> date:
    """First day shown: the start of the week containing ``today``."""
    return today - timedelta(days=(today.weekday() - first_weekday) % 7)


def grid_days(today: date, weeks: int = 5, first_weekday: int = 6) -> list[list[date]]:
    start = grid_start(today, first_weekday)
    return [[start + timedelta(days=w * 7 + d) for d in range(7)] for w in range(weeks)]


def bin_icon_for(summary: str) -> str:
    text = summary.lower()
    for pattern, icon in _BIN_RULES:
        if re.search(pattern, text):
            return icon
    return "trash"


def _parse_dt(value: Any, tz: tzinfo) -> tuple[date | datetime, bool]:
    """Return (value, all_day). HA returns all-day bounds as 'YYYY-MM-DD'."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        return value, True
    else:
        text = str(value)
        if len(text) == 10:
            return date.fromisoformat(text), True
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz), False


def parse_ha_events(
    response: dict[str, Any],
    tz: tzinfo,
    tags: dict[str, str] | None = None,
    waste_calendar: str | None = None,
) -> list[CalEvent]:
    """Convert a ``calendar.get_events`` service response into CalEvents.

    ``response`` is ``{entity_id: {"events": [{"start", "end", "summary", ...}]}}``.
    Events from ``waste_calendar`` become bin icons instead of text.
    """
    tags = tags or {}
    out: list[CalEvent] = []
    seen: set[tuple[Any, ...]] = set()
    for entity_id, payload in response.items():
        for raw in (payload or {}).get("events", []):
            try:
                start, all_day = _parse_dt(raw["start"], tz)
                end, _ = _parse_dt(raw.get("end", raw["start"]), tz)
            except (KeyError, ValueError):
                continue
            if all_day and not isinstance(end, datetime) and end <= start:
                end = start + timedelta(days=1)  # type: ignore[operator]
            summary = (raw.get("summary") or "").strip() or "(busy)"
            is_waste = waste_calendar is not None and entity_id == waste_calendar
            ev = CalEvent(
                summary=summary,
                start=start,
                end=end,
                all_day=all_day,
                tag=tags.get(entity_id, ""),
                calendar=entity_id,
                bin_icon=bin_icon_for(summary) if is_waste else None,
            )
            # The same event shared to two subscribed calendars shows once.
            key = (ev.summary, ev.start, ev.end, ev.bin_icon)
            if key in seen:
                continue
            seen.add(key)
            out.append(ev)
    out.sort(key=lambda e: (e.start_date, not e.all_day, _sort_dt(e)))
    return out


def _sort_dt(ev: CalEvent) -> float:
    if ev.all_day:
        return 0.0
    return ev.start.timestamp()  # type: ignore[union-attr]


def time_label(dt: datetime) -> str:
    """Compact 12-hour label: '6:30p', '10a', '12p'."""
    hour = dt.hour % 12 or 12
    suffix = "a" if dt.hour < 12 else "p"
    return f"{hour}{suffix}" if dt.minute == 0 else f"{hour}:{dt.minute:02d}{suffix}"


def event_label(ev: CalEvent, show_end: bool = False, day: date | None = None) -> str:
    if ev.all_day or ev.is_bar:
        return ev.summary
    start: datetime = ev.start  # type: ignore[assignment]
    if day is not None and start.date() != day:
        return f"cont. {ev.summary}"
    label = time_label(start)
    if show_end:
        end: datetime = ev.end  # type: ignore[assignment]
        label = f"{label}-{time_label(end)}"
    return f"{label} {ev.summary}"


@dataclass(frozen=True)
class BarSegment:
    event: CalEvent
    col_start: int  # 0..6 within the week
    col_end: int  # inclusive
    lane: int
    continues_left: bool
    continues_right: bool


def allocate_lanes(week: list[date], events: Iterable[CalEvent]) -> list[BarSegment]:
    """Greedy lane assignment for bar events intersecting one week row.

    Longer bars and earlier starts get lower lanes so multi-day trips stay on
    top and continuous across days.
    """
    first, last = week[0], week[-1]
    segs: list[tuple[int, int, CalEvent, bool, bool]] = []
    for ev in events:
        if ev.bin_icon or not ev.is_bar:
            continue
        s, e = ev.start_date, ev.last_date
        if e < first or s > last:
            continue
        cs = max(s, first)
        ce = min(e, last)
        segs.append(((cs - first).days, (ce - first).days, ev, s < first, e > last))
    segs.sort(key=lambda t: (t[0], -(t[1] - t[0]), t[2].summary))
    lanes_end: list[int] = []
    out: list[BarSegment] = []
    for cs, ce, ev, cl, cr in segs:
        lane = next((i for i, end in enumerate(lanes_end) if end < cs), None)
        if lane is None:
            lane = len(lanes_end)
            lanes_end.append(ce)
        else:
            lanes_end[lane] = ce
        out.append(BarSegment(ev, cs, ce, lane, cl, cr))
    return out


def timed_events_for(day: date, events: Iterable[CalEvent]) -> list[CalEvent]:
    """Timed (non-bar, non-bin) events that occupy ``day``, in start order."""
    out = [
        ev
        for ev in events
        if not ev.bin_icon and not ev.is_bar and ev.start_date <= day <= ev.last_date
    ]
    out.sort(key=_sort_dt)
    return out


def bins_for(day: date, events: Iterable[CalEvent]) -> list[str]:
    icons: list[str] = []
    for ev in events:
        if ev.bin_icon and ev.start_date <= day <= ev.last_date and ev.bin_icon not in icons:
            icons.append(ev.bin_icon)
    return icons
