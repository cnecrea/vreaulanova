"""Coordinator pentru integrarea Nova Power & Gas."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import NovaPGAPI
from .const import LOGGER, DOMAIN, CONF_EMAIL, CONF_PASSWORD, CONF_UPDATE_INTERVAL

class NovaPGDataCoordinator(DataUpdateCoordinator):
    """
    Coordinator responsabil cu gestionarea și actualizarea datelor
    prin intermediul NovaPGAPI.
    """

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """
        Inițializează coordinatorul.
        """
        self.hass = hass
        self.config = config
        self.api = NovaPGAPI(config[CONF_EMAIL], config[CONF_PASSWORD])

        update_interval = config.get(CONF_UPDATE_INTERVAL, 60)  # minute
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=update_interval),
        )

    async def _async_update_data(self):
        """
        Metodă care se apelează automat la fiecare update_interval,
        pentru a obține cele mai noi date de la API (sincron).
        """
        # Deoarece NovaPGAPI folosește requests (sincron), apelăm logica în executor
        return await self.hass.async_add_executor_job(self._fetch_data)

    def _fetch_data(self):
        """
        Se execută în thread separat. 
        Apelăm direct fetch_all_data() (care face intern login/validare o dată).
        """
        data = self.api.fetch_all_data()
        if not data:
            LOGGER.error("Eșec la obținerea datelor cu emailul %s", self.config[CONF_EMAIL])
            return {}

        # Inițializăm fallback pentru cheile care pot fi None
        data.setdefault("locuri_consum", {})
        data.setdefault("facturi", {})
        data.setdefault("citiri_ee", [])
        data.setdefault("citiri_gn", [])

        return data
