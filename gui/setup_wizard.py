"""Opsætningsdialog der udfylder ``.env`` ved første start.

Dialogen går trinvis gennem:

1. **Driftsform** – ATS (arbejdskø i Automation Server) eller lokalt (ingen kø).
2. **Automation Server** – URL, token og workqueue-ID (kun ved ATS).
3. **Output-mappe** – ``BASE_DIR``; overblik og logs lægges i ``<mappe>/Output``.
4. **Genvej** – valgfri genvej til ``start-dataaftaler.bat`` med ``app.ico`` som ikon.

Værdierne gemmes med :func:`helpers.settings.save_settings`, når brugeren
trykker "Gem".
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from helpers import config, settings

logger = logging.getLogger(__name__)

_PAD = {"padx": 12, "pady": 4}
_WRAP = 460


class SetupWizard(tk.Toplevel):
    """Modal opsætningsdialog. ``completed`` er True, hvis opsætningen blev gemt."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Opsætning – Dataaftaler")
        self.geometry("520x360")
        self.resizable(False, False)
        self.completed = False

        current = settings.current_settings()
        self.mode_var = tk.StringVar(value=config.get_run_mode() or config.RUN_MODE_ATS)
        self.url_var = tk.StringVar(value=current["ATS_URL"])
        self.token_var = tk.StringVar(value=current["ATS_TOKEN"])
        self.workqueue_var = tk.StringVar(value=current["ATS_WORKQUEUE_OVERRIDE"])
        self.base_dir_var = tk.StringVar(
            value=current["BASE_DIR"] or str(config.get_base_dir())
        )
        self.shortcut_var = tk.BooleanVar(value=settings.shortcuts_supported())
        self.shortcut_dir_var = tk.StringVar(value=str(settings.default_shortcut_dir()))

        self.body = ttk.Frame(self, padding=10)
        self.body.pack(fill=tk.BOTH, expand=True)
        self._build_buttons()

        self.step_index = 0
        self._show_step()

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        # Et vindue der er transient til et skjult hovedvindue, vises ikke på
        # Windows; ved første start er hovedvinduet endnu skjult.
        if parent.winfo_viewable():
            self.transient(parent)
        self.grab_set()
        self.focus_force()

    # ------------------------------------------------------------ navigation
    def _steps(self) -> list:
        steps = [self._step_mode]
        if self.mode_var.get() == config.RUN_MODE_ATS:
            steps.append(self._step_ats)
        steps += [self._step_output, self._step_shortcut]
        return steps

    def _build_buttons(self) -> None:
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(bar, text="Annullér", command=self._cancel).pack(side=tk.LEFT)
        self.btn_next = ttk.Button(bar, text="Næste", command=self._next)
        self.btn_next.pack(side=tk.RIGHT)
        self.btn_back = ttk.Button(bar, text="Tilbage", command=self._back)
        self.btn_back.pack(side=tk.RIGHT, padx=4)

    def _show_step(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        steps = self._steps()
        ttk.Label(
            self.body,
            text=f"Trin {self.step_index + 1} af {len(steps)}",
            foreground="gray",
        ).pack(anchor=tk.W, **_PAD)
        steps[self.step_index]()
        self.btn_back.config(state=tk.NORMAL if self.step_index else tk.DISABLED)
        last = self.step_index == len(steps) - 1
        self.btn_next.config(text="Gem" if last else "Næste")

    def _next(self) -> None:
        if not self._validate_step():
            return
        if self.step_index == len(self._steps()) - 1:
            self._finish()
            return
        self.step_index += 1
        self._show_step()

    def _back(self) -> None:
        self.step_index = max(0, self.step_index - 1)
        self._show_step()

    def _cancel(self) -> None:
        self.completed = False
        self.grab_release()
        self.destroy()

    # ----------------------------------------------------------------- steps
    def _heading(self, text: str, help_text: str) -> None:
        ttk.Label(self.body, text=text, font=("TkDefaultFont", 11, "bold")).pack(
            anchor=tk.W, **_PAD
        )
        ttk.Label(self.body, text=help_text, wraplength=_WRAP).pack(anchor=tk.W, **_PAD)

    def _step_mode(self) -> None:
        self._heading(
            "Hvordan skal ændringerne køres?",
            "Vælg ATS, hvis ændringerne skal lægges i en arbejdskø i Automation "
            "Server. Vælg Lokalt, hvis ændringerne fra overbliks-arket skal køres "
            "direkte fra denne computer uden arbejdskø.",
        )
        ttk.Radiobutton(
            self.body,
            text="ATS (Automation Server-arbejdskø)",
            variable=self.mode_var,
            value=config.RUN_MODE_ATS,
        ).pack(anchor=tk.W, **_PAD)
        ttk.Radiobutton(
            self.body,
            text="Lokalt (ingen arbejdskø)",
            variable=self.mode_var,
            value=config.RUN_MODE_LOCAL,
        ).pack(anchor=tk.W, **_PAD)

    def _labelled_entry(self, label: str, var: tk.StringVar, **kwargs) -> None:
        row = ttk.Frame(self.body)
        row.pack(fill=tk.X, **_PAD)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var, **kwargs).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

    def _step_ats(self) -> None:
        self._heading(
            "Automation Server",
            "Indtast adressen på Automation Server, dit token og ID'et på den "
            "arbejdskø, der skal bruges.",
        )
        self._labelled_entry("URL", self.url_var)
        self._labelled_entry("Token", self.token_var, show="•")
        self._labelled_entry("Workqueue-ID", self.workqueue_var)

    def _folder_picker(self, var: tk.StringVar, title: str) -> None:
        row = ttk.Frame(self.body)
        row.pack(fill=tk.X, **_PAD)
        ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def browse() -> None:
            chosen = filedialog.askdirectory(
                parent=self, title=title, initialdir=var.get() or None
            )
            if chosen:
                var.set(str(Path(chosen)))

        ttk.Button(row, text="Vælg...", command=browse).pack(side=tk.LEFT, padx=4)

    def _step_output(self) -> None:
        self._heading(
            "Mappe til output",
            "Vælg den mappe, hvor programmet skal gemme sine filer. Overbliks-"
            "arket og logfiler lægges i undermappen Output.",
        )
        self._folder_picker(self.base_dir_var, "Vælg mappe til output")
        preview = tk.StringVar()

        def update_preview(*_args) -> None:
            base = self.base_dir_var.get().strip()
            preview.set(f"Filer gemmes i: {Path(base) / 'Output'}" if base else "")

        self.base_dir_var.trace_add("write", update_preview)
        update_preview()
        ttk.Label(self.body, textvariable=preview, foreground="gray").pack(
            anchor=tk.W, **_PAD
        )

    def _step_shortcut(self) -> None:
        self._heading(
            "Genvej (valgfrit)",
            "Programmet kan oprette en genvej, så det kan startes med et "
            "dobbeltklik. Genvejen får programmets ikon.",
        )
        if not settings.shortcuts_supported():
            self.shortcut_var.set(False)
            ttk.Label(self.body, text="Genveje kan kun oprettes på Windows.").pack(
                anchor=tk.W, **_PAD
            )
            return
        ttk.Checkbutton(
            self.body, text="Opret genvej", variable=self.shortcut_var
        ).pack(anchor=tk.W, **_PAD)
        self._folder_picker(self.shortcut_dir_var, "Vælg placering af genvej")

    # ------------------------------------------------------------ validation
    def _validate_step(self) -> bool:
        step = self._steps()[self.step_index]
        if step == self._step_ats:
            missing = [
                name
                for name, var in (
                    ("URL", self.url_var),
                    ("Token", self.token_var),
                    ("Workqueue-ID", self.workqueue_var),
                )
                if not var.get().strip()
            ]
            if missing:
                self._warn(f"Udfyld venligst: {', '.join(missing)}.")
                return False
            if (
                not self.url_var.get()
                .strip()
                .lower()
                .startswith(("http://", "https://"))
            ):
                self._warn("URL skal starte med http:// eller https://.")
                return False
        elif step == self._step_output:
            base = self.base_dir_var.get().strip()
            if not base:
                self._warn("Vælg en mappe til output.")
                return False
            if not Path(base).is_dir():
                self._warn(f"Mappen findes ikke: {base}")
                return False
        elif step == self._step_shortcut and self.shortcut_var.get():
            if not Path(self.shortcut_dir_var.get().strip()).is_dir():
                self._warn("Vælg en eksisterende mappe til genvejen.")
                return False
        return True

    def _warn(self, message: str) -> None:
        messagebox.showwarning("Opsætning", message, parent=self)

    # ---------------------------------------------------------------- finish
    def _finish(self) -> None:
        values = {
            "RUN_MODE": self.mode_var.get(),
            "BASE_DIR": self.base_dir_var.get().strip(),
        }
        if self.mode_var.get() == config.RUN_MODE_ATS:
            values |= {
                "ATS_URL": self.url_var.get().strip().rstrip("/"),
                "ATS_TOKEN": self.token_var.get().strip(),
                "ATS_WORKQUEUE_OVERRIDE": self.workqueue_var.get().strip(),
            }
        try:
            settings.save_settings(values)
        except OSError as e:
            logger.exception("Kunne ikke gemme opsætningen")
            messagebox.showerror(
                "Opsætning", f"Opsætningen kunne ikke gemmes: {e}", parent=self
            )
            return

        if self.shortcut_var.get():
            try:
                link = settings.create_shortcut(
                    Path(self.shortcut_dir_var.get().strip())
                )
                messagebox.showinfo(
                    "Opsætning", f"Genvej oprettet:\n{link}", parent=self
                )
            except RuntimeError as e:
                # Opsætningen er gemt; kun genvejen mangler.
                logger.exception("Kunne ikke oprette genvej")
                messagebox.showwarning(
                    "Opsætning",
                    f"Opsætningen er gemt, men genvejen kunne ikke oprettes: {e}",
                    parent=self,
                )

        self.completed = True
        self.grab_release()
        self.destroy()


def run_setup_wizard(parent: tk.Misc) -> bool:
    """Vis opsætningsdialogen og vent på den. Returnér True hvis den blev gemt."""
    wizard = SetupWizard(parent)
    parent.wait_window(wizard)
    return wizard.completed
