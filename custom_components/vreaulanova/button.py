"""Platforma Button pentru Nova Power & Gas (Vreau la Nova).

Arhitectura v1.1 — PER LOC DE CONSUM (metering point):

  Buton per contor (meter) per loc de consum pentru trimiterea autocitirilor.
  Nova API: POST /self-readings/add cu payload specific per contor.

Pattern entity_id: button.{DOMAIN}_{crm}_{mp_slug}_trimite_index
  mp_slug = numărul locului de consum (LC-00202600 → lc00202600)

Device: un device per CRM per metering point (identic cu sensor.py).
  identifier: (DOMAIN, f"mp_{crm}_{mp_slug}")
"""

import logging
import re
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .api import NovaApiError
from .const import ATTRIBUTION, DOMAIN, LICENSE_DATA_KEY
from .coordinator import NovaCoordinator

_LOGGER = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════

def _utility_short(mp: dict) -> str:
    """Returnează eticheta scurtă pt utilitate (entity_id suffix)."""
    ut = mp.get("utilityType", "")
    if ut == "gas":
        return "gaz"
    if ut == "electricity":
        return "electricitate"
    return ut


def _utility_label(mp: dict) -> str:
    """Returnează eticheta afișabilă pt utilitate."""
    ut = mp.get("utilityType", "")
    if ut == "gas":
        return "Gaz"
    if ut == "electricity":
        return "Energie Electrică"
    return ut


def _mp_slug(mp: dict) -> str:
    """Generează un slug unic din numărul locului de consum.

    LC-00202600 → lc00202600  (folosit în entity_id și device identifier)
    Orice alt caracter nevalid într-un entity_id (ex: „/") devine „_".
    """
    number = mp.get("number", "") or mp.get("meteringPointId", "")[:12]
    slug = number.lower().replace("-", "").replace(" ", "")
    return re.sub(r"[^a-z0-9_]+", "_", slug).strip("_")


def helper_index_entity_id(clc_pod: str, series: str) -> str:
    """ID-ul helperului input_number din care se citește indexul de trimis.

    Normalizat exact ca Home Assistant (slugify): litere mici, „/", „-" și
    spațiile devin „_" (issue #10 — înainte seria rămânea neschimbată, ex:
    „...ABC/1234/2022_index", iar helperul creat de utilizator nu era găsit).
    """
    return f"input_number.{slugify(f'{DOMAIN}_{clc_pod}_{series}_index')}"


def _mp_device(crm: str, mp: dict) -> DeviceInfo:
    """Device info per CRM per loc de consum (metering point).

    Identic cu sensor.py — același identifier = aceeași intrare în device registry.
    Exemplu: Nova Power & Gas (6085537) LC-00202600 Gaz
    """
    mp_number = mp.get("number", "?")
    ut_label = _utility_label(mp)
    return DeviceInfo(
        identifiers={(DOMAIN, f"mp_{crm}_{_mp_slug(mp)}")},
        name=f"Nova Power & Gas ({crm}) {mp_number} {ut_label}",
        manufacturer="Ciprian Nicolae (cnecrea)",
        model="Nova Power & Gas",
        entry_type=DeviceEntryType.SERVICE,
    )


