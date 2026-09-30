"""Module for general configurations of the process.

Holds both the ATS framework settings (retry/concurrency) and the
STIL/Dataaftaler-specific constants ported from the legacy
``MBU_Databehandlingsaftaler`` robot.
"""

import os
from pathlib import Path

# ----------------------
# ATS framework settings
# ----------------------
MAX_RETRY = 10

# Queue population settings
MAX_CONCURRENCY = 100  # tune based on backend capacity
MAX_RETRIES = 3  # transient failure retries per item
RETRY_BASE_DELAY = 0.5  # seconds (exponential backoff)

# ----------------------
# HTTP / STIL settings
# ----------------------
REQUEST_TIMEOUT = 10  # seconds

# STIL tilslutning endpoints.
# Endpoints sat til None er endnu ikke fastlagt; kald mod dem rejser
# NotImplementedError (se helpers.stil_api._require_url).
STIL_LOGIN_URL = "https://tilslutning.stil.dk/tilslutning/login"
STIL_ORGANISATIONER_URL = "https://tilslutning.stil.dk/adm/api/bruger/organisationer"
STIL_SKIFT_ORG_URL: str | None = (
    "https://tilslutning.stil.dk/adm/api/bruger/skift-organisation"
)
STIL_DATAAFTALER_URL: str | None = (
    "https://tilslutning.stil.dk/adm/api/dataejer/dataaftale"
)
STIL_DATAAFTALER_PAGE_SIZE = 300  # største sidestørrelse STIL tillader

# Organisationstyper fra organisationer-kaldet, der er dataejere og derfor
# indgår i kørslen. UDBYDER er udeladt.
STIL_ORG_TYPES = ("INSTITUTION", "DAGTILBUD", "RESTINSTITUTION")

# TODO(HAR): opdater_status (endpoint og metode).
STIL_OPDATER_STATUS_URL: str | None = None
STIL_OPDATER_STATUS_METHOD = "POST"  # TODO(HAR): bekræft metode

# Cookies der udgør den faste session efter login.
# TODO(HAR): bekræft cookie-navne (fx om AuthTokenTilslutning stadig indgår).
STIL_SESSION_COOKIES = ("persistence-cookie", "SESSION", "XSRF-TOKEN")

# Aarhus Kommune Lokal IdP organisation string used on the login page
LOGIN_ORGANISATION = "Aarhus Kommune, 55133018, Aarhus Kommune"

# Login flow waits (seconds)
LOGIN_PAGE_TIMEOUT = 60
LOGIN_USER_TIMEOUT = 300  # how long we wait for the user to complete MitID login

# Overview API throttling: pause after this many calls inside the time window
THROTTLE_AFTER_CALLS = 200
THROTTLE_WINDOW_SECONDS = 60
THROTTLE_PAUSE_SECONDS = 30

# ----------------------
# Status mapping
# ----------------------
# Reference prefix (from the queue reference / Excel) -> STIL API status value.
SET_STATUS_MAP = {
    "Godkend": "GODKENDT",
    "Vent": "VENTER",
    "Slet": "SLETTET",
}

# Excel "statusændring" cell value -> reference prefix used to build queue references.
EXCEL_CHANGE_TO_REFERENCE = {
    "GODKEND": "Godkend",
    "VENT": "Vent",
    "SLET": "Slet",
}

# ----------------------
# Filesystem layout
# ----------------------
# Base directory for input/output files. Overridable via the BASE_DIR env var so the
# desktop user can point it at a shared/synced folder. Defaults to the repo root.
_DEFAULT_BASE_DIR = Path(__file__).resolve().parent.parent


def get_base_dir() -> Path:
    """Return the configured base directory for files (env BASE_DIR or repo root)."""
    return Path(os.getenv("BASE_DIR", str(_DEFAULT_BASE_DIR)))


def get_output_dir() -> Path:
    """Return (and create) the Output directory where overviews/logs are written."""
    output_dir = get_base_dir() / "Output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_log_dir() -> Path:
    """Return (and create) the directory where run log files are written."""
    log_dir = get_output_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


# ----------------------
# Automation Server (workqueue) connection
# ----------------------
# Env vars the desktop run needs to reach the Automation Server workqueue. The
# ATS client only validates ATS_URL itself (and with an English message), so we
# check all three up front to give the caseworker one clear Danish message.
REQUIRED_ATS_ENV = ("ATS_URL", "ATS_TOKEN", "ATS_WORKQUEUE_OVERRIDE")


def missing_ats_env() -> list[str]:
    """Return the required ATS env vars that are unset/empty (in declared order)."""
    return [name for name in REQUIRED_ATS_ENV if not os.getenv(name)]


# ----------------------
# Error handling
# ----------------------
# DB-backed error emails are off by default for desktop runs (no RPAConnection
# constants reachable). Set SEND_ERROR_EMAILS=true for headless/AS runs.
SEND_ERROR_EMAILS = os.getenv("SEND_ERROR_EMAILS", "false").lower() == "true"

# ----------------------
# GUI settings
# ----------------------
GUI_POLL_MS = 100  # how often the Tkinter loop drains the worker event queue
