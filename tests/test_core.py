from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.layout import (
    allocate_lanes,
    bin_icon_for,
    grid_days,
    grid_start,
    parse_ha_events,
    time_label,
    timed_events_for,
)
from core.model import CalEvent, RenderConfig, RenderData
from core.noaa import icon_for, parse_periods
from core.policy import Published, content_hash, next_sleep_seconds, should_publish, weather_hash
from core.render import render_calendar

TZ = ZoneInfo("America/Los_Angeles")


def at(d: date, h: int, m: int = 0) -> datetime:
    return datetime.combine(d, time(h, m), TZ)


# --- layout -----------------------------------------------------------------

def test_grid_starts_on_sunday_and_covers_five_weeks():
    today = date(2026, 11, 6)  # Friday
    assert grid_start(today) == date(2026, 11, 1)
    assert grid_start(today, first_weekday=0) == date(2026, 11, 2)
    weeks = grid_days(today, 5)
    assert len(weeks) == 5 and all(len(w) == 7 for w in weeks)
    assert weeks[-1][-1] == date(2026, 12, 5)


def test_time_label():
    d = date(2026, 11, 6)
    assert time_label(at(d, 18, 30)) == "6:30p"
    assert time_label(at(d, 10)) == "10a"
    assert time_label(at(d, 0)) == "12a"
    assert time_label(at(d, 12)) == "12p"


def test_lanes_keep_multiday_bar_continuous_and_split_across_weeks():
    weeks = grid_days(date(2026, 11, 6), 5)
    trip = CalEvent("Trip", date(2026, 11, 13), date(2026, 11, 17), True)  # Fri-Mon
    single = CalEvent("Holiday", date(2026, 11, 14), date(2026, 11, 15), True)
    segs = allocate_lanes(weeks[1], [single, trip])
    by = {s.event.summary: s for s in segs}
    assert (by["Trip"].col_start, by["Trip"].col_end, by["Trip"].lane) == (5, 6, 0)
    assert by["Trip"].continues_right and not by["Trip"].continues_left
    assert by["Holiday"].lane == 1
    nxt = allocate_lanes(weeks[2], [trip])
    assert (nxt[0].col_start, nxt[0].col_end, nxt[0].continues_left) == (0, 1, True)


def test_long_timed_event_is_a_bar_short_one_is_not():
    d = date(2026, 11, 10)
    assert CalEvent("Conf", at(d, 9), at(d, 9) + timedelta(days=2), False).is_bar
    late = CalEvent("Late show", at(d, 22), at(d, 23, 30), False)
    assert not late.is_bar
    assert timed_events_for(d, [late]) == [late]


def test_parse_ha_events_tags_waste_and_dedupe():
    resp = {
        "calendar.family": {
            "events": [
                {"start": "2026-11-06T18:30:00-08:00", "end": "2026-11-06T19:30:00-08:00", "summary": "Pizza night"},
                {"start": "2026-11-13", "end": "2026-11-17", "summary": "Trip"},
            ]
        },
        "calendar.kyle": {
            "events": [
                {"start": "2026-11-06T18:30:00-08:00", "end": "2026-11-06T19:30:00-08:00", "summary": "Pizza night"},
            ]
        },
        "calendar.waste": {"events": [{"start": "2026-11-05", "end": "2026-11-06", "summary": "Recycling pickup"}]},
    }
    evs = parse_ha_events(resp, TZ, tags={"calendar.kyle": "K"}, waste_calendar="calendar.waste")
    assert len(evs) == 3  # duplicate pizza night collapsed
    waste = [e for e in evs if e.bin_icon]
    assert waste[0].bin_icon == "recycle"
    trip = next(e for e in evs if e.summary == "Trip")
    assert trip.all_day and trip.last_date == date(2026, 11, 16)


def test_bin_icons():
    assert bin_icon_for("Trash day") == "trash"
    assert bin_icon_for("Recycling") == "recycle"
    assert bin_icon_for("Green waste") == "green"


# --- NOAA -------------------------------------------------------------------

