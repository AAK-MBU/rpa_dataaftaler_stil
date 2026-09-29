"""STIL tilslutning API + Selenium helpers.

Robotten er *attended*: Et Chrome-vindue åbnes, og brugeren logger selv ind i
STIL (Aarhus Kommune Lokal IdP). Efter login høstes sessionens cookies én gang,
og resten af flowet kører som ``requests``-kald på én fast :class:`Session`.

Hvilken institution kaldene gælder, er tilstand på serveren: Den skiftes med
:func:`switch_organisation`, hvorefter :func:`get_data` og :func:`update_status`
virker på den valgte institution. Kaldene skal derfor køre sekventielt på samme
session.

Endpoints der endnu ikke er fastlagt i :mod:`helpers.config` (``None``), rejser
``NotImplementedError`` ved brug. Steder hvor payload eller svarstruktur skal
bekræftes, er markeret med ``TODO(HAR)``.
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

HTTP_OK = 200


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
    """Log ``message`` og rejs :class:`ResponseError` hvis kaldet ikke gav 200."""
    if resp.status_code != HTTP_OK:
        logger.error(message)
        raise ResponseError(resp)


# ----------------------------------------------------------------------------
# Organisation lookups
# ----------------------------------------------------------------------------
def get_org_dict(session: Session) -> dict:
    """Hent alle institutioner og dagtilbud, som brugeren har adgang til.

    Datakilde: GET ``config.STIL_ORGANISATIONER_URL``.

    Returns:
        dict: Organisationsobjekter fra STIL nøglet på institutionsnummer
        (``kode``).
    """
    resp = session.get(config.STIL_ORGANISATIONER_URL, timeout=config.REQUEST_TIMEOUT)
    _check_response(resp, "Fejl ved hentning af organisationer")
    orgs = resp.json()
    # TODO(HAR): bekræft svarets struktur (grupper og navnet på nøglefeltet).
    return {
        org["kode"]: org
        for group in ("institutioner", "dagtilbud")
        for org in orgs.get(group, [])
    }


def get_switch_payload(org_num: str, org_dict: dict) -> dict:
    """Byg payload til skift-organisation for institutionsnummeret ``org_num``.

    Raises:
        KeyError: Hvis ``org_num`` ikke findes i ``org_dict``.
    """
    if org_num not in org_dict:
        raise KeyError(f"Organisation {org_num} findes ikke i organisationslisten")
    # TODO(HAR): bekræft payload – hele organisationsobjektet eller kun nummeret.
    return org_dict[org_num]


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

    # Load the STIL login page and pre-select the Aarhus Kommune Lokal IdP.
    try:
        WebDriverWait(browser, config.LOGIN_PAGE_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "LoginMenuItem_2"))
        ).click()
        switch_to_new_tab(browser)
        WebDriverWait(browser, config.LOGIN_PAGE_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "ddlLocalIdPOrganization-input"))
        ).send_keys(config.LOGIN_ORGANISATION)

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
        WebDriverWait(browser, config.LOGIN_USER_TIMEOUT).until(
            EC.element_to_be_clickable((By.ID, "organisation-search"))
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

    Datakilde: POST ``config.STIL_SKIFT_ORG_URL``.
    """
    url = _require_url(config.STIL_SKIFT_ORG_URL, "skift-organisation")
    payload = get_switch_payload(org_num, org_dict)
    resp = session.post(url, json=payload, timeout=config.REQUEST_TIMEOUT)
    # TODO(HAR): hvis svaret angiver den aktive organisation, verificér den her.
    _check_response(resp, f"Fejl ved skift til organisation: {org_num}")


def get_data(session: Session, org_num: str | None = None) -> dict:
    """Hent dataaftalerne for den aktive institution.

    Datakilde: GET ``config.STIL_DATAAFTALER_URL``.

    Returns:
        dict: Aftaleobjekter fra STIL nøglet på
        ``<systemNavn>_<serviceNavn>_<aktuelStatus>``.
    """
    url = _require_url(config.STIL_DATAAFTALER_URL, "dataaftaler")
    resp = session.get(url, timeout=config.REQUEST_TIMEOUT)
    _check_response(resp, f"Fejl ved hentning af aftaler for organisation: {org_num}")

    # TODO(HAR): bekræft feltnavne (udbydersystem.navn, stilService.servicenavn,
    # aktuelStatus, aftaleId) og om svaret er en liste.
    return {
        f"{agr['udbydersystem']['navn']}_{agr['stilService']['servicenavn']}_{agr['aktuelStatus']}": agr
        for agr in resp.json()
        if agr["stilService"] is not None
    }


def update_status(agreement: dict, status: str, session: Session) -> Response:
    """Sæt aftalens status til ``status`` (``GODKENDT``, ``VENTER`` eller ``SLETTET``).

    Datakilde: ``config.STIL_OPDATER_STATUS_METHOD`` mod
    ``config.STIL_OPDATER_STATUS_URL``.
    """
    url = _require_url(config.STIL_OPDATER_STATUS_URL, "opdater_status")
    logger.info("Ændrer status fra %s til %s", agreement.get("aktuelStatus"), status)

    # TODO(HAR): bekræft payload, og om sletning også går via dette kald.
    payload = {"aftaleid": agreement["aftaleId"], "status": status, "kommentar": None}
    resp = session.request(
        config.STIL_OPDATER_STATUS_METHOD,
        url,
        json=payload,
        timeout=config.REQUEST_TIMEOUT,
    )
    _check_response(resp, "Fejl ved ændring af status")
    return resp


def get_status(reference: str) -> str | None:
    """Convert a reference prefix (``Godkend_...``) to the STIL API status value."""
    return config.SET_STATUS_MAP.get(reference.split("_", maxsplit=1)[0])
