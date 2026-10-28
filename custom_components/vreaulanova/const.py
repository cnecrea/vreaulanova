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
LICENSE_PURCHASE_URL = "https://hubinteligent.org/donate?ref=vreaulanova"

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
# URL-uri API — myaccount-admin.nova-energy.ro (din octombrie 2026)
# ──────────────────────────────────────────────
# Backend-ul vechi (backend.nova-energy.ro/api, Payload CMS) întoarce 404 la orice rută.
# API-ul nou e cel folosit de myaccount.nova-energy.ro și de aplicația mobilă 5.x.
# Răspunsurile au forma {"data": {...}}; listele sunt în data.<nume> (nu în „docs"),
# cu excepția /contracts (paginat: docs, totalDocs, page …).
API_BASE = "https://myaccount-admin.nova-energy.ro/api/v1"

# Auth — /auth/login întoarce data.loggedInAccount (cu associatedAccounts), data.viewedAccount,
# data.session {token, expireAt (epoch, 30 de zile)}. Contul vizualizat: POST /auth/switch-account
# {accountId} + antetul X-Viewed-Account pe fiecare cerere (ca aplicația).
URL_LOGIN = f"{API_BASE}/auth/login"
URL_LOGOUT = f"{API_BASE}/auth/logout"
URL_SWITCH_ACCOUNT = f"{API_BASE}/auth/switch-account"

# App info (selfReadingsEnabled, selfReadingIntervalMessage, announcements)
URL_APP_INFO = f"{API_BASE}/system/info"

# Metering points
URL_METERING_POINTS = f"{API_BASE}/metering-points"
URL_METERING_POINTS_SELF_READINGS = f"{API_BASE}/metering-points/for-self-readings"
URL_GAS_REVISIONS = f"{API_BASE}/metering-points/gas-revisions"
# Consumption agreements: f"{API_BASE}/metering-points/{mp_id}/consumption-agreements"

# Self readings — GET = istoric (data.selfReadings), POST = trimitere autocitire
URL_SELF_READINGS = f"{API_BASE}/self-readings"

# Invoices (data.invoices + data.balance)
URL_INVOICES = f"{API_BASE}/invoices"

# Sold (total, electricity, gas, prosumer, prosumerDue, isProsumer)
URL_BALANCES = f"{API_BASE}/dashboard/balance"

# Contracts
URL_CONTRACTS = f"{API_BASE}/contracts"

# Payments (data.payments)
URL_PAYMENTS = f"{API_BASE}/payments"

# Raport consum și costuri (pe loc de consum: ultimele 12 luni, medii lunare)
URL_REPORT_LOCATIONS = f"{API_BASE}/reports/consumption-costs/locations"
URL_REPORT = f"{API_BASE}/reports/consumption-costs"

# Antet pentru contul vizualizat (cont principal sau asociat)
HEADER_VIEWED_ACCOUNT = "X-Viewed-Account"

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
