"""Application startup / shutdown for the STIL Dataaftaler process.

``startup()`` opens Chrome, waits for the manual STIL login, builds the fixed
API session from the login cookies and fetches the organisation lookup. It all
lives in a global :class:`AppContext` (retrievable via :func:`get_app`), which
both the overview and ``process_item`` use.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from helpers.reporting import NullReporter, ProgressReporter
from helpers.stil_api import (
    build_session,
    get_org_dict,
    open_stil_connection,
    switch_organisation,
)

if TYPE_CHECKING:
    from requests import Session

logger = logging.getLogger(__name__)

APP: AppContext | None = None


@dataclass
class AppContext:
    """Shared, authenticated state used by every queue item.

    ``active_org`` is the institution most recently selected via
    :meth:`activate`. The selection is server-side state on ``session``.
    """

    browser: object  # selenium webdriver.Chrome
    session: Session
    org_dict: dict = field(default_factory=dict)
    active_org: str | None = None

    def activate(self, org_num: str) -> None:
        """Make ``org_num`` the active institution, skipping the call if it already is."""
        if self.active_org == org_num:
            return
        # Clear first so a failed switch never leaves a stale active_org behind.
        self.active_org = None
        switch_organisation(org_num, self.org_dict, self.session)
        self.active_org = org_num


def get_app() -> AppContext | None:
    """Return the current application context (set by :func:`startup`)."""
    return APP


def startup(reporter: ProgressReporter | None = None) -> AppContext:
    """Open STIL, wait for manual login, and build the shared auth context."""
    reporter = reporter or NullReporter()
    logger.info("Starter applikationer...")
    reporter.phase("Login")
    reporter.log("Åbner STIL i browseren – log venligst ind...")

    browser = open_stil_connection(reporter)

    try:
        session = build_session(browser)
    except Exception:
        browser.quit()
        raise

    # ruff: noqa: PLW0603
    global APP
    # Registered before get_org_dict so close() also quits the browser if it fails.
    APP = AppContext(browser=browser, session=session)

    reporter.log("Henter liste over organisationer...")
    APP.org_dict = get_org_dict(APP.session)
    reporter.log(f"Login fuldført. {len(APP.org_dict)} organisationer indlæst.")
    return APP


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
