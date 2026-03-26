"""Plateforme binary_sensor OkoVision – cendrier à vider."""
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

from .const import CONF_BASE_URL, DOMAIN, MANUFACTURER
from .coordinator import OkovisionLiveCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure le binary_sensor OkoVision."""
    live_coord: OkovisionLiveCoordinator = hass.data[DOMAIN][entry.entry_id]["live"]
    async_add_entities([OkovisionAshtrayBinarySensor(live_coord, entry)])


class OkovisionAshtrayBinarySensor(
    CoordinatorEntity[OkovisionLiveCoordinator], BinarySensorEntity
):
    """True quand le cendrier doit être vidé (needs_emptying = true)."""

    _attr_has_entity_name = True
    _attr_name = "Cendrier – À vider"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:trash-can"

    def __init__(self, coordinator: OkovisionLiveCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ashtray_needs_emptying"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="OkoVision",
            manufacturer=MANUFACTURER,
            model="Chaudière à pellets",
            configuration_url=entry.data.get(CONF_BASE_URL),
        )

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data.get("ashtray_error"):
            return None
        return self.coordinator.data.get("ashtray_needs_emptying")

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        last_empty = data.get("ashtray_last_empty")
        return {
            "last_empty_date": last_empty.isoformat() if last_empty else None,
            "remains_kg":      data.get("ashtray_remains_kg"),
            "capacity_kg":     data.get("ashtray_capacity_kg"),
        }
