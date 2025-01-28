"""Constante pentru integrarea Nova Power & Gas."""
import logging

DOMAIN = "vreaulanova"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_UPDATE_INTERVAL = "update_interval"

BASE_URL = "https://crmadmin.novapg.ro/webapi"
URL_LOGIN = f"{BASE_URL}/account/postLogin"
URL_LOGIN_VALIDARE = f"{BASE_URL}/default/validate"
URL_LOCURI_CONSUM = f"{BASE_URL}/default/locuriConsum"
URL_FACTURI = f"{BASE_URL}/default/bills"
URL_CITIRE_EE = f"{BASE_URL}/autocitire/all?module=1"
URL_CITIRE_GN = f"{BASE_URL}/autocitire/all?module=2"

DEFAULT_UPDATE_INTERVAL = 60  # minute
DEFAULT_NAME = "Nova Power & Gas"

ATTRIBUTION = "Date furnizate de Nova Power & Gas"

LOGGER = logging.getLogger(__package__)
