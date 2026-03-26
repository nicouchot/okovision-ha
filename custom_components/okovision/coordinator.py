"""Data update coordinator pour OkoVision."""
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
    """Coordinator qui interroge action=today toutes les N secondes.

    Structure de données retournée (à plat pour faciliter l'accès des entités) :
    {
        # Données journalières live
        "date":              str,
        "dju":               float | None,
        "conso_kg":          float | None,
        "conso_ecs_kg":      float | None,
        "conso_kwh":         float | None,
        "nb_cycle":          int   | None,
        "tc_ext_max":        float | None,
        "tc_ext_min":        float | None,

        # Silo
        "silo_remains_kg":   float | None,
        "silo_capacity_kg":  float | None,
        "silo_percent":      int   | None,
        "silo_last_fill":    str   | None,
        "silo_error":        str   | None,

        # Cendrier
        "ashtray_remains_kg":   float | None,
        "ashtray_capacity_kg":  float | None,
        "ashtray_percent":      int   | None,
        "ashtray_needs_emptying": bool | None,
        "ashtray_last_empty":   str   | None,
        "ashtray_error":        str   | None,
    }
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: OkovisionApiClient,
        scan_interval: int,
    ) -> None:
        """Initialise le coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Interroge action=today et aplatit la réponse."""
        try:
            raw = await self.client.async_get_today()
        except OkovisionApiError as err:
            raise UpdateFailed(f"Erreur API OkoVision: {err}") from err

        silo    = raw.get("silo", {}) or {}
        ashtray = raw.get("ashtray", {}) or {}

        return {
            # Journalier
            "date":         raw.get("date"),
            "dju":          raw.get("dju"),
            "conso_kg":     raw.get("conso_kg"),
            "conso_ecs_kg": raw.get("conso_ecs_kg"),
            "conso_kwh":    raw.get("conso_kwh"),
            "nb_cycle":     raw.get("nb_cycle"),
            "tc_ext_max":   raw.get("tc_ext_max"),
            "tc_ext_min":   raw.get("tc_ext_min"),

            # Silo
            "silo_remains_kg":  silo.get("remains_kg"),
            "silo_capacity_kg": silo.get("capacity_kg"),
            "silo_percent":     silo.get("percent"),
            "silo_last_fill":   silo.get("last_fill_date"),
            "silo_error":       silo.get("error"),

            # Cendrier
            "ashtray_remains_kg":     ashtray.get("remains_kg"),
            "ashtray_capacity_kg":    ashtray.get("capacity_kg"),
            "ashtray_percent":        ashtray.get("percent"),
            "ashtray_needs_emptying": ashtray.get("needs_emptying"),
            "ashtray_last_empty":     ashtray.get("last_empty_date"),
            "ashtray_error":          ashtray.get("error"),
        }
