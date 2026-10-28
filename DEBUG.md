# Depanare — Nova Power & Gas

Pentru majoritatea problemelor ajunge **diagnosticul** (fără date personale). Jurnalul de depanare e util când trebuie urmărit pas cu pas ce se întâmplă.

---

## Diagnosticul

Pagina integrării (**Setări** → **Dispozitive și servicii** → **Nova Power & Gas**) → **⋮** → **Descarcă diagnosticul**.

Conține:

- versiunea integrării și a Home Assistant, starea licenței (cheia mascată);
- conexiunea la Nova: token valid, câte zile mai e valabil, conturi asociate;
- ultima actualizare: reușită sau nu, ultima eroare, câte actualizări au rulat;
- perioada de autocitire (deschisă / închisă) și numărul de anunțuri Nova;
- pe fiecare cont și loc de consum: activ sau nu (CLC/POD), contoare (reale sau reconstruite din istoric), facturi pe status, plăți, autocitiri, convenție, revizii, raportul de consum;
- locurile fără CLC/POD ignorate;
- entitățile integrării și starea lor (activă / indisponibilă / dezactivată / **orfană**);
- dacă există helperii `input_number` de care are nevoie butonul „Trimite index".

Nu conține sume, indexuri, adrese, nume, email-uri sau tokenuri. Numărul contului, numerele LC și codurile CLC/POD apar doar cu ultimele cifre (`x2600`). Se poate atașa direct la un issue.

---

## Jurnalul de depanare

### Activare

Cel mai simplu: pagina integrării → **⋮** → **Activează jurnalizarea de depanare**. Reproduci problema, apoi **Dezactivează jurnalizarea de depanare** — Home Assistant descarcă fișierul cu jurnalul.

Sau permanent, în `configuration.yaml` (apoi repornire):

```yaml
logger:
  default: warning
  logs:
    custom_components.vreaulanova: debug
```

Toate mesajele integrării încep cu `[VreauLaNova]`. Le găsești în **Setări** → **Sistem** → **Jurnale** (caută `vreaulanova`) sau în `config/home-assistant.log`.

### O actualizare normală

```
INFO  [VreauLaNova] Login reușit pentru i*********u@yahoo.com: cont 1234567, conturi asociate 0, token valabil 30 zile
DEBUG [VreauLaNova] Actualizare #0 (completă: + plăți, revizii, raport consum)
DEBUG [VreauLaNova] GET /system/info → 200 (0.12s)
DEBUG [VreauLaNova] GET /metering-points → 200 (0.31s)
DEBUG [VreauLaNova] GET /invoices → 200 (0.42s)
DEBUG [VreauLaNova] GET /dashboard/balance → 200 (0.10s)
DEBUG [VreauLaNova] GET /self-readings → 200 (0.38s)
DEBUG [VreauLaNova] GET /contracts → 200 (0.09s)
DEBUG [VreauLaNova] Cont 1234567: 1 loc(uri) fără CLC/POD ignorate (fără senzori): LC-00199881
…
DEBUG [VreauLaNova] GET /reports/consumption-costs → 200 (0.11s)
DEBUG [VreauLaNova] Cont 1234567 · LC-00202600 (gas): activ (CLC/POD) · contoare 1 (din istoric) · facturi 10 · autocitiri 10 · convenție da · revizii 2 · raport consum da
DEBUG [VreauLaNova] Cont 1234567: 1 locuri, 10 facturi, 10 plăți, 10 autocitiri, 1 contracte, sold 0 lei
DEBUG [VreauLaNova] Actualizare #0 terminată: 1 conturi, 1 locuri de consum, sold total 0.00 lei, autocitire închisă (Puteți trimite consumul doar în intervalul calendaristic 19-26)
```

- **Actualizare completă** (la fiecare a 6-a, ≈ 6 ore): în plus plățile, reviziile de gaz și raportul de consum. Celelalte sunt **rapide**.
- **contoare 1 (din istoric)**: în afara perioadei de citire Nova nu trimite contoarele, iar integrarea le reconstruiește din ultima autocitire. În perioada de citire apar fără „(din istoric)".

### Ce înseamnă mesajele

| Mesaj | Ce înseamnă | Ce faci |
|---|---|---|
| `Login eșuat pentru …: HTTP 401 — …` | Nova a respins emailul sau parola | Home Assistant îți cere parola nouă; o poți schimba și din **Configurare** → **Setări cont** |
| `Login: Nova nu răspunde (…)` | rețea sau Nova indisponibil | nimic — se reîncearcă automat |
| `GET … → HTTP 404` la **toate** cererile | Nova a schimbat adresa API (ca în octombrie 2026) | actualizează integrarea; dacă ești la zi, deschide un issue |
| `… → 401 — re-login și reîncercare` | Nova a invalidat tokenul | nimic — se reconectează singur |
| `… nu a putut fi citit (cont …): …` | o parte din date nu a răspuns | nimic, dacă e ocazional — se păstrează valorile anterioare |
| `… loc(uri) fără CLC/POD ignorate` | loc vechi sau neactivat la Nova | nimic — nu primește senzori |
| `Locul … nu are cod CLC/POD la Nova — device-ul … au fost scoase` | curățarea device-urilor create de versiunile 1.x | nimic — apare o singură dată |
| `Locuri sau contoare noi: … — integrarea se reîncarcă` | a apărut un loc activ sau un contor nou | nimic — entitățile lui se creează automat |
| `Licență invalidă — se omit apelurile API` | licența a expirat sau lipsește | **Configurare** → **Licență** |

### Trimiterea indexului

Fiecare apăsare a butonului apare în jurnal, cu același text ca notificarea:

```
DEBUG   [VreauLaNova] Trimite index LC-00202600: apăsat (cont 1234567)
INFO    [VreauLaNova] Trimite index LC-00202600: cont 1234567, serie ABC/12345678/2021, index nou 1234 (index curent 1200)
INFO    [VreauLaNova] Trimite index LC-00202600: Indexul **1234 m³** a fost trimis pentru gaz, contor ABC/12345678/2021, …
```

Un refuz apare ca `WARNING … Trimite index LC-…: <motiv>` — perioada închisă, helper lipsă sau mesajul Nova.

---

## Raportarea unei probleme

Deschide un [issue](https://github.com/cnecrea/vreaulanova/issues) cu:

1. ce ai făcut, ce te așteptai să se întâmple și ce s-a întâmplat;
2. **diagnosticul** (fișierul descărcat, așa cum e);
3. dacă ți se cere, jurnalul de depanare — doar liniile cu `vreaulanova`, între trei backtick-uri (```).

Emailul e mascat în jurnal, dar jurnalul conține numărul contului, numerele locurilor de consum, codul CLC/POD (în ID-ul helperului) și seria contorului. Înlocuiește-le înainte de a-l posta public.
