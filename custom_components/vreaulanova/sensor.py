"""Platforma Sensor pentru Nova Power & Gas (Vreau la Nova).

Un device per cont (CRM) per loc de consum (metering point):
  - Nova Power & Gas (6085537) LC-00202600 Gaz
  - Nova Power & Gas (3047398) LC-00123456 Energie Electrică

Pattern entity_id:
  - Per loc:    sensor.{DOMAIN}_{crm}_{mp_slug}_{suffix}
  - Per contor: sensor.{DOMAIN}_{crm}_{mp_slug}_index_contor_{series}
  mp_slug = numărul locului de consum (LC-00202600 → lc00202600)

Senzori la nivel de cont (aceeași valoare sub fiecare loc al contului):
  - Sold total, Sold prosumator (doar prosumatori), Citire permisă
Senzori per loc de consum:
  - Date contract, Convenție consum, Factură restantă, Arhivă facturi, Arhivă plăți,
    Revizie tehnică (gaz), Consum lunar, Cost lunar (din raportul Nova), Index contor (per contor)

Locurile fără CLC/POD (vechi / neactivate) nu au contract activ, facturi sau contor: coordinatorul
le scoate, deci nu primesc device și senzori (cele create de versiunile anterioare se șterg la pornire).

Conform STANDARD-LICENTA.md:
- Licență invalidă → doar LicentaNecesaraSensor
- Licență validă → cleanup LicentaNecesaraSensor + senzori normali
"""

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import ATTRIBUTION, DOMAIN, LICENSE_DATA_KEY, MONTHS_RO
from .coordinator import NovaCoordinator
from .helpers import (
    days_word,
    format_amount,
    format_date_ro,
    format_number,
    ha_unit,
    helper_index_entity_id,
    is_active_mp,
    mp_device,
    mp_slug,
    normalize_unit,
    parse_date,
    period_label,
    to_float,
    utility_label,
    utility_short,
)

_LOGGER = logging.getLogger(__name__)

# Facturi cu sumă de plată (aplicația: paid, unpaid, pastDue, inProcessing, reversed)
_UNPAID = ("unpaid", "pastDue")


def _is_license_valid(hass: HomeAssistant) -> bool:
    """Verifică dacă licența este validă (real-time)."""
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    return bool(mgr and mgr.is_valid)


def _get_first_mp(accounts_data: dict | None) -> dict | None:
    """Primul loc de consum din orice cont (pentru senzorul „Licență necesară")."""
    for acct in (accounts_data or {}).values():
        if acct.get("metering_points"):
            return acct["metering_points"][0]
    return None


def _belongs_to(item: dict, mp: dict, number_key: str) -> bool | None:
    """Factura / plata e a acestui loc? None dacă elementul nu spune locul (atunci se ia tot contul)."""
    number = item.get(number_key)
    code = item.get("meteringPointCode")
    if not number and not code:
        return None
    return (number and number == mp.get("number")) or (code and code == mp.get("specificIdForUtilityType")) or False


def _report(acct: dict, mp: dict) -> dict | None:
    """Raportul consum-costuri al locului (după numărul LC și utilitate), dacă Nova îl oferă."""
    return ((acct.get("consumption_reports") or {}).get(mp.get("number") or "") or {}).get(mp.get("utilityType") or "")


# ═══════════════════════════════════════════════
# CLASĂ DE BAZĂ — PER LOC DE CONSUM
# ═══════════════════════════════════════════════

