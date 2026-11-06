"""Tests unitaires – services.py (reconstruction cumul_cout, configs, reset_history, températures)."""
from __future__ import annotations

from datetime import date, datetime, time
import pytest

from custom_components.okovision.services import (
    DOMAIN,
    EXTERNAL_STATS_CONFIG,
    RECORDER_CUMUL_CONFIG,
    RECORDER_DAILY_CONFIG,
    RECORDER_SNAPSHOT_CONFIG,
    RECORDER_TEMP_CONFIG,
)


# ── Intégrité des configs ─────────────────────────────────────────────────────

class TestConfigs:
    def test_external_stats_have_required_keys(self):
        for cfg in EXTERNAL_STATS_CONFIG:
            assert "entity_key" in cfg
            assert "api_key" in cfg
            assert "unit" in cfg
            assert "has_sum" in cfg

    def test_external_stats_inclut_cumul_kg(self):
        """okovision:cumul_kg existe, en kg, avec sum (variation journalière exploitable)."""
        cfg = {c["entity_key"]: c for c in EXTERNAL_STATS_CONFIG}
        assert "cumul_kg" in cfg
        assert cfg["cumul_kg"]["api_key"] == "cumul_kg"
        assert cfg["cumul_kg"]["unit"] == "kg"
        assert cfg["cumul_kg"]["has_sum"] is True
        assert cfg["cumul_kg"]["has_mean"] is False

    def test_external_stats_cles_uniques(self):
        keys = [c["entity_key"] for c in EXTERNAL_STATS_CONFIG]
        assert len(keys) == len(set(keys))

    def test_recorder_daily_have_required_keys(self):
        for cfg in RECORDER_DAILY_CONFIG:
            assert "key" in cfg
            assert "unit" in cfg
            assert "is_total" in cfg

    def test_recorder_cumul_have_required_keys(self):
        for cfg in RECORDER_CUMUL_CONFIG:
            assert "key" in cfg
            assert "api_key" in cfg
            assert "unit" in cfg

    def test_recorder_snapshot_have_required_keys(self):
        for cfg in RECORDER_SNAPSHOT_CONFIG:
            assert "key" in cfg
            assert "api_key" in cfg
            assert "unit" in cfg

    def test_snapshot_entity_keys(self):
        keys = {cfg["key"] for cfg in RECORDER_SNAPSHOT_CONFIG}
        assert "silo_remains_kg"    in keys
        assert "silo_percent"       in keys
        assert "ashtray_remains_kg" in keys
        assert "ashtray_percent"    in keys
        assert "prix_kg"            in keys
        assert "prix_kwh"           in keys

    def test_snapshot_api_keys(self):
        api_keys = {cfg["api_key"] for cfg in RECORDER_SNAPSHOT_CONFIG}
        assert "silo_pellets_restants"          in api_keys
        assert "silo_niveau"                    in api_keys
        assert "cendrier_capacite_restante"     in api_keys
        assert "cendrier_niveau_de_remplissage" in api_keys


# ── Reconstruction cumul_cout ─────────────────────────────────────────────────

class TestCumulCoutReconstruction:
    """Vérifie la logique de la section 1c d'async_import_history."""

    def _run(self, all_days: dict) -> dict:
        """Reproduit la section 1c de services.py."""
        running_cout = 0.0
        for day_str in sorted(all_days.keys()):
            day = all_days[day_str]
            if day.get("cumul_cout") is not None:
                running_cout = float(day["cumul_cout"])
            elif day.get("conso_kwh") is not None and day.get("prix_kwh") is not None:
                running_cout = round(
                    running_cout + float(day["conso_kwh"]) * float(day["prix_kwh"]), 4
                )
                day["cumul_cout"] = running_cout
        return all_days

    def test_calcul_depuis_zero(self):
        days = {
            "2024-01-01": {"date": "2024-01-01", "conso_kwh": 10.0, "prix_kwh": 0.10},
            "2024-01-02": {"date": "2024-01-02", "conso_kwh": 20.0, "prix_kwh": 0.10},
        }
        result = self._run(days)
        assert result["2024-01-01"]["cumul_cout"] == pytest.approx(1.0)
        assert result["2024-01-02"]["cumul_cout"] == pytest.approx(3.0)

    def test_ancrage_sur_valeur_reelle(self):
        """Si un jour a cumul_cout réel, il sert d'ancre pour les suivants."""
        days = {
            "2024-01-01": {"date": "2024-01-01", "cumul_cout": 100.0},
            "2024-01-02": {"date": "2024-01-02", "conso_kwh": 10.0, "prix_kwh": 0.10},
        }
        result = self._run(days)
        assert result["2024-01-01"]["cumul_cout"] == 100.0   # valeur réelle inchangée
        assert result["2024-01-02"]["cumul_cout"] == pytest.approx(101.0)

    def test_jour_sans_donnees_ignore(self):
        """Un jour sans conso_kwh ni prix_kwh ni cumul_cout ne plante pas."""
        days = {
            "2024-01-01": {"date": "2024-01-01"},
            "2024-01-02": {"date": "2024-01-02", "conso_kwh": 10.0, "prix_kwh": 0.10},
        }
        result = self._run(days)
        assert "cumul_cout" not in result["2024-01-01"]
        assert result["2024-01-02"]["cumul_cout"] == pytest.approx(1.0)

    def test_valeur_reelle_non_ecrasee(self):
        """cumul_cout déjà présent dans un jour ne doit pas être recalculé."""
        days = {
            "2024-01-01": {"date": "2024-01-01", "cumul_cout": 50.0,
                           "conso_kwh": 999.0, "prix_kwh": 999.0},
        }
        result = self._run(days)
        assert result["2024-01-01"]["cumul_cout"] == 50.0


