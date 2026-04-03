# Ghid de debugging — Nova Power & Gas

Acest ghid explică cum activezi logarea detaliată, ce mesaje să cauți, și cum interpretezi fiecare situație.

---

## 1. Activează debug logging

Editează `configuration.yaml` și adaugă:

```yaml
logger:
  default: warning
  logs:
    custom_components.vreaulanova: debug
```

Restartează Home Assistant (**Setări** → **Sistem** → **Restart**).

Pentru a reduce zgomotul din loguri, poți adăuga:

```yaml
logger:
  default: warning
  logs:
    custom_components.vreaulanova: debug
    homeassistant.const: critical
    homeassistant.loader: critical
    homeassistant.helpers.frame: critical
```

**Important**: dezactivează debug logging după ce ai rezolvat problema (setează `custom_components.vreaulanova: info` sau șterge blocul). Logarea debug generează mult text și poate conține date personale.

---

## 2. Unde găsești logurile

### Din UI

**Setări** → **Sistem** → **Jurnale** → filtrează după `vreaulanova`

### Din fișier

```bash
# Calea implicită
cat config/home-assistant.log | grep -i vreaulanova

# Doar erorile
grep -E "(ERROR|WARNING).*vreaulanova" config/home-assistant.log

# Ultimele 100 linii
grep -i vreaulanova config/home-assistant.log | tail -100
```

### Din terminal (Docker/HAOS)

```bash
# Docker
docker logs homeassistant 2>&1 | grep -i vreaulanova

# Home Assistant OS (SSH add-on)
ha core logs | grep -i vreaulanova
```

---

## 3. Cum citești logurile API

Fiecare cerere API este etichetată cu un **label descriptiv** între paranteze pătrate. Formatul general:

```
[VreauLaNova] mesaj descriptiv
[LOGIN] Autentificare reușită
[SWITCH] Comutare cont → CRM 7654321
```

### Exemplu de ciclu normal de actualizare (cont unic)

```
[VreauLaNova] Începe actualizarea datelor.
[LOGIN] Token obținut cu succes (expire_at=1743600000).
[VreauLaNova] Fetch cont principal CRM=1234567.
GET https://backend.nova-energy.ro/api/metering-points → 200 OK
GET https://backend.nova-energy.ro/api/invoices → 200 OK
GET https://backend.nova-energy.ro/api/balances → 200 OK
GET https://backend.nova-energy.ro/api/contracts → 200 OK
GET https://backend.nova-energy.ro/api/payments → 200 OK
[VreauLaNova] Actualizare finalizată. Conturi procesate: 1.
```

### Exemplu de ciclu normal de actualizare (multi-account)

```
[VreauLaNova] Începe actualizarea datelor.
[VreauLaNova] Fetch cont principal CRM=1234567 (contul logat).
GET https://backend.nova-energy.ro/api/metering-points → 200 OK
GET https://backend.nova-energy.ro/api/invoices → 200 OK
GET https://backend.nova-energy.ro/api/balances → 200 OK
[SWITCH] Comutare la contul asociat: CRM=7654321 (IOAN POPESCU).
POST https://backend.nova-energy.ro/api/accounts/switch → 200 OK
[VreauLaNova] Fetch cont asociat CRM=7654321.
GET https://backend.nova-energy.ro/api/metering-points → 200 OK
GET https://backend.nova-energy.ro/api/invoices → 200 OK
GET https://backend.nova-energy.ro/api/balances → 200 OK
[SWITCH] Comutare înapoi la contul principal: CRM=1234567.
POST https://backend.nova-energy.ro/api/accounts/switch → 200 OK
[VreauLaNova] Actualizare finalizată. Conturi procesate: 2.
```

### Endpoint-uri și senzori asociați

| Endpoint | Descriere | Senzor asociat |
|----------|-----------|----------------|
| `/accounts/login/client` | Autentificare web (cu associatedAccounts) | — (autentificare) |
| `/accounts/switch` | Comutare între conturi | — (multi-account) |
| `/accounts/me` | Detalii utilizator curent | — (fallback CRM) |
| `/globals/app-info/general` | Info aplicație | Citire permisă |
| `/metering-points` | Puncte de măsurare (contoare, meters, gasRevisions) | Index contor, Revizie tehnică |
| `/metering-points/{id}/consumption-agreements` | Convenție consum | Convenție consum |
| `/self-readings` | Autocitiri istoric | Index contor (atribute) |
| `/self-readings/add` | Trimitere autocitire (POST) | Buton Trimite index |
| `/invoices` | Facturi | Arhivă facturi, Factură restantă |
| `/balances` | Sold total + prosumator | Sold total, Sold prosumator |
| `/contracts` | Contracte per utilitate | Date contract |
| `/payments` | Plăți | Arhivă plăți |

