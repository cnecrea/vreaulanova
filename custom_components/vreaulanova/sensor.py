"""Platforma Sensor pentru integrarea Nova Power & Gas."""
from __future__ import annotations

from datetime import datetime
import logging
import re
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType

from .coordinator import NovaPGDataCoordinator
from .const import DOMAIN, LOGGER, DEFAULT_NAME, ATTRIBUTION

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """
    Configurează platforma sensor, folosind configurarea de la config entry.
    Creează senzori dinamici PE ANI pentru fiecare IdPunctConsum (EE/GN) și index (EE/GN).
    Filtrăm anii, ca să nu apară senzori prea vechi / nerelevanți.
    """
    coordinator: NovaPGDataCoordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")

    if not coordinator:
        coordinator = NovaPGDataCoordinator(hass, entry.data)
        hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # Facem prima actualizare (pentru a avea date)
    await coordinator.async_config_entry_first_refresh()


    sensors = []

    # Obținem datele locurilor de consum
    data = coordinator.data.get("locuri_consum", {})
    locuri = data.get("data", {}).get("locuriConsum", [])

    # Adăugăm senzori pentru locurile de consum cu AreContractEE=1
    for pc in locuri:
        if pc.get("AreContractEE") == "1":
            sensors.append(DateContractEESensor(coordinator, entry, pc.get("IdPunctConsum")))

    # Adăugăm senzori pentru locurile de consum cu AreContractGN=1
    for pc in locuri:
        if pc.get("AreContractGN") == "1":
            sensors.append(DateContractGNSensor(coordinator, entry, pc.get("IdPunctConsum")))

    # -------------------------------------------------
    # 1) Preluăm datele din coordinator
    # -------------------------------------------------
    locuri_consum = coordinator.data.get("locuri_consum", {}).get("data", {}).get("locuriConsum", [])
    facturi = coordinator.data.get("facturi", {}).get("data", {}).get("bills", [])
    citiri_ee = coordinator.data.get("citiri_ee", [])
    citiri_gn = coordinator.data.get("citiri_gn", [])

    # -------------------------------------------------
    # 2) Pregătim dict-uri: {id_punct_consum -> set(ani)}
    # -------------------------------------------------
    facturi_ee_years = {}
    facturi_gn_years = {}
    index_ee_years = {}
    index_gn_years = {}

    # a) Facturi: extragem anul din "DataEmitere"
    for bill in facturi:
        pc = bill.get("IdEntitate")
        tip = bill.get("PrescurtareTipContract")  # "EE" / "GN"
        data_emitere_str = bill.get("DataEmitere")
        if not (pc and tip and data_emitere_str):
            continue
        try:
            dt = datetime.strptime(data_emitere_str, "%Y-%m-%d")
            y = dt.year
        except ValueError:
            continue

        if tip == "EE":
            facturi_ee_years.setdefault(pc, set()).add(y)
        elif tip == "GN":
            facturi_gn_years.setdefault(pc, set()).add(y)

    # b) Index EE: extragem anul din "PentruLuna"
    for cit in citiri_ee:
        pc = cit.get("IdPunctConsum")
        luna_str = cit.get("PentruLuna")
        if not (pc and luna_str):
            continue
        found_year = _extract_year_from_luna(luna_str)
        if found_year:
            index_ee_years.setdefault(pc, set()).add(found_year)

    # c) Index GN: la fel
    for cit in citiri_gn:
        pc = cit.get("IdPunctConsum")
        luna_str = cit.get("PentruLuna")
        if not (pc and luna_str):
            continue
        found_year = _extract_year_from_luna(luna_str)
        if found_year:
            index_gn_years.setdefault(pc, set()).add(found_year)

    # -------------------------------------------------
    # FILTRU DE ANI (ex. ultimii 1 an + anul curent)
    # -------------------------------------------------
    current_year = datetime.now().year
    min_year = current_year - 1  # de ex. 2 ani in urma
    max_year = current_year      # pana la anul curent
    # Ajustez min_year / max_year cum doresc

    # -------------------------------------------------
    # 3) Creăm senzori an (EE/GN) pentru fiecare punct consum
    # -------------------------------------------------
    for pc_data in locuri_consum:
        id_punct_consum = pc_data.get("IdPunctConsum")
        adresa_consum = pc_data.get("Adresa", "Adresa necunoscută").strip()

        are_ee = (pc_data.get("AreEE") == "1") and (pc_data.get("AreContractEE") == "1")
        are_gn = (pc_data.get("AreGN") == "1") and (pc_data.get("AreContractGN") == "1")

        # FACTURI EE by year, filtrate
        if are_ee:
            yrs_ee = facturi_ee_years.get(id_punct_consum, set())
            # Limităm la [min_year, max_year]
            yrs_ee = {y for y in yrs_ee if min_year <= y <= max_year}
            for y in sorted(yrs_ee):
                sensors.append(
                    ArhivaFacturiEESensorYear(coordinator, entry, id_punct_consum, adresa_consum, y)
                )

            # INDEX EE by year
            idx_ee = index_ee_years.get(id_punct_consum, set())
            idx_ee = {y for y in idx_ee if min_year <= y <= max_year}
            for y in sorted(idx_ee):
                sensors.append(
                    ArhivaIndexEESensorYear(coordinator, entry, id_punct_consum, adresa_consum, y)
                )

        # FACTURI GN by year
        if are_gn:
            yrs_gn = facturi_gn_years.get(id_punct_consum, set())
            yrs_gn = {y for y in yrs_gn if min_year <= y <= max_year}
            for y in sorted(yrs_gn):
                sensors.append(
                    ArhivaFacturaGNSensorYear(coordinator, entry, id_punct_consum, adresa_consum, y)
                )

            # INDEX GN by year
            idx_gn = index_gn_years.get(id_punct_consum, set())
            idx_gn = {y for y in idx_gn if min_year <= y <= max_year}
            for y in sorted(idx_gn):
                sensors.append(
                    ArhivaIndexGNSensorYear(coordinator, entry, id_punct_consum, adresa_consum, y)
                )

    # -------------------------------------------------
    # 4) Adăugăm entitățile
    # -------------------------------------------------
    async_add_entities(sensors, update_before_add=True)


