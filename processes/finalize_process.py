"""Process finalization: tally queue outcomes into an end-result summary."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from helpers import ats_functions
from helpers.reporting import NullReporter, ProgressReporter

if TYPE_CHECKING:
    from automation_server_client import Workqueue

logger = logging.getLogger(__name__)

# Reference prefix -> summary key for completed items.
_PREFIX_TO_KEY = {"Godkend": "godkendt", "Vent": "venter", "Slet": "slettet"}


def _classify(status: str) -> str:
    """Map an ATS work item status string to a coarse outcome bucket."""
    status = (status or "").lower()
    if "fail" in status:
        return "fejlet"
    if "pending" in status:
        return "afventer_bruger"
    if "complet" in status or "done" in status:
        return "completed"
    return "andet"


def format_summary_message(summary: dict) -> str:
    """Build the Danish end-result message shown to the user."""
    return (
        f"{summary['godkendt']} aftaler godkendt, "
        f"{summary['slettet']} slettet, "
        f"{summary['venter']} sat til venter, "
        f"{summary['fejlet']} fejlet, "
        f"{summary['afventer_bruger']} afventer bruger "
        f"(i alt {summary['i_alt']} kø-elementer)."
    )


def finalize_process(
    workqueue: Workqueue,
    reporter: ProgressReporter | None = None,
) -> dict:
    """Summarise the workqueue outcome and report it. Returns the summary dict."""
    reporter = reporter or NullReporter()
    reporter.phase("Afslut")

    rows = ats_functions.get_workqueue_items(workqueue, return_data=True)

    summary = {
        "godkendt": 0,
        "venter": 0,
        "slettet": 0,
        "fejlet": 0,
        "afventer_bruger": 0,
        "i_alt": len(rows),
    }

    for ref, row in rows.items():
        outcome = _classify(str(row.get("status", "")))
        if outcome == "completed":
            key = _PREFIX_TO_KEY.get(ref.split("_")[0])
            if key:
                summary[key] += 1
        elif outcome in ("fejlet", "afventer_bruger"):
            summary[outcome] += 1

    message = format_summary_message(summary)
    reporter.summary(summary)
    reporter.log(message)
    return summary