class NovaBaseSensor(CoordinatorEntity[NovaCoordinator], SensorEntity):
    """Bază pentru toți senzorii Nova — verificare licență, entity_id propriu, device per loc."""

    _attr_has_entity_name = False
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: NovaCoordinator, crm: str, mp: dict) -> None:
        super().__init__(coordinator)
        self._crm = crm
        self._mp = mp
        self._mp_id = mp.get("meteringPointId", "")
        self._mp_number = mp.get("number", "")
        self._mp_slug = mp_slug(mp)
        self._ut_short = utility_short(mp)
        self._ut_label = utility_label(mp)
        self._clc_pod = mp.get("specificIdForUtilityType", "") or ""
        self._custom_entity_id: str | None = None

    def _set_ids(self, suffix: str, name: str) -> None:
        """unique_id, entity_id și numele: {DOMAIN}_{crm}_{mp_slug}_{suffix}."""
        self._attr_unique_id = f"{DOMAIN}_{self._crm}_{self._mp_slug}_{suffix}"
        self._attr_name = name

    def _account_data(self) -> dict:
        """Datele contului (CRM) acestui senzor."""
        return ((self.coordinator.data or {}).get("accounts_data") or {}).get(self._crm, {})

    def _current_mp(self) -> dict:
        """Locul de consum din ultima actualizare (cu contoare / revizii la zi), altfel cel de la creare."""
        for mp in self._account_data().get("metering_points", []):
            if mp.get("meteringPointId") == self._mp_id:
                return mp
        return self._mp

    @property
    def _license_valid(self) -> bool:
        """Verifică dacă licența este validă (real-time, STANDARD-LICENTA §3.4)."""
        mgr = self.coordinator.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        return mgr.is_valid if mgr else False

    @property
    def entity_id(self) -> str | None:
        return self._custom_entity_id

    @entity_id.setter
    def entity_id(self, value: str) -> None:
        self._custom_entity_id = value

    @property
    def device_info(self) -> DeviceInfo:
        return mp_device(self._crm, self._mp)


# ═══════════════════════════════════════════════
# LICENȚĂ NECESARĂ — SENZOR DEDICAT
# ═══════════════════════════════════════════════

class LicentaNecesaraSensor(NovaBaseSensor):
    """Senzor care afișează 'Licență necesară' când nu există licență validă."""

    _attr_icon = "mdi:license"
    _attr_translation_key = "licenta_necesara"

    def __init__(self, coordinator: NovaCoordinator, crm: str, mp: dict) -> None:
        super().__init__(coordinator, crm, mp)
        self._attr_name = "Nova Power & Gas"
        self._attr_unique_id = f"{DOMAIN}_licenta_{crm}"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_licenta"

    @property
    def native_value(self):
        return "Licență necesară"

    @property
    def extra_state_attributes(self):
        return {
            "status": "Licență necesară",
            "info": "Integrarea necesită o licență validă pentru a funcționa.",
        }


