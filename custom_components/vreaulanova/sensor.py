"""Platforma Sensor pentru Nova Power & Gas (Vreau la Nova).

Arhitectura v1.1 — PER LOC DE CONSUM (metering point):

  Un cont CRM poate avea MULTIPLE locuri de consum de același tip de utilitate.
  Exemplu: CRM 6085537 → 2 puncte de măsurare gaz, la 2 adrese diferite.

Device-uri: un device per CRM per metering point.
  - Nova Power & Gas (6085537) LC-00202600 Gaz
  - Nova Power & Gas (6085537) LC-00202592 Gaz
  - Nova Power & Gas (3047398) LC-00123456 Energie Electrică

Pattern entity_id:
  - Per MP:    sensor.{DOMAIN}_{crm}_{mp_slug}_{suffix}
  - Per meter: sensor.{DOMAIN}_{crm}_{mp_slug}_index_contor_{series}

  mp_slug = numărul locului de consum (LC-00202600 → lc00202600)

Senzori nivel cont (GLOBAL — sub FIECARE device LC):
  - Sold total, Sold prosumator, Citire permisă, Arhivă plăți

Senzori per loc de consum (1 per MP):
  - Date contract, Convenție consum, Factură restantă
  - Arhivă facturi, Revizie tehnică gaz
  - Index contor (per meter din MP)

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
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, LICENSE_DATA_KEY, MONTHS_RO
from .coordinator import NovaCoordinator

_LOGGER = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════

def _is_license_valid(hass: HomeAssistant) -> bool:
    """Verifică dacă licența este validă (real-time)."""
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    if mgr is None:
        return False
    return mgr.is_valid


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


def _utility_api_type(ut_short: str) -> str:
    """Convertește ut_short înapoi la tipul API (gas/electricity)."""
    if ut_short == "gaz":
        return "gas"
    if ut_short == "electricitate":
        return "electricity"
    return ut_short


def _mp_slug(mp: dict) -> str:
    """Generează un slug unic din numărul locului de consum.

    LC-00202600 → lc00202600  (folosit în entity_id și device identifier)
    """
    number = mp.get("number", "") or mp.get("meteringPointId", "")[:12]
    return number.lower().replace("-", "").replace(" ", "")


def _mp_device(crm: str, mp: dict) -> DeviceInfo:
    """Device info per CRM per loc de consum (metering point).

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


def _unit_for_utility(mp: dict, meter: dict | None = None) -> str | None:
    """Returnează unitatea HA potrivită pe baza datelor reale."""
    unit_raw = ""
    if meter:
        unit_raw = (meter.get("unit") or "").upper()
    if not unit_raw:
        utility = mp.get("utilityType", "")
        unit_raw = "KWH" if utility == "electricity" else "MC"

    if unit_raw in ("KWH",):
        return UnitOfEnergy.KILO_WATT_HOUR
    if unit_raw in ("MWH",):
        return UnitOfEnergy.MEGA_WATT_HOUR
    if unit_raw in ("MC", "M3"):
        return UnitOfVolume.CUBIC_METERS
    return None


def _get_first_mp(data: dict, accounts_data: dict | None = None) -> dict | None:
    """Returnează primul metering point din orice cont (pentru fallback)."""
    if accounts_data:
        for acct in accounts_data.values():
            mps = acct.get("metering_points", [])
            if mps:
                return mps[0]
    mps = data.get("metering_points", [])
    if mps:
        return mps[0]
    return None


# Luni românești (lowercase) — pentru formatarea datelor
_MONTHS_RO_LOWER = [
    "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
    "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie",
]


def _format_date_ro(date_str: str) -> str:
    """Convertește data în format românesc: '4 martie 2026'."""
    if not date_str:
        return "N/A"
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            clean = date_str[:19] if "T" in date_str else date_str
            dt = datetime.strptime(clean, fmt)
            month_name = _MONTHS_RO_LOWER[dt.month - 1]
            return f"{dt.day} {month_name} {dt.year}"
        except ValueError:
            continue
    return date_str


