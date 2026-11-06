"""Vector icons drawn with Pillow primitives so they stay crisp at any size."""

from __future__ import annotations

import math

from PIL import ImageDraw

INK = 0
WHITE = 255
MID = 136  # mid grey, an exact 16-level step (8 * 17)


def _sun(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, w: int) -> None:
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INK, width=w)
    for i in range(8):
        a = math.pi / 4 * i
        x1, y1 = cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45
        x2, y2 = cx + math.cos(a) * r * 1.95, cy + math.sin(a) * r * 1.95
        d.line([x1, y1, x2, y2], fill=INK, width=w)


def _cloud(d: ImageDraw.ImageDraw, x: float, y: float, s: float, w: int, fill: int = WHITE) -> None:
    """Cloud occupying roughly the box (x, y)-(x+s, y+0.62s)."""
    base = y + s * 0.62
    parts = [
        (x + s * 0.05, y + s * 0.28, x + s * 0.45, base),
        (x + s * 0.25, y + s * 0.05, x + s * 0.70, y + s * 0.50),
        (x + s * 0.52, y + s * 0.22, x + s * 0.95, base),
    ]
    for box in parts:
        d.ellipse(box, fill=INK)
    d.rectangle([x + s * 0.25, y + s * 0.40, x + s * 0.75, base], fill=INK)
    if fill != INK:
        inset = w
        for box in parts:
            d.ellipse([box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset], fill=fill)
        d.rectangle([x + s * 0.25, y + s * 0.40 + inset, x + s * 0.75, base - inset], fill=fill)


def draw_weather_icon(d: ImageDraw.ImageDraw, key: str | None, x: float, y: float, s: float) -> None:
    """Draw a weather icon in the square (x, y, s)."""
    w = max(2, round(s / 14))
    key = key or "cloudy"
    if key == "sun":
        _sun(d, x + s / 2, y + s / 2, s * 0.22, w)
    elif key == "partly":
        _sun(d, x + s * 0.36, y + s * 0.36, s * 0.15, w)
        _cloud(d, x + s * 0.22, y + s * 0.34, s * 0.78, w)
    elif key == "cloudy":
        _cloud(d, x, y + s * 0.18, s, w)
    elif key == "rain":
        _cloud(d, x, y + s * 0.02, s, w)
        for i in range(3):
            cx = x + s * (0.28 + 0.22 * i)
            d.line([cx, y + s * 0.74, cx - s * 0.07, y + s * 0.96], fill=INK, width=w)
    elif key == "thunder":
        _cloud(d, x, y + s * 0.02, s, w)
        bolt = [
            (x + s * 0.55, y + s * 0.62),
            (x + s * 0.40, y + s * 0.82),
            (x + s * 0.52, y + s * 0.82),
            (x + s * 0.44, y + s * 1.0),
            (x + s * 0.66, y + s * 0.76),
            (x + s * 0.54, y + s * 0.76),
            (x + s * 0.62, y + s * 0.62),
        ]
        d.polygon(bolt, fill=INK)
    elif key == "snow":
        _cloud(d, x, y + s * 0.02, s, w)
        for i in range(3):
            cx, cy, r = x + s * (0.28 + 0.22 * i), y + s * 0.86, s * 0.07
            for a in (0, 60, 120):
                rad = math.radians(a)
                d.line(
                    [cx - math.cos(rad) * r, cy - math.sin(rad) * r, cx + math.cos(rad) * r, cy + math.sin(rad) * r],
                    fill=INK,
                    width=max(1, w - 1),
                )
    elif key == "fog":
        for i in range(4):
            yy = y + s * (0.25 + 0.17 * i)
            inset = s * (0.05 if i % 2 == 0 else 0.15)
            d.line([x + inset, yy, x + s - inset, yy], fill=INK, width=w)
    elif key == "wind":
        for i, length in enumerate((0.75, 0.9, 0.6)):
            yy = y + s * (0.3 + 0.2 * i)
            d.line([x + s * 0.05, yy, x + s * length, yy], fill=INK, width=w)
            r = s * 0.08
            d.arc([x + s * length - r, yy - 2 * r, x + s * length + r, yy], start=270, end=90, fill=INK, width=w)
    else:
        _cloud(d, x, y + s * 0.18, s, w)


def draw_bin_icon(d: ImageDraw.ImageDraw, key: str, x: float, y: float, s: float) -> None:
    """Waste-collection glyphs: filled can (trash), outlined can + arrows (recycle), leaf (green)."""
    w = max(2, round(s / 12))
    if key == "green":
        d.ellipse([x + s * 0.15, y + s * 0.1, x + s * 0.85, y + s * 0.8], outline=INK, width=w)
        d.line([x + s * 0.2, y + s * 0.95, x + s * 0.75, y + s * 0.2], fill=INK, width=w)
        return
    # can body and lid
    d.rectangle([x + s * 0.12, y + s * 0.12, x + s * 0.88, y + s * 0.22], fill=INK)
    d.rectangle([x + s * 0.40, y + s * 0.02, x + s * 0.60, y + s * 0.12], fill=INK)
    body = [(x + s * 0.18, y + s * 0.26), (x + s * 0.82, y + s * 0.26), (x + s * 0.74, y + s * 0.98), (x + s * 0.26, y + s * 0.98)]
    if key == "recycle":
        d.polygon(body, outline=INK, width=w)
        # small triangle of chevrons
        cx, cy, r = x + s * 0.5, y + s * 0.63, s * 0.2
        pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in (-90, 30, 150)]
        d.polygon(pts, outline=INK, width=max(1, w - 1))
    else:
        d.polygon(body, fill=INK)
        for i in range(3):
            xx = x + s * (0.36 + 0.14 * i)
            d.line([xx, y + s * 0.36, xx, y + s * 0.88], fill=WHITE, width=max(1, w - 1))


def draw_battery(d: ImageDraw.ImageDraw, pct: int | None, x: float, y: float, h: float) -> float:
    """Battery outline with fill level; returns the drawn width."""
    w = h * 2.0
    lw = max(2, round(h / 10))
    d.rectangle([x, y, x + w, y + h], outline=INK, width=lw)
    d.rectangle([x + w, y + h * 0.3, x + w + h * 0.18, y + h * 0.7], fill=INK)
    if pct is not None:
        inner = (w - 4 * lw) * max(0, min(100, pct)) / 100
        if inner > 0:
            d.rectangle([x + 2 * lw, y + 2 * lw, x + 2 * lw + inner, y + h - 2 * lw], fill=INK)
    return w + h * 0.18
