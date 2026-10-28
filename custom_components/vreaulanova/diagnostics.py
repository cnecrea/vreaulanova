"""
Diagnosticare pentru integrarea Nova Power & Gas (Vreau la Nova).

Exportă informații de diagnostic pentru support tickets:
- Licență (fingerprint trunchiat, status, cheie mascată)
- API: adresa, token valid, conturi asociate, contul vizualizat
- Coordinator: stare, ultima eroare, actualizări (rapide / complete)
- Pe fiecare cont și loc de consum: activ (CLC/POD) sau nu, contoare (reale / din istoric),
  facturi pe status, plăți, autocitiri, convenție, revizii, raport consum-costuri, contract găsit
- Entitățile intrării: active, indisponibile, dezactivate sau orfane; helperii input_number ai butoanelor

Diagnosticul se atașează la issue-uri publice: fără sume, indexuri, adrese, nume, email-uri,
tokenuri. Numărul contului, numerele LC și codurile CLC/POD apar doar cu ultimele cifre.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .const import API_BASE, DOMAIN, HEAVY_UPDATE_MULTIPLIER, LICENSE_DATA_KEY
from .helpers import helper_index_entity_id, is_active_mp, mask_email


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Returnează datele de diagnostic pentru Nova Power & Gas."""

    # ── Licență (fingerprint TRUNCHIAT + cheie mascată) ──
    # Fingerprint-ul complet NU apare în diagnostic: diagnosticele se atașează la
    # issue-uri publice, iar serverul de licențe acceptă cereri semnate cu fingerprint.
    license_mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    licenta_info: dict[str, Any] = {}
    if license_mgr:
        licenta_info = {
            "fingerprint": license_mgr.fingerprint[:16] + "...",
            "status": license_mgr.status,
            "license_key": license_mgr.license_key_masked,
            "is_valid": license_mgr.is_valid,
            "license_type": license_mgr.license_type,
        }

    runtime = getattr(entry, "runtime_data", None)
    coordinator = getattr(runtime, "coordinator", None)
    api = getattr(runtime, "api_client", None)
    data = (coordinator.data if coordinator else None) or {}

    # Codurile care se mască peste tot (și în entity ID-uri): CRM, numere LC, CLC/POD
    masca = _Masca()
    for crm, acct in (data.get("accounts_data") or {}).items():
        masca.add(crm)
        for mp in (acct.get("metering_points") or []) + (acct.get("inactive_metering_points") or []):
            masca.add(mp.get("number"), keep=4)
            masca.add(mp.get("specificIdForUtilityType"), keep=4)
    for aa in (api.associated_accounts if api else None) or []:
        masca.add(aa.get("accountNumber"))

    try:
        versiune_integrare = str((await async_get_integration(hass, DOMAIN)).version)
    except Exception:  # noqa: BLE001
        versiune_integrare = None

    return {
        "intrare": {
            "titlu": masca.text(entry.title.replace(
                entry.data.get("username", "") or "\0", mask_email(entry.data.get("username", ""))
            )),
            "versiune": entry.version,
            "versiune_integrare": versiune_integrare,
            "versiune_home_assistant": HA_VERSION,
            "domeniu": DOMAIN,
            "username": mask_email(entry.data.get("username", "")),
            "update_interval": entry.data.get("update_interval"),
            "token_salvat": bool(entry.data.get("token_data")),
            "token_salvat_pentru_api_nou": (entry.data.get("token_data") or {}).get("api_base") == API_BASE,
        },
        "licenta": licenta_info,
        "api": _api(api, masca),
        "coordinator": _coordinator(coordinator),
        "perioada_autocitire": _app_info(data.get("app_info")),
        "conturi": {
            masca.text(crm): _cont(acct, masca) for crm, acct in (data.get("accounts_data") or {}).items()
        },
        "entitati": _entitati(hass, entry, data, masca),
    }


# ══════════════════════════════════════════════
# API, coordinator, perioada de autocitire
# ══════════════════════════════════════════════

