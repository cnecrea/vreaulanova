
<!-- Adaugă o ancoră la începutul paginii -->
<a name="top"></a>
# Întrebări frecvente
- [Cum să adaug integrarea în Home Assistant?](#cum-să-adaug-integrarea-în-home-assistant)
- [Observ în loguri "Eroare de excepție la login: HTTPSConnectionPool". De ce?](#observ-în-loguri-eroare-de-excepție-la-login-httpsconnectionpool-de-ce)


## Cum să adaug integrarea în Home Assistant?

Pentru a reveni la începutul paginii, [apăsați aici](#top).


**Răspuns:**  
HACS (Home Assistant Community Store) permite instalarea și gestionarea integrărilor, temelor și modulelor personalizate create de comunitate. Urmează pașii de mai jos pentru a adăuga un repository extern în HACS și pentru a instala o integrare:

  - **1.	Asigură-te că HACS este instalat**
      - Verifică dacă HACS este deja instalat în Home Assistant.
      - Navighează la **Setări** > **Dispozitive și servicii** > **Integrări** și caută "HACS".
      - Dacă nu este instalat, urmează ghidul oficial de instalare pentru HACS: [HACS Installation Guide](https://hacs.xyz/docs/use).
   
  - **2. Găsește repository-ul extern**
      - Accesează pagina GitHub a integrării pe care vrei să o adaugi. De exemplu, repository-ul ar putea arăta astfel:  
  `https://github.com/autorul-integarii/nume-integrare`.

  - **3. Adaugă repository-ul în HACS**
      - În Home Assistant, mergi la **HACS** din bara laterală.
      - Apasă pe butonul cu **cele trei puncte** din colțul din dreapta sus și selectează **Repositories**.
      - În secțiunea "Custom repositories", introdu URL-ul repository-ului extern (de exemplu, `https://github.com/autorul-integarii/nume-integrare`).
      - Selectează tipul de repository:
        - **Integration** pentru integrări.
        - **Plugin** pentru module front-end.
        - **Theme** pentru teme.
      - Apasă pe **Add** pentru a adăuga repository-ul.

  - **4. Instalează integrarea**
      - După ce repository-ul a fost adăugat, mergi la **HACS** > **Integrations**.
      - Caută numele integrării pe care tocmai ai adăugat-o.
      - Apasă pe integrare și selectează **Download** sau **Install**.
      - După instalare, Home Assistant îți poate solicita să repornești sistemul. Urmează instrucțiunile pentru a finaliza configurarea.

  - **5. Configurează integrarea**
      - După repornire, mergi la **Setări** > **Dispozitive și servicii** > **Adaugă integrare**.
      - Caută numele integrării instalate și urmează pașii de configurare specifici.

> **Notă:** 
> Asigură-te că Home Assistant și HACS sunt actualizate la cea mai recentă versiune pentru a evita erorile de compatibilitate.

---

## Observ în loguri "Eroare de excepție la login: HTTPSConnectionPool". De ce?

Pentru a reveni la începutul paginii, [apăsați aici](#top).


**Răspuns:**  
Eroarea „Eroare de excepție la login: HTTPSConnectionPool” apare din cauza unei probleme de conexiune între Home Assistant și serverul Nova Power & Gas. Aceasta NU este cauzată de integrare, ci de factori externi. Iată posibilele motive și soluții:

  - **1. Probleme de rețea**
      - Serverul Nova Power & Gas nu poate fi contactat din cauza unei conexiuni instabile.
      - Verifică dacă dispozitivul care rulează Home Assistant are o conexiune la internet.
      - Asigură-te că nicio regulă de firewall nu blochează accesul.

  - **2. Serverul Nova Power & Gas este offline**
      - Este posibil ca serverul să fie temporar indisponibil sau să fie în mentenanță.
      - Încearcă din nou peste câteva ore.

  - **3. Certificat SSL invalid**
      - Serverul API ar putea folosi un certificat SSL expirat sau invalid, ceea ce blochează conexiunea.
      - Aceasta este o problemă de partea furnizorului Nova Power & Gas.


---

### Ce trebuie să faci:
1. Verifică conexiunea la internet și firewall-ul.
2. Încearcă să accesezi manual serverul API pentru a confirma că este disponibil.
3. Dacă problema persistă, contactează furnizorul Nova Power & Gas și informează-i despre eroarea apărută.

Această problemă nu ține de integrarea în Home Assistant, ci de conectivitatea către serverul furnizorului.