def _extract_year_from_luna(text: str) -> int | None:
    """
    Caută 4 cifre la final: "Decembrie 2024" -> 2024.
    """
    text = text.strip()
    match = re.search(r'(\d{4})$', text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


# ------------------------------------------------------------------------
# Baza: BaseNovaPGSensor
# ------------------------------------------------------------------------
class BaseNovaPGSensor(CoordinatorEntity, SensorEntity):
    """
    Bază pentru senzorii Nova Power & Gas, moștenește CoordinatorEntity și SensorEntity.
    """

    def __init__(
        self,
        coordinator: NovaPGDataCoordinator,
        config_entry: ConfigEntry,
        name: str,
        unique_id: str,
        icon: str | None = None,
    ):
        """
        Inițializează senzorul de bază cu atribute definibile.
        """
        super().__init__(coordinator)
        self.config_entry = config_entry

        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_icon = icon

        # Atribute suplimentare (fără raw_data)
        self._attr_extra_state_attributes = {}

        LOGGER.debug(
            "Inițializare BaseNovaPGSensor: name=%s, unique_id=%s",
            self._attr_name,
            self._attr_unique_id
        )

    @property
    def device_info(self):
        """
        Toate entitățile cu același 'identifiers' vor fi grupate sub același "device".
        """
        return {
            "identifiers": {(DOMAIN, f"{self.config_entry.entry_id}_{self._id_punct_consum}")},
            "name": "Nova Power & Gas",
            "manufacturer": "Nova Power & Gas",
            "model": "Furnizor energie electrică și gaze naturale",
            "entry_type": DeviceEntryType.SERVICE,
        }

    async def async_update(self):
        """Forțează actualizarea datelor prin coordinator."""
        await self.coordinator.async_request_refresh()




# ------------------------------------------------------------------------
# DateContractEESensor / AreContractEE
# ------------------------------------------------------------------------
class DateContractEESensor(BaseNovaPGSensor):
    """
    Senzor care afișează datele locurilor de consum care au contract de gaze naturale (AreContractEE=1).
    """
    def __init__(self, coordinator: NovaPGDataCoordinator, entry: ConfigEntry, id_punct_consum: str):
        name = "Date contract"
        unique_id = f"{entry.entry_id}_datecontract_electricitate_{id_punct_consum}"
        icon = "mdi:file-document"
        super().__init__(coordinator, entry, name, unique_id, icon)
        self._attr_entity_id = f"sensor.{DOMAIN}_datecontract_electricitate_{id_punct_consum}"
        self._id_punct_consum = id_punct_consum

    @property
    def entity_id(self):
        return self._attr_entity_id

    @entity_id.setter
    def entity_id(self, value):
        self._attr_entity_id = value

    @property
    def native_value(self):
        """
        Afișează numărul locurilor de consum care au contract de energie electrică (AreContractEE=1).
        """
        data = self.coordinator.data.get("locuri_consum")
        if not data:
            return "N/A"
        locuri = data.get("data", {}).get("locuriConsum", [])

        # Filtrare: AreContractEE=1
        doar_cu_contract_ee = [pc for pc in locuri if pc.get("AreContractEE") == "1"]

        return str(len(doar_cu_contract_ee))

    @property
    def extra_state_attributes(self):
        """
        Returnăm atribute suplimentare pentru locurile de consum cu contract de gaze naturale.
        """
        data = self.coordinator.data.get("locuri_consum", {})
        locuri = data.get("data", {}).get("locuriConsum", [])

        doar_cu_contract_gn = [pc for pc in locuri if pc.get("AreContractEE") == "1"]

        atribute = {}
        for idx, pc in enumerate(doar_cu_contract_gn, start=1):
            # NumePunctConsum specific pentru fiecare loc de consum
            atribute[f"Numele și prenumele"] = pc.get("NumePartener").title()
            atribute[f"Adresă de consum"] = pc.get("NumePunctConsum")
            atribute[f"Cod loc de consum (NLC)"] = pc.get("CodPOD")
            atribute[f"Operator de distribuție (OD)"] = pc.get("CodDistribuitorGN")
            atribute[f"Tip client"] = pc.get("DenumireTipConsumator")

        return {
            "attribution": ATTRIBUTION,
            **atribute,
        }





# ------------------------------------------------------------------------
# DateContractGNSensor / AreContractGN
# ------------------------------------------------------------------------
class DateContractGNSensor(BaseNovaPGSensor):
    """
    Senzor care afișează datele locurilor de consum care au contract de gaze naturale (AreContractGN=1).
    """
    def __init__(self, coordinator: NovaPGDataCoordinator, entry: ConfigEntry, id_punct_consum: str):
        name = "Date contract"
        unique_id = f"{entry.entry_id}_datecontract_gaz_{id_punct_consum}"
        icon = "mdi:file-document"
        super().__init__(coordinator, entry, name, unique_id, icon)
        self._attr_entity_id = f"sensor.{DOMAIN}_date_contract_gaz_{id_punct_consum}"
        self._id_punct_consum = id_punct_consum


    @property
    def entity_id(self):
        return self._attr_entity_id

    @entity_id.setter
    def entity_id(self, value):
        self._attr_entity_id = value

    @property
    def native_value(self):
        """
        Afișează numărul locurilor de consum care au contract de gaze naturale (AreContractGN=1).
        """
        data = self.coordinator.data.get("locuri_consum")
        if not data:
            return "N/A"
        locuri = data.get("data", {}).get("locuriConsum", [])

        # Filtrare: AreContractGN=1
        doar_cu_contract_gn = [pc for pc in locuri if pc.get("AreContractGN") == "1"]

        return str(len(doar_cu_contract_gn))

    @property
    def extra_state_attributes(self):
        """
        Returnăm atribute suplimentare pentru locurile de consum cu contract de gaze naturale.
        """
        data = self.coordinator.data.get("locuri_consum", {})
        locuri = data.get("data", {}).get("locuriConsum", [])

        doar_cu_contract_gn = [pc for pc in locuri if pc.get("AreContractGN") == "1"]

        atribute = {}
        for idx, pc in enumerate(doar_cu_contract_gn, start=1):
            # NumePunctConsum specific pentru fiecare loc de consum
            atribute[f"Numele și prenumele"] = pc.get("NumePartener").title()
            atribute[f"Adresă de consum"] = pc.get("NumePunctConsum")
            atribute[f"Cod loc de consum (NLC)"] = pc.get("CodPOD")
            atribute[f"Operator de distribuție (OD)"] = pc.get("CodDistribuitorGN")
            atribute[f"Tip client"] = pc.get("DenumireTipConsumator")

        return {
            "attribution": ATTRIBUTION,
            **atribute,
        }



# =============================================================================
#  FACTURI EE PE UN AN (Year)
# =============================================================================
class ArhivaFacturiEESensorYear(BaseNovaPGSensor):
    """
    Senzor care afișează facturile EE (energie electrică) pentru un anumit IdPunctConsum,
    dar DOAR pentru un AN specific.
    
    Aceleași atribute ca ArhivaPlatiEESensor, dar filtrarea + naming + unique_id conțin year.
    """
    def __init__(self, coordinator: NovaPGDataCoordinator, entry: ConfigEntry, id_punct_consum: str, adresa: str, year: int):
        # Observă cum adăugăm year în unique_id, entity_id, name
        name = f"Arhivă facturi - {year}"
        unique_id = f"{entry.entry_id}_arhiva_facturi_electricitate_{id_punct_consum}_{year}"
        icon = "mdi:file-document"

        super().__init__(coordinator, entry, name, unique_id, icon)

        self._attr_entity_id = f"sensor.{DOMAIN}_arhiva_facturi_electricitate_{id_punct_consum}_{year}"
        self._id_punct_consum = id_punct_consum
        self._adresa = adresa
        self._year = year

    @property
    def entity_id(self):
        return self._attr_entity_id

    @entity_id.setter
    def entity_id(self, value):
        self._attr_entity_id = value

    @property
    def native_value(self):
        """
        Afișează numărul facturilor EE pentru id_punct_consum și doar pentru anul self._year.
        """
        facturi_data = self.coordinator.data.get("facturi", {})
        all_bills = facturi_data.get("data", {}).get("bills", [])

        count = 0
        for bill in all_bills:
            if bill.get("PrescurtareTipContract") != "EE":
                continue
            if bill.get("IdEntitate") != self._id_punct_consum:
                continue

            # Procesăm `PentruLuna`
            luna_str = bill.get("PentruLuna")
            luna_str = luna_str.lower() if luna_str else None  # Convertim în litere mici
            an = _extract_year_from_luna(luna_str) if luna_str else None
            if an == self._year:
                count += 1

        return f"{count}"

    @property
    def extra_state_attributes(self):
        """Atribute suplimentare pentru senzor."""
        facturi_data = self.coordinator.data.get("facturi", {})
        all_bills = facturi_data.get("data", {}).get("bills", [])

        atribute = {}

        # Filtrăm datele relevante pe baza logicii din `native_value`
        for idx, bill in enumerate(all_bills):
            if bill.get("PrescurtareTipContract") != "EE":
                continue
            if bill.get("IdEntitate") != self._id_punct_consum:
                continue

            # Procesăm `PentruLuna`
            luna_str = bill.get("PentruLuna")
            luna_str = luna_str.lower() if luna_str else None  # Convertim în litere mici
            an = _extract_year_from_luna(luna_str) if luna_str else None
            if an != self._year:
                continue

            # Adăugăm informațiile relevante pentru fiecare factură validă
            valoare_cu_tva = bill.get("ValoareCuTVA", "0")
            atribute[f"Factură luna {luna_str}"] = f"{float(valoare_cu_tva):.2f} lei"

        # Returnăm atributele generale și cele specifice facturilor
        return {
            "attribution": ATTRIBUTION,
            **atribute,  # Adăugăm informațiile filtrate
            "--------": "",
            "Arhiva facturilor pentru electricitate": "",
        }



# =============================================================================
#  FACTURI GN PE UN AN (Year)
# =============================================================================
class ArhivaFacturaGNSensorYear(BaseNovaPGSensor):
    """
    Senzor care afișează facturile GN (gaz natural) pentru un anumit IdPunctConsum,
    dar DOAR pentru un AN specific.
    """
    def __init__(self, coordinator: NovaPGDataCoordinator, entry: ConfigEntry, id_punct_consum: str, adresa: str, year: int):
        name = f"Arhivă facturi - {year}"
        unique_id = f"{entry.entry_id}_arhiva_facturi_gaz_{id_punct_consum}_{year}"
        icon = "mdi:file-document"

        super().__init__(coordinator, entry, name, unique_id, icon)
        self._attr_entity_id = f"sensor.{DOMAIN}_arhiva_facturi_gaz_{id_punct_consum}_{year}"
        self._id_punct_consum = id_punct_consum
        self._adresa = adresa
        self._year = year

    @property
    def entity_id(self):
        return self._attr_entity_id

    @entity_id.setter
    def entity_id(self, value):
        self._attr_entity_id = value

    @property
    def native_value(self):
        """Returnează numărul de facturi GN pentru anul specificat."""
        facturi_data = self.coordinator.data.get("facturi", {})
        all_bills = facturi_data.get("data", {}).get("bills", [])

        count = 0
        for bill in all_bills:
            if bill.get("PrescurtareTipContract") != "GN":
                continue
            if bill.get("IdEntitate") != self._id_punct_consum:
                continue

            # Procesăm `PentruLuna`
            luna_str = bill.get("PentruLuna")
            luna_str = luna_str.lower() if luna_str else None  # Convertim în litere mici
            an = _extract_year_from_luna(luna_str) if luna_str else None
            if an == self._year:
                count += 1

        return f"{count}"

    @property
    def extra_state_attributes(self):
        """Atribute suplimentare pentru senzor."""
        facturi_data = self.coordinator.data.get("facturi", {})
        all_bills = facturi_data.get("data", {}).get("bills", [])

        atribute = {}

        # Filtrăm datele relevante pe baza logicii din `native_value`
        for idx, bill in enumerate(all_bills):
            if bill.get("PrescurtareTipContract") != "GN":
                continue
            if bill.get("IdEntitate") != self._id_punct_consum:
                continue

            # Procesăm `PentruLuna`
            luna_str = bill.get("PentruLuna")
            luna_str = luna_str.lower() if luna_str else None  # Convertim în litere mici
            an = _extract_year_from_luna(luna_str) if luna_str else None
            if an != self._year:
                continue

            # Adăugăm informațiile relevante pentru fiecare factură validă
            valoare_cu_tva = bill.get("ValoareCuTVA", "0")
            atribute[f"Factură luna {luna_str}"] = f"{float(valoare_cu_tva):.2f} lei"

        # Returnăm atributele generale și cele specifice facturilor
        return {
            "attribution": ATTRIBUTION,
            **atribute,  # Adăugăm informațiile filtrate
            "--------": "",
            "Arhiva facturilor pentru gaze naturale": "",
        }




# =============================================================================
#  INDEX EE PE UN AN (din PentruLuna)
# =============================================================================
class ArhivaIndexEESensorYear(BaseNovaPGSensor):
    """
    Senzor pentru indexări EE (energie electrică) pentru un anumit IdPunctConsum,
    DOAR pentru un AN (ex. 2024) extras din "PentruLuna".
    """
    def __init__(self, coordinator: NovaPGDataCoordinator, entry: ConfigEntry, id_punct_consum: str, adresa: str, year: int):
        name = f"Arhivă index - {year}"
        unique_id = f"{entry.entry_id}_arhiva_index_electricitate_{id_punct_consum}_{year}"
        icon = "mdi:counter"
        super().__init__(coordinator, entry, name, unique_id, icon)

        self._attr_entity_id = f"sensor.{DOMAIN}_arhiva_index_electricitate_{id_punct_consum}_{year}"
        self._id_punct_consum = id_punct_consum
        self._adresa = adresa
        self._year = year

    @property
    def entity_id(self):
        return self._attr_entity_id

    @entity_id.setter
    def entity_id(self, value):
        self._attr_entity_id = value

    @property
    def native_value(self):
        """
        Returnează numărul de citiri cu DataInceputAutocitire=null și DataFinalAutocitire=null
        și PentruLuna având anul == self._year.
        """
        citiri_ee = self.coordinator.data.get("citiri_ee", [])
        count = 0
        for c in citiri_ee:
            if c.get("IdPunctConsum") != self._id_punct_consum:
                continue
            if c.get("DataInceputAutocitire") is not None or c.get("DataFinalAutocitire") is not None:
                continue

            luna_str = c.get("PentruLuna")
            an = _extract_year_from_luna(luna_str) if luna_str else None
            if an == self._year:
                count += 1

        return f"{count}"

    @property
    def extra_state_attributes(self):
        """Atribute suplimentare pentru senzor."""
        citiri_ee = self.coordinator.data.get("citiri_ee", [])
        atribute = {}

        # Filtrăm datele pe baza logicii din `native_value`
        for idx, c in enumerate(citiri_ee):
            if c.get("IdPunctConsum") != self._id_punct_consum:
                continue
            if c.get("DataInceputAutocitire") is not None or c.get("DataFinalAutocitire") is not None:
                continue

            luna_str = c.get("PentruLuna")
            luna_str = luna_str.lower() if luna_str else None  # Convertim în litere mici
            an = _extract_year_from_luna(luna_str) if luna_str else None
            if an != self._year:
                continue

            # Adăugăm informațiile relevante pentru fiecare citire validă
            atribute[f"Index pentru luna {luna_str}"] = int(float(c.get("TotalVolum", 0)))

        # Returnăm atributele generale și cele specifice citirilor
        return {
            "attribution": ATTRIBUTION,
            **atribute,  # Adăugăm datele din citirile filtrate
            "--------": "",
            "Arhiva de indexuri pentru energie electrică": "",
        }




# =============================================================================
#  INDEX GN PE UN AN (din PentruLuna)
# =============================================================================
class ArhivaIndexGNSensorYear(BaseNovaPGSensor):
    """
    Senzor pentru indexări GN (gaz natural) pentru un anumit IdPunctConsum,
    DOAR pentru un AN (ex. 2025) extras din "PentruLuna".
    """
    def __init__(self, coordinator: NovaPGDataCoordinator, entry: ConfigEntry, id_punct_consum: str, adresa: str, year: int):
        name = f"Arhivă index - {year}"
        unique_id = f"{entry.entry_id}_arhiva_index_gaz_{id_punct_consum}_{year}"
        icon = "mdi:counter"
        super().__init__(coordinator, entry, name, unique_id, icon)

        self._attr_entity_id = f"sensor.{DOMAIN}_arhiva_index_gaz_{id_punct_consum}_{year}"
        self._id_punct_consum = id_punct_consum
        self._adresa = adresa
        self._year = year

    @property
    def entity_id(self):
        return self._attr_entity_id

    @entity_id.setter
    def entity_id(self, value):
        self._attr_entity_id = value

    @property
    def native_value(self):
        citiri_gn = self.coordinator.data.get("citiri_gn", [])
        count = 0
        for c in citiri_gn:
            if c.get("IdPunctConsum") != self._id_punct_consum:
                continue
            if c.get("DataInceputAutocitire") is not None or c.get("DataFinalAutocitire") is not None:
                continue

            luna_str = c.get("PentruLuna")
            an = _extract_year_from_luna(luna_str) if luna_str else None
            if an == self._year:
                count += 1

        return f"{count}"

    @property
    def extra_state_attributes(self):
        """Atribute suplimentare pentru senzor."""
        citiri_gn = self.coordinator.data.get("citiri_gn", [])
        atribute = {}

        # Filtrăm datele pe baza logicii din `native_value`
        for idx, c in enumerate(citiri_gn):
            if c.get("IdPunctConsum") != self._id_punct_consum:
                continue
            if c.get("DataInceputAutocitire") is not None or c.get("DataFinalAutocitire") is not None:
                continue

            luna_str = c.get("PentruLuna")
            luna_str = luna_str.lower() if luna_str else None  # Convertim în litere mici
            an = _extract_year_from_luna(luna_str) if luna_str else None
            if an != self._year:
                continue

            # Adăugăm informațiile relevante pentru fiecare citire validă
            atribute[f"Index pentru luna {luna_str}"] = int(float(c.get("TotalVolum", 0)))

        # Returnăm atributele generale și cele specifice citirilor
        return {
            "attribution": ATTRIBUTION,
            **atribute,  # Adăugăm datele din citirile filtrate
            "--------": "",
            "Arhiva de indexuri pentru gaze naturale": "",
        }
