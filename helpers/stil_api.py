"""STIL tilslutning API + Selenium helpers.

Ported from the legacy ``MBU_Databehandlingsaftaler`` robot
(``robot_framework/subprocesses/helper_functions.py``). All
``OrchestratorConnection`` coupling has been removed; logging goes through the
stdlib ``logging`` module and endpoints/timeouts come from :mod:`helpers.config`.

The robot acts as an *attended* automation: a Chrome window is opened and the
user logs in to STIL manually (Aarhus Kommune Lokal IdP). After login we harvest
the auth cookies and drive the rest of the flow through plain ``requests`` calls.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from helpers import config
from helpers.exceptions import ResponseError

if TYPE_CHECKING:
    from requests import Response, Session

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


# ----------------------------------------------------------------------------
# Organisation lookups
# ----------------------------------------------------------------------------
def get_org_dict(session: Session) -> dict:
    """Return a combined dict of institutions and dagtilbud keyed by ``kode``."""
    inst_dict = get_inst_dict(session)
    dag_dict = get_dag_dict(session)
    return inst_dict | dag_dict


def get_inst_dict(session: Session) -> dict:
    """Get dict of institutions keyed by their ``kode``."""
    resp = session.get(config.STIL_ORGANISATIONER_URL, timeout=config.REQUEST_TIMEOUT)
    if resp.status_code != HTTP_OK:
        raise ResponseError(resp)
    inst_json = json.loads(resp.text)
    return {org["kode"]: org for org in inst_json["institutioner"]}


def get_dag_dict(session: Session) -> dict:
    """Get dict of dagtilbud keyed by their ``kode``."""
    resp = session.get(config.STIL_ORGANISATIONER_URL, timeout=config.REQUEST_TIMEOUT)
    if resp.status_code != HTTP_OK:
        raise ResponseError(resp)
    dag_json = json.loads(resp.text)
    return {org["kode"]: org for org in dag_json["dagtilbud"]}


def get_payload(org_num: str, org_dict: dict) -> dict | None:
    """Look up the active-organisation payload for an organisation number."""
    if org_dict is None:
        raise ValueError("No organisation dictionary provided")
    return org_dict.get(org_num)


# ----------------------------------------------------------------------------
# Selenium login
# ----------------------------------------------------------------------------
def switch_to_new_tab(browser: webdriver.Chrome) -> None:
    """Switch to the second browser tab if one was opened."""
    if len(browser.window_handles) > 1:
        browser.switch_to.window(browser.window_handles[1])


def open_stil_connection() -> webdriver.Chrome:
    """Open STIL in Chrome and wait for the user to complete the manual login.

    Returns the live Chrome webdriver once login has succeeded. Raises on timeout
    or missing elements (after closing the browser).
    """
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("log-level=3")
    browser = webdriver.Chrome(options=chrome_options)
    browser.maximize_window()
    browser.get(config.STIL_LOGIN_URL)

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

        logger.info("Waiting for user to login...")
        WebDriverWait(browser, config.LOGIN_USER_TIMEOUT).until(
            EC.element_to_be_clickable((By.ID, "organisation-search"))
        )
        logger.info("Login successful. Continuing...")

    except (TimeoutException, NoSuchElementException):
        logger.exception("Error during login")
        browser.quit()
        raise

    return browser


# ----------------------------------------------------------------------------
# Cookie handling
# ----------------------------------------------------------------------------
def get_browser_cookie(cookie_name: str, browser: webdriver.Chrome) -> str | None:
    """Return ``name=value`` for a named cookie from the browser, or None."""
    for c in browser.get_cookies():
        if c["name"] == cookie_name:
            return f"{c['name']}={c['value']}"
    return None


def get_base_cookies(browser: webdriver.Chrome) -> tuple[str, str]:
    """Return the base cookie string and the x-xsrf-token used for all calls."""
    base_cookie = ""
    for cookie_name in ["persistence-cookie", "SESSION", "XSRF-TOKEN"]:
        base_cookie += get_browser_cookie(cookie_name, browser) + ";"
    x_xsrf_token = get_browser_cookie("XSRF-TOKEN", browser).split("=", maxsplit=1)[-1]
    return base_cookie, x_xsrf_token


def get_request_cookie(cookie_name: str, response: Response) -> str | None:
    """Return ``name=value;`` for a named cookie from a requests response, or None."""
    for c in response.cookies:
        if c.name == cookie_name:
            return f"{c.name}={c.value};"
    return None


# ----------------------------------------------------------------------------
# Agreement operations
# ----------------------------------------------------------------------------
def get_org(org_num: str, org_dict: dict, session: Session) -> Response:
    """Activate the organisation for ``org_num`` so its agreements can be read."""
    payload = get_payload(org_num, org_dict)
    resp = session.post(
        config.STIL_ACTIVE_ORG_URL,
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "Accept": "*/*",
        },
        data=json.dumps(payload),
        timeout=config.REQUEST_TIMEOUT,
    )
    if resp.status_code != HTTP_OK:
        logger.error("Error fetching organisation: %s", org_num)
        raise ResponseError(resp)
    return resp


def get_data(session: Session, org_num: str | None = None) -> dict:
    """Retrieve the data agreements for the currently active organisation.

    Returns a dict keyed by ``<systemNavn>_<serviceNavn>_<aktuelStatus>``.
    """
    resp = session.get(config.STIL_HENT_ADGANG_URL, timeout=config.REQUEST_TIMEOUT)
    if resp.status_code != HTTP_OK:
        logger.error("Error while accessing data for organisation: %s", org_num)
        raise ResponseError(resp)

    data_access_json = json.loads(resp.text)
    return {
        f"{agr['udbydersystem']['navn']}_{agr['stilService']['servicenavn']}_{agr['aktuelStatus']}": agr
        for agr in data_access_json
        if agr["stilService"] is not None
    }


def delete_agreement(agreement: dict, session: Session) -> Response:
    """Delete the given agreement in STIL."""
    agreement_id = agreement["aftaleId"]
    resp = session.delete(
        f"{config.STIL_SLET_ADGANG_URL}/{agreement_id}",
        timeout=config.REQUEST_TIMEOUT,
    )
    if resp.status_code != HTTP_OK:
        logger.error("Error when deleting agreement: %s", resp)
        raise ResponseError(resp)
    return resp


def change_status(reference: str, agreement: dict, session: Session) -> Response:
    """Change the status of an agreement based on the reference prefix."""
    set_status = get_status(reference)
    if set_status is None:
        raise ValueError(
            f"reference status: {reference.split('_', maxsplit=1)[0]} does not match any of "
            "'Godkend', 'Vent', or 'Slet'"
        )

    logger.info(
        "Setting status from %s to %s", agreement.get("aktuelStatus"), set_status
    )

    payload = json.dumps(
        {"aftaleid": agreement["aftaleId"], "status": set_status, "kommentar": None}
    )
    resp = session.post(
        config.STIL_SET_STATUS_URL,
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "Accept": "*/*",
        },
        data=payload,
        timeout=config.REQUEST_TIMEOUT,
    )
    if resp.status_code != HTTP_OK:
        logger.error("Error while changing status")
        raise ResponseError(resp)
    return resp


def get_status(reference: str) -> str | None:
    """Convert a reference prefix (``Godkend_...``) to the STIL API status value."""
    return config.SET_STATUS_MAP.get(reference.split("_", maxsplit=1)[0])
