"""Platforma Button pentru Nova Power & Gas (Vreau la Nova).

Un buton „Trimite index" per loc de consum activ (cu cod CLC/POD). Locurile fără CLC/POD
(vechi / neactivate) sunt scoase de coordinator: fără contor la Nova, fără buton și fără senzori.

Pattern entity_id: button.{DOMAIN}_{crm}_{mp_slug}_trimite_index
Device: același cu al senzorilor locului (helpers.mp_device).

Trimiterea: POST /self-readings cu utilityType, meteringPointNumber, specificIdForUtilityType,
meterSeries, meterCode, newIndex, currentIndex, unit, accountName [, dialCode] — ca aplicația.
Indexul se citește din helperul input_number afișat în atributele butonului.

Rezultatul fiecărei apăsări (reușită sau motivul refuzului) apare ca notificare persistentă
în bara laterală — una per loc de consum, înlocuită la apăsarea următoare.
"""

import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import NovaApiError
from .const import ATTRIBUTION, DOMAIN, LICENSE_DATA_KEY
from .coordinator import NovaCoordinator
from .helpers import (
    format_number,
    helper_index_entity_id,
    is_active_mp,
    mp_device,
    mp_slug,
    normalize_unit,
    notification_id,
    utility_label,
)

_LOGGER = logging.getLogger(__name__)


def _unique_id(crm: str, mp: dict) -> str:
    return f"{DOMAIN}_{crm}_{mp_slug(mp)}_trimite_index"


# ═══════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Un buton „Trimite index" per loc de consum activ, pentru toate conturile (principal + asociate)."""
    coordinator: NovaCoordinator = config_entry.runtime_data.coordinator
    registru = er.async_get(hass)

    # Fără licență, fără butoane (cele create anterior ar rămâne „indisponibile" în registry)
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    if not mgr or not mgr.is_valid:
        _LOGGER.debug("[VreauLaNova] Licență invalidă — nu se creează butoane")
        for entry_reg in er.async_entries_for_config_entry(registru, config_entry.entry_id):
            if entry_reg.domain == "button":
                registru.async_remove(entry_reg.entity_id)
        return

    accounts_data = (coordinator.data or {}).get("accounts_data", {})
    buttons: list[ButtonEntity] = [
        TrimiteIndexButton(coordinator, crm, mp)
        for crm, acct_data in accounts_data.items()
        for mp in acct_data.get("metering_points", [])
        if is_active_mp(mp)  # coordinatorul a scos deja locurile fără CLC/POD; verificare defensivă
    ]

    _LOGGER.debug(
        "[VreauLaNova] Se adaugă %d butoane „Trimite index” pentru %d conturi", len(buttons), len(accounts_data)
    )
    if buttons:
        async_add_entities(buttons)


# ═══════════════════════════════════════════════
# BUTON
# ═══════════════════════════════════════════════

