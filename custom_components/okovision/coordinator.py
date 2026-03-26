"""Data update coordinator for Okovision."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OkovisionApiClient, OkovisionApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class OkovisionCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch all sensor data from Okovision."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: OkovisionApiClient,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Okovision API."""
        try:
            sensors = await self.client.async_get_sensors()
            return {sensor["id"]: sensor for sensor in sensors}
        except OkovisionApiError as err:
            raise UpdateFailed(f"Error communicating with Okovision API: {err}") from err
