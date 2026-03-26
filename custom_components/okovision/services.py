"""Service okovision.import_history – backfill des statistiques cumulatives OkoVision."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.const import UnitOfEnergy, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import OkovisionApiClient, OkovisionApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ── Compatibilité HA recorder API ─────────────────────────────────────────────
# Statistiques EXTERNES (source=DOMAIN, statistic_id="okovision:xxx")
# → indépendantes du recorder du sensor live → aucun conflit possible
#
# HA ≥ 2024.11 : StatisticMetaData(mean_type=StatisticMeanType, ...)
# HA < 2024.11 : StatisticMetaData(has_mean=bool, ...)

try:
    from homeassistant.components.recorder.statistics import (
        StatisticData,
        StatisticMeanType,
        StatisticMetaData,
        async_add_external_statistics,
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
        async_add_external_statistics,
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
# statistic_id externe : "okovision:{entity_key}"
# api_key    : champ dans la réponse journalière de l'API
# has_sum    : True  → courbe cumulative progressive
# has_mean   : True  → mesure journalière (ex: prix)
#
# Stratégie courbe progressive :
#   Les valeurs API cumul_kwh / cumul_kg / cumul_cycle sont déjà le cumulatif
#   exact depuis le début → injectées directement comme sum ET state.
#
# Tableau Énergie HA :
#   Dans Paramètres → Énergie, sélectionner le statistic_id externe
#   (ex: "okovision:cumul_kwh") et non le sensor entity.

STATISTICS_CONFIG: list[dict[str, Any]] = [
    {
        "entity_key": "cumul_kwh",
        "api_key":    "cumul_kwh",
        "name":       "OkoVision – Énergie cumulée",
        "unit":       UnitOfEnergy.KILO_WATT_HOUR,
        "has_sum":    True,
        "has_mean":   False,
    },
    {
        "entity_key": "cumul_kg",
        "api_key":    "cumul_kg",
        "name":       "OkoVision – Consommation cumulée pellets",
        "unit":       UnitOfMass.KILOGRAMS,
        "has_sum":    True,
        "has_mean":   False,
    },
    {
        "entity_key": "cumul_cycle",
        "api_key":    "cumul_cycle",
        "name":       "OkoVision – Cycles cumulés",
        "unit":       "cycles",
        "has_sum":    True,
        "has_mean":   False,
    },
    {
        "entity_key": "prix_kwh",
        "api_key":    "prix_kwh",
        "name":       "OkoVision – Prix énergie (€/kWh)",
        "unit":       "EUR/kWh",
        "has_sum":    False,
        "has_mean":   True,
    },
    {
        # Coût cumulé calculé : ∑(conso_kwh × prix_kwh) par jour
        # Permet d'afficher l'historique de coûts dans le tableau Énergie HA
        # (configurer comme "entité de suivi des coûts totaux" sur la source kWh)
        "entity_key": "cumul_cout_eur",
        "api_key":    None,          # calculé, pas lu directement depuis l'API
        "calc_keys":  ("conso_kwh", "prix_kwh"),
        "name":       "OkoVision – Coût cumulé chauffage",
        "unit":       "EUR",
        "has_sum":    True,
        "has_mean":   False,
    },
]


async def async_import_history(
    hass: HomeAssistant,
    client: OkovisionApiClient,
    entry_id: str,
    years: int = 4,
) -> dict[str, int]:
    """Backfill des statistiques historiques OkoVision dans le recorder HA.

    Injecte des statistiques EXTERNES (source=DOMAIN, statistic_id="okovision:xxx")
    totalement indépendantes des sensors live → aucun conflit avec le recorder.

    Dans le tableau Énergie HA, sélectionner "okovision:cumul_kwh" (et non
    le sensor sensor.okovision_energie_cumulee) pour éviter les valeurs négatives.
    """
    tz         = dt_util.get_default_time_zone()
    today      = date.today()
    end_date   = today - timedelta(days=1)
    start_date = date(today.year - years, today.month, 1)

    _LOGGER.info(
        "OkoVision import_history : démarrage %s → %s (%d an(s))",
        start_date, end_date, years,
    )

    # ── 1. Collecte mensuelle ──────────────────────────────────────────────────
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
        except OkovisionApiError as err:  # noqa: PERF203
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
        _LOGGER.warning("OkoVision import_history : aucune donnée reçue depuis l'API")
        return {}

    # ── 1b. Ajout d'aujourd'hui ───────────────────────────────────────────────
    # Inclure le cumul live du jour pour que le tableau Énergie soit à jour.
    try:
        today_raw = await client.async_get_today()
        today_str = today.isoformat()
        today_day: dict[str, Any] = {"date": today_str}
        for api_key in ("cumul_kwh", "cumul_kg", "cumul_cycle", "prix_kwh", "conso_kwh"):
            val = today_raw.get(api_key)
            if val is not None:
                today_day[api_key] = val
        if len(today_day) > 1:
            all_days[today_str] = today_day
            _LOGGER.debug(
                "OkoVision import_history : aujourd'hui ajouté – %s",
                {k: v for k, v in today_day.items() if k != "date"},
            )
    except OkovisionApiError as err:
        _LOGGER.warning(
            "OkoVision import_history : impossible de récupérer les données live "
            "d'aujourd'hui (%s)",
            err,
        )

    sorted_days = sorted(all_days.values(), key=lambda d: d["date"])
    _LOGGER.info(
        "OkoVision import_history : %d jours collectés – injection statistiques externes",
        len(sorted_days),
    )

    # ── 2. Injection par statistique (externe) ────────────────────────────────
    summary: dict[str, int] = {}

    for cfg in STATISTICS_CONFIG:
        entity_key  = cfg["entity_key"]
        api_key     = cfg["api_key"]
        has_sum     = cfg["has_sum"]
        has_mean    = cfg["has_mean"]
        statistic_id = f"{DOMAIN}:{entity_key}"   # ex: "okovision:cumul_kwh"

        try:
            metadata = _make_metadata(
                statistic_id=statistic_id,
                source=DOMAIN,
                name=cfg["name"],
                unit=cfg["unit"],
                has_mean=has_mean,
                has_sum=has_sum,
            )
        except Exception as err:
            _LOGGER.error(
                "OkoVision import_history : impossible de créer metadata '%s' – %s",
                entity_key, err,
            )
            continue

        statistics: list[Any] = []
        calc_keys   = cfg.get("calc_keys")
        running_sum = 0.0

        for day in sorted_days:
            try:
                day_date = date.fromisoformat(str(day["date"]))
                start    = datetime.combine(day_date, time.min).replace(tzinfo=tz)
            except (ValueError, TypeError, KeyError):
                continue

            if calc_keys:
                a = day.get(calc_keys[0])
                b = day.get(calc_keys[1])
                if a is None or b is None:
                    continue
                try:
                    day_value = round(float(a) * float(b), 4)
                except (ValueError, TypeError):
                    continue
                running_sum += day_value
                statistics.append(StatisticData(
                    start=start, state=day_value, sum=round(running_sum, 4)
                ))
            else:
                raw = day.get(api_key)
                if raw is None:
                    continue
                try:
                    value = float(raw)
                except (ValueError, TypeError):
                    continue
                if has_sum:
                    statistics.append(StatisticData(start=start, state=value, sum=value))
                else:
                    statistics.append(StatisticData(start=start, mean=value))

        if not statistics:
            _LOGGER.warning(
                "OkoVision import_history : '%s' – aucune valeur dans les données mensuelles",
                entity_key,
            )
            continue

        try:
            async_add_external_statistics(hass, metadata, statistics)
            summary[entity_key] = len(statistics)
            last_val = statistics[-1].sum if has_sum else statistics[-1].mean
            _LOGGER.info(
                "OkoVision import_history : ✓ %-18s → %4d pts | dernier=%s %s | id=%s",
                entity_key, len(statistics),
                f"{last_val:.2f}", cfg["unit"], statistic_id,
            )
        except Exception as err:
            _LOGGER.error(
                "OkoVision import_history : ✗ erreur injection '%s' → %s",
                entity_key, err,
            )

    _LOGGER.info(
        "OkoVision import_history : terminé – %d/%d métriques injectées",
        len(summary), len(STATISTICS_CONFIG),
    )
    return summary
