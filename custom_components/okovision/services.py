"""Service okovision.import_history – import des statistiques historiques OkoVision."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import UnitOfEnergy, UnitOfMass, UnitOfTemperature
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from .api import OkovisionApiClient, OkovisionApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ── Définition des statistiques à importer ────────────────────────────────────
#
# has_sum=True  → compteur cumulatif (énergie, poids, cycles)
#                 HA stocke : state (valeur du jour) + sum (total cumulatif)
# has_mean=True → mesure (température, DJU)
#                 HA stocke : mean (valeur du jour)

STATISTICS_CONFIG: list[dict[str, Any]] = [
    {
        "key":     "conso_kwh",
        "name":    "Énergie produite",
        "unit":    UnitOfEnergy.KILO_WATT_HOUR,
        "has_sum": True,
        "has_mean": False,
    },
    {
        "key":     "conso_kg",
        "name":    "Consommation pellets",
        "unit":    UnitOfMass.KILOGRAMS,
        "has_sum": True,
        "has_mean": False,
    },
    {
        "key":     "conso_ecs_kg",
        "name":    "Consommation pellets ECS",
        "unit":    UnitOfMass.KILOGRAMS,
        "has_sum": True,
        "has_mean": False,
    },
    {
        "key":     "nb_cycle",
        "name":    "Cycles chaudière",
        "unit":    "cycles",
        "has_sum": True,
        "has_mean": False,
    },
    {
        "key":     "dju",
        "name":    "DJU",
        "unit":    "DJU",
        "has_sum": False,
        "has_mean": True,
    },
    {
        "key":     "tc_ext_max",
        "name":    "Température extérieure max",
        "unit":    UnitOfTemperature.CELSIUS,
        "has_sum": False,
        "has_mean": True,
    },
    {
        "key":     "tc_ext_min",
        "name":    "Température extérieure min",
        "unit":    UnitOfTemperature.CELSIUS,
        "has_sum": False,
        "has_mean": True,
    },
]


async def async_import_history(
    hass: HomeAssistant,
    client: OkovisionApiClient,
    years: int = 4,
) -> dict[str, Any]:
    """Importe les statistiques historiques OkoVision dans le recorder HA.

    Stratégie :
    - Récupère les données mois par mois via action=monthly (évite les timeouts)
    - Pour les compteurs (has_sum), calcule le cumul chronologique
    - Pour les mesures (has_mean), stocke la valeur journalière comme moyenne
    - Appelle async_import_statistics pour chaque métrique

    Retourne un dict de résumé : {key: nb_jours_importés, ...}
    """
    tz = dt_util.get_default_time_zone()
    today = date.today()
    end_date = today - timedelta(days=1)

    # Premier jour du mois il y a N années
    start_year = today.year - years
    start_date = date(start_year, today.month, 1)

    _LOGGER.info(
        "OkoVision import_history : début – période %s → %s (%d an(s))",
        start_date, end_date, years,
    )

    # ── 1. Collecte de toutes les données journalières ────────────────────────
    all_days: dict[str, dict[str, Any]] = {}
    current = start_date
    total_months = (
        (end_date.year - start_date.year) * 12
        + (end_date.month - start_date.month)
        + 1
    )
    fetched = 0

    while current <= end_date:
        try:
            monthly = await client.async_get_monthly(current.month, current.year)
            days = monthly.get("days", [])
            for day in days:
                day_str = day.get("date")
                if day_str:
                    all_days[day_str] = day
            fetched += 1
            _LOGGER.debug(
                "OkoVision import_history : %02d/%04d ✓ (%d/%d mois, %d jours cumulés)",
                current.month, current.year, fetched, total_months, len(all_days),
            )
        except OkovisionApiError as err:
            _LOGGER.warning(
                "OkoVision import_history : erreur %02d/%04d – %s (ignoré)",
                current.month, current.year, err,
            )

        # Petit délai pour ne pas saturer l'API
        await asyncio.sleep(0.2)

        # Mois suivant
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    if not all_days:
        _LOGGER.warning("OkoVision import_history : aucune donnée récupérée")
        return {}

    # Tri chronologique
    sorted_days = sorted(all_days.values(), key=lambda d: d["date"])
    _LOGGER.info(
        "OkoVision import_history : %d jours collectés, début import recorder",
        len(sorted_days),
    )

    # ── 2. Import statistique par statistique ─────────────────────────────────
    summary: dict[str, int] = {}

    for cfg in STATISTICS_CONFIG:
        key       = cfg["key"]
        has_sum   = cfg["has_sum"]
        has_mean  = cfg["has_mean"]

        metadata = StatisticMetaData(
            statistic_id=f"{DOMAIN}:{key}",
            source=DOMAIN,
            name=f"OkoVision – {cfg['name']}",
            unit_of_measurement=cfg["unit"],
            has_mean=has_mean,
            has_sum=has_sum,
        )

        statistics: list[StatisticData] = []
        running_sum = 0.0

        for day in sorted_days:
            raw_value = day.get(key)
            if raw_value is None:
                continue

            try:
                value     = float(raw_value)
                day_date  = date.fromisoformat(day["date"])
                start     = datetime.combine(day_date, time.min).replace(tzinfo=tz)
            except (ValueError, TypeError):
                continue

            if has_sum:
                running_sum += value
                statistics.append(StatisticData(
                    start=start,
                    state=value,
                    sum=running_sum,
                ))
            else:
                statistics.append(StatisticData(
                    start=start,
                    mean=value,
                ))

        if statistics:
            async_import_statistics(hass, metadata, statistics)
            summary[key] = len(statistics)
            _LOGGER.info(
                "OkoVision import_history : %-20s → %d entrées (sum=%.1f %s)",
                key, len(statistics),
                running_sum if has_sum else 0,
                cfg["unit"],
            )
        else:
            _LOGGER.debug("OkoVision import_history : %s – aucune valeur disponible", key)

    _LOGGER.info(
        "OkoVision import_history : terminé – %d métriques importées",
        len(summary),
    )
    return summary
