"""Handle a single queue element: change status, delete, or confirm already-ok.

The shared authenticated context (session + org lookup) comes from
:func:`processes.application_handler.get_app`, populated by ``startup()``.
"""

from __future__ import annotations

import logging

from mbu_rpa_core.exceptions import BusinessError, ProcessError

from helpers.reporting import NullReporter, ProgressReporter
from helpers.stil_api import get_data, get_status, update_status
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

    if wanted_status is None:
        raise ValueError(f"Ukendt ønsket status for reference: {item_reference}")

    if org_num not in app.org_dict:
        raise BusinessError(
            f"Institution {org_num} findes ikke blandt de organisationer, "
            "brugeren har adgang til i STIL"
        )

    app.activate(org_num)
    agreements = get_data(app.session, org_num)
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

    # TODO(HAR): hvis sletning ikke går via opdater_status, skal SLETTET have sit eget kald.
    update_status(agreement, wanted_status, app.session)
    reporter.log(
        f"{org_num}: {system_name}/{service_name} sat fra {current_status} "
        f"til {wanted_status}."
    )
