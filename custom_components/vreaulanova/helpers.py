"""Funcții și constante utilitare pentru integrarea Nova Power & Gas."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Any

from homeassistant.helpers.selector import SelectOptionDict
from homeassistant.util import dt as dt_util

from .const import DOMAIN


# ══════════════════════════════════════════════
# Mapping-uri luni și tipuri citire
# ══════════════════════════════════════════════

MONTHS_EN_RO: dict[str, str] = {
    "January": "ianuarie",
    "February": "februarie",
    "March": "martie",
    "April": "aprilie",
    "May": "mai",
    "June": "iunie",
    "July": "iulie",
    "August": "august",
    "September": "septembrie",
    "October": "octombrie",
    "November": "noiembrie",
    "December": "decembrie",
}

MONTHS_NUM_RO: dict[int, str] = {
    1: "ianuarie",
    2: "februarie",
    3: "martie",
    4: "aprilie",
    5: "mai",
    6: "iunie",
    7: "iulie",
    8: "august",
    9: "septembrie",
    10: "octombrie",
    11: "noiembrie",
    12: "decembrie",
}

READING_TYPE_MAP: dict[str, str] = {
    "01": "Citire distribuitor",
    "02": "Autocitire",
    "03": "Estimare",
}

# ══════════════════════════════════════════════
# Mapping-uri orașe
# ══════════════════════════════════════════════
COUNTY_CODE_MAP: dict[str, str] = {
    "AB": "Alba",
    "AR": "Arad",
    "AG": "Argeș",
    "BC": "Bacău",
    "BH": "Bihor",
    "BN": "Bistrița-Năsăud",
    "BT": "Botoșani",
    "BR": "Brăila",
    "BV": "Brașov",
    "B": "București",
    "BZ": "Buzău",
    "CS": "Caraș-Severin",
    "CL": "Călărași",
    "CJ": "Cluj",
    "CT": "Constanța",
    "CV": "Covasna",
    "DB": "Dâmbovița",
    "DJ": "Dolj",
    "GL": "Galați",
    "GR": "Giurgiu",
    "GJ": "Gorj",
    "HR": "Harghita",
    "HD": "Hunedoara",
    "IL": "Ialomița",
    "IS": "Iași",
    "IF": "Ilfov",
    "MM": "Maramureș",
    "MH": "Mehedinți",
    "MS": "Mureș",
    "NT": "Neamț",
    "OT": "Olt",
    "PH": "Prahova",
    "SM": "Satu Mare",
    "SJ": "Sălaj",
    "SB": "Sibiu",
    "SV": "Suceava",
    "TR": "Teleorman",
    "TM": "Timiș",
    "TL": "Tulcea",
    "VS": "Vaslui",
    "VL": "Vâlcea",
    "VN": "Vrancea",
}

# ══════════════════════════════════════════════
# Mapping-uri utilități și unități de măsură
# ══════════════════════════════════════════════

UTILITY_TYPE_LABEL: dict[str, str] = {
    "electric": "Energie electrică",
    "gas": "Gaze naturale",
}

UTILITY_TYPE_SENSOR_LABEL: dict[str, tuple[str, str, str, str]] = {
    "electric": ("Energie electrică", "Index energie electrică", "mdi:lightning-bolt", "index_energie_electrica"),
    "gas": ("Gaze naturale", "Index gaze naturale", "mdi:gauge", "index_gaze_naturale"),
}

PORTFOLIO_LABEL: dict[str, str] = {
    "GN": "Gaze naturale",
    "EE": "Energie electrică",
}

UNIT_NORMALIZE: dict[str, str] = {
    "MC": "m³",
    "M3": "m³",
    "m3": "m³",
    "KWH": "kWh",
    "kwh": "kWh",
    "MWH": "MWh",
    "mwh": "MWh",
}

CONVENTION_MONTH_MAPPING: dict[str, str] = {
    "valueMonth1": "ianuarie", "valueMonth2": "februarie", "valueMonth3": "martie",
    "valueMonth4": "aprilie", "valueMonth5": "mai", "valueMonth6": "iunie",
    "valueMonth7": "iulie", "valueMonth8": "august", "valueMonth9": "septembrie",
    "valueMonth10": "octombrie", "valueMonth11": "noiembrie", "valueMonth12": "decembrie",
}


# ══════════════════════════════════════════════
# Mapping-uri traducere atribute API → română
# ══════════════════════════════════════════════

INVOICE_BALANCE_KEY_MAP: dict[str, str] = {
    "balance": "Sold",
    "total": "Total",
    "totalBalance": "Sold total",
    "invoiceValue": "Valoare factură",
    "issuedValue": "Valoare emisă",
    "balanceValue": "Sold rămas",
    "paidValue": "Sumă achitată",
    "maturityDate": "Data scadenței",
    "invoiceNumber": "Număr factură",
    "emissionDate": "Data emiterii",
    "paymentDate": "Data plății",
    "currency": "Monedă",
    "status": "Stare",
    "type": "Tip",
    "accountContract": "Cod încasare",
    "refund": "Rambursare disponibilă",
    "date": "Data sold",
    "refundInProcess": "Rambursare în curs",
    "hasGuarantee": "Garanție activă",
    "hasUnpaidGuarantee": "Garanție neachitată",
    "balancePay": "Sold de plată",
    "refundDocumentsRequired": "Documente rambursare necesare",
    "isAssociation": "Asociație",
}

INVOICE_BALANCE_MONEY_KEYS: set[str] = {
    "balance",
    "total",
    "totalBalance",
    "invoiceValue",
    "issuedValue",
    "balanceValue",
    "paidValue",
}


# ══════════════════════════════════════════════
# Funcții de formatare
# ══════════════════════════════════════════════

def format_ron(value: float) -> str:
    """Formatează o valoare numerică în format românesc (1.234,56)."""
    formatted = f"{value:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_number_ro(value: float | int | str) -> str:
    """Formatează un număr cu separatorul zecimal românesc (virgulă).

    Exemple:
        4.029   → '4,029'
        124.91  → '124,91'
        11.9    → '11,9'
        0.424   → '0,424'
        100     → '100'
        100.0   → '100'
    """
    try:
        num = float(value)
    except (ValueError, TypeError):
        return str(value)
    if num == int(num):
        return str(int(num))
    text = str(num)
    return text.replace(".", ",")


def format_invoice_due_message(display_value: float, raw_date: str, date_format: str = "%d.%m.%Y") -> str:
    """Formatează mesajul de scadență pentru o factură.

    Returnează un mesaj de tip:
    - „Restanță de X lei, termen depășit cu N zile"
    - „De achitat astăzi: X lei"
    - „Sumă de X lei scadentă pe luna LUNA (N zile)"

    Ridică ValueError dacă data nu poate fi parsată.
    """
    parsed_date = datetime.strptime(raw_date, date_format)
    month_name_en = parsed_date.strftime("%B")
    month_name_ro = MONTHS_EN_RO.get(month_name_en, "necunoscut")
    days_until_due = (parsed_date.date() - dt_util.now().date()).days

    if days_until_due < 0:
        day_unit = "zi" if abs(days_until_due) == 1 else "zile"
        return f"Restanță de {format_ron(display_value)} lei, termen depășit cu {abs(days_until_due)} {day_unit}"
    if days_until_due == 0:
        return f"De achitat astăzi, {dt_util.now().strftime('%d.%m.%Y')}: {format_ron(display_value)} lei"
    day_unit = "zi" if days_until_due == 1 else "zile"
    return f"Sumă de {format_ron(display_value)} lei scadentă pe luna {month_name_ro} ({days_until_due} {day_unit})"


# ══════════════════════════════════════════════
# Funcții de autentificare
# ══════════════════════════════════════════════

def mask_email(email: str) -> str:
    """Mascarea adresei de email: a*****b@gmail.com.

    Păstrează primul și ultimul caracter din local part,
    înlocuiește restul cu asteriscuri. Domeniul rămâne vizibil.
    Dacă local part are 1-2 caractere, mascarea e minimală.
    """
    if not email or "@" not in email:
        return email or "—"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        masked = local
    elif len(local) == 2:
        masked = f"{local[0]}*"
    else:
        masked = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    return f"{masked}@{domain}"


def generate_verify_hmac(username: str, secret: str) -> str:
    """Generează semnătura HMAC-MD5 pentru câmpul verify din mobile-login.

    Nova nu utilizează verificarea HMAC, deci se returnează șirul gol.
    """
    return ""


# ══════════════════════════════════════════════
# Funcții pentru config flow (selecție contracte)
# ══════════════════════════════════════════════

def build_address_consum(address_obj: dict) -> str:
    """Construiește adresa completă formatată corect pentru România."""
    if not isinstance(address_obj, dict):
        return ""

    def safe_str(value: Any) -> str:
        return str(value).strip() if value else ""

    def clean_parentheses(text: str) -> str:
        """Elimină orice conținut de tip '(XX)' din text."""
        if "(" in text:
            text = text.split("(")[0]
        return " ".join(text.split())

    parts: list[str] = []

    # ─────────────────────────────
    # Stradă
    # ─────────────────────────────
    street_obj = address_obj.get("street")
    if isinstance(street_obj, dict):

        street_type = safe_str(
            (street_obj.get("streetType") or {}).get("label")
        )
        street_name = safe_str(street_obj.get("streetName"))

        full_street = " ".join(
            filter(None, [street_type, street_name])
        ).strip()

        if full_street:
            # Title doar pe stradă, nu pe tot textul
            full_street = " ".join(word.capitalize() for word in full_street.split())

            nr = safe_str(address_obj.get("streetNumber"))
            if nr:
                parts.append(f"{full_street} {nr}")
            else:
                parts.append(full_street)

    # Apartament
    apartment = safe_str(address_obj.get("apartment"))
    if apartment and apartment != "0":
        parts.append(f"ap. {apartment}")

    # ─────────────────────────────
    # Localitate + județ
    # ─────────────────────────────
    locality_obj = address_obj.get("locality")
    if isinstance(locality_obj, dict):

        raw_city = clean_parentheses(
            safe_str(locality_obj.get("localityName"))
        )

        city = raw_city.strip()

        county_code = safe_str(locality_obj.get("countyCode")).upper()
        county_name = COUNTY_CODE_MAP.get(county_code)

        if city:
            if county_name:
                parts.append(f"{city}, jud. {county_name}")
            else:
                parts.append(city)

    return ", ".join(parts)

def build_contract_options(metering_points: list[dict]) -> list[SelectOptionDict]:
    """Construiește lista de opțiuni pentru selectorul de locuri de consum.

    Nova: cheia primară este specificIdForUtilityType (CLC/POD) din metering-points,
    NU contractId din /contracts (care nu se potrivește între endpoint-uri).

    Args:
        metering_points: Lista de metering-point docs din /metering-points API.
    """
    options: list[SelectOptionDict] = []
    seen: set[str] = set()

    def safe_str(value: Any) -> str:
        return str(value).strip() if value else ""

    for mp in metering_points or []:
        if not isinstance(mp, dict):
            continue

        # CLC/POD este cheia primară
        clc_pod = safe_str(mp.get("specificIdForUtilityType"))
        if not clc_pod or clc_pod in seen:
            continue

        seen.add(clc_pod)

        # Adresa — direct din metering-point
        address = safe_str(mp.get("address")) or "Fără adresă"

        # Tip utilitate
        utility = safe_str(mp.get("utilityType"))
        utility_label = {
            "electricity": "Energie electrică",
            "electric": "Energie electrică",
            "gas": "Gaze naturale",
        }.get(utility, utility)

        # Număr punct de măsurare
        mp_number = safe_str(mp.get("number"))

        # Label final: adresă + CLC/POD + tip utilitate
        label = f"{address}"
        if utility_label:
            label += f" ({utility_label})"
        label += f" — {clc_pod}"

        options.append(
            SelectOptionDict(
                value=clc_pod,
                label=label,
            )
        )

    options.sort(key=lambda x: x["label"].lower())

    return options


def extract_all_contracts(metering_points: list[dict]) -> list[str]:
    """Extrage toate CLC/POD-urile unice din metering-points.

    Nova: cheia primară este specificIdForUtilityType (CLC/POD).
    """
    result: list[str] = []
    for mp in metering_points:
        if isinstance(mp, dict):
            clc_pod = (mp.get("specificIdForUtilityType") or "").strip()
            if clc_pod and clc_pod not in result:
                result.append(clc_pod)
    return result


def build_contract_metadata(
    metering_points: list[dict],
    contracts: list[dict] | None = None,
    crm_account_number: str = "",
    crm_map: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Construiește un dict cu metadatele relevante per loc de consum (CLC/POD).

    Nova: cheia primară este specificIdForUtilityType (CLC/POD) din metering-points.
    Contractele se asociază prin utilityType (best-effort match).

    Returnează: {CLC_POD: {
        "utility_type": "electricity"|"gas",
        "is_collective": bool,
        "metering_point_number": str,  # number din metering-point
        "meter_series": [str, ...],    # seria fiecărui contor
        "contract_id": str|None,       # contractId din /contracts (via utilityType match)
        "contract_number": str|None,   # number din /contracts
        "address": str,
        "crm_account_number": str,     # CRM-ul sub care e acest metering-point
    }}
    """
    metadata: dict[str, dict] = {}

    # Construiește index contracte pe utilityType (pentru matching)
    contracts_by_utility: dict[str, list[dict]] = {}
    for c in contracts or []:
        if not isinstance(c, dict):
            continue
        ut = (c.get("utilityType") or "").strip()
        if ut:
            contracts_by_utility.setdefault(ut, []).append(c)

    for mp in metering_points or []:
        if not isinstance(mp, dict):
            continue
        clc_pod = (mp.get("specificIdForUtilityType") or "").strip()
        if not clc_pod:
            continue

        utility_type = (mp.get("utilityType") or "").strip()
        is_collective = (
            mp.get("contractType", "").lower() == "collective"
            or mp.get("isCollectiveContract") is True
        )

        # Extrage meter_series din meters[]
        meter_series = []
        for meter in mp.get("meters", []):
            if isinstance(meter, dict):
                series = (meter.get("series") or "").strip()
                if series:
                    meter_series.append(series)

        # Match contract via utilityType (best-effort)
        matched_contract_id = None
        matched_contract_number = None
        matching_contracts = contracts_by_utility.get(utility_type, [])
        if len(matching_contracts) == 1:
            matched_contract_id = matching_contracts[0].get("contractId")
            matched_contract_number = matching_contracts[0].get("number")
        elif len(matching_contracts) > 1:
            # Ambiguu — nu putem determina, luăm primul
            matched_contract_id = matching_contracts[0].get("contractId")
            matched_contract_number = matching_contracts[0].get("number")

        metadata[clc_pod] = {
            "utility_type": utility_type,
            "is_collective": is_collective,
            "metering_point_number": (mp.get("number") or "").strip(),
            "meter_series": meter_series,
            "contract_id": matched_contract_id,
            "contract_number": matched_contract_number,
            "address": (mp.get("address") or "").strip(),
            "crm_account_number": (crm_map or {}).get(clc_pod, crm_account_number),
        }

    return metadata


