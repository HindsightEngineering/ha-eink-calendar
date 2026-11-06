"""Device telemetry reported on each wake: battery, signal, check-in times."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EinkCalendarConfigEntry
from .coordinator import EinkCalendarCoordinator
from .entity import EinkEntity


@dataclass(frozen=True, kw_only=True)
class EinkSensorDescription(SensorEntityDescription):
    value: Callable[[EinkCalendarCoordinator], Any]
    restore_field: str | None = None  # Telemetry field to repopulate after an HA restart


SENSORS: tuple[EinkSensorDescription, ...] = (
    EinkSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda c: c.telemetry.battery_pct,
        restore_field="battery_pct",
    ),
    EinkSensorDescription(
        key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda c: c.telemetry.battery_v,
        restore_field="battery_v",
    ),
    EinkSensorDescription(
        key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda c: c.telemetry.rssi,
    ),
    EinkSensorDescription(
        key="last_checkin",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda c: c.telemetry.last_checkin,
        restore_field="last_checkin",
    ),
    EinkSensorDescription(
        key="next_wake",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda c: c.telemetry.next_wake,
    ),
    EinkSensorDescription(
        key="last_published",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda c: c.published.published_at if c.published else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EinkCalendarConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(EinkSensor(entry.runtime_data, d) for d in SENSORS)


class EinkSensor(EinkEntity, RestoreSensor):
    entity_description: EinkSensorDescription

    def __init__(self, coordinator: EinkCalendarCoordinator, description: EinkSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        field = self.entity_description.restore_field
        if field is None or getattr(self.coordinator.telemetry, field) is not None:
            return
        last = await self.async_get_last_sensor_data()
        if last is None or last.native_value is None:
            return
        value = last.native_value
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP and not isinstance(value, datetime):
            value = dt_util.parse_datetime(str(value))
        setattr(self.coordinator.telemetry, field, value)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator)

