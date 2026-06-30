"""Application startup / shutdown for the STIL Dataaftaler process.

``startup()`` opens Chrome, waits for the manual STIL login, harvests the auth
cookies and builds the organisation lookup, then stashes everything in a global
:class:`AppContext` (retrievable via :func:`get_app`). ``process_item`` reads that
context for every queue element — this mirrors the legacy robot's ``runtime_args``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from requests import Session

from helpers.reporting import NullReporter, ProgressReporter
from helpers.stil_api import (
    get_base_cookies,
    get_browser_cookie,
    get_org_dict,
    open_stil_connection,
)

logger = logging.getLogger(__name__)

APP: AppContext | None = None


@dataclass
class AppContext:
    """Shared, authenticated state used by every queue item."""

    browser: object  # selenium webdriver.Chrome
    base_cookie: str
    x_xsrf_token: str
    cookie_inst_list: str | None
    org_dict: dict = field(default_factory=dict)


def get_app() -> AppContext | None:
    """Return the current application context (set by :func:`startup`)."""
    return APP


def startup(reporter: ProgressReporter | None = None) -> None:
    """Open STIL, wait for manual login, and build the shared auth context."""
    reporter = reporter or NullReporter()
    logger.info("Starter applikationer...")
    reporter.phase("Login")
    reporter.log("Åbner STIL i browseren – log venligst ind...")

    browser = open_stil_connection(reporter)

    base_cookie, x_xsrf_token = get_base_cookies(browser)
    cookie_inst_list = get_browser_cookie("AuthTokenTilslutning", browser)

    session = Session()
    session.headers.update(
        {
            "cookie": f"{base_cookie};{cookie_inst_list}",
            "x-xsrf-token": x_xsrf_token,
            "accept": "application/json",
            "content-type": "application/json",
            "Accept": "*/*",
        }
    )
    reporter.log("Henter liste over organisationer...")
    org_dict = get_org_dict(session)

    # ruff: noqa: PLW0603
    global APP
    APP = AppContext(
        browser=browser,
        base_cookie=base_cookie,
        x_xsrf_token=x_xsrf_token,
        cookie_inst_list=cookie_inst_list,
        org_dict=org_dict,
    )
    reporter.log(f"Login fuldført. {len(org_dict)} organisationer indlæst.")


def soft_close() -> None:
    """Gracefully close the browser."""
    logger.info("Lukker applikationer blødt...")
    if APP is not None and APP.browser is not None:
        APP.browser.quit()


def hard_close() -> None:
    """Forcefully close the browser (best effort)."""
    logger.info("Lukker applikationer hårdt...")
    if APP is not None and APP.browser is not None:
        try:
            APP.browser.quit()
        except Exception:
            logger.exception("Kunne ikke tvangslukke browseren")


def close() -> None:
    """Close applications softly, falling back to a hard close."""
    try:
        soft_close()
    except Exception:
        hard_close()
    finally:
        # ruff: noqa: PLW0603
        global APP
        APP = None


def reset(reporter: ProgressReporter | None = None) -> None:
    """Close and re-open applications to recover from an error."""
    close()
    startup(reporter)
