"""Okovision API client."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class OkovisionApiError(Exception):
    """Base exception for Okovision API errors."""


class OkovisionAuthError(OkovisionApiError):
    """Authentication error."""


class OkovisionConnectionError(OkovisionApiError):
    """Connection error."""


class OkovisionApiClient:
    """Client for the Okovision local API."""

    def __init__(
        self,
        host: str,
        api_key: str,
        session: aiohttp.ClientSession,
        port: int = 8080,
    ) -> None:
        """Initialize the API client."""
        self._base_url = f"http://{host}:{port}"
        self._api_key = api_key
        self._session = session
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated HTTP request."""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method, url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10), **kwargs
            ) as response:
                if response.status == 401:
                    raise OkovisionAuthError("Invalid API key")
                if response.status == 403:
                    raise OkovisionAuthError("Access denied")
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientConnectorError as err:
            raise OkovisionConnectionError(f"Cannot connect to {self._base_url}: {err}") from err
        except aiohttp.ServerTimeoutError as err:
            raise OkovisionConnectionError(f"Timeout connecting to {self._base_url}") from err

    async def async_test_connection(self) -> bool:
        """Test the connection and authentication."""
        await self._request("GET", "/api/status")
        return True

    async def async_get_sensors(self) -> list[dict[str, Any]]:
        """Fetch all sensors from the API.

        Expected response format:
        [
          {
            "id": "sensor_1",
            "name": "Temperature Bureau",
            "type": "temperature",
            "value": 21.5,
            "unit": "°C",
            "device_class": "temperature",
            "last_updated": "2024-01-01T12:00:00Z"
          },
          ...
        ]
        """
        return await self._request("GET", "/api/sensors")

    async def async_get_sensor(self, sensor_id: str) -> dict[str, Any]:
        """Fetch a single sensor by ID."""
        return await self._request("GET", f"/api/sensors/{sensor_id}")
