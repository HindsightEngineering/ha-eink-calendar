"""End-to-end tests against a real Home Assistant core (pytest-homeassistant-custom-component).

Calendar fetching and NOAA are patched; everything else (config flow, setup,
publishing, HTTP views, entities) runs for real.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.eink_calendar.const import CONF_DEVICE_ID, CONF_TOKEN, DOMAIN  # noqa: E402
from custom_components.eink_calendar.core.model import CalEvent, DayForecast  # noqa: E402

TOKEN = "test-token-123"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _events():
    tz = dt_util.get_default_time_zone()
    today = dt_util.now().date()
    start = datetime.combine(today, time(18, 30), tz)
    return [
        CalEvent("Pizza night", start, start + timedelta(hours=1), False, "K"),
        CalEvent("Trip", today, today + timedelta(days=3), True),
    ]


def _forecast():
    today = dt_util.now().date()
    return {today + timedelta(days=i): DayForecast(today + timedelta(days=i), 70 + i, 50, "sun", "Sunny", None) for i in range(7)}


@pytest.fixture
def patched_sources():
    with (
        patch(
            "custom_components.eink_calendar.coordinator.EinkCalendarCoordinator._fetch_events",
            return_value=_events(),
        ),
        patch(
            "custom_components.eink_calendar.coordinator.async_get_forecast_url",
            return_value="https://api.weather.gov/gridpoints/SGX/1,1/forecast",
        ),
        patch(
            "custom_components.eink_calendar.coordinator.async_fetch_forecast",
            return_value=_forecast(),
        ),
    ):
        yield


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kitchen Calendar",
        unique_id="kitchen_calendar",
        data={"name": "Kitchen Calendar", CONF_DEVICE_ID: "kitchen_calendar", CONF_TOKEN: TOKEN},
        options={"calendars": ["calendar.family"], "tags": {"calendar.family": "F"}},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_creates_entry_with_token(hass: HomeAssistant, patched_sources) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Kitchen Calendar", "calendars": ["calendar.family", "calendar.kyle"]}
    )
    assert result["step_id"] == "tags"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tag_calendar.kyle": "Kyle"}
    )
    assert result["step_id"] == "finish"
    token = result["description_placeholders"]["token"]
    assert len(token) >= 20
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_ID] == "kitchen_calendar"
    assert result["data"][CONF_TOKEN] == token
    assert result["options"]["tags"] == {"calendar.kyle": "Kyl"}  # tags are capped at 3 characters


async def test_device_checkin_redraw_cycle(hass: HomeAssistant, hass_client_no_auth, patched_sources) -> None:
    await _setup(hass)
    client = await hass_client_no_auth()

    # wrong token / unknown device -> 404, no information leaked
    assert (await client.get("/api/eink_calendar/kitchen_calendar/status?token=nope")).status == 404
    assert (await client.get(f"/api/eink_calendar/other/status?token={TOKEN}")).status == 404

    # first wake: nothing shown yet -> redraw
    resp = await client.get(
        f"/api/eink_calendar/kitchen_calendar/status?token={TOKEN}&battery_v=3.95&rssi=-58&hash=&wake=boot"
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["redraw"] is True and body["hash"] and body["sleep_s"] >= 60 and body["stay_awake"] is False

    img = await client.get(f"/api/eink_calendar/kitchen_calendar/image.png?token={TOKEN}")
    assert img.status == 200 and img.headers["Content-Type"] == "image/png"
    png = await img.read()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    etag = img.headers["ETag"]
    assert (
        await client.get(f"/api/eink_calendar/kitchen_calendar/image.png?token={TOKEN}", headers={"If-None-Match": etag})
    ).status == 304

    # second wake with the drawn hash -> no redraw
    resp = await client.get(
        f"/api/eink_calendar/kitchen_calendar/status?token={TOKEN}&battery_v=3.94&hash={body['hash']}&wake=timer"
    )
    assert (await resp.json())["redraw"] is False

    # telemetry landed in entities
    battery = hass.states.get("sensor.kitchen_calendar_battery")
    assert battery is not None and int(battery.state) == round((3.94 - 3.27) / (4.15 - 3.27) * 100)
    assert hass.states.get("image.kitchen_calendar_calendar") is not None

    # republish button -> new hash -> device redraws next wake
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.kitchen_calendar_republish_now"}, blocking=True
    )
    resp = await client.get(
        f"/api/eink_calendar/kitchen_calendar/status?token={TOKEN}&hash={body['hash']}&wake=timer"
    )
    again = await resp.json()
    assert again["redraw"] is True and again["hash"] != body["hash"]

    # keep-awake switch is reported to the device
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.kitchen_calendar_keep_awake_for_update"}, blocking=True
    )
    resp = await client.get(f"/api/eink_calendar/kitchen_calendar/status?token={TOKEN}&hash={again['hash']}")
    assert (await resp.json())["stay_awake"] is True


async def test_options_flow_updates_and_clears(hass: HomeAssistant, patched_sources) -> None:
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "calendars": ["calendar.family"],
            "temperature_unit": "C",
            "first_weekday": "monday",
            "weeks": 4,
            "show_end_time": True,
            "wake_minutes": 20,
            "quiet_start": "22:00:00",
            "quiet_end": "06:30:00",
            "weather_redraw_hours": 2,
            "refresh_minutes": 5,
            "width": 1872,
            "height": 1404,
        },
    )
    assert result["step_id"] == "tags"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["weeks"] == 4 and entry.options["temperature_unit"] == "C"
    assert entry.options["tags"] == {}
    assert entry.options["waste_calendar"] is None
