"""ConfigFlow și OptionFlow pentru integrarea Nova Power & Gas."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    LOGGER,
)
from .api import NovaPGAPI

def _test_credentials_sync(email: str, password: str) -> bool:
    api = NovaPGAPI(email, password)
    return api.login() and api.validate()

async def _test_credentials(hass: HomeAssistant, email: str, password: str) -> bool:
    try:
        return await hass.async_add_executor_job(_test_credentials_sync, email, password)
    except Exception as err:
        LOGGER.error("Eroare la testarea credențialelor: %s", err)
    return False

class NovaPGConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow pentru Nova Power & Gas."""
    VERSION = 1

    def __init__(self):
        self._errors = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        self._errors = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            update_interval = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

            if await _test_credentials(self.hass, email, password):
                return self.async_create_entry(
                    title="Nova Power & Gas",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_UPDATE_INTERVAL: update_interval,
                    },
                )
            else:
                self._errors["base"] = "auth_failed"

        schema = vol.Schema({
            vol.Required(CONF_EMAIL): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): int,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=self._errors,
        )

    async def async_step_import(self, user_input=None):
        return await self.async_step_user(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Expune handlerul de opțiuni pentru Home Assistant."""
        return NovaPGOptionsFlowHandler(config_entry)

class NovaPGOptionsFlowHandler(config_entries.OptionsFlow):
    """Gestionare opțiuni (interval de update)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        schema = vol.Schema({
            vol.Optional(CONF_UPDATE_INTERVAL, default=current_interval): int,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