# ═══════════════════════════════════════════════
# ASYNC_SETUP_ENTRY
# ═══════════════════════════════════════════════

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează senzorii: pentru fiecare cont (principal + asociate), pentru fiecare loc de consum."""
    coordinator: NovaCoordinator = entry.runtime_data.coordinator
    data = coordinator.data or {}
    accounts_data = data.get("accounts_data", {})
    fallback_crm = data.get("crm_viewed") or data.get("crm_logged") or entry.entry_id[:8]

    if not _is_license_valid(hass):
        # ── Licență INVALIDĂ: curăță senzorii normali + creează LicentaNecesaraSensor ──
        licenta_uid = f"{DOMAIN}_licenta_{fallback_crm}"
        registru = er.async_get(hass)
        for entry_reg in er.async_entries_for_config_entry(registru, entry.entry_id):
            if entry_reg.domain == "sensor" and entry_reg.unique_id != licenta_uid:
                registru.async_remove(entry_reg.entity_id)
                _LOGGER.debug("[VreauLaNova] Senzor orfan eliminat (licență expirată): %s", entry_reg.entity_id)
        fallback_mp = _get_first_mp(accounts_data) or {"utilityType": "gas"}
        async_add_entities([LicentaNecesaraSensor(coordinator, fallback_crm, fallback_mp)], update_before_add=True)
        return

    # ── Licență VALIDĂ: curăță LicentaNecesaraSensor orfan (per fiecare cont) ──
    registru = er.async_get(hass)
    for crm in list(accounts_data.keys()) + [fallback_crm]:
        entitate_licenta = registru.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_licenta_{crm}")
        if entitate_licenta is not None:
            registru.async_remove(entitate_licenta)
            _LOGGER.debug("[VreauLaNova] LicentaNecesaraSensor orfan eliminat: %s", entitate_licenta)

    entities: list[SensorEntity] = []
    for crm, acct_data in accounts_data.items():
        contracts = acct_data.get("contracts", [])
        # API-ul nou: isProsumer în sold; prosumerContract era în contractele de pe API-ul vechi
        is_prosumer = bool((acct_data.get("balance") or {}).get("isProsumer")) or any(
            c.get("prosumerContract") for c in contracts
        )

        for mp in acct_data.get("metering_points", []):
            created = [
                NovaBalanceSensor(coordinator, crm, mp),
                NovaCitirePermisaSensor(coordinator, crm, mp),
                NovaArhivaPlatiSensor(coordinator, crm, mp),
                NovaArhivaFacturiSensor(coordinator, crm, mp),
                NovaDateContractSensor(coordinator, crm, mp),
                NovaConventionCurrentMonthSensor(coordinator, crm, mp),
                NovaFacturaRestantaSensor(coordinator, crm, mp),
            ]
            if is_prosumer:
                created.append(NovaBalanceProsumerSensor(coordinator, crm, mp))
            if mp.get("utilityType") == "gas":
                created.append(NovaGasRevisionSensor(coordinator, crm, mp))
            if _report(acct_data, mp):
                created.append(NovaConsumLunarSensor(coordinator, crm, mp))
                created.append(NovaCostLunarSensor(coordinator, crm, mp))
            for meter in mp.get("meters") or []:
                if meter.get("series"):
                    created.append(NovaMeterIndexSensor(coordinator, crm, mp, meter))
            entities.extend(created)
            _LOGGER.debug("[VreauLaNova] Cont %s · %s: %d senzori", crm, mp.get("number", "?"), len(created))

    _LOGGER.debug(
        "[VreauLaNova] Se creează %d senzori pentru %d conturi, %d locuri de consum",
        len(entities), len(accounts_data),
        sum(len(a.get("metering_points", [])) for a in accounts_data.values()),
    )
    async_add_entities(entities)


# ═══════════════════════════════════════════════
# SENZORI LA NIVEL DE CONT
# ═══════════════════════════════════════════════

class NovaBalanceSensor(NovaBaseSensor):
    """Sold total (lei) al contului — apare sub fiecare loc de consum al contului.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_sold_total
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "RON"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("balance", "Sold total")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_sold_total"

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return None  # senzor numeric: fără licență → necunoscut
        return to_float((self._account_data().get("balance") or {}).get("total")) or 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        balance = self._account_data().get("balance") or {}
        attrs: dict[str, Any] = {}
        for key, label in (("gas", "Gaz"), ("electricity", "Energie electrică")):
            if to_float(balance.get(key)):
                attrs[label] = format_amount(balance[key])
        if to_float(balance.get("processingPayments")):
            attrs["Plăți în procesare"] = format_amount(balance["processingPayments"])
        if balance.get("pendingInvoicesCount") is not None:
            attrs["Facturi de plată"] = balance["pendingInvoicesCount"]
        per_mp = balance.get("perMeteringPoint")
        if isinstance(per_mp, dict) and self._mp_number in per_mp:
            attrs["Sold pe acest loc"] = format_amount((per_mp[self._mp_number] or {}).get("total", per_mp[self._mp_number]))
        return attrs