# ── Logique de collecte des IDs pour reset_history ────────────────────────────

class TestResetHistoryIdCollection:
    """Vérifie la logique de construction de all_ids dans async_reset_history."""

    def _build_all_ids(self, db_ids: list[str], fallback_ids: list[str]) -> list[str]:
        """Reproduit la déduplication union de reset_history."""
        return list(dict.fromkeys([*db_ids, *fallback_ids]))

    def test_db_ids_prioritaires(self):
        """Les IDs de la base apparaissent en premier."""
        db       = ["sensor.okovision_cumul_kwh", "sensor.okovision_old_name"]
        fallback = ["sensor.okovision_cumul_kwh", "okovision:cumul_kwh"]
        result   = self._build_all_ids(db, fallback)
        assert result[0] == "sensor.okovision_cumul_kwh"
        assert "sensor.okovision_old_name" in result
        assert "okovision:cumul_kwh" in result

    def test_pas_de_doublons(self):
        """Un ID présent dans db et fallback n'apparaît qu'une fois."""
        db       = ["sensor.okovision_cumul_kwh"]
        fallback = ["sensor.okovision_cumul_kwh", "okovision:cumul_kwh"]
        result   = self._build_all_ids(db, fallback)
        assert result.count("sensor.okovision_cumul_kwh") == 1

    def test_ancien_id_inclus(self):
        """Un ancien statistic_id (non présent dans le registre) est conservé."""
        db       = ["sensor.okovision_cumul_cout_eur",   # ancien nom
                    "sensor.okovision_cumul_cout_chauffage"]  # nom actuel
        fallback = ["sensor.okovision_cumul_cout_chauffage"]
        result   = self._build_all_ids(db, fallback)
        assert "sensor.okovision_cumul_cout_eur" in result
        assert "sensor.okovision_cumul_cout_chauffage" in result

    def test_liste_vide_db_utilise_fallback(self):

        """Si async_list_statistic_ids renvoie vide, le fallback seul est utilisé."""
        db       = []
        fallback = ["okovision:cumul_kwh", "sensor.okovision_cumul_kg"]
        result   = self._build_all_ids(db, fallback)
        assert result == fallback

    def test_filtre_prefixe_domaine(self):
        """Seuls les IDs du domaine okovision passent le filtre."""
        all_stats = [
            {"statistic_id": "okovision:cumul_kwh"},
            {"statistic_id": "sensor.okovision_cumul_kg"},
            {"statistic_id": "sensor.autre_integration_energie"},
            {"statistic_id": "binary_sensor.okovision_cendrier_a_vider"},
        ]
        domain = DOMAIN
        filtered = [
            s["statistic_id"] for s in all_stats
            if (
                s["statistic_id"].startswith(f"{domain}:")
                or s["statistic_id"].startswith(f"sensor.{domain}_")
                or s["statistic_id"].startswith(f"binary_sensor.{domain}_")
            )
        ]
        assert "okovision:cumul_kwh"                    in filtered
        assert "sensor.okovision_cumul_kg"              in filtered
        assert "binary_sensor.okovision_cendrier_a_vider" in filtered
        assert "sensor.autre_integration_energie"       not in filtered


# ── Import des températures – un point par jour ───────────────────────────────