# ═══════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează butoanele pentru trimiterea autocitirilor.

    Iterează prin TOATE conturile (principal + asociate) din accounts_data.
    Creează un buton per loc de consum (metering point).
    Dacă MP-ul are meters, butonul le folosește la submit.
    Dacă NU are meters, butonul se creează oricum (sub device-ul LC).
    """
    coordinator: NovaCoordinator = config_entry.runtime_data.coordinator

    # Verificare licență — fără licență, fără butoane
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    if not mgr or not mgr.is_valid:
        _LOGGER.debug("[Nova:Button] Licență invalidă — nu se creează butoane")
        # Butoanele create anterior ar rămâne orfane („indisponibile") în registry
        registru = er.async_get(hass)
        for entry_reg in er.async_entries_for_config_entry(
            registru, config_entry.entry_id
        ):
            if entry_reg.domain == "button":
                registru.async_remove(entry_reg.entity_id)
        return

    data = coordinator.data or {}
    accounts_data = data.get("accounts_data", {})

    buttons: list[ButtonEntity] = []

    for crm, acct_data in accounts_data.items():
        metering_points = acct_data.get("metering_points", [])

        for mp in metering_points:
            # Un buton per MP — meter-ul e opțional (se ia primul dacă există)
            buttons.append(
                TrimiteIndexButton(coordinator, crm, mp)
            )

    if buttons:
        _LOGGER.debug(
            "[Nova:Button] Se adaugă %d butoane pentru %d conturi (entry_id=%s).",
            len(buttons), len(accounts_data), config_entry.entry_id,
        )
        async_add_entities(buttons)


# ═══════════════════════════════════════════════
# CLASĂ DE BAZĂ — PER LOC DE CONSUM
# ═══════════════════════════════════════════════

class NovaBaseButton(CoordinatorEntity[NovaCoordinator], ButtonEntity):
    """Bază pentru toate butoanele Nova — custom entity_id, device per MP.

    CoordinatorEntity: disponibilitatea se reevaluează la fiecare actualizare
    (înainte rămânea cea de la pornire — ex: contorul apărut ulterior).
    """

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: NovaCoordinator,
        crm: str,
        mp: dict,
    ) -> None:
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._crm = crm
        self._mp = mp
        self._mp_slug = _mp_slug(mp)
        self._ut_short = _utility_short(mp)
        self._ut_label = _utility_label(mp)
        self._custom_entity_id: str | None = None

    @property
    def _license_valid(self) -> bool:
        """Verifică dacă licența este validă (real-time)."""
        mgr = self._coordinator.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        return mgr.is_valid if mgr else False

    @property
    def entity_id(self) -> str | None:
        return self._custom_entity_id

    @entity_id.setter
    def entity_id(self, value: str) -> None:
        self._custom_entity_id = value

    @property
    def device_info(self) -> DeviceInfo:
        return _mp_device(self._crm, self._mp)


# ═══════════════════════════════════════════════
# BUTOANE
# ═══════════════════════════════════════════════

class TrimiteIndexButton(NovaBaseButton):
    """Buton pentru trimiterea autocitirilor la Nova API.

    Se creează UN buton per loc de consum (metering point).
    Meter-ul se ia din coordinator data la runtime (nu la init).
    Dacă MP-ul nu are meters, butonul apare dar e unavailable.
    """

    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: NovaCoordinator,
        crm: str,
        mp: dict,
    ):
        """Inițializare buton trimitere index — per MP."""
        super().__init__(coordinator, crm, mp)

        self._clc_pod = mp.get("specificIdForUtilityType", "")
        self._utility = mp.get("utilityType", "unknown")

        self._attr_name = "Trimite index"
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_trimite_index"
        self._attr_icon = "mdi:fire" if self._utility == "gas" else "mdi:flash"

        # Custom entity_id: button.vreaulanova_{crm}_{mp_slug}_trimite_index
        self._custom_entity_id = (
            f"button.{DOMAIN}_{crm}_{self._mp_slug}_trimite_index"
        )

    def _get_current_meter(self) -> dict | None:
        """Obține primul meter din MP la runtime (din coordinator data).

        Meter-ul poate apărea mai târziu (heavy refresh, self-readings fetch).
        """
        data = self._coordinator.data or {}
        acct = data.get("accounts_data", {}).get(self._crm, {})
        for mp in acct.get("metering_points", []):
            if mp.get("meteringPointId") == self._mp.get("meteringPointId"):
                meters = mp.get("meters", [])
                if meters:
                    return meters[0]
        # Fallback: meters din MP-ul stocat la init
        meters = self._mp.get("meters", [])
        return meters[0] if meters else None

    @property
    def available(self) -> bool:
        """Butonul e disponibil dacă: licență validă + coordinator ok + meter prezent."""
        if not self._license_valid or not self._coordinator.last_update_success:
            return False
        return self._get_current_meter() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Helperul din care se citește indexul — ca utilizatorul să știe ce să creeze."""
        meter = self._get_current_meter()
        if not meter:
            return {"Loc de consum": self._mp.get("number", "")}
        return {
            "Loc de consum": self._mp.get("number", ""),
            "Serie contor": meter.get("series", ""),
            "Helper index": helper_index_entity_id(self._clc_pod, meter.get("series", "")),
        }

    async def async_press(self) -> None:
        """Trimite autocitirea la Nova API.

        Nova folosește POST /self-readings/add cu payload:
            utilityType, meteringPointNumber, meterSeries, meterCode,
            newIndex, specificIdForUtilityType, currentIndex, unit,
            accountName, [dialCode]

        Dacă butonul aparține unui cont asociat (diferit de cel principal),
        se face switch înainte de submit și switch înapoi după.
        Orice eșec ridică HomeAssistantError → mesajul apare în interfață
        (înainte erorile ajungeau doar în log și apăsarea părea reușită).
        """
        if not self._license_valid:
            raise HomeAssistantError("Licență invalidă — trimiterea indexului nu e posibilă.")

        # Verifică dacă suntem în perioada de transmitere autocitiri
        data = self._coordinator.data or {}
        app_info = data.get("app_info") or {}
        if not app_info.get("selfReadingsEnabled", False):
            raise HomeAssistantError(
                "Nova nu permite autocitiri în această perioadă — butonul funcționează "
                "doar când fereastra de transmitere este deschisă."
            )

        meter = self._get_current_meter()
        if not meter:
            raise HomeAssistantError(
                f"Nu există contor pentru locul de consum {self._mp.get('number', '?')}."
            )

        series = meter.get("series", "")

        # Citește valoarea din helperul input_number (ID normalizat ca în HA — #10)
        input_entity_id = helper_index_entity_id(self._clc_pod, series)
        state = self.hass.states.get(input_entity_id)
        if not state or state.state in ("unknown", "unavailable"):
            raise HomeAssistantError(
                f"Helperul {input_entity_id} nu există sau nu are valoare. "
                "Creați un input_number cu acest ID și introduceți indexul."
            )

        try:
            index_value = int(float(state.state))
        except (ValueError, TypeError) as err:
            raise HomeAssistantError(
                f"Valoare invalidă în {input_entity_id}: {state.state}"
            ) from err

        # Determinăm accountName din accounts_data
        acct_data = data.get("accounts_data", {}).get(self._crm, {})
        account_name = acct_data.get("account_name", "")

        api = self._coordinator.api
        current_crm = api.crm_viewed_account or ""
        needs_switch = current_crm != self._crm
        target_account = None
        if needs_switch:
            for aa in api.associated_accounts or []:
                if str(aa.get("accountNumber", "")).strip() == self._crm:
                    target_account = aa
                    break
            if target_account is None:
                # Înainte: se trimitea „fără switch" — adică pe contul principal
                raise HomeAssistantError(
                    f"Contul asociat {self._crm} nu mai este disponibil — indexul nu a fost trimis."
                )

        # Construiește payload-ul Nova
        payload = {
            "utilityType": self._utility,
            "meteringPointNumber": self._mp.get("number", ""),
            "meterSeries": series,
            "meterCode": meter.get("meterCode", ""),
            "newIndex": index_value,
            "specificIdForUtilityType": self._clc_pod,
            "currentIndex": meter.get("currentIndex", 0),
            "unit": meter.get("unit", ""),
            "dialCode": meter.get("dialCode", ""),
            "accountName": account_name,
        }

        # Comutarea de cont + trimiterea + revenirea se fac sub lacătul de cont:
        # o actualizare a datelor în paralel comută și ea contul pe server.
        async with api.account_lock:
            if needs_switch:
                _LOGGER.debug("[Nova:Button] Switch la contul %s pentru submit", self._crm)
                try:
                    switched = await api.async_switch_account(target_account)
                except NovaApiError as err:
                    raise HomeAssistantError(
                        f"Comutarea pe contul {self._crm} a eșuat: {err}"
                    ) from err
                if not switched:
                    raise HomeAssistantError(
                        f"Comutarea pe contul {self._crm} a eșuat — indexul nu a fost trimis."
                    )

            _LOGGER.info(
                "[Nova:Button] Trimitere autocitire: cont=%s, clc_pod=%s, series=%s, "
                "newIndex=%s, utility=%s",
                self._crm, self._clc_pod, series, index_value, self._utility,
            )
            try:
                result = await api.async_submit_self_reading(payload)
            except NovaApiError as err:
                raise HomeAssistantError(
                    f"Nova a respins autocitirea {index_value} ({series}): {err}"
                ) from err
            finally:
                # Switch înapoi la contul principal
                if needs_switch and not await self._coordinator._async_switch_to_primary():
                    self._coordinator._session_on_other_account = True

        if not result:
            raise HomeAssistantError(
                f"Trimiterea autocitirii a eșuat pentru {series} (răspuns gol de la Nova)."
            )

        _LOGGER.info("[Nova:Button] Autocitire trimisă cu succes pentru %s.", series)
        await self._coordinator.async_request_refresh()