class TrimiteIndexButton(CoordinatorEntity[NovaCoordinator], ButtonEntity):
    """Trimite autocitirea unui loc de consum la Nova; rezultatul apare ca notificare persistentă."""

    _attr_has_entity_name = False
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: NovaCoordinator, crm: str, mp: dict) -> None:
        super().__init__(coordinator)
        self._crm = crm
        self._mp = mp
        self._mp_id = mp.get("meteringPointId", "")
        self._mp_slug = mp_slug(mp)
        self._clc_pod = mp.get("specificIdForUtilityType", "") or ""
        self._utility = mp.get("utilityType", "unknown")
        self._attr_name = "Trimite index"
        self._attr_unique_id = _unique_id(crm, mp)
        self._attr_icon = "mdi:fire" if self._utility == "gas" else "mdi:flash"
        self._custom_entity_id = f"button.{DOMAIN}_{crm}_{self._mp_slug}_trimite_index"

    @property
    def entity_id(self) -> str | None:
        return self._custom_entity_id

    @entity_id.setter
    def entity_id(self, value: str) -> None:
        self._custom_entity_id = value

    @property
    def device_info(self) -> DeviceInfo:
        return mp_device(self._crm, self._mp)

    @property
    def _license_valid(self) -> bool:
        mgr = self.coordinator.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        return bool(mgr and mgr.is_valid)

    @property
    def available(self) -> bool:
        """Disponibil cât licența e validă: motivul unui refuz (perioadă închisă, lipsă helper) apare
        în notificare, nu ca buton „Indisponibil" fără explicație."""
        return self._license_valid and self.coordinator.last_update_success

    def _current_mp(self) -> dict:
        acct = ((self.coordinator.data or {}).get("accounts_data") or {}).get(self._crm, {})
        for mp in acct.get("metering_points", []):
            if mp.get("meteringPointId") == self._mp_id:
                return mp
        return self._mp

    def _meter(self) -> dict | None:
        meters = self._current_mp().get("meters") or []
        return meters[0] if meters else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Helperul din care se citește indexul — ca utilizatorul să știe ce să creeze."""
        meter = self._meter()
        app_info = (self.coordinator.data or {}).get("app_info") or {}
        attrs: dict[str, Any] = {"Loc de consum": self._mp.get("number", ""), "CLC/POD": self._clc_pod}
        if meter:
            attrs["Serie contor"] = meter.get("series", "")
            attrs["Helper index"] = helper_index_entity_id(self._clc_pod, meter.get("series", ""))
        attrs["Perioadă de citire deschisă"] = "Da" if app_info.get("selfReadingsEnabled") else "Nu"
        if app_info.get("selfReadingIntervalMessage"):
            attrs["Interval autocitire"] = app_info["selfReadingIntervalMessage"]
        return attrs

    # ─────────────────────────────────────────
    # Apăsare
    # ─────────────────────────────────────────

    def _notify(self, success: bool, message: str) -> None:
        """Notificare persistentă (una per loc de consum; apăsarea următoare o înlocuiește)."""
        number = self._mp.get("number", "")
        title = (
            f"Nova Power & Gas — index trimis ({number})" if success
            else f"Nova Power & Gas — indexul nu a fost trimis ({number})"
        )
        persistent_notification.async_create(
            self.hass, message, title=title, notification_id=notification_id(self._crm, self._mp)
        )
        (_LOGGER.info if success else _LOGGER.warning)("[VreauLaNova] Trimite index %s: %s", number, message)

    async def async_press(self) -> None:
        """Trimite autocitirea. Nu ridică excepții: fiecare rezultat devine o notificare persistentă."""
        try:
            await self._async_submit()
        except Exception as err:  # noqa: BLE001 — utilizatorul trebuie să afle ce s-a întâmplat
            _LOGGER.exception("[VreauLaNova] Eroare neașteptată la trimiterea indexului")
            self._notify(False, f"Eroare neașteptată: {type(err).__name__}. Detalii în jurnalul Home Assistant.")

    async def _async_submit(self) -> None:
        number = self._mp.get("number", "?")
        _LOGGER.debug("[VreauLaNova] Trimite index %s: apăsat (cont %s)", number, self._crm)
        if not self._license_valid:
            self._notify(False, "Licența integrării nu este validă — indexul nu poate fi trimis.")
            return

        api = self.coordinator.api
        data = self.coordinator.data or {}

        # 1. Perioada de autocitire — verificată acum la Nova (datele salvate pot avea o oră)
        app_info = data.get("app_info") or {}
        try:
            app_info = await api.async_get_app_info() or app_info
        except NovaApiError as err:
            _LOGGER.debug("[VreauLaNova] /system/info indisponibil (%s) — se folosesc datele salvate", err)
        if not app_info.get("selfReadingsEnabled"):
            lines = ["Perioada de autocitire nu este deschisă acum la Nova."]
            if app_info.get("selfReadingIntervalMessage"):
                lines.append(app_info["selfReadingIntervalMessage"])
            for ann in app_info.get("announcements") or []:
                if isinstance(ann, dict) and ann.get("message"):
                    lines.append(f"Anunț Nova: {ann['message']}")
            self._notify(False, "\n\n".join(lines))
            return

        # 2. Indexul din helperul input_number (seria vine din contorul cunoscut)
        meter = self._meter()
        if not meter:
            self._notify(False, f"Nova nu a trimis niciun contor pentru locul {number}. "
                                "Încearcă după următoarea actualizare a integrării.")
            return
        series = meter.get("series", "")
        helper = helper_index_entity_id(self._clc_pod, series)
        state = self.hass.states.get(helper)
        if not state or state.state in ("unknown", "unavailable"):
            self._notify(False, f"Nu există helperul `{helper}` sau nu are valoare.\n\n"
                                "Creează-l din Setări → Dispozitive și servicii → Ajutoare → Număr, "
                                "cu exact acest ID, și scrie în el indexul de trimis.")
            return
        try:
            index_value = int(float(state.state))
        except (ValueError, TypeError):
            self._notify(False, f"Valoarea din `{helper}` nu este un număr: „{state.state}”.")
            return

        acct = (data.get("accounts_data") or {}).get(self._crm, {})
        needs_switch = (api.crm_viewed_account or "") != self._crm
        target = next(
            (aa for aa in api.associated_accounts or [] if str(aa.get("accountNumber", "")).strip() == self._crm),
            None,
        )
        if needs_switch and target is None:
            self._notify(False, f"Contul asociat {self._crm} nu mai este disponibil în contul Nova — indexul nu a fost trimis.")
            return

        # 3. Comutare cont (dacă e asociat) + contorul real + trimitere — sub lacătul de cont
        async with api.account_lock:
            try:
                if needs_switch:
                    _LOGGER.debug("[VreauLaNova] Trimite index %s: comutare pe contul %s", number, self._crm)
                    await api.async_switch_account(target)

                if meter.get("fromHistory"):
                    # Contorul salvat e reconstruit din istoric: cerem acum contorul real (cu currentIndex
                    # și meterCode la zi), exact cum face aplicația înainte de trimitere.
                    fresh = await api.async_get_metering_points_self_readings()
                    real = next((m for m in fresh if m.get("meteringPointId") == self._mp_id), {})
                    meters = real.get("meters") or []
                    meter = next((m for m in meters if m.get("series") == series), meters[0] if meters else None)
                    if not meter:
                        self._notify(False, f"Nova nu oferă acum contorul locului {number} pentru autocitire, "
                                            "deși perioada este deschisă. Încearcă din nou mai târziu.")
                        return
                    series = meter.get("series", series)

                payload = {
                    "utilityType": self._utility,
                    "meteringPointNumber": number,
                    "specificIdForUtilityType": self._clc_pod,
                    "meterSeries": series,
                    "meterCode": meter.get("meterCode", ""),
                    "newIndex": index_value,
                    "currentIndex": meter.get("currentIndex", 0),
                    "unit": meter.get("unit", ""),
                    "accountName": acct.get("account_name", ""),
                }
                if meter.get("dialCode"):
                    payload["dialCode"] = meter["dialCode"]
                _LOGGER.info(
                    "[VreauLaNova] Trimite index %s: cont %s, serie %s, index nou %s (index curent %s)",
                    number, self._crm, series, index_value, payload["currentIndex"],
                )
                result = await api.async_submit_self_reading(payload)
            except NovaApiError as err:
                reason = err.message or str(err)
                self._notify(False, f"Nova a refuzat indexul **{index_value}** (contor {series}): {reason}")
                return
            finally:
                if needs_switch and not await self.coordinator._async_switch_to_primary():
                    self.coordinator._session_on_other_account = True

        unit = normalize_unit(meter.get("unit")) or ""
        nova_message = result.get("message") if isinstance(result, dict) else None
        self._notify(True, (
            f"Indexul **{format_number(index_value)}{f' {unit}' if unit else ''}** a fost trimis pentru "
            f"{utility_label(self._mp).lower()}, contor {series}, locul {number}, "
            f"pe {dt_util.now().strftime('%d.%m.%Y, la %H:%M')}."
            + (f"\n\nNova: {nova_message}" if nova_message else "")
        ))
        await self.coordinator.async_request_refresh()
