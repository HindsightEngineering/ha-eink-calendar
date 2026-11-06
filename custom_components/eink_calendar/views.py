"""HTTP endpoints the display calls on each wake.

GET /api/eink_calendar/<device_id>/status?token=...&battery_v=4.01&rssi=-61&hash=<shown>&wake=timer
    -> {"hash": "...", "redraw": true, "sleep_s": 1800, "stay_awake": false}
GET /api/eink_calendar/<device_id>/image.png?token=...
    -> the published 16-level grayscale PNG

Both skip Home Assistant's login (the ESP32 can't do OAuth) and are instead
protected by a per-device random token. Unknown device or wrong token -> 404.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import API_BASE_PATH, CONF_DEVICE_ID, CONF_TOKEN, DOMAIN

if TYPE_CHECKING:
    from .coordinator import EinkCalendarCoordinator


def _find(hass: HomeAssistant, device_id: str, token: str | None) -> EinkCalendarCoordinator | None:
    if not token:
        return None
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        if entry.data.get(CONF_DEVICE_ID) == device_id and secrets.compare_digest(
            str(entry.data.get(CONF_TOKEN, "")), token
        ):
            return entry.runtime_data
    return None


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    f = _float(value)
    return int(f) if f is not None else None


class EinkStatusView(HomeAssistantView):
    url = API_BASE_PATH + "/{device_id}/status"
    name = "api:eink_calendar:status"
    requires_auth = False

    async def get(self, request: web.Request, device_id: str) -> web.Response:
        hass = request.app[KEY_HASS]
        coordinator = _find(hass, device_id, request.query.get("token"))
        if coordinator is None:
            return web.Response(status=404)
        wake = request.query.get("wake", "timer")
        if wake not in ("timer", "button", "boot", "awake"):
            wake = "timer"
        result = await coordinator.async_handle_checkin(
            battery_v=_float(request.query.get("battery_v")),
            rssi=_int(request.query.get("rssi")),
            shown_hash=request.query.get("hash", ""),
            wake=wake,
        )
        return self.json(result)


class EinkImageView(HomeAssistantView):
    url = API_BASE_PATH + "/{device_id}/image.png"
    name = "api:eink_calendar:image"
    requires_auth = False

    async def get(self, request: web.Request, device_id: str) -> web.Response:
        hass = request.app[KEY_HASS]
        coordinator = _find(hass, device_id, request.query.get("token"))
        if coordinator is None:
            return web.Response(status=404)
        if not coordinator.png:
            return web.Response(status=503, text="No image published yet")
        etag = f'"{coordinator.image_hash}"'
        headers = {"ETag": etag, "Cache-Control": "no-cache"}
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers=headers)
        return web.Response(body=coordinator.png, content_type="image/png", headers=headers)


@callback
def async_register_views(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("views_registered"):
        return
    hass.http.register_view(EinkStatusView())
    hass.http.register_view(EinkImageView())
    domain_data["views_registered"] = True
