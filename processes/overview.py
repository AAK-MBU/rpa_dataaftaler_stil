"""Create the Dataaftaler overview Excel (the human-review artifact).

Ported from the legacy ``overview_creation.py``. Logs into STIL, walks every
organisation, collects its data agreements and writes them to
``Output/dataaftaler_oversigt_<dato>.xlsx`` with a ``statusændring`` dropdown
(GODKEND / SLET / VENT). Progress and the API throttle are surfaced through the
reporter, and a stop/pause checkpoint runs once per organisation.

This is *not* a workqueue phase – it produces the spreadsheet the user reviews
before the queue is populated.
"""

from __future__ import annotations

import contextlib
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from openpyxl.worksheet.datavalidation import DataValidation
from requests import Session

from helpers import config
from helpers.reporting import NullReporter, ProgressReporter
from helpers.stil_api import (
    flatten_dict,
    get_base_cookies,
    get_browser_cookie,
    get_data,
    get_org,
    get_org_dict,
    get_request_cookie,
    open_stil_connection,
)

logger = logging.getLogger(__name__)

_COLS_LEFT = [
    "Instregnr",
    "inst_navn",
    "status",
    "statusændring",
    "systemNavn",
    "systemBeskrivelse",
    "serviceNavn",
    "udbyderNavn",
    "Kontaktperson",
]

_COLS_RENAME = {
    "inst_kode": "Instregnr",
    "aktuelStatus": "status",
    "stilService_servicenavn": "serviceNavn",
    "udbydersystem_navn": "systemNavn",
    "udbydersystem_beskrivelse": "systemBeskrivelse",
    "udbyder_navn": "udbyderNavn",
    "udbydersystem_kontaktNavn": "Kontaktperson",
}


def run_overview(reporter: ProgressReporter | None = None) -> str:
    """Scrape all agreements from STIL and write the overview Excel.

    Returns the path of the written spreadsheet.
    """
    reporter = reporter or NullReporter()
    reporter.phase("Dan overblik")

    browser = open_stil_connection(reporter)
    try:
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
        org_dict = get_org_dict(session)
        total = len(org_dict)
        reporter.log(f"Henter aftaler fra {total} organisationer...")

        all_agreements: list[dict] = []
        orgs_without_agr: list[str] = []
        api_counter = 0
        window_start = time.monotonic()

        for index, org in enumerate(org_dict.values()):
            reporter.checkpoint()  # cooperative pause/stop point

            # Throttle: pause after THROTTLE_AFTER_CALLS calls inside the window.
            if (
                api_counter >= config.THROTTLE_AFTER_CALLS
                and time.monotonic() - window_start < config.THROTTLE_WINDOW_SECONDS
            ):
                reporter.log(
                    f"{api_counter} API-kald – pauser "
                    f"{config.THROTTLE_PAUSE_SECONDS} sekunder for ikke at "
                    "overbelaste STIL."
                )
                time.sleep(config.THROTTLE_PAUSE_SECONDS)
                reporter.log(
                    f"Pause på {config.THROTTLE_PAUSE_SECONDS} sekunder afsluttet "
                    "– fortsætter API-kald."
                )
                api_counter = 0
                window_start = time.monotonic()

            org_num = org["kode"]
            org_response = get_org(org_num, org_dict, session)
            org_cookie = get_request_cookie("AuthTokenTilslutning", org_response)
            session.headers.update({"Cookie": f"{base_cookie};{org_cookie}"})

            agreements_raw = get_data(session, org_num)
            agreements = [flatten_dict(a) for a in agreements_raw.values()]
            if not agreements:
                orgs_without_agr.append(org_num)
            for agreement in agreements:
                agreement["Instregnr"] = org.get("kode")
                agreement["inst_navn"] = org.get("navn")
                all_agreements.append(agreement)

            api_counter += 2
            reporter.set_progress(index + 1, total)

        agreements_df = pd.DataFrame(all_agreements)
        existing = {k: v for k, v in _COLS_RENAME.items() if k in agreements_df.columns}
        agreements_df = agreements_df.rename(columns=existing)

        unique_insts = (
            len(pd.unique(agreements_df["Instregnr"]))
            if "Instregnr" in agreements_df.columns
            else 0
        )
        reporter.log(
            f"{len(all_agreements)} aftaler fra {unique_insts} institutioner hentet. "
            f"{len(orgs_without_agr)} institutioner uden aftaler."
        )

        path = store_overview(agreements_df)
        reporter.log(f"Overblik gemt: {path}")
        reporter.summary(
            {
                "aftaler_hentet": len(all_agreements),
                "institutioner": unique_insts,
                "uden_aftaler": len(orgs_without_agr),
                "fil": path,
            },
            f"{len(all_agreements)} aftaler fra {unique_insts} institutioner gemt. "
            f"Overblik gemt: {path}",
        )
        return path
    finally:
        browser.quit()


def store_overview(agreements_df: pd.DataFrame) -> str:
    """Write the agreements DataFrame to an Excel with a status dropdown.

    Returns the written file path.
    """
    agreements_df = agreements_df.copy()
    agreements_df["statusændring"] = ""

    for col in _COLS_LEFT:
        if col not in agreements_df.columns:
            agreements_df[col] = ""
    agreements_df = agreements_df[[c for c in _COLS_LEFT if c in agreements_df.columns]]

    today = datetime.now(tz=ZoneInfo("Europe/Copenhagen")).strftime("%d%m%Y")
    filename = str(config.get_output_dir() / f"dataaftaler_oversigt_{today}.xlsx")

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        agreements_df.to_excel(writer, index=False, sheet_name="Oversigt")
        worksheet = writer.sheets["Oversigt"]
        worksheet.auto_filter.ref = worksheet.dimensions

        for row in range(2, worksheet.max_row + 1):
            status_cell = worksheet[f"C{row}"]
            statusaendring_cell = worksheet[f"D{row}"]  # 'statusændring' column
            if status_cell.value != "SLETTET":
                dv = DataValidation(type="list", formula1='"GODKEND, SLET, VENT"')
                dv.error_title = "Ugyldigt input"
                dv.error_message = "Vælg venligst en værdi fra rullelisten"
                worksheet.add_data_validation(dv)
                dv.add(statusaendring_cell)

        max_column_width = 30
        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                with contextlib.suppress(TypeError, ValueError):
                    max_length = max(max_length, len(str(cell.value)))
            worksheet.column_dimensions[column].width = min(
                max_length + 2, max_column_width
            )

    return filename
