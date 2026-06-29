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
            logger.info("Duplicate reference found, renamed to %s", item["reference"])
        else:
            seen[ref] = 0
    return items


def retrieve_items_for_queue() -> list[dict]:
    """Read the single ``*Oversigt*.xlsx`` in Output/ and build queue items.

    Only rows whose ``statusændring`` requests a change to a *different* status
    are included. Raises ``ValueError`` if there is not exactly one overview file.
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
            "Der skal være præcis ét Oversigt-regneark i Output-mappen. "
            f"Slet gamle filer. Filer fundet: {names or '(ingen)'}"
        )

    df = pd.read_excel(excel_files[0])
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
    logger.info("Total changes: %d", len(items))
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
                    logger.info("Added item to queue with reference: %s", reference)
                    return True

                except Exception as e:
                    if attempt >= config.MAX_RETRIES:
                        logger.error(
                            "Failed to add item %s after %d attempts: %s",
                            reference,
                            attempt,
                            e,
                        )
                        return False

                    backoff = config.RETRY_BASE_DELAY * (2 ** (attempt - 1))

                    logger.warning(
                        "Error adding %s (attempt %d/%d). Retrying in %.2fs... %s",
                        reference,
                        attempt,
                        config.MAX_RETRIES,
                        backoff,
                        e,
                    )
                    await asyncio.sleep(backoff)

    if not items:
        logger.info("No new items to add.")
        return

    sorted_items = sorted(items, key=create_sort_key)
    logger.info(
        "Processing %d items sorted by complete JSON structure", len(sorted_items)
    )

    results = await asyncio.gather(*(add_one(i) for i in sorted_items))
    successes = sum(1 for r in results if r)
    failures = len(results) - successes

    logger.info(
        "Summary: %d succeeded, %d failed out of %d", successes, failures, len(results)
    )