class TestTemperatureImport:
    """Vérifie que la section 6 produit un seul point par jour à minuit."""

    def _build_stats(self, sorted_days, key, tz=None):
        """Reproduit la logique de la section 6 d'async_import_history."""
        import datetime as dt
        if tz is None:
            tz = dt.timezone.utc
        statistics = []
        for day in sorted_days:
            try:
                day_date = date.fromisoformat(str(day["date"]))
                midnight = datetime.combine(day_date, time.min).replace(tzinfo=tz)
            except (ValueError, TypeError, KeyError):
                continue
            raw = day.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (ValueError, TypeError):
                continue
            statistics.append({"start": midnight, "mean": value})
        return statistics

    def test_un_point_par_jour(self):
        """Chaque jour produit exactement un StatisticData."""
        days = [
            {"date": "2024-01-01", "tc_ext_max": 15.0},
            {"date": "2024-01-02", "tc_ext_max": 18.0},
            {"date": "2024-01-03", "tc_ext_max": 12.0},
        ]
        stats = self._build_stats(days, "tc_ext_max")
        assert len(stats) == 3

    def test_point_a_minuit_du_jour(self):
        """Le point est placé à minuit du jour concerné (pas du lendemain)."""
        import datetime as dt
        days = [{"date": "2024-03-15", "tc_ext_max": 20.0}]
        stats = self._build_stats(days, "tc_ext_max")
        assert len(stats) == 1
        expected_midnight = datetime(2024, 3, 15, 0, 0, tzinfo=dt.timezone.utc)
        assert stats[0]["start"] == expected_midnight

    def test_valeur_directe_sans_interpolation(self):
        """La valeur enregistrée est celle de l'API, sans interpolation avec le jour suivant."""
        days = [
            {"date": "2024-01-01", "tc_ext_max": 10.0},
            {"date": "2024-01-02", "tc_ext_max": 20.0},
        ]
        stats = self._build_stats(days, "tc_ext_max")
        assert stats[0]["mean"] == 10.0   # pas (10+20)/2 = 15
        assert stats[1]["mean"] == 20.0

    def test_pas_de_doublon_5h(self):
        """Aucun point à 5h – l'ancienne logique créait 2 points par jour."""
        import datetime as dt
        days = [{"date": "2024-01-01", "tc_ext_max": 15.0}]
        stats = self._build_stats(days, "tc_ext_max")
        five_am = datetime(2024, 1, 2, 5, 0, tzinfo=dt.timezone.utc)
        starts = [s["start"] for s in stats]
        assert five_am not in starts

    def test_jour_sans_valeur_ignore(self):
        """Un jour sans la clé de température n'est pas inséré."""
        days = [
            {"date": "2024-01-01"},
            {"date": "2024-01-02", "tc_ext_max": 18.0},
        ]
        stats = self._build_stats(days, "tc_ext_max")
        assert len(stats) == 1
        assert stats[0]["mean"] == 18.0


# ── Push quotidien des statistiques externes ──────────────────────────────────

class TestPushDailyStats:
    """Vérifie qu'async_push_daily_stats date chaque statistique du jour J (minuit)."""

    def _run(self, monkeypatch, daily_data):
        import asyncio
        from custom_components.okovision import services

        calls = []
        monkeypatch.setattr(services, "_make_metadata", lambda **kw: kw)
        monkeypatch.setattr(services, "StatisticData", lambda **kw: kw)
        monkeypatch.setattr(
            services, "async_add_external_statistics",
            lambda hass, metadata, stats: calls.append((metadata, stats)),
        )
        asyncio.run(services.async_push_daily_stats(None, daily_data))
        return {meta["statistic_id"]: (meta, stats) for meta, stats in calls}

    def test_cumul_kg_pousse_a_minuit_du_jour(self, monkeypatch):
        import datetime as dt
        pushed = self._run(monkeypatch, {
            "date": date(2026, 11, 5),
            "cumul_kwh": 25511.05, "cumul_cout_eur": 3704.69, "cumul_kg": 7076.94,
        })
        assert f"{DOMAIN}:cumul_kg" in pushed
        meta, stats = pushed[f"{DOMAIN}:cumul_kg"]
        assert meta["unit"] == "kg"
        assert meta["source"] == DOMAIN
        assert len(stats) == 1
        assert stats[0]["start"] == datetime(2026, 11, 5, 0, 0, tzinfo=dt.timezone.utc)
        assert stats[0]["sum"] == pytest.approx(7076.94)

    def test_meme_date_que_cumul_kwh(self, monkeypatch):
        """kg et kWh partagent la même date : plus de décalage d'un jour entre eux."""
        pushed = self._run(monkeypatch, {
            "date": date(2026, 11, 5), "cumul_kwh": 25511.05, "cumul_kg": 7076.94,
        })
        assert pushed[f"{DOMAIN}:cumul_kg"][1][0]["start"] == pushed[f"{DOMAIN}:cumul_kwh"][1][0]["start"]

    def test_cumul_kg_absent_ignore(self, monkeypatch):
        pushed = self._run(monkeypatch, {"date": date(2026, 11, 5), "cumul_kwh": 25511.05})
        assert f"{DOMAIN}:cumul_kg" not in pushed
        assert f"{DOMAIN}:cumul_kwh" in pushed

    def test_sans_date_rien_pousse(self, monkeypatch):
        pushed = self._run(monkeypatch, {"cumul_kg": 7076.94})
        assert pushed == {}
