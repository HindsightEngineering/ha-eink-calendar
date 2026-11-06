"""Config and options flow.

Setup: name + calendars -> per-calendar tags -> a final step that shows the
device ID and token to paste into the ESPHome secrets file.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    API_BASE_PATH,
    CONF_CALENDARS,
    CONF_DEVICE_ID,
    CONF_FIRST_WEEKDAY,
    CONF_HEIGHT,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_REFRESH_MINUTES,
    CONF_SHOW_END_TIME,
    CONF_TAGS,
    CONF_TEMP_UNIT,
    CONF_TITLE,
    CONF_TOKEN,
    CONF_WAKE_MINUTES,
    CONF_WASTE_CALENDAR,
    CONF_WEATHER_REDRAW_HOURS,
    CONF_WEEKS,
    CONF_WIDTH,
    DEFAULTS,
    DOMAIN,
)

TAG_PREFIX = "tag_"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "calendar"


def _cal_selector(multiple: bool) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="calendar", multiple=multiple))


def _num(lo: float, hi: float, step: float | str = 1, unit: str | None = None) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(min=lo, max=hi, step=step, mode=selector.NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _options_schema(current: dict[str, Any], advanced: bool) -> vol.Schema:
    def d(key: str) -> Any:
        return current.get(key, DEFAULTS.get(key))

    fields: dict[Any, Any] = {
        vol.Required(CONF_CALENDARS, default=d(CONF_CALENDARS)): _cal_selector(True),
        vol.Optional(CONF_WASTE_CALENDAR, description={"suggested_value": d(CONF_WASTE_CALENDAR)}): _cal_selector(False),
        vol.Required(CONF_TEMP_UNIT, default=d(CONF_TEMP_UNIT)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=["F", "C"], translation_key=CONF_TEMP_UNIT)
        ),
        vol.Required(CONF_FIRST_WEEKDAY, default=d(CONF_FIRST_WEEKDAY)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=["sunday", "monday"], translation_key=CONF_FIRST_WEEKDAY)
        ),
        vol.Required(CONF_WEEKS, default=d(CONF_WEEKS)): _num(3, 6),
        vol.Required(CONF_SHOW_END_TIME, default=d(CONF_SHOW_END_TIME)): selector.BooleanSelector(),
        vol.Optional(CONF_TITLE, description={"suggested_value": d(CONF_TITLE)}): selector.TextSelector(),
        vol.Required(CONF_WAKE_MINUTES, default=d(CONF_WAKE_MINUTES)): _num(5, 240, unit="min"),
        vol.Required(CONF_QUIET_START, default=d(CONF_QUIET_START)): selector.TimeSelector(),
        vol.Required(CONF_QUIET_END, default=d(CONF_QUIET_END)): selector.TimeSelector(),
        vol.Required(CONF_WEATHER_REDRAW_HOURS, default=d(CONF_WEATHER_REDRAW_HOURS)): _num(0, 24, 0.5, "h"),
    }
    if advanced:
        fields.update(
            {
                vol.Required(CONF_REFRESH_MINUTES, default=d(CONF_REFRESH_MINUTES)): _num(2, 60, unit="min"),
                vol.Optional(CONF_LATITUDE, description={"suggested_value": d(CONF_LATITUDE)}): _num(-90, 90, "any"),
                vol.Optional(CONF_LONGITUDE, description={"suggested_value": d(CONF_LONGITUDE)}): _num(-180, 180, "any"),
                vol.Required(CONF_WIDTH, default=d(CONF_WIDTH)): _num(400, 3000),
                vol.Required(CONF_HEIGHT, default=d(CONF_HEIGHT)): _num(300, 3000),
            }
        )
    return vol.Schema(fields)


def _tags_schema(calendars: list[str], tags: dict[str, str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(TAG_PREFIX + cal, description={"suggested_value": tags.get(cal, "")}): selector.TextSelector()
            for cal in calendars
        }
    )


def _collect_tags(user_input: dict[str, Any]) -> dict[str, str]:
    return {
        key[len(TAG_PREFIX):]: str(val).strip()[:3]
        for key, val in user_input.items()
        if key.startswith(TAG_PREFIX) and str(val or "").strip()
    }


def _normalise(options: dict[str, Any]) -> dict[str, Any]:
    out = dict(options)
    for key in (CONF_WEEKS, CONF_WAKE_MINUTES, CONF_REFRESH_MINUTES, CONF_WIDTH, CONF_HEIGHT):
        if key in out and out[key] is not None:
            out[key] = int(out[key])
    out[CONF_WASTE_CALENDAR] = out.get(CONF_WASTE_CALENDAR) or None
    return out


class EinkCalendarConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._name = ""
        self._options: dict[str, Any] = {}
        self._token = secrets.token_urlsafe(18)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._name = user_input.pop(CONF_NAME).strip()
            await self.async_set_unique_id(_slug(self._name))
            self._abort_if_unique_id_configured()
            if not user_input.get(CONF_CALENDARS):
                errors[CONF_CALENDARS] = "no_calendars"
            else:
                self._options = _normalise(user_input)
                return await self.async_step_tags()
        schema = vol.Schema({vol.Required(CONF_NAME, default="Kitchen Calendar"): str}).extend(
            _options_schema(self._options, advanced=False).schema
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_tags(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._options[CONF_TAGS] = _collect_tags(user_input)
            return await self.async_step_finish()
        return self.async_show_form(step_id="tags", data_schema=_tags_schema(self._options[CONF_CALENDARS], {}))

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        device_id = _slug(self._name)
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={CONF_NAME: self._name, CONF_DEVICE_ID: device_id, CONF_TOKEN: self._token},
                options=self._options,
            )
        return self.async_show_form(
            step_id="finish",
            data_schema=vol.Schema({}),
            description_placeholders={
                "device_id": device_id,
                "token": self._token,
                "path": f"{API_BASE_PATH}/{device_id}/status",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EinkCalendarOptionsFlow()


class EinkCalendarOptionsFlow(OptionsFlow):
    def __init__(self) -> None:
        self._options: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = dict(self.config_entry.options)
        if user_input is not None:
            # Optional fields left blank are absent from user_input; clear them explicitly.
            cleared = {k: None for k in (CONF_WASTE_CALENDAR, CONF_TITLE, CONF_LATITUDE, CONF_LONGITUDE)}
            self._options = {**current, **cleared, **_normalise(user_input)}
            return await self.async_step_tags()
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(current, advanced=True),
            description_placeholders={
                "device_id": self.config_entry.data[CONF_DEVICE_ID],
                "token": self.config_entry.data[CONF_TOKEN],
            },
        )

    async def async_step_tags(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._options[CONF_TAGS] = _collect_tags(user_input)
            return self.async_create_entry(data=self._options)
        return self.async_show_form(
            step_id="tags",
            data_schema=_tags_schema(self._options[CONF_CALENDARS], dict(self._options.get(CONF_TAGS) or {})),
        )
