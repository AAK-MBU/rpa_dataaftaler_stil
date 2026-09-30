"""Opdatering fra GitHub Releases, når programmet kører fra en release-zip.

Datakilde: GitHub's REST API ``GET /repos/<config.GITHUB_REPO>/releases/latest``
(offentligt repo, ingen token). En release skal have en zip-fil med navnet
``Dataaftaler-<tag>.zip`` bygget af ``.github/workflows/release.yml``.

Opdateringen erstatter indholdet af ``app\\`` med ``app\\`` fra den nye zip og
kopierer filerne i zip'ens yderste mappe (launcher, LÆS MIG) til
installationsmappen. ``.venv``, ``.env`` og ``Output`` i ``app\\`` bevares. Går
noget galt undervejs, lægges de gamle filer tilbage.

Kører programmet ikke fra en release-pakke (``config.INSTALL_DIR`` er None,
fx i et git-checkout), tjekkes der ikke for opdateringer.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
import tomllib
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests

from helpers import config

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_API_URL = f"https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest"
_CHECK_TIMEOUT = 5  # sekunder; tjekket må ikke forsinke opstarten mærkbart
_DOWNLOAD_TIMEOUT = 60
_UPDATE_DIR_NAME = ".update"
# Navne i app\ der tilhører brugeren/maskinen og aldrig erstattes.
_KEEP_NAMES = {".venv", ".env", "Output"}
_CREATE_NO_WINDOW = 0x08000000


@dataclass
class ReleaseInfo:
    """En nyere release end den installerede.

    Attributes:
        version: Versionen uden ``v`` (fx ``2.1.0``).
        zip_url: Download-URL til release-zip'en.
        page_url: URL til release-siden på GitHub.
    """

    version: str
    zip_url: str
    page_url: str


def installed_version() -> str:
    """Returnér den installerede version fra ``pyproject.toml`` i kodemappen."""
    with (config.CODE_DIR / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def parse_version(text: str) -> tuple[int, ...] | None:
    """Omsæt ``v2.1.0``/``2.1.0`` til ``(2, 1, 0)``; None hvis teksten ikke er en version."""
    try:
        return tuple(int(part) for part in text.strip().lstrip("vV").split("."))
    except ValueError:
        return None


def updates_enabled() -> bool:
    """Returnér True hvis programmet kører fra en release-pakke, og tjekket ikke er slået fra.

    Tjekket slås fra med env ``DATAAFTALER_NO_UPDATE=true``.
    """
    disabled = os.getenv("DATAAFTALER_NO_UPDATE", "").lower() == "true"
    return config.INSTALL_DIR is not None and not disabled


def check_for_update() -> ReleaseInfo | None:
    """Slå den seneste release op og returnér den, hvis den er nyere end den installerede.

    Netværksfejl, API-begrænsninger (HTTP 403/429) og releases uden zip-fil
    giver None, så opstarten aldrig fejler på grund af tjekket.
    """
    if not updates_enabled():
        return None
    try:
        resp = requests.get(
            _API_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=_CHECK_TIMEOUT,
        )
        if resp.status_code != 200:  # noqa: PLR2004
            logger.info("Opdateringstjek sprunget over (HTTP %s)", resp.status_code)
            return None
        release = resp.json()
    except (requests.RequestException, ValueError):
        logger.info("Opdateringstjek sprunget over (ingen forbindelse)", exc_info=True)
        return None

    latest = parse_version(release.get("tag_name", ""))
    current = parse_version(installed_version())
    if latest is None or current is None or latest <= current:
        return None

    zip_url = next(
        (
            asset["browser_download_url"]
            for asset in release.get("assets", [])
            if asset.get("name", "").startswith("Dataaftaler-")
            and asset["name"].endswith(".zip")
        ),
        None,
    )
    if zip_url is None:
        logger.info("Release %s har ingen zip-fil", release.get("tag_name"))
        return None
    return ReleaseInfo(
        version=".".join(map(str, latest)),
        zip_url=zip_url,
        page_url=release.get("html_url", ""),
    )


def _move(src: Path, dst: Path, attempts: int = 5) -> None:
    """Flyt ``src`` til ``dst`` og prøv igen, hvis Windows kortvarigt låser filen.

    Antivirus scanner ofte nyudpakkede filer og låser dem et øjeblik.
    """
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dst))
            return
        except PermissionError:
            if attempt == attempts:
                raise
            time.sleep(0.5 * attempt)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _keep_names(app_dir: Path) -> set[str]:
    """Navne i ``app_dir`` der skal bevares, inkl. en output-mappe valgt inde i app\\."""
    keep = set(_KEEP_NAMES)
    try:
        relative = config.get_base_dir().resolve().relative_to(app_dir.resolve())
        if relative.parts:
            keep.add(relative.parts[0])
    except ValueError:
        pass  # output-mappen ligger uden for app\
    return keep


def apply_update(release: ReleaseInfo) -> None:
    """Hent ``release`` og erstat programfilerne med den nye version.

    Raises:
        RuntimeError: Hvis programmet ikke kører fra en release-pakke, eller
            zip-filen ikke har den forventede struktur.
        OSError, requests.RequestException: Ved fejl under download eller
            udskiftning. De gamle filer er da lagt tilbage.
    """
    if config.INSTALL_DIR is None:
        raise RuntimeError("Opdatering kræver, at programmet kører fra en release-zip.")
    install_dir = config.INSTALL_DIR
    app_dir = config.CODE_DIR
    work_dir = install_dir / _UPDATE_DIR_NAME
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir()
    backup_dir = work_dir / "old"
    succeeded = False

    try:
        zip_path = work_dir / "download.zip"
        logger.info("Henter version %s fra %s", release.version, release.zip_url)
        with requests.get(release.zip_url, stream=True, timeout=_DOWNLOAD_TIMEOUT) as r:
            r.raise_for_status()
            with zip_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    f.write(chunk)

        extract_dir = work_dir / "new"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        new_root = extract_dir / "Dataaftaler"
        new_app = new_root / "app"
        if not (new_app / "pyproject.toml").is_file():
            raise RuntimeError(
                "Zip-filen har ikke den forventede struktur (Dataaftaler/app)."
            )

        _swap_app_dir(app_dir, new_app, backup_dir)

        # Launcher og LÆS MIG i yderste mappe. Launcheren kører ikke længere, når
        # programvinduet er åbent, så den kan overskrives.
        for item in new_root.iterdir():
            if item.is_file():
                shutil.copy2(item, install_dir / item.name)
        succeeded = True
    finally:
        # Efter en fejl betyder filer i backup-mappen, at gendannelsen ikke
        # lykkedes; så bevares de, så de kan lægges tilbage manuelt.
        if not succeeded and backup_dir.exists() and any(backup_dir.iterdir()):
            logger.error("Gamle programfiler ligger i %s", backup_dir)
        else:
            shutil.rmtree(work_dir, ignore_errors=True)
    logger.info("Opdateret til version %s", release.version)


def _swap_app_dir(app_dir: Path, new_app: Path, backup_dir: Path) -> None:
    """Erstat alt i ``app_dir`` undtagen de bevarede navne med indholdet af ``new_app``.

    Ved fejl fjernes de nye filer, og de gamle flyttes tilbage fra ``backup_dir``.
    """
    keep = _keep_names(app_dir)
    backup_dir.mkdir()
    try:
        for item in list(app_dir.iterdir()):
            if item.name not in keep:
                _move(item, backup_dir / item.name)
        for item in new_app.iterdir():
            if item.name not in keep:
                _move(item, app_dir / item.name)
    except Exception:
        logger.exception("Opdatering fejlede – gendanner de gamle filer")
        for item in list(app_dir.iterdir()):
            if item.name not in keep:
                _remove(item)
        for item in backup_dir.iterdir():
            _move(item, app_dir / item.name)
        raise


def restart() -> None:
    """Start programmet igen via launcheren i installationsmappen.

    Launcheren kører ``uv sync``, hvis den nye version har ændrede afhængigheder.
    """
    if config.INSTALL_DIR is None:
        return
    launcher = config.INSTALL_DIR / config.OUTER_LAUNCHER_NAME
    subprocess.Popen(  # noqa: S603
        ["cmd.exe", "/c", "start", "", str(launcher)],  # noqa: S607
        cwd=config.INSTALL_DIR,
        creationflags=_CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
    )
