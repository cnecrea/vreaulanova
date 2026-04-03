# Nova Power & Gas — Integrare Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/cnecrea/vreaulanova)](https://github.com/cnecrea/vreaulanova/releases)
[![GitHub Stars](https://img.shields.io/github/stars/cnecrea/vreaulanova?style=flat&logo=github)](https://github.com/cnecrea/vreaulanova/stargazers)
[![Instalări](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/vreaulanova/main/statistici/shields/descarcari.json)](https://github.com/cnecrea/vreaulanova)
[![Ultima versiune](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/vreaulanova/main/statistici/shields/ultima_release.json)](https://github.com/cnecrea/vreaulanova/releases/latest)


Integrare custom pentru [Home Assistant](https://www.home-assistant.io/) care monitorizează datele contractuale, consumul și facturile prin API-ul [Nova Power & Gas](https://nova-energy.ro/) (platforma „Vreau la Nova").

Oferă senzori dedicați per cod CRM și per utilitate (gaz / electricitate), sold, facturi, plăți, convenție consum, index contor, revizie tehnică gaz, și butoane de trimitere autocitiri. Suportă complet **multi-account** (cont principal + conturi asociate).

---

## Ce face integrarea

- **Descoperire automată** a conturilor asociate prin endpoint-ul web `/accounts/login/client`
- **Multi-account** — un singur config_entry extrage datele pentru TOATE conturile (principal + asociate): switch automat între conturi
- **Senzori per utilitate** — fiecare cont CRM poate avea gaz, electricitate sau ambele; fiecare utilitate devine un device separat
- **Sold și facturi** — sold total (RON), facturi restante cu calcul scadență, facturi prosumator (condiționat)
- **Index contor** — index curent per contor (serie), cu ultima citire și consum în atribute
- **Convenție consum** — nr luni cu convenție, valori per lună în atribute
- **Arhive** — facturi și plăți pe anul curent, cu sume per intrare și totaluri
- **Revizie tehnică gaz** — Validă / Expirată / Nedefinit, cu date revizii și verificări
- **Trimitere autocitiri** — buton per contor care citește din `input_number` și trimite la API
- **Sistem de licență** — fără licență validă se afișează doar senzorul „Licență necesară"
- **Reconfigurare fără reinstalare** — OptionsFlow pentru credențiale și licență

---

## Sursa datelor

Datele vin prin API-ul backend Nova Power & Gas (Payload CMS / Next.js) la `https://backend.nova-energy.ro/api`, care expune endpoint-uri REST:

| Endpoint | Descriere |
|----------|-----------|
| `/accounts/login/client` | Autentificare (web) — returnează loggedInAccount, viewedAccount, associatedAccounts |
| `/accounts/switch` | Comutare între conturi asociate |
| `/accounts/me` | Detalii utilizator curent |
| `/globals/app-info/general` | Info aplicație (selfReadingsEnabled) |
| `/metering-points` | Puncte de măsurare (contoare, meters, gasRevisions) |
| `/metering-points/{id}/consumption-agreements` | Convenție consum per punct de măsurare |
| `/self-readings` | Autocitiri (istoric) |
| `/self-readings/add` | Trimitere autocitire (POST) |
| `/invoices` | Facturi |
| `/balances` | Sold total + prosumator |
| `/contracts` | Contracte per utilitate |
| `/payments` | Plăți |

Autentificarea se face cu email + parolă (POST JSON). Token-ul JWT expiră la 30 de zile. Re-autentificarea este automată.

---

## Instalare

### HACS (recomandat)

1. Deschide HACS în Home Assistant
2. Click pe cele 3 puncte (⋮) din colțul dreapta sus → **Custom repositories**
3. Adaugă URL-ul: `https://github.com/cnecrea/vreaulanova`
4. Categorie: **Integration**
5. Click **Add** → găsește „Nova Power & Gas" → **Install**
6. Restartează Home Assistant

### Manual

1. Copiază folderul `custom_components/vreaulanova/` în directorul `config/custom_components/` din Home Assistant
2. Restartează Home Assistant

---

## Configurare

### Pasul 1 — Adaugă integrarea

1. **Setări** → **Dispozitive și Servicii** → **Adaugă Integrare**
2. Caută „**Nova Power & Gas**" sau „**Vreau la Nova**"
3. Completează formularul:

| Câmp | Descriere | Implicit |
|------|-----------|----------|
| **Email** | Adresa de email a contului Nova | — |
| **Parolă** | Parola contului Nova | — |
| **Interval actualizare** | Secunde între interogările API | `3600` (1 oră) |

### Pasul 2 — Licență

Integrarea necesită o licență validă. Poți achiziționa una de la [hubinteligent.org/donate?ref=vreaulanova](https://hubinteligent.org/donate?ref=vreaulanova). Licența se introduce din **OptionsFlow** (Setări → Dispozitive și Servicii → Nova Power & Gas → Configurare).

### Pasul 3 — Descoperire automată conturi

După autentificare, integrarea descoperă automat:
- Contul principal (loggedInAccount)
- Toate conturile asociate (associatedAccounts)

Fiecare cont CRM generează device-uri separate per utilitate. Nu trebuie să selectezi manual — totul este automat.

Detalii complete în [SETUP.md](SETUP.md).

---

## Entități create

### Structura device-urilor

Integrarea creează un **device per CRM per utilitate**. Exemple:
- `Nova Power & Gas (3008726) Gaz`
- `Nova Power & Gas (3047398) Gaz`
- `Nova Power & Gas (3047398) Energie Electrică`

### Pattern entity_id

Toate entitățile urmează pattern-ul: `{platformă}.vreaulanova_{crm}_{utilitate}_{suffix}`

| `{utilitate}` | Utilitate API |
|---|---|
| `gaz` | gas |
| `electricitate` | electricity |

### Senzori per utilitate

| Senzor | Entity ID | Valoare principală | Icon |
|--------|-----------|-------------------|------|
| Sold total | `sensor.vreaulanova_{crm}_{ut}_sold_total` | Sumă RON | mdi:cash |
| Sold prosumator | `sensor.vreaulanova_{crm}_{ut}_sold_prosumator` | Sumă RON | mdi:solar-power |
| Citire permisă | `sensor.vreaulanova_{crm}_{ut}_citire_permisa` | Da / Nu | mdi:pencil-box-outline |
| Arhivă facturi | `sensor.vreaulanova_{crm}_{ut}_arhiva_facturi` | Nr facturi (anul curent) | mdi:file-document-multiple-outline |
| Arhivă plăți | `sensor.vreaulanova_{crm}_{ut}_arhiva_plati` | Nr plăți (anul curent) | mdi:cash-check |
| Date contract | `sensor.vreaulanova_{crm}_{ut}_date_contract` | Status (Activ / Inactiv) | mdi:file-sign |
| Convenție consum | `sensor.vreaulanova_{crm}_{ut}_conventie_consum` | Nr luni cu convenție | mdi:chart-bar |
| Factură restantă | `sensor.vreaulanova_{crm}_{ut}_factura_restanta` | Da / Nu | mdi:file-document-alert |

### Senzori per contor (meters)

| Senzor | Entity ID | Valoare principală | Icon |
|--------|-----------|-------------------|------|
| Index contor | `sensor.vreaulanova_{crm}_{ut}_index_contor_{series}` | Valoare index (m³ / kWh) | mdi:counter |

### Senzori specifici gaz

| Senzor | Entity ID | Valoare principală | Icon |
|--------|-----------|-------------------|------|
| Revizie tehnică | `sensor.vreaulanova_{crm}_gaz_revizie_tehnica` | Validă / Expirată / Nedefinit | mdi:wrench-clock |

### Senzor licență (fără licență validă)

| Senzor | Entity ID | Valoare principală | Icon |
|--------|-----------|-------------------|------|
| Licență necesară | `sensor.vreaulanova_{crm}_licenta` | „Licență necesară" | mdi:license |

### Butoane

| Buton | Entity ID | Icon | Condiție |
|-------|-----------|------|----------|
| Trimite index | `button.vreaulanova_{crm}_{ut}_trimite_index` | mdi:fire (gaz) / mdi:flash (electricitate) | Licență validă |

---

## Atribute detaliate per senzor

### Sold total

Valoare principală: suma în RON (device_class: monetary, state_class: total).

### Citire permisă

Valoare principală: Da / Nu — pe baza `app_info.selfReadingsEnabled` de la API.

### Arhivă facturi

Atribute:
```yaml
Emisă pe 4 martie 2026: "125,50 lei"
Emisă pe 15 februarie 2026: "98,20 lei"
Total facturi: "2"
Total facturat: "223,70 lei"
```

### Arhivă plăți

Atribute:
```yaml
Plătită pe 10 martie 2026: "125,50 lei"
Total plăți: "1"
Total plătit: "125,50 lei"
```

### Date contract

Atribute:
```yaml
Contract: "NV-12345"
Tip client: "Casnic"
Semnat la: "2024-01-15"
Intrat în vigoare: "2024-02-01"
Tip: "Doar electronic"
```

### Convenție consum

Atribute:
```yaml
Convenție din luna ianuarie: "150 m³"
Convenție din luna februarie: "120 m³"
# ... per fiecare lună cu valoare nenulă
```

### Factură restantă

Atribute:
```yaml
Total restantă: "223.70 RON"
Scadență ultima factură: "2026-04-15"
Facturi neachitate: 2
```

### Index contor

Atribute:
```yaml
Ultima citire: 6030
Consum: 150
Data ultima citire: "2026-03-01"
Index vechi: 5880
```

### Revizie tehnică gaz

Atribute:
```yaml
Data ultimei revizii: "2024-06-15"
Data următoarei revizii: "2026-06-15"
Data ultimei verificări: "2023-09-10"
Data următoarei verificări: "2025-09-10"
```

---

## Exemple de automatizări

### Notificare factură restantă

```yaml
automation:
  - alias: "Notificare factură restantă Nova"
    trigger:
      - platform: state
        entity_id: sensor.vreaulanova_3043777_gaz_factura_restanta
        to: "Da"
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "Factură restantă Nova"
          message: >
            Ai {{ state_attr('sensor.vreaulanova_3043777_gaz_factura_restanta', 'Total restantă') }}
            de plătit.
```

### Card pentru Dashboard

```yaml
type: entities
title: Nova Power & Gas
entities:
  - entity: sensor.vreaulanova_3043777_gaz_date_contract
    name: Contract
  - entity: sensor.vreaulanova_3043777_gaz_sold_total
    name: Sold total
  - entity: sensor.vreaulanova_3043777_gaz_citire_permisa
    name: Citire permisă
  - entity: sensor.vreaulanova_3043777_gaz_factura_restanta
    name: Factură restantă
  - entity: sensor.vreaulanova_3043777_gaz_revizie_tehnica
    name: Revizie tehnică
```

### Card condiționat — Alertă factură restantă

```yaml
type: conditional
conditions:
  - condition: state
    entity: sensor.vreaulanova_3043777_gaz_factura_restanta
    state: "Da"
card:
  type: markdown
  content: >-
    ## ⚠️ Ai factură restantă Nova!

    **Total restantă:** {{ state_attr('sensor.vreaulanova_3043777_gaz_factura_restanta', 'Total restantă') }}

    Verifică detaliile în secțiunea Facturi.
```

---

## Structura fișierelor

```
custom_components/vreaulanova/
├── __init__.py          # Setup/unload integrare (runtime_data, licență, heartbeat)
├── api.py               # Manager API — login /accounts/login/client, switch, GET/POST
├── button.py            # Butoane trimitere autocitiri per contor (gaz / electricitate)
├── config_flow.py       # ConfigFlow + OptionsFlow (autentificare, licență)
├── const.py             # Constante, URL-uri API
├── coordinator.py       # DataUpdateCoordinator — multi-account (switch → fetch → switch înapoi)
├── diagnostics.py       # Diagnostics pentru troubleshooting
├── helpers.py           # Funcții utilitare
├── license.py           # Manager licență (server-side v3.3, Ed25519, HMAC-SHA256)
├── manifest.json        # Metadata integrare
├── sensor.py            # Clase senzor per utilitate + per contor
├── strings.json         # Traduceri implicite (engleză)
└── translations/
    └── ro.json          # Traduceri române
```

---

## Cerințe

- **Home Assistant** 2025.11 sau mai nou (pattern `entry.runtime_data`)
- **HACS** (opțional, pentru instalare ușoară)
- **Cont Nova Power & Gas** activ cu email + parolă
- **Licență** validă — [hubinteligent.org/donate?ref=vreaulanova](https://hubinteligent.org/donate?ref=vreaulanova)
- **Python**: `cryptography >= 41.0.0` (dependință automată prin manifest)

---

## Limitări cunoscute

1. **O singură instanță per cont** — dacă încerci să adaugi același email de două ori, vei primi eroare.

2. **Citire permisă** — depinde de `app_info.selfReadingsEnabled` global de la Nova, nu per metering point.

3. **Trimitere autocitiri** — butonul citește din `input_number.vreaulanova_{clc_pod}_{series}_index`. Entitatea trebuie creată manual în `configuration.yaml`.

4. **Sold prosumator** — senzorul apare doar dacă există contracte prosumator.

5. **Heavy refresh** — plățile se reîmprospătează doar la fiecare al 6-lea ciclu de actualizare (≈6h la interval implicit de 1h).

---

## ☕ Susține dezvoltatorul

Dacă ți-a plăcut această integrare și vrei să sprijini munca depusă, **invită-mă la o cafea**! 🫶

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Susține%20dezvoltatorul-orange?style=for-the-badge&logo=buy-me-a-coffee)](https://buymeacoffee.com/cnecrea)

---

## 🧑‍💻 Contribuții

Contribuțiile sunt binevenite! Simte-te liber să trimiți un pull request sau să raportezi probleme [aici](https://github.com/cnecrea/vreaulanova/issues).

---

## 🌟 Suport
Dacă îți place această integrare, oferă-i un ⭐ pe [GitHub](https://github.com/cnecrea/vreaulanova/)! 😊


## Licență

[MIT](LICENSE)
