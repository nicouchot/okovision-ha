"""Tests unitaires – OkovisionCoordinator (logique métier sans HA)."""
from __future__ import annotations

import pytest

from custom_components.okovision.coordinator import _merge_with_previous, _parse_date


# ── _parse_date ───────────────────────────────────────────────────────────────

class TestParseDate:
    def test_valid_iso(self):
        from datetime import date
        assert _parse_date("2024-03-15") == date(2024, 3, 15)

    def test_none_returns_none(self):
        assert _parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_date("") is None

    def test_invalid_format_returns_none(self):
        assert _parse_date("15/03/2024") is None

    def test_integer_string(self):
        assert _parse_date("not-a-date") is None


# ── _merge_with_previous ──────────────────────────────────────────────────────

class TestMergeWithPrevious:
    def test_no_previous_returns_new(self):
        new = {"a": 1, "b": None}
        assert _merge_with_previous(new, None) == new

    def test_fills_none_with_previous(self):
        new      = {"conso_kg": None, "dju": 5.0}
        previous = {"conso_kg": 12.5, "dju": 3.0}
        result   = _merge_with_previous(new, previous)
        assert result["conso_kg"] == 12.5   # récupéré du cache
        assert result["dju"] == 5.0         # valeur réelle conservée

    def test_nullable_keys_not_filled(self):
        """Les clés de _NULLABLE_KEYS restent None même si previous a une valeur."""
        new      = {"date": None, "silo_error": None, "conso_kg": None}
        previous = {"date": "2024-01-01", "silo_error": "err", "conso_kg": 10.0}
        result   = _merge_with_previous(new, previous)
        assert result["date"] is None        # nullable → pas de merge
        assert result["silo_error"] is None  # nullable → pas de merge
        assert result["conso_kg"] == 10.0   # non-nullable → merge

    def test_zero_is_not_replaced(self):
        """0 est une valeur valide et ne doit pas être remplacé par le cache."""
        new      = {"conso_kg": 0.0}
        previous = {"conso_kg": 12.5}
        result   = _merge_with_previous(new, previous)
        assert result["conso_kg"] == 0.0

    def test_empty_previous_returns_new(self):
        new = {"a": None, "b": 1}
        assert _merge_with_previous(new, {}) == new
