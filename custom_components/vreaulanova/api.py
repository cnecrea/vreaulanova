"""Client API pentru Nova Power & Gas (myaccount-admin.nova-energy.ro/api/v1).

Din octombrie 2026, Nova a înlocuit backend-ul Payload CMS (backend.nova-energy.ro) cu un API nou,
folosit de myaccount.nova-energy.ro și de aplicația mobilă 5.x. Rutele și învelișurile răspunsurilor
s-au schimbat; modelele din interior (locuri de consum, facturi, convenții, autocitiri) au rămas
aproape aceleași. Validat cu răspunsuri reale (cont individual, gaz).
"""

import asyncio
import logging
import time
from typing import Any

import aiohttp
from aiohttp import ClientSession, ClientTimeout

from .const import (
    API_BASE,
    API_TIMEOUT,
    HEADER_VIEWED_ACCOUNT,
    HEADERS_BASE,
    TOKEN_MAX_AGE,
    TOKEN_REFRESH_THRESHOLD,
    URL_APP_INFO,
    URL_BALANCES,
    URL_CONTRACTS,
    URL_GAS_REVISIONS,
    URL_INVOICES,
    URL_LOGIN,
    URL_METERING_POINTS,
    URL_METERING_POINTS_SELF_READINGS,
    URL_PAYMENTS,
    URL_REPORT,
    URL_REPORT_LOCATIONS,
    URL_SELF_READINGS,
    URL_SWITCH_ACCOUNT,
)
from .helpers import mask_email

_LOGGER = logging.getLogger(__name__)


class NovaApiError(Exception):
    """Cerere Nova eșuată (rețea, timeout, răspuns HTTP neașteptat).

    `status` = codul HTTP (None la rețea / timeout); `message` = mesajul Nova din răspuns, dacă există.
    """

    def __init__(self, text: str, status: int | None = None, message: str | None = None) -> None:
        super().__init__(text)
        self.status = status
        self.message = message


class NovaAuthError(NovaApiError):
    """Nova a respins email-ul / parola."""


def _data(raw: Any) -> Any:
    """Conținutul util al unui răspuns: raw["data"] dacă există, altfel răspunsul întreg."""
    if isinstance(raw, dict) and "data" in raw:
        return raw["data"]
    return raw


def _list(raw: Any, key: str) -> list[dict]:
    """O listă din răspuns: data.<key>, cu rezervă pe „docs" (forma veche) sau pe o listă directă."""
    inner = _data(raw)
    if isinstance(inner, list):
        return inner
    if isinstance(inner, dict):
        for k in (key, "docs"):
            if isinstance(inner.get(k), list):
                return inner[k]
    if isinstance(raw, dict) and isinstance(raw.get("docs"), list):
        return raw["docs"]
    return []


