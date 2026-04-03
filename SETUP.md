# Ghid de instalare și configurare — Nova Power & Gas

Acest ghid acoperă fiecare pas al instalării și configurării integrării Nova Power & Gas pentru Home Assistant. Dacă ceva nu e clar, deschide un [issue pe GitHub](https://github.com/cnecrea/vreaulanova/issues).

---

## Cerințe preliminare

Înainte de a începe, asigură-te că ai:

- **Home Assistant** versiunea 2025.11 sau mai nouă (necesită pattern `entry.runtime_data`)
- **Cont Nova Power & Gas** activ — cu email și parolă funcționale pe platforma [Vreau la Nova](https://nova-energy.ro/)
- **Licență** validă — de la [hubinteligent.org/donate?ref=vreaulanova](https://hubinteligent.org/donate?ref=vreaulanova)
- **HACS** instalat (opțional, dar recomandat) — [instrucțiuni HACS](https://hacs.xyz/docs/setup/download)

---

## Metoda 1: Instalare prin HACS (recomandat)

### Pasul 1 — Adaugă repository-ul custom

1. Deschide Home Assistant → sidebar → **HACS**
2. Click pe cele 3 puncte (⋮) din colțul dreapta sus
3. Selectează **Custom repositories**
4. În câmpul „Repository" scrie: `https://github.com/cnecrea/vreaulanova`
5. În câmpul „Category" selectează: **Integration**
6. Click **Add**

### Pasul 2 — Instalează integrarea

1. În HACS, caută „**Nova Power & Gas**" sau „**Vreau la Nova**"
2. Click pe rezultat → **Download** (sau **Install**)
3. Confirmă instalarea

### Pasul 3 — Restartează Home Assistant

1. **Setări** → **Sistem** → **Restart**
2. Sau din terminal: `ha core restart`

**Așteptare**: restartul durează 1–3 minute. Nu continua până nu se încarcă complet dashboard-ul.

---

## Metoda 2: Instalare manuală

### Pasul 1 — Descarcă fișierele

1. Mergi la [Releases](https://github.com/cnecrea/vreaulanova/releases) pe GitHub
2. Descarcă ultima versiune (zip sau tar.gz)
3. Dezarhivează

### Pasul 2 — Copiază folderul

Copiază întregul folder `custom_components/vreaulanova/` în directorul de configurare al Home Assistant:

```
config/
└── custom_components/
    └── vreaulanova/
        ├── __init__.py
        ├── api.py
        ├── button.py
        ├── config_flow.py
        ├── const.py
        ├── coordinator.py
        ├── diagnostics.py
        ├── helpers.py
        ├── license.py
        ├── manifest.json
        ├── sensor.py
        ├── strings.json
        └── translations/
            └── ro.json
```

**Atenție**: folderul trebuie să fie exact `vreaulanova` (litere mici, fără spații).

Dacă folderul `custom_components` nu există, creează-l.

### Pasul 3 — Restartează Home Assistant

La fel ca la Metoda 1.

---

## Configurare inițială

### Pasul 1 — Adaugă integrarea

1. **Setări** → **Dispozitive și Servicii**
2. Click **+ Adaugă Integrare** (butonul albastru, dreapta jos)
3. Caută „**Nova**" — va apărea „Nova Power & Gas"
4. Click pe ea

### Pasul 2 — Completează formularul de autentificare

Vei vedea un formular cu 3 câmpuri:

#### Câmp 1: Adresă de email

- **Ce face**: adresa de email a contului Nova Power & Gas
- **Format**: email valid (ex: `utilizator@exemplu.com`)
- **Observație**: este și identificatorul unic al integrării — nu poți adăuga același email de două ori

#### Câmp 2: Parolă

- **Ce face**: parola contului Nova
- **Observație**: stocată criptat în baza de date HA

#### Câmp 3: Interval actualizare (secunde)

- **Ce face**: la câte secunde se reîmprospătează datele de la API
- **Implicit**: `3600` (1 oră)
- **Recomandare**: lasă pe 3600. Datele Nova nu se schimbă frecvent. Nu se recomandă valori sub 600 secunde.

### Pasul 3 — Descoperire automată conturi

După autentificare reușită, integrarea descoperă automat **toate conturile asociate**:

- **Contul principal** — contul cu care te-ai autentificat (loggedInAccount)
- **Conturi asociate** — alte coduri CRM legate de contul tău (associatedAccounts)

Integrarea extrage datele pentru fiecare cont CRM separat, prin mecanismul de switch automat între conturi.

**Observație**: Nu trebuie să selectezi manual conturile — descoperirea este complet automată. Toate conturile asociate vor genera device-uri și senzori proprii.

### Pasul 4 — Licență

Integrarea necesită o **licență validă** pentru a funcționa. Fără licență:
- Se creează doar senzorul `sensor.vreaulanova_{crm}_licenta` cu valoarea „Licență necesară"
- Toți senzorii normali și butoanele sunt dezactivate

Pentru a introduce licența:
1. **Setări** → **Dispozitive și Servicii**
2. Găsește **Nova Power & Gas** → click pe **Configurare** (⚙️)
3. Introdu cheia de licență
4. Click **Salvează**

Licențe disponibile la: [hubinteligent.org/donate?ref=vreaulanova](https://hubinteligent.org/donate?ref=vreaulanova)

### Pasul 5 — Confirmă

Click **Salvează**. Integrarea se instalează și creează:
- 1 device per CRM per utilitate (ex: „Nova Power & Gas (1234567) Gaz")
- Senzori dedicați per device (sold, facturi, contract, index, etc.)
- 1 buton de trimitere autocitiri per contor

Prima actualizare durează câteva secunde (interogare API pentru toate endpoint-urile per cont, în paralel).

---

## Reconfigurare (fără reinstalare)

Setările pot fi modificate din UI, fără a șterge și readăuga integrarea.

1. **Setări** → **Dispozitive și Servicii**
2. Găsește **Nova Power & Gas** → click pe **Configurare** (⚙️)
3. Poți modifica:
   - Credențialele (email, parolă)
   - Intervalul de actualizare
   - Cheia de licență
4. Click **Salvează**
5. Integrarea se reîncarcă automat (nu e nevoie de restart)

**Validare**: dacă modifici credențialele și noile date sunt greșite, vei primi o eroare și configurația existentă rămâne neschimbată.

---

## Referință rapidă — Entity ID-uri

### Senzori per utilitate (gaz / electricitate)

| Senzor | Entity ID |
|---|---|
| Sold total | `sensor.vreaulanova_{crm}_{ut}_sold_total` |
| Sold prosumator | `sensor.vreaulanova_{crm}_{ut}_sold_prosumator` |
| Citire permisă | `sensor.vreaulanova_{crm}_{ut}_citire_permisa` |
| Arhivă facturi | `sensor.vreaulanova_{crm}_{ut}_arhiva_facturi` |
| Arhivă plăți | `sensor.vreaulanova_{crm}_{ut}_arhiva_plati` |
| Date contract | `sensor.vreaulanova_{crm}_{ut}_date_contract` |
| Convenție consum | `sensor.vreaulanova_{crm}_{ut}_conventie_consum` |
| Factură restantă | `sensor.vreaulanova_{crm}_{ut}_factura_restanta` |

### Senzori per contor

| Senzor | Entity ID |
|---|---|
| Index contor | `sensor.vreaulanova_{crm}_{ut}_index_contor_{series}` |

### Senzori specifici gaz

| Senzor | Entity ID |
|---|---|
| Revizie tehnică | `sensor.vreaulanova_{crm}_gaz_revizie_tehnica` |

### Butoane

| Buton | Entity ID |
|---|---|
| Trimite index | `button.vreaulanova_{crm}_{ut}_trimite_index` |

**Unde**: `{crm}` = codul CRM (ex: `1234567`), `{ut}` = `gaz` sau `electricitate`, `{series}` = seria contorului.

---

## Pregătire pentru butoanele Trimite index

Butoanele de trimitere autocitiri citesc valoarea din entitatea `input_number` corespunzătoare. Entity ID-ul `input_number` este generat automat pe baza codului CLC/POD și seriei contorului:

```
input_number.vreaulanova_{clc_pod}_{series}_index
```

Adaugă în `configuration.yaml`:

```yaml
input_number:
  vreaulanova_RO123456789_AB12345_index:
    name: Index contor gaz Nova
    min: 0
    max: 999999
    step: 1
    mode: box
```

> **Observație:** Înlocuiește `RO123456789` și `AB12345` cu valorile reale ale codului CLC/POD și seriei contorului tău. Le găsești în atributele senzorului de index sau în logurile de debug.

Restartează HA după adăugare.

---

## Exemple de carduri Lovelace

### Card general — toate entitățile

```yaml
type: entities
title: Nova Power & Gas
entities:
  - entity: sensor.vreaulanova_1234567_gaz_date_contract
    name: Date contract
  - entity: sensor.vreaulanova_1234567_gaz_sold_total
    name: Sold total
  - entity: sensor.vreaulanova_1234567_gaz_citire_permisa
    name: Citire permisă
  - entity: sensor.vreaulanova_1234567_gaz_conventie_consum
    name: Convenție consum
  - entity: sensor.vreaulanova_1234567_gaz_factura_restanta
    name: Factură restantă
  - entity: sensor.vreaulanova_1234567_gaz_revizie_tehnica
    name: Revizie tehnică
  - entity: button.vreaulanova_1234567_gaz_trimite_index
    name: Trimite index gaz
```

### Card — Sold total

```yaml
type: entity
entity: sensor.vreaulanova_1234567_gaz_sold_total
name: Sold Nova - Gaz
icon: mdi:cash
```

### Card — Factură restantă

```yaml
type: entities
title: Facturi restante Nova
entities:
  - entity: sensor.vreaulanova_1234567_gaz_factura_restanta
    name: Factură restantă
  - type: attribute
    entity: sensor.vreaulanova_1234567_gaz_factura_restanta
    attribute: Total restantă
    name: Total neachitat
  - type: attribute
    entity: sensor.vreaulanova_1234567_gaz_factura_restanta
    attribute: Facturi neachitate
    name: Nr facturi
```

### Card — Trimitere index gaz cu input_number

```yaml
type: vertical-stack
title: Trimitere index gaz
cards:
  - type: entities
    entities:
      - entity: input_number.vreaulanova_RO123456789_AB12345_index
        name: Index de trimis
      - entity: sensor.vreaulanova_1234567_gaz_citire_permisa
        name: Citire permisă
  - type: button
    entity: button.vreaulanova_1234567_gaz_trimite_index
    name: Trimite indexul gaz
    icon: mdi:fire
    tap_action:
      action: toggle
```

### Card condiționat — Alertă factură restantă

```yaml
type: conditional
conditions:
  - condition: state
    entity: sensor.vreaulanova_1234567_gaz_factura_restanta
    state: "Da"
card:
  type: markdown
  content: >-
    ## ⚠️ Ai factură restantă Nova!

    **Total restantă:** {{ state_attr('sensor.vreaulanova_1234567_gaz_factura_restanta', 'Total restantă') }}

    Verifică detaliile în secțiunea Facturi din dashboard.
```

---

## Verificare după instalare

### Verifică că device-urile există

1. **Setări** → **Dispozitive și Servicii** → click pe **Nova Power & Gas**
2. Ar trebui să vezi un device per CRM per utilitate (ex: „Nova Power & Gas (1234567) Gaz")

### Verifică senzorii

1. **Instrumente dezvoltator** → **Stări**
2. Filtrează după `vreaulanova`
3. Ar trebui să vezi entitățile cu valori (ex: `Da`, `Nu`, `Activ`, `Validă`, sume RON, etc.)

### Verifică logurile (dacă ceva nu merge)

1. **Setări** → **Sistem** → **Jurnale**
2. Caută mesaje cu `vreaulanova`
3. Pentru detalii, activează debug logging — vezi [DEBUG.md](DEBUG.md)

---

## Dezinstalare

### Prin HACS

1. HACS → găsește „Nova Power & Gas" → **Remove**
2. Restartează Home Assistant

### Manual

1. **Setări** → **Dispozitive și Servicii** → Nova Power & Gas → **Șterge**
2. Șterge folderul `config/custom_components/vreaulanova/`
3. Restartează Home Assistant

---

## Observații generale

- **Înlocuiește `1234567`** cu codul tău CRM real în toate exemplele de mai sus.
- **Entity ID-urile sunt setate manual** de integrare pe baza codului CRM, utilitații și (pentru index) a seriei contorului.
- **Atributele apar doar când Nova furnizează datele.** Dacă un atribut nu e vizibil, înseamnă că API-ul nu a returnat acea informație — nu e o eroare.
- **Senzorii prosumator** apar doar dacă există contracte prosumator.
- **Revizia tehnică gaz** afișează „Validă", „Expirată" sau „Nedefinit" — nu data brută.
- **Heavy refresh**: plățile se actualizează doar la fiecare al 6-lea ciclu (≈6h la interval implicit de 1h) pentru a reduce încărcarea API.
- Dacă întâmpini probleme, consultă [DEBUG.md](DEBUG.md) pentru activarea logării detaliate.
