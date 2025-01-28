![logo](https://github.com/user-attachments/assets/dcbb160f-adbb-403b-9a0b-bfd650c5ccb9)


# Nova Power & Gas - Integrare pentru Home Assistant 🏠🇷🇴

Această integrare permite monitorizarea detaliată a datelor contractuale disponibile pentru utilizatorii Nova Power & Gas. Se configurează ușor prin interfața grafică și oferă afișarea completă a informațiilor din contul de utilizator.

---

## 🌟 Caracteristici

### Senzor `Date contract`:
  - **🔍 Monitorizare Generală**:
      - Afișează informații detaliate despre utilizator și cont.
  - **📊 Atribute disponibile**:
      - Numele și prenumele
      - Adresa de consum
      - Cod loc de consum (NLC)
      - Operator de distribuție (OD)
      - Tip client


### Senzor `Arhivă index`:
- **📚 Date istorice**:
  - Afișează indexurile lunare pentru fiecare an disponibil.
- **📊 Atribute disponibile**:
  - **An**: Anul pentru care se afișează datele.
  - **Indexuri lunare**: Indexurile consumului pentru fiecare lună.


### Senzor `Arhivă facturi`:
- **📚 Date istorice**:
  - Afișează facturi lunare pentru fiecare an disponibil.
- **📊 Atribute disponibile**:
  - **An**: Anul pentru care se afișează datele.
  - **Facturi lunare**: Totalul plăților efectuate pentru fiecare lună în anul selectat.

---

## ⚙️ Configurare

### 🛠️ Interfața UI:
1. Adaugă integrarea din meniul **Setări > Dispozitive și Servicii > Adaugă Integrare**.
2. Introdu datele contului Nova Power & Gas:
   - **Nume utilizator**: username-ul contului tău Nova Power & Gas.
   - **Parolă**: parola asociată contului tău.
3. Specifică intervalul de actualizare (implicit: 1 oră).

---

## 🚀 Instalare

### 💡 Instalare prin HACS:
1. Adaugă [depozitul personalizat](https://github.com/cnecrea/vreaulanova) în HACS. 🛠️
2. Caută integrarea **Nova Power & Gas** și instaleaz-o. ✅
3. Repornește Home Assistant și configurează integrarea. 🔄

### ✋ Instalare manuală:
1. Clonează sau descarcă [depozitul GitHub](https://github.com/cnecrea/vreaulanova). 📂
2. Copiază folderul `custom_components/vreaulanova` în directorul `custom_components` al Home Assistant. 🗂️
3. Repornește Home Assistant și configurează integrarea. 🔧


---

## ☕ Susține dezvoltatorul

Dacă ți-a plăcut această integrare și vrei să sprijini munca depusă, **invită-mă la o cafea**! 🫶  
Nu costă nimic, iar contribuția ta ajută la dezvoltarea viitoare a proiectului. 🙌  

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Susține%20dezvoltatorul-orange?style=for-the-badge&logo=buy-me-a-coffee)](https://buymeacoffee.com/cnecrea)

Mulțumesc pentru sprijin și apreciez fiecare gest de susținere! 🤗

--- 

## 🧑‍💻 Contribuții

Contribuțiile sunt binevenite! Simte-te liber să trimiți un pull request sau să raportezi probleme [aici](https://github.com/cnecrea/vreaulanova/issues).
