"""
Diagnosticare pentru integrarea Nova Power & Gas (Vreau la Nova).

Exportă informații de diagnostic pentru support tickets:
- Licență (fingerprint, status, cheie mascată)
- Starea coordinator-ului
- Senzori, butoane, senzori binari activi

Datele sensibile (parolă, token-uri) sunt excluse.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LICENSE_DATA_KEY


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Returnează datele de diagnostic pentru Nova Power & Gas."""

    # ── Licență (fingerprint + cheie mascată) ──
    license_mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    licenta_info: dict[str, Any] = {}
    if license_mgr:
        licenta_info = {
            "fingerprint": license_mgr.fingerprint,
            "status": license_mgr.status,
            "license_key": license_mgr.license_key_masked,
            "is_valid": license_mgr.is_valid,
            "license_type": license_mgr.license_type,
        }

    # ── Coordinator (via runtime_data) ──
    runtime = getattr(entry, "runtime_data", None)
    coordinator_info: dict[str, Any] = {}
    if runtime and hasattr(runtime, "coordinator") and runtime.coordinator:
        coordinator = runtime.coordinator
        coordinator_info = {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        }
        data = coordinator.data or {}
        coordinator_info["crm_logged"] = data.get("crm_logged")
        coordinator_info["crm_viewed"] = data.get("crm_viewed")
        coordinator_info["metering_points_count"] = len(
            data.get("metering_points", [])
        )
        coordinator_info["invoices_count"] = len(data.get("invoices", []))
        coordinator_info["contracts_count"] = len(data.get("contracts", []))

    # ── Senzori activi ──
    senzori_activi = sorted(
        entitate.entity_id
        for entitate in hass.states.async_all("sensor")
        if entitate.entity_id.startswith(f"sensor.{DOMAIN}_")
    )

    # ── Butoane active ──
    butoane_active = sorted(
        entitate.entity_id
        for entitate in hass.states.async_all("button")
        if entitate.entity_id.startswith(f"button.{DOMAIN}_")
    )

    # ── Senzori binari activi ──
    binary_activi = sorted(
        entitate.entity_id
        for entitate in hass.states.async_all("binary_sensor")
        if entitate.entity_id.startswith(f"binary_sensor.{DOMAIN}_")
    )

    # ── Config entry (fără date sensibile) ──
    return {
        "intrare": {
            "titlu": entry.title,
            "versiune": entry.version,
            "domeniu": DOMAIN,
            "username": _mascheaza_email(entry.data.get("username", "")),
            "update_interval": entry.data.get("update_interval"),
        },
        "licenta": licenta_info,
        "coordinator": coordinator_info,
        "stare": {
            "senzori_activi": len(senzori_activi),
            "lista_senzori": senzori_activi,
            "butoane_active": len(butoane_active),
            "lista_butoane": butoane_active,
            "binary_activi": len(binary_activi),
            "lista_binary": binary_activi,
        },
    }


def _mascheaza_email(email: str) -> str:
    """Maschează email-ul păstrând prima literă și domeniul."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}{'*' * (len(local) - 1)}@{domain}"
