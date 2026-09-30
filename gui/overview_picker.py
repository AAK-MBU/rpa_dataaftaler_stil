"""Dialog til at vælge hvilket overbliks-ark ændringerne skal indlæses fra.

Arkene vises sorteret efter senest ændret. Det nyeste står øverst, er
forvalgt, vist med fed skrift og markeret "Senest ændret".
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import font as tkfont
from tkinter import ttk
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from pathlib import Path

_NEWEST_LABEL = "★ Senest ændret"


class OverviewPicker(tk.Toplevel):
    """Modal dialog. ``selected`` er det valgte ark, eller None ved annullering."""

    def __init__(self, parent: tk.Misc, files: list[Path]):
        super().__init__(parent)
        self.title("Vælg overbliks-ark")
        self.geometry("640x320")
        self.minsize(480, 240)
        self.selected: Path | None = None
        # Nyeste først, uanset rækkefølgen de blev givet i.
        self._files = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)

        body = ttk.Frame(self, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            body,
            text=(
                f"Der ligger {len(self._files)} overbliks-ark i mappen. "
                "Vælg det ark, ændringerne skal indlæses fra."
            ),
            wraplength=600,
        ).pack(anchor=tk.W, pady=(0, 8))

        self.tree = ttk.Treeview(
            body,
            columns=("name", "modified", "note"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("name", text="Filnavn")
        self.tree.heading("modified", text="Senest ændret")
        self.tree.heading("note", text="")
        self.tree.column("name", width=300, anchor=tk.W)
        self.tree.column("modified", width=150, anchor=tk.W)
        self.tree.column("note", width=130, anchor=tk.W)

        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")
        self._bold = bold  # Tk holder ikke selv en reference til fonten
        self.tree.tag_configure("newest", font=bold, background="#fff4c2")

        tz = ZoneInfo("Europe/Copenhagen")
        for index, path in enumerate(self._files):
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=tz)
            self.tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    path.name,
                    modified.strftime("%d-%m-%Y %H:%M"),
                    _NEWEST_LABEL if index == 0 else "",
                ),
                tags=("newest",) if index == 0 else (),
            )

        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        self.tree.selection_set("0")
        self.tree.focus("0")
        self.tree.bind("<Double-1>", lambda _e: self._choose())
        self.tree.bind("<Return>", lambda _e: self._choose())

        bar = ttk.Frame(self, padding=10)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(bar, text="Annullér", command=self._cancel).pack(side=tk.LEFT)
        ttk.Button(bar, text="Brug valgt ark", command=self._choose).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.transient(parent)
        self.grab_set()
        self.tree.focus_set()

    def _choose(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected = self._files[int(selection[0])]
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.selected = None
        self.grab_release()
        self.destroy()


def pick_overview_file(parent: tk.Misc, files: list[Path]) -> Path | None:
    """Vis dialogen og vent på den. Returnér det valgte ark, eller None."""
    picker = OverviewPicker(parent, files)
    parent.wait_window(picker)
    return picker.selected
