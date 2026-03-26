"""Intégration OkoVision pour Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OkovisionApiClient
from .const import CONF_BASE_URL, CONF_SCAN_INTERVAL, CONF_TOKEN, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import OkovisionDailyCoordinator, OkovisionLiveCoordinator
from .services import async_import_history

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

SERVICE_IMPORT_HISTORY = "import_history"
SERVICE_IMPORT_HISTORY_SCHEMA = vol.Schema({
    vol.Optional("years", default=4): vol.All(vol.Coerce(int), vol.Range(min=1, max=4)),
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise les deux coordinators OkoVision et enregistre les services."""
    base_url      = entry.data[CONF_BASE_URL]
    token         = entry.data[CONF_TOKEN]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    session = async_get_clientsession(hass)
    client  = OkovisionApiClient(base_url, token, session)

    live_coord  = OkovisionLiveCoordinator(hass, client, scan_interval)
    daily_coord = OkovisionDailyCoordinator(hass, client)

    # Premier fetch – bloquant au démarrage
    await live_coord.async_config_entry_first_refresh()
    await daily_coord.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "live":   live_coord,
        "daily":  daily_coord,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ── Service import_history ────────────────────────────────────────────────
    async def handle_import_history(call: ServiceCall) -> None:
        """Handler du service okovision.import_history."""
        years = call.data.get("years", 4)
        _LOGGER.info("OkoVision : lancement import_history (%d an(s))", years)
        summary = await async_import_history(hass, client, years)
        if summary:
            _LOGGER.info(
                "OkoVision import_history terminé : %s",
                ", ".join(f"{k}={v}j" for k, v in summary.items()),
            )
        else:
            _LOGGER.warning("OkoVision import_history : aucune donnée importée")

    # Enregistrement une seule fois (si pas déjà fait par une autre entry)
    if not hass.services.has_service(DOMAIN, SERVICE_IMPORT_HISTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_IMPORT_HISTORY,
            handle_import_history,
            schema=SERVICE_IMPORT_HISTORY_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge la config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        # Désenregistre le service si plus aucune entry active
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_IMPORT_HISTORY)
    return unload_ok
