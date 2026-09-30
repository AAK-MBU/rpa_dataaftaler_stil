"""Handle a single queue element: change status, delete, or confirm already-ok.

After every change the agreements are fetched again and the affected agreement
(matched on ``aftaleId``) is checked to have the wanted status; see
:func:`verify_change`.

The shared authenticated context (session + org lookup) comes from
:func:`processes.application_handler.get_app`, populated by ``startup()``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mbu_rpa_core.exceptions import BusinessError, ProcessError

from helpers import config
from helpers.reporting import NullReporter, ProgressReporter
from helpers.stil_api import delete_agreement, get_data, get_status, update_status
from processes.application_handler import get_app

if TYPE_CHECKING:
    from requests import Session

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
    # Kø-elementer oprettet før kommentar-kolonnen fandtes, har ingen kommentar.
    kommentar = item_data.get("kommentar") or ""
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

    if agreement["aftaleStatus"] != current_status:
        raise ValueError(
            f"Aftalens aktuelle status fra STIL ({agreement['aftaleStatus']}) "
            f"matcher ikke status fra kø-elementet ({current_status})"
        )

    if wanted_status == config.STATUS_DELETED:
        delete_agreement(agreement, app.session)
    else:
        update_status(agreement, wanted_status, app.session, kommentar)

    verify_change(agreement, wanted_status, org_num, app.session)
    if wanted_status == config.STATUS_DELETED:
        reporter.log(f"{org_num}: {system_name}/{service_name} slettet (verificeret).")
    else:
        reporter.log(
            f"{org_num}: {system_name}/{service_name} sat fra {current_status} "
            f"til {wanted_status} (verificeret)."
        )


def verify_change(
    agreement: dict, wanted_status: str, org_num: str, session: Session
) -> None:
    """Hent aftalerne igen og kontrollér, at ``agreement`` har fået ``wanted_status``.

    Datakilde: :func:`helpers.stil_api.get_data` for den aktive institution.
    Aftalen findes på ``aftaleId``. En slettet aftale godkendes både med status
    ``SLETTET`` og hvis den ikke længere er med i listen.

    Raises:
        BusinessError: Hvis aftalen ikke har fået den ønskede status, så
            ændringen kan kontrolleres manuelt.
    """
    aftale_id = agreement["aftaleId"]
    refreshed = next(
        (a for a in get_data(session, org_num).values() if a["aftaleId"] == aftale_id),
        None,
    )

    if refreshed is None:
        if wanted_status == config.STATUS_DELETED:
            logger.info("Aftale %s findes ikke længere i STIL – slettet.", aftale_id)
            return
        raise BusinessError(
            f"Aftale {aftale_id} for institution {org_num} blev ikke fundet ved "
            f"kontrol efter statusændring til {wanted_status}. Kontrollér den i STIL."
        )

    if refreshed["aftaleStatus"] != wanted_status:
        raise BusinessError(
            f"Statusændring ikke bekræftet: aftale {aftale_id} for institution "
            f"{org_num} har status {refreshed['aftaleStatus']} i STIL efter "
            f"ændring til {wanted_status}. Kontrollér den i STIL."
        )
    logger.info("Aftale %s har status %s i STIL.", aftale_id, wanted_status)