---

## 4. Mesajele de la pornire

La prima pornire a integrării (sau după restart), ar trebui să vezi:

### Cont unic (fără conturi asociate):
```
INFO  [VreauLaNova] Se configurează integrarea vreaulanova (entry_id=01ABC...).
DEBUG [VreauLaNova] Interval actualizare: 3600s, heavy multiplier: 6.
DEBUG [LOGIN] Autentificare reușită. loggedInAccount=1234567, viewedAccount=1234567.
DEBUG [VreauLaNova] Conturi asociate: 0. Se procesează doar contul principal.
DEBUG [VreauLaNova] Fetch cont principal CRM=1234567.
DEBUG [VreauLaNova] Actualizare finalizată. Conturi procesate: 1.
INFO  [VreauLaNova] Se creează 8 senzori pentru 1 conturi.
```

### Multi-account (cu conturi asociate):
```
INFO  [VreauLaNova] Se configurează integrarea vreaulanova (entry_id=01ABC...).
DEBUG [VreauLaNova] Interval actualizare: 3600s, heavy multiplier: 6.
DEBUG [LOGIN] Autentificare reușită. loggedInAccount=1234567, viewedAccount=1234567.
DEBUG [VreauLaNova] Conturi asociate: 1 → ['7654321'].
DEBUG [VreauLaNova] Fetch cont principal CRM=1234567.
DEBUG [SWITCH] Comutare la contul asociat: CRM=7654321.
DEBUG [VreauLaNova] Fetch cont asociat CRM=7654321.
DEBUG [SWITCH] Comutare înapoi la contul principal: CRM=1234567.
DEBUG [VreauLaNova] Actualizare finalizată. Conturi procesate: 2.
INFO  [VreauLaNova] Se creează 19 senzori pentru 2 conturi.
```

---

## 5. Situații normale (nu sunt erori)

### Token reutilizat

```
[LOGIN] Token valid, nu se re-autentifică (expire_at > now).
```

**Cauza**: token-ul JWT nu a expirat încă (validitate 30 zile). Comportament normal.

### Conturi asociate goale

```
[VreauLaNova] Conturi asociate: 0. Se procesează doar contul principal.
```

**Cauza**: contul nu are alte conturi CRM asociate. Integrarea funcționează normal doar cu contul principal.

### Heavy refresh skip

```
[VreauLaNova] Ciclu light (nr. 3/6). Se sare peste plăți.
```

**Cauza**: plățile se actualizează doar la fiecare al 6-lea ciclu (heavy refresh). Ciclurile intermediare sunt „light" — nu interogă endpoint-ul de plăți. Comportament normal pentru a reduce încărcarea API.

### Licență — heartbeat

```
[LICENSE] Heartbeat OK. Licența este validă (expiră: 2027-01-15).
```

**Cauza**: verificarea periodică a licenței cu serverul a reușit. Comportament normal.

### Senzor prosumator necreat

```
[VreauLaNova] Nu există contracte prosumator pentru CRM=1234567. Senzorul sold prosumator nu se creează.
```

**Cauza**: contul nu are contract prosumator. Nu e o eroare.

---

## 6. Situații de eroare

### Autentificare eșuată

```
[LOGIN] Eroare autentificare. Status HTTP=401, Răspuns={"message":"Invalid credentials"}
```

**Cauza**: email sau parolă incorectă.

