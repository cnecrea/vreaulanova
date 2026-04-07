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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NovaApiClient
from .const import DEFAULT_UPDATE_INTERVAL, HEAVY_UPDATE_MULTIPLIER, MONTHS_EN

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
        mp_primary = essential[0] if not isinstance(essential[0], Exception) else []
        mp_self_readings = essential[1] if not isinstance(essential[1], Exception) else []
        invoices_raw = essential[2] if not isinstance(essential[2], Exception) else None
        balances_raw = essential[3] if not isinstance(essential[3], Exception) else None
        self_readings = essential[4] if not isinstance(essential[4], Exception) else []
        contracts = essential[5] if not isinstance(essential[5], Exception) else []

        for i, label in enumerate(labels):
            if isinstance(essential[i], Exception):
                _LOGGER.warning("Eroare la %s (cont %s): %s", label, crm, essential[i])

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
                                "Merge meters din /self-readings pentru MP %s",
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
                        "MP extra din /self-readings: %s (%s) spec=%s",
                        sr_mp.get("number", sr_id),
                        sr_mp.get("utilityType", "?"),
                        spec,
                    )
                else:
                    _LOGGER.debug(
                        "MP ignorat din /self-readings (fără CLC/POD): %s",
                        sr_mp.get("number", sr_id),
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
                            "Eroare agreement %s (cont %s): %s", mp_id, crm, result
                        )
                    elif result:
                        agreements[mp_id] = result

        # ── Payments (doar la heavy refresh) ──
        if is_heavy:
            payments = await self.api.async_get_payments()
        else:
            payments = prev_acct.get("payments", [])

        # ── Procesare invoices ──
        invoices = []
        balance = {"total": 0, "prosumer": 0}
        if invoices_raw and isinstance(invoices_raw, dict):
            invoices = invoices_raw.get("invoices", [])
            balance = invoices_raw.get("balance", balance)

        # Suprascriem balance cu endpoint-ul dedicat (mai fiabil)
        if balances_raw and isinstance(balances_raw, dict):
            balance = {
                "total": balances_raw.get("balance", 0),
                "prosumer": balances_raw.get("prosumerBalance", 0),
            }

        # ── Indexare self_readings per contor ──
        readings_by_meter = {}
        for sr in self_readings:
            series = sr.get("meterSeries", "")
            readings_by_meter.setdefault(series, []).append(sr)

        # ── Indexare facturi per metering point ──
        invoices_by_mp = {}
        for inv in invoices:
            mp_code = inv.get("meteringPointCode", "")
            invoices_by_mp.setdefault(mp_code, []).append(inv)

        _LOGGER.debug(
            "Fetch cont %s (%s): %d puncte, %d facturi, %d autocitiri, %d contracte",
            crm, account_name, len(metering_points), len(invoices),
            len(self_readings), len(contracts),
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
        }

    # ──────────────────────────────────────────
    # Update principal — multi-account
    # ──────────────────────────────────────────

    async def _async_update_data(self) -> dict:
        """Extrage toate datele de la API-ul Nova pentru TOATE conturile."""
        is_heavy = self._is_heavy
        _LOGGER.debug(
            "Actualizare Nova (refresh=#%s, tip=%s)",
            self._refresh_count, "HEAVY" if is_heavy else "light",
        )

        try:
            # Asigurăm autentificarea
            if not await self.api.async_ensure_authenticated():
                raise UpdateFailed("Autentificare eșuată la Nova Power & Gas")

            # ── Date globale (nu depind de cont) ──
            app_info = None
            try:
                app_info = await self.api.async_get_app_info()
            except Exception as err:
                _LOGGER.warning("Eroare la app_info: %s", err)

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
            switched = False

            for aa in associated:
                aa_crm = str(aa.get("accountNumber", "")).strip()
                if not aa_crm or aa_crm in accounts_data:
                    continue  # Deja extras sau CRM invalid

                _LOGGER.debug(
                    "Switch la contul asociat: %s (%s)",
                    aa.get("accountName", "?"), aa_crm,
                )

                switch_result = await self.api.async_switch_account(aa)
                if switch_result:
                    switched = True
                    aa_name = aa.get("accountName", "")
                    aa_data = await self._fetch_account_data(aa_crm, aa_name, is_heavy)
                    accounts_data[aa_crm] = aa_data
                else:
                    _LOGGER.warning(
                        "Switch eșuat la contul asociat %s (%s)",
                        aa.get("accountName", "?"), aa_crm,
                    )

            # ── Revenire la contul principal ──
            if switched and logged_crm:
                logged_in = self.api.logged_in_account or {}
                _LOGGER.debug("Revenire la contul principal: %s", logged_crm)
                await self.api.async_switch_account({
                    "accountName": logged_in.get("accountName", ""),
                    "accountNumber": logged_in.get("accountNumber", ""),
                    "accountId": logged_in.get("accountId", ""),
                })

            # Incrementăm counter
            self._refresh_count += 1

            # Persistăm token
            self._persist_token()

            total_mp = sum(
                len(a.get("metering_points", [])) for a in accounts_data.values()
            )
            total_balance = sum(
                a.get("balance", {}).get("total", 0) for a in accounts_data.values()
            )
            _LOGGER.debug(
                "Actualizare finalizată: %d conturi, %d puncte măsurare total, "
                "balance total=%.2f Lei",
                len(accounts_data), total_mp, total_balance,
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

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.exception("Eroare la actualizare Nova: %s", err)
            raise UpdateFailed(f"Eroare la actualizare Nova: {err}") from err

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