def _format_amount(val) -> str:
    """Formatează suma: 2.675,47 lei."""
    try:
        num = float(val)
    except (ValueError, TypeError):
        return "0 lei"
    formatted = f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} lei"


# ═══════════════════════════════════════════════
# CLASĂ DE BAZĂ — PER LOC DE CONSUM
# ═══════════════════════════════════════════════

class NovaBaseSensor(CoordinatorEntity[NovaCoordinator], SensorEntity):
    """Bază pentru toți senzorii Nova — include verificare licență + custom entity_id."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: NovaCoordinator,
        crm: str,
        mp: dict,
    ) -> None:
        super().__init__(coordinator)
        self._crm = crm
        self._mp = mp
        self._mp_id = mp.get("meteringPointId", "")
        self._mp_number = mp.get("number", "")
        self._mp_slug = _mp_slug(mp)
        self._ut_short = _utility_short(mp)
        self._ut_label = _utility_label(mp)
        self._clc_pod = mp.get("specificIdForUtilityType", "")
        self._custom_entity_id: str | None = None

    def _account_data(self) -> dict:
        """Returnează datele specifice contului (CRM) acestui senzor."""
        data = self.coordinator.data or {}
        return data.get("accounts_data", {}).get(self._crm, {})

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
        return _mp_device(self._crm, self._mp)


# ═══════════════════════════════════════════════
# LICENȚĂ NECESARĂ — SENZOR DEDICAT
# ═══════════════════════════════════════════════

class LicentaNecesaraSensor(NovaBaseSensor):
    """Senzor care afișează 'Licență necesară' când nu există licență validă."""

    _attr_icon = "mdi:license"
    _attr_translation_key = "licenta_necesara"

    def __init__(
        self,
        coordinator: NovaCoordinator,
        crm: str,
        mp: dict,
    ) -> None:
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
            "attribution": ATTRIBUTION,
        }


# ═══════════════════════════════════════════════
# ASYNC_SETUP_ENTRY
# ═══════════════════════════════════════════════

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează senzorii din config entry.

    Iterează prin TOATE conturile (principal + asociate) din accounts_data.
    Per fiecare cont, iterează prin TOATE locurile de consum (metering points).
    Fiecare MP devine un device separat cu senzori proprii.
    """
    coordinator: NovaCoordinator = entry.runtime_data.coordinator
    data = coordinator.data or {}
    accounts_data = data.get("accounts_data", {})

    license_valid = _is_license_valid(hass)

    # Fallback CRM — pentru licență invalidă (când nu avem accounts_data)
    fallback_crm = data.get("crm_viewed") or data.get("crm_logged") or entry.entry_id[:8]

    if not license_valid:
        # ── Licență INVALIDĂ: curăță senzorii normali + creează LicentaNecesaraSensor ──
        licenta_uid = f"{DOMAIN}_licenta_{fallback_crm}"
        registru = er.async_get(hass)
        for entry_reg in er.async_entries_for_config_entry(registru, entry.entry_id):
            if (
                entry_reg.domain == "sensor"
                and entry_reg.unique_id != licenta_uid
            ):
                registru.async_remove(entry_reg.entity_id)
                _LOGGER.debug(
                    "[VreauLaNova] Senzor orfan eliminat (licență expirată): %s",
                    entry_reg.entity_id,
                )
        # Fallback MP
        fallback_mp = _get_first_mp(data, accounts_data) or {"utilityType": "gas"}
        async_add_entities(
            [LicentaNecesaraSensor(coordinator, fallback_crm, fallback_mp)],
            update_before_add=True,
        )
        return

    # ── Licență VALIDĂ: curăță LicentaNecesaraSensor orfan (per fiecare cont) ──
    registru = er.async_get(hass)
    for crm in list(accounts_data.keys()) + [fallback_crm]:
        licenta_uid = f"{DOMAIN}_licenta_{crm}"
        entitate_licenta = registru.async_get_entity_id("sensor", DOMAIN, licenta_uid)
        if entitate_licenta is not None:
            registru.async_remove(entitate_licenta)
            _LOGGER.debug(
                "[VreauLaNova] LicentaNecesaraSensor orfan eliminat: %s",
                entitate_licenta,
            )

    entities: list[SensorEntity] = []

    # ── Iterăm prin TOATE conturile din accounts_data ──
    for crm, acct_data in accounts_data.items():
        contracts = acct_data.get("contracts", [])
        is_prosumer = any(c.get("prosumerContract") for c in contracts)

        metering_points = acct_data.get("metering_points", [])

        for mp in metering_points:
            slug = _mp_slug(mp)
            utility = mp.get("utilityType", "unknown")

            # ── Senzori cont-level — GLOBAL: sub FIECARE device LC ──
            # Unique ID include mp_slug → fiecare device are propriul senzor
            entities.append(NovaBalanceSensor(coordinator, crm, mp))
            entities.append(NovaCitirePermisaSensor(coordinator, crm, mp))
            entities.append(NovaArhivaPlatiSensor(coordinator, crm, mp))

            if is_prosumer:
                entities.append(NovaBalanceProsumerSensor(coordinator, crm, mp))

            # ── Senzori per loc de consum (per fiecare MP) ──
            entities.append(NovaArhivaFacturiSensor(coordinator, crm, mp))
            entities.append(NovaDateContractSensor(coordinator, crm, mp))
            entities.append(NovaConventionCurrentMonthSensor(coordinator, crm, mp))
            entities.append(NovaFacturaRestantaSensor(coordinator, crm, mp))

            # Revizie tehnică gaz — doar pentru MP-uri gaz
            if utility == "gas":
                entities.append(NovaGasRevisionSensor(coordinator, crm, mp))

            # ── Senzori per contor (meters array din MP) ──
            meters = mp.get("meters", [])
            for meter in meters:
                entities.append(NovaMeterIndexSensor(coordinator, crm, mp, meter))

    _LOGGER.debug(
        "[VreauLaNova] Se creează %d senzori pentru %d conturi, %d locuri de consum",
        len(entities), len(accounts_data),
        sum(len(a.get("metering_points", [])) for a in accounts_data.values()),
    )
    async_add_entities(entities)


