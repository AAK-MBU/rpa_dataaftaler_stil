"""Programmets lokale opsætning: læsning og skrivning af ``.env`` samt genvej.

Opsætningen gemmes i ``config.ENV_PATH`` med nøglerne ``RUN_MODE``,
``BASE_DIR`` og – ved ``RUN_MODE=ATS`` – ``ATS_URL``, ``ATS_TOKEN`` og
``ATS_WORKQUEUE_OVERRIDE``. Øvrige nøgler i filen bevares uændrede.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import set_key

from helpers import config

logger = logging.getLogger(__name__)

PROJECT_DIR = config.ENV_PATH.parent
LAUNCHER_PATH = PROJECT_DIR / "start-dataaftaler.bat"
ICON_PATH = PROJECT_DIR / "app.ico"
SHORTCUT_NAME = "Dataaftaler - STIL.lnk"

# Nøgler som opsætningsdialogen udfylder.
SETTING_KEYS = (
    "RUN_MODE",
    "ATS_URL",
    "ATS_TOKEN",
    "ATS_WORKQUEUE_OVERRIDE",
    "BASE_DIR",
)

_CREATE_NO_WINDOW = 0x08000000  # skjul PowerShell-konsollen på Windows


def is_configured() -> bool:
    """Returnér True hvis driftsformen er valgt og ATS-felterne er udfyldt ved ATS."""
    mode = config.get_run_mode()
    if mode is None:
        return False
    return mode != config.RUN_MODE_ATS or not config.missing_ats_env()


def current_settings() -> dict[str, str]:
    """Returnér de nuværende værdier for ``SETTING_KEYS`` fra miljøet (tom streng hvis ikke sat)."""
    return {key: os.getenv(key, "") for key in SETTING_KEYS}


def save_settings(values: dict[str, str]) -> None:
    """Skriv ``values`` til ``.env`` og til det kørende programs miljø.

    Args:
        values: Nøgler fra ``SETTING_KEYS`` og deres nye værdier. Nøgler der
            ikke er med, røres ikke.
    """
    config.ENV_PATH.touch(exist_ok=True)
    for key, value in values.items():
        set_key(config.ENV_PATH, key, value)
        os.environ[key] = value
    logger.info("Opsætning gemt i %s", config.ENV_PATH)


def shortcuts_supported() -> bool:
    """Returnér True hvis genveje kan oprettes på denne platform (kun Windows)."""
    return sys.platform.startswith("win")


def _run_powershell(script: str, env: dict[str, str] | None = None) -> str:
    """Kør ``script`` i PowerShell uden konsolvindue og returnér stdout.

    Raises:
        RuntimeError: Hvis PowerShell afslutter med fejl.
    """
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        creationflags=_CREATE_NO_WINDOW if shortcuts_supported() else 0,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell fejlede")
    return result.stdout.strip()


def default_shortcut_dir() -> Path:
    """Returnér brugerens skrivebord (også når det er flyttet til OneDrive)."""
    if not shortcuts_supported():
        return Path.home() / "Desktop"
    try:
        desktop = _run_powershell("[Environment]::GetFolderPath('Desktop')")
        if desktop:
            return Path(desktop)
    except (OSError, RuntimeError):
        logger.debug("Kunne ikke slå skrivebordet op", exc_info=True)
    return Path.home() / "Desktop"


def create_shortcut(folder: Path) -> Path:
    """Opret en genvej til ``start-dataaftaler.bat`` i ``folder``.

    Genvejen får ``app.ico`` som ikon, hvis filen findes, og starter i
    projektmappen med konsolvinduet minimeret.

    Returns:
        Path: Stien til den oprettede ``.lnk``-fil.

    Raises:
        RuntimeError: Hvis genvejen ikke kunne oprettes.
    """
    if not shortcuts_supported():
        raise RuntimeError("Genveje kan kun oprettes på Windows.")
    link = Path(folder) / SHORTCUT_NAME
    # Stierne sendes som miljøvariabler, så mellemrum og citationstegn i
    # stierne ikke skal escapes i PowerShell-scriptet.
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:DA_LINK);"
        "$s.TargetPath = $env:DA_TARGET;"
        "$s.WorkingDirectory = $env:DA_WORKDIR;"
        "$s.WindowStyle = 7;"
        "if ($env:DA_ICON) { $s.IconLocation = $env:DA_ICON + ',0' };"
        "$s.Save()"
    )
    env = {
        "DA_LINK": str(link),
        "DA_TARGET": str(LAUNCHER_PATH),
        "DA_WORKDIR": str(PROJECT_DIR),
        "DA_ICON": str(ICON_PATH) if ICON_PATH.exists() else "",
    }
    try:
        _run_powershell(script, env)
    except OSError as e:
        raise RuntimeError(str(e)) from e
    logger.info("Genvej oprettet: %s", link)
    return link