class NovaBalanceProsumerSensor(NovaBaseSensor):
    """Sold prosumator (lei) — doar la conturile de prosumator.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_sold_prosumator
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "RON"
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("balance_prosumer", "Sold prosumator")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_sold_prosumator"

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return None
        return to_float((self._account_data().get("balance") or {}).get("prosumer")) or 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        due = to_float((self._account_data().get("balance") or {}).get("prosumerDue"))
        return {"De încasat / de plătit (prosumator)": format_amount(due)} if due else {}


class NovaCitirePermisaSensor(NovaBaseSensor):
    """Citire permisă — Da/Nu: e deschisă perioada de autocitire la Nova?

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_citire_permisa
    """

    _attr_icon = "mdi:pencil-box-outline"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("citire_permisa", "Citire permisă")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_citire_permisa"

    def _app_info(self) -> dict:
        return (self.coordinator.data or {}).get("app_info") or {}

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        return "Da" if self._app_info().get("selfReadingsEnabled") else "Nu"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        info = self._app_info()
        attrs: dict[str, Any] = {}
        if info.get("selfReadingIntervalMessage"):
            attrs["Interval autocitire"] = info["selfReadingIntervalMessage"]
        for i, ann in enumerate(info.get("announcements") or [], start=1):
            if isinstance(ann, dict) and ann.get("message"):
                attrs["Anunț Nova" if i == 1 else f"Anunț Nova {i}"] = ann["message"]
        return attrs


# ═══════════════════════════════════════════════
# SENZORI PER LOC DE CONSUM
# ═══════════════════════════════════════════════

class NovaArhivaPlatiSensor(NovaBaseSensor):
    """Arhivă plăți — numărul plăților din anul curent pentru acest loc de consum.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_arhiva_plati
    Plățile au meteringPointNumber pe API-ul nou; fără el (API vechi) se iau toate plățile contului.
    """

    _attr_icon = "mdi:cash-check"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("arhiva_plati", "Arhivă plăți")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_arhiva_plati"

    def _payments_current_year(self) -> list[dict]:
        year = datetime.now().year
        result = []
        for pay in self._account_data().get("payments", []):
            paid_on = parse_date(pay.get("date"))
            if paid_on and paid_on.year == year and _belongs_to(pay, self._mp, "meteringPointNumber") is not False:
                result.append(pay)
        return result

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return None
        return len(self._payments_current_year())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        payments = self._payments_current_year()
        attrs: dict[str, Any] = {}
        total = 0.0
        for pay in sorted(payments, key=lambda p: parse_date(p.get("date")) or datetime.min.date()):
            amount = to_float(pay.get("totalAmount", pay.get("paidValue"))) or 0.0
            total += amount
            key = f"Plătită pe {format_date_ro(pay.get('date'))}"
            while key in attrs:  # două plăți în aceeași zi
                key += " "
            attrs[key] = format_amount(amount)
        attrs["Total plăți"] = str(len(payments))
        attrs["Total plătit"] = format_amount(total)
        return attrs


class NovaArhivaFacturiSensor(NovaBaseSensor):
    """Arhivă facturi — numărul facturilor emise în anul curent pentru acest loc de consum.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_arhiva_facturi
    Înainte se filtra doar pe utilitate: două locuri de gaz arătau aceleași facturi.
    """

    _attr_icon = "mdi:file-document-multiple-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("arhiva_facturi", "Arhivă facturi")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_arhiva_facturi"

    def _invoices_current_year(self) -> list[dict]:
        year = datetime.now().year
        result = []
        for inv in self._account_data().get("invoices", []):
            issued = parse_date(inv.get("issueDate"))
            if not issued or issued.year != year:
                continue
            mine = _belongs_to(inv, self._mp, "meteringPointNumber")
            if mine or (mine is None and inv.get("utilityType") == self._mp.get("utilityType")):
                result.append(inv)
        return result

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return None
        return len(self._invoices_current_year())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        invoices = self._invoices_current_year()
        attrs: dict[str, Any] = {}
        total = 0.0
        for inv in sorted(invoices, key=lambda i: parse_date(i.get("issueDate")) or datetime.min.date()):
            amount = to_float(inv.get("amountTotal")) or 0.0
            total += amount
            text = format_amount(amount)
            if inv.get("status") in _UNPAID:
                text += " (neachitată)"
            key = f"Emisă pe {format_date_ro(inv.get('issueDate'))}"
            while key in attrs:  # două facturi în aceeași zi
                key += " "
            attrs[key] = text
        attrs["Total facturi"] = str(len(invoices))
        attrs["Total facturat"] = format_amount(total)
        return attrs


class NovaDateContractSensor(NovaBaseSensor):
    """Date contract per loc de consum — starea contractului + detalii.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_date_contract
    Potrivire: contractId-ul locului ↔ contractId din /contracts; altfel, dacă există un singur
    contract pe acea utilitate și un singur loc ACTIV pe ea, acela. Locurile fără CLC/POD nu
    primesc contractul altui loc (înainte: „Activ", cu datele contractului celuilalt loc).
    """

    _attr_icon = "mdi:file-sign"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._mp_contract_id = mp.get("contractId", "") or ""
        self._set_ids("date_contract", "Date contract")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_date_contract"

    def _find_contract(self) -> dict | None:
        acct = self._account_data()
        contracts = acct.get("contracts", [])
        if self._mp_contract_id:
            for c in contracts:
                if c.get("contractId") == self._mp_contract_id:
                    return c
        if not is_active_mp(self._mp):
            return None
        utility = self._mp.get("utilityType", "")
        on_utility = [c for c in contracts if c.get("utilityType") == utility]
        active_mps = [
            m for m in acct.get("metering_points", []) if m.get("utilityType") == utility and is_active_mp(m)
        ]
        if len(on_utility) == 1 and len(active_mps) == 1:
            return on_utility[0]
        return None

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        if not is_active_mp(self._mp):
            return "Inactiv"
        contract = self._find_contract()
        return contract.get("status", "N/A") if contract else "N/A"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        if not is_active_mp(self._mp):
            return {
                "Loc de consum": self._mp_number,
                "Motiv": "Nova nu are cod CLC/POD pentru acest loc (fără contract activ, facturi sau contor).",
            }
        contract = self._find_contract()
        if not contract:
            return {"Loc de consum": self._mp_number, "CLC/POD": self._clc_pod}
        return {
            "Contract": contract.get("number", "N/A"),
            "Tip client": contract.get("type", "N/A"),
            "Semnat la": contract.get("signedAt", "N/A"),
            "Intrat în vigoare": contract.get("inForceAt", "N/A"),
            "Tip": contract.get("invoiceDeliveryType", "N/A"),
            "Loc de consum": self._mp_number,
            "CLC/POD": self._clc_pod,
        }


class NovaConventionCurrentMonthSensor(NovaBaseSensor):
    """Convenție consum — câte luni au convenție + valoarea pe fiecare lună.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_conventie_consum
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-bar"
    _attr_native_unit_of_measurement = "luni"

    _MONTH_KEYS = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    ]

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("conventie_consum", "Convenție consum")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_conventie_consum"

    def _agreement(self) -> dict | None:
        return (self._account_data().get("agreements") or {}).get(self._mp_id)

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return None
        data = self._agreement()
        if not data:
            return None
        agreement = data.get("agreement") or {}
        return sum(1 for key in self._MONTH_KEYS if agreement.get(key) not in (None, 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        data = self._agreement()
        if not data:
            return None
        agreement = data.get("agreement") or {}
        state = data.get("state") or {}
        unit = normalize_unit(state.get("unitOfMeasure")) or state.get("unitOfMeasure") or "m³"
        attrs: dict[str, Any] = {
            f"Convenție din luna {MONTHS_RO[i].lower()}": f"{format_number(agreement.get(key, 0) or 0)} {unit}"
            for i, key in enumerate(self._MONTH_KEYS)
        }
        current = self._MONTH_KEYS[datetime.now().month - 1]
        attrs["Luna curentă"] = f"{format_number(agreement.get(current, 0) or 0)} {unit}"
        if "isEditable" in state:
            attrs["Se poate modifica"] = "Da" if state["isEditable"] else "Nu"
        return attrs


class NovaFacturaRestantaSensor(NovaBaseSensor):
    """Factură restantă — Da/Nu: are locul facturi neachitate?

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_factura_restanta
    Atribute: fiecare factură neachitată (sumă + scadență), totalul și, pentru automatizări,
    „Următoarea scadență" + „Zile până la scadență" (număr, negativ după scadență).
    """

    _attr_icon = "mdi:file-document-alert"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("factura_restanta", "Factură restantă")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_factura_restanta"

    def _invoices(self) -> list[dict]:
        return (self._account_data().get("invoices_by_mp") or {}).get(self._clc_pod, []) if self._clc_pod else []

    def _unpaid(self) -> list[dict]:
        return [inv for inv in self._invoices() if inv.get("status") in _UNPAID]

    @staticmethod
    def _to_pay(inv: dict) -> float:
        """Rămas de plată: amountRemaining (după plăți parțiale), altfel amountToPay."""
        remaining = to_float(inv.get("amountRemaining"))
        return remaining if remaining else (to_float(inv.get("amountToPay")) or 0.0)

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        return "Da" if self._unpaid() else "Nu"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        unpaid = self._unpaid()
        today = datetime.now().date()
        attrs: dict[str, Any] = {}
        total = 0.0
        due_dates = []
        for inv in unpaid:
            amount = self._to_pay(inv)
            total += amount
            due = parse_date(inv.get("dueDate"))
            if due:
                due_dates.append(due)
                days = (due - today).days
                when = (
                    f"termen depășit cu {days_word(days)}" if days < 0
                    else "scadentă astăzi" if days == 0
                    else f"scadentă pe {format_date_ro(inv['dueDate'])} (peste {days_word(days)})"
                )
            else:
                when = "fără dată de scadență"
            attrs[f"Factură {inv.get('invoiceId', '?')}"] = f"{format_amount(amount)}, {when}"

        invoices = self._invoices()
        attrs["Total restantă"] = f"{round(total, 2)} RON"
        attrs["Scadență ultima factură"] = invoices[0].get("dueDate") if invoices else None
        attrs["Facturi neachitate"] = len(unpaid)
        if due_dates:
            nearest = min(due_dates)
            attrs["Următoarea scadență"] = nearest.strftime("%d.%m.%Y")
            attrs["Zile până la scadență"] = (nearest - today).days
        return attrs


class NovaConsumLunarSensor(NovaBaseSensor):
    """Consum lunar — din raportul Nova „consum și costuri": ultima lună cu consum + istoricul pe 12 luni.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_consum_lunar
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("consum_lunar", "Consum lunar")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_consum_lunar"
        self._attr_icon = "mdi:fire" if mp.get("utilityType") == "gas" else "mdi:lightning-bolt"
        acct = ((coordinator.data or {}).get("accounts_data") or {}).get(crm, {})
        summary = ((_report(acct, mp) or {}).get("summary") or {}).get(mp.get("utilityType")) or {}
        self._attr_native_unit_of_measurement = ha_unit(mp, summary.get("unit"))

    def _months(self) -> list[tuple[str, dict]]:
        report = _report(self._account_data(), self._mp) or {}
        utility = self._mp.get("utilityType")
        return [(m.get("period", ""), m.get(utility) or {}) for m in report.get("monthly") or [] if isinstance(m, dict)]

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return None
        with_data = [v for _, v in self._months() if v.get("consumption") is not None]
        return with_data[-1]["consumption"] if with_data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        report = _report(self._account_data(), self._mp) or {}
        summary = (report.get("summary") or {}).get(self._mp.get("utilityType")) or {}
        unit = normalize_unit(summary.get("unit")) or self._attr_native_unit_of_measurement or ""
        months = self._months()
        last = next((p for p, v in reversed(months) if v.get("consumption") is not None), None)
        attrs: dict[str, Any] = {}
        if last:
            attrs["Luna"] = period_label(last)
        if summary.get("averageMonthlyConsumption") is not None:
            attrs["Consum mediu lunar"] = f"{format_number(summary['averageMonthlyConsumption'])} {unit}"
        if summary.get("consumptionTotal") is not None:
            attrs["Consum total"] = (
                f"{format_number(summary['consumptionTotal'])} {unit} ({summary.get('monthsWithData', '?')} luni cu date)"
            )
        for period, values in months:
            value = values.get("consumption")
            attrs[f"Consum {period_label(period)}"] = f"{format_number(value)} {unit}" if value is not None else "fără date"
        return attrs


class NovaCostLunarSensor(NovaBaseSensor):
    """Cost lunar (lei) — din raportul Nova „consum și costuri": ultima lună facturată + istoricul pe 12 luni.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_cost_lunar
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "RON"
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("cost_lunar", "Cost lunar")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_cost_lunar"

    def _months(self) -> list[tuple[str, dict]]:
        report = _report(self._account_data(), self._mp) or {}
        utility = self._mp.get("utilityType")
        return [(m.get("period", ""), m.get(utility) or {}) for m in report.get("monthly") or [] if isinstance(m, dict)]

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return None
        with_cost = [to_float(v.get("cost")) for _, v in self._months() if v.get("cost") is not None]
        return round(with_cost[-1], 2) if with_cost else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        report = _report(self._account_data(), self._mp) or {}
        summary = (report.get("summary") or {}).get(self._mp.get("utilityType")) or {}
        months = self._months()
        last = next((p for p, v in reversed(months) if v.get("cost") is not None), None)
        attrs: dict[str, Any] = {}
        if last:
            attrs["Luna"] = period_label(last)
        if summary.get("averageMonthlyCost") is not None:
            attrs["Cost mediu lunar"] = format_amount(summary["averageMonthlyCost"])
        if summary.get("costTotal") is not None:
            attrs["Cost total"] = f"{format_amount(summary['costTotal'])} ({summary.get('monthsWithData', '?')} luni cu date)"
        for period, values in months:
            cost = values.get("cost")
            attrs[f"Cost {period_label(period)}"] = format_amount(cost) if cost is not None else "fără date"
        return attrs


# ═══════════════════════════════════════════════
# SENZORI PER CONTOR
# ═══════════════════════════════════════════════

class NovaMeterIndexSensor(NovaBaseSensor):
    """Index curent al contorului + ultima autocitire ca atribute.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_index_contor_{series}
    În afara perioadei de citire, Nova nu dă contoarele: indexul vine din ultima autocitire.
    Unitate + device_class (gaz / energie) → poate fi folosit în panoul Energie.
    """

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, crm, mp, meter):
        super().__init__(coordinator, crm, mp)
        self._series = meter.get("series", "")
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_index_contor_{self._series}"
        self._attr_name = "Index contor"
        # Seria poate conține „/" sau majuscule: entity_id normalizat ca în HA (slugify)
        self._custom_entity_id = f"sensor.{slugify(f'{DOMAIN}_{crm}_{self._mp_slug}_index_contor_{self._series}')}"
        unit = ha_unit(mp, meter.get("unit"))
        self._attr_native_unit_of_measurement = unit
        if unit == UnitOfVolume.CUBIC_METERS and mp.get("utilityType") == "gas":
            self._attr_device_class = SensorDeviceClass.GAS
        elif unit in (UnitOfEnergy.KILO_WATT_HOUR, UnitOfEnergy.MEGA_WATT_HOUR):
            self._attr_device_class = SensorDeviceClass.ENERGY

    def _meter(self) -> dict | None:
        for m in self._current_mp().get("meters") or []:
            if m.get("series") == self._series:
                return m
        return None

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return None
        meter = self._meter()
        return to_float(meter.get("currentIndex")) if meter else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        readings = (self._account_data().get("readings_by_meter") or {}).get(self._series, [])
        latest = readings[0] if readings else {}
        meter = self._meter() or {}
        return {
            # API-ul nou: newIndex / oldIndex / period (dd.mm.yyyy); cele vechi rămân ca rezervă
            "Ultima citire": latest.get("newIndex", latest.get("consumptionNewIndex")),
            "Consum": latest.get("consumption"),
            "Data ultima citire": latest.get("period") or latest.get("lastSelfReadingDate"),
            "Index vechi": latest.get("oldIndex", latest.get("consumptionOldIndex")),
            "Tip citire": latest.get("readingType"),
            "Sursa indexului": "ultima autocitire" if meter.get("fromHistory") else "contor Nova (perioada de citire)",
            "Serie contor": self._series,
            "Helper index": helper_index_entity_id(self._clc_pod, self._series),
        }


# ═══════════════════════════════════════════════
# REVIZII GAZ
# ═══════════════════════════════════════════════

class NovaGasRevisionSensor(NovaBaseSensor):
    """Revizie tehnică gaz — Validă / Expirată / Nedefinit.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_revizie_tehnica
    Revizii: GET /metering-points/gas-revisions, pe CLC; „Revision" = revizie tehnică periodică,
    „Check" = verificare tehnică periodică.
    """

    _attr_icon = "mdi:wrench-clock"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._set_ids("revizie_tehnica", "Revizie tehnică")
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_revizie_tehnica"

    def _find_by_type(self, rev_type: str) -> dict | None:
        # API-ul nou trimite „gasRevisions": null la locurile fără revizii
        for rev in self._current_mp().get("gasRevisions") or []:
            if rev.get("revisionType") == rev_type:
                return rev
        return None

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        revision = self._find_by_type("Revision")
        expires = parse_date((revision or {}).get("expirationDate"))
        if not expires:
            return "Nedefinit"
        return "Expirată" if expires < datetime.now().date() else "Validă"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        revision = self._find_by_type("Revision")
        check = self._find_by_type("Check")
        attrs: dict[str, Any] = {
            "Data ultimei revizii": format_date_ro(revision.get("executionDate")) if revision else "Nedefinit",
            "Data următoarei revizii": format_date_ro(revision.get("expirationDate")) if revision else "Nedefinit",
            "Data ultimei verificări": format_date_ro(check.get("executionDate")) if check else "Nedefinit",
            "Data următoarei verificări": format_date_ro(check.get("expirationDate")) if check else "Nedefinit",
        }
        today = datetime.now().date()
        for label, item in (("revizie", revision), ("verificare", check)):
            expires = parse_date((item or {}).get("expirationDate"))
            if expires:
                attrs[f"Zile până la {label}"] = (expires - today).days
        return attrs
