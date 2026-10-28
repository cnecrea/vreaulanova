<a name="top"></a>
# Întrebări frecvente

- [Integrarea nu mai funcționează („Login eșuat", HTTP 404). Ce fac?](#integrarea-nu-mai-funcționează-login-eșuat-http-404-ce-fac)
- [Am mai multe conturi asociate. Sunt descoperite automat?](#am-mai-multe-conturi-asociate-sunt-descoperite-automat)
- [După actualizare a dispărut un loc de consum. De ce?](#după-actualizare-a-dispărut-un-loc-de-consum-de-ce)
- [Nu îmi apare „Index contor" sau butonul „Trimite index". De ce?](#nu-îmi-apare-index-contor-sau-butonul-trimite-index-de-ce)
- [Ce helper trebuie să creez pentru trimiterea indexului?](#ce-helper-trebuie-să-creez-pentru-trimiterea-indexului)
- [Am apăsat „Trimite index". Cum aflu dacă a mers?](#am-apăsat-trimite-index-cum-aflu-dacă-a-mers)
- [„Citire permisă" arată „Nu", deși Nova a prelungit perioada. De ce?](#citire-permisă-arată-nu-deși-nova-a-prelungit-perioada-de-ce)
- [Ce arată „Consum lunar" și „Cost lunar"?](#ce-arată-consum-lunar-și-cost-lunar)
- [Pot folosi indexul în panoul Energie?](#pot-folosi-indexul-în-panoul-energie)
- [Cum primesc o notificare înainte de scadența facturii?](#cum-primesc-o-notificare-înainte-de-scadența-facturii)
- [Ce înseamnă „Revizie tehnică"?](#ce-înseamnă-revizie-tehnică)
- [Nu am senzorul „Sold prosumator". E normal?](#nu-am-senzorul-sold-prosumator-e-normal)
- [Am introdus licența, dar tot apare „Licență necesară". De ce?](#am-introdus-licența-dar-tot-apare-licență-necesară-de-ce)
- [Trebuie să șterg și să readaug integrarea la actualizare?](#trebuie-să-șterg-și-să-readaug-integrarea-la-actualizare)
- [Cum raportez o problemă?](#cum-raportez-o-problemă)
- [Îmi place proiectul. Cum îl pot susține?](#îmi-place-proiectul-cum-îl-pot-susține)

---

## Integrarea nu mai funcționează („Login eșuat", HTTP 404). Ce fac?

[↑ Înapoi la cuprins](#top)

Actualizează la **2.0.0** sau mai nou. În octombrie 2026, Nova a trecut la o platformă nouă (myaccount.nova-energy.ro), iar vechiul server la care se conectau versiunile 1.x a fost oprit — răspunde cu 404 la orice cerere, inclusiv la login. Parola ta nu are nicio problemă.

După actualizare și repornire, integrarea se conectează singură la platforma nouă, cu aceleași entități și același istoric.

---

## Am mai multe conturi asociate. Sunt descoperite automat?

[↑ Înapoi la cuprins](#top)

Da. La login, Nova trimite lista conturilor asociate; integrarea citește datele fiecăruia și le creează device-urile, fără nicio selecție manuală. Fiecare loc de consum activ devine un device separat, de exemplu:

- Nova Power & Gas (1234567) LC-00202600 Gaz
- Nova Power & Gas (7654321) LC-00123456 Energie Electrică

---

## După actualizare a dispărut un loc de consum. De ce?

[↑ Înapoi la cuprins](#top)

Nova trimite uneori și locuri **fără cod CLC/POD** — locuri vechi sau neactivate, fără contract activ, facturi, contor sau autocitiri. Senzorii lor afișau doar zerouri și „Nedefinit", iar butonul era „Indisponibil". Din 2.0.0 aceste locuri nu mai primesc device; cele create de versiunile anterioare se șterg la prima pornire.

Dacă locul devine activ (primește CLC/POD), integrarea observă la următoarea actualizare și se reîncarcă singură pentru a-l adăuga. Locurile ignorate apar în [diagnostic](DEBUG.md#diagnosticul) la `locuri_inactive_ignorate`.

---

## Nu îmi apare „Index contor" sau butonul „Trimite index". De ce?

[↑ Înapoi la cuprins](#top)

- **Locul nu are CLC/POD** — vezi întrebarea anterioară; nu are contor la Nova.
- **Locul nu are nicio autocitire în istoric** — în afara perioadei de citire Nova nu trimite contoarele; integrarea le reconstruiește din ultima autocitire. Un loc fără nicio autocitire primește senzorul de index când Nova trimite contorul, în perioada de citire (integrarea se reîncarcă singură). Butonul „Trimite index” există oricum pentru orice loc activ.

În afara perioadei de citire, indexul afișat este cel din ultima autocitire (atributul „Sursa indexului" spune de unde vine).

---

## Ce helper trebuie să creez pentru trimiterea indexului?

[↑ Înapoi la cuprins](#top)

ID-ul exact este în atributul **Helper index** al butonului „Trimite index" (sau al senzorului „Index contor"), de exemplu:

```
input_number.vreaulanova_dgsvlrvl12345678_abc_12345678_2021_index
```

Creează un helper **Număr** din **Setări** → **Dispozitive și servicii** → **Ajutoare** și setează-i exact acest **ID entitate**, sau adaugă-l în `configuration.yaml` (vezi [README](README.md#trimiterea-indexului)). ID-ul e scris cu litere mici: „/" și „-" din seria contorului devin „_".

---

## Am apăsat „Trimite index". Cum aflu dacă a mers?

[↑ Înapoi la cuprins](#top)

Rezultatul apare în **notificările din bara laterală** (clopoțelul):

- **index trimis** — valoarea, contorul, locul și ora, plus mesajul Nova;
- **indexul nu a fost trimis** — motivul: perioada de autocitire e închisă (cu intervalul și anunțurile Nova), helperul lipsește sau nu are valoare, sau mesajul cu care Nova a refuzat indexul (de exemplu un index mai mic decât cel curent).

Fiecare loc are o singură notificare, înlocuită la apăsarea următoare.

---

## „Citire permisă" arată „Nu", deși Nova a prelungit perioada. De ce?

[↑ Înapoi la cuprins](#top)

Senzorul se actualizează la intervalul integrării (implicit o oră), deci poate rămâne în urmă puțin timp. Prelungirile apar în atributele lui, ca „Anunț Nova". Butonul **verifică perioada direct la Nova în momentul apăsării**, deci poți trimite indexul chiar dacă senzorul nu s-a actualizat încă.

Perioada de autocitire e stabilită de Nova pentru toată platforma, nu pentru fiecare loc de consum.

---

## Ce arată „Consum lunar" și „Cost lunar"?

[↑ Înapoi la cuprins](#top)

Vin din raportul Nova „consum și costuri" (același din myaccount.nova-energy.ro → Rapoarte):

- **Consum lunar** — consumul ultimei luni care are consum înregistrat (m³ sau kWh); în atribute: media lunară, totalul și fiecare lună din ultimele 12.
- **Cost lunar** — costul ultimei luni facturate (lei), cu aceeași structură.

Ultima lună cu cost poate fi diferită de ultima lună cu consum (raportul Nova poate avea costul unei luni înaintea consumului ei), de aceea fiecare senzor își arată luna în atributul „Luna". Raportul se actualizează la fiecare a 6-a actualizare (≈ 6 ore). Senzorii apar doar pentru locurile pentru care Nova oferă raportul.

---

## Pot folosi indexul în panoul Energie?

[↑ Înapoi la cuprins](#top)

Da. „Index contor" are unitate (m³ / kWh) și tipul potrivit (gaz / energie), deci apare în **Setări** → **Panouri** → **Energie** → **Consum de gaz** (sau electricitate). Indexul se schimbă când Nova înregistrează o citire nouă, deci consumul apare lunar, nu pe ore.

---

## Cum primesc o notificare înainte de scadența facturii?

[↑ Înapoi la cuprins](#top)

„Factură restantă" are atributele **Următoarea scadență** (dată) și **Zile până la scadență** (număr, negativ după scadență). O automatizare completă e în [README](README.md#exemple). Condiția de bază:

```yaml
{{ state_attr('sensor.vreaulanova_1234567_lc00202600_factura_restanta', 'Zile până la scadență') | int(99) <= 3 }}
```

---

## Ce înseamnă „Revizie tehnică"?

[↑ Înapoi la cuprins](#top)

Doar pentru gaz. Starea reviziei tehnice periodice a instalației:

- **Validă** — data următoarei revizii e în viitor;
- **Expirată** — data a trecut;
- **Nedefinit** — Nova nu are date despre revizie.

În atribute: datele ultimei și următoarei revizii și verificări, plus zilele rămase până la fiecare.

---

## Nu am senzorul „Sold prosumator". E normal?

[↑ Înapoi la cuprins](#top)

Da. Senzorul apare doar dacă Nova marchează contul ca prosumator.

---

## Am introdus licența, dar tot apare „Licență necesară". De ce?

[↑ Înapoi la cuprins](#top)

1. **Cheia** — verifică să fie copiată exact, fără spații.
2. **Serverul de licențe** — Home Assistant trebuie să aibă acces la internet; erorile apar în formularul de licență și în jurnal.
3. **Reîncărcare** — după activare integrarea se reîncarcă singură; dacă nu, repornește Home Assistant.

Licența se gestionează din pagina integrării → **Configurare** → **Licență**.

---

## Trebuie să șterg și să readaug integrarea la actualizare?

[↑ Înapoi la cuprins](#top)

Nu. Setările rămân în Home Assistant, iar actualizarea înlocuiește doar codul. Repornește Home Assistant după actualizare. La trecerea de la 1.x la 2.0.0, integrarea face singură un login nou pe platforma Nova.

---

## Cum raportez o problemă?

[↑ Înapoi la cuprins](#top)

Deschide un [issue](https://github.com/cnecrea/vreaulanova/issues) și atașează **diagnosticul** (pagina integrării → **⋮** → **Descarcă diagnosticul**) — nu conține date personale. Dacă ți se cere jurnalul, urmează [DEBUG.md](DEBUG.md).

---

## Îmi place proiectul. Cum îl pot susține?

[↑ Înapoi la cuprins](#top)

- ⭐ un **star** pe [GitHub](https://github.com/cnecrea/vreaulanova/)
- 🐛 [issue-uri](https://github.com/cnecrea/vreaulanova/issues) pentru probleme și idei
- ☕ o cafea pe [Buy Me a Coffee](https://buymeacoffee.com/cnecrea)
