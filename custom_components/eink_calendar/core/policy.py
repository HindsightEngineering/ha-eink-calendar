"""When to publish a new image, and how long the device should sleep.

Redraws are the expensive part of the power budget, so the image is only
republished when something the reader would notice has changed:

* calendar content, the date, the layout config, or the battery bucket
  -> publish now;
* weather only -> publish at most once every ``weather_min_interval``.

The device compares the hash it last drew with the published hash, so it
redraws exactly once per publish.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from .model import RenderConfig, RenderData


def _digest(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def battery_bucket(pct: int | None) -> int | None:
    """Round to 10 % so the header icon doesn't trigger a redraw on every wake."""
    return None if pct is None else int(round(pct / 10.0) * 10)


def content_hash(data: RenderData, cfg: RenderConfig) -> str:
    return _digest(
        {
            "today": data.today.isoformat(),
            "events": [e.fingerprint() for e in data.events],
            "cfg": cfg.fingerprint(),
            "battery": battery_bucket(data.battery_pct),
        }
    )


def weather_hash(data: RenderData) -> str:
    return _digest([f.fingerprint() for _, f in sorted(data.forecast.items())])


@dataclass
class Published:
    content_hash: str
    weather_hash: str
    published_at: datetime
    weather_published_at: datetime

    @property
    def image_hash(self) -> str:
        return _digest([self.content_hash, self.weather_hash, self.published_at.isoformat()])[:12]


def should_publish(
    prev: Published | None,
    content: str,
    weather: str,
    now: datetime,
    weather_min_interval: timedelta,
    force: bool = False,
) -> bool:
    if prev is None or force:
        return True
    if content != prev.content_hash:
        return True
    if weather != prev.weather_hash and now - prev.weather_published_at >= weather_min_interval:
        return True
    return False


def _in_quiet(t: time, start: time, end: time) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end  # window crosses midnight


def next_sleep_seconds(
    now: datetime,
    interval: timedelta,
    quiet_start: time | None = None,
    quiet_end: time | None = None,
) -> int:
    """Seconds until the device should next wake.

    * Inside quiet hours: sleep until quiet hours end.
    * Otherwise: the normal interval, but never past the start of quiet hours
      (so the night is one long sleep) and, when quiet hours are off, wake
      a couple of minutes after midnight for the date rollover.
    """
    t = now.timetz().replace(tzinfo=None)
    if quiet_start is not None and quiet_end is not None and _in_quiet(t, quiet_start, quiet_end):
        end_dt = now.replace(hour=quiet_end.hour, minute=quiet_end.minute, second=0, microsecond=0)
        if end_dt <= now:
            end_dt += timedelta(days=1)
        return max(60, int((end_dt - now).total_seconds()) + 30)

    candidates = [interval.total_seconds()]
    if quiet_start is not None and quiet_end is not None and quiet_start != quiet_end:
        qs = now.replace(hour=quiet_start.hour, minute=quiet_start.minute, second=0, microsecond=0)
        if qs <= now:
            qs += timedelta(days=1)
        # Wake once at the start of quiet hours; that wake then sleeps through the night.
        candidates.append((qs - now).total_seconds() + 30)
    else:
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=2, second=0, microsecond=0)
        candidates.append((midnight - now).total_seconds())
    return max(60, int(min(candidates)))
