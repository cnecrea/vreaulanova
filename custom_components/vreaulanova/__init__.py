"""Inițializarea integrării Nova Power & Gas."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """
    Setare inițială a integrării Nova Power & Gas folosind configurația YAML (dacă există).
    
    Acest setup se apelează doar dacă în configuration.yaml apare domeniul
    respectiv. Deoarece folosim Config Flow, vom returna True pentru a permite
    configurarea prin UI.
    """
    _LOGGER.debug("async_setup() a fost apelat.")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Configurarea integrării pe baza unui entry creat în UI (ConfigFlow).
    
    Se ocupă de inițializarea integrării și de încărcarea platformelor necesare.
    """
    _LOGGER.debug("async_setup_entry() a fost apelat pentru: %s", entry.as_dict())
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    # Încarcă platforma "sensor"
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Șterge integrarea și entitățile asociate unui entry atunci când
    utilizatorul o elimină din UI.
    """
    _LOGGER.debug("async_unload_entry() a fost apelat pentru: %s", entry.as_dict())
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
