"""Progress reporting + run control abstraction.

The ported process phases (overview creation, queue processing, finalize) emit
progress through a :class:`ProgressReporter` and call :meth:`ProgressReporter.checkpoint`
at natural boundaries. This lets the *same* phase code run two ways:

* headless (``main.py``) with a :class:`NullReporter` — events just go to the log;
* from the Tkinter desktop app with a :class:`GuiReporter` — events are pushed
  onto a thread-safe queue the GUI drains, and pause/stop is honoured via two
  ``threading.Event`` flags.

``checkpoint()`` is the single place that blocks while paused and raises
:class:`StopRequested` when the user asks to stop, so cancellation stays cooperative.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import queue
    import threading

logger = logging.getLogger(__name__)

# How long checkpoint() sleeps between pause/stop polls while paused.
_PAUSE_POLL_SECONDS = 0.1


class StopRequested(Exception):
    """Raised by ``checkpoint()`` when the user has requested the run to stop."""


@dataclass
class ReporterEvent:
    """A single event sent from the worker thread to the GUI."""

    kind: str  # "log" | "progress" | "phase" | "summary" | "done"
    message: str = ""
    level: str = "info"  # for "log" events
    current: int = 0  # for "progress" events
    total: int = 0  # for "progress" events
    data: dict = field(default_factory=dict)  # for "summary" events


class ProgressReporter:
    """Base reporter. Logs everything; does nothing fancy and never pauses/stops.

    Used directly as the headless (no-GUI) reporter.
    """

    def log(self, message: str, level: str = "info") -> None:
        """Log a human-readable progress line."""
        logger.log(logging.getLevelName(level.upper()), message)

    def set_progress(self, current: int, total: int) -> None:
        """Report progress as ``current`` of ``total``."""

    def phase(self, name: str) -> None:
        """Announce that a new phase of the run has started."""
        logger.info("Phase: %s", name)

    def checkpoint(self) -> None:
        """Cooperative cancellation point. No-op for the headless reporter."""

    def summary(self, data: dict) -> None:
        """Report the final result summary."""
        logger.info("Summary: %s", data)

    def done(self, message: str = "") -> None:
        """Signal that the run has finished (success, error, or stopped)."""
        if message:
            logger.info(message)


# Headless reporter is just the base behaviour.
NullReporter = ProgressReporter


class GuiReporter(ProgressReporter):
    """Reporter that feeds a Tkinter GUI and honours pause/stop flags.

    Args:
        event_queue: thread-safe queue the GUI drains on its main loop.
        pause_event: when set, ``checkpoint()`` blocks until it is cleared.
        stop_event: when set, ``checkpoint()`` raises :class:`StopRequested`.
    """

    def __init__(
        self,
        event_queue: queue.Queue[ReporterEvent],
        pause_event: threading.Event,
        stop_event: threading.Event,
    ):
        self._queue = event_queue
        self._pause_event = pause_event
        self._stop_event = stop_event

    def log(self, message: str, level: str = "info") -> None:
        # Text goes through stdlib logging only; the GUI captures the logging
        # stream via a handler (see gui/app.py) so handle_error() output and
        # library logs show up in the history too, with no duplication.
        logger.log(logging.getLevelName(level.upper()), message)

    def set_progress(self, current: int, total: int) -> None:
        self._queue.put(ReporterEvent(kind="progress", current=current, total=total))

    def phase(self, name: str) -> None:
        logger.info("Phase: %s", name)
        self._queue.put(ReporterEvent(kind="phase", message=name))

    def checkpoint(self) -> None:
        # Block while paused, but break out immediately if a stop is requested.
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(_PAUSE_POLL_SECONDS)
        if self._stop_event.is_set():
            raise StopRequested

    def summary(self, data: dict) -> None:
        logger.info("Summary: %s", data)
        self._queue.put(ReporterEvent(kind="summary", data=data))

    def done(self, message: str = "") -> None:
        if message:
            logger.info(message)
        self._queue.put(ReporterEvent(kind="done", message=message))