# ═══════════════════════════════════════════════
# SENZORI CONT-LEVEL (1x PER CRM)
# ═══════════════════════════════════════════════

class NovaBalanceSensor(NovaBaseSensor):
    """Sold total (Lei) — GLOBAL: apare sub fiecare device LC.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_sold_total
    Toate instanțele afișează aceeași valoare (balance e per cont, nu per MP).
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "RON"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_balance"
        self._attr_name = "Sold total"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_sold_total"

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        acct = self._account_data()
        balance = acct.get("balance", {})
        return balance.get("total", 0)


class NovaBalanceProsumerSensor(NovaBaseSensor):
    """Sold prosumator (Lei) — per cont.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_sold_prosumator
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "RON"
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_balance_prosumer"
        self._attr_name = "Sold prosumator"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_sold_prosumator"

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        acct = self._account_data()
        balance = acct.get("balance", {})
        return balance.get("prosumer", 0)


class NovaCitirePermisaSensor(NovaBaseSensor):
    """Citire permisă — Da/Nu pe baza selfReadingsEnabled — per cont.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_citire_permisa
    """

    _attr_icon = "mdi:pencil-box-outline"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_citire_permisa"
        self._attr_name = "Citire permisă"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_citire_permisa"

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        data = self.coordinator.data or {}
        app_info = data.get("app_info") or {}
        enabled = app_info.get("selfReadingsEnabled", False)
        return "Da" if enabled else "Nu"