def resolve_selection(
    select_all: bool,
    selected: list[str],
    metering_points: list[dict],
) -> list[str]:
    """Returnează lista finală de locuri de consum selectate (CLC/POD)."""
    if select_all:
        return extract_all_contracts(metering_points)
    return selected


# ══════════════════════════════════════════════
# Constante și helperi pentru butoane (trimitere index)
# ══════════════════════════════════════════════

# Mapare utility_type → configurație buton
# utility_type "gas" = Gaz, "electric" = Electricitate
UTILITY_BUTTON_CONFIG: dict[str, dict[str, str]] = {
    "gas": {
        "suffix": "trimite_index_gaz",
        "label": "Trimite index gaz",
        "icon": "mdi:fire",
        "input_number": "input_number.gas_meter_reading",
        "translation_key": "trimite_index_gaz",
    },
    "electric": {
        "suffix": "trimite_index_energie_electrica",
        "label": "Trimite index energie electrică",
        "icon": "mdi:flash",
        "input_number": "input_number.energy_meter_reading",
        "translation_key": "trimite_index_energie_electrica",
    },
}

# Fallback pentru contracte individuale (detectare din unitatea de măsură)
UNIT_TO_UTILITY: dict[str, str] = {
    "m3": "gas",
    "mc": "gas",
    "kwh": "electric",
}


