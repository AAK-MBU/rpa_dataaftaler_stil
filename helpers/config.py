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

# Én dataaftale: PUT opdaterer status og kommentar, DELETE sletter aftalen.
STIL_DATAAFTALE_URL = (
    "https://tilslutning.stil.dk/adm/api/dataejer/dataaftale/{aftale_id}"
)

# Cookies der udgør den faste session efter login.
STIL_SESSION_COOKIES = ("SESSION", "stil_generic_persist", "XSRF-TOKEN")

# Lokal IdP-organisation der vælges på STIL's loginside. Teksten skal svare
# præcis til en linje i listen på loginsiden ("<navn>, <CVR>, <navn>").
# Sættes i opsætningsdialogen som env LOGIN_ORGANISATION.
DEFAULT_LOGIN_ORGANISATION = "Aarhus Kommune, 55133018, Aarhus Kommune"


def get_login_organisation() -> str:
    """Returnér IdP-organisationen fra env ``LOGIN_ORGANISATION`` eller standardværdien."""
    return (os.getenv("LOGIN_ORGANISATION") or "").strip() or DEFAULT_LOGIN_ORGANISATION


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
# GODKENDT, VENTER og AFVIST sættes med PUT; SLETTET betyder at aftalen slettes
# med DELETE.
STATUS_DELETED = "SLETTET"
SET_STATUS_MAP = {
    "Godkend": "GODKENDT",
    "Vent": "VENTER",
    "Afvis": "AFVIST",
    "Slet": STATUS_DELETED,
}

# Excel "statusændring" cell value -> reference prefix used to build queue references.
EXCEL_CHANGE_TO_REFERENCE = {
    "GODKEND": "Godkend",
    "VENT": "Vent",
    "AFVIS": "Afvis",
    "SLET": "Slet",
}

# Valgmulighederne i rullelisten i overbliks-arkets "statusændring"-kolonne.
EXCEL_CHANGE_OPTIONS = tuple(EXCEL_CHANGE_TO_REFERENCE)

# ----------------------
# Filesystem layout
# ----------------------
# CODE_DIR er mappen med koden (repoets rod, eller app\ i en release-zip).
CODE_DIR = Path(__file__).resolve().parent.parent

# En release-zip har strukturen Dataaftaler\<OUTER_LAUNCHER_NAME> + Dataaftaler\app\
# (se .github/workflows/release.yml). INSTALL_DIR er den yderste mappe, når
# programmet kører fra en sådan pakke, ellers None (fx i et git-checkout).
OUTER_LAUNCHER_NAME = "Start Dataaftaler.bat"
INSTALL_DIR: Path | None = (
    CODE_DIR.parent if (CODE_DIR.parent / OUTER_LAUNCHER_NAME).is_file() else None
)

# GitHub-repoet hvis releases programmet opdaterer sig fra (helpers/updater.py).
GITHUB_REPO = "AAK-MBU/rpa_dataaftaler_stil"

# Base directory for input/output files. Overridable via the BASE_DIR env var so the
# desktop user can point it at a shared/synced folder. Defaults to the outer
# install folder of a release, otherwise the code folder.
_DEFAULT_BASE_DIR = INSTALL_DIR or CODE_DIR

# Programmets egne indstillinger (ATS, driftsform, BASE_DIR) ligger i .env i
# kodemappen. Opsætningsdialogen i gui/setup_wizard.py skriver til den.
ENV_PATH = CODE_DIR / ".env"


def get_base_dir() -> Path:
    """Return the configured base directory for files (env BASE_DIR or the default)."""
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
# Driftsform
# ----------------------
# RUN_MODE=ATS: ændringerne lægges i Automation Server-arbejdskøen og behandles
# derfra. RUN_MODE=LOKAL: ændringerne fra overbliks-arket køres direkte uden kø.
RUN_MODE_ATS = "ATS"
RUN_MODE_LOCAL = "LOKAL"
RUN_MODES = (RUN_MODE_ATS, RUN_MODE_LOCAL)


def get_run_mode() -> str | None:
    """Returnér driftsformen fra env ``RUN_MODE``, eller None hvis den ikke er gyldig."""
    mode = (os.getenv("RUN_MODE") or "").strip().upper()
    return mode if mode in RUN_MODES else None


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
