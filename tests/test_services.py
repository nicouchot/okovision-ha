"""Tests unitaires – services.py (reconstruction cumul_cout, configs)."""
from __future__ import annotations

import pytest

from custom_components.okovision.services import (
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