def _api(api, masca: _Masca) -> dict[str, Any]:
    if api is None:
        return {}
    remaining = None
    if api.has_token and api._token_obtained_at:  # noqa: SLF001 — doar pentru diagnostic
        remaining = int(api._token_expires_in - (time.monotonic() - api._token_obtained_at))  # noqa: SLF001
    return {
        "adresa": API_BASE,
        "are_token": api.has_token,
        "token_valid": api.is_token_valid(),
        "token_expira_in_zile": round(remaining / 86400, 1) if remaining is not None else None,
        "credentiale_respinse": api.auth_rejected,
        "cont_logat": masca.text(api.crm_logged_account or ""),
        "cont_vizualizat": masca.text(api.crm_viewed_account or ""),
        "antet_x_viewed_account_setat": bool(getattr(api, "_viewed_account_id", None)),
        "conturi_asociate": len(api.associated_accounts or []),
    }


def _coordinator(coordinator) -> dict[str, Any]:
    if coordinator is None:
        return {}
    counter = getattr(coordinator, "_refresh_count", None)
    exc = getattr(coordinator, "last_exception", None)
    return {
        "last_update_success": coordinator.last_update_success,
        "ultima_eroare": f"{type(exc).__name__}: {str(exc)[:200]}" if exc else None,
        "interval_secunde": int(coordinator.update_interval.total_seconds()) if coordinator.update_interval else None,
        "actualizari_efectuate": counter,
        "urmatoarea_completa": (counter % HEAVY_UPDATE_MULTIPLIER == 0) if isinstance(counter, int) else None,
        "sesiune_ramasa_pe_alt_cont": getattr(coordinator, "_session_on_other_account", None),
    }


def _app_info(info: Any) -> dict[str, Any] | None:
    if not isinstance(info, dict):
        return None
    return {
        "deschisa": bool(info.get("selfReadingsEnabled")),
        "are_mesaj_interval": bool(info.get("selfReadingIntervalMessage")),
        "anunturi": len(info.get("announcements") or []),
        "campuri": sorted(info),
    }


# ══════════════════════════════════════════════
# Conturi și locuri de consum (structură, fără valori)
# ══════════════════════════════════════════════

def _cont(acct: dict, masca: _Masca) -> dict[str, Any]:
    invoices = acct.get("invoices") or []
    balance = acct.get("balance") or {}
    reports = acct.get("consumption_reports") or {}
    return {
        "locuri_de_consum": len(acct.get("metering_points") or []),
        "facturi": len(invoices),
        "facturi_pe_status": dict(Counter(str(i.get("status")) for i in invoices)),
        "plati": len(acct.get("payments") or []),
        "autocitiri": len(acct.get("self_readings") or []),
        "contracte": len(acct.get("contracts") or []),
        "contracte_campuri": _campuri(acct.get("contracts")),
        "conventii": len(acct.get("agreements") or {}),
        "sold_campuri": sorted(balance),
        "prosumator": bool(balance.get("isProsumer")),
        "rapoarte_consum": {masca.text(place): sorted(utils) for place, utils in reports.items()},
        "facturi_campuri": _campuri(invoices),
        "plati_campuri": _campuri(acct.get("payments")),
        "autocitiri_campuri": _campuri(acct.get("self_readings")),
        "locuri": [_loc(mp, acct, masca) for mp in acct.get("metering_points") or []],
        # locuri fără CLC/POD: ignorate (fără senzori), listate doar ca să se vadă că există
        "locuri_inactive_ignorate": [
            {"numar": masca.text(m.get("number")), "utilitate": m.get("utilityType")}
            for m in acct.get("inactive_metering_points") or []
        ],
    }


