"""Plateforme sensor pour OkoVision (chaudière à pellets)."""
from __future__ import annotations

from dataclasses import dataclass
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

from .const import DOMAIN, MANUFACTURER
from .coordinator import OkovisionCoordinator


@dataclass(frozen=True, kw_only=True)
class OkovisionSensorDescription(SensorEntityDescription):
    """Description étendue avec clé dans coordinator.data."""

    data_key: str


SENSORS: tuple[OkovisionSensorDescription, ...] = (
    # ── Températures extérieures ─────────────────────────────────────────────
    OkovisionSensorDescription(
        key="tc_ext_max",
        data_key="tc_ext_max",
        name="Température extérieure max",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-chevron-up",
    ),
    OkovisionSensorDescription(
        key="tc_ext_min",
        data_key="tc_ext_min",
        name="Température extérieure min",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-chevron-down",
    ),

    # ── Consommation journalière ──────────────────────────────────────────────
    OkovisionSensorDescription(
        key="conso_kg",
        data_key="conso_kg",
        name="Consommation pellets du jour",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:fire",
    ),
    OkovisionSensorDescription(
        key="conso_ecs_kg",
        data_key="conso_ecs_kg",
        name="Consommation pellets ECS du jour",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:water-boiler",
    ),
    OkovisionSensorDescription(
        key="conso_kwh",
        data_key="conso_kwh",
        name="Énergie produite du jour",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:lightning-bolt",
    ),

    # ── Cycles chaudière ─────────────────────────────────────────────────────
    OkovisionSensorDescription(
        key="nb_cycle",
        data_key="nb_cycle",
        name="Cycles chaudière du jour",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="cycles",
        icon="mdi:restart",
    ),

    # ── DJU ──────────────────────────────────────────────────────────────────
    OkovisionSensorDescription(
        key="dju",
        data_key="dju",
        name="DJU du jour",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="DJU",
        icon="mdi:weather-snowflake-alert",
    ),

    # ── Silo à pellets ───────────────────────────────────────────────────────
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
        entity_registry_enabled_default=False,
    ),
    OkovisionSensorDescription(
        key="silo_percent",
        data_key="silo_percent",
        name="Silo – Niveau",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        icon="mdi:gauge",
    ),

    # ── Cendrier ─────────────────────────────────────────────────────────────
    OkovisionSensorDescription(
        key="ashtray_remains_kg",
        data_key="ashtray_remains_kg",
        name="Cendrier – Capacité restante",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:trash-can-outline",
    ),
    OkovisionSensorDescription(
        key="ashtray_percent",
        data_key="ashtray_percent",
        name="Cendrier – Niveau de remplissage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        icon="mdi:gauge",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure les entités sensor OkoVision."""
    coordinator: OkovisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        OkovisionSensor(coordinator, description, entry)
        for description in SENSORS
    )


class OkovisionSensor(CoordinatorEntity[OkovisionCoordinator], SensorEntity):
    """Entité sensor OkoVision."""

    _attr_has_entity_name = True
    entity_description: OkovisionSensorDescription

    def __init__(
        self,
        coordinator: OkovisionCoordinator,
        description: OkovisionSensorDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialise le sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="OkoVision",
            manufacturer=MANUFACTURER,
            model="Chaudière à pellets",
            configuration_url=entry.data.get("base_url"),
        )

    @property
    def native_value(self) -> Any:
        """Retourne la valeur depuis coordinator.data."""
        value = self.coordinator.data.get(self.entity_description.data_key)
        # Ne pas exposer la valeur si l'API remonte une erreur sur ce sous-bloc
        if self.entity_description.data_key.startswith("silo_") and self.coordinator.data.get("silo_error"):
            return None
        if self.entity_description.data_key.startswith("ashtray_") and self.coordinator.data.get("ashtray_error"):
            return None
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributs supplémentaires selon le capteur."""
        attrs: dict[str, Any] = {}
        data = self.coordinator.data

        if self.entity_description.key == "silo_remains_kg":
            attrs["last_fill_date"] = data.get("silo_last_fill")
            attrs["capacity_kg"]    = data.get("silo_capacity_kg")
        elif self.entity_description.key == "ashtray_remains_kg":
            attrs["last_empty_date"]  = data.get("ashtray_last_empty")
            attrs["needs_emptying"]   = data.get("ashtray_needs_emptying")
        elif self.entity_description.key in ("conso_kg", "conso_ecs_kg", "conso_kwh", "nb_cycle", "dju"):
            attrs["date"] = data.get("date")

        return attrs
