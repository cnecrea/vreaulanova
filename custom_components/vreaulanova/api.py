"""API Manager pentru integrarea Nova Power & Gas."""
from __future__ import annotations

import logging
import json
import requests

from .const import (
    URL_LOGIN,
    URL_LOGIN_VALIDARE,
    URL_LOCURI_CONSUM,
    URL_FACTURI,
    URL_CITIRE_EE,
    URL_CITIRE_GN,
    LOGGER,
)

class NovaPGAPI:
    """
    Clasă care gestionează apelurile către API-ul Nova Power & Gas.
    Folosește un token Bearer obținut în urma logării.
    """

    def __init__(self, email: str, password: str):
        """
        Inițializează clasa cu credențialele de autentificare.
        """
        self._email = email
        self._password = password
        self._token: str | None = None

    def _request(
        self,
        url: str,
        method: str = "GET",
        files: dict | None = None,
        headers: dict | None = None,
        timeout: int = 30,
    ) -> requests.Response | None:
        """
        Metodă internă utilitară pentru a face request-uri (GET/POST).
        - Poate fi extinsă pentru retry logic, logging suplimentar etc.
        """
        try:
            if method.upper() == "POST":
                resp = requests.post(url, files=files, headers=headers, timeout=timeout)
            else:
                resp = requests.get(url, headers=headers, timeout=timeout)
            return resp
        except Exception as err:
            LOGGER.exception(f"Eroare la _request({url}): {err}")
            return None

    def login(self) -> bool:
        """
        Face POST la /account/postLogin și setează token-ul dacă autentificarea reușește.
        Returnează True/False în funcție de succesul autentificării.
        """
        LOGGER.debug("Se încearcă logarea cu email: %s", self._email)

        files = {
            'LoginForm': (None, json.dumps({
                "username": self._email,
                "password": self._password
            }))
        }

        response = self._request(URL_LOGIN, method="POST", files=files)
        if not response:
            LOGGER.error("Nu am primit niciun răspuns la login()")
            return False

        if response.status_code == 200:
            data = response.json()
            token = data.get("data")
            if token:
                self._token = token
                LOGGER.debug("Autentificare reușită. Token obținut: %s...", token[:10])
                return True
            else:
                LOGGER.error("Răspuns neașteptat, nu există token: %s", data)
        else:
            LOGGER.error(
                "Eroare la login. Status code: %s, răspuns: %s",
                response.status_code,
                response.text
            )
        return False

    def validate(self) -> bool:
        """
        Apelează endpoint-ul /default/validate pentru a verifica dacă token-ul este valid.
        Returnează True/False în funcție de validitatea token-ului.
        """
        if not self._token:
            LOGGER.warning("Token inexistent. Apelăm login() mai întâi.")
            return False

        headers = {"Authorization": f"Bearer {self._token}"}
        response = self._request(URL_LOGIN_VALIDARE, headers=headers)
        if not response:
            LOGGER.error("Nu am primit niciun răspuns la validate()")
            return False

        if response.status_code == 200:
            LOGGER.debug("Token validat cu succes.")
            return True
        else:
            LOGGER.error(
                "Eroare la validare. Cod status: %s, răspuns: %s",
                response.status_code,
                response.text
            )
        return False

    def _ensure_valid_token(self) -> bool:
        """
        Metodă internă care se asigură că avem un token valid.
        - Dacă token-ul e None sau validate() eșuează, încearcă relogarea.
        - Returnează True dacă totul e OK, False dacă nu a putut re-obține token valid.
        """
        # Dacă nu există token sau nu e valid, încercăm login.
        if not self._token or not self.validate():
            LOGGER.debug("Tokenul lipsește sau este expirat; încerc login() din nou.")
            if not self.login():
                LOGGER.error("Nu s-a putut obține token valid.")
                return False
        return True

    def fetch_all_data(self) -> dict:
        """
        Metodă "completă" care face login/validare o singură dată
        și întoarce toate datele necesare:
        - locuri_consum
        - facturi
        - citiri_ee
        - citiri_gn
        """
        # Validare unică
        if not self._ensure_valid_token():
            LOGGER.error("Nu s-a putut valida/reobține token-ul.")
            return {}

        # Apoi, apelăm direct metodele *private* (sau pot fi publice)
        # care NU mai apelează _ensure_valid_token().
        data = {}
        data["locuri_consum"] = self._get_locuri_consum()
        data["facturi"] = self._get_facturi()
        data["citiri_ee"] = self._get_citire_ee()
        data["citiri_gn"] = self._get_citire_gn()

        return data

    # Metodele "private" care NU mai apelează _ensure_valid_token().
    # Validarea / login se fac o singură dată în fetch_all_data().
    def _get_locuri_consum(self) -> dict | None:
        if not self._token:
            LOGGER.error("Nu se poate apela _get_locuri_consum() fără token.")
            return None
        headers = {"Authorization": f"Bearer {self._token}"}
        response = self._request(URL_LOCURI_CONSUM, headers=headers)
        if response and response.status_code == 200:
            return response.json()
        LOGGER.error("Eroare la _get_locuri_consum: %s", response.text if response else "no response")
        return None

    def _get_facturi(self) -> dict | None:
        if not self._token:
            LOGGER.error("Nu se poate apela _get_facturi() fără token.")
            return None
        headers = {"Authorization": f"Bearer {self._token}"}
        response = self._request(URL_FACTURI, headers=headers)
        if response and response.status_code == 200:
            return response.json()
        LOGGER.error("Eroare la _get_facturi: %s", response.text if response else "no response")
        return None

    def _get_citire_ee(self) -> list | None:
        if not self._token:
            LOGGER.error("Nu se poate apela _get_citire_ee() fără token.")
            return None
        headers = {"Authorization": f"Bearer {self._token}"}
        response = self._request(URL_CITIRE_EE, headers=headers)
        if response and response.status_code == 200:
            return response.json()
        LOGGER.error("Eroare la _get_citire_ee: %s", response.text if response else "no response")
        return None

    def _get_citire_gn(self) -> list | None:
        if not self._token:
            LOGGER.error("Nu se poate apela _get_citire_gn() fără token.")
            return None
        headers = {"Authorization": f"Bearer {self._token}"}
        response = self._request(URL_CITIRE_GN, headers=headers)
        if response and response.status_code == 200:
            return response.json()
        LOGGER.error("Eroare la _get_citire_gn: %s", response.text if response else "no response")
        return None
