"""Client API pentru Nova Power & Gas (backend Payload CMS).

Bazat pe analiza APK-ului (bundle.out decompilat) și date reale din API.
Toate endpoint-urile sunt validate cu răspunsuri reale.
"""

import asyncio
import logging
import time
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .const import (
    API_BASE,
    API_TIMEOUT,
    HEADERS_BASE,
    TOKEN_MAX_AGE,
    TOKEN_REFRESH_THRESHOLD,
    URL_APP_INFO,
    URL_BALANCES,
    URL_CONTRACTS,
    URL_CONTRACTS_DELIVERY,
    URL_INVOICES,
    URL_LOGIN,
    URL_ME,
    URL_METERING_POINTS,
    URL_METERING_POINTS_SELF_READINGS,
    URL_PAYMENTS,
    URL_SELF_READINGS,
    URL_SELF_READINGS_ADD,
    URL_SWITCH_ACCOUNT,
)

_LOGGER = logging.getLogger(__name__)


class NovaApiClient:
    """Client API pentru Nova Power & Gas (Payload CMS backend)."""

    def __init__(self, session: ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password

        # Token
        self._access_token: str | None = None
        self._token_obtained_at: float = 0.0
        self._token_expires_in: int = TOKEN_MAX_AGE
        self._auth_lock = asyncio.Lock()

        # Date cont din login — endpoint-ul /accounts/login/client returnează:
        #   data.loggedInAccount  — contul principal (cu associatedAccounts[])
        #   data.viewedAccount    — contul vizualizat (cu address, phone)
        #   data.session          — {token, expireAt, username, role}
        self._user_data: dict | None = None          # payload-ul complet (data)
        self._logged_in_account: dict | None = None  # loggedInAccount
        self._viewed_account: dict | None = None     # viewedAccount
        self._associated_accounts: list[dict] = []   # loggedInAccount.associatedAccounts
        self._crm_logged: str | None = None
        self._crm_viewed: str | None = None

        # MFA — Nova nu folosește MFA, dar config_flow verifică aceste câmpuri
        self._mfa_required: bool = False
        self._mfa_data: dict | None = None

        self._timeout = ClientTimeout(total=API_TIMEOUT)

    # ──────────────────────────────────────────
    # Proprietăți
    # ──────────────────────────────────────────

    @property
    def crm_logged_account(self) -> str | None:
        """CRM-ul contului logat (principal)."""
        return self._crm_logged

    @property
    def crm_viewed_account(self) -> str | None:
        """CRM-ul contului vizualizat (poate fi subcont)."""
        return self._crm_viewed

    @property
    def user_data(self) -> dict | None:
        """Payload-ul complet din login (loggedInAccount, viewedAccount, session)."""
        return self._user_data

    @property
    def logged_in_account(self) -> dict | None:
        """Contul principal (loggedInAccount) — cu associatedAccounts[]."""
        return self._logged_in_account

    @property
    def viewed_account(self) -> dict | None:
        """Contul vizualizat (viewedAccount) — cu address, phone."""
        return self._viewed_account

    @property
    def associated_accounts(self) -> list[dict]:
        """Lista conturilor asociate din loggedInAccount.associatedAccounts."""
        return self._associated_accounts

    @property
    def crm_account_number(self) -> str:
        """Alias — CRM-ul curent (viewed). Folosit de config_flow pt linked accounts."""
        return self._crm_viewed or self._crm_logged or ""

    @crm_account_number.setter
    def crm_account_number(self, value: str) -> None:
        """Permite config_flow să schimbe CRM-ul activ (conturi linkate)."""
        self._crm_viewed = value

    @property
    def mfa_required(self) -> bool:
        """Nova nu folosește MFA — mereu False."""
        return self._mfa_required

    @property
    def mfa_data(self) -> dict | None:
        """Nova nu folosește MFA — mereu None."""
        return self._mfa_data

    @property
    def has_token(self) -> bool:
        return self._access_token is not None

    def is_token_valid(self) -> bool:
        """Verifică dacă token-ul e valid (există și nu a expirat)."""
        if not self._access_token:
            return False
        age = time.monotonic() - self._token_obtained_at
        return age < (self._token_expires_in - TOKEN_REFRESH_THRESHOLD)

    def _auth_headers(self) -> dict[str, str]:
        """Headers cu Bearer token."""
        headers = dict(HEADERS_BASE)
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    # ──────────────────────────────────────────
    # Autentificare
    # ──────────────────────────────────────────

    async def async_login(self) -> bool:
        """POST /accounts/login/client → Bearer JWT.

        Endpoint-ul web returnează structura completă:
            {
                "success": true,
                "data": {
                    "loggedInAccount": {
                        "accountId": "uuid",
                        "accountNumber": "CRM",
                        "accountName": "NUME",
                        "associatedAccounts": [{accountName, accountNumber, accountId, ...}]
                    },
                    "viewedAccount": {
                        "accountId": "uuid",
                        "accountName": "...",
                        "accountNumber": "CRM",
                        "email": "...",
                        "role": "client",
                        "address": "...",
                        "phone": "..."
                    },
                    "session": {
                        "token": "JWT",
                        "expireAt": epoch,
                        "username": "email",
                        "role": "client"
                    }
                }
            }

        Returnează True dacă autentificarea a reușit.
        """
        async with self._auth_lock:
            try:
                async with self._session.post(
                    URL_LOGIN,
                    json={"email": self._email, "password": self._password},
                    headers=HEADERS_BASE,
                    timeout=self._timeout,
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.error(
                            "Login eșuat: status=%s, email=%s", resp.status, self._email
                        )
                        return False

                    data = await resp.json()
                    payload = data.get("data", {}) or {}

                    logged_in = payload.get("loggedInAccount", {}) or {}
                    viewed = payload.get("viewedAccount", {}) or {}
                    session_data = payload.get("session", {}) or {}

                    # Token — din data.session.token
                    self._access_token = session_data.get("token")
                    if not self._access_token:
                        # Fallback: token la nivel root (compatibilitate)
                        self._access_token = data.get("token")
                    if not self._access_token:
                        # Fallback: cookie payload-token
                        cookie = self._session.cookie_jar.filter_cookies(URL_LOGIN)
                        pt = cookie.get("payload-token")
                        if pt:
                            self._access_token = pt.value

                    if not self._access_token:
                        _LOGGER.error("Login reușit dar token absent din răspuns")
                        return False

                    self._token_obtained_at = time.monotonic()

                    # Calculăm expires_in din expireAt (epoch)
                    expire_at = session_data.get("expireAt")
                    if expire_at and isinstance(expire_at, (int, float)):
                        self._token_expires_in = int(expire_at - time.time())
                    else:
                        # Fallback: exp la nivel root (format APK)
                        exp = data.get("exp")
                        if exp and isinstance(exp, (int, float)):
                            self._token_expires_in = int(exp - time.time())
                        else:
                            self._token_expires_in = TOKEN_MAX_AGE

                    # Salvăm payload-ul complet
                    self._user_data = payload

                    # Cont principal (loggedInAccount)
                    self._logged_in_account = logged_in
                    self._crm_logged = str(
                        logged_in.get("accountNumber", "")
                    ).strip() or None

                    # Cont vizualizat (viewedAccount)
                    self._viewed_account = viewed
                    self._crm_viewed = str(
                        viewed.get("accountNumber", "")
                    ).strip() or None

                    # Conturi asociate — din loggedInAccount.associatedAccounts
                    self._associated_accounts = logged_in.get("associatedAccounts", []) or []

                    _LOGGER.info(
                        "Login reușit: email=%s, crmLogged=%s, crmViewed=%s, "
                        "asociate=%d",
                        self._email,
                        self._crm_logged,
                        self._crm_viewed,
                        len(self._associated_accounts),
                    )
                    return True

            except Exception:
                _LOGGER.exception("Eroare la login Nova API")
                return False

    async def async_ensure_authenticated(self) -> bool:
        """Asigură un token valid. Re-login dacă e necesar."""
        if self.is_token_valid():
            return True
        return await self.async_login()

    # ──────────────────────────────────────────
    # Helpers request
    # ──────────────────────────────────────────

    async def _get(self, url: str, params: dict | None = None) -> Any:
        """GET request autentificat. Returnează JSON parsed sau None."""
        if not await self.async_ensure_authenticated():
            return None
        try:
            async with self._session.get(
                url, headers=self._auth_headers(), params=params, timeout=self._timeout
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                _LOGGER.warning("GET %s → %s", url, resp.status)
                return None
        except Exception:
            _LOGGER.exception("Eroare GET %s", url)
            return None

    async def _post(self, url: str, body: dict | None = None) -> Any:
        """POST request autentificat. Returnează JSON parsed sau None."""
        if not await self.async_ensure_authenticated():
            return None
        try:
            async with self._session.post(
                url, headers=self._auth_headers(), json=body, timeout=self._timeout
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                _LOGGER.warning("POST %s → %s", url, resp.status)
                return None
        except Exception:
            _LOGGER.exception("Eroare POST %s", url)
            return None

    # ──────────────────────────────────────────
    # Endpoint-uri date
    # ──────────────────────────────────────────

    async def async_get_app_info(self) -> dict | None:
        """GET /globals/app-info/general

        Returnează: {data: {selfReadingsEnabled, selfReadingIntervalMessage, announcements}}
        """
        raw = await self._get(URL_APP_INFO)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_metering_points(self) -> list[dict]:
        """GET /metering-points → lista puncte de măsurare.

        Fiecare punct conține: utilityType, specificIdForUtilityType, address,
        meteringPointId, number, contractId, meters[], gasRevisions[]
        """
        raw = await self._get(URL_METERING_POINTS, params={"limit": 100})
        if raw and isinstance(raw, dict):
            return raw.get("docs", [])
        if isinstance(raw, list):
            return raw
        return []

    async def async_get_metering_points_self_readings(self) -> list[dict]:
        """GET /metering-points/self-readings → puncte pt autocitiri."""
        raw = await self._get(URL_METERING_POINTS_SELF_READINGS)
        if raw and isinstance(raw, dict):
            return raw.get("docs", [])
        if isinstance(raw, list):
            return raw
        return []

    async def async_get_consumption_agreement(self, metering_point_id: str) -> dict | None:
        """GET /metering-points/{id}/consumption-agreements

        Returnează: {agreement: {january: ..., december: ...}, state: {isEditable, unitOfMeasure}}
        """
        url = f"{API_BASE}/metering-points/{metering_point_id}/consumption-agreements"
        raw = await self._get(url)
        if raw and isinstance(raw, dict):
            inner = raw.get("data", raw)
            if isinstance(inner, dict) and ("agreement" in inner or "state" in inner):
                return inner
            return raw
        return None

    async def async_get_self_readings(self) -> list[dict]:
        """GET /self-readings → istoric autocitiri (toate punctele de măsurare).

        Fiecare intrare: month, utilityType, lastSelfReadingDate, meterSeries,
        consumptionOldIndex, consumptionNewIndex, consumption, unit, dialCode,
        meteringPointAddress
        """
        raw = await self._get(URL_SELF_READINGS, params={"limit": 100})
        if raw and isinstance(raw, dict):
            return raw.get("docs", [])
        if isinstance(raw, list):
            return raw
        return []

    async def async_get_invoices(self) -> dict | None:
        """GET /invoices → wrapper cu facturi + balance.

        Returnează docs[0] care conține:
          - invoices: [{invoiceId, utilityType, amountTotal, amountToPay, dueDate, status, ...}]
          - balance: {total, prosumer}
          - shouldPayAllBtnBeDisabled: bool
        """
        raw = await self._get(URL_INVOICES, params={"limit": 100})
        if raw and isinstance(raw, dict):
            docs = raw.get("docs", [])
            if docs and isinstance(docs, list) and len(docs) > 0:
                return docs[0]  # Wrapper-ul principal
        return None

    async def async_get_balances(self) -> dict | None:
        """GET /balances → sold separat.

        Returnează: {balance: float, prosumerBalance: float}
        """
        raw = await self._get(URL_BALANCES)
        if raw and isinstance(raw, dict):
            docs = raw.get("docs", [])
            if docs and isinstance(docs, list) and len(docs) > 0:
                return docs[0]
        return None

    async def async_get_contracts(self) -> list[dict]:
        """GET /contracts → lista contracte.

        Fiecare: number, utilityType, status, signedAt, etc.
        """
        raw = await self._get(URL_CONTRACTS, params={"limit": 100})
        if raw and isinstance(raw, dict):
            return raw.get("docs", [])
        if isinstance(raw, list):
            return raw
        return []

    async def async_get_contracts_delivery(self) -> list[dict]:
        """GET /contracts/invoice-delivery-type."""
        raw = await self._get(URL_CONTRACTS_DELIVERY)
        if raw and isinstance(raw, dict):
            return raw.get("docs", [])
        if isinstance(raw, list):
            return raw
        return []

    async def async_get_payments(self) -> list[dict]:
        """GET /payments → istoric plăți."""
        raw = await self._get(URL_PAYMENTS, params={"limit": 100})
        if raw and isinstance(raw, dict):
            return raw.get("docs", [])
        if isinstance(raw, list):
            return raw
        return []

    # ──────────────────────────────────────────
    # Acțiuni (POST)
    # ──────────────────────────────────────────

    async def async_submit_self_reading(self, payload: dict) -> dict | None:
        """POST /self-readings/add — trimite autocitire.

        Payload necesar:
            utilityType, meteringPointNumber, meterSeries, meterCode,
            newIndex, specificIdForUtilityType, currentIndex, unit,
            accountName, [dialCode]
        """
        return await self._post(URL_SELF_READINGS_ADD, body=payload)

    async def async_switch_account(self, account: dict) -> dict | None:
        """POST /accounts/switch — comută pe un cont asociat.

        Body: obiectul contului selectat (accountName, accountNumber, etc.)
        """
        return await self._post(URL_SWITCH_ACCOUNT, body=account)

    # ──────────────────────────────────────────
    # Token persistence (pentru restart HA)
    # ──────────────────────────────────────────

    def export_token_data(self) -> dict | None:
        """Exportă datele de token pentru persistare."""
        if not self._access_token:
            return None
        return {
            "access_token": self._access_token,
            "token_expires_in": self._token_expires_in,
            "crm_logged": self._crm_logged,
            "crm_viewed": self._crm_viewed,
            "logged_in_account": self._logged_in_account,
            "viewed_account": self._viewed_account,
            "associated_accounts": self._associated_accounts,
            "obtained_at_wall": time.time() - (time.monotonic() - self._token_obtained_at),
        }

    def inject_token(self, token_data: dict) -> None:
        """Restaurează un token salvat anterior."""
        self._access_token = token_data.get("access_token")
        self._token_expires_in = token_data.get("token_expires_in", TOKEN_MAX_AGE)
        self._crm_logged = token_data.get("crm_logged")
        self._crm_viewed = token_data.get("crm_viewed")
        self._logged_in_account = token_data.get("logged_in_account")
        self._viewed_account = token_data.get("viewed_account")
        self._associated_accounts = token_data.get("associated_accounts", [])

        wall = token_data.get("obtained_at_wall")
        if wall:
            age = max(0.0, time.time() - wall)
            self._token_obtained_at = time.monotonic() - age
        else:
            self._token_obtained_at = 0.0

    # ──────────────────────────────────────────
    # Aliasuri compatibilitate config_flow
    # ──────────────────────────────────────────

    async def async_fetch_metering_points_list(self) -> list[dict] | None:
        """Alias pentru config_flow: returnează lista metering-points."""
        result = await self.async_get_metering_points()
        return result if result else None

    async def async_fetch_contracts_list(self) -> list[dict] | None:
        """Alias pentru config_flow: returnează lista contracte."""
        result = await self.async_get_contracts()
        return result if result else None

    async def async_fetch_user_details(self) -> dict | None:
        """Returnează datele user din login (loggedInAccount, viewedAccount).

        Config_flow folosește asta pt a detecta conturi linkate.
        Dacă avem deja user_data din login, nu facem request suplimentar.
        """
        if self._user_data:
            return self._user_data
        # Fallback: /accounts/me returnează Payload CMS standard
        raw = await self._get(URL_ME)
        if raw and isinstance(raw, dict):
            user = raw.get("user", raw)
            # Mapăm câmpurile vechi (Payload CMS) pe structura nouă
            if user and not self._crm_logged:
                self._crm_logged = str(
                    user.get("crmLoggedAccountNumber", "")
                ).strip() or None
            if user and not self._crm_viewed:
                self._crm_viewed = str(
                    user.get("crmViewedAccountNumber", "")
                ).strip() or None
            return user
        return None

    # ──────────────────────────────────────────
    # MFA stubs (Nova nu folosește MFA)
    # ──────────────────────────────────────────

    async def async_mfa_complete(self, code: str) -> bool:
        """Stub — Nova nu folosește MFA."""
        return False

    async def async_mfa_resend(self, channel: str) -> bool:
        """Stub — Nova nu folosește MFA."""
        return False