def _loc(mp: dict, acct: dict, masca: _Masca) -> dict[str, Any]:
    number = mp.get("number") or ""
    clc = mp.get("specificIdForUtilityType") or ""
    meters = mp.get("meters") or []
    report = ((acct.get("consumption_reports") or {}).get(number) or {}).get(mp.get("utilityType") or "")
    summary = ((report or {}).get("summary") or {}).get(mp.get("utilityType") or "") or {}
    contract_ids = {c.get("contractId") for c in acct.get("contracts") or []}
    return {
        "numar": masca.text(number),
        "utilitate": mp.get("utilityType"),
        "tip_contract": mp.get("contractType"),
        "activ_cu_clc_pod": is_active_mp(mp),
        "contract_gasit_dupa_contractId": mp.get("contractId") in contract_ids if mp.get("contractId") else False,
        "contoare": len(meters),
        "contoare_din_istoric": sum(1 for m in meters if m.get("fromHistory")),
        "contor_campuri": _campuri(meters),
        "facturi": len((acct.get("invoices_by_mp") or {}).get(clc, [])) if clc else 0,
        "autocitiri": sum(1 for sr in acct.get("self_readings") or [] if sr.get("meteringPointNo") == number),
        "conventie": mp.get("meteringPointId") in (acct.get("agreements") or {}),
        "revizii_gaz": len(mp.get("gasRevisions") or []),
        "raport_consum": bool(report),
        "raport_luni_cu_date": summary.get("monthsWithData"),
        "campuri": sorted(mp),
    }


def _campuri(items: Any) -> list[str]:
    """Reuniunea numelor de câmpuri dintr-o listă de obiecte."""
    if not isinstance(items, list):
        return []
    return sorted({k for i in items if isinstance(i, dict) for k in i})


# ══════════════════════════════════════════════
# Entități
# ══════════════════════════════════════════════

def _entitati(hass: HomeAssistant, entry: ConfigEntry, data: dict, masca: _Masca) -> dict[str, Any]:
    """Entitățile intrării din registru, cu starea lor.

    „orfană" = există în registru, dar integrarea nu o mai creează (ex. un buton al unui loc fără
    CLC/POD sau un senzor de index pentru un contor schimbat); HA păstrează doar o stare restaurată.
    """
    registry = er.async_get(hass)
    entitati: dict[str, dict[str, str]] = {}
    numar: Counter = Counter()
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        state = hass.states.get(reg.entity_id)
        if reg.disabled_by:
            stare = "dezactivată"
        elif state is None or state.attributes.get("restored"):
            stare = "orfană"
        elif state.state == "unavailable":
            stare = "indisponibilă"
        else:
            stare = "activă"
        entitati.setdefault(reg.domain, {})[masca.text(reg.entity_id)] = stare
        numar[stare] += 1

    # helperii input_number din care butoanele citesc indexul
    helperi: dict[str, bool] = {}
    for acct in (data.get("accounts_data") or {}).values():
        for mp in acct.get("metering_points") or []:
            for meter in mp.get("meters") or []:
                if is_active_mp(mp) and meter.get("series"):
                    helper = helper_index_entity_id(mp.get("specificIdForUtilityType"), meter["series"])
                    helperi[masca.text(helper)] = hass.states.get(helper) is not None

    return {
        "numar": dict(numar),
        "helperi_index_existenti": helperi,
        **{domeniu: dict(sorted(lista.items())) for domeniu, lista in sorted(entitati.items())},
    }


# ══════════════════════════════════════════════
# Mascare
# ══════════════════════════════════════════════

class _Masca:
    """Înlocuiește codurile (CRM, LC, CLC/POD) cu „x" + ultimele cifre, și în entity ID-uri."""

    def __init__(self) -> None:
        self._coduri: dict[str, int] = {}

    def add(self, code: Any, keep: int = 3) -> None:
        code = str(code or "").strip()
        if len(code) > keep:
            self._coduri[code] = keep

    def text(self, text: str) -> str:
        text = str(text or "")
        # cele mai lungi întâi; și forma din entity_id (litere mici, fără „-")
        for code, keep in sorted(self._coduri.items(), key=lambda kv: -len(kv[0])):
            for variant in {code, code.lower(), code.lower().replace("-", "")}:
                if variant in text:
                    text = text.replace(variant, f"x{code[-keep:].lower()}")
        return text
