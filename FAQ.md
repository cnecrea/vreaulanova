<a name="top"></a>
# Întrebări frecvente

- [Cum adaug integrarea în Home Assistant?](#cum-adaug-integrarea-în-home-assistant)
- [Am mai multe conturi CRM asociate. Sunt descoperite automat?](#am-mai-multe-conturi-crm-asociate-sunt-descoperite-automat)
- [Ce senzori primesc per cont?](#ce-senzori-primesc-per-cont)
- [Ce înseamnă „Sold total"?](#ce-înseamnă-sold-total)
- [Ce înseamnă senzorul „Citire permisă"?](#ce-înseamnă-senzorul-citire-permisă)
- [Nu îmi apare indexul curent. De ce?](#nu-îmi-apare-indexul-curent-de-ce)
- [Ce înseamnă senzorul „Factură restantă"?](#ce-înseamnă-senzorul-factură-restantă)
- [Ce înseamnă senzorul „Revizie tehnică"?](#ce-înseamnă-senzorul-revizie-tehnică)
- [Nu sunt prosumator. Senzorul de prosumator lipsește — e normal?](#nu-sunt-prosumator-senzorul-de-prosumator-lipsește--e-normal)
- [De ce entitățile au un nume lung, cu codul CRM inclus?](#de-ce-entitățile-au-un-nume-lung-cu-codul-crm-inclus)
- [Vreau să trimit indexul automat. De ce am nevoie?](#vreau-să-trimit-indexul-automat-de-ce-am-nevoie)
- [Ce e licența și de ce am nevoie de ea?](#ce-e-licența-și-de-ce-am-nevoie-de-ea)
- [Am introdus licența dar senzorii tot arată „Licență necesară". De ce?](#am-introdus-licența-dar-senzorii-tot-arată-licență-necesară-de-ce)
- [Am schimbat opțiunile integrării. Trebuie să restartez?](#am-schimbat-opțiunile-integrării-trebuie-să-restartez)
- [Trebuie să șterg și readaug integrarea la actualizare?](#trebuie-să-șterg-și-readaug-integrarea-la-actualizare)
- [Îmi place proiectul. Cum pot să-l susțin?](#îmi-place-proiectul-cum-pot-să-l-susțin)

---

## Cum adaug integrarea în Home Assistant?

[↑ Înapoi la cuprins](#top)

Ai nevoie de HACS (Home Assistant Community Store) instalat. Dacă nu-l ai, urmează [ghidul oficial HACS](https://hacs.xyz/docs/use).

1. În Home Assistant, mergi la **HACS** → cele **trei puncte** din dreapta sus → **Custom repositories**.
2. Introdu URL-ul: `https://github.com/cnecrea/vreaulanova` și selectează tipul **Integration**.
3. Apasă **Add**, apoi caută **Nova Power & Gas** în HACS și instalează.
4. Repornește Home Assistant.
5. Mergi la **Setări** → **Dispozitive și Servicii** → **Adaugă Integrare** → caută **Nova Power & Gas** și urmează pașii de configurare.

Detalii complete în [SETUP.md](./SETUP.md).

---

## Am mai multe conturi CRM asociate. Sunt descoperite automat?

[↑ Înapoi la cuprins](#top)

Da. Integrarea folosește endpoint-ul web `/accounts/login/client` care returnează lista completă de conturi asociate (`associatedAccounts`). La fiecare ciclu de actualizare, coordinator-ul:

1. Extrage datele contului principal (cel cu care ești logat)
2. Face switch la fiecare cont asociat → extrage datele → switch înapoi

Toate conturile CRM descoperite generează device-uri și senzori proprii, fără intervenție manuală. De exemplu, dacă ai contul principal `1234567` (gaz) și un cont asociat `7654321` (gaz + electricitate), vei avea 3 device-uri:
- Nova Power & Gas (1234567) Gaz
- Nova Power & Gas (7654321) Gaz
- Nova Power & Gas (7654321) Energie Electrică

---

## Ce senzori primesc per cont?

[↑ Înapoi la cuprins](#top)

Pentru fiecare cont CRM și fiecare utilitate (gaz / electricitate), se creează:

**Senzori per utilitate** (sub fiecare device):
- **Sold total** — suma în RON
- **Citire permisă** — Da / Nu
- **Arhivă facturi** — nr facturi pe anul curent, cu sume în atribute
- **Arhivă plăți** — nr plăți pe anul curent, cu sume în atribute
- **Date contract** — status (Activ / Inactiv), cu detalii contract în atribute
- **Convenție consum** — nr luni cu convenție, cu valori per lună în atribute
- **Factură restantă** — Da / Nu, cu total restantă în atribute

**Senzori per contor** (per meter series):
- **Index contor** — valoarea indexului curent (m³ / kWh), cu ultima citire și consum în atribute

**Senzori condiționali**:
- **Sold prosumator** — apare doar dacă există contracte prosumator
- **Revizie tehnică** — apare doar pentru utilitatea gaz (Validă / Expirată / Nedefinit)

**Buton**:
- **Trimite index** — un buton per contor, trimite autocitirea la API

---

## Ce înseamnă „Sold total"?

[↑ Înapoi la cuprins](#top)

Senzorul „Sold total" (`sensor.vreaulanova_{crm}_{ut}_sold_total`) afișează suma în RON pe care o ai de plătit sau credit pe care îl ai. Valoarea vine de la endpoint-ul `/balances` (câmpul `balance`).

Este un senzor cu device_class `monetary` și state_class `total`, deci poate fi folosit în statistici și grafice HA.

---

## Ce înseamnă senzorul „Citire permisă"?

[↑ Înapoi la cuprins](#top)

Senzorul „Citire permisă" (`sensor.vreaulanova_{crm}_{ut}_citire_permisa`) indică dacă trimiterea autocitirilor este activă pe platforma Nova. Valoarea vine din `app_info.selfReadingsEnabled` — un flag global setat de Nova.

- **Da** — autocitirile sunt acceptate
- **Nu** — autocitirile sunt dezactivate de Nova (temporar sau permanent)

**Observație**: Spre deosebire de E·ON (unde citirea permisă depinde de perioada de citire per contract), la Nova acest indicator este global — nu per punct de măsurare.

---

## Nu îmi apare indexul curent. De ce?

[↑ Înapoi la cuprins](#top)

Indexul curent vine de la endpoint-ul `/metering-points` și depinde de ce returnează API-ul Nova. Dacă senzorul afișează `None` sau nu are valoare:

1. Verifică atributele senzorului — ar trebui să vezi „Ultima citire", „Consum", „Data ultima citire", „Index vechi"
2. Dacă atributele sunt toate `None`, API-ul Nova nu furnizează date de contor pentru acel punct de măsurare
3. Activează debug logging ([DEBUG.md](DEBUG.md)) și verifică răspunsul endpoint-ului `metering_points`

Dacă ești client nou sau contorul nu a fost citit niciodată, e posibil ca API-ul să nu aibă date.

---

## Ce înseamnă senzorul „Factură restantă"?

[↑ Înapoi la cuprins](#top)

Senzorul „Factură restantă" (`sensor.vreaulanova_{crm}_{ut}_factura_restanta`) indică dacă ai facturi neachitate:

- **Da** — ai facturi cu status `unpaid` sau `pastDue`
- **Nu** — toate facturile sunt achitate

Atribute disponibile:
- **Total restantă** — suma totală neachitată (RON)
- **Scadență ultima factură** — data scadenței celei mai recente facturi
- **Facturi neachitate** — numărul de facturi neachitate

---

## Ce înseamnă senzorul „Revizie tehnică"?

[↑ Înapoi la cuprins](#top)

Senzorul „Revizie tehnică" (`sensor.vreaulanova_{crm}_gaz_revizie_tehnica`) apare doar pentru utilitatea gaz și arată starea reviziei tehnice a instalației:

- **Validă** — revizia tehnică nu a expirat (data expirării este în viitor)
- **Expirată** — revizia tehnică a expirat (data expirării este în trecut)
- **Nedefinit** — nu există date despre revizie în API

Atribute:
- Data ultimei revizii, Data următoarei revizii
- Data ultimei verificări, Data următoarei verificări

---

## Nu sunt prosumator. Senzorul de prosumator lipsește — e normal?

[↑ Înapoi la cuprins](#top)

Da, absolut normal. Senzorul „Sold prosumator" se creează doar dacă în contractele returnate de API există cel puțin un contract cu `prosumerContract = true`. Dacă nu ești prosumator, senzorul pur și simplu nu este creat — nu e o eroare.

---

## De ce entitățile au un nume lung, cu codul CRM inclus?

[↑ Înapoi la cuprins](#top)

Integrarea setează manual `entity_id`-ul fiecărei entități, incluzând codul CRM, utilitatea și (pentru index) seria contorului. Formatul general este:

- `sensor.vreaulanova_{crm}_{utilitate}_{tip_senzor}`
- `button.vreaulanova_{crm}_{utilitate}_trimite_index`

De exemplu, pentru un cont CRM `1234567` cu utilitate gaz:
- `sensor.vreaulanova_1234567_gaz_sold_total`
- `sensor.vreaulanova_1234567_gaz_date_contract`
- `sensor.vreaulanova_1234567_gaz_factura_restanta`
- `button.vreaulanova_1234567_gaz_trimite_index`

Avantajul principal: dacă ai mai multe conturi CRM cu mai multe utilități, fiecare entitate are un ID unic, fără conflicte.

---

## Vreau să trimit indexul automat. De ce am nevoie?

[↑ Înapoi la cuprins](#top)

Două lucruri:

**1. Entitate `input_number`** — Butonul de trimitere citește valoarea din:
```
input_number.vreaulanova_{clc_pod}_{series}_index
```
Această entitate trebuie creată manual în `configuration.yaml`. Valorile `clc_pod` (specificIdForUtilityType) și `series` (seria contorului) le găsești în logurile de debug sau în atributele senzorilor.

**2. Citire permisă = Da** — API-ul Nova trebuie să accepte autocitiri (`selfReadingsEnabled = true`).

Exemplu de automatizare:

```yaml
alias: "GAZ: Transmitere index automat Nova"
description: >-
  Trimite autocitirea în ziua 9 a fiecărei luni la ora 12:00.
triggers:
  - trigger: time
    at: "12:00:00"
conditions:
  - condition: template
    value_template: "{{ now().day == 9 }}"
  - condition: state
    entity_id: sensor.vreaulanova_1234567_gaz_citire_permisa
    state: "Da"
actions:
  - action: button.press
    target:
      entity_id: button.vreaulanova_1234567_gaz_trimite_index
```

> **⚠️ Important:** Înlocuiește `1234567` cu codul tău CRM real. Entity_id-urile exacte le găsești în **Setări** → **Dispozitive și Servicii** → **Nova Power & Gas**.

---

## Ce e licența și de ce am nevoie de ea?

[↑ Înapoi la cuprins](#top)

Integrarea folosește un sistem de licențiere server-side (v3.3) cu semnături Ed25519 și HMAC-SHA256. Fără o licență validă, integrarea afișează doar senzorul „Licență necesară" și nu creează senzori sau butoane funcționale.

Licența se achiziționează de la: [hubinteligent.org/donate?ref=vreaulanova](https://hubinteligent.org/donate?ref=vreaulanova)

După achiziție, introdu cheia de licență din OptionsFlow:
1. **Setări** → **Dispozitive și Servicii** → **Nova Power & Gas** → **Configurare**
2. Completează câmpul „Cheie licență"
3. Salvează

Licența este validată automat cu serverul. Există un grace period în caz de probleme temporare de conectivitate.

---

## Am introdus licența dar senzorii tot arată „Licență necesară". De ce?

[↑ Înapoi la cuprins](#top)

Câteva cauze posibile:

1. **Licența nu a fost validată** — verifică logurile pentru mesaje cu `license` sau `licenta`
2. **Serverul de licențe nu este accesibil** — dacă HA nu are acces la internet, validarea eșuează
3. **Cheie greșită** — verifică că ai copiat cheia corect, fără spații suplimentare
4. **Restartare necesară** — în rare cazuri, un restart al HA poate rezolva problema

Activează debug logging ([DEBUG.md](DEBUG.md)) și caută mesaje legate de licență pentru a diagnostica problema exactă.

---

## Am schimbat opțiunile integrării. Trebuie să restartez?

[↑ Înapoi la cuprins](#top)

Nu. Integrarea se reîncarcă automat când salvezi modificările din OptionsFlow. Nu este necesar un restart manual al Home Assistant.

De asemenea, dacă modifici credențialele (email, parolă) din opțiuni, integrarea validează autentificarea înainte de a salva — dacă noile date sunt greșite, vei primi o eroare și configurația existentă rămâne neschimbată.

---

## Trebuie să șterg și readaug integrarea la actualizare?

[↑ Înapoi la cuprins](#top)

De regulă nu. Setările sunt stocate în baza de date HA, nu în fișiere. Actualizarea suprascrie doar codul. Restartează Home Assistant după actualizare și integrarea continuă cu aceleași setări.

---

## Îmi place proiectul. Cum pot să-l susțin?

[↑ Înapoi la cuprins](#top)

- ⭐ Oferă un **star** pe [GitHub](https://github.com/cnecrea/vreaulanova/)
- 🐛 **Raportează probleme** — deschide un [issue](https://github.com/cnecrea/vreaulanova/issues)
- 🔀 **Contribuie cu cod** — trimite un pull request
- ☕ **Donează** prin [Buy Me a Coffee](https://buymeacoffee.com/cnecrea)
- 📢 **Distribuie** proiectul prietenilor sau comunității tale
