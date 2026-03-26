"""Config flow pour l'intégration OkoVision."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OkovisionApiClient, OkovisionApiError, OkovisionAuthError, OkovisionConnectionError
from .const import CONF_BASE_URL, CONF_SCAN_INTERVAL, CONF_TOKEN, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL, description={"suggested_value": "http://192.168.1.100/okovision/ha_api.php"}): str,
        vol.Required(CONF_TOKEN): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=30, max=3600)
        ),
    }
)


class OkovisionConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration OkoVision."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape initiale : saisie de l'URL et du token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].strip().rstrip("/")
            token    = user_input[CONF_TOKEN].strip()

            # Identifiant unique basé sur le host
            try:
                host = urlparse(base_url).netloc or base_url
            except Exception:
                host = base_url

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = OkovisionApiClient(base_url, token, session)

            try:
                await client.async_test_connection()
            except OkovisionAuthError:
                errors["base"] = "invalid_auth"
            except OkovisionConnectionError:
                errors["base"] = "cannot_connect"
            except OkovisionApiError:
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Erreur inattendue lors de la configuration OkoVision")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"OkoVision ({host})",
                    data={
                        CONF_BASE_URL:      base_url,
                        CONF_TOKEN:         token,
                        CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
