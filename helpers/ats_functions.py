"""Helper module to call some functionality in Automation Server using the API"""

import logging
import os

import requests
from automation_server_client import WorkItem, Workqueue
from dotenv import load_dotenv


def get_workqueue_items(workqueue: Workqueue, return_data=False):
    """
    Retrieve items from the specified workqueue.
    If the queue is empty, return an empty list.
    """
    load_dotenv()

    url = os.getenv("ATS_URL")
    token = os.getenv("ATS_TOKEN")

    if not url or not token:
        raise OSError("ATS_URL or ATS_TOKEN is not set in the environment")

    headers = {"Authorization": f"Bearer {token}"}

    workqueue_items = {} if return_data else set()

    page = 1
    size = 200  # max allowed

    while True:
        full_url = f"{url}/workqueues/{workqueue.id}/items?page={page}&size={size}"
        response = requests.get(full_url, headers=headers, timeout=60)
        response.raise_for_status()

        res_json = response.json().get("items", [])

        if not res_json:
            break

        for row in res_json:
            ref = row.get("reference")
            if ref:
                if return_data:
                    workqueue_items[ref] = row
                else:
                    workqueue_items.add(ref)

        page += 1

    return workqueue_items


def count_new_items(workqueue: Workqueue) -> int:
    """Returnér antallet af elementer med status ``new`` i arbejdskøen.

    Bruger Automation Servers ``GET /workqueues/information``, der returnerer en
    liste med én dict pr. arbejdskø (nøgler bl.a. ``id``, ``new``,
    ``in_progress``, ``completed``, ``failed``, ``pending_user_action``).
    Antallet tælles uden at tage nogen elementer fra køen.

    Raises:
        OSError: Hvis ``ATS_URL`` eller ``ATS_TOKEN`` mangler i miljøet.
        requests.HTTPError: Hvis API-kaldet fejler.
        LookupError: Hvis arbejdskøen ikke findes i svaret.
    """
    load_dotenv()

    url = os.getenv("ATS_URL")
    token = os.getenv("ATS_TOKEN")

    if not url or not token:
        raise OSError("ATS_URL or ATS_TOKEN is not set in the environment")

    response = requests.get(
        f"{url}/workqueues/information",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()

    for info in response.json():
        if info.get("id") == workqueue.id:
            return int(info["new"])

    raise LookupError(f"Arbejdskø {workqueue.id} findes ikke i /workqueues/information")


def get_item_info(item: WorkItem):
    """Unpack item"""
    return item.data["item"]["data"], item.data["item"]["reference"]


def init_logger():
    """Initialize the root logger with JSON formatting."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(module)s.%(funcName)s:%(lineno)d — %(message)s",
        datefmt="%H:%M:%S",
    )
