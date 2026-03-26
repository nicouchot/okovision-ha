"""Sensor platform for Okovision."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_LAST_UPDATED, ATTR_SENSOR_ID, DOMAIN, MANUFACTURER
from .coordinator import OkovisionCoordinator

_LOGGER = logging.getLogger(__name__)

# Map from Okovision sensor type to HA SensorDeviceClass
DEVICE_CLASS_MAP: dict[str, SensorDeviceClass | None] = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "humidity": SensorDeviceClass.HUMIDITY,
    "co2": SensorDeviceClass.CO2,
    "pressure": SensorDeviceClass.ATMOSPHERIC_PRESSURE,
    "illuminance": SensorDeviceClass.ILLUMINANCE,
    "motion": None,
    "occupancy": None,
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
    "power": SensorDeviceClass.POWER,
    "energy": SensorDeviceClass.ENERGY,
    "battery": SensorDeviceClass.BATTERY,
}

STATE_CLASS_MAP: dict[str, SensorStateClass | None] = {
    "temperature": SensorStateClass.MEASUREMENT,
    "humidity": SensorStateClass.MEASUREMENT,
    "co2": SensorStateClass.MEASUREMENT,
    "pressure": SensorStateClass.MEASUREMENT,
    "illuminance": SensorStateClass.MEASUREMENT,
    "motion": None,
    "occupancy": None,
    "voltage": SensorStateClass.MEASUREMENT,
    "current": SensorStateClass.MEASUREMENT,
    "power": SensorStateClass.MEASUREMENT,
    "energy": SensorStateClass.TOTAL_INCREASING,
    "battery": SensorStateClass.MEASUREMENT,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Okovision sensors from a config entry."""
    coordinator: OkovisionCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        OkovisionSensorEntity(coordinator, sensor_id, entry)
        for sensor_id in coordinator.data
    )


class OkovisionSensorEntity(CoordinatorEntity[OkovisionCoordinator], SensorEntity):
    """Representation of an Okovision sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OkovisionCoordinator,
        sensor_id: str,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(coordinator)
        self._sensor_id = sensor_id
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{sensor_id}"

        sensor_data = coordinator.data[sensor_id]
        sensor_type = sensor_data.get("type", "")

        self._attr_device_class = DEVICE_CLASS_MAP.get(sensor_type)
        self._attr_state_class = STATE_CLASS_MAP.get(sensor_type)
        self._attr_native_unit_of_measurement = sensor_data.get("unit")
        self._attr_name = sensor_data.get("name", sensor_id)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{sensor_id}")},
            name=sensor_data.get("name", sensor_id),
            manufacturer=MANUFACTURER,
            model=sensor_data.get("model"),
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        sensor_data = self.coordinator.data.get(self._sensor_id)
        if sensor_data is None:
            return None
        return sensor_data.get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        sensor_data = self.coordinator.data.get(self._sensor_id, {})
        return {
            ATTR_SENSOR_ID: self._sensor_id,
            ATTR_LAST_UPDATED: sensor_data.get("last_updated"),
        }
