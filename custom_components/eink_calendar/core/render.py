"""Render the rolling multi-week calendar to a 16-level grayscale image.

Coordinates are tuned for the reTerminal E1003 (1872 x 1404) and scale with
the configured size, so other panels work if they are roughly 4:3.
"""

from __future__ import annotations

import io
from datetime import date
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .icons import INK, MID, WHITE, draw_battery, draw_bin_icon, draw_weather_icon
from .layout import allocate_lanes, bins_for, event_label, grid_days, time_label, timed_events_for
from .model import RenderConfig, RenderData

FONT_DIR = Path(__file__).parent / "fonts"
GRID = 170  # grid lines (10 * 17)
BAR_FILL = 221  # bar background (13 * 17)
PAST = 119  # text on past days (7 * 17)
WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_LONG = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
WEEKDAYS_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@lru_cache(maxsize=64)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    files = {
        "regular": "Inter-Regular.otf",
        "medium": "Inter-Medium.otf",
        "semibold": "Inter-SemiBold.otf",
        "bold": "Inter-Bold.otf",
        "serif": "Caladea-Bold.ttf",
    }
    return ImageFont.truetype(str(FONT_DIR / files[name]), size)


def quantize16(img: Image.Image) -> Image.Image:
    """Snap every pixel to one of the panel's 16 gray levels (multiples of 17)."""
    return img.point(lambda v: min(255, int(round(v / 17.0)) * 17))


def _text_w(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont) -> float:
    return d.textlength(text, font=f)


def _ellipsize(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: float) -> str:
    if _text_w(d, text, f) <= max_w:
        return text
    while text and _text_w(d, text + "…", f) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, first_w: float, next_w: float, max_lines: int) -> list[str]:
    """Greedy word wrap into at most ``max_lines`` lines; every line fits its width."""
    words = text.split()
    lines: list[str] = []
    while words and len(lines) < max_lines:
        width = first_w if not lines else next_w
        last = len(lines) == max_lines - 1
        cur = ""
        while words and _text_w(d, f"{cur} {words[0]}".strip(), f) <= width:
            cur = f"{cur} {words.pop(0)}".strip()
        if not cur:
            # The next word alone is wider than the line: break at a hyphen, else hard-cut.
            word = words.pop(0)
            head, sep, tail = word.partition("-")
            if sep and tail and _text_w(d, head + "-", f) <= width:
                cur = head + "-"
                words.insert(0, tail)
            else:
                cur = word
        if last and words:
            cur = f"{cur} {' '.join(words)}"
            words = []
        lines.append(_ellipsize(d, cur, f, width))
    return lines


class _Metrics:
    def __init__(self, cfg: RenderConfig) -> None:
        k = cfg.height / 1404.0
        self.k = k
        self.margin = round(28 * k)
        self.header_h = round(112 * k)
        self.weekday_h = round(44 * k)
        self.grid_top = self.margin + self.header_h + self.weekday_h
        self.grid_bottom = cfg.height - self.margin
        self.col_w = (cfg.width - 2 * self.margin) / 7
        self.row_h = (self.grid_bottom - self.grid_top) / cfg.weeks
        self.pad = round(10 * k)
        self.date_band = round(66 * k)
        self.lane_h = round(38 * k)
        self.line_h = round(33 * k)
        self.max_lanes = 2  # keep room for timed events; extra bars count toward "+N more"


def render_calendar(data: RenderData, cfg: RenderConfig) -> Image.Image:
    m = _Metrics(cfg)
    img = Image.new("L", (cfg.width, cfg.height), WHITE)
    d = ImageDraw.Draw(img)
    _draw_header(d, data, cfg, m)
    weeks = grid_days(data.today, cfg.weeks, cfg.first_weekday)
    _draw_weekday_row(d, weeks[0], cfg, m)
    _draw_grid(d, cfg, m)  # first, so multi-day bars run over the cell dividers
    for r, week in enumerate(weeks):
        _draw_week(d, r, week, data, cfg, m)
    _draw_today_frame(d, weeks, data.today, m)
    return quantize16(img)


