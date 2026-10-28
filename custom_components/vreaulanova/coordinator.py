"""DataUpdateCoordinator pentru Nova Power & Gas.

Un singur coordinator per config_entry. Extrage TOATE datele disponibile
pentru TOATE conturile (principal + asociate) via switch automat:

  1. Login → se obțin associatedAccounts din loggedInAccount
  2. Fetch date pentru contul vizualizat (primary)
  3. Switch la fiecare cont asociat → fetch date → switch înapoi

Structura returnată:
  {
      "accounts_data": {
          "3043777": { "crm", "account_name", "metering_points", ... },
          "3047398": { "crm", "account_name", "metering_points", ... },
      },
      "app_info": { ... },
      "current_month_key": "april",
      "crm_logged": "3043777",
      "crm_viewed": "3043777",
      ...
  }
"""

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NovaApiClient, NovaApiError, NovaAuthError
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, HEAVY_UPDATE_MULTIPLIER, LICENSE_DATA_KEY, MONTHS_EN
from .helpers import is_active_mp, to_float

_LOGGER = logging.getLogger(__name__)


class NovaCoordinator(DataUpdateCoordinator):
    """Coordinator unic per cont Nova Power & Gas."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: NovaApiClient,
        config_entry: ConfigEntry,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Nova_{config_entry.entry_id[:8]}",
            update_interval=timedelta(seconds=update_interval),
        )
        self.api = api_client
        self.api_client = api_client  # Alias — button.py îl referă ca api_client
        self.config_entry = config_entry
        self._refresh_count: int = 0
        self._last_persisted_token: str | None = None
        # Revenirea pe contul principal a eșuat → sesiunea de pe server a rămas
        # pe un cont asociat; următoarea actualizare revine întâi pe contul principal.
        self._session_on_other_account: bool = False

    @property
    def _is_heavy(self) -> bool:
        return self._refresh_count % HEAVY_UPDATE_MULTIPLIER == 0

    # ──────────────────────────────────────────
    # Fetch per cont (un singur cont la un moment dat)
    # ──────────────────────────────────────────

    async def _fetch_account_data(self, crm: str, account_name: str, is_heavy: bool) -> dict:
        """Extrage toate datele pentru contul curent vizualizat pe server.

        Apelurile API returnează date pentru contul activ (setat prin login sau switch).
        """
        prev = self.data or {}
        prev_acct = prev.get("accounts_data", {}).get(crm, {})

        # ── Fetch paralel: date esențiale ──
        essential = await asyncio.gather(
            self.api.async_get_metering_points(),
            self.api.async_get_metering_points_self_readings(),
            self.api.async_get_invoices(),
            self.api.async_get_balances(),
            self.api.async_get_self_readings(),
            self.api.async_get_contracts(),
            return_exceptions=True,
        )

        labels = [
            "metering_points", "metering_points_sr",
            "invoices", "balances", "self_readings", "contracts",
        ]
        failed = {
            label for label, result in zip(labels, essential) if isinstance(result, Exception)
        }
        for label, result in zip(labels, essential):
            if isinstance(result, Exception):
                if not isinstance(result, NovaApiError):
                    raise result
                _LOGGER.warning("[VreauLaNova] %s nu a putut fi citit (cont %s): %s", label, crm, result)
        if failed == set(labels):
            # Nova nu răspunde: entitățile devin indisponibile și își păstrează
            # ultimele valori (înainte: datele erau înlocuite cu liste goale →
            # sold 0, nicio factură, contoare dispărute).
            raise UpdateFailed(f"Nova Power & Gas nu a răspuns (cont {crm})")

        # Un endpoint care nu a răspuns acum nu golește datele: se păstrează cele anterioare
        mp_primary = (
            prev_acct.get("metering_points", []) if "metering_points" in failed else essential[0]
        )
        mp_self_readings = [] if "metering_points_sr" in failed else essential[1]
        invoices_raw = None if "invoices" in failed else essential[2]
        balances_raw = None if "balances" in failed else essential[3]
        self_readings = (
            prev_acct.get("self_readings", []) if "self_readings" in failed else essential[4]
        )
        contracts = prev_acct.get("contracts", []) if "contracts" in failed else essential[5]

        # ── Merge metering points: /metering-points + /metering-points/self-readings ──
        # /self-readings poate conține MP-uri extra (ex: LC vechi) sau meters populate
        # când /metering-points le returnează goale.
        metering_points = list(mp_primary)  # copie — nu mutăm originalul
        seen_mp_ids = {
            mp.get("meteringPointId") for mp in metering_points if mp.get("meteringPointId")
        }

        for sr_mp in mp_self_readings:
            sr_id = sr_mp.get("meteringPointId", "")

            if sr_id in seen_mp_ids:
                # MP există deja — merge meters dacă primary are meters gol
                for existing_mp in metering_points:
                    if existing_mp.get("meteringPointId") == sr_id:
                        if not existing_mp.get("meters") and sr_mp.get("meters"):
                            existing_mp["meters"] = sr_mp["meters"]
                            _LOGGER.debug(
                                "[VreauLaNova] Contoarele locului %s preluate din for-self-readings",
                                existing_mp.get("number", sr_id),
                            )
                        break
            else:
                # MP NOU — apare doar în /self-readings.
                # Adăugăm DOAR dacă are specificIdForUtilityType valid (CLC/POD).
                # MP-uri fără CLC/POD sunt vechi/inactive (ex: LC-00199881).
                spec = sr_mp.get("specificIdForUtilityType", "")
                if spec:
                    metering_points.append(sr_mp)
                    seen_mp_ids.add(sr_id)
                    _LOGGER.debug(
                        "[VreauLaNova] Loc în plus din for-self-readings: %s (%s), CLC/POD %s",
                        sr_mp.get("number", sr_id),
                        sr_mp.get("utilityType", "?"),
                        spec,
                    )
                else:
                    _LOGGER.debug(
                        "[VreauLaNova] Loc ignorat din for-self-readings (fără CLC/POD): %s",
                        sr_mp.get("number", sr_id),
                    )

        # ── Locuri fără CLC/POD (vechi / neactivate): fără contract, facturi, contor sau autocitiri.
        # Nu primesc senzori și nu se mai cer date pentru ele; rămân doar în listă (diagnostic, jurnal).
        inactive = [
            {"number": mp.get("number", ""), "utilityType": mp.get("utilityType", ""), "meteringPointId": mp.get("meteringPointId", "")}
            for mp in metering_points if not is_active_mp(mp)
        ]
        metering_points = [mp for mp in metering_points if is_active_mp(mp)]
        if inactive:
            _LOGGER.debug(
                "[VreauLaNova] Cont %s: %d loc(uri) fără CLC/POD ignorate (fără senzori): %s",
                crm, len(inactive), ", ".join(m["number"] or "?" for m in inactive),
            )

        # ── Consumption agreements per metering point ──
        agreements = {}
        if metering_points:
            agreement_tasks = []
            mp_ids = []
            for mp in metering_points:
                mp_id = mp.get("meteringPointId")
                if mp_id:
                    mp_ids.append(mp_id)
                    agreement_tasks.append(
                        self.api.async_get_consumption_agreement(mp_id)
                    )

            if agreement_tasks:
                results = await asyncio.gather(*agreement_tasks, return_exceptions=True)
                for mp_id, result in zip(mp_ids, results):
                    if isinstance(result, Exception):
                        _LOGGER.warning(
                            "[VreauLaNova] Convenția de consum a locului %s nu a putut fi citită (cont %s): %s", mp_id, crm, result
                        )
                        old = prev_acct.get("agreements", {}).get(mp_id)
                        if old:
                            agreements[mp_id] = old
                    elif result:
                        agreements[mp_id] = result

        # ── Plăți, revizii gaz, raport consum-costuri (doar la heavy refresh; altfel cele anterioare) ──
        payments = prev_acct.get("payments", [])
        gas_revisions = prev_acct.get("gas_revisions", {})
        reports = prev_acct.get("consumption_reports", {})
        if is_heavy:
            try:
                payments = await self.api.async_get_payments()
            except NovaApiError as err:
                _LOGGER.warning("[VreauLaNova] Plățile nu au putut fi citite (cont %s): %s", crm, err)
            if any(mp.get("utilityType") == "gas" for mp in metering_points):
                try:
                    gas_revisions = await self.api.async_get_gas_revisions()
                except NovaApiError as err:
                    _LOGGER.warning("[VreauLaNova] Reviziile de gaz nu au putut fi citite (cont %s): %s", crm, err)
            reports = await self._fetch_reports(crm, reports)

        # Reviziile vin separat, pe CLC (specificIdForUtilityType); senzorul le citește din MP
        for mp in metering_points:
            spec = mp.get("specificIdForUtilityType")
            if spec and spec in gas_revisions:
                mp["gasRevisions"] = gas_revisions[spec]

        # ── Procesare invoices ──
        invoices = []
        balance = {"total": 0, "prosumer": 0}
        if "invoices" in failed:
            invoices = prev_acct.get("invoices", [])
            balance = prev_acct.get("balance", balance)
        elif invoices_raw and isinstance(invoices_raw, dict):
            invoices = invoices_raw.get("invoices", []) or []
            balance = invoices_raw.get("balance", balance) or balance

        # Suprascriem balance cu endpoint-ul dedicat (/dashboard/balance): total, electricity, gas,
        # prosumer, prosumerDue, processingPayments, pendingInvoicesCount, perMeteringPoint, isProsumer
        if balances_raw and isinstance(balances_raw, dict):
            balance = {**balances_raw, "isProsumer": bool(balances_raw.get("isProsumer"))}
        elif "balances" in failed:
            balance = prev_acct.get("balance", balance)

        # ── Indexare self_readings per contor (cel mai nou primul, ca în API) ──
        readings_by_meter = {}
        for sr in self_readings:
            series = sr.get("meterSeries", "")
            readings_by_meter.setdefault(series, []).append(sr)

        # ── Contoare din istoric, când API-ul nu le dă ──
        # /metering-points nu are „meters", iar for-self-readings le dă doar în perioada de
        # citire. Fără ele, senzorii de index ar dispărea la fiecare repornire din afara
        # perioadei. Le reconstruim din ultima autocitire a fiecărei serii a locului.
        for mp in metering_points:
            if not isinstance(mp.get("meters"), list):
                mp["meters"] = []  # null / lipsă → listă goală (senzorii și butonul iterează pe ea)
            if mp["meters"]:
                continue
            derived = {}
            for sr in self_readings:  # cel mai nou primul → prima apariție a seriei e cea curentă
                series = sr.get("meterSeries")
                if not series or series in derived or sr.get("meteringPointNo") != mp.get("number"):
                    continue
                derived[series] = {
                    "series": series,
                    "meterCode": sr.get("meterCode", ""),
                    "dialCode": sr.get("dialCode", ""),
                    "unit": sr.get("unit", ""),
                    "currentIndex": sr.get("newIndex", sr.get("consumptionNewIndex")),
                    "fromHistory": True,
                }
            if derived:
                mp["meters"] = list(derived.values())

        # ── Indexare facturi per metering point ──
        invoices_by_mp = {}
        for inv in invoices:
            mp_code = inv.get("meteringPointCode", "")
            invoices_by_mp.setdefault(mp_code, []).append(inv)

        for mp in metering_points:
            meters = mp.get("meters") or []
            _LOGGER.debug(
                "[VreauLaNova] Cont %s · %s (%s): %s · contoare %d%s · facturi %d · autocitiri %d · "
                "convenție %s · revizii %d · raport consum %s",
                crm, mp.get("number", "?"), mp.get("utilityType", "?"),
                "activ (CLC/POD)" if mp.get("specificIdForUtilityType") else "FĂRĂ CLC/POD (inactiv)",
                len(meters), " (din istoric)" if any(m.get("fromHistory") for m in meters) else "",
                len(invoices_by_mp.get(mp.get("specificIdForUtilityType") or "", [])),
                sum(1 for sr in self_readings if sr.get("meteringPointNo") == mp.get("number")),
                "da" if mp.get("meteringPointId") in agreements else "nu",
                len(mp.get("gasRevisions") or []),
                "da" if mp.get("number") in reports else "nu",
            )
        _LOGGER.debug(
            "[VreauLaNova] Cont %s: %d locuri, %d facturi, %d plăți, %d autocitiri, %d contracte, sold %s lei%s",
            crm, len(metering_points), len(invoices), len(payments), len(self_readings), len(contracts),
            balance.get("total", 0), f" — endpoint-uri eșuate: {', '.join(sorted(failed))}" if failed else "",
        )

        return {
            "crm": crm,
            "account_name": account_name,
            "metering_points": metering_points,
            "invoices": invoices,
            "balance": balance,
            "contracts": contracts,
            "payments": payments,
            "agreements": agreements,
            "self_readings": self_readings,
            "readings_by_meter": readings_by_meter,
            "invoices_by_mp": invoices_by_mp,
            "inactive_metering_points": inactive,
            "gas_revisions": gas_revisions,
            "consumption_reports": reports,
        }

    async def _fetch_reports(self, crm: str, previous: dict) -> dict:
        """Raportul consum-costuri pentru fiecare loc cu furnizare: {număr LC: {utilitate: raport}}.

        Lista de locuri vine de la Nova (doar cele active). Un raport care nu răspunde acum
        își păstrează valoarea anterioară.
        """
        try:
            locations = await self.api.async_get_report_locations()
        except NovaApiError as err:
            _LOGGER.warning("[VreauLaNova] Locurile pentru raportul de consum nu au putut fi citite (cont %s): %s", crm, err)
            return previous
        reports: dict[str, dict] = {}
        for loc in locations:
            place = str(loc.get("id") or loc.get("code") or "").strip()
            for utility in loc.get("utilities") or []:
                if not place or utility not in ("gas", "electricity"):
                    continue
                try:
                    report = await self.api.async_get_consumption_report(place, utility)
                except NovaApiError as err:
                    _LOGGER.warning(
                        "[VreauLaNova] Raportul de consum %s/%s nu a putut fi citit (cont %s): %s", place, utility, crm, err
                    )
                    report = (previous.get(place) or {}).get(utility)
                if report:
                    reports.setdefault(place, {})[utility] = report
        return reports

    # ──────────────────────────────────────────
    # Update principal — multi-account
    # ──────────────────────────────────────────

    async def _async_update_data(self) -> dict:
        """Extrage toate datele de la API-ul Nova pentru TOATE conturile."""
        # Verificare licență — nu fetchuim date dacă licența/trial nu e validă
        license_mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if license_mgr and not license_mgr.is_valid:
            _LOGGER.debug("[VreauLaNova] Licență invalidă — se omit apelurile API")
            return self.data or {}

        is_heavy = self._is_heavy
        _LOGGER.debug(
            "[VreauLaNova] Actualizare #%s (%s)",
            self._refresh_count, "completă: + plăți, revizii, raport consum" if is_heavy else "rapidă",
        )

        try:
            # Asigurăm autentificarea
            if not await self.api.async_ensure_authenticated():
                if self.api.auth_rejected:
                    # Parolă schimbată: HA cere reautentificarea (fără reîncercări inutile)
                    raise ConfigEntryAuthFailed("Nova a respins email-ul sau parola")
                raise UpdateFailed("Autentificare eșuată la Nova Power & Gas")

            # Toate comutările de cont (și trimiterea indexului) folosesc aceeași
            # sesiune de pe server → se serializează prin account_lock.
            async with self.api.account_lock:
                return await self._async_fetch_all(is_heavy)

        except (UpdateFailed, ConfigEntryAuthFailed):
            raise
        except NovaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NovaApiError as err:
            raise UpdateFailed(f"Eroare la actualizare Nova: {err}") from err
        except Exception as err:
            _LOGGER.exception("[VreauLaNova] Eroare neașteptată la actualizare: %s", err)
            raise UpdateFailed(f"Eroare la actualizare Nova: {err}") from err

    async def _async_switch_to_primary(self) -> bool:
        """Revine pe contul principal (loggedInAccount). Returnează True la succes."""
        logged_in = self.api.logged_in_account or {}
        try:
            result = await self.api.async_switch_account({
                "accountName": logged_in.get("accountName", ""),
                "accountNumber": logged_in.get("accountNumber", ""),
                "accountId": logged_in.get("accountId", ""),
            })
        except NovaApiError as err:
            _LOGGER.error("[VreauLaNova] Revenirea pe contul principal a eșuat: %s", err)
            return False
        return bool(result)

    async def _async_fetch_all(self, is_heavy: bool) -> dict:
        """Extrage datele tuturor conturilor (apelat cu account_lock deținut)."""
        if self._session_on_other_account:
            # Altfel datele contului principal ar fi citite de pe alt cont
            if not await self._async_switch_to_primary():
                raise UpdateFailed(
                    "Sesiunea Nova a rămas pe un cont asociat și revenirea a eșuat"
                )
            self._session_on_other_account = False

        # ── Date globale (nu depind de cont) ──
        app_info = None
        try:
            app_info = await self.api.async_get_app_info()
        except Exception as err:
            _LOGGER.warning("[VreauLaNova] /system/info (perioada de autocitire) nu a putut fi citit: %s", err)

        current_month_key = MONTHS_EN[datetime.now().month - 1]

        # ── Fetch contul principal (vizualizat după login) ──
        accounts_data: dict[str, dict] = {}
        primary_crm = self.api.crm_viewed_account or self.api.crm_logged_account or ""
        logged_crm = self.api.crm_logged_account or primary_crm

        if primary_crm:
            # Numele contului principal
            primary_name = ""
            viewed = self.api.viewed_account
            if viewed and isinstance(viewed, dict):
                primary_name = viewed.get("accountName", "")
            if not primary_name:
                logged_in = self.api.logged_in_account
                if logged_in and isinstance(logged_in, dict):
                    primary_name = logged_in.get("accountName", "")

            primary_data = await self._fetch_account_data(
                primary_crm, primary_name, is_heavy
            )
            accounts_data[primary_crm] = primary_data

        # ── Fetch conturi asociate (switch → fetch → switch înapoi) ──
        associated = self.api.associated_accounts or []
        prev_accounts = (self.data or {}).get("accounts_data", {})
        switched = False

        try:
            for aa in associated:
                aa_crm = str(aa.get("accountNumber", "")).strip()
                if not aa_crm or aa_crm in accounts_data:
                    continue  # Deja extras sau CRM invalid

                _LOGGER.debug(
                    "[VreauLaNova] Comutare pe contul asociat %s (%s)",
                    aa.get("accountName", "?"), aa_crm,
                )

                try:
                    switch_result = await self.api.async_switch_account(aa)
                    if not switch_result:
                        raise NovaApiError("răspuns gol la switch")
                    switched = True
                    aa_name = aa.get("accountName", "")
                    accounts_data[aa_crm] = await self._fetch_account_data(
                        aa_crm, aa_name, is_heavy
                    )
                except (NovaApiError, UpdateFailed) as err:
                    # Un cont asociat indisponibil nu oprește actualizarea
                    # celorlalte: își păstrează datele anterioare.
                    _LOGGER.warning(
                        "[VreauLaNova] Contul asociat %s (%s) nu a putut fi actualizat: %s",
                        aa.get("accountName", "?"), aa_crm, err,
                    )
                    if aa_crm in prev_accounts:
                        accounts_data[aa_crm] = prev_accounts[aa_crm]
        finally:
            # ── Revenire la contul principal (ALWAYS — inclusiv pe excepție) ──
            if switched and logged_crm:
                _LOGGER.debug("[VreauLaNova] Revenire pe contul principal %s", logged_crm)
                if not await self._async_switch_to_primary():
                    self._session_on_other_account = True

        # Loc nou activ (ex: a primit CLC/POD după activarea contractului) sau contor nou (ex: primul
        # contor al unui loc fără autocitiri, apărut în perioada de citire) → reîncărcare, ca să i se
        # creeze senzorii și butonul (entitățile se creează doar la configurare). Doar la apariții noi:
        # contoarele care dispar în afara perioadei nu declanșează nimic.
        if self.data and self.config_entry:
            def _known(data: dict) -> set[tuple[str, str, str]]:
                return {
                    (crm, mp.get("number", ""), meter.get("series", ""))
                    for crm, acct in (data.get("accounts_data") or {}).items()
                    for mp in acct.get("metering_points", [])
                    for meter in (mp.get("meters") or [{}])
                }
            new = _known({"accounts_data": accounts_data}) - _known(self.data)
            if new:
                _LOGGER.info(
                    "[VreauLaNova] Locuri sau contoare noi: %s — integrarea se reîncarcă pentru a le crea entitățile",
                    ", ".join(f"{n}{f' (contor {s})' if s else ''}" for _, n, s in sorted(new)),
                )
                self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)

        # Incrementăm counter
        self._refresh_count += 1

        # Persistăm token
        self._persist_token()

        total_mp = sum(
            len(a.get("metering_points", [])) for a in accounts_data.values()
        )
        total_balance = sum(
            to_float((a.get("balance") or {}).get("total")) or 0.0 for a in accounts_data.values()
        )
        app = app_info or {}
        _LOGGER.debug(
            "[VreauLaNova] Actualizare #%d terminată: %d conturi, %d locuri de consum, sold total %.2f lei, "
            "autocitire %s%s",
            self._refresh_count - 1, len(accounts_data), total_mp, total_balance,
            "DESCHISĂ" if app.get("selfReadingsEnabled") else "închisă",
            f" ({app['selfReadingIntervalMessage']})" if app.get("selfReadingIntervalMessage") else "",
        )

        return {
            # Date per cont
            "accounts_data": accounts_data,

            # Date globale
            "app_info": app_info,
            "current_month_key": current_month_key,

            # User info (metadate sesiune)
            "crm_logged": self.api.crm_logged_account,
            "crm_viewed": self.api.crm_viewed_account,
            "user_data": self.api.user_data,
            "logged_in_account": self.api.logged_in_account,
            "viewed_account": self.api.viewed_account,
            "associated_accounts": self.api.associated_accounts,
        }

    def _persist_token(self) -> None:
        """Salvează token-ul în config_entry doar dacă s-a schimbat."""
        token_data = self.api.export_token_data()
        if not token_data or not self.config_entry:
            return

        current_token = token_data.get("access_token")
        if current_token == self._last_persisted_token:
            return  # Nu s-a schimbat — evităm scrieri inutile

        new_data = dict(self.config_entry.data)
        new_data["token_data"] = token_data
        self.hass.config_entries.async_update_entry(
            self.config_entry, data=new_data
        )
        self._last_persisted_token = current_token
