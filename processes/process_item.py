"""Handle a single queue element: change status, delete, or confirm already-ok.

Ported from the legacy ``queue_handling.process_queue_element``. The shared
authenticated context (cookies + org lookup) comes from
:func:`processes.application_handler.get_app`, populated by ``startup()``.
"""

from __future__ import annotations

import logging

from mbu_rpa_core.exceptions import BusinessError, ProcessError
from requests import Session

from helpers.reporting import NullReporter, ProgressReporter
from helpers.stil_api import (
    change_status,
    delete_agreement,
    get_data,
    get_org,
    get_request_cookie,
    get_status,
)
from processes.application_handler import get_app

logger = logging.getLogger(__name__)


def process_item(
    item_data: dict,
    item_reference: str,
    reporter: ProgressReporter | None = None,
) -> None:
    """Apply the requested status change for one data agreement in STIL."""
    reporter = reporter or NullReporter()
    assert item_data, "Item data is required"
    assert item_reference, "Item reference is required"

    app = get_app()
    if app is None:
        raise ProcessError("Application not started – call startup() first.")

    org_num = item_data["Instregnr"]
    system_name = item_data["systemNavn"]
    service_name = item_data["serviceNavn"]
    current_status = item_data["status"]
    wanted_status = get_status(item_reference)

    # Fresh session seeded with the shared base/auth cookies for this org.
    session = Session()
    session.headers.update(
        {
            "Cookie": f"{app.base_cookie};{app.cookie_inst_list}",
            "x-xsrf-token": app.x_xsrf_token,
        }
    )

    # Activate the organisation, then refresh the cookie with its org token.
    org_response = get_org(org_num, app.org_dict, session)
    org_cookie = get_request_cookie("AuthTokenTilslutning", org_response)
    session.headers.update({"Cookie": f"{app.base_cookie};{org_cookie}"})

    agreements = get_data(session, org_num)
    agreement = agreements.get(f"{system_name}_{service_name}_{current_status}")

    if agreement is None:
        # Maybe it is already in the wanted status – then there is nothing to do.
        already_ok = agreements.get(f"{system_name}_{service_name}_{wanted_status}")
        if already_ok is not None:
            reporter.log(
                f"{org_num}: {system_name}/{service_name} har allerede status "
                f"{wanted_status}. Springer over."
            )
            return
        raise BusinessError(
            f"Aftale ikke fundet: {system_name} / {service_name} / {current_status} "
            f"for institution {org_num}"
        )

    if agreement["aktuelStatus"] != current_status:
        raise ValueError(
            f"Aftalens aktuelle status fra STIL ({agreement['aktuelStatus']}) "
            f"matcher ikke status fra kø-elementet ({current_status})"
        )

    if wanted_status in ("GODKENDT", "VENTER"):
        change_status(item_reference, agreement, session)
        reporter.log(
            f"{org_num}: {system_name}/{service_name} sat fra {current_status} "
            f"til {wanted_status}."
        )
    elif wanted_status == "SLETTET":
        delete_agreement(agreement, session)
        reporter.log(f"{org_num}: {system_name}/{service_name} slettet.")
    else:
        raise ValueError(f"Ukendt ønsket status for reference: {item_reference}")