def render_png(data: RenderData, cfg: RenderConfig) -> bytes:
    buf = io.BytesIO()
    render_calendar(data, cfg).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _draw_header(d: ImageDraw.ImageDraw, data: RenderData, cfg: RenderConfig, m: _Metrics) -> None:
    k = m.k
    t = data.today
    title = f"{WEEKDAYS_LONG[t.weekday()]}, {MONTHS_LONG[t.month - 1]} {t.day}, {t.year}"
    f_title = font("serif", round(70 * k))
    x = m.margin
    base_y = m.margin + round(8 * k)
    d.text((x, base_y), title, font=f_title, fill=INK)
    x += _text_w(d, title, f_title) + round(44 * k)

    fc = data.forecast.get(t)
    if fc is not None:
        icon_s = round(66 * k)
        draw_weather_icon(d, fc.icon, x, base_y + round(4 * k), icon_s)
        x += icon_s + round(18 * k)
        hi = f"{fc.high}°" if fc.high is not None else "—"
        lo = f"{fc.low}°" if fc.low is not None else "—"
        f_temp = font("semibold", round(46 * k))
        d.text((x, base_y + round(10 * k)), f"{hi} / {lo}", font=f_temp, fill=INK)
        x += _text_w(d, f"{hi} / {lo}", f_temp) + round(22 * k)
        short = fc.short + (f" · {fc.pop}% precip" if fc.pop else "")
        f_short = font("regular", round(30 * k))
        d.text((x, base_y + round(22 * k)), short, font=f_short, fill=MID)

    # right side: optional title, battery, publish time
    f_small = font("regular", round(24 * k))
    right = cfg.width - m.margin
    y = base_y + round(6 * k)
    stamp = ""
    if data.published_at is not None:
        stamp = f"Updated {time_label(data.published_at)}"
    if stamp:
        tw = _text_w(d, stamp, f_small)
        d.text((right - tw, y + round(44 * k)), stamp, font=f_small, fill=MID)
    bh = round(26 * k)
    label = f"{data.battery_pct}%" if data.battery_pct is not None else ""
    lw = _text_w(d, label, f_small)
    bw = bh * 2.18
    d.text((right - lw, y), label, font=f_small, fill=MID)
    draw_battery(d, data.battery_pct, right - lw - round(10 * k) - bw, y + round(2 * k), bh)
    if cfg.title:
        f_t = font("medium", round(28 * k))
        tw = _text_w(d, cfg.title, f_t)
        d.text((right - lw - bw - round(36 * k) - tw, y), cfg.title, font=f_t, fill=MID)


def _draw_weekday_row(d: ImageDraw.ImageDraw, week: list[date], cfg: RenderConfig, m: _Metrics) -> None:
    f = font("semibold", round(27 * m.k))
    y = m.margin + m.header_h + round(8 * m.k)
    for c, day in enumerate(week):
        label = WEEKDAYS[day.weekday()]
        cx = m.margin + m.col_w * c + m.col_w / 2
        d.text((cx - _text_w(d, label, f) / 2, y), label, font=f, fill=68)


def _cell_box(r: int, c: int, m: _Metrics) -> tuple[float, float, float, float]:
    x0 = m.margin + m.col_w * c
    y0 = m.grid_top + m.row_h * r
    return x0, y0, x0 + m.col_w, y0 + m.row_h


def _draw_week(d: ImageDraw.ImageDraw, r: int, week: list[date], data: RenderData, cfg: RenderConfig, m: _Metrics) -> None:
    k = m.k
    segments = allocate_lanes(week, data.events)
    visible = [s for s in segments if s.lane < m.max_lanes]
    hidden_bars = {c: 0 for c in range(7)}
    for s in segments:
        if s.lane >= m.max_lanes:
            for c in range(s.col_start, s.col_end + 1):
                hidden_bars[c] += 1

    for c, day in enumerate(week):
        _draw_cell_top(d, r, c, day, data, cfg, m, is_first=(r == 0 and c == 0))

    # bars
    f_bar = font("semibold", round(25 * k))
    for s in visible:
        x0, y0, _, _ = _cell_box(r, s.col_start, m)
        _, _, x1, _ = _cell_box(r, s.col_end, m)
        top = y0 + m.date_band + s.lane * m.lane_h
        left = x0 + (2 if s.continues_left else m.pad * 0.6)
        right = x1 - (2 if s.continues_right else m.pad * 0.6)
        past = s.event.last_date < data.today
        d.rounded_rectangle([left, top, right, top + m.lane_h - round(5 * k)], radius=round(6 * k), fill=BAR_FILL)
        text_x = left + round(8 * k)
        if s.event.tag:
            text_x = _draw_chip(d, s.event.tag, text_x, top + round(3 * k), m) + round(6 * k)
        label = ("‹ " if s.continues_left else "") + s.event.summary
        label = _ellipsize(d, label, f_bar, right - text_x - round(6 * k))
        d.text((text_x, top + round(2 * k)), label, font=f_bar, fill=PAST if past else INK)

    # timed events per day
    for c, day in enumerate(week):
        lanes_here = [s.lane for s in visible if s.col_start <= c <= s.col_end]
        top = _cell_box(r, c, m)[1] + m.date_band + (max(lanes_here) + 1 if lanes_here else 0) * m.lane_h
        _draw_timed(d, r, c, day, top, hidden_bars[c], data, cfg, m)


def _draw_chip(d: ImageDraw.ImageDraw, tag: str, x: float, y: float, m: _Metrics) -> float:
    f = font("bold", round(19 * m.k))
    w = _text_w(d, tag, f) + round(10 * m.k)
    h = round(26 * m.k)
    d.rounded_rectangle([x, y, x + w, y + h], radius=round(4 * m.k), fill=INK)
    d.text((x + round(5 * m.k), y + round(1 * m.k)), tag, font=f, fill=WHITE)
    return x + w


