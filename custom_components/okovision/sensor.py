"""Plateforme sensor OkoVision – capteurs live (silo/cendrier) et daily (J-1 confirmé)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfMass, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BASE_URL, DOMAIN, MANUFACTURER
from .coordinator import OkovisionDailyCoordinator, OkovisionLiveCoordinator


# ── Descriptions ─────────────────────────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class OkovisionSensorDescription(SensorEntityDescription):
    """Description étendue avec clé dans coordinator.data."""
    data_key: str


# Capteurs live – silo et cendrier (mis à jour toutes les N secondes)
LIVE_SENSORS: tuple[OkovisionSensorDescription, ...] = (
    OkovisionSensorDescription(
        key="silo_remains_kg",
        data_key="silo_remains_kg",
        name="Silo – Pellets restants",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:silo",
    ),
    OkovisionSensorDescription(
        key="silo_capacity_kg",
        data_key="silo_capacity_kg",
        name="Silo – Capacité totale",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:silo-outline",
    ),
    OkovisionSensorDescription(
        key="silo_percent",
        data_key="silo_percent",
        name="Silo – Niveau",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        icon="mdi:gauge",
    ),
    OkovisionSensorDescription(
        key="silo_last_fill",
        data_key="silo_last_fill",
        name="Silo – Dernier remplissage",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-arrow-right",
    ),
    OkovisionSensorDescription(
        key="ashtray_remains_kg",
        data_key="ashtray_remains_kg",
        name="Cendrier – Capacité restante",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:trash-can-outline",
    ),
    OkovisionSensorDescription(
        key="ashtray_capacity_kg",
        data_key="ashtray_capacity_kg",
        name="Cendrier – Capacité totale",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:trash-can",
        entity_registry_enabled_default=False,
    ),
    OkovisionSensorDescription(
        key="ashtray_percent",
        data_key="ashtray_percent",
        name="Cendrier – Niveau de remplissage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        icon="mdi:gauge",
    ),
    OkovisionSensorDescription(
        key="ashtray_last_empty",
        data_key="ashtray_last_empty",
        name="Cendrier – Dernier vidage",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-arrow-left",
    ),
    OkovisionSensorDescription(
        key="last_sweep",
        data_key="last_sweep",
        name="Dernier ramonage",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:brush",
    ),
    OkovisionSensorDescription(
        key="last_maintenance",
        data_key="last_maintenance",
        name="Dernière maintenance",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:wrench-clock",
    ),
)

# Capteurs daily – données J-1 confirmées (mis à jour 1×/jour après 5h)
DAILY_SENSORS: tuple[OkovisionSensorDescription, ...] = (
    OkovisionSensorDescription(
        key="tc_ext_max",
        data_key="tc_ext_max",
        name="Température extérieure max (J-1)",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-chevron-up",
    ),
    OkovisionSensorDescription(
        key="tc_ext_min",
        data_key="tc_ext_min",
        name="Température extérieure min (J-1)",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-chevron-down",
    ),
    OkovisionSensorDescription(
        key="conso_kg",
        data_key="conso_kg",
        name="Consommation pellets (J-1)",
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:fire",
    ),
    OkovisionSensorDescription(
        key="conso_ecs_kg",
        data_key="conso_ecs_kg",
        name="Consommation pellets ECS (J-1)",
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:water-boiler",
    ),
    OkovisionSensorDescription(
        key="conso_kwh",
        data_key="conso_kwh",
        name="Énergie produite (J-1)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:lightning-bolt",
    ),
    OkovisionSensorDescription(
        key="nb_cycle",
        data_key="nb_cycle",
        name="Cycles chaudière (J-1)",
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="cycles",
        icon="mdi:restart",
    ),
    OkovisionSensorDescription(
        key="dju",
        data_key="dju",
        name="DJU (J-1)",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="DJU",
        icon="mdi:weather-snowflake-alert",
    ),
)


# ── Setup ─────────────────────────────────────────────────────────────────────

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure les entités sensor OkoVision."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    live_coord  = coordinators["live"]
    daily_coord = coordinators["daily"]

    entities: list[SensorEntity] = []

    entities.extend(
        OkovisionLiveSensor(live_coord, desc, entry)
        for desc in LIVE_SENSORS
    )
    entities.extend(
        OkovisionDailySensor(daily_coord, desc, entry)
        for desc in DAILY_SENSORS
    )

    async_add_entities(entities)


# ── Entité de base ────────────────────────────────────────────────────────────

def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="OkoVision",
        manufacturer=MANUFACTURER,
        model="Chaudière à pellets",
        configuration_url=entry.data.get(CONF_BASE_URL),
    )


# ── Sensors live ─────────────────────────────────────────────────────────────

class OkovisionLiveSensor(CoordinatorEntity[OkovisionLiveCoordinator], SensorEntity):
    """Capteur live OkoVision (silo / cendrier)."""

    _attr_has_entity_name = True
    entity_description: OkovisionSensorDescription

    def __init__(
        self,
        coordinator: OkovisionLiveCoordinator,
        description: OkovisionSensorDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> Any:
        key = self.entity_description.data_key
        if key.startswith("silo_") and self.coordinator.data.get("silo_error"):
            return None
        if key.startswith("ashtray_") and self.coordinator.data.get("ashtray_error"):
            return None
        return self.coordinator.data.get(key)


# ── Sensors daily ─────────────────────────────────────────────────────────────

class OkovisionDailySensor(CoordinatorEntity[OkovisionDailyCoordinator], SensorEntity):
    """Capteur J-1 OkoVision (données confirmées après 5h du matin)."""

    _attr_has_entity_name = True
    entity_description: OkovisionSensorDescription

    def __init__(
        self,
        coordinator: OkovisionDailyCoordinator,
        description: OkovisionSensorDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.get(self.entity_description.data_key)

    @property
    def last_reset(self):
        """Minuit de J-1 – permet à HA d'affecter la valeur au bon jour."""
        if self.state_class == SensorStateClass.TOTAL:
            return self.coordinator.data.get("last_reset")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Date de référence (J-1) exposée en attribut."""
        ref: date | None = self.coordinator.data.get("date")
        return {"reference_date": ref.isoformat() if ref else None}
