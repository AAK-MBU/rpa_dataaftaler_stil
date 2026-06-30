"""Queue population: read the reviewed Excel overview and build queue items.

``retrieve_items_for_queue`` ports the legacy ``queue_upload.retrieve_changes``
+ reference/hash logic. Each returned item is ``{"reference": ..., "data": ...}``;
``main.populate_queue`` then de-dupes against the live queue and ``concurrent_add``
pushes them to the Automation Server workqueue.
"""

from __future__ import annotations

import asyncio
import glob
import hashlib
import json
import logging
import os
from typing import TYPE_CHECKING

import pandas as pd

from helpers import config

if TYPE_CHECKING:
    from automation_server_client import Workqueue

logger = logging.getLogger(__name__)

# Columns the reviewed overview must still contain for the queue to be built.
# The caseworker edits the sheet by hand, so a deleted/renamed column is a real
# risk – we validate up front and tell them exactly what is missing.
REQUIRED_COLUMNS = ("Instregnr", "status", "statusændring", "systemNavn", "serviceNavn")


def clean_instregnr(instregnr) -> str:
    """Remove any decimal point and trailing digits from an Instregnr value."""
    return str(instregnr).split(".", maxsplit=1)[0]


def generate_short_hash(data, length: int = 8) -> str:
    """Generate a short, stable hash from a dict/string (used in references)."""
    if isinstance(data, dict):
        data = json.dumps(data, sort_keys=True)
    return hashlib.md5(data.encode()).hexdigest()[:length]


def _dedupe_references(items: list[dict]) -> list[dict]:
    """Ensure references are unique by suffixing duplicates with an index."""
    seen: dict[str, int] = {}
    for item in items:
        ref = item["reference"]
        if ref in seen:
            seen[ref] += 1
            item["reference"] = f"{ref}_{seen[ref]}"
            logger.info("Dublet-reference fundet, omdøbt til %s", item["reference"])
        else:
            seen[ref] = 0
    return items


def retrieve_items_for_queue() -> list[dict]:
    """Read the single ``*Oversigt*.xlsx`` in Output/ and build queue items.

    Only rows whose ``statusændring`` requests a change to a *different* status
    are included.

    Raises ``ValueError`` with a user-facing Danish message if there is not
    exactly one overview file, the file cannot be read (e.g. it is still open in
    Excel), or a required column has been deleted/renamed.
    """
    output_dir = config.get_output_dir()
    # Case-insensitive match: the file is written lowercase ("...oversigt...") but
    # we must not rely on the OS filesystem being case-insensitive.
    excel_files = [
        f
        for f in glob.glob(os.path.join(output_dir, "*.xlsx"))
        if "oversigt" in os.path.basename(f).lower()
    ]
    if len(excel_files) != 1:
        names = ", ".join(os.path.basename(f) for f in excel_files)
        raise ValueError(
            "Der skal være præcis ét Oversigt-regneark i mappen "
            f"'{output_dir}'. Det reviderede regneark skal ligge dér (det er også "
            "hvor 'Dan overblik' gemmer det). Slet evt. gamle filer. "
            f"Filer fundet: {names or '(ingen)'}"
        )

    excel_path = excel_files[0]
    filename = os.path.basename(excel_path)
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        raise ValueError(
            f"Kunne ikke læse regnearket '{filename}'. "
            "Er filen stadig åben i Excel? Luk den og prøv igen."
        ) from e

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"Regnearket '{filename}' mangler nødvendige kolonner: "
            f"{', '.join(missing)}. Disse kolonner må ikke slettes eller omdøbes. "
            "Dan overblikket igen, eller gendan kolonnerne, og prøv igen. "
            f"(Kolonner fundet: {', '.join(map(str, df.columns))})"
        )

    df["Instregnr"] = df["Instregnr"].apply(clean_instregnr)

    items: list[dict] = []
    for change_value, ref_prefix in config.EXCEL_CHANGE_TO_REFERENCE.items():
        target_status = config.SET_STATUS_MAP[ref_prefix]
        filtered = df[
            (df["statusændring"] == change_value) & (df["status"] != target_status)
        ]
        records = (
            filtered[["Instregnr", "systemNavn", "serviceNavn", "status"]]
            .dropna()
            .to_dict(orient="records")
        )
        for rec in records:
            items.append(
                {"reference": f"{ref_prefix}_{generate_short_hash(rec)}", "data": rec}
            )

    items = _dedupe_references(items)
    logger.info("Antal ændringer i alt: %d", len(items))
    return items


def create_sort_key(item: dict) -> str:
    """
    Create a sort key based on the entire JSON structure.
    Converts the item to a sorted JSON string for consistent ordering.
    """
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


async def concurrent_add(workqueue: Workqueue, items: list[dict]) -> None:
    """
    Populate the workqueue with items to be processed.
    Uses concurrency and retries with exponential backoff.

    Args:
        workqueue (Workqueue): The workqueue to populate.
        items (list[dict]): List of items to add to the queue.

    Returns:
        None

    Raises:
        Exception: If adding an item fails after all retries.
    """
    sem = asyncio.Semaphore(config.MAX_CONCURRENCY)

    async def add_one(it: dict):
        reference = str(it.get("reference") or "")
        data = {"item": it}

        async with sem:
            for attempt in range(1, config.MAX_RETRIES + 1):
                try:
                    await asyncio.to_thread(workqueue.add_item, data, reference)
                    logger.info(
                        "Tilføjede element til køen med reference: %s", reference
                    )
                    return True

                except Exception as e:
                    if attempt >= config.MAX_RETRIES:
                        logger.error(
                            "Kunne ikke tilføje element %s efter %d forsøg: %s",
                            reference,
                            attempt,
                            e,
                        )
                        return False

                    backoff = config.RETRY_BASE_DELAY * (2 ** (attempt - 1))

                    logger.warning(
                        "Fejl ved tilføjelse af %s (forsøg %d/%d). "
                        "Prøver igen om %.2fs... %s",
                        reference,
                        attempt,
                        config.MAX_RETRIES,
                        backoff,
                        e,
                    )
                    await asyncio.sleep(backoff)

    if not items:
        logger.info("Ingen nye elementer at tilføje.")
        return

    sorted_items = sorted(items, key=create_sort_key)
    logger.info(
        "Behandler %d elementer sorteret efter komplet JSON-struktur",
        len(sorted_items),
    )

    results = await asyncio.gather(*(add_one(i) for i in sorted_items))
    successes = sum(1 for r in results if r)
    failures = len(results) - successes

    logger.info(
        "Opsummering: %d lykkedes, %d fejlede ud af %d",
        successes,
        failures,
        len(results),
    )
