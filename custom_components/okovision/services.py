"""Service okovision.import_history – import des statistiques historiques OkoVision."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.const import UnitOfEnergy, UnitOfMass, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .api import OkovisionApiClient, OkovisionApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ── Compatibilité HA recorder API ─────────────────────────────────────────────
# HA 2024.11+ : StatisticMetaData(mean_type=StatisticMeanType, ...)
# HA < 2024.11 : StatisticMetaData(has_mean=bool, ...)

try:
    from homeassistant.components.recorder.statistics import (
        StatisticData,
        StatisticMeanType,
        StatisticMetaData,
        async_import_statistics,
    )

    def _make_metadata(
        statistic_id: str, source: str, name: str,
        unit: str | None, has_mean: bool, has_sum: bool,
    ) -> StatisticMetaData:
        return StatisticMetaData(
            statistic_id=statistic_id,
            source=source,
            name=name,
            unit_of_measurement=unit,
            mean_type=StatisticMeanType.ARITHMETIC if has_mean else StatisticMeanType.NONE,
            has_sum=has_sum,
        )

except ImportError:
    from homeassistant.components.recorder.models import (  # type: ignore[no-redef]
        StatisticData,
        StatisticMetaData,
    )
    from homeassistant.components.recorder.statistics import (  # type: ignore[no-redef]
        async_import_statistics,
    )

    def _make_metadata(  # type: ignore[misc]
        statistic_id: str, source: str, name: str,
        unit: str | None, has_mean: bool, has_sum: bool,
    ) -> Any:
        return StatisticMetaData(
            statistic_id=statistic_id,
            source=source,
            name=name,
            unit_of_measurement=unit,
            has_mean=has_mean,
            has_sum=has_sum,
        )


# ── Statistiques à importer ───────────────────────────────────────────────────
#
# key       : clé dans les données journalières de l'API
# cumul_key : clé fournissant directement le cumul (évite de le recalculer)
# has_sum   : True → injecté comme compteur cumulatif dans le recorder
# has_mean  : True → injecté comme valeur moyenne journalière

STATISTICS_CONFIG: list[dict[str, Any]] = [
    {
        "key":       "conso_kwh",
        "cumul_key": "cumul_kwh",
        "name":      "Énergie produite (J-1)",
        "unit":      UnitOfEnergy.KILO_WATT_HOUR,
        "has_sum":   True,
        "has_mean":  False,
    },
    {
        "key":       "conso_kg",
        "cumul_key": "cumul_kg",
        "name":      "Consommation pellets (J-1)",
        "unit":      UnitOfMass.KILOGRAMS,
        "has_sum":   True,
        "has_mean":  False,
    },
    {
        "key":       "conso_ecs_kg",
        "cumul_key": None,
        "name":      "Consommation pellets ECS (J-1)",
        "unit":      UnitOfMass.KILOGRAMS,
        "has_sum":   True,
        "has_mean":  False,
    },
    {
        "key":       "nb_cycle",
        "cumul_key": "cumul_cycle",
        "name":      "Cycles chaudière (J-1)",
        "unit":      "cycles",
        "has_sum":   True,
        "has_mean":  False,
    },
    {
        "key":       "dju",
        "cumul_key": None,
        "name":      "DJU (J-1)",
        "unit":      "DJU",
        "has_sum":   False,
        "has_mean":  True,
    },
    {
        "key":       "tc_ext_max",
        "cumul_key": None,
        "name":      "Température extérieure max (J-1)",
        "unit":      UnitOfTemperature.CELSIUS,
        "has_sum":   False,
        "has_mean":  True,
    },
    {
        "key":       "tc_ext_min",
        "cumul_key": None,
        "name":      "Température extérieure min (J-1)",
        "unit":      UnitOfTemperature.CELSIUS,
        "has_sum":   False,
        "has_mean":  True,
    },
    {
        "key":       "prix_kg",
        "cumul_key": None,
        "name":      "Prix pellets (€/kg)",
        "unit":      "EUR/kg",
        "has_sum":   False,
        "has_mean":  True,
    },
    {
        "key":       "prix_kwh",
        "cumul_key": None,
        "name":      "Prix énergie (€/kWh)",
        "unit":      "EUR/kWh",
        "has_sum":   False,
        "has_mean":  True,
    },
]


async def async_import_history(
    hass: HomeAssistant,
    client: OkovisionApiClient,
    entry_id: str,
    years: int = 4,
) -> dict[str, int]:
    """Importe les statistiques historiques OkoVision dans le recorder HA.

    Stratégie :
    - Les statistic_id sont récupérés depuis le registre d'entités HA → format
      garanti valide (source="recorder", statistic_id="sensor.okovision_xxx").
    - Les cumuls (cumul_kg, cumul_kwh, cumul_cycle) fournis par l'API sont
      utilisés directement comme valeur `sum` → pas de dérive de calcul.
    - Mesures (températures, DJU, prix) → valeur journalière comme `mean`.
    """
    tz       = dt_util.get_default_time_zone()
    today    = date.today()
    end_date = today - timedelta(days=1)
    start_date = date(today.year - years, today.month, 1)

    _LOGGER.info(
        "OkoVision import_history : début – %s → %s (%d an(s))",
        start_date, end_date, years,
    )

    # ── 1. Résolution des entity_id via le registre ───────────────────────────
    entity_reg = er.async_get(hass)
    entities_by_key: dict[str, str] = {}  # key → entity_id (ex: "sensor.okovision_xxx")

    for entity_entry in er.async_entries_for_config_entry(entity_reg, entry_id):
        uid = entity_entry.unique_id or ""
        prefix = f"{entry_id}_"
        if uid.startswith(prefix):
            key = uid[len(prefix):]
            entities_by_key[key] = entity_entry.entity_id

    if not entities_by_key:
        _LOGGER.error(
            "OkoVision import_history : aucune entité trouvée pour entry_id=%s "
            "– l'intégration est-elle bien configurée ?",
            entry_id,
        )
        return {}

    _LOGGER.debug(
        "OkoVision import_history : %d entités trouvées : %s",
        len(entities_by_key), list(entities_by_key.keys()),
    )

    # ── 2. Collecte mensuelle ─────────────────────────────────────────────────
    all_days: dict[str, dict[str, Any]] = {}
    current = start_date

    total_months = (
        (end_date.year  - start_date.year)  * 12
        + (end_date.month - start_date.month) + 1
    )
    fetched = 0

    while current <= end_date:
        try:
            monthly = await client.async_get_monthly(current.month, current.year)
            for day in monthly.get("days", []):
                if day.get("date"):
                    all_days[day["date"]] = day
            fetched += 1
            _LOGGER.debug(
                "OkoVision import_history : %02d/%04d ✓ (%d/%d – %d jours cumulés)",
                current.month, current.year, fetched, total_months, len(all_days),
            )
        except OkovisionApiError as err:
            _LOGGER.warning(
                "OkoVision import_history : erreur %02d/%04d – %s (ignoré)",
                current.month, current.year, err,
            )

        await asyncio.sleep(0.2)

        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    if not all_days:
        _LOGGER.warning("OkoVision import_history : aucune donnée récupérée depuis l'API")
        return {}

    sorted_days = sorted(all_days.values(), key=lambda d: d["date"])
    _LOGGER.info(
        "OkoVision import_history : %d jours collectés – début injection recorder",
        len(sorted_days),
    )

    # ── 3. Injection par statistique ──────────────────────────────────────────
    summary: dict[str, int] = {}

    for cfg in STATISTICS_CONFIG:
        key       = cfg["key"]
        cumul_key = cfg["cumul_key"]
        has_sum   = cfg["has_sum"]
        has_mean  = cfg["has_mean"]

        entity_id = entities_by_key.get(key)
        if not entity_id:
            _LOGGER.debug(
                "OkoVision import_history : entité introuvable pour '%s' – ignoré", key
            )
            continue

        # source="recorder" + statistic_id=entity_id → format toujours valide
        try:
            metadata = _make_metadata(
                statistic_id=entity_id,
                source="recorder",
                name=cfg["name"],
                unit=cfg["unit"],
                has_mean=has_mean,
                has_sum=has_sum,
            )
        except Exception as err:
            _LOGGER.error(
                "OkoVision import_history : erreur création metadata '%s' – %s", key, err
            )
            continue

        statistics: list[Any] = []
        running_sum = 0.0  # fallback si cumul_key absent de l'API

        for day in sorted_days:
            raw = day.get(key)
            if raw is None:
                continue
            try:
                value    = float(raw)
                day_date = date.fromisoformat(day["date"])
                start    = datetime.combine(day_date, time.min).replace(tzinfo=tz)
            except (ValueError, TypeError):
                continue

            if has_sum:
                # Priorité au cumul natif de l'API (plus précis)
                if cumul_key and day.get(cumul_key) is not None:
                    stat_sum = float(day[cumul_key])
                else:
                    running_sum += value
                    stat_sum = running_sum

                statistics.append(StatisticData(
                    start=start,
                    state=value,
                    sum=stat_sum,
                ))
            else:
                statistics.append(StatisticData(
                    start=start,
                    mean=value,
                ))

        if not statistics:
            _LOGGER.debug("OkoVision import_history : '%s' – aucune valeur disponible", key)
            continue

        try:
            async_import_statistics(hass, metadata, statistics)
            final_sum = float(sorted_days[-1].get(cumul_key, 0) or 0) if cumul_key else running_sum
            summary[key] = len(statistics)
            _LOGGER.info(
                "OkoVision import_history : %-20s → %d jours | entity=%s%s",
                key, len(statistics), entity_id,
                f" | cumul={final_sum:.1f} {cfg['unit']}" if has_sum else "",
            )
        except Exception as err:
            _LOGGER.error(
                "OkoVision import_history : erreur injection '%s' – %s", key, err
            )

    _LOGGER.info(
        "OkoVision import_history : terminé – %d/%d métriques importées",
        len(summary), len(STATISTICS_CONFIG),
    )
    return summary