class NovaApiClient:
    """Client API pentru Nova Power & Gas."""

    def __init__(self, session: ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password

        # Token
        self._access_token: str | None = None
        self._token_obtained_at: float = 0.0
        self._token_expires_in: int = TOKEN_MAX_AGE
        self._auth_lock = asyncio.Lock()
        self._token_generation: int = 0
        # Token salvat fără momentul obținerii → re-login la prima cerere
        self._force_login: bool = False
        # Ultimul login a fost respins pentru credențiale (parolă schimbată)
        self._auth_rejected: bool = False
        # Contul vizualizat se schimbă pentru conturile asociate (actualizare date / trimitere
        # index) doar sub acest lacăt, altfel un index putea fi trimis pe contul greșit.
        self.account_lock = asyncio.Lock()

        # Date cont din login — /auth/login întoarce:
        #   data.loggedInAccount  — contul principal (cu associatedAccounts[], poate fi null)
        #   data.viewedAccount    — contul vizualizat (cu address, phone)
        #   data.session          — {token, expireAt, username, role}
        self._user_data: dict | None = None          # payload-ul complet (data)
        self._logged_in_account: dict | None = None  # loggedInAccount
        self._viewed_account: dict | None = None     # viewedAccount
        self._associated_accounts: list[dict] = []   # loggedInAccount.associatedAccounts
        self._crm_logged: str | None = None
        self._crm_viewed: str | None = None
        # accountId-ul contului vizualizat — trimis în X-Viewed-Account, ca în aplicație
        self._viewed_account_id: str | None = None

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

    @property
    def auth_rejected(self) -> bool:
        """True dacă Nova a respins credențialele la ultimul login."""
        return self._auth_rejected

    def is_token_valid(self) -> bool:
        """Verifică dacă token-ul e valid (există și nu a expirat)."""
        if not self._access_token or self._force_login:
            return False
        age = time.monotonic() - self._token_obtained_at
        return age < (self._token_expires_in - TOKEN_REFRESH_THRESHOLD)

    def _auth_headers(self) -> dict[str, str]:
        """Headers cu Bearer token și contul vizualizat."""
        headers = dict(HEADERS_BASE)
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        if self._viewed_account_id:
            headers[HEADER_VIEWED_ACCOUNT] = self._viewed_account_id
        return headers

    # ──────────────────────────────────────────
    # Autentificare
    # ──────────────────────────────────────────

    async def async_login(self) -> bool:
        """POST /auth/login {email, password} → token Bearer.

        Răspunsul:
            {
                "success": true, "status": 200,
                "data": {
                    "loggedInAccount": {accountId, accountNumber (CRM), accountName, associatedAccounts},
                    "viewedAccount": {accountId, accountNumber, accountName, email, role, address, phone,
                                      parentAccountId, isMainAccount, contactName},
                    "session": {token, expireAt (epoch), username, role, canImpersonate},
                    "preferences": {language, theme}
                }
            }

        Returnează True dacă autentificarea a reușit.
        """
        async with self._auth_lock:
            return await self._async_login_unlocked()

    async def _async_login_unlocked(self) -> bool:
        """Login propriu-zis (apelat doar cu _auth_lock deținut)."""
        try:
            async with self._session.post(
                URL_LOGIN,
                json={"email": self._email, "password": self._password},
                headers=HEADERS_BASE,
                timeout=self._timeout,
            ) as resp:
                if resp.status != 200:
                    if resp.status in (400, 401, 403, 422):
                        # Credențiale respinse (422 = validare Laravel) — reîncercările automate nu ajută
                        self._auth_rejected = True
                    _LOGGER.error(
                        "[VreauLaNova] Login eșuat pentru %s: HTTP %s — %s",
                        mask_email(self._email), resp.status, await self._error_message(resp),
                    )
                    return False

                data = await resp.json(content_type=None)
                payload = data.get("data", {}) if isinstance(data, dict) else {}
                payload = payload or {}

                logged_in = payload.get("loggedInAccount", {}) or {}
                viewed = payload.get("viewedAccount", {}) or {}
                session_data = payload.get("session", {}) or {}

                self._access_token = session_data.get("token")
                if not self._access_token:
                    _LOGGER.error("[VreauLaNova] Login reușit, dar răspunsul nu conține data.session.token")
                    return False

                self._token_obtained_at = time.monotonic()
                self._token_generation += 1
                self._force_login = False
                self._auth_rejected = False

                # expireAt e epoch (secunde) → durata rămasă
                expire_at = session_data.get("expireAt")
                if isinstance(expire_at, (int, float)) and expire_at > time.time():
                    self._token_expires_in = int(expire_at - time.time())
                else:
                    self._token_expires_in = TOKEN_MAX_AGE

                self._user_data = payload
                self._logged_in_account = logged_in
                self._crm_logged = str(logged_in.get("accountNumber", "")).strip() or None
                self._set_viewed(viewed or logged_in)
                # associatedAccounts vine null la conturile fără conturi asociate
                self._associated_accounts = logged_in.get("associatedAccounts") or []

                _LOGGER.info(
                    "[VreauLaNova] Login reușit pentru %s: cont %s, conturi asociate %d, token valabil %d zile",
                    mask_email(self._email), self._crm_logged, len(self._associated_accounts),
                    self._token_expires_in // 86400,
                )
                return True

        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.warning("[VreauLaNova] Login: Nova nu răspunde (%s: %s)", type(err).__name__, err)
            return False
        except Exception:
            _LOGGER.exception("[VreauLaNova] Eroare neașteptată la login")
            return False

    def _set_viewed(self, account: dict) -> None:
        """Contul vizualizat: CRM, accountId (pentru X-Viewed-Account) și datele lui."""
        self._viewed_account = account
        self._crm_viewed = str(account.get("accountNumber", "")).strip() or None
        self._viewed_account_id = str(account.get("accountId") or "").strip() or None

    async def async_ensure_authenticated(self) -> bool:
        """Asigură un token valid. Re-login dacă e necesar.

        Cererile paralele care găsesc token-ul expirat fac UN singur login
        (înainte: câte unul per cerere).
        """
        if self.is_token_valid():
            return True
        async with self._auth_lock:
            if self.is_token_valid():
                return True
            return await self._async_login_unlocked()

    # ──────────────────────────────────────────
    # Helpers request
    # ──────────────────────────────────────────

    @staticmethod
    async def _error_message(resp: aiohttp.ClientResponse) -> str:
        """Mesajul de eroare din răspuns ({"message": …} la API-ul nou), scurtat; altfel „HTTP n"."""
        try:
            body = await resp.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError):
            return f"HTTP {resp.status}"
        if isinstance(body, dict) and isinstance(body.get("message"), str) and body["message"].strip():
            return body["message"].strip()[:300]
        return f"HTTP {resp.status}"

    async def _request(
        self, method: str, url: str, params: dict | None = None, body: dict | None = None
    ) -> Any:
        """Cerere autentificată. Returnează JSON-ul sau ridică NovaApiError.

        La 401 (token invalidat pe server înainte de expirare — ex: parolă
        schimbată, sesiune închisă) se face re-login o dată și se reia cererea.
        """
        for attempt in (1, 2):
            if not await self.async_ensure_authenticated():
                if self._auth_rejected:
                    raise NovaAuthError("Nova a respins email-ul sau parola")
                raise NovaApiError("Autentificare eșuată la Nova Power & Gas")
            generation = self._token_generation
            path = url.removeprefix(API_BASE)
            started = time.monotonic()
            try:
                async with self._session.request(
                    method, url, headers=self._auth_headers(), params=params,
                    json=body, timeout=self._timeout,
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json(content_type=None)
                        _LOGGER.debug(
                            "[VreauLaNova] %s %s → 200 (%.2fs)", method, path, time.monotonic() - started
                        )
                        return result
                    status = resp.status
                    message = await self._error_message(resp)
            except (asyncio.TimeoutError, aiohttp.ClientError, ValueError) as err:
                _LOGGER.debug(
                    "[VreauLaNova] %s %s → %s după %.2fs", method, path, type(err).__name__, time.monotonic() - started
                )
                raise NovaApiError(f"{method} {path}: {type(err).__name__} {err}".strip()) from err

            _LOGGER.debug(
                "[VreauLaNova] %s %s → HTTP %s (%.2fs): %s", method, path, status, time.monotonic() - started, message
            )
            if status == 401 and attempt == 1:
                _LOGGER.debug("[VreauLaNova] %s %s → 401 — re-login și reîncercare", method, path)
                async with self._auth_lock:
                    # Alt apel paralel poate fi refăcut deja login-ul
                    if self._token_generation == generation:
                        self._force_login = True
                continue
            nova_message = None if message == f"HTTP {status}" else message
            raise NovaApiError(
                f"{method} {path} → HTTP {status}{f': {nova_message}' if nova_message else ''}",
                status=status, message=nova_message,
            )
        raise NovaApiError(f"{method} {url.removeprefix(API_BASE)} → HTTP 401")  # pragma: no cover

    async def _get(self, url: str, params: dict | None = None) -> Any:
        """GET autentificat (ridică NovaApiError la eșec)."""
        return await self._request("GET", url, params=params)

    async def _post(self, url: str, body: dict | None = None) -> Any:
        """POST autentificat (ridică NovaApiError la eșec)."""
        return await self._request("POST", url, body=body)

    # ──────────────────────────────────────────
    # Endpoint-uri date
    # ──────────────────────────────────────────

    async def async_get_app_info(self) -> dict | None:
        """GET /system/info → {name, announcements, selfReadingsEnabled, selfReadingIntervalMessage}."""
        inner = _data(await self._get(URL_APP_INFO))
        return inner if isinstance(inner, dict) else None

    async def async_get_metering_points(self) -> list[dict]:
        """GET /metering-points → data.meteringPoints.

        Fiecare punct: meteringPointId, number (LC-…), address, utilityType, contractType,
        specificIdForUtilityType (CLC/POD), contractId, gasRevisions (null — reviziile vin
        din /metering-points/gas-revisions). Fără „meters" (vin din for-self-readings).
        """
        return _list(await self._get(URL_METERING_POINTS), "meteringPoints")

    async def async_get_metering_points_self_readings(self) -> list[dict]:
        """GET /metering-points/for-self-readings → data.meteringPoints, cu meters[]
        (series, meterCode, currentIndex, unit, dialCode) — goale în afara perioadei de citire."""
        return _list(await self._get(URL_METERING_POINTS_SELF_READINGS), "meteringPoints")

    async def async_get_gas_revisions(self) -> dict[str, list[dict]]:
        """GET /metering-points/gas-revisions → {specificIdForUtilityType: [{revisionType,
        executionDate, expirationDate}]}."""
        inner = _data(await self._get(URL_GAS_REVISIONS))
        revisions = inner.get("revisions") if isinstance(inner, dict) else None
        return revisions if isinstance(revisions, dict) else {}

    async def async_get_consumption_agreement(self, metering_point_id: str) -> dict | None:
        """GET /metering-points/{id}/consumption-agreements

        Returnează: {agreement: {january: ..., december: ...}, state: {isEditable, unitOfMeasure}}
        """
        url = f"{API_BASE}/metering-points/{metering_point_id}/consumption-agreements"
        inner = _data(await self._get(url))
        if isinstance(inner, dict) and ("agreement" in inner or "state" in inner):
            return inner
        return None

    async def async_get_self_readings(self) -> list[dict]:
        """GET /self-readings → data.selfReadings (istoricul, cel mai nou primul).

        Fiecare intrare: period (dd.mm.yyyy), periodStart, periodEnd, oldIndex, newIndex,
        consumption, unit, meteringPointNo, meteringPointCode, meterSeries, meterCode,
        readingType, utilityType, dialCode.
        """
        return _list(await self._get(URL_SELF_READINGS), "selfReadings")

    async def async_get_invoices(self) -> dict | None:
        """GET /invoices → {invoices: [...], balance: {total, prosumer, isProsumer, …},
        shouldPayAllBtnBeDisabled, clePayableDocuments}."""
        inner = _data(await self._get(URL_INVOICES))
        if isinstance(inner, dict) and "invoices" in inner:
            return inner
        return None

    async def async_get_balances(self) -> dict | None:
        """GET /dashboard/balance → {total, electricity, gas, prosumer, prosumerDue,
        processingPayments, pendingInvoicesCount, perMeteringPoint, isProsumer}."""
        inner = _data(await self._get(URL_BALANCES))
        return inner if isinstance(inner, dict) else None

    async def async_get_contracts(self) -> list[dict]:
        """GET /contracts → docs (paginat). Fiecare: contractId, number, utilityType, status,
        type, signedAt, inForceAt, invoiceDeliveryType."""
        return _list(await self._get(URL_CONTRACTS, params={"page": 1, "limit": 100}), "docs")

    async def async_get_payments(self) -> list[dict]:
        """GET /payments → data.payments (date, totalAmount, invoiceValue, paidValue, utilityType …)."""
        return _list(await self._get(URL_PAYMENTS), "payments")

    async def async_get_report_locations(self) -> list[dict]:
        """GET /reports/consumption-costs/locations → [{id (= numărul LC), code, name, address, utilities}].

        Conține doar locurile cu furnizare (cele fără CLC/POD nu apar).
        """
        return _list(await self._get(URL_REPORT_LOCATIONS), "locations")

    async def async_get_consumption_report(self, place_id: str, utility: str) -> dict | None:
        """GET /reports/consumption-costs?consumptionPlaceId=LC-…&utility=gas&reportType=simplified

        → {location, filters, supplyStart, consumptionAvailable, summary.{gas|electricity}
           {consumptionTotal, unit, costTotal, currency, averageMonthlyConsumption, averageMonthlyCost,
           monthsWithData}, monthly[{period „2026-09", {gas|electricity}: {consumption, unit, cost}}], yearly, yoy}

        Raportul „detailed" cere parametri în plus (întoarce 422 fără ei) — folosim „simplified", ca aplicația.
        """
        inner = _data(await self._get(
            URL_REPORT,
            params={"consumptionPlaceId": place_id, "utility": utility, "reportType": "simplified"},
        ))
        return inner if isinstance(inner, dict) and "monthly" in inner else None

    # ──────────────────────────────────────────
    # Acțiuni (POST)
    # ──────────────────────────────────────────

    async def async_submit_self_reading(self, payload: dict) -> dict | None:
        """POST /self-readings — trimite autocitire.

        Payload (ca în aplicație):
            utilityType, meteringPointNumber, specificIdForUtilityType, meterSeries, meterCode,
            newIndex, currentIndex, unit, accountName, [dialCode]
        """
        return await self._post(URL_SELF_READINGS, body=payload)

    async def async_switch_account(self, account: dict) -> dict | None:
        """POST /auth/switch-account {accountId} — comută pe alt cont (asociat sau principal).

        Ca în aplicație: după comutare, cererile poartă X-Viewed-Account cu accountId-ul nou.
        Returnează un dict ne-gol la succes.
        """
        account_id = str(account.get("accountId") or "").strip()
        if not account_id:
            raise NovaApiError("Cont fără accountId — comutarea nu e posibilă")
        raw = await self._post(URL_SWITCH_ACCOUNT, body={"accountId": account_id})
        inner = _data(raw)
        viewed = inner.get("viewedAccount") if isinstance(inner, dict) else None
        self._set_viewed(viewed if isinstance(viewed, dict) and viewed.get("accountId") else {**account, "accountId": account_id})
        return inner if isinstance(inner, dict) and inner else {"success": True}

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
            "api_base": API_BASE,
        }

    def inject_token(self, token_data: dict) -> None:
        """Restaurează un token salvat anterior."""
        self._access_token = token_data.get("access_token")
        self._token_expires_in = token_data.get("token_expires_in", TOKEN_MAX_AGE)
        self._crm_logged = token_data.get("crm_logged")
        self._logged_in_account = token_data.get("logged_in_account")
        self._set_viewed(token_data.get("viewed_account") or self._logged_in_account or {})
        self._crm_viewed = token_data.get("crm_viewed") or self._crm_viewed
        self._associated_accounts = token_data.get("associated_accounts") or []

        wall = token_data.get("obtained_at_wall")
        if wall:
            age = max(0.0, time.time() - wall)
            self._token_obtained_at = time.monotonic() - age
        else:
            # Înainte: obtained_at=0, care după o repornire recentă a sistemului
            # (monotonic mic) făcea un token vechi să pară valid
            self._token_obtained_at = time.monotonic()
            self._force_login = True
        if token_data.get("api_base") != API_BASE:
            # Token emis de backend-ul vechi (Payload CMS): nu e valid pe API-ul nou
            self._force_login = True
        self._token_generation += 1

    # ──────────────────────────────────────────
    # Aliasuri compatibilitate config_flow
    # ──────────────────────────────────────────

    async def async_fetch_metering_points_list(self) -> list[dict] | None:
        """Alias pentru config_flow: returnează lista metering-points."""
        try:
            result = await self.async_get_metering_points()
        except NovaApiError:
            return None
        return result if result else None

    async def async_fetch_contracts_list(self) -> list[dict] | None:
        """Alias pentru config_flow: returnează lista contracte."""
        try:
            result = await self.async_get_contracts()
        except NovaApiError:
            return None
        return result if result else None

    async def async_fetch_user_details(self) -> dict | None:
        """Returnează datele user din login (loggedInAccount, viewedAccount).

        Config_flow folosește asta pt a detecta conturi linkate. API-ul nou nu are
        /accounts/me: datele vin doar din răspunsul la login.
        """
        return self._user_data

    # ──────────────────────────────────────────
    # MFA stubs (Nova nu folosește MFA)
    # ──────────────────────────────────────────

    async def async_mfa_complete(self, code: str) -> bool:
        """Stub — Nova nu folosește MFA."""
        return False

    async def async_mfa_resend(self, channel: str) -> bool:
        """Stub — Nova nu folosește MFA."""
        return False
