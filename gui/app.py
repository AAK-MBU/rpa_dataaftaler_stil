"""Tkinter desktop launcher for the STIL Dataaftaler process.

Runs the process from a caseworker's desktop (not from Automation Server) and
shows live feedback while it runs:

1. **Progress** – a bar + phase label driven by the reporter.
2. **History** – a scrolling log of everything that has happened (also written to
   a timestamped file under ``Output/logs/``).
3. **Pause / Stop** – cooperative controls honoured at every checkpoint.
4. **End result** – a Danish summary ("X aftaler godkendt, Y slettet, ...").

The process runs on a worker thread; it communicates back via a thread-safe queue
that the Tk main loop drains. The worker never touches Tk widgets directly.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk
from zoneinfo import ZoneInfo

from automation_server_client import AutomationServer
from dotenv import load_dotenv

from helpers import config
from helpers.reporting import GuiReporter, ReporterEvent, StopRequested
from main import finalize, populate_queue, process_workqueue
from processes.finalize_process import format_summary_message
from processes.overview import run_overview

logger = logging.getLogger(__name__)


class _QueueLogHandler(logging.Handler):
    """Logging handler that forwards every formatted record to the GUI queue."""

    def __init__(self, event_queue: queue.Queue[ReporterEvent]):
        super().__init__()
        self._queue = event_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put(ReporterEvent(kind="log", message=self.format(record)))
        except Exception:  # never let logging break the run
            self.handleError(record)


def _setup_logging(event_queue: queue.Queue[ReporterEvent]) -> None:
    """Route logging to the GUI history queue and a timestamped run log file."""
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s", datefmt="%H:%M:%S"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    gui_handler = _QueueLogHandler(event_queue)
    gui_handler.setFormatter(formatter)
    root_logger.addHandler(gui_handler)

    stamp = datetime.now(tz=ZoneInfo("Europe/Copenhagen")).strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(
        config.get_log_dir() / f"run_{stamp}.log", encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


class DataaftalerApp:
    """The main Tkinter application window."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Dataaftaler – STIL")
        self.root.geometry("820x600")

        # Worker <-> GUI plumbing
        self.event_queue: queue.Queue[ReporterEvent] = queue.Queue()
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.reporter = GuiReporter(self.event_queue, self.pause_event, self.stop_event)
        self.worker: threading.Thread | None = None
        self.last_summary: dict | None = None

        _setup_logging(self.event_queue)
        self._build_widgets()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(config.GUI_POLL_MS, self._drain_events)

    # ------------------------------------------------------------------ UI
    def _build_widgets(self) -> None:
        controls = ttk.Frame(self.root, padding=10)
        controls.pack(fill=tk.X)

        self.btn_overview = ttk.Button(
            controls, text="Dann overblik (Excel)", command=self._start_overview
        )
        self.btn_overview.pack(side=tk.LEFT, padx=4)

        self.btn_run = ttk.Button(
            controls, text="Indlæs ændringer & kør", command=self._start_full_run
        )
        self.btn_run.pack(side=tk.LEFT, padx=4)

        self.btn_pause = ttk.Button(
            controls, text="Pause", command=self._toggle_pause, state=tk.DISABLED
        )
        self.btn_pause.pack(side=tk.LEFT, padx=4)

        self.btn_stop = ttk.Button(
            controls, text="Stop", command=self._request_stop, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        progress = ttk.Frame(self.root, padding=(10, 0))
        progress.pack(fill=tk.X)

        self.phase_var = tk.StringVar(value="Klar.")
        ttk.Label(progress, textvariable=self.phase_var).pack(side=tk.LEFT)
        self.count_var = tk.StringVar(value="")
        ttk.Label(progress, textvariable=self.count_var).pack(side=tk.RIGHT)

        self.progress_bar = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=10, pady=(2, 8))

        ttk.Label(self.root, text="Historik:", padding=(10, 0)).pack(anchor=tk.W)
        self.history = scrolledtext.ScrolledText(
            self.root, height=20, state=tk.DISABLED, wrap=tk.WORD
        )
        self.history.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        self.summary_var = tk.StringVar(value="")
        summary_label = ttk.Label(
            self.root,
            textvariable=self.summary_var,
            padding=10,
            relief=tk.GROOVE,
            anchor=tk.W,
            wraplength=780,
        )
        summary_label.pack(fill=tk.X, padx=10, pady=(0, 10))

    # -------------------------------------------------------------- actions
    def _start_overview(self) -> None:
        self._start_worker(self._overview_worker)

    def _start_full_run(self) -> None:
        self._start_worker(self._full_run_worker)

    def _start_worker(self, target) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Kører allerede", "En proces kører allerede.")
            return

        self.stop_event.clear()
        self.pause_event.clear()
        self.last_summary = None
        self.summary_var.set("")
        self._set_progress(0, 0)

        self.worker = threading.Thread(target=target, daemon=True)
        self._set_running_state(True)
        self.worker.start()

    def _toggle_pause(self) -> None:
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.config(text="Pause")
            self.reporter.log("Genoptaget.")
        else:
            self.pause_event.set()
            self.btn_pause.config(text="Fortsæt")
            self.reporter.log("Sat på pause...")

    def _request_stop(self) -> None:
        self.stop_event.set()
        self.pause_event.clear()  # unblock a paused checkpoint so it can stop
        self.reporter.log("Stop anmodet – afslutter ved næste checkpoint...")
        self.btn_stop.config(state=tk.DISABLED)

    # -------------------------------------------------------------- workers
    def _overview_worker(self) -> None:
        try:
            run_overview(self.reporter)
        except StopRequested:
            self.reporter.log("Overblik stoppet af bruger.", "warning")
        except Exception as e:  # surfaced in the history + log file
            logger.exception("Fejl under dannelse af overblik")
            self.reporter.log(f"Fejl: {e}", "error")
        finally:
            self.reporter.done("Overblik afsluttet.")

    def _full_run_worker(self) -> None:
        try:
            load_dotenv()
            ats = AutomationServer.from_environment()
            workqueue = ats.workqueue()

            asyncio.run(populate_queue(workqueue, self.reporter))
            asyncio.run(process_workqueue(workqueue, self.reporter))
            asyncio.run(finalize(workqueue, self.reporter))
        except StopRequested:
            self.reporter.log("Kørsel stoppet af bruger.", "warning")
        except Exception as e:
            logger.exception("Fejl under kørsel")
            self.reporter.log(f"Fejl: {e}", "error")
        finally:
            self.reporter.done("Kørsel afsluttet.")

    # --------------------------------------------------------------- events
    def _drain_events(self) -> None:
        try:
            while True:
                event = self.event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            self.root.after(config.GUI_POLL_MS, self._drain_events)

    def _handle_event(self, event: ReporterEvent) -> None:
        if event.kind == "log":
            self._append_history(event.message)
        elif event.kind == "progress":
            self._set_progress(event.current, event.total)
        elif event.kind == "phase":
            self.phase_var.set(f"Fase: {event.message}")
        elif event.kind == "summary":
            self.last_summary = event.data
        elif event.kind == "done":
            self._on_done(event.message)

    def _append_history(self, message: str) -> None:
        self.history.config(state=tk.NORMAL)
        self.history.insert(tk.END, message + "\n")
        self.history.see(tk.END)
        self.history.config(state=tk.DISABLED)

    def _set_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.progress_bar.config(value=current / total * 100)
            self.count_var.set(f"{current} / {total}")
        else:
            self.progress_bar.config(value=0)
            self.count_var.set("")

    def _on_done(self, message: str) -> None:
        self._set_running_state(False)
        self.phase_var.set("Klar.")
        if self.last_summary is not None:
            self.summary_var.set(format_summary_message(self.last_summary))
        elif message:
            self.summary_var.set(message)

    def _set_running_state(self, running: bool) -> None:
        run_state = tk.DISABLED if running else tk.NORMAL
        ctl_state = tk.NORMAL if running else tk.DISABLED
        self.btn_overview.config(state=run_state)
        self.btn_run.config(state=run_state)
        self.btn_pause.config(state=ctl_state, text="Pause")
        self.btn_stop.config(state=ctl_state)

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askokcancel(
                "Afslut",
                "En proces kører stadig. Vil du stoppe den og lukke vinduet?",
            ):
                return
            self.stop_event.set()
            self.pause_event.clear()
        self.root.destroy()


def main() -> None:
    """Launch the desktop application."""
    root = tk.Tk()
    DataaftalerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
