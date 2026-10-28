# Nova Power & Gas — Integrare Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/cnecrea/vreaulanova)](https://github.com/cnecrea/vreaulanova/releases)
[![GitHub Stars](https://img.shields.io/github/stars/cnecrea/vreaulanova?style=flat&logo=github)](https://github.com/cnecrea/vreaulanova/stargazers)
[![Instalări](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/vreaulanova/main/statistici/shields/descarcari.json)](https://github.com/cnecrea/vreaulanova)
[![Ultima versiune](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/vreaulanova/main/statistici/shields/ultima_release.json)](https://github.com/cnecrea/vreaulanova/releases/latest)

Integrare pentru [Home Assistant](https://www.home-assistant.io/) care aduce din contul tău [Nova Power & Gas](https://nova-energy.ro/) soldul, facturile, plățile, consumul și costurile lunare, convenția de consum, indexul contorului și revizia tehnică a instalației de gaz — și trimite autocitirea direct din Home Assistant.


---

## Ce oferă

- **Sold, facturi, plăți** — sold total, factură restantă cu scadența și zilele rămase, arhivele anului curent.
- **Consum și cost lunar** — din raportul Nova: ultima lună, mediile lunare și istoricul pe 12 luni.
- **Index contor** — cu unitate și tip (gaz / energie), deci poate fi adăugat în panoul **Energie**.
- **Trimitere index** — un buton per loc de consum; rezultatul (reușită sau motivul refuzului) apare ca notificare.
- **Convenție de consum, revizie tehnică gaz, date contract.**
- **Mai multe conturi** — contul principal și conturile asociate sunt descoperite automat.
- **Diagnostic** descărcabil, fără date personale, pentru raportarea problemelor.

---

## Instalare

### HACS (recomandat)

1. HACS → meniul **⋮** din dreapta sus → **Custom repositories**.
2. URL: `https://github.com/cnecrea/vreaulanova`, categoria **Integration** → **Add**.
3. Caută **Nova Power & Gas** → **Download**.
4. Repornește Home Assistant.

### Manual

Copiază folderul `custom_components/vreaulanova/` în `config/custom_components/` și repornește Home Assistant.

---

## Configurare

**Setări** → **Dispozitive și servicii** → **Adaugă integrare** → **Nova Power & Gas**.

| Câmp | Descriere | Implicit |
|---|---|---|
| Adresă de email | Emailul contului Nova (cel din myaccount.nova-energy.ro) | — |
| Parolă | Parola contului Nova | — |
| Interval de actualizare | Secunde între actualizări (minim 3600) | `3600` |

Conturile asociate se descoperă singure — nu selectezi nimic manual.

**Licența** se introduce din **Configurare** → **Licență** (pe pagina integrării). Fără licență validă apare doar senzorul „Licență necesară". Licență: [hubinteligent.org/donate?ref=vreaulanova](https://hubinteligent.org/donate?ref=vreaulanova).

Email, parolă și interval se pot schimba oricând din **Configurare** → **Setări cont**, fără reinstalare. Dacă Nova respinge parola salvată, Home Assistant îți cere direct parola nouă.

---

## Device-uri și entități

Fiecare **loc de consum activ** devine un device: `Nova Power & Gas (1234567) LC-00202600 Gaz`.

Entity ID-urile au forma `sensor.vreaulanova_{cont}_{loc}_{tip}`, de exemplu `sensor.vreaulanova_1234567_lc00202600_sold_total`.

| Entitate | Sufix | Valoare |
|---|---|---|
| Sold total | `sold_total` | lei (al contului) |
| Sold prosumator | `sold_prosumator` | lei — doar la prosumatori |
| Factură restantă | `factura_restanta` | Da / Nu |
| Arhivă facturi | `arhiva_facturi` | facturi emise în anul curent |
| Arhivă plăți | `arhiva_plati` | plăți din anul curent |
| Date contract | `date_contract` | starea contractului |
| Convenție consum | `conventie_consum` | luni cu convenție |
| Consum lunar | `consum_lunar` | m³ / kWh — ultima lună cu consum |
| Cost lunar | `cost_lunar` | lei — ultima lună facturată |
| Citire permisă | `citire_permisa` | Da / Nu — perioada de autocitire |
| Revizie tehnică | `revizie_tehnica` | Validă / Expirată / Nedefinit — doar gaz |
| Index contor | `index_contor_{serie}` | m³ / kWh |
| Trimite index | `button.…_trimite_index` | buton |

„Consum lunar" și „Cost lunar" apar doar dacă Nova oferă raportul de consum pentru acel loc.

**Locurile fără cod CLC/POD** (vechi sau neactivate) nu au contract activ, facturi sau contor la Nova și nu primesc device. Dacă un loc devine activ mai târziu, integrarea se reîncarcă singură și îl adaugă.

### Atribute utile

**Factură restantă** — fiecare factură neachitată, plus două atribute pentru automatizări:

```yaml
Factură FG-1234567: "133,37 lei, scadentă pe 15 noiembrie 2026 (peste 5 zile)"
Total restantă: "133.37 RON"
Facturi neachitate: 1
Următoarea scadență: "15.11.2026"
Zile până la scadență: 5      # număr; negativ după scadență
```

**Consum lunar** — `Luna`, `Consum mediu lunar`, `Consum total` și câte un atribut pe lună (`Consum septembrie 2026: "98 m³"`). **Cost lunar** are aceeași structură, în lei.

**Citire permisă** — intervalul de autocitire și anunțurile Nova (de exemplu prelungirea perioadei).

**Index contor** — ultima citire, consumul, data, tipul citirii și `Helper index` (vezi mai jos).

---

## Trimiterea indexului

Butonul **Trimite index** citește indexul dintr-un helper `input_number`. ID-ul exact îl găsești în atributul **Helper index** al butonului (sau al senzorului de index), de exemplu:

```
input_number.vreaulanova_dgsvlrvl12345678_abc_12345678_2021_index
```

Creează-l din **Setări** → **Dispozitive și servicii** → **Ajutoare** → **Creează ajutor** → **Număr**, apoi deschide-i setările și pune exact acest **ID entitate**. Sau în `configuration.yaml`:

```yaml
input_number:
  vreaulanova_dgsvlrvl12345678_abc_12345678_2021_index:
    name: Index gaz de trimis
    min: 0
    max: 999999
    step: 1
    mode: box
```

Scrie indexul în helper și apasă butonul. Rezultatul apare în **notificările din bara laterală**: indexul trimis, sau motivul refuzului (perioadă închisă, helper lipsă, mesajul Nova). Butonul verifică perioada de autocitire direct la Nova în momentul apăsării.

Automatizare — trimite indexul unui contor inteligent când se deschide perioada:

```yaml
alias: "Nova: trimite indexul gazului"
triggers:
  - trigger: state
    entity_id: sensor.vreaulanova_1234567_lc00202600_citire_permisa
    to: "Da"
actions:
  - action: input_number.set_value
    target:
      entity_id: input_number.vreaulanova_dgsvlrvl12345678_abc_12345678_2021_index
    data:
      value: "{{ states('sensor.contor_gaz') | int }}"
  - action: button.press
    target:
      entity_id: button.vreaulanova_1234567_lc00202600_trimite_index
```

---

## Exemple

**Notificare cu 3 zile înainte de scadență:**

```yaml
alias: "Nova: factură aproape de scadență"
triggers:
  - trigger: time
    at: "09:00:00"
conditions:
  - condition: template
    value_template: >
      {{ state_attr('sensor.vreaulanova_1234567_lc00202600_factura_restanta', 'Zile până la scadență')
         | int(99) <= 3 }}
actions:
  - action: notify.mobile_app_telefonul_meu
    data:
      title: "Factură Nova"
      message: >
        Scadență pe {{ state_attr('sensor.vreaulanova_1234567_lc00202600_factura_restanta', 'Următoarea scadență') }}:
        {{ state_attr('sensor.vreaulanova_1234567_lc00202600_factura_restanta', 'Total restantă') }}
```

**Panoul Energie:** **Setări** → **Panouri** → **Energie** → **Consum de gaz** → adaugă senzorul *Index contor*. Indexul se actualizează când Nova înregistrează o citire nouă (de regulă lunar).

**Card:**

```yaml
type: entities
title: Nova Power & Gas
entities:
  - sensor.vreaulanova_1234567_lc00202600_sold_total
  - sensor.vreaulanova_1234567_lc00202600_factura_restanta
  - sensor.vreaulanova_1234567_lc00202600_consum_lunar
  - sensor.vreaulanova_1234567_lc00202600_cost_lunar
  - sensor.vreaulanova_1234567_lc00202600_citire_permisa
  - button.vreaulanova_1234567_lc00202600_trimite_index
```

---

## Cum se actualizează datele

- La fiecare interval (implicit o oră): sold, facturi, locuri de consum, autocitiri, contracte, convenții, perioada de autocitire.
- La fiecare a 6-a actualizare (≈ 6 ore): în plus plățile, reviziile de gaz și raportul de consum-costuri.
- Dacă Nova nu răspunde la o parte din date, se păstrează valorile anterioare; dacă nu răspunde deloc, entitățile devin indisponibile până la următoarea încercare.

Datele vin de la `https://myaccount-admin.nova-energy.ro/api/v1` — același API pe care îl folosesc myaccount.nova-energy.ro și aplicația mobilă.

---

## Probleme?

- [FAQ.md](FAQ.md) — întrebări frecvente.
- [DEBUG.md](DEBUG.md) — jurnalul de depanare și diagnosticul.
- [Issues](https://github.com/cnecrea/vreaulanova/issues) — atașează diagnosticul (pagina integrării → **⋮** → **Descarcă diagnosticul**); nu conține date personale.

---

## Cerințe

- Home Assistant 2025.11 sau mai nou
- Cont Nova Power & Gas (email + parolă)
- Licență validă — [hubinteligent.org/donate?ref=vreaulanova](https://hubinteligent.org/donate?ref=vreaulanova)

---

## ☕ Susține dezvoltatorul

Dacă integrarea îți e utilă, **invită-mă la o cafea**! 🫶

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Susține%20dezvoltatorul-orange?style=for-the-badge&logo=buy-me-a-coffee)](https://buymeacoffee.com/cnecrea)

Contribuțiile sunt binevenite — pull request-uri sau [issue-uri](https://github.com/cnecrea/vreaulanova/issues). Un ⭐ pe [GitHub](https://github.com/cnecrea/vreaulanova/) ajută mult.

## Licență

[MIT](LICENSE.md)