def _draw_cell_top(d: ImageDraw.ImageDraw, r: int, c: int, day: date, data: RenderData, cfg: RenderConfig, m: _Metrics, is_first: bool) -> None:
    k = m.k
    x0, y0, x1, _ = _cell_box(r, c, m)
    today = day == data.today
    past = day < data.today
    f_num = font("bold", round(40 * k))
    f_mon = font("semibold", round(28 * k))
    num = str(day.day)
    tx, ty = x0 + m.pad, y0 + round(8 * k)
    if day.day == 1 or is_first:
        mon = MONTHS[day.month - 1] + " "
        d.text((tx, ty + round(8 * k)), mon, font=f_mon, fill=PAST if past else INK)
        tx += _text_w(d, mon, f_mon)
    nw = _text_w(d, num, f_num)
    if today:
        d.rounded_rectangle(
            [tx - round(6 * k), ty - round(2 * k), tx + nw + round(6 * k), ty + round(46 * k)],
            radius=round(8 * k),
            fill=INK,
        )
        d.text((tx, ty - round(2 * k)), num, font=f_num, fill=WHITE)
    else:
        d.text((tx, ty - round(2 * k)), num, font=f_num, fill=PAST if past else INK)
    bx = tx + nw + round(12 * k)

    for icon in bins_for(day, data.events):
        draw_bin_icon(d, icon, bx, ty + round(4 * k), round(34 * k))
        bx += round(40 * k)

    fc = data.forecast.get(day)
    if fc is not None and not past:
        f_t = font("medium", round(26 * k))
        hi = f"{fc.high}°" if fc.high is not None else "—"
        lo = f"{fc.low}°" if fc.low is not None else "—"
        txt = f"{hi}/{lo}"
        tw = _text_w(d, txt, f_t)
        right = x1 - m.pad
        d.text((right - tw, ty), txt, font=f_t, fill=INK)
        s = round(40 * k)
        draw_weather_icon(d, fc.icon, right - tw - s - round(6 * k), ty - round(5 * k), s)
        if fc.pop and fc.pop >= 20:
            f_p = font("regular", round(21 * k))
            p = f"{fc.pop}%"
            d.text((right - _text_w(d, p, f_p), ty + round(32 * k)), p, font=f_p, fill=MID)


def _draw_timed(d: ImageDraw.ImageDraw, r: int, c: int, day: date, top: float, hidden: int, data: RenderData, cfg: RenderConfig, m: _Metrics) -> None:
    k = m.k
    x0, _, x1, y1 = _cell_box(r, c, m)
    past = day < data.today
    color = PAST if past else INK
    f_time = font("semibold", round(26 * k))
    f_text = font("regular", round(26 * k))
    left = x0 + m.pad
    width = x1 - m.pad - left
    bottom = y1 - round(6 * k)
    events = timed_events_for(day, data.events)
    y = top + round(3 * k)
    shown = 0
    for i, ev in enumerate(events):
        remaining_events = len(events) - i - 1 + hidden
        lines_left = int((bottom - y) // m.line_h)
        reserve = 1 if remaining_events else 0
        if lines_left - reserve < 1:
            break
        x = left
        if ev.tag:
            x = _draw_chip(d, ev.tag, x, y + round(3 * k), m) + round(5 * k)
        label = event_label(ev, cfg.show_end_time, day)
        if label.startswith("cont. "):
            time_part, text_part = "cont.", label[6:]
        else:
            time_part, _, text_part = label.partition(" ")
        d.text((x, y), time_part, font=f_time, fill=color)
        x += _text_w(d, time_part + " ", f_time)
        max_lines = min(2, lines_left - reserve)
        lines = _wrap(d, text_part, f_text, left + width - x, width - round(12 * k), max_lines)
        for j, line in enumerate(lines):
            lx = x if j == 0 else left + round(12 * k)
            d.text((lx, y), line, font=f_text, fill=color)
            y += m.line_h
        shown += 1
    more = len(events) - shown + hidden
    if more > 0:
        f_more = font("medium", round(23 * k))
        d.text((left, min(y, bottom - m.line_h)), f"+{more} more", font=f_more, fill=MID)


def _draw_grid(d: ImageDraw.ImageDraw, cfg: RenderConfig, m: _Metrics) -> None:
    w = max(2, round(2 * m.k))
    left, right = m.margin, cfg.width - m.margin
    for r in range(cfg.weeks + 1):
        y = m.grid_top + m.row_h * r
        d.line([left, y, right, y], fill=GRID, width=w)
    for c in range(8):
        x = m.margin + m.col_w * c
        d.line([x, m.grid_top, x, m.grid_bottom], fill=GRID, width=w)


def _draw_today_frame(d: ImageDraw.ImageDraw, weeks: list[list[date]], today: date, m: _Metrics) -> None:
    for r, week in enumerate(weeks):
        if today in week:
            x0, y0, x1, y1 = _cell_box(r, week.index(today), m)
            w = max(3, round(4 * m.k))
            d.rectangle([x0, y0, x1, y1], outline=INK, width=w)
            return
