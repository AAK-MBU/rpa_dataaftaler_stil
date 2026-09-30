"""Custom exceptions for the Dataaftaler process.

The ATS framework uses ``mbu_rpa_core.exceptions`` (``BusinessError`` /
``ProcessError``) for queue handling. ``ResponseError`` is a thin transport-level
error raised by the STIL API helpers; the queue loop wraps any non-business
exception into a ``ProcessError``, so ``ResponseError`` only needs to carry a
useful message (and the originating response, when available).
"""

from __future__ import annotations

import requests


class ResponseError(Exception):
    """Raised when a STIL API request returns an unexpected response.

    Accepts either a ``requests.Response`` or a plain message string so it can be
    used both for failed HTTP calls and for higher-level "unexpected payload" cases.
    """

    def __init__(
        self,
        response: requests.Response | None = None,
        message: str | None = None,
    ):
        self.response = response if isinstance(response, requests.Response) else None

        # Allow ResponseError("some message") as a convenience.
        if message is None and isinstance(response, str):
            message = response

        if message is not None:
            generated = message
        elif self.response is not None:
            generated = (
                f"Status Code: {self.response.status_code}, "
                f"Response: {self.response.text}"
            )
        else:
            generated = "Unexpected STIL API response"

        super().__init__(generated)