class NovaArhivaPlatiSensor(NovaBaseSensor):
    """Arhivă plăți — nr plăți pe anul curent — per cont.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_arhiva_plati
    Notă: Plățile NU au utilityType → se afișează toate plățile contului.
    """

    _attr_icon = "mdi:cash-check"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_arhiva_plati"
        self._attr_name = "Arhivă plăți"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_arhiva_plati"

    def _payments_current_year(self) -> list[dict]:
        """Filtrează plățile pe anul curent."""
        acct = self._account_data()
        payments = acct.get("payments", [])
        current_year = str(datetime.now().year)
        result = []
        for pay in payments:
            pay_date = pay.get("date", "")
            if pay_date and current_year in pay_date:
                result.append(pay)
        return result

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        return len(self._payments_current_year())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        payments = self._payments_current_year()
        attrs: dict[str, Any] = {}

        total = 0.0
        for pay in payments:
            date_ro = _format_date_ro(pay.get("date", ""))
            try:
                amount = float(pay.get("totalAmount", 0))
            except (ValueError, TypeError):
                amount = 0.0
            total += amount
            attrs[f"Plătită pe {date_ro}"] = _format_amount(amount)

        attrs["Total plăți"] = str(len(payments))
        attrs["Total plătit"] = _format_amount(total)
        return attrs


# ═══════════════════════════════════════════════
# SENZORI PER LOC DE CONSUM (PER MP)
# ═══════════════════════════════════════════════

class NovaArhivaFacturiSensor(NovaBaseSensor):
    """Arhivă facturi — nr facturi pe anul curent PER LOC DE CONSUM.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_arhiva_facturi
    Filtrează facturile pe utilityType al MP-ului.
    """

    _attr_icon = "mdi:file-document-multiple-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._utility_api = _utility_api_type(self._ut_short)
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_arhiva_facturi"
        self._attr_name = "Arhivă facturi"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_arhiva_facturi"

    def _invoices_current_year(self) -> list[dict]:
        """Filtrează facturile pe anul curent și utilitatea senzorului."""
        acct = self._account_data()
        invoices = acct.get("invoices", [])
        current_year = str(datetime.now().year)
        result = []
        for inv in invoices:
            issue_date = inv.get("issueDate", "")
            inv_utility = inv.get("utilityType", "")
            if (
                issue_date
                and current_year in issue_date
                and inv_utility == self._utility_api
            ):
                result.append(inv)
        return result

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        return len(self._invoices_current_year())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        invoices = self._invoices_current_year()
        attrs: dict[str, Any] = {}

        total = 0.0
        for inv in invoices:
            date_ro = _format_date_ro(inv.get("issueDate", ""))
            try:
                amount = float(inv.get("amountTotal", 0))
            except (ValueError, TypeError):
                amount = 0.0
            total += amount
            attrs[f"Emisă pe {date_ro}"] = _format_amount(amount)

        attrs["Total facturi"] = str(len(invoices))
        attrs["Total facturat"] = _format_amount(total)
        return attrs


