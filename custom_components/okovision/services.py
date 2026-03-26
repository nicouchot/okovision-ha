"""Service okovision.import_history – backfill des statistiques cumulatives OkoVision."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.const import UnitOfEnergy, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .api import OkovisionApiClient, OkovisionApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ── Compatibilité HA recorder API ─────────────────────────────────────────────
# HA ≥ 2024.11 : StatisticMetaData(mean_type=StatisticMeanType, ...)
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
# entity_key : clé unique_id du sensor HA (doit être TOTAL_INCREASING ou MEASUREMENT)
# api_key    : champ dans la réponse journalière de l'API
# has_sum    : True  → courbe cumulative progressive (TOTAL_INCREASING)
# has_mean   : True  → mesure journalière
#
# Stratégie courbe progressive :
#   Les entités ciblées sont cumul_kwh / cumul_kg / cumul_cycle (TOTAL_INCREASING).
#   Leur valeur API est déjà le cumulatif exact depuis le début → on l'injecte
#   directement comme sum ET state : HA reconstruit automatiquement la courbe 0→actuel.

STATISTICS_CONFIG: list[dict[str, Any]] = [
    {
        "entity_key": "cumul_kwh",
        "api_key":    "cumul_kwh",
        "name":       "Énergie cumulée",
        "unit":       UnitOfEnergy.KILO_WATT_HOUR,
        "has_sum":    True,
        "has_mean":   False,
    },
    {
        "entity_key": "cumul_kg",
        "api_key":    "cumul_kg",
        "name":       "Consommation cumulée pellets",
        "unit":       UnitOfMass.KILOGRAMS,
        "has_sum":    True,
        "has_mean":   False,
    },
    {
        "entity_key": "cumul_cycle",
        "api_key":    "cumul_cycle",
        "name":       "Cycles cumulés",
        "unit":       "cycles",
        "has_sum":    True,
        "has_mean":   False,
    },
    {
        "entity_key": "prix_kwh",
        "api_key":    "prix_kwh",
        "name":       "Prix énergie (€/kWh)",
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
        "name":       "Coût cumulé chauffage",
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

    Cible les entités TOTAL_INCREASING (cumul_kwh, cumul_kg, cumul_cycle) et
    prix_kwh. Les valeurs cumulatives de l'API sont injectées directement comme
    `sum` + `state` → HA reconstruit la courbe progressive sans recalcul.
    """
    tz         = dt_util.get_default_time_zone()
    today      = date.today()
    end_date   = today - timedelta(days=1)
    start_date = date(today.year - years, today.month, 1)

    _LOGGER.info(
        "OkoVision import_history : démarrage %s → %s (%d an(s))",
        start_date, end_date, years,
    )

    # ── 1. Résolution entity_id via le registre ───────────────────────────────
    entity_reg = er.async_get(hass)
    entities_by_key: dict[str, str] = {}

    for entity_entry in er.async_entries_for_config_entry(entity_reg, entry_id):
        uid    = entity_entry.unique_id or ""
        prefix = f"{entry_id}_"
        if uid.startswith(prefix):
            key = uid[len(prefix):]
            entities_by_key[key] = entity_entry.entity_id

    _LOGGER.info(
        "OkoVision import_history : %d entités trouvées dans le registre",
        len(entities_by_key),
    )
    for k, eid in entities_by_key.items():
        _LOGGER.debug("  %-20s → %s", k, eid)

    # Vérifie que les entités cibles sont bien présentes
    missing = [c["entity_key"] for c in STATISTICS_CONFIG if c["entity_key"] not in entities_by_key]
    if missing:
        _LOGGER.warning(
            "OkoVision import_history : entités introuvables : %s – "
            "rechargez l'intégration puis relancez le service.",
            missing,
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

    # ── 2b. Ajout d'aujourd'hui ───────────────────────────────────────────────
    # CRITIQUE : le recorder HA a déjà créé une entrée pour aujourd'hui avec
    # sum = delta_depuis_installation (ex: 21 kWh).
    # Sans ce patch, le tableau Énergie calcule : 21 - 15234 = -15213 → négatif.
    # On écrase l'entrée d'aujourd'hui avec le cumul correct issu de action=today.
    try:
        today_raw = await client.async_get_today()
        today_str = today.isoformat()
        today_day: dict[str, Any] = {"date": today_str}
        # Récupère les cumuls live (champs directs dans la réponse action=today)
        for api_key in ("cumul_kwh", "cumul_kg", "cumul_cycle", "prix_kwh", "conso_kwh"):
            val = today_raw.get(api_key)
            if val is not None:
                today_day[api_key] = val
        if len(today_day) > 1:  # au moins un cumul disponible
            all_days[today_str] = today_day
            _LOGGER.debug(
                "OkoVision import_history : aujourd'hui ajouté – %s",
                {k: v for k, v in today_day.items() if k != "date"},
            )
    except OkovisionApiError as err:
        _LOGGER.warning(
            "OkoVision import_history : impossible de récupérer les données live "
            "d'aujourd'hui – l'entrée incorrecte du recorder ne sera pas corrigée (%s)",
            err,
        )

    sorted_days = sorted(all_days.values(), key=lambda d: d["date"])
    _LOGGER.info(
        "OkoVision import_history : %d jours collectés (dont aujourd'hui) – injection dans le recorder",
        len(sorted_days),
    )

    # ── 3. Injection par statistique ──────────────────────────────────────────
    summary: dict[str, int] = {}

    for cfg in STATISTICS_CONFIG:
        entity_key = cfg["entity_key"]
        api_key    = cfg["api_key"]
        has_sum    = cfg["has_sum"]
        has_mean   = cfg["has_mean"]

        entity_id = entities_by_key.get(entity_key)
        if not entity_id:
            _LOGGER.warning(
                "OkoVision import_history : entité '%s' absente du registre – ignoré",
                entity_key,
            )
            continue

        try:
            metadata = _make_metadata(
                statistic_id=entity_id,   # ex: "sensor.okovision_energie_cumulee"
                source="recorder",
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
        calc_keys  = cfg.get("calc_keys")   # (clé_a, clé_b) pour les champs calculés
        running_sum = 0.0                   # utilisé uniquement pour cumul_cout_eur

        for day in sorted_days:
            try:
                day_date = date.fromisoformat(str(day["date"]))
                start    = datetime.combine(day_date, time.min).replace(tzinfo=tz)
            except (ValueError, TypeError, KeyError):
                continue

            if calc_keys:
                # Champ calculé : valeur = produit des deux clés (ex: conso_kwh × prix_kwh)
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
                    # cumul_* natif : sum = state = valeur cumulée exacte de l'API
                    statistics.append(StatisticData(start=start, state=value, sum=value))
                else:
                    statistics.append(StatisticData(start=start, mean=value))

        if not statistics:
            _LOGGER.warning(
                "OkoVision import_history : '%s' (api_key=%s) – aucune valeur dans les données mensuelles",
                entity_key, api_key,
            )
            continue

        try:
            async_import_statistics(hass, metadata, statistics)
            summary[entity_key] = len(statistics)
            last_val = statistics[-1].sum if has_sum else statistics[-1].mean
            _LOGGER.info(
                "OkoVision import_history : ✓ %-18s → %4d pts | dernier=%s %s | entity=%s",
                entity_key, len(statistics),
                f"{last_val:.2f}", cfg["unit"], entity_id,
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
