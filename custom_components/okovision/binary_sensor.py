"""Plateforme binary_sensor pour OkoVision – cendrier à vider."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import OkovisionCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure le binary_sensor OkoVision."""
    coordinator: OkovisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OkovisionAshtrayBinarySensor(coordinator, entry)])


class OkovisionAshtrayBinarySensor(
    CoordinatorEntity[OkovisionCoordinator], BinarySensorEntity
):
    """Indique si le cendrier doit être vidé (needs_emptying = true)."""

    _attr_has_entity_name = True
    _attr_name = "Cendrier – À vider"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:trash-can"

    def __init__(
        self,
        coordinator: OkovisionCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialise le binary_sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ashtray_needs_emptying"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="OkoVision",
            manufacturer=MANUFACTURER,
            model="Chaudière à pellets",
            configuration_url=entry.data.get("base_url"),
        )

    @property
    def is_on(self) -> bool | None:
        """Retourne True si le cendrier doit être vidé."""
        if self.coordinator.data.get("ashtray_error"):
            return None
        return self.coordinator.data.get("ashtray_needs_emptying")

    @property
    def extra_state_attributes(self) -> dict:
        """Attributs supplémentaires."""
        data = self.coordinator.data
        return {
            "last_empty_date": data.get("ashtray_last_empty"),
            "remains_kg":      data.get("ashtray_remains_kg"),
            "capacity_kg":     data.get("ashtray_capacity_kg"),
        }