def test_noaa_periods_fold_into_days():
    periods = [
        {"startTime": "2026-11-06T18:00:00-08:00", "isDaytime": False, "temperature": 52, "temperatureUnit": "F",
         "shortForecast": "Mostly Clear", "probabilityOfPrecipitation": {"value": None}},
        {"startTime": "2026-11-07T06:00:00-08:00", "isDaytime": True, "temperature": 71, "temperatureUnit": "F",
         "shortForecast": "Chance Rain Showers", "probabilityOfPrecipitation": {"value": 40}},
        {"startTime": "2026-11-07T18:00:00-08:00", "isDaytime": False, "temperature": 50, "temperatureUnit": "F",
         "shortForecast": "Rain", "probabilityOfPrecipitation": {"value": 70}},
    ]
    days = parse_periods(periods)
    today = days[date(2026, 11, 6)]
    assert today.high is None and today.low == 52 and today.icon == "partly"
    sat = days[date(2026, 11, 7)]
    assert (sat.high, sat.low, sat.icon, sat.pop) == (71, 50, "rain", 70)
    assert parse_periods(periods, "C")[date(2026, 11, 7)].high == 22


def test_icon_rules_prefer_specific_matches():
    assert icon_for("Slight Chance Showers And Thunderstorms") == "thunder"
    assert icon_for("Partly Sunny") == "partly"
    assert icon_for("Mostly Cloudy") == "cloudy"
    assert icon_for("Sunny") == "sun"
    assert icon_for("Patchy Fog") == "fog"
    assert icon_for("Rain And Snow") == "snow"


# --- policy -----------------------------------------------------------------

def test_publish_policy_gates_weather_only_changes():
    now = at(date(2026, 11, 6), 12)
    prev = Published("c1", "w1", now - timedelta(hours=1), now - timedelta(hours=1))
    three_h = timedelta(hours=3)
    assert not should_publish(prev, "c1", "w1", now, three_h)
    assert should_publish(prev, "c2", "w1", now, three_h)  # calendar change: now
    assert not should_publish(prev, "c1", "w2", now, three_h)  # weather only, too soon
    assert should_publish(prev, "c1", "w2", now + timedelta(hours=2), three_h)
    assert should_publish(prev, "c1", "w1", now, three_h, force=True)
    assert should_publish(None, "c1", "w1", now, three_h)


def test_content_hash_ignores_small_battery_changes_and_changes_with_date():
    cfg = RenderConfig()
    a = RenderData(today=date(2026, 11, 6), battery_pct=81)
    b = RenderData(today=date(2026, 11, 6), battery_pct=83)
    c = RenderData(today=date(2026, 11, 7), battery_pct=81)
    assert content_hash(a, cfg) == content_hash(b, cfg)
    assert content_hash(a, cfg) != content_hash(c, cfg)
    assert weather_hash(a) == weather_hash(c)


def test_sleep_schedule():
    q0, q1 = time(23, 0), time(6, 0)
    day = date(2026, 11, 6)
    assert next_sleep_seconds(at(day, 12), timedelta(minutes=30), q0, q1) == 1800
    # 22:50 -> wake just after quiet hours begin, then sleep through
    assert next_sleep_seconds(at(day, 22, 50), timedelta(minutes=30), q0, q1) == 630
    # 23:10 -> sleep until 06:00 (+30 s)
    assert next_sleep_seconds(at(day, 23, 10), timedelta(minutes=30), q0, q1) == (6 * 60 + 50) * 60 + 30
    # 03:00 -> until 06:00
    assert next_sleep_seconds(at(day, 3), timedelta(minutes=30), q0, q1) == 3 * 3600 + 30
    # no quiet hours: wake after midnight for the date rollover
    assert next_sleep_seconds(at(day, 23, 50), timedelta(minutes=30), None, None) == 12 * 60


# --- render -----------------------------------------------------------------

def test_render_handles_crowded_days_and_uses_16_levels():
    d = date(2026, 11, 6)
    evs = [CalEvent(f"Event number {i} with a long name", at(d, 8 + i % 12), at(d, 9 + i % 12), False, "K")
           for i in range(12)]
    evs += [CalEvent(f"Bar {i}", d, d + timedelta(days=2), True) for i in range(5)]
    img = render_calendar(RenderData(today=d, events=evs, battery_pct=50), RenderConfig())
    assert img.size == (1872, 1404) and img.mode == "L"
    assert set(img.tobytes()) <= {i * 17 for i in range(16)}


def test_render_scales_to_other_sizes():
    img = render_calendar(RenderData(today=date(2026, 2, 1)), RenderConfig(width=1200, height=825, weeks=4))
    assert img.size == (1200, 825)
