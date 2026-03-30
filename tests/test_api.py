"""Tests unitaires – OkovisionApiClient (gestion des erreurs HTTP)."""
from __future__ import annotations

import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.okovision.api import (
    OkovisionApiClient,
    OkovisionAuthError,
    OkovisionConnectionError,
    OkovisionDataNotFoundError,
    OkovisionApiError,
)


def _make_client(session):
    return OkovisionApiClient("http://test/ha_api.php", "token123", session)


def _mock_response(status: int, json_data: dict):
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=json_data)
    response.raise_for_status = MagicMock()
    if status >= 400:
        response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=status
        )
    return response


class TestApiErrors:
    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self):
        session = MagicMock()
        response = _mock_response(401, {})
        session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=response),
            __aexit__=AsyncMock(return_value=False),
        ))
        client = _make_client(session)
        with pytest.raises(OkovisionAuthError):
            await client._request({"action": "status"})

    @pytest.mark.asyncio
    async def test_404_raises_data_not_found(self):
        session = MagicMock()
        response = _mock_response(404, {"error": "No data found for 2026-03-27"})
        session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=response),
            __aexit__=AsyncMock(return_value=False),
        ))
        client = _make_client(session)
        with pytest.raises(OkovisionDataNotFoundError) as exc_info:
            await client._request({"action": "daily", "date": "2026-03-27"})
        assert "No data found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_json_error_field_raises_api_error(self):
        session = MagicMock()
        response = _mock_response(200, {"error": "some api error"})
        session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=response),
            __aexit__=AsyncMock(return_value=False),
        ))
        client = _make_client(session)
        with pytest.raises(OkovisionApiError):
            await client._request({"action": "today"})

    @pytest.mark.asyncio
    async def test_connection_error(self):
        session = MagicMock()
        session.get = MagicMock(side_effect=aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError("refused")
        ))
        client = _make_client(session)
        with pytest.raises(OkovisionConnectionError):
            await client._request({"action": "status"})

    @pytest.mark.asyncio
    async def test_data_not_found_is_subclass_of_api_error(self):
        assert issubclass(OkovisionDataNotFoundError, OkovisionApiError)