def detect_utility_type_individual(coordinator_data: dict | None) -> str:
    """Detectează utility_type pentru un contract individual din datele coordinator.

    Folosește unitatea de măsură din graphic_consumption (um).
    Returnează "gas" ca fallback.
    """
    if not coordinator_data:
        return "gas"
    um = coordinator_data.get("um", "m3")
    return UNIT_TO_UTILITY.get(um.lower(), "gas")


def get_subcontract_utility_type(
    subcontracts_list: list[dict] | None, sc_code: str
) -> str | None:
    """Extrage utility_type pentru un subcontract din lista de subcontracte.

    Nova folosește 'contractId'.
    """
    if not subcontracts_list or not isinstance(subcontracts_list, list):
        return None
    for s in subcontracts_list:
        if isinstance(s, dict) and s.get("contractId") == sc_code:
            return s.get("utilityType")
    return None


def get_meter_data(coordinator_data: dict | None, contract_id: str, is_subcontract: bool = False) -> dict | None:
    """Obține datele meter_index pentru un contract sau subcontract.

    Args:
        coordinator_data: Dicționarul complet de date din coordinator.
        contract_id: Codul de contract / subcontract.
        is_subcontract: True dacă se caută în subcontracts_meter_index.

    Returns:
        Dicționarul meter_index sau None.
    """
    if not coordinator_data:
        return None
    if is_subcontract:
        smi = coordinator_data.get("subcontracts_meter_index")
        if smi and isinstance(smi, dict):
            return smi.get(contract_id)
        return None
    return coordinator_data.get("meter_index")


def extract_ablbelnr(meter_data: dict | None) -> str | None:
    """Extrage ablbelnr (ID intern contor) din datele meter_index.

    Parcurge devices → indexes și returnează primul ablbelnr găsit.
    """
    if not meter_data or not isinstance(meter_data, dict):
        return None
    devices = meter_data.get("indexDetails", {}).get("devices", [])
    for device in devices:
        indexes = device.get("indexes", [])
        if indexes:
            ablbelnr = indexes[0].get("ablbelnr")
            if ablbelnr:
                return ablbelnr
    return None
