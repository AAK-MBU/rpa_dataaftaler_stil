"""STIL tilslutning API + Selenium helpers.

Robotten er *attended*: Et Chrome-vindue åbnes, og brugeren logger selv ind i
STIL via den lokale IdP fra ``config.get_login_organisation()``. Efter login høstes sessionens cookies én gang,
og resten af flowet kører som ``requests``-kald på én fast :class:`Session`.

Hvilken institution kaldene gælder, er tilstand på serveren: Den skiftes med
:func:`switch_organisation`, hvorefter :func:`get_data` og :func:`update_status`
virker på den valgte institution. Kaldene skal derfor køre sekventielt på samme
session.

Endpoints der ikke er sat i :mod:`helpers.config` (``None``), rejser
``NotImplementedError`` ved brug.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from requests import Session
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from helpers import config
from helpers.exceptions import ResponseError

if TYPE_CHECKING:
    from requests import Response

    from helpers.reporting import ProgressReporter

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Generic helpers
# ----------------------------------------------------------------------------
def flatten_dict(d: dict, parent_key: str = "", sep: str = "_") -> dict:
    """Flatten a nested dictionary into a single level using ``sep`` joined keys."""
    items: dict = {}
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def _require_url(url: str | None, name: str) -> str:
    """Returnér ``url`` eller rejs ``NotImplementedError`` hvis den ikke er sat."""
    if not url:
        raise NotImplementedError(
            f"STIL-endpoint '{name}' er ikke konfigureret endnu (helpers/config.py)."
        )
    return url


def _check_response(resp: Response, message: str) -> None:
    """Log ``message`` og rejs :class:`ResponseError` hvis kaldet ikke gav 2xx."""
    if not 200 <= resp.status_code < 300:  # noqa: PLR2004
        logger.error(message)
        raise ResponseError(resp)


# ----------------------------------------------------------------------------
# Organisation lookups
# ----------------------------------------------------------------------------
def get_org_dict(session: Session) -> dict:
    """Hent alle institutioner og dagtilbud, som brugeren har adgang til.

    Datakilde: GET ``config.STIL_ORGANISATIONER_URL``. Svaret er en liste af
    organisationsobjekter med nøglerne ``kode``, ``navn``, ``cvr``, ``pnr``,
    ``type``, ``erPassiveret`` og ``passiveretKommentar``. Kun typerne i
    ``config.STIL_ORG_TYPES`` medtages.

    Returns:
        dict: Organisationsobjekter fra STIL nøglet på institutionsnummer
        (``kode``).
    """
    resp = session.get(config.STIL_ORGANISATIONER_URL, timeout=config.REQUEST_TIMEOUT)
    _check_response(resp, "Fejl ved hentning af organisationer")
    return {
        org["kode"]: org
        for org in resp.json()
        if org.get("type") in config.STIL_ORG_TYPES
    }


def get_switch_payload(org_num: str, org_dict: dict) -> dict:
    """Byg payload til skift-organisation for institutionsnummeret ``org_num``.

    Returns:
        dict: ``{"orgNr": <kode>}``.

    Raises:
        KeyError: Hvis ``org_num`` ikke findes i ``org_dict``.
    """
    if org_num not in org_dict:
        raise KeyError(f"Organisation {org_num} findes ikke i organisationslisten")
    return {"orgNr": org_dict[org_num]["kode"]}


# ----------------------------------------------------------------------------
# Selenium login
# ----------------------------------------------------------------------------
def switch_to_new_tab(browser: webdriver.Chrome) -> None:
    """Switch to the second browser tab if one was opened."""
    if len(browser.window_handles) > 1:
        browser.switch_to.window(browser.window_handles[1])


def open_stil_connection(reporter: ProgressReporter | None = None) -> webdriver.Chrome:
    """Open STIL in Chrome and wait for the user to complete the manual login.

    Returns the live Chrome webdriver once login has succeeded. Raises on timeout
    or missing elements (after closing the browser).

    Once login is done the browser is minimised and ``reporter.focus()`` is called
    so the GUI returns to the foreground while the automated work runs.
    """
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("log-level=3")
    browser = webdriver.Chrome(options=chrome_options)
    browser.maximize_window()
    browser.get(config.STIL_LOGIN_URL)

    # Load the STIL login page and pre-select the configured Lokal IdP.
    try:
        WebDriverWait(browser, config.LOGIN_PAGE_TIMEOUT).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(@class, 'button-primary')"
                    " and normalize-space()='Log på']",
                )
            )
        ).click()
        WebDriverWait(browser, config.LOGIN_PAGE_TIMEOUT).until(
            EC.element_to_be_clickable((By.ID, "LoginMenuItem_2"))
        ).click()
        switch_to_new_tab(browser)
        WebDriverWait(browser, config.LOGIN_PAGE_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "ddlLocalIdPOrganization-input"))
        ).send_keys(config.get_login_organisation())

        browser.find_element(By.ID, "ddlLocalIdPOrganization-input").click()
        browser.find_element(By.ID, "btnSubmit").click()
    except WebDriverException as e:
        # Covers timeouts, missing elements, and a closed/crashed browser.
        logger.exception("STIL-loginsiden kunne ikke indlæses")
        with contextlib.suppress(Exception):
            browser.quit()
        raise TimeoutError(
            "STIL-loginsiden kunne ikke indlæses. Tjek din internetforbindelse "
            "og at STIL er tilgængelig, og prøv igen."
        ) from e

    # Wait for the user to complete the manual MitID login.
    logger.info("Venter på at brugeren logger ind...")
    try:
        # Efter login viser STIL en modal med overskriften "Vælg organisation".
        WebDriverWait(browser, config.LOGIN_USER_TIMEOUT).until(
            EC.text_to_be_present_in_element(
                (
                    By.CSS_SELECTOR,
                    "div.modal-content div.modal-header h2#modal-title",
                ),
                "Vælg organisation",
            )
        )
    except TimeoutException as e:
        minutes = config.LOGIN_USER_TIMEOUT // 60
        logger.exception("Login blev ikke gennemført i tide")
        with contextlib.suppress(Exception):
            browser.quit()
        raise TimeoutError(
            f"Login blev ikke gennemført inden for {minutes} minutter. "
            "Prøv igen, og log ind i STIL når browseren åbner."
        ) from e
    except WebDriverException as e:
        # The user closed the browser window (or it crashed) mid-login.
        logger.exception("Browseren blev lukket eller mistede forbindelsen under login")
        with contextlib.suppress(Exception):
            browser.quit()
        raise RuntimeError(
            "Browseren blev lukket under login. Start igen, og lad browservinduet "
            "stå åbent indtil du er logget ind i STIL."
        ) from e
    logger.info("Login gennemført. Fortsætter...")

    # Login done – get the browser out of the way and bring the GUI back up.
    with contextlib.suppress(Exception):
        browser.minimize_window()
    if reporter is not None:
        reporter.focus()

    return browser


# ----------------------------------------------------------------------------
# Session
# ----------------------------------------------------------------------------
def get_browser_cookie(cookie_name: str, browser: webdriver.Chrome) -> str | None:
    """Return ``name=value`` for a named cookie from the browser, or None."""
    for c in browser.get_cookies():
        if c["name"] == cookie_name:
            return f"{c['name']}={c['value']}"
    return None


def build_session(browser: webdriver.Chrome) -> Session:
    """Byg den faste API-session ud fra browserens login-cookies.

    Cookies i ``config.STIL_SESSION_COOKIES`` sættes i ``Cookie``-headeren, og
    værdien af ``XSRF-TOKEN`` sendes desuden som ``x-xsrf-token``.

    Raises:
        RuntimeError: Hvis en af cookies mangler efter login.
    """
    cookies = {
        name: get_browser_cookie(name, browser) for name in config.STIL_SESSION_COOKIES
    }
    missing = [name for name, value in cookies.items() if value is None]
    if missing:
        raise RuntimeError(
            f"Login-cookies mangler efter login: {', '.join(missing)}. Prøv igen."
        )

    x_xsrf_token = cookies["XSRF-TOKEN"].split("=", maxsplit=1)[-1]

    session = Session()
    session.headers.update(
        {
            "Cookie": ";".join(cookies.values()),
            "x-xsrf-token": x_xsrf_token,
            "accept": "application/json",
            "content-type": "application/json",
        }
    )
    return session


# ----------------------------------------------------------------------------
# Agreement operations
# ----------------------------------------------------------------------------
def switch_organisation(org_num: str, org_dict: dict, session: Session) -> None:
    """Gør ``org_num`` til den aktive institution for ``session``.

    Datakilde: POST ``config.STIL_SKIFT_ORG_URL``. Svaret beskriver brugeren,
    og ``orgResponse.kode`` er den organisation, der nu er aktiv.

    Raises:
        RuntimeError: Hvis STIL svarer med en anden aktiv organisation.
    """
    url = _require_url(config.STIL_SKIFT_ORG_URL, "skift-organisation")
    payload = get_switch_payload(org_num, org_dict)
    resp = session.post(url, json=payload, timeout=config.REQUEST_TIMEOUT)
    _check_response(resp, f"Fejl ved skift til organisation: {org_num}")

    active = (resp.json().get("orgResponse") or {}).get("kode")
    if active != org_num:
        raise RuntimeError(
            f"Skift til organisation {org_num} mislykkedes; STIL angiver {active} "
            "som aktiv organisation."
        )


def get_data(session: Session, org_num: str | None = None) -> dict:
    """Hent dataaftalerne for den aktive institution.

    Datakilde: GET ``config.STIL_DATAAFTALER_URL``, side for side med
    ``config.STIL_DATAAFTALER_PAGE_SIZE`` aftaler pr. side, inklusive slettede.
    Hver side har nøglerne ``antalSider``, ``side``, ``totalAntalHits`` og
    ``resultater``. Et aftaleobjekt har nøglerne ``aftaleId``, ``aftaleStatus``
    (``GODKENDT``, ``VENTER`` eller ``SLETTET``), ``udbyderNavn``,
    ``udbydersystemNavn``, ``udbydersystemId``, ``udbydersystemPassiveret``,
    ``servicekode`` og ``serviceNavn``.

    Returns:
        dict: Aftaleobjekter fra STIL nøglet på
        ``<udbydersystemNavn>_<serviceNavn>_<aftaleStatus>``.
    """
    url = _require_url(config.STIL_DATAAFTALER_URL, "dataaftaler")
    agreements: list[dict] = []
    page = 1
    while True:
        params = {
            "inkluderSlettede": "true",
            "soegning": "",
            "side": page,
            "antalPrSide": config.STIL_DATAAFTALER_PAGE_SIZE,
            "sort": "UDBYDERNAVN",
            "sortDesc": "false",
        }
        resp = session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
        _check_response(
            resp, f"Fejl ved hentning af aftaler for organisation: {org_num}"
        )
        body = resp.json()
        agreements.extend(body.get("resultater") or [])
        if page >= (body.get("antalSider") or 1):
            break
        page += 1

    return {
        f"{agr['udbydersystemNavn']}_{agr['serviceNavn']}_{agr['aftaleStatus']}": agr
        for agr in agreements
        if agr.get("serviceNavn")
    }


def update_status(
    agreement: dict, status: str, session: Session, kommentar: str = ""
) -> Response:
    """Sæt aftalens status til ``status`` (``GODKENDT``, ``VENTER`` eller ``AFVIST``).

    Datakilde: PUT ``config.STIL_DATAAFTALE_URL`` med payload
    ``{"status": <status>, "kommentar": <kommentar>}``.

    Args:
        agreement: Aftaleobjekt fra :func:`get_data` (bruger ``aftaleId`` og
            ``aftaleStatus``).
        status: Den nye status.
        session: Den faste API-session.
        kommentar: Kommentar til statusændringen; tom streng hvis ingen.
    """
    url = config.STIL_DATAAFTALE_URL.format(aftale_id=agreement["aftaleId"])
    logger.info("Ændrer status fra %s til %s", agreement.get("aftaleStatus"), status)
    payload = {"status": status, "kommentar": kommentar}
    resp = session.put(url, json=payload, timeout=config.REQUEST_TIMEOUT)
    _check_response(resp, "Fejl ved ændring af status")
    return resp


def delete_agreement(agreement: dict, session: Session) -> Response:
    """Slet aftalen.

    Datakilde: DELETE ``config.STIL_DATAAFTALE_URL``.

    Args:
        agreement: Aftaleobjekt fra :func:`get_data` (bruger ``aftaleId``).
        session: Den faste API-session.
    """
    url = config.STIL_DATAAFTALE_URL.format(aftale_id=agreement["aftaleId"])
    logger.info("Sletter aftale %s", agreement["aftaleId"])
    resp = session.delete(url, timeout=config.REQUEST_TIMEOUT)
    _check_response(resp, "Fejl ved sletning af aftale")
    return resp


def get_status(reference: str) -> str | None:
    """Convert a reference prefix (``Godkend_...``) to the STIL API status value."""
    return config.SET_STATUS_MAP.get(reference.split("_", maxsplit=1)[0])
