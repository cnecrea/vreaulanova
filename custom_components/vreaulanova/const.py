"""Constante pentru integrarea Nova Power & Gas (Vreau la Nova)."""

from homeassistant.const import Platform

DOMAIN = "vreaulanova"

# ──────────────────────────────────────────────
# Configurare
# ──────────────────────────────────────────────
DEFAULT_UPDATE_INTERVAL = 3600      # 1 oră (secunde)
HEAVY_UPDATE_MULTIPLIER = 6         # Heavy refresh la fiecare al 6-lea ciclu (≈6h)

# ──────────────────────────────────────────────
# Licență
# ──────────────────────────────────────────────
CONF_LICENSE_KEY = "license_key"
LICENSE_DATA_KEY = "vreaulanova_license_manager"
LICENSE_PURCHASE_URL = "https://hubinteligent.org/licenta/vreaulanova"

# ──────────────────────────────────────────────
# Token store (între config_flow și __init__)
# ──────────────────────────────────────────────
DOMAIN_TOKEN_STORE = f"{DOMAIN}_token_store"

# ──────────────────────────────────────────────
# Token management
# ──────────────────────────────────────────────
TOKEN_REFRESH_THRESHOLD = 300       # Refresh cu 5 min înainte de expirare
TOKEN_MAX_AGE = 2592000             # JWT Nova expiră la 30 zile (exp din răspuns)

# ──────────────────────────────────────────────
# Timeout API (secunde)
# ──────────────────────────────────────────────
API_TIMEOUT = 30

# ──────────────────────────────────────────────
# URL-uri API — Backend Payload CMS
# ──────────────────────────────────────────────
API_BASE = "https://backend.nova-energy.ro/api"

# Auth — /accounts/login/client returnează structura completă
#         cu loggedInAccount.associatedAccounts (endpoint web)
URL_LOGIN = f"{API_BASE}/accounts/login/client"
URL_LOGOUT = f"{API_BASE}/accounts/logout"
URL_ME = f"{API_BASE}/accounts/me"
URL_SWITCH_ACCOUNT = f"{API_BASE}/accounts/switch"

# App info (selfReadingsEnabled, selfReadingIntervalMessage)
URL_APP_INFO = f"{API_BASE}/globals/app-info/general"

# Metering points
URL_METERING_POINTS = f"{API_BASE}/metering-points"
URL_METERING_POINTS_SELF_READINGS = f"{API_BASE}/metering-points/self-readings"
# Consumption agreements: f"{API_BASE}/metering-points/{mp_id}/consumption-agreements"

# Self readings
URL_SELF_READINGS = f"{API_BASE}/self-readings"
URL_SELF_READINGS_ADD = f"{API_BASE}/self-readings/add"

# Invoices
URL_INVOICES = f"{API_BASE}/invoices"

# Balances
URL_BALANCES = f"{API_BASE}/balances"

# Contracts
URL_CONTRACTS = f"{API_BASE}/contracts"
URL_CONTRACTS_DELIVERY = f"{API_BASE}/contracts/invoice-delivery-type"

# Payments
URL_PAYMENTS = f"{API_BASE}/payments"

# Accounts users
URL_ACCOUNTS_USERS = f"{API_BASE}/accounts-users"

# ──────────────────────────────────────────────
# Headers HTTP
# ──────────────────────────────────────────────
HEADERS_BASE = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# ──────────────────────────────────────────────
# Platforme suportate
# ──────────────────────────────────────────────
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

# ──────────────────────────────────────────────
# Atribuție
# ──────────────────────────────────────────────
ATTRIBUTION = "Date furnizate de Nova Power & Gas"

# ──────────────────────────────────────────────
# Luni (pentru convenție consum)
# ──────────────────────────────────────────────
MONTHS_EN = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
MONTHS_RO = [
    "Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie",
    "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie",
]
