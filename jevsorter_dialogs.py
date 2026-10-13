"""Brand-styled modal dialogs: a confirmation with a "don't ask again" box, and a
checklist picker used to preview presets before they are added."""

from __future__ import annotations

import textwrap
from tkinter import ttk

import customtkinter as ctk

import jevsorter_theme as th

ON, OFF = "☑", "☐"


class _Modal(ctk.CTkToplevel):
    def __init__(self, master, title: str):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.result = None
        self.configure(fg_color=th.BG)
        self.bind("<Escape>", lambda e: self.close(None))
        self.protocol("WM_DELETE_WINDOW", lambda: self.close(None))
        self.after(250, self._icon)  # customtkinter overwrites an icon set any earlier

    def _icon(self):
        th.set_window_icon(self)

    def _place(self, width: int, height: int | None = None):
        """Centre over the main window. Sizes are in unscaled pixels."""
        self.update_idletasks()
        if height is None:
            height = int(self._reverse_window_scaling(self.winfo_reqheight()))
        m = self.master
        sc = self._get_window_scaling()
        x = int(self._reverse_window_scaling(m.winfo_rootx() + (m.winfo_width() - width * sc) / 2))
        y = int(self._reverse_window_scaling(m.winfo_rooty() + (m.winfo_height() - height * sc) / 3))
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    def show(self):
        self.after(60, self._grab)
        self.wait_window(self)
        return self.result

    def _grab(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass  # the window may already be closed

    def close(self, result):
        self.result = result
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


class ConfirmDialog(_Modal):
    """show() -> (confirmed, dont_ask_again)."""

    def __init__(self, master, message: str, yes: str = "Yes", title: str = "Jev Sorter"):
        super().__init__(master, title)
        ctk.CTkLabel(self, text=message, wraplength=400, justify="left", anchor="w",
                     font=th.font(14)).pack(anchor="w", padx=24, pady=(24, 14))
        self.quiet = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="Don't ask me again", variable=self.quiet,
                        font=th.font(13)).pack(anchor="w", padx=24)
        row = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        row.pack(fill="x", padx=24, pady=(18, 22))
        self.yes_btn = th.button(row, yes, command=self.accept)
        self.yes_btn.pack(side="right")
        self.no_btn = th.button(row, "Cancel", "secondary", width=90, command=lambda: self.close((False, False)))
        self.no_btn.pack(side="right", padx=8)
        self.bind("<Return>", lambda e: self.accept())
        self._place(460)

    def accept(self):
        self.close((True, bool(self.quiet.get())))

    def show(self):
        return super().show() or (False, False)


class PickDialog(_Modal):
    """A checklist preview. packs maps a pack name to [(name, description)];
    entries whose name is in `existing` are shown but cannot be added.
    show() -> the chosen [(name, description)], or None if cancelled."""

    def __init__(self, master, title: str, intro: str, packs: dict[str, list[tuple[str, str]]],
                 existing: set[str], add_label: str = "Add"):
        super().__init__(master, title)
        self.packs, self.existing, self.add_label = packs, {e.lower() for e in existing}, add_label
        self.rows: list[tuple[str, str]] = []
        self.checked: set[int] = set()
        th.muted(self, intro, 13, anchor="w", justify="left", wraplength=700).pack(anchor="w", padx=24, pady=(20, 8))
        if len(packs) > 1:
            self.menu = ctk.CTkOptionMenu(self, values=list(packs), width=300, command=self._load)
            self.menu.pack(anchor="w", padx=24, pady=(0, 8))
        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=24)
        self.tree = ttk.Treeview(frame, columns=("ok", "name", "desc"), show="headings", height=9,
                                 selectmode="browse")
        for cid, text, w, stretch in (("ok", "", 36, False), ("name", "FOLDER NAME", 200, False),
                                      ("desc", "WHAT BELONGS IN IT", 460, True)):
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=w, stretch=stretch, anchor="w")
        sb = ctk.CTkScrollbar(frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=8)
        self.tree.tag_configure("dup", foreground=th.pick(th.MUTED))
        self.tree.bind("<Button-1>", self._click)
        self.tree.bind("<space>", lambda e: self._toggle(self.tree.focus()))
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)
        self.detail = th.muted(self, "", 12, anchor="w", justify="left", wraplength=700)
        self.detail.pack(anchor="w", padx=24, pady=(8, 0))
        row = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        row.pack(fill="x", padx=24, pady=(10, 20))
        self.add_btn = th.button(row, add_label, command=self.accept)
        self.add_btn.pack(side="right")
        th.button(row, "Cancel", "secondary", width=90, command=lambda: self.close(None)).pack(side="right", padx=8)
        th.button(row, "All", "soft", width=60, height=30, command=lambda: self._all(True)).pack(side="left")
        th.button(row, "None", "soft", width=60, height=30, command=lambda: self._all(False)).pack(side="left", padx=6)
        self._load(next(iter(packs)))
        self._place(780, 560)

    def _load(self, pack: str):
        self.rows = self.packs[pack]
        self.checked = {i for i, (n, _) in enumerate(self.rows) if n.lower() not in self.existing}
        self.tree.delete(*self.tree.get_children())
        for i, (name, desc) in enumerate(self.rows):
            dup = name.lower() in self.existing
            self.tree.insert("", "end", iid=str(i), tags=("dup",) if dup else (),
                             values=(OFF if dup else ON, name + ("  (in your list)" if dup else ""),
                                     textwrap.shorten(desc, 95, placeholder="…")))
        self.detail.configure(text="Click a row to read its full description.")
        self._refresh()

    def _refresh(self):
        n = len(self.checked)
        self.add_btn.configure(text=f"{self.add_label} {n}" if n else self.add_label,
                               state="normal" if n else "disabled")

    def _toggle(self, iid: str):
        if not iid or self.rows[int(iid)][0].lower() in self.existing:
            return
        i = int(iid)
        self.checked ^= {i}
        self.tree.set(iid, "ok", ON if i in self.checked else OFF)
        self._refresh()

    def _click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            self._toggle(self.tree.identify_row(event.y))
            return "break"

    def _all(self, on: bool):
        self.checked = ({i for i, (n, _) in enumerate(self.rows) if n.lower() not in self.existing}
                        if on else set())
        for i, (n, _) in enumerate(self.rows):
            if n.lower() not in self.existing:
                self.tree.set(str(i), "ok", ON if i in self.checked else OFF)
        self._refresh()

    def _show_detail(self, _e=None):
        sel = self.tree.selection()
        if sel:
            name, desc = self.rows[int(sel[0])]
            self.detail.configure(text=f"{name}: {desc}")

    def accept(self):
        self.close([self.rows[i] for i in sorted(self.checked)])
