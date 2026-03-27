"""Service okovision.import_history – backfill des statistiques OkoVision.

Deux types de statistiques sont créées :

A) STATISTIQUES EXTERNES (source=DOMAIN, id="okovision:xxx")
   → Cumulatives (cumul_kwh, cumul_kg, cumul_cycle, cumul_cout_eur, prix_kwh)
   → Indépendantes du recorder du sensor live → aucun conflit possible
   → À sélectionner dans Paramètres → Énergie (ex: "okovision:cumul_kwh")
   → Mises à jour automatiquement à chaque fetch du DailyCoordinator (~5h)

B) STATISTIQUES RECORDER (source="recorder", id=entity_id)
   → Capteurs journaliers (conso_kwh, conso_kg, nb_cycle, dju) : crénelage
     - 00:00 → 0 (reset), 05:00 → valeur J-1 (données disponibles dès 5h)
   → Températures (tc_ext_max, tc_ext_min) : interpolation douce à minuit
     - 00:00 → moyenne (J-1 / J), 05:00 → valeur J-1
   → Alimentation l'historique des sensors directement dans HA
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
# HA ≥ 2024.11 : StatisticMetaData(mean_type=StatisticMeanType, ...)
# HA < 2024.11 : StatisticMetaData(has_mean=bool, ...)

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
# Courbes cumulatives progressives pour le tableau Énergie HA.
# statistic_id : "okovision:{entity_key}"

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
        "entity_key": "cumul_cout_eur",
        "api_key":    None,
        "calc_keys":  ("conso_kwh", "prix_kwh"),
        "name":       "OkoVision – Coût cumulé chauffage",
        "unit":       "EUR",
        "has_sum":    True,
        "has_mean":   False,
    },
]

# Alias pour la compatibilité (coordinator.py l'importe sous ce nom)
STATISTICS_CONFIG = EXTERNAL_STATS_CONFIG


# ── B) Statistiques RECORDER (source="recorder") ──────────────────────────────
# Sensors journaliers : crénelage (00:00→0, 05:00→valeur J-1)
# Temperatures        : interpolation douce à minuit

RECORDER_DAILY_CONFIG: list[dict[str, Any]] = [
    # state_class=TOTAL avec last_reset → crénelage quotidien
    {"key": "conso_kwh",    "unit": UnitOfEnergy.KILO_WATT_HOUR, "is_total": True},
    {"key": "conso_kg",     "unit": UnitOfMass.KILOGRAMS,         "is_total": True},
    {"key": "conso_ecs_kg", "unit": UnitOfMass.KILOGRAMS,         "is_total": True},
    {"key": "nb_cycle",     "unit": "cycles",                     "is_total": True},
    # state_class=MEASUREMENT → crénelage sans last_reset
    {"key": "dju",          "unit": "DJU",                        "is_total": False},
]

RECORDER_TEMP_CONFIG: list[dict[str, Any]] = [
    # MEASUREMENT → interpolation douce (mean)
    {"key": "tc_ext_max", "unit": UnitOfTemperature.CELSIUS},
    {"key": "tc_ext_min", "unit": UnitOfTemperature.CELSIUS},
]


# ── Push automatique J-1 (appelé par DailyCoordinator) ────────────────────────

async def async_push_daily_stats(
    hass: HomeAssistant,
    daily_data: dict[str, Any],
) -> None:
    """Pousse les statistiques externes pour la date J-1 contenue dans daily_data.

    Appelée automatiquement après chaque fetch réussi du DailyCoordinator.
    Permet de maintenir okovision:cumul_kwh / cumul_cout_eur à jour dans le
    tableau Énergie sans avoir à relancer le service import_history.
    """
    ref_date = daily_data.get("date")
    if not ref_date:
        return

    tz    = dt_util.get_default_time_zone()
    start = datetime.combine(ref_date, time.min).replace(tzinfo=tz)

    for cfg in EXTERNAL_STATS_CONFIG:
        entity_key = cfg["entity_key"]
        api_key    = cfg["api_key"]
        has_sum    = cfg["has_sum"]
        has_mean   = cfg["has_mean"]
        calc_keys  = cfg.get("calc_keys")

        try:
            if calc_keys:
                # cumul_cout_eur : utilise la valeur pré-calculée du coordinator
                raw = daily_data.get("cumul_cout_eur")
            else:
                raw = daily_data.get(api_key)

            if raw is None:
                continue

            value = float(raw)

            metadata = _make_metadata(
                statistic_id=f"{DOMAIN}:{entity_key}",
                source=DOMAIN,
                name=cfg["name"],
                unit=cfg["unit"],
                has_mean=has_mean,
                has_sum=has_sum,
            )

            if has_sum:
                stat = StatisticData(start=start, state=value, sum=value)
            else:
                stat = StatisticData(start=start, mean=value)

            async_add_external_statistics(hass, metadata, [stat])

        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("OkoVision push_daily_stats '%s': %s", entity_key, err)


# ── Import historique complet ──────────────────────────────────────────────────

async def async_import_history(
    hass: HomeAssistant,
    client: OkovisionApiClient,
    entry_id: str,
    years: int = 4,
) -> dict[str, int]:
    """Backfill 4 ans d'historique dans le recorder HA.

    Injecte deux types de statistiques :
    - Externes (okovision:cumul_kwh…)  → tableau Énergie
    - Recorder (entity_id)             → graphiques des sensors journaliers
                                         avec crénelage à minuit et températures interpolées

    Idempotent : peut être relancé sans risque de doublons.
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

    # ── 1b. Ajout d'aujourd'hui (patch du tableau Énergie) ────────────────────
    try:
        today_raw = await client.async_get_today()
        today_str = today.isoformat()
        today_day: dict[str, Any] = {"date": today_str}
        for api_key in ("cumul_kwh", "cumul_kg", "cumul_cycle", "prix_kwh",
                        "conso_kwh", "conso_kg", "conso_ecs_kg", "nb_cycle",
                        "tc_ext_max", "tc_ext_min", "dju"):
            val = today_raw.get(api_key)
            if val is not None:
                today_day[api_key] = val
        if len(today_day) > 1:
            all_days[today_str] = today_day
    except OkovisionApiError as err:
        _LOGGER.warning("OkoVision import_history : données live aujourd'hui non dispo (%s)", err)

    sorted_days = sorted(all_days.values(), key=lambda d: d["date"])
    # Index par date pour accès aux voisins (interpolation températures, crénelage)
    days_by_date: dict[str, dict[str, Any]] = {d["date"]: d for d in sorted_days}

    _LOGGER.info(
        "OkoVision import_history : %d jours collectés – injection en cours…",
        len(sorted_days),
    )

    summary: dict[str, int] = {}

    # ── 2. Statistiques EXTERNES ──────────────────────────────────────────────
    for cfg in EXTERNAL_STATS_CONFIG:
        entity_key  = cfg["entity_key"]
        api_key     = cfg["api_key"]
        has_sum     = cfg["has_sum"]
        has_mean    = cfg["has_mean"]
        calc_keys   = cfg.get("calc_keys")
        statistic_id = f"{DOMAIN}:{entity_key}"

        metadata = _make_metadata(
            statistic_id=statistic_id,
            source=DOMAIN,
            name=cfg["name"],
            unit=cfg["unit"],
            has_mean=has_mean,
            has_sum=has_sum,
        )

        statistics: list[Any] = []
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
                statistics.append(StatisticData(start=start, state=day_value, sum=round(running_sum, 4)))
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

        if statistics:
            try:
                async_add_external_statistics(hass, metadata, statistics)
                summary[entity_key] = len(statistics)
                last_val = statistics[-1].sum if has_sum else statistics[-1].mean
                _LOGGER.info(
                    "OkoVision import ✓ [ext] %-18s → %4d pts | dernier=%s %s",
                    entity_key, len(statistics), f"{last_val:.2f}", cfg["unit"],
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("OkoVision import ✗ [ext] '%s' → %s", entity_key, err)

    # ── 3. Statistiques RECORDER – résolution entity_id ───────────────────────
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    registry    = er.async_get(hass)
    entity_map  = {}   # key → entity_id
    for er_entry in er.async_entries_for_config_entry(registry, entry_id):
        uid = er_entry.unique_id or ""
        if uid.startswith(f"{entry_id}_"):
            key = uid[len(f"{entry_id}_"):]
            entity_map[key] = er_entry.entity_id

    if not entity_map:
        _LOGGER.warning(
            "OkoVision import_history : aucune entité trouvée pour entry_id=%s "
            "– import recorder ignoré (relancer après redémarrage HA)",
            entry_id,
        )
        return summary

    # ── 3a. Sensors journaliers – crénelage (00:00→0, 05:00→valeur J-1) ───────
    for cfg in RECORDER_DAILY_CONFIG:
        key       = cfg["key"]
        is_total  = cfg["is_total"]
        unit      = cfg["unit"]
        entity_id = entity_map.get(key)
        if not entity_id:
            _LOGGER.debug("OkoVision import : entité '%s' introuvable, ignoré", key)
            continue

        metadata = _make_metadata(
            statistic_id=entity_id,
            source="recorder",
            name=entity_id,
            unit=unit,
            has_mean=not is_total,
            has_sum=is_total,
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

            # Crénelage : les données J du jour D sont visibles le jour D+1 dès 5h
            next_day   = day_date + timedelta(days=1)
            midnight   = datetime.combine(next_day, time(0, 0)).replace(tzinfo=tz)
            five_am    = datetime.combine(next_day, time(5, 0)).replace(tzinfo=tz)

            if is_total:
                # 00:00 → remise à 0 (nouveau jour)
                statistics.append(StatisticData(
                    start=midnight, state=0.0, sum=0.0, last_reset=midnight,
                ))
                # 05:00 → valeur J-1 disponible
                statistics.append(StatisticData(
                    start=five_am, state=value, sum=value, last_reset=midnight,
                ))
            else:
                # MEASUREMENT (dju) : crénelage sans last_reset
                statistics.append(StatisticData(start=midnight, mean=0.0))
                statistics.append(StatisticData(start=five_am,  mean=value))

        if statistics:
            try:
                async_import_statistics(hass, metadata, statistics)
                summary[f"recorder_{key}"] = len(statistics) // 2
                _LOGGER.info(
                    "OkoVision import ✓ [rec] %-18s → %4d jours | entity=%s",
                    key, len(statistics) // 2, entity_id,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("OkoVision import ✗ [rec] '%s' → %s", key, err)

    # ── 3b. Températures – interpolation douce à minuit ───────────────────────
    for cfg in RECORDER_TEMP_CONFIG:
        key       = cfg["key"]
        unit      = cfg["unit"]
        entity_id = entity_map.get(key)
        if not entity_id:
            _LOGGER.debug("OkoVision import : entité '%s' introuvable, ignoré", key)
            continue

        metadata = _make_metadata(
            statistic_id=entity_id,
            source="recorder",
            name=entity_id,
            unit=unit,
            has_mean=True,
            has_sum=False,
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

            # Valeur du jour suivant pour interpolation à minuit
            next_date_str = (day_date + timedelta(days=1)).isoformat()
            next_day_raw  = days_by_date.get(next_date_str, {}).get(key)
            next_value    = float(next_day_raw) if next_day_raw is not None else value

            next_day = day_date + timedelta(days=1)
            midnight = datetime.combine(next_day, time(0, 0)).replace(tzinfo=tz)
            five_am  = datetime.combine(next_day, time(5, 0)).replace(tzinfo=tz)

            # Minuit : interpolation entre valeur J et valeur J+1 (transition douce)
            interp = round((value + next_value) / 2.0, 2)
            statistics.append(StatisticData(start=midnight, mean=interp))

            # 05:00 : valeur J-1 disponible (stable jusqu'au prochain minuit)
            statistics.append(StatisticData(start=five_am,  mean=value))

        if statistics:
            try:
                async_import_statistics(hass, metadata, statistics)
                summary[f"recorder_{key}"] = len(statistics) // 2
                _LOGGER.info(
                    "OkoVision import ✓ [rec] %-18s → %4d jours | entity=%s",
                    key, len(statistics) // 2, entity_id,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("OkoVision import ✗ [rec] '%s' → %s", key, err)

    _LOGGER.info(
        "OkoVision import_history : terminé – %d séries injectées",
        len(summary),
    )
    return summary