class NovaDateContractSensor(NovaBaseSensor):
    """Date contract per loc de consum — status + detalii.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_date_contract
    Matching: contractId de pe MP ↔ contractId din lista de contracte.
    Fallback: match pe utilityType dacă contractId nu corespunde.
    """

    _attr_icon = "mdi:file-sign"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._mp_contract_id = mp.get("contractId", "")
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_date_contract"
        self._attr_name = "Date contract"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_date_contract"

    def _find_contract(self) -> dict | None:
        """Găsește contractul potrivit pentru acest loc de consum.

        Strategia de matching:
          1. contractId exact (MP.contractId == contract.contractId)
          2. contractId partial (ultimele 32 chars) — Nova uneori diferă primele bytes
          3. Fallback: utilityType match (dacă un singur contract pe acea utilitate)
        """
        acct = self._account_data()
        contracts = acct.get("contracts", [])
        utility = self._mp.get("utilityType", "")

        # 1. Match exact pe contractId
        if self._mp_contract_id:
            for c in contracts:
                if c.get("contractId") == self._mp_contract_id:
                    return c

        # 2. Match partial (ultimele 32 chars — Nova poate diferi în primele bytes)
        if self._mp_contract_id and len(self._mp_contract_id) > 8:
            mp_suffix = self._mp_contract_id[4:]
            for c in contracts:
                cid = c.get("contractId", "")
                if len(cid) > 8 and cid[4:] == mp_suffix:
                    return c

        # 3. Fallback: utilityType (dacă un singur contract pe acea utilitate)
        utility_contracts = [c for c in contracts if c.get("utilityType") == utility]
        if len(utility_contracts) == 1:
            return utility_contracts[0]

        return None

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        contract = self._find_contract()
        if contract:
            return contract.get("status", "N/A")
        return "N/A"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        contract = self._find_contract()
        if not contract:
            return None

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
    """Convenție consum — nr luni cu convenție + detalii per lună.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_conventie_consum
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-bar"

    _MONTH_KEYS = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    ]

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_conventie_consum"
        self._attr_name = "Convenție consum"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_conventie_consum"

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        acct = self._account_data()
        agreement_data = acct.get("agreements", {}).get(self._mp_id)
        if agreement_data:
            agreement = agreement_data.get("agreement", {})
            count = 0
            for key in self._MONTH_KEYS:
                val = agreement.get(key)
                if val is not None and val != 0:
                    count += 1
            return count
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "luni"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        acct = self._account_data()
        agreement_data = acct.get("agreements", {}).get(self._mp_id)
        if agreement_data:
            agreement = agreement_data.get("agreement", {})
            state = agreement_data.get("state", {})
            unit = state.get("unitOfMeasure", "m³")
            attrs: dict[str, Any] = {}
            for i, key in enumerate(self._MONTH_KEYS):
                val = agreement.get(key, 0)
                attrs[f"Convenție din luna {MONTHS_RO[i].lower()}"] = f"{val} {unit}"
            return attrs
        return None


class NovaFacturaRestantaSensor(NovaBaseSensor):
    """Factură restantă — Da/Nu dacă există facturi neachitate per loc de consum.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_factura_restanta
    """

    _attr_icon = "mdi:file-document-alert"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_factura_restanta"
        self._attr_name = "Factură restantă"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_factura_restanta"

    def _get_unpaid(self) -> list[dict]:
        """Returnează lista facturilor neachitate pentru acest loc de consum."""
        acct = self._account_data()
        inv_list = acct.get("invoices_by_mp", {}).get(self._clc_pod, [])
        return [
            inv for inv in inv_list
            if inv.get("status") in ("unpaid", "pastDue")
        ]

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        unpaid = self._get_unpaid()
        return "Da" if unpaid else "Nu"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        unpaid = self._get_unpaid()
        total = 0.0
        for inv in unpaid:
            try:
                total += float(inv.get("amountToPay", 0))
            except (ValueError, TypeError):
                pass

        acct = self._account_data()
        inv_list = acct.get("invoices_by_mp", {}).get(self._clc_pod, [])
        scadenta = None
        if inv_list:
            scadenta = inv_list[0].get("dueDate")

        return {
            "Total restantă": f"{round(total, 2)} RON",
            "Scadență ultima factură": scadenta,
            "Facturi neachitate": len(unpaid),
        }


# ═══════════════════════════════════════════════
# SENZORI PER CONTOR (PER METER DIN MP)
# ═══════════════════════════════════════════════

class NovaMeterIndexSensor(NovaBaseSensor):
    """Index curent contor + date ultima autocitire ca atribute.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_index_contor_{series}
    """

    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, crm, mp, meter):
        super().__init__(coordinator, crm, mp)
        self._meter = meter
        self._series = meter.get("series", "")
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_index_contor_{self._series}"
        self._attr_name = "Index contor"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_index_contor_{self._series}"
        self._attr_native_unit_of_measurement = _unit_for_utility(mp, meter)

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        acct = self._account_data()
        for mp in acct.get("metering_points", []):
            if mp.get("meteringPointId") == self._mp_id:
                for m in mp.get("meters", []):
                    if m.get("series") == self._series:
                        return m.get("currentIndex")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        acct = self._account_data()
        attrs: dict[str, Any] = {}

        readings = acct.get("readings_by_meter", {}).get(self._series, [])
        if readings:
            latest = readings[0]
            attrs["Ultima citire"] = latest.get("consumptionNewIndex")
            attrs["Consum"] = latest.get("consumption")
            attrs["Data ultima citire"] = latest.get("lastSelfReadingDate")
            attrs["Index vechi"] = latest.get("consumptionOldIndex")
        else:
            attrs["Ultima citire"] = None
            attrs["Consum"] = None
            attrs["Data ultima citire"] = None
            attrs["Index vechi"] = None

        return attrs


# ═══════════════════════════════════════════════
# SENZORI PER LOC DE CONSUM — REVIZII GAZ
# ═══════════════════════════════════════════════

class NovaGasRevisionSensor(NovaBaseSensor):
    """Revizie tehnică gaz — un senzor per loc de consum gaz.

    Entity ID: sensor.{DOMAIN}_{crm}_{mp_slug}_revizie_tehnica
    """

    _attr_icon = "mdi:wrench-clock"

    def __init__(self, coordinator, crm, mp):
        super().__init__(coordinator, crm, mp)
        self._attr_unique_id = f"{DOMAIN}_{crm}_{self._mp_slug}_revizie_tehnica"
        self._attr_name = "Revizie tehnică"
        self._custom_entity_id = f"sensor.{DOMAIN}_{crm}_{self._mp_slug}_revizie_tehnica"

    def _get_revisions(self) -> list[dict]:
        """Extrage gasRevisions din datele coordinator-ului."""
        acct = self._account_data()
        for mp in acct.get("metering_points", []):
            if mp.get("meteringPointId") == self._mp_id:
                return mp.get("gasRevisions", [])
        return []

    def _find_by_type(self, rev_type: str) -> dict | None:
        """Găsește revizia/verificarea după tip.

        API-ul Nova returnează revisionType:
          - "Revision"  → Revizie Tehnică Periodică
          - "Check"     → Verificare Tehnică Periodică
        """
        for rev in self._get_revisions():
            if rev.get("revisionType") == rev_type:
                return rev
        return None

    @staticmethod
    def _is_expired(date_str: str) -> bool:
        """Verifică dacă data a trecut."""
        if not date_str:
            return False
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date() < datetime.now().date()
        except ValueError:
            return False

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        revision = self._find_by_type("Revision")
        if revision:
            exp = revision.get("expirationDate", "")
            if not exp:
                return "Nedefinit"
            if self._is_expired(exp):
                return "Expirată"
            return "Validă"
        return "Nedefinit"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        revision = self._find_by_type("Revision")
        check = self._find_by_type("Check")

        attrs: dict[str, Any] = {}
        attrs["Data ultimei revizii"] = (
            _format_date_ro(revision.get("executionDate", "")) if revision else "Nedefinit"
        )
        attrs["Data următoarei revizii"] = (
            _format_date_ro(revision.get("expirationDate", "")) if revision else "Nedefinit"
        )
        attrs["Data ultimei verificări"] = (
            _format_date_ro(check.get("executionDate", "")) if check else "Nedefinit"
        )
        attrs["Data următoarei verificări"] = (
            _format_date_ro(check.get("expirationDate", "")) if check else "Nedefinit"
        )
        return attrs
