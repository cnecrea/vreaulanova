"""Funcții comune pentru senzorii, butoanele și diagnosticul Nova Power & Gas.

Device-ul și ID-urile unui loc de consum se construiesc DOAR aici, ca senzorii și butoanele
să ajungă sub același device (înainte, sensor.py și button.py aveau fiecare copia lor).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.util import slugify

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MONTHS_RO_LOWER = [
    "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
    "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie",
]


# ══════════════════════════════════════════════
# Locul de consum (metering point)
# ══════════════════════════════════════════════

def utility_short(mp: dict) -> str:
    """Eticheta scurtă a utilității (folosită în ID-uri): gaz / electricitate."""
    ut = mp.get("utilityType", "")
    return {"gas": "gaz", "electricity": "electricitate"}.get(ut, ut)


def utility_label(mp: dict) -> str:
    """Eticheta afișată a utilității: Gaz / Energie Electrică."""
    ut = mp.get("utilityType", "")
    return {"gas": "Gaz", "electricity": "Energie Electrică"}.get(ut, ut)


def id_part(value: Any) -> str:
    """Fragment valid de entity_id: litere mici, cifre și „_" (valorile valide rămân neschimbate)."""
    return re.sub(r"[^a-z0-9_]+", "_", str(value).lower()).strip("_")


def mp_slug(mp: dict) -> str:
    """Slug-ul locului de consum: LC-00202600 → lc00202600 (în entity_id și în identificatorul device-ului)."""
    number = mp.get("number", "") or mp.get("meteringPointId", "")[:12]
    return id_part(number.lower().replace("-", "").replace(" ", ""))


def mp_device(crm: str, mp: dict) -> DeviceInfo:
    """Device-ul unui loc de consum: „Nova Power & Gas (6085537) LC-00202600 Gaz"."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"mp_{crm}_{mp_slug(mp)}")},
        name=f"Nova Power & Gas ({crm}) {mp.get('number', '?')} {utility_label(mp)}",
        manufacturer="Ciprian Nicolae (cnecrea)",
        model="Nova Power & Gas",
        entry_type=DeviceEntryType.SERVICE,
    )


def is_active_mp(mp: dict) -> bool:
    """Loc de consum activ = are cod CLC/POD (specificIdForUtilityType).

    Nova întoarce și locuri fără CLC/POD (vechi sau neactivate): fără contract activ,
    facturi, contor sau autocitiri — pentru ele nu se poate trimite index.
    """
    return bool((mp.get("specificIdForUtilityType") or "").strip())


def remove_inactive_devices(hass: HomeAssistant, entry: ConfigEntry, accounts_data: dict) -> int:
    """Scoate device-urile locurilor fără CLC/POD (și entitățile lor) create de versiunile anterioare.

    Locurile inactive nu mai primesc senzori; fără curățare, device-ul lor ar rămâne în registry cu
    entități orfane („Indisponibil"). Întoarce câte device-uri au fost scoase.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    removed = 0
    for crm, acct in (accounts_data or {}).items():
        for mp in acct.get("inactive_metering_points") or []:
            device = dev_reg.async_get_device(identifiers={(DOMAIN, f"mp_{crm}_{mp_slug(mp)}")})
            if device is None or entry.entry_id not in device.config_entries:
                continue
            entities = [
                e for e in er.async_entries_for_device(ent_reg, device.id, include_disabled_entities=True)
                if e.config_entry_id == entry.entry_id
            ]
            for ent in entities:
                ent_reg.async_remove(ent.entity_id)
            dev_reg.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
            removed += 1
            _LOGGER.info(
                "[VreauLaNova] Locul %s (cont %s) nu are cod CLC/POD la Nova — device-ul și cele %d entități ale lui au fost scoase",
                mp.get("number", "?"), crm, len(entities),
            )
    return removed


def helper_index_entity_id(clc_pod: str, series: str) -> str:
    """ID-ul helperului input_number din care se citește indexul de trimis.

    Normalizat exact ca Home Assistant (slugify) — issue #10: seria cu „/" sau „-".
    """
    return f"input_number.{slugify(f'{DOMAIN}_{clc_pod}_{series}_index')}"


def notification_id(crm: str, mp: dict) -> str:
    """ID-ul notificării persistente a butonului „Trimite index" (una per loc de consum)."""
    return f"{DOMAIN}_index_{id_part(crm)}_{mp_slug(mp)}"


# ══════════════════════════════════════════════
# Unități de măsură
# ══════════════════════════════════════════════

def normalize_unit(raw: Any) -> str | None:
    """Unitatea din API (m³, m3, MC, kwh, KWH, MWh) → „m³" / „kWh" / „MWh"."""
    unit = str(raw or "").strip().lower().replace("³", "3")
    if unit in ("m3", "mc"):
        return "m³"
    if unit == "kwh":
        return "kWh"
    if unit == "mwh":
        return "MWh"
    return None


def ha_unit(mp: dict, raw_unit: Any = None) -> str | None:
    """Unitatea Home Assistant: din unitatea primită, altfel după utilitate (gaz → m³, electricitate → kWh)."""
    unit = normalize_unit(raw_unit) or ("kWh" if mp.get("utilityType") == "electricity" else "m³")
    return {
        "m³": UnitOfVolume.CUBIC_METERS,
        "kWh": UnitOfEnergy.KILO_WATT_HOUR,
        "MWh": UnitOfEnergy.MEGA_WATT_HOUR,
    }.get(unit)


# ══════════════════════════════════════════════
# Date, sume, perioade
# ══════════════════════════════════════════════

def parse_date(value: Any) -> date | None:
    """„dd.mm.yyyy", „yyyy-mm-dd" sau ISO cu oră → date; None dacă nu se poate."""
    text = str(value or "").strip()
    for fmt, size in (("%d.%m.%Y", 10), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    return None


def format_date_ro(value: Any) -> str:
    """Data în română: „4 martie 2026" (sau textul primit, dacă nu e o dată)."""
    if not value:
        return "N/A"
    parsed = parse_date(value)
    if not parsed:
        return str(value)
    return f"{parsed.day} {MONTHS_RO_LOWER[parsed.month - 1]} {parsed.year}"


def format_amount(value: Any) -> str:
    """Suma în format românesc: 2.675,47 lei."""
    try:
        num = float(value)
    except (ValueError, TypeError):
        return "0,00 lei"
    return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " lei"


def format_number(value: Any) -> str:
    """Număr cu virgulă zecimală, fără zecimale inutile: 98,39 / 120."""
    try:
        num = float(value)
    except (ValueError, TypeError):
        return str(value)
    return str(int(num)) if num == int(num) else f"{num:.2f}".rstrip("0").replace(".", ",")


def to_float(value: Any) -> float | None:
    """Sumă din API (număr sau text numeric) → float; None dacă lipsește."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def period_label(period: str) -> str:
    """„2026-09" → „septembrie 2026"."""
    try:
        year, month = (int(x) for x in str(period).split("-")[:2])
        return f"{MONTHS_RO_LOWER[month - 1]} {year}"
    except (ValueError, IndexError):
        return str(period)


def days_word(n: int) -> str:
    """„1 zi", „2 zile", „20 de zile" (cu „de" de la 20 în sus, ca în română)."""
    n = abs(n)
    if n == 1:
        return "1 zi"
    return f"{n} {'de ' if n % 100 >= 20 or (n and n % 100 == 0) else ''}zile"


def mask_email(email: str) -> str:
    """Email mascat pentru jurnal și diagnostic: i*********u@yahoo.com."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[0]}*@{domain}"
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"
