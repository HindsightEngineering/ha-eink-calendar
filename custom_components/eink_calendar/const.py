"""Constants for the E-Ink Calendar integration."""

from __future__ import annotations

DOMAIN = "eink_calendar"
PLATFORMS = ["image", "sensor", "switch", "button"]

# config entry data (fixed for the life of the entry)
CONF_DEVICE_ID = "device_id"
CONF_TOKEN = "token"

# options (editable)
CONF_CALENDARS = "calendars"
CONF_WASTE_CALENDAR = "waste_calendar"
CONF_TAGS = "tags"
CONF_TEMP_UNIT = "temperature_unit"
CONF_FIRST_WEEKDAY = "first_weekday"
CONF_WEEKS = "weeks"
CONF_SHOW_END_TIME = "show_end_time"
CONF_TITLE = "title"
CONF_REFRESH_MINUTES = "refresh_minutes"
CONF_WAKE_MINUTES = "wake_minutes"
CONF_QUIET_START = "quiet_start"
CONF_QUIET_END = "quiet_end"
CONF_WEATHER_REDRAW_HOURS = "weather_redraw_hours"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_WIDTH = "width"
CONF_HEIGHT = "height"

DEFAULTS = {
    CONF_CALENDARS: [],
    CONF_WASTE_CALENDAR: None,
    CONF_TAGS: {},
    CONF_TEMP_UNIT: "F",
    CONF_FIRST_WEEKDAY: "sunday",
    CONF_WEEKS: 5,
    CONF_SHOW_END_TIME: False,
    CONF_TITLE: "",
    CONF_REFRESH_MINUTES: 10,
    CONF_WAKE_MINUTES: 30,
    CONF_QUIET_START: "23:00:00",
    CONF_QUIET_END: "06:00:00",
    CONF_WEATHER_REDRAW_HOURS: 3,
    CONF_WIDTH: 1872,
    CONF_HEIGHT: 1404,
}

WEATHER_REFRESH_MINUTES = 60  # NWS updates forecasts roughly hourly
WEATHER_STALE_HOURS = 6  # drop the forecast rather than show something this old

# reTerminal E1003 battery curve from Seeed's ESPHome cookbook (linear between these)
BATTERY_FULL_V = 4.15
BATTERY_EMPTY_V = 3.27

API_BASE_PATH = "/api/eink_calendar"
