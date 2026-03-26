"""Okovision API client (ha_api.php)."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class OkovisionApiError(Exception):
    """Base exception for Okovision API errors."""


class OkovisionAuthError(OkovisionApiError):
    """Authentication error (invalid token)."""


class OkovisionConnectionError(OkovisionApiError):
    """Connection / network error."""


class OkovisionApiClient:
    """Client pour l'API ha_api.php d'OkoVision.

    Authentification : token passé en paramètre GET (?token=XXXX).
    Le token correspond aux 12 premiers caractères de la constante TOKEN
    définie dans config.php côté serveur.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialise le client.

        Args:
            base_url: URL complète vers ha_api.php,
                      ex: http://192.168.1.100/okovision/ha_api.php
            token:    12 premiers caractères du TOKEN serveur.
            session:  Session aiohttp partagée par HA.
        """
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session = session

    async def _request(self, params: dict[str, Any]) -> Any:
        """Effectue une requête GET authentifiée vers ha_api.php."""
        params["token"] = self._token
        try:
            async with self._session.get(
                self._base_url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 401:
                    raise OkovisionAuthError("Token invalide ou accès refusé")
                response.raise_for_status()
                data = await response.json(content_type=None)
                if isinstance(data, dict) and "error" in data:
                    raise OkovisionApiError(f"Erreur API: {data['error']}")
                return data
        except aiohttp.ClientConnectorError as err:
            raise OkovisionConnectionError(
                f"Impossible de contacter {self._base_url}: {err}"
            ) from err
        except aiohttp.ServerTimeoutError as err:
            raise OkovisionConnectionError(
                f"Timeout lors de la connexion à {self._base_url}"
            ) from err

    async def async_test_connection(self) -> bool:
        """Teste la connexion et le token via action=status."""
        await self._request({"action": "status"})
        return True

    async def async_get_today(self) -> dict[str, Any]:
        """Récupère les données live du jour + état silo + cendrier.

        Réponse (action=today) :
        {
          "date":         "2024-01-15",
          "dju":          5.2,
          "conso_kg":     12.5,
          "conso_ecs_kg": 2.1,
          "conso_kwh":    65.3,
          "nb_cycle":     8,
          "tc_ext_max":   8.5,
          "tc_ext_min":   2.1,
          "silo": {
            "remains_kg":     450,
            "capacity_kg":    600,
            "percent":        75,
            "last_fill_date": "2024-01-01"
          },
          "ashtray": {
            "remains_kg":      2.5,
            "capacity_kg":     5.0,
            "percent":         50,
            "needs_emptying":  false,
            "last_empty_date": "2023-12-20"
          }
        }
        """
        return await self._request({"action": "today"})

    async def async_get_status(self) -> dict[str, Any]:
        """Récupère uniquement l'état du silo et du cendrier (action=status)."""
        return await self._request({"action": "status"})

    async def async_get_daily(self, date: str) -> dict[str, Any]:
        """Récupère le résumé d'un jour précis (action=daily&date=YYYY-MM-DD)."""
        return await self._request({"action": "daily", "date": date})

    async def async_get_monthly(self, month: int, year: int) -> dict[str, Any]:
        """Récupère les données d'un mois complet (action=monthly)."""
        return await self._request({"action": "monthly", "month": month, "year": year})
