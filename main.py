"""
Entry point for the STIL Dataaftaler process.

The same phase functions are used two ways:

* Headless (this file's ``__main__``) with a ``NullReporter`` — selected via the
  ``--overview`` / ``--queue`` / ``--process`` / ``--finalize`` flags.
* From the Tkinter desktop app (``gui/app.py``), which calls these functions on a
  worker thread with a ``GuiReporter`` for live progress, history and pause/stop.

The work queue still lives in Automation Server; the ATS client is bootstrapped
from the local ``.env`` (``ATS_URL`` / ``ATS_TOKEN`` / ``ATS_WORKQUEUE_OVERRIDE``).
"""

import asyncio
import logging
import sys

from automation_server_client import AutomationServer, Workqueue
from mbu_rpa_core.exceptions import BusinessError, ProcessError
from mbu_rpa_core.process_states import CompletedState

from helpers import ats_functions, config
from helpers.reporting import NullReporter, ProgressReporter
from processes.application_handler import close, reset, startup
from processes.error_handling import ErrorContext, handle_error
from processes.finalize_process import finalize_process
from processes.overview import run_overview
from processes.process_item import process_item
from processes.queue_handler import concurrent_add, retrieve_items_for_queue

logger = logging.getLogger(__name__)


async def populate_queue(
    workqueue: Workqueue, reporter: ProgressReporter | None = None
):
    """Populate the workqueue with items read from the reviewed overview Excel."""
    reporter = reporter or NullReporter()
    reporter.phase("Indlæs ændringer i kø")
    logger.info("Fylder arbejdskøen...")

    reporter.log(f"Læser revideret overblik fra mappen: {config.get_output_dir()}")
    items_to_queue = retrieve_items_for_queue()

    queue_references = {str(r) for r in ats_functions.get_workqueue_items(workqueue)}

    new_items: list[dict] = []
    for item in items_to_queue:
        reference = str(item.get("reference") or "")
        if reference and reference in queue_references:
            logger.info(
                "Reference: %s er allerede i køen. Element: %s blev ikke tilføjet",
                reference,
                item,
            )
        else:
            new_items.append(item)

    reporter.log(f"{len(new_items)} nye ændringer tilføjes til køen.")
    await concurrent_add(workqueue, new_items)
    logger.info("Færdig med at fylde arbejdskøen.")


async def process_workqueue(
    workqueue: Workqueue, reporter: ProgressReporter | None = None
):
    """Process items from the workqueue, applying each change in STIL."""
    reporter = reporter or NullReporter()
    reporter.phase("Behandl kø")
    logger.info("Behandler arbejdskøen...")

    startup(reporter)

    error_count = 0

    try:
        while error_count < config.MAX_RETRY:
            for item in workqueue:
                # Cooperative pause/stop point (raises StopRequested under the GUI).
                reporter.checkpoint()
                try:
                    with item:
                        data, reference = ats_functions.get_item_info(item)

                        try:
                            logger.info(
                                "Behandler element med reference: %s", reference
                            )
                            process_item(data, reference, reporter)

                            completed_state = CompletedState.completed(
                                "Process completed without exceptions"
                            )
                            item.complete(str(completed_state))

                            continue

                        except BusinessError as e:
                            context = ErrorContext(
                                item=item,
                                action=item.pending_user(str(e)),
                                send_mail=False,
                                process_name=workqueue.name,
                            )
                            handle_error(error=e, log=logger.info, context=context)

                        except Exception as e:
                            pe = ProcessError(str(e))
                            raise pe from e

                except ProcessError as e:
                    context = ErrorContext(
                        item=item,
                        action=item.fail,
                        send_mail=True,
                        process_name=workqueue.name,
                    )
                    handle_error(error=e, log=logger.error, context=context)
                    error_count += 1
                    reset(reporter)

            break

        logger.info("Færdig med at behandle arbejdskøen.")
    finally:
        close()


async def finalize(workqueue: Workqueue, reporter: ProgressReporter | None = None):
    """Finalize process and produce the end-result summary."""
    reporter = reporter or NullReporter()
    logger.info("Afslutter processen...")

    try:
        finalize_process(workqueue, reporter)
        logger.info("Færdig med at afslutte processen.")

    except BusinessError as e:
        handle_error(error=e, log=logger.info)

    except Exception as e:
        pe = ProcessError(str(e))
        context = ErrorContext(send_mail=True, process_name=workqueue.name)
        handle_error(error=pe, log=logger.error, context=context)
        raise pe from e


if __name__ == "__main__":
    ats_functions.init_logger()
    reporter = NullReporter()

    if "--overview" in sys.argv:
        run_overview(reporter)

    queue_flags = ("--queue", "--process", "--finalize")
    if any(flag in sys.argv for flag in queue_flags):
        ats = AutomationServer.from_environment()
        prod_workqueue = ats.workqueue()

        if "--queue" in sys.argv:
            asyncio.run(populate_queue(prod_workqueue, reporter))

        if "--process" in sys.argv:
            asyncio.run(process_workqueue(prod_workqueue, reporter))

        if "--finalize" in sys.argv:
            asyncio.run(finalize(prod_workqueue, reporter))

    sys.exit(0)
