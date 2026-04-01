"""Platforma Button pentru Nova Power & Gas (Vreau la Nova).

Buton per punct de măsurare pentru trimiterea autocitirilor.
Nova API: POST /self-readings/add cu payload specific per contor.

Pattern entity_id: button.{DOMAIN}_{crm}_{ut_short}_{suffix}
Pattern 1:1 cu eonromania: _attr_has_entity_name = False, custom entity_id property.
Device: un serviciu per CRM per utilitate.
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


def _utility_device(crm: str, ut_short: str, ut_label: str) -> DeviceInfo:
    """Device info per CRM per utilitate — un serviciu per utilitate."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"account_{crm}_{ut_short}")},
        name=f"Nova Power & Gas ({crm}) {ut_label}",
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
            meters = mp.get("meters", [])

            for meter in meters:
                series = meter.get("series", "")
                if not series:
                    continue
                buttons.append(
                    TrimiteIndexButton(coordinator, crm, mp, meter)
                )

    if buttons:
        _LOGGER.debug(
            "[Nova:Button] Se adaugă %d butoane pentru %d conturi (entry_id=%s).",
            len(buttons), len(accounts_data), config_entry.entry_id,
        )
        async_add_entities(buttons)


# ═══════════════════════════════════════════════
# CLASĂ DE BAZĂ — PATTERN IDENTIC CU EONROMANIA
# ═══════════════════════════════════════════════

class NovaBaseButton(ButtonEntity):
    """Bază pentru toate butoanele Nova — custom entity_id."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: NovaCoordinator,
        crm: str,
        ut_short: str = "gaz",
        ut_label: str = "Gaz",
    ) -> None:
        self._coordinator = coordinator
        self._crm = crm
        self._ut_short = ut_short
        self._ut_label = ut_label
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
        return _utility_device(self._crm, self._ut_short, self._ut_label)


# ═══════════════════════════════════════════════
# BUTOANE
# ═══════════════════════════════════════════════

class TrimiteIndexButton(NovaBaseButton):
    """Buton pentru trimiterea autocitirilor la Nova API."""

    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: NovaCoordinator,
        crm: str,
        mp: dict,
        meter: dict,
    ):
        """Inițializare buton trimitere index."""
        ut_short = _utility_short(mp)
        ut_label = _utility_label(mp)
        super().__init__(coordinator, crm, ut_short, ut_label)
        self._mp = mp
        self._meter = meter

        self._clc_pod = mp.get("specificIdForUtilityType", "")
        self._series = meter.get("series", "")
        self._utility = mp.get("utilityType", "unknown")

        self._attr_name = "Trimite index"
        self._attr_unique_id = f"{DOMAIN}_{crm}_{ut_short}_trimite_index_{self._series}"
        self._attr_icon = "mdi:fire" if self._utility == "gas" else "mdi:flash"

        # Custom entity_id: button.vreaulanova_{crm}_{ut_short}_trimite_index
        self._custom_entity_id = (
            f"button.{DOMAIN}_{crm}_{ut_short}_trimite_index"
        )

    @property
    def available(self) -> bool:
        """Butonul e disponibil doar dacă licența e validă și coordinator-ul e ok."""
        return self._license_valid and self._coordinator.last_update_success

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

        # Citește valoarea din input_number entity
        input_entity_id = f"input_number.{DOMAIN}_{self._clc_pod}_{self._series}_index"
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
            # Găsim obiectul contului din associated_accounts
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
            "meterSeries": self._series,
            "meterCode": self._meter.get("meterCode", ""),
            "newIndex": index_value,
            "specificIdForUtilityType": self._clc_pod,
            "currentIndex": self._meter.get("currentIndex", 0),
            "unit": self._meter.get("unit", ""),
            "dialCode": self._meter.get("dialCode", ""),
            "accountName": account_name,
        }

        _LOGGER.info(
            "[Nova:Button] Trimitere autocitire: cont=%s, clc_pod=%s, series=%s, "
            "newIndex=%s, utility=%s",
            self._crm, self._clc_pod, self._series, index_value, self._utility,
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
            _LOGGER.info("[Nova:Button] Autocitire trimisă cu succes pentru %s.", self._series)
            await self._coordinator.async_request_refresh()
        else:
            _LOGGER.error("[Nova:Button] Trimiterea autocitirilor a eșuat pentru %s.", self._series)
