"""Intégration OkoVision pour Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OkovisionApiClient
from .const import CONF_BASE_URL, CONF_SCAN_INTERVAL, CONF_TOKEN, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import OkovisionDailyCoordinator, OkovisionLiveCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise les deux coordinators OkoVision."""
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
        "live":  live_coord,
        "daily": daily_coord,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge la config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