**Rezolvare**:
1. Verifică credențialele pe platforma [Nova](https://nova-energy.ro/)
2. Reconfigurează integrarea cu credențiale corecte (Setări → Dispozitive și Servicii → Nova Power & Gas → Configurare)

### Eroare de rețea / timeout

```
[VreauLaNova] Eroare la fetch metering_points: ClientConnectorError / TimeoutError
```

**Cauza**: API-ul Nova nu răspunde sau conexiunea HA la internet e întreruptă.

**Rezolvare**:
1. Verifică conexiunea la internet din HA
2. Integrarea reîncearcă automat la următorul ciclu — de obicei se rezolvă singur
3. Dacă persistă, verifică dacă `https://backend.nova-energy.ro` este accesibil

### Switch cont eșuat

```
[SWITCH] Eroare la comutare cont CRM=7654321. Status HTTP=500.
```

**Cauza**: API-ul Nova nu a putut comuta la contul asociat.

**Rezolvare**:
1. Verifică dacă contul asociat mai există pe platforma Nova
2. La următorul ciclu de actualizare, switch-ul se reîncearcă automat
3. Dacă persistă, verifică cu Nova dacă contul asociat este valid

### Licență invalidă

```
[LICENSE] Licența nu este validă. Motiv: expired / invalid_key / server_unreachable.
[VreauLaNova] Licență invalidă — se creează doar LicentaNecesaraSensor.
```

**Cauza**: licența a expirat, cheia este greșită, sau serverul de licențe nu este accesibil.

**Rezolvare**:
1. Verifică cheia de licență în OptionsFlow
2. Dacă a expirat, reînnoiește de la [hubinteligent.org/donate?ref=vreaulanova](https://hubinteligent.org/donate?ref=vreaulanova)
3. Dacă serverul nu e accesibil, există un grace period — licența rămâne validă temporar

### Eroare la trimitere autocitire

```
[VreauLaNova] Eroare la trimitere autocitire: input_number nu există sau are valoare invalidă.
```

sau

```
[VreauLaNova] Autocitire eșuată. Status HTTP=400. Răspuns: {"message":"Self readings are not enabled"}
```

**Cauze posibile**:
1. `input_number` corespunzător nu există — trebuie creat manual (vezi [SETUP.md](SETUP.md))
2. `input_number` are valoare invalidă (0 sau negativă)
3. Autocitirile nu sunt activate pe platforma Nova (`selfReadingsEnabled = false`)
4. Token-ul e invalid și re-autentificarea a eșuat

---

## 7. Logare date API

La nivel debug, integrarea loghează statusul răspunsurilor HTTP:

```
GET https://backend.nova-energy.ro/api/metering-points → 200 OK
GET https://backend.nova-energy.ro/api/invoices → 200 OK
POST https://backend.nova-energy.ro/api/accounts/switch → 200 OK
```

Pentru login, răspunsul complet poate fi logat (include token-ul):

```
[LOGIN] Răspuns: loggedInAccount={accountId=..., accountNumber=1234567, associatedAccounts=[...]}, session={token=eyJ...}
```

**Atenție**: aceste loguri conțin date personale (token-uri, coduri CRM, nume conturi asociate). **Nu le posta public fără a le anonimiza.**

---

## 8. Cum raportezi un bug

1. Activează debug logging (secțiunea 1)
2. Reproduce problema
3. Deschide un [issue pe GitHub](https://github.com/cnecrea/vreaulanova/issues) cu:
   - **Descrierea problemei** — ce ai așteptat vs. ce s-a întâmplat
   - **Logurile relevante** — filtrează după `vreaulanova` și include 20–50 linii relevante
   - **Versiunea HA** — din **Setări** → **Despre**
   - **Versiunea integrării** — din `manifest.json` sau HACS
   - **Tip cont** — cont unic sau multi-account (cu conturi asociate)

### Cum postezi loguri pe GitHub

Folosește blocuri de cod delimitate de 3 backticks:

````
```
2026-04-01 10:15:12 DEBUG custom_components.vreaulanova [VreauLaNova] Fetch cont principal CRM=1234567.
2026-04-01 10:15:13 DEBUG custom_components.vreaulanova GET https://backend.nova-energy.ro/api/metering-points → 200 OK
2026-04-01 10:15:14 ERROR custom_components.vreaulanova [LOGIN] Eroare autentificare. Status HTTP=401
```
````

Dacă logul e foarte lung (peste 50 linii), folosește secțiunea colapsabilă:

````
<details>
<summary>Log complet (click pentru a expanda)</summary>

```
... logul aici ...
```

</details>
````

> **Nu posta parola, token-ul sau date personale în loguri.** Integrarea loghează token-urile în mesajele de login — anonimizează-le înainte de a le posta.
