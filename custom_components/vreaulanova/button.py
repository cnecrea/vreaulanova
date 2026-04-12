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
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    """
    number = mp.get("number", "") or mp.get("meteringPointId", "")[:12]
    return number.lower().replace("-", "").replace(" ", "")


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

class NovaBaseButton(ButtonEntity):
    """Bază pentru toate butoanele Nova — custom entity_id, device per MP."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: NovaCoordinator,
        crm: str,
        mp: dict,
    ) -> None:
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

    async def async_press(self) -> None:
        """Trimite autocitirea la Nova API.

        Nova folosește POST /self-readings/add cu payload:
            utilityType, meteringPointNumber, meterSeries, meterCode,
            newIndex, specificIdForUtilityType, currentIndex, unit,
            accountName, [dialCode]

        Dacă butonul aparține unui cont asociat (diferit de cel principal),
        se face switch înainte de submit și switch înapoi după.
        """
        if not self._license_valid:
            _LOGGER.warning("[Nova:Button] Licență invalidă — trimiterea indexului nu e posibilă.")
            return

        # Verifică dacă suntem în perioada de transmitere autocitiri
        data = self._coordinator.data or {}
        app_info = data.get("app_info") or {}
        if not app_info.get("selfReadingsEnabled", False):
            _LOGGER.warning(
                "[Nova:Button] Autocitirile nu sunt permise în această perioadă. "
                "Butonul este blocat până la deschiderea ferestrei de transmitere."
            )
            return

        meter = self._get_current_meter()
        if not meter:
            _LOGGER.error(
                "[Nova:Button] Nu există contor (meter) pentru MP %s — nu se poate trimite index.",
                self._mp.get("number", "?"),
            )
            return

        series = meter.get("series", "")

        # Citește valoarea din input_number entity
        # Sanitizăm CLC/POD: HA normalizează entity ID-urile (lowercase, / → _)
        safe_pod = self._clc_pod.lower().replace("/", "_").replace("-", "_").replace(" ", "_")
        input_entity_id = f"input_number.{DOMAIN}_{safe_pod}_{series}_index"
        state = self._coordinator.hass.states.get(input_entity_id)

        if not state or state.state in ("unknown", "unavailable"):
            _LOGGER.error(
                "[Nova:Button] Entitatea %s nu există sau nu are valoare.",
                input_entity_id,
            )
            return

        try:
            index_value = int(float(state.state))
        except (ValueError, TypeError):
            _LOGGER.error(
                "[Nova:Button] Valoare invalidă în %s: %s",
                input_entity_id, state.state,
            )
            return

        # Determinăm accountName din accounts_data
        data = self._coordinator.data or {}
        acct_data = data.get("accounts_data", {}).get(self._crm, {})
        account_name = acct_data.get("account_name", "")

        # Verificăm dacă trebuie switch la contul asociat
        current_crm = self._coordinator.api.crm_viewed_account or ""
        needs_switch = current_crm != self._crm

        if needs_switch:
            associated = self._coordinator.api.associated_accounts or []
            target_account = None
            for aa in associated:
                if str(aa.get("accountNumber", "")).strip() == self._crm:
                    target_account = aa
                    break
            if target_account:
                _LOGGER.debug("[Nova:Button] Switch la contul %s pentru submit", self._crm)
                await self._coordinator.api_client.async_switch_account(target_account)
            else:
                _LOGGER.warning(
                    "[Nova:Button] Nu s-a găsit contul asociat %s — submit fără switch",
                    self._crm,
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

        _LOGGER.info(
            "[Nova:Button] Trimitere autocitire: cont=%s, clc_pod=%s, series=%s, "
            "newIndex=%s, utility=%s",
            self._crm, self._clc_pod, series, index_value, self._utility,
        )

        result = await self._coordinator.api_client.async_submit_self_reading(payload)

        # Switch înapoi la contul principal
        if needs_switch:
            logged_in = self._coordinator.api.logged_in_account or {}
            if logged_in:
                _LOGGER.debug("[Nova:Button] Switch înapoi la contul principal")
                await self._coordinator.api_client.async_switch_account({
                    "accountName": logged_in.get("accountName", ""),
                    "accountNumber": logged_in.get("accountNumber", ""),
                    "accountId": logged_in.get("accountId", ""),
                })

        if result:
            _LOGGER.info("[Nova:Button] Autocitire trimisă cu succes pentru %s.", series)
            await self._coordinator.async_request_refresh()
        else:
            _LOGGER.error("[Nova:Button] Trimiterea autocitirilor a eșuat pentru %s.", series)
