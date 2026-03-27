"""Services OkoVision : import_history et reset_history.

Deux types de statistiques sont gérées :

A) STATISTIQUES EXTERNES (source=DOMAIN, id="okovision:xxx")
   → Uniquement cumul_kwh et cumul_cout_eur (tableau Énergie HA)
   → Mises à jour automatiquement après chaque fetch du DailyCoordinator

B) STATISTIQUES RECORDER (source="recorder", id=entity_id)
   → Sensors journaliers (conso_*,  nb_cycle, dju)   : crénelage quotidien
   → Sensors cumulatifs (cumul_*)                     : courbe progressive
   → Températures (tc_ext_*)                          : interpolation douce
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.const import UnitOfEnergy, UnitOfMass, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import OkovisionApiClient, OkovisionApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ── Compatibilité HA recorder API ─────────────────────────────────────────────
try:
    from homeassistant.components.recorder.statistics import (
        StatisticData,
        StatisticMeanType,
        StatisticMetaData,
        async_add_external_statistics,
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
        async_add_external_statistics,
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


# ── A) Statistiques EXTERNES (source=DOMAIN) ──────────────────────────────────
# Seulement cumul_kwh et cumul_cout_eur pour le tableau Énergie HA.

EXTERNAL_STATS_CONFIG: list[dict[str, Any]] = [
    {
        "entity_key": "cumul_kwh",
        "api_key":    "cumul_kwh",
        "name":       "OkoVision – Énergie cumulée",
        "unit":       UnitOfEnergy.KILO_WATT_HOUR,
        "has_sum":    True,
        "has_mean":   False,
    },
    {
        # Coût cumulé – valeur directe depuis l'API (champ cumul_cout)
        "entity_key": "cumul_cout_eur",
        "api_key":    "cumul_cout",
        "name":       "OkoVision – Coût cumulé chauffage",
        "unit":       "EUR",
        "has_sum":    True,
        "has_mean":   False,
    },
]

# Alias utilisé par coordinator.py
STATISTICS_CONFIG = EXTERNAL_STATS_CONFIG


# ── B) Statistiques RECORDER – sensors journaliers (crénelage) ────────────────
# 00:00 → 0 (reset), 05:00 → valeur J-1

RECORDER_DAILY_CONFIG: list[dict[str, Any]] = [
    {"key": "conso_kwh",    "unit": UnitOfEnergy.KILO_WATT_HOUR, "is_total": True},
    {"key": "conso_kg",     "unit": UnitOfMass.KILOGRAMS,         "is_total": True},
    {"key": "conso_ecs_kg", "unit": UnitOfMass.KILOGRAMS,         "is_total": True},
    {"key": "nb_cycle",     "unit": "cycles",                     "is_total": True},
    {"key": "dju",          "unit": "DJU",                        "is_total": False},
]

# ── C) Statistiques RECORDER – sensors cumulatifs (courbe progressive) ────────
# Une entrée par jour à minuit, mean = valeur cumulative absolue.

RECORDER_CUMUL_CONFIG: list[dict[str, Any]] = [
    {"key": "cumul_kwh",      "api_key": "cumul_kwh",   "unit": UnitOfEnergy.KILO_WATT_HOUR, "calc": False},
    {"key": "cumul_kg",       "api_key": "cumul_kg",    "unit": UnitOfMass.KILOGRAMS,         "calc": False},
    {"key": "cumul_cycle",    "api_key": "cumul_cycle", "unit": "cycles",                     "calc": False},
    {"key": "cumul_cout_eur", "api_key": "cumul_cout",    "unit": "EUR",                        "calc": False},
]

# ── D) Statistiques RECORDER – températures (interpolation douce) ─────────────

RECORDER_TEMP_CONFIG: list[dict[str, Any]] = [
    {"key": "tc_ext_max", "unit": UnitOfTemperature.CELSIUS},
    {"key": "tc_ext_min", "unit": UnitOfTemperature.CELSIUS},
]


# ── Push automatique J-1 (appelé par DailyCoordinator) ────────────────────────

async def async_push_daily_stats(
    hass: HomeAssistant,
    daily_data: dict[str, Any],
) -> None:
    """Pousse les statistiques externes (cumul_kwh, cumul_cout_eur) pour J-1.

    Appelée automatiquement après chaque fetch réussi du DailyCoordinator.
    """
    ref_date = daily_data.get("date")
    if not ref_date:
        return

    tz    = dt_util.get_default_time_zone()
    start = datetime.combine(ref_date, time.min).replace(tzinfo=tz)

    for cfg in EXTERNAL_STATS_CONFIG:
        entity_key = cfg["entity_key"]

        try:
            # Le coordinator stocke les valeurs sous entity_key (ex: "cumul_cout_eur")
            raw = daily_data.get(entity_key)

            if raw is None:
                continue

            value    = float(raw)
            metadata = _make_metadata(
                statistic_id=f"{DOMAIN}:{entity_key}",
                source=DOMAIN,
                name=cfg["name"],
                unit=cfg["unit"],
                has_mean=cfg["has_mean"],
                has_sum=cfg["has_sum"],
            )
            stat = StatisticData(start=start, state=value, sum=value)
            async_add_external_statistics(hass, metadata, [stat])

        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("OkoVision push_daily_stats '%s': %s", entity_key, err)


# ── Service import_history ─────────────────────────────────────────────────────

async def async_import_history(
    hass: HomeAssistant,
    client: OkovisionApiClient,
    entry_id: str,
    years: int = 4,
) -> dict[str, int]:
    """Backfill 4 ans d'historique dans le recorder HA.

    - Externes   : okovision:cumul_kwh, okovision:cumul_cout_eur
    - Recorder   : crénelage (conso_*, nb_cycle, dju), courbe (cumul_*), températures
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
                "OkoVision import_history : %02d/%04d ✓ (%d/%d – %d jours)",
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

    # ── 1b. Données du jour en cours ──────────────────────────────────────────
    try:
        today_raw = await client.async_get_today()
        today_str = today.isoformat()
        today_day: dict[str, Any] = {"date": today_str}
        for k in ("cumul_kwh", "cumul_kg", "cumul_cycle", "prix_kwh",
                  "conso_kwh", "conso_kg", "conso_ecs_kg", "nb_cycle",
                  "tc_ext_max", "tc_ext_min", "dju"):
            v = today_raw.get(k)
            if v is not None:
                today_day[k] = v
        if len(today_day) > 1:
            all_days[today_str] = today_day
    except OkovisionApiError as err:
        _LOGGER.warning("OkoVision import_history : données live non dispo (%s)", err)

    sorted_days   = sorted(all_days.values(), key=lambda d: d["date"])
    days_by_date  = {d["date"]: d for d in sorted_days}

    _LOGGER.info("OkoVision import_history : %d jours – injection…", len(sorted_days))
    summary: dict[str, int] = {}

    # ── 2. Statistiques EXTERNES ──────────────────────────────────────────────
    for cfg in EXTERNAL_STATS_CONFIG:
        entity_key   = cfg["entity_key"]
        api_key      = cfg["api_key"]
        statistic_id = f"{DOMAIN}:{entity_key}"

        metadata = _make_metadata(
            statistic_id=statistic_id,
            source=DOMAIN,
            name=cfg["name"],
            unit=cfg["unit"],
            has_mean=cfg["has_mean"],
            has_sum=cfg["has_sum"],
        )

        statistics: list[Any] = []

        for day in sorted_days:
            try:
                day_date = date.fromisoformat(str(day["date"]))
                start    = datetime.combine(day_date, time.min).replace(tzinfo=tz)
            except (ValueError, TypeError, KeyError):
                continue

            raw = day.get(api_key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (ValueError, TypeError):
                continue
            statistics.append(StatisticData(start=start, state=value, sum=value))

        if statistics:
            try:
                async_add_external_statistics(hass, metadata, statistics)
                summary[entity_key] = len(statistics)
                _LOGGER.info(
                    "OkoVision import ✓ [ext] %-18s → %4d pts | dernier=%.2f %s",
                    entity_key, len(statistics), statistics[-1].sum, cfg["unit"],
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("OkoVision import ✗ [ext] '%s' → %s", entity_key, err)

    # ── 3. Résolution entity_id via entity registry ────────────────────────────
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    registry   = er.async_get(hass)
    entity_map: dict[str, str] = {}
    for er_entry in er.async_entries_for_config_entry(registry, entry_id):
        uid = er_entry.unique_id or ""
        if uid.startswith(f"{entry_id}_"):
            entity_map[uid[len(f"{entry_id}_"):]] = er_entry.entity_id

    if not entity_map:
        _LOGGER.warning(
            "OkoVision import_history : aucune entité trouvée (entry_id=%s) "
            "– import recorder ignoré, relancer après redémarrage HA",
            entry_id,
        )
        return summary

    # ── 4. Sensors journaliers – crénelage (00:00→0, 05:00→valeur J-1) ────────
    for cfg in RECORDER_DAILY_CONFIG:
        key       = cfg["key"]
        is_total  = cfg["is_total"]
        entity_id = entity_map.get(key)
        if not entity_id:
            _LOGGER.debug("OkoVision import : entité '%s' introuvable, ignoré", key)
            continue

        metadata = _make_metadata(
            statistic_id=entity_id, source="recorder", name=entity_id,
            unit=cfg["unit"], has_mean=not is_total, has_sum=is_total,
        )
        statistics = []

        for day in sorted_days:
            try:
                day_date = date.fromisoformat(str(day["date"]))
            except (ValueError, TypeError, KeyError):
                continue
            raw = day.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (ValueError, TypeError):
                continue

            next_day = day_date + timedelta(days=1)
            midnight = datetime.combine(next_day, time(0, 0)).replace(tzinfo=tz)
            five_am  = datetime.combine(next_day, time(5, 0)).replace(tzinfo=tz)

            if is_total:
                statistics.append(StatisticData(start=midnight, state=0.0,   sum=0.0,   last_reset=midnight))
                statistics.append(StatisticData(start=five_am,  state=value, sum=value, last_reset=midnight))
            else:
                statistics.append(StatisticData(start=midnight, mean=0.0))
                statistics.append(StatisticData(start=five_am,  mean=value))

        if statistics:
            try:
                async_import_statistics(hass, metadata, statistics)
                summary[f"recorder_{key}"] = len(statistics) // 2
                _LOGGER.info(
                    "OkoVision import ✓ [rec] %-18s → %4d jours | %s",
                    key, len(statistics) // 2, entity_id,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("OkoVision import ✗ [rec] '%s' → %s", key, err)

    # ── 5. Sensors cumulatifs – courbe progressive (mean par jour) ─────────────
    for cfg in RECORDER_CUMUL_CONFIG:
        key       = cfg["key"]
        entity_id = entity_map.get(key)
        if not entity_id:
            _LOGGER.debug("OkoVision import : entité '%s' introuvable, ignoré", key)
            continue

        metadata = _make_metadata(
            statistic_id=entity_id, source="recorder", name=entity_id,
            unit=cfg["unit"], has_mean=True, has_sum=False,
        )
        statistics = []

        for day in sorted_days:
            try:
                day_date = date.fromisoformat(str(day["date"]))
                midnight = datetime.combine(day_date, time.min).replace(tzinfo=tz)
            except (ValueError, TypeError, KeyError):
                continue

            raw   = day.get(cfg["api_key"])
            value = float(raw) if raw is not None else None

            if value is None:
                continue
            statistics.append(StatisticData(start=midnight, mean=value))

        if statistics:
            try:
                async_import_statistics(hass, metadata, statistics)
                summary[f"recorder_{key}"] = len(statistics)
                _LOGGER.info(
                    "OkoVision import ✓ [rec] %-18s → %4d jours | %s",
                    key, len(statistics), entity_id,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("OkoVision import ✗ [rec] '%s' → %s", key, err)

    # ── 6. Températures – interpolation douce à minuit ────────────────────────
    for cfg in RECORDER_TEMP_CONFIG:
        key       = cfg["key"]
        entity_id = entity_map.get(key)
        if not entity_id:
            _LOGGER.debug("OkoVision import : entité '%s' introuvable, ignoré", key)
            continue

        metadata = _make_metadata(
            statistic_id=entity_id, source="recorder", name=entity_id,
            unit=cfg["unit"], has_mean=True, has_sum=False,
        )
        statistics = []

        for day in sorted_days:
            try:
                day_date = date.fromisoformat(str(day["date"]))
            except (ValueError, TypeError, KeyError):
                continue
            raw = day.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (ValueError, TypeError):
                continue

            next_date_str = (day_date + timedelta(days=1)).isoformat()
            next_raw      = days_by_date.get(next_date_str, {}).get(key)
            next_value    = float(next_raw) if next_raw is not None else value

            next_day = day_date + timedelta(days=1)
            midnight = datetime.combine(next_day, time(0, 0)).replace(tzinfo=tz)
            five_am  = datetime.combine(next_day, time(5, 0)).replace(tzinfo=tz)

            statistics.append(StatisticData(start=midnight, mean=round((value + next_value) / 2.0, 2)))
            statistics.append(StatisticData(start=five_am,  mean=value))

        if statistics:
            try:
                async_import_statistics(hass, metadata, statistics)
                summary[f"recorder_{key}"] = len(statistics) // 2
                _LOGGER.info(
                    "OkoVision import ✓ [rec] %-18s → %4d jours | %s",
                    key, len(statistics) // 2, entity_id,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("OkoVision import ✗ [rec] '%s' → %s", key, err)

    _LOGGER.info("OkoVision import_history : terminé – %d séries injectées", len(summary))
    return summary


# ── Service reset_history ──────────────────────────────────────────────────────

async def async_reset_history(
    hass: HomeAssistant,
    entry_id: str,
) -> int:
    """Supprime toutes les statistiques OkoVision (externes + recorder entities).

    Destiné à la phase de développement pour repartir de zéro.
    N'efface pas les états actuels des entités, seulement leur historique
    statistique dans le recorder.
    """
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    # Statistiques externes
    ext_ids = [f"{DOMAIN}:{cfg['entity_key']}" for cfg in EXTERNAL_STATS_CONFIG]

    # Entity_ids de toutes les entités OkoVision
    registry   = er.async_get(hass)
    entity_ids = [e.entity_id for e in er.async_entries_for_config_entry(registry, entry_id)]

    all_ids = [*ext_ids, *entity_ids]

    try:
        # Utilise le service recorder.clear_statistics qui gère lui-même
        # le thread du recorder (évite "unsafe call not in recorder thread")
        await hass.services.async_call(
            "recorder",
            "clear_statistics",
            {"statistic_ids": all_ids},
            blocking=True,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.error(
            "OkoVision reset_history : échec suppression statistiques – %s: %s",
            type(err).__name__, err,
            exc_info=True,
        )
        raise

    _LOGGER.info(
        "OkoVision reset_history : %d séries supprimées (%d ext + %d entities)",
        len(all_ids), len(ext_ids), len(entity_ids),
    )
    return len(all_ids)
