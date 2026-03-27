"""Coordinators OkoVision – Live (silo/cendrier) et Daily (données J-1 confirmées)."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OkovisionApiClient, OkovisionApiError, OkovisionDataNotFoundError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Clés dont la valeur None est acceptable (non-numériques)
_NULLABLE_KEYS = {"date", "last_reset", "silo_error", "ashtray_error"}


def _merge_with_previous(new: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Remplace les valeurs None dans `new` par les dernières valeurs connues de `previous`.

    Cela garantit la continuité des sensors dans HA même quand l'API renvoie
    null entre minuit et ~5h (données J-1 pas encore disponibles).
    Les clés non-numériques (date, last_reset, erreurs) ne sont pas préservées.
    """
    if not previous:
        return new
    return {
        k: (v if v is not None or k in _NULLABLE_KEYS else previous.get(k))
        for k, v in new.items()
    }


class OkovisionLiveCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Interroge action=today toutes les N secondes.

    Données retournées (silo + cendrier uniquement) :
    {
        "silo_remains_kg":        float | None,
        "silo_capacity_kg":       float | None,
        "silo_percent":           int   | None,
        "silo_last_fill":         date  | None,
        "silo_error":             str   | None,

        "ashtray_remains_kg":     float | None,
        "ashtray_capacity_kg":    float | None,
        "ashtray_percent":        int   | None,
        "ashtray_needs_emptying": bool  | None,
        "ashtray_last_empty":     date  | None,
        "ashtray_error":          str   | None,
    }
    """

    def __init__(self, hass: HomeAssistant, client: OkovisionApiClient, scan_interval: int) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_live", update_interval=timedelta(seconds=scan_interval))
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            raw = await self.client.async_get_today()
        except OkovisionDataNotFoundError as err:
            _LOGGER.info("OkoVision live: données non disponibles, conservation du cache (%s)", err)
            return self.data or {}
        except OkovisionApiError as err:
            if self.data:
                _LOGGER.debug("OkoVision live: erreur API, conservation du cache (%s)", err)
                return self.data
            raise UpdateFailed(f"Erreur API OkoVision (live): {err}") from err

        silo        = raw.get("silo", {}) or {}
        ashtray     = raw.get("ashtray", {}) or {}
        maintenance = raw.get("maintenance", {}) or {}

        result = {
            # Silo
            "silo_remains_kg":  silo.get("remains_kg"),
            "silo_capacity_kg": silo.get("capacity_kg"),
            "silo_percent":     silo.get("percent"),
            "silo_last_fill":   _parse_date(silo.get("last_fill_date")),
            "silo_error":       silo.get("error"),

            # Cendrier
            "ashtray_remains_kg":     ashtray.get("remains_kg"),
            "ashtray_capacity_kg":    ashtray.get("capacity_kg"),
            "ashtray_percent":        ashtray.get("percent"),
            "ashtray_needs_emptying": ashtray.get("needs_emptying"),
            "ashtray_last_empty":     _parse_date(ashtray.get("last_empty_date")),
            "ashtray_error":          ashtray.get("error"),

            # Maintenance
            "last_sweep":       _parse_date(maintenance.get("last_sweep")),
            "last_maintenance": _parse_date(maintenance.get("last_maintenance")),
        }

        # Préserve les valeurs précédentes si l'API renvoie null
        return _merge_with_previous(result, self.data)


class OkovisionDailyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Récupère le résumé confirmé de J-1 (action=daily&date=hier).

    Rafraîchi toutes les 30 minutes – les données sont stables une fois
    disponibles (vers 5h du matin). Le coordinator mémorise la dernière
    date fetched pour éviter des requêtes inutiles.

    Après chaque fetch réussi de nouvelles données J-1, pousse automatiquement
    une entrée dans les statistiques externes (okovision:cumul_kwh, etc.) pour
    que le tableau Énergie soit à jour sans avoir à relancer import_history.

    Données retournées :
    {
        "date":         date  | None,   # date de J-1
        "last_reset":   datetime,       # minuit de J-1 (pour last_reset HA)
        "dju":          float | None,
        "conso_kg":     float | None,
        "conso_ecs_kg": float | None,
        "conso_kwh":    float | None,
        "nb_cycle":     int   | None,
        "tc_ext_max":   float | None,
        "tc_ext_min":   float | None,
        "cumul_kg":     float | None,
        "cumul_kwh":    float | None,
        "cumul_cycle":  float | None,
        "prix_kg":      float | None,
        "prix_kwh":     float | None,
        "cumul_cout_eur": float | None,
    }
    """

    def __init__(self, hass: HomeAssistant, client: OkovisionApiClient) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_daily",
            update_interval=timedelta(hours=1),
        )
        self.client = client
        self._last_fetched_date: date | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        yesterday = date.today() - timedelta(days=1)
        last_reset = datetime.combine(yesterday, time.min).replace(
            tzinfo=dt_util.get_default_time_zone()
        )

        # Réutilise les données en cache si déjà fetchées aujourd'hui
        if self._last_fetched_date == date.today() and self.data:
            return self.data

        try:
            raw = await self.client.async_get_daily(yesterday.isoformat())
        except OkovisionDataNotFoundError as err:
            # Données pas encore importées par OkoVision (typiquement entre minuit et ~5h)
            # On conserve le cache et on ne marque PAS _last_fetched_date pour retenter au prochain cycle
            _LOGGER.info("OkoVision daily: données non encore disponibles pour J-1, nouvelle tentative au prochain cycle (%s)", err)
            return self.data or {}
        except OkovisionApiError as err:
            # Autre erreur API : conserver le cache si disponible
            if self.data:
                _LOGGER.debug("OkoVision daily: erreur API, conservation du cache (%s)", err)
                return self.data
            raise UpdateFailed(f"Erreur API OkoVision (daily): {err}") from err

        self._last_fetched_date = date.today()

        result = {
            "date":         _parse_date(raw.get("date")) or yesterday,
            "last_reset":   last_reset,
            # Journalier
            "dju":          raw.get("dju"),
            "conso_kg":     raw.get("conso_kg"),
            "conso_ecs_kg": raw.get("conso_ecs_kg"),
            "conso_kwh":    raw.get("conso_kwh"),
            "nb_cycle":     raw.get("nb_cycle"),
            "tc_ext_max":   raw.get("tc_ext_max"),
            "tc_ext_min":   raw.get("tc_ext_min"),
            # Cumulatifs (depuis le début de l'historique)
            "cumul_kg":     raw.get("cumul_kg"),
            "cumul_kwh":    raw.get("cumul_kwh"),
            "cumul_cycle":  raw.get("cumul_cycle"),
            # Prix
            "prix_kg":      raw.get("prix_kg"),
            "prix_kwh":     raw.get("prix_kwh"),
            # Coût cumulé – valeur directe depuis l'API (champ cumul_cout)
            "cumul_cout_eur": (
                round(float(raw["cumul_cout"]), 2)
                if raw.get("cumul_cout") is not None
                else None
            ),
        }

        # Préserve les valeurs précédentes si l'API renvoie null sur certains champs
        result = _merge_with_previous(result, self.data)

        # ── Push automatique des statistiques externes pour J-1 ───────────────
        # Maintient okovision:cumul_kwh / cumul_cout_eur à jour dans le tableau
        # Énergie sans nécessiter de relancer le service import_history.
        try:
            from .services import async_push_daily_stats  # import local pour éviter le cycle
            await async_push_daily_stats(self.hass, result)
        except Exception as push_err:  # noqa: BLE001
            _LOGGER.debug("OkoVision daily: push stats externes ignoré (%s)", push_err)

        return result


def _parse_date(value: str | None) -> date | None:
    """Convertit une chaîne 'YYYY-MM-DD' en objet date, ou None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
