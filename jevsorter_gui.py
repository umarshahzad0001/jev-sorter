#!/usr/bin/env python3
"""Jev Sorter - desktop app. Same engine as the jevsorter command, with a
preview-then-apply window. Usage: jevsorter_gui.py [FOLDER ...]"""

from __future__ import annotations

import json
import os
import queue
import sys
import textwrap
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tkinter import TclError, filedialog, messagebox, ttk
from types import SimpleNamespace

import customtkinter as ctk

import jevsorter as engine
import jevsorter_dialogs as dlg
import jevsorter_presets as presets
import jevsorter_settings as cfg
import jevsorter_theme as th
import jevsorter_tray as tray_mod

APP_NAME = "Jev Sorter"
MAC = sys.platform == "darwin"  # no tray icon there (it clashes with Tk's main loop); the Dock plays that role
WHERE = "Dock" if MAC else "system tray"
STAY_LABEL = "(stay where it is)"
NO_ROWS = "Select rows first"
CONFIRMS = {  # setting key: label in Settings > Ask before
    "move": "Moving files",
    "undo": "Undoing a run",
    "remove_folder": "Removing a folder from the list",
    "clear_key": "Removing the saved API key",
    "delete_categories": "Deleting a categories file",
}
PAGES = ("Sort", "Categories", "History", "Settings")
KEY_MASK = "•" * 16   # stands in for a saved key; the real one is never put back in the box


def log_error(text: str) -> None:
    try:
        p = cfg.settings_path().with_name("gui.log")
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')}\n{text}\n")
    except OSError:
        pass


class App(ctk.CTk):
    def __init__(self, start_folders: list[str] | None = None, start_hidden: bool = False):
        self.s = cfg.load()
        th.register_fonts()
        th.apply_theme()
        ctk.set_appearance_mode(self.s["theme"])
        super().__init__()
        self.title(APP_NAME)
        scale = self._get_window_scaling()
        w = min(1100, int(self.winfo_screenwidth() / scale) - 60)
        h = min(680, int(self.winfo_screenheight() / scale) - 110)
        self.geometry(f"{w}x{h}+{max(0, int((self.winfo_screenwidth() / scale - w) / 2))}+20")
        self.minsize(860, 520)
        self._set_icon()

        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.cancel = threading.Event()
        self.plans: list[engine.FolderPlan] = []
        self.props: dict[str, engine.Proposal] = {}
        self.cats: dict[str, list[str]] = {}      # sort folder -> category names
        self.checked: set[str] = set()
        self.last_run: str | None = None
        self.watch_job = None
        self.cat_rows: list[list[str]] = []       # Categories editor [name, desc]
        self.cat_raw: dict = {}

        for f in start_folders or []:
            self._add_folder(f, save=False)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_nav()
        self.pages: dict[str, ctk.CTkFrame] = {}
        self._build_sort()
        self._build_categories()
        self._build_history()
        self._build_settings()
        self.titles = {n: th.PageTitle(self, t, k) for n, t, k in (
            ("Sort", "Sort a folder", "mark"), ("Categories", "Your categories", "wave"),
            ("History", "Past runs", "circle"), ("Settings", "Settings", "brush"))}
        self.status = th.muted(self, "", 12, anchor="w")
        self.status.grid(row=2, column=1, sticky="ew", padx=(0, 24), pady=(0, 8))
        self._style_tree()
        self.show("Settings" if self._needs_setup() else "Sort")
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._told_tray = False
        self.tray = tray_mod.Tray(lambda action: self._post("tray", action))
        if self.s["tray"]:
            self.tray.start()
        if MAC:
            self.createcommand("tk::mac::ReopenApplication", self._show_window)  # Dock icon click
            self.createcommand("tk::mac::Quit", self._quit)  # Cmd+Q really quits, even from the Dock
        if start_hidden and (self.tray.active or (MAC and self.s["tray"])):  # a sign-in launch: no window
            self.after(300, self.withdraw)  # customtkinter re-shows the window during startup

    def report_callback_exception(self, exc, val, tb):
        if isinstance(val, TclError) and "bad window path name" in str(val):
            return  # customtkinter's delayed focus/deiconify firing on a dialog already closed; harmless
        text = "".join(traceback.format_exception(exc, val, tb))
        log_error(text)
        messagebox.showerror(APP_NAME, f"Something went wrong:\n\n{val}\n\nDetails saved to gui.log")

    def _set_icon(self):
        th.set_window_icon(self)

    # ------------------------------------------------------------ plumbing

    def _needs_setup(self) -> bool:
        if self.s["provider"] == "custom":
            return not self.s["custom_url"].strip()
        return not cfg.api_key(self.s)

    def _note(self, text: str, error: bool = False):
        self.status.configure(text=text, text_color=th.DANGER if error else th.MUTED)

    def _post(self, *msg):
        self.q.put(msg)  # worker threads never touch widgets directly

    def _poll(self):
        try:
            while True:
                kind, *rest = self.q.get_nowait()
                getattr(self, f"_on_{kind}")(*rest)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _save(self):
        cfg.save(self.s)

    def confirm(self, key: str, message: str, yes: str) -> bool:
        """Ask before an action unless the user turned that question off."""
        if not self.s["confirm"].get(key, True):
            return True
        ok, quiet = dlg.ConfirmDialog(self, message, yes).show()
        if ok and quiet:
            self.s["confirm"][key] = False
            self._save()
            sw = getattr(self, "confirm_sw", {}).get(key)
            if sw:
                sw.deselect()
        return ok

    def _close(self):
        if self.s["tray"] and (self.tray.active or MAC):
            self.withdraw()  # keep running (and watching) in the tray or Dock
            if not self._told_tray and self.tray.active:
                self._told_tray = True
                self.tray.notify("Still running in the tray. Right-click the icon to quit.")
            return
        self._quit()

    def _quit(self):
        if self.busy:  # killing the apply thread between move() and its log line would orphan the file
            self._show_window()
            messagebox.showinfo(APP_NAME, "Jev Sorter is still working. Wait for it to finish, or press Cancel.")
            return
        self.cancel.set()
        self.destroy()

    def destroy(self):
        self.tray.stop()
        super().destroy()

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_tray(self, action):
        if action == "open":
            self._show_window()
        elif action == "watch":
            self.watch_var.set(not self.watch_var.get())
            self._toggle_watch()
        elif action == "quit":
            self._quit()

    def _on_instance(self, folders):
        # a second launch (shortcut, or the folder right-click item) lands here instead
        for f in folders:
            self._add_folder(f)
        self._show_window()

    def show(self, name: str):
        for n, f in self.pages.items():
            if n == name:
                f.grid(row=1, column=1, sticky="nsew", padx=(0, 24), pady=(0, 14))
                self.titles[n].grid(row=0, column=1, sticky="w", pady=(16, 6))
            else:
                f.grid_forget()
                self.titles[n].grid_forget()
        for n, b in self.nav.items():
            on = n == name
            b.configure(fg_color=th.ACCENT_SOFT if on else "transparent",
                        text_color=th.ACCENT if on else th.TEXT,
                        font=th.font(14, th.SEMI if on else th.BODY))
        if name == "Categories":
            self._cat_refresh_folders()
        if name == "History":
            self._hist_refresh()

    def _style_tree(self):
        bg, fg, muted = th.pick(th.SURFACE), th.pick(th.TEXT), th.pick(th.MUTED)
        st = ttk.Style()
        st.theme_use("clam")
        st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Treeview", background=bg, fieldbackground=bg, foreground=fg,
                     rowheight=32, borderwidth=0, font=(th.BODY, 10))
        st.configure("Treeview.Heading", background=th.pick(th.SURFACE_2), foreground=muted,
                     relief="flat", font=(th.BOLD, 9), padding=(6, 7))
        st.map("Treeview", background=[("selected", th.pick(th.ACCENT_SOFT))],
               foreground=[("selected", th.pick(th.ACCENT))])
        st.map("Treeview.Heading", background=[("active", th.pick(th.BORDER))])
        for tree in (self.tree, self.cat_tree, self.hist_tree, self.hist_files):
            tree.tag_configure("err", foreground=th.pick(th.DANGER))
            tree.tag_configure("stay", foreground=muted)
        for t in self.titles.values():
            t.redraw()

    def _tree(self, parent, cols, widths, height=6):
        frame = ctk.CTkFrame(parent)
        tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings",
                            height=height, selectmode="extended")
        for (cid, title), w in zip(cols, widths):
            tree.heading(cid, text=title.upper())
            tree.column(cid, width=abs(w), stretch=w < 0, anchor="w")
        sb = ctk.CTkScrollbar(frame, command=tree.yview, width=12)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sb.pack(side="right", fill="y", padx=(2, 4), pady=8)
        return frame, tree

    # ------------------------------------------------------------ nav

    def _build_nav(self):
        bar = ctk.CTkFrame(self, width=190, corner_radius=0, border_width=0)
        bar.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=(0, 24))
        bar.grid_propagate(False)
        ctk.CTkLabel(bar, text=APP_NAME, font=th.font(19, th.BOLD)).pack(padx=18, pady=(24, 20), anchor="w")
        self.nav = {}
        for name in PAGES:
            b = ctk.CTkButton(bar, text=name, anchor="w", height=38, corner_radius=19,
                              fg_color="transparent", text_color=th.TEXT, hover_color=th.SURFACE_2,
                              font=th.font(14),
                              command=lambda n=name: self.show(n))
            b.pack(fill="x", padx=12, pady=2)
            self.nav[name] = b

    # ------------------------------------------------------------ sort page

    def _build_sort(self):
        page = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        self.pages["Sort"] = page
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)

        top = ctk.CTkFrame(page)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(top, fg_color="transparent", border_width=0)
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        th.eyebrow(head, "Folders to sort").pack(side="left")
        th.button(head, "Add folder", width=100, command=self._pick_folder).pack(side="right")
        self.folder_box = ctk.CTkFrame(top, fg_color="transparent", border_width=0)
        self.folder_box.grid(row=1, column=0, sticky="ew", padx=6, pady=6)
        th.muted(top, "Subfolders too: also sorts the loose files inside each subfolder into that subfolder's own folders. "
                 "Re-check filed: also reconsiders files already filed one level down, so they can move again.",
                 12, anchor="w", justify="left", wraplength=760).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 10))
        self._render_folders()

        bar = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
        bar.grid(row=1, column=0, sticky="ew", pady=10)
        self.btn_preview = th.button(bar, "Preview (moves nothing)", command=self._start_preview)
        self.btn_preview.pack(side="left")
        self.btn_cancel = th.button(bar, "Cancel", width=80, kind="secondary",
                                        state="disabled", command=self.cancel.set)
        self.btn_cancel.pack(side="left", padx=8)
        self.progress = ctk.CTkProgressBar(bar, width=200)
        self.progress.set(0)
        self.progress.pack(side="left", padx=8)
        self.watch_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(bar, text="Watch", variable=self.watch_var, command=self._toggle_watch).pack(side="right")
        self.watch_lbl = ctk.CTkLabel(bar, text=f"every {self.s['watch_minutes']} min (Settings)",
                                      text_color=th.MUTED)
        self.watch_lbl.pack(side="right", padx=6)

        sumbar = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
        sumbar.grid(row=2, column=0, sticky="ew")
        self.summary = ctk.CTkLabel(sumbar, text="Add a folder, then press Preview.", anchor="w")
        self.summary.pack(side="left")
        self.show_stay = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(sumbar, text="Show files that stay", variable=self.show_stay,
                        command=self._render_rows).pack(side="right", padx=(12, 0))
        th.button(sumbar, "Uncheck all", "soft", width=96, height=30,
                  command=lambda: self._check_all(False)).pack(side="right", padx=4)
        th.button(sumbar, "Check all", "soft", width=84, height=30,
                  command=lambda: self._check_all(True)).pack(side="right")

        frame, self.tree = self._tree(
            page, [("ok", ""), ("file", "File"), ("where", "Folder"), ("dest", "Move to"), ("conf", "Confidence")],
            [36, -300, 170, 200, 110])
        frame.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        self.empty = th.muted(frame, "", 14)
        self.tree.bind("<Button-1>", self._tree_click)
        self.tree.bind("<space>", lambda e: self._toggle_selected())
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        act = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
        act.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(act, text="Move selected rows to:").pack(side="left", padx=(0, 6))
        self.dest_menu = ctk.CTkOptionMenu(act, values=[NO_ROWS], width=190, command=self._override)
        self.dest_menu.set(NO_ROWS)
        self.dest_menu.configure(state="disabled")
        self.dest_menu.pack(side="left")
        self.btn_apply = th.button(act, "Move checked files", state="disabled", command=self._start_apply)
        self.btn_apply.pack(side="right")
        self.btn_undo = th.button(act, "Undo last move", width=165, kind="secondary",
                                      state="disabled", command=self._undo_last)
        self.btn_undo.pack(side="right", padx=8)
        self._render_rows()

    def _render_folders(self):
        for w in self.folder_box.winfo_children():
            w.destroy()
        if not self.s["folders"]:
            ctk.CTkLabel(self.folder_box, text="No folders yet. Try your Downloads folder.",
                         text_color=th.MUTED).pack(anchor="w", padx=6)
        for i, f in enumerate(self.s["folders"]):
            row = ctk.CTkFrame(self.folder_box, fg_color="transparent", border_width=0)
            row.pack(fill="x", pady=1)
            ok = Path(f["path"]).is_dir()
            ctk.CTkLabel(row, text=f["path"] + ("" if ok else "   (missing)"), anchor="w",
                         text_color=th.TEXT if ok else th.DANGER).pack(side="left", padx=4)
            th.button(row, "Remove", width=70, kind="secondary",
                          command=lambda i=i: self._remove_folder(i)).pack(side="right", padx=2)
            rv = ctk.BooleanVar(value=f["resort"])
            cv = ctk.BooleanVar(value=f["recursive"])
            resort = ctk.CTkCheckBox(row, text="Re-check filed", variable=rv, width=20,
                                     state="disabled" if f["recursive"] else "normal",
                                     command=lambda i=i, v=rv: self._folder_opt(i, "resort", v.get()))
            resort.pack(side="right", padx=6)
            ctk.CTkCheckBox(row, text="Subfolders too", variable=cv, width=20,
                            state="disabled" if f["resort"] else "normal",
                            command=lambda i=i, v=cv: self._folder_opt(i, "recursive", v.get())).pack(side="right", padx=6)

    def _pick_folder(self):
        d = filedialog.askdirectory(title="Choose a folder to sort")
        if d:
            self._add_folder(d)

    def _add_folder(self, path: str, save: bool = True):
        path = str(Path(path).resolve())
        if any(f["path"].lower() == path.lower() for f in self.s["folders"]):
            return
        self.s["folders"].append({"path": path, "recursive": False, "resort": False})
        if save:
            self._save()
            self._render_folders()

    def _remove_folder(self, i: int):
        if not self.confirm("remove_folder", f"Remove {self.s['folders'][i]['path']} from the list?\n\n"
                            "Your files are not touched.", "Remove"):
            return
        del self.s["folders"][i]
        self._save()
        self._render_folders()

    def _folder_opt(self, i: int, key: str, val: bool):
        # --recursive with --resort would judge a file twice, so only one at a time
        self.s["folders"][i][key] = val
        self._save()
        self._render_folders()

    # ------------------------------------------------------------ preview

    def _args(self, apply: bool = False, resort: bool = False):
        return SimpleNamespace(min_age=int(self.s["min_age"]), min_confidence=float(self.s["min_confidence"]),
                               margin=float(self.s["margin"]), resort=resort, apply=apply)

    def _set_busy(self, busy: bool):
        self.busy = busy
        self.btn_preview.configure(state="disabled" if busy else "normal")
        self.btn_cancel.configure(state="normal" if busy else "disabled")
        if not busy:
            self.progress.set(0)

    def _start_preview(self, auto: bool = False):
        """auto=True is a watch-mode tick: never opens a dialog, reports to the status line."""
        if self.busy:
            return
        folders = [f for f in self.s["folders"] if Path(f["path"]).is_dir()]
        setup = self._needs_setup()
        problem = ("Add your Jev API key (or a custom API URL) in Settings first." if setup
                   else "Add a folder to sort first." if not folders else None)
        if problem:
            if auto:
                self._note(f"Watch: {problem}", error=True)
            else:
                messagebox.showinfo(APP_NAME, problem)
                if setup:
                    self.show("Settings")
            return
        url, model = cfg.endpoint(self.s)
        key = cfg.api_key(self.s)
        self.cancel.clear()
        self._set_busy(True)
        self.summary.configure(text="Asking Jev ...")
        self._note("Previewing. Nothing is moved until you press 'Move checked files'.")
        threading.Thread(target=self._preview_worker, args=(folders, key, url, model, auto), daemon=True).start()

    def _preview_worker(self, folders, key, url, model, auto):
        usage: list = []
        plans: list[engine.FolderPlan] = []
        try:
            jobs = []
            for f in folders:
                for sub in engine.collect_jobs(Path(f["path"]), f["recursive"], int(self.s["max_depth"])):
                    jobs.append((sub, f["resort"]))
            for n, (folder, resort) in enumerate(jobs, 1):
                if self.cancel.is_set():
                    break
                self._post("progress", f"Folder {n} of {len(jobs)}: {folder.name}", 0, 1)
                plan = engine.plan_folder(
                    folder, self._args(resort=resort), key, usage_sink=usage, url=url, model=model,
                    cancel=self.cancel,
                    progress=lambda d, t, folder=folder: self._post("progress", folder.name, d, t))
                plans.append(plan)
            self._post("plans", plans, usage, auto)
        except engine.JevError as exc:
            self._post("error", str(exc), auto)
        except Exception as exc:
            log_error(traceback.format_exc())
            self._post("error", f"{type(exc).__name__}: {exc}", auto)

    def _on_progress(self, label, done, total):
        self.progress.set(done / total if total else 0)
        self.summary.configure(text=f"Asking Jev ... {label} ({done}/{total})")

    def _on_error(self, msg, auto=False):
        self._set_busy(False)
        self.summary.configure(text="Stopped.")
        self._note(msg, error=True)
        if not auto:
            messagebox.showerror(APP_NAME, msg)

    def _on_plans(self, plans, usage, auto=False):
        self._set_busy(False)
        self.plans = plans
        self.cats = {str(p.folder): p.categories for p in plans}
        self.props, self.checked = {}, set()
        for pi, plan in enumerate(plans):
            for ri, prop in enumerate(plan.proposals):
                iid = f"{pi}.{ri}"
                self.props[iid] = prop
                if prop.target:
                    self.checked.add(iid)
        self._render_rows()
        skipped = [p for p in plans if p.status]
        errs = sum(1 for p in self.props.values() if p.error)
        n_move = len(self.checked)
        text = f"{len(self.props)} files checked: {n_move} would move, {len(self.props) - n_move - errs} stay"
        if errs:
            text += f", {errs} failed"
        if self.cancel.is_set():
            text += " (cancelled)"
        self.summary.configure(text=text + ".")
        if usage:
            i, o, cost = engine.summarize_usage(usage)
            self._note(f"Jev usage: {i:,} input tokens across {len(usage)} requests (about ${cost:.4f}).")
        else:
            self._note("Done.")
        if skipped:
            if auto:
                self._note(f"Watch: {len(skipped)} folder(s) skipped ({skipped[0].status}).", error=True)
            else:
                messagebox.showwarning(APP_NAME, "Some folders were skipped:\n\n" + "\n".join(
                    f"{p.folder}: {p.status}" for p in skipped))
        if auto and self.checked:
            # the flag travels with the result, so a manual Preview can never auto-apply
            n = len(self.checked)
            hidden = self.state() != "normal"
            if self.s["auto_apply"] and self.watch_var.get():
                if hidden:
                    self.tray.notify(f"Moving {n} file{'s' if n != 1 else ''}.")
                self._start_apply(confirm=False)
            else:
                self.title(f"{APP_NAME} - {n} ready to move")
                if hidden:
                    self.tray.notify(f"{n} file{'s' if n != 1 else ''} ready to move. Open Jev Sorter to review.")

    def _row_values(self, iid: str, prop: engine.Proposal):
        mark = "☑" if iid in self.checked else ("☐" if prop.target else "")
        if prop.error:
            dest, conf = f"ERROR: {prop.error}", ""
        else:
            dest, conf = (prop.target or "(stays)"), f"{prop.confidence:.0%}"
        where = prop.current or "(loose)"
        return (mark, prop.path.name, f"{prop.folder.name} / {where}", dest, conf)

    def _render_rows(self):
        self.tree.delete(*self.tree.get_children())
        for iid, prop in self.props.items():
            if not (prop.target or prop.error or self.show_stay.get()):
                continue
            tag = "err" if prop.error else ("" if prop.target else "stay")
            self.tree.insert("", "end", iid=iid, values=self._row_values(iid, prop), tags=(tag,))
        if self.tree.get_children():
            self.empty.place_forget()
        else:
            self.empty.configure(text="Nothing to show yet. Press Preview." if not self.props else
                                 "Nothing would move. Tick \"Show files that stay\" to see why.")
            self.empty.place(relx=0.5, rely=0.6, anchor="center")
        self._refresh_apply()
        self._on_select()

    def _refresh_row(self, iid):
        if self.tree.exists(iid):
            prop = self.props[iid]
            self.tree.item(iid, values=self._row_values(iid, prop),
                           tags=("err" if prop.error else ("" if prop.target else "stay"),))

    def _refresh_apply(self):
        n = len(self.checked)
        self.btn_apply.configure(state="normal" if n and not self.busy else "disabled",
                                 text=f"Move {n} checked file{'s' if n != 1 else ''}" if n else "Move checked files")

    def _tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            iid = self.tree.identify_row(event.y)
            if iid:
                self._toggle(iid)
                return "break"

    def _toggle(self, iid):
        if not self.props[iid].target:
            return
        self.checked ^= {iid}
        self._refresh_row(iid)
        self._refresh_apply()

    def _toggle_selected(self):
        for iid in self.tree.selection():
            self._toggle(iid)

    def _check_all(self, on: bool):
        self.checked = {i for i, p in self.props.items() if p.target} if on else set()
        for iid in self.tree.get_children():
            self._refresh_row(iid)
        self._refresh_apply()

    def _on_select(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            self.dest_menu.configure(values=[NO_ROWS], state="disabled")
            self.dest_menu.set(NO_ROWS)
            return
        # rows can come from different folders: offer only what every selected row can go to
        lists = [self.cats.get(str(self.props[i].folder), []) for i in sel]
        names = [c for c in lists[0] if all(c in other for other in lists)]
        self.dest_menu.configure(values=names + [STAY_LABEL], state="normal")
        targets = {self.props[i].target for i in sel}
        self.dest_menu.set((targets.pop() or STAY_LABEL) if len(targets) == 1 else "Mixed (pick one)")

    def _override(self, choice: str):
        for iid in self.tree.selection():
            prop = self.props[iid]
            if prop.error:
                continue
            if choice == STAY_LABEL:
                prop.target = None
                self.checked.discard(iid)
            elif choice in self.cats.get(str(prop.folder), []):
                prop.target = choice
                self.checked.add(iid)  # a hand-picked destination means "yes, move it"
            self._refresh_row(iid)
        self._refresh_apply()

    # ------------------------------------------------------------ apply / undo

    def _start_apply(self, confirm: bool = True):
        props = [self.props[i] for i in sorted(self.checked) if self.props[i].target]
        if not props or self.busy:
            return
        if confirm and not self.confirm(
                "move", f"Move {len(props)} file{'s' if len(props) != 1 else ''}?\n\n"
                "Every move is logged and can be undone from History.", "Move files"):
            return
        self._set_busy(True)
        run_id = uuid.uuid4().hex[:12]
        _, model = cfg.endpoint(self.s)
        threading.Thread(target=self._apply_worker, args=(props, run_id, model), daemon=True).start()

    def _apply_worker(self, props, run_id, model):
        try:
            results = engine.apply_moves(props, run_id, min_age=int(self.s["min_age"]), model=model)
            self._post("applied", results, run_id)
        except Exception as exc:
            log_error(traceback.format_exc())
            self._post("error", f"{type(exc).__name__}: {exc}")

    def _on_applied(self, results, run_id):
        self._set_busy(False)
        moved = [r for r in results if r.dst]
        failed = [r for r in results if r.error]
        done = {id(r.proposal) for r in moved}
        for iid in [i for i, p in self.props.items() if id(p) in done]:
            del self.props[iid]
            self.checked.discard(iid)
        self._render_rows()
        if moved:
            self.last_run = run_id
            self.btn_undo.configure(state="normal")
        self.summary.configure(text=f"Moved {len(moved)} file{'s' if len(moved) != 1 else ''}."
                                    + (f" {len(failed)} skipped." if failed else ""))
        self.title(APP_NAME)
        self._note("Moved. Use 'Undo last move' or the History page to reverse it.")
        if failed:
            messagebox.showwarning(APP_NAME, "Not moved:\n\n" + "\n".join(
                f"{r.proposal.path.name}: {r.error}" for r in failed[:15]))

    def _undo_last(self):
        if self.last_run and self.confirm(
                "undo", "Put the files from the last move back where they were?", "Undo move"):
            self._undo(self.last_run)

    def _undo(self, run_id: str):
        try:
            restored, lines = engine.undo_run(run_id)
        except engine.JevError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.btn_undo.configure(state="disabled")
        self._hist_refresh()
        skipped = [ln for ln in lines if ln.startswith(("skip", "FAILED"))]
        msg = f"Restored {restored} of {len(lines)} files."
        if skipped:
            msg += "\n\nNot restored:\n" + "\n".join(skipped[:15])
        messagebox.showinfo(APP_NAME, msg)

    # ------------------------------------------------------------ watch mode

    def _toggle_watch(self):
        if self.watch_job:
            self.after_cancel(self.watch_job)
            self.watch_job = None
        if self.watch_var.get():
            self._watch_tick()
        else:
            self._note("Watch mode off.")
        self.tray.set_watching(self.watch_var.get())

    def _watch_tick(self):
        if not self.watch_var.get():
            return
        # a preview still on screen holds the user's unticks and overrides; do not wipe it
        if not self.busy and not any(p.target for p in self.props.values()):
            self._start_preview(auto=True)
        self.watch_job = self.after(max(1, int(self.s["watch_minutes"])) * 60_000, self._watch_tick)

    # ------------------------------------------------------------ categories page

    def _build_categories(self):
        page = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        self.pages["Categories"] = page
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
        head.grid(row=0, column=0, sticky="ew")
        th.muted(head, "Categories decide where files go. Write one line per folder saying what belongs in it.",
                 14, anchor="w").pack(anchor="w")
        self.cat_info = th.muted(head, "", 12, anchor="w")
        self.cat_info.pack(anchor="w")
        top = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
        top.grid(row=1, column=0, sticky="ew", pady=8)
        self.cat_folder = ctk.CTkOptionMenu(top, values=["(add a folder first)"], width=420, command=lambda _: self._cat_load())
        self.cat_folder.pack(side="left")
        th.button(top, "Presets", width=80, kind="secondary", command=self._cat_preset).pack(side="left", padx=6)
        th.button(top, "From subfolders", width=140, kind="secondary", command=self._cat_from_subfolders).pack(side="left")

        frame, self.cat_tree = self._tree(page, [("name", "Folder name"), ("desc", "What belongs in it")], [200, -600])
        frame.grid(row=2, column=0, sticky="nsew")
        self.cat_tree.bind("<<TreeviewSelect>>", self._cat_select)

        form = ctk.CTkFrame(page)
        form.grid(row=3, column=0, sticky="ew", pady=10)
        form.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(form, text="Name").grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")
        self.cat_name = ctk.CTkEntry(form)
        self.cat_name.grid(row=0, column=1, sticky="ew", padx=10, pady=(8, 2))
        ctk.CTkLabel(form, text="Description").grid(row=1, column=0, padx=10, pady=2, sticky="nw")
        self.cat_desc = ctk.CTkTextbox(form, height=64)
        self.cat_desc.grid(row=1, column=1, sticky="ew", padx=10, pady=2)
        btns = ctk.CTkFrame(form, fg_color="transparent", border_width=0)
        btns.grid(row=2, column=1, sticky="e", padx=10, pady=8)
        th.button(btns, "Remove", width=80, kind="secondary", command=self._cat_remove).pack(side="left", padx=4)
        th.button(btns, "Add / update", width=110, command=self._cat_upsert).pack(side="left", padx=4)

        bottom = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
        bottom.grid(row=4, column=0, sticky="ew")
        th.button(bottom, "Save categories", command=self._cat_save).pack(side="right")
        th.button(bottom, "Delete file (use subfolders)", kind="secondary", width=190,
                      command=self._cat_delete).pack(side="right", padx=8)

    def _cat_refresh_folders(self):
        paths = [f["path"] for f in self.s["folders"]]
        self.cat_folder.configure(values=paths or ["(add a folder first)"])
        if paths and self.cat_folder.get() not in paths:
            self.cat_folder.set(paths[0])
            self._cat_load()
        elif not paths:
            self.cat_folder.set("(add a folder first)")

    def _cat_dir(self) -> Path | None:
        p = Path(self.cat_folder.get())
        return p if p.is_dir() else None

    def _cat_load(self):
        folder = self._cat_dir()
        self.cat_rows, self.cat_raw = [], {}
        if folder:
            f = folder / engine.CONFIG_NAME
            if f.exists():
                try:
                    self.cat_raw = json.loads(f.read_text(encoding="utf-8"))
                    self.cat_rows = [[str(k), str(v)] for k, v in self.cat_raw.get("categories", {}).items()]
                    self.cat_info.configure(text=f"Editing {engine.CONFIG_NAME}")
                except (OSError, json.JSONDecodeError) as exc:
                    self.cat_info.configure(text=f"Cannot read {engine.CONFIG_NAME}: {exc}")
            else:
                self.cat_info.configure(text="No categories file: existing subfolders are used")
        self._cat_render()

    def _cat_render(self):
        self.cat_tree.delete(*self.cat_tree.get_children())
        for i, (n, d) in enumerate(self.cat_rows):
            self.cat_tree.insert("", "end", iid=str(i), values=(n, textwrap.shorten(d, 140, placeholder="\u2026")))

    def _cat_select(self, _e=None):
        sel = self.cat_tree.selection()
        if sel:
            n, d = self.cat_rows[int(sel[0])]
            self.cat_name.delete(0, "end")
            self.cat_name.insert(0, n)
            self.cat_desc.delete("1.0", "end")
            self.cat_desc.insert("1.0", d)

    def _cat_upsert(self):
        name = self.cat_name.get().strip()
        desc = self.cat_desc.get("1.0", "end").strip()
        if not name or name == engine.STAY or any(c in name for c in '\\/:*?"<>|'):
            messagebox.showwarning(APP_NAME, "Give the category a valid folder name (no \\ / : * ? \" < > |).")
            return
        if not desc:
            messagebox.showwarning(APP_NAME, "Add a one-line description. It is what Jev reads to decide.")
            return
        for row in self.cat_rows:
            if row[0].lower() == name.lower():
                row[:] = [name, desc]
                break
        else:
            self.cat_rows.append([name, desc])
        self._cat_render()

    def _cat_remove(self):
        for iid in sorted(self.cat_tree.selection(), key=int, reverse=True):
            del self.cat_rows[int(iid)]
        self._cat_render()

    def _cat_preset(self):
        picked = dlg.PickDialog(
            self, "Presets", "Pick a pack, untick anything you do not want, then add. Nothing is saved until "
            "you press Save categories, and you can edit every description afterwards.",
            presets.PACKS, {r[0] for r in self.cat_rows}, "Add").show()
        self._cat_add(picked)

    def _cat_from_subfolders(self):
        folder = self._cat_dir()
        if not folder:
            return
        entries = []
        for sub in engine.subfolders(folder):
            try:
                names = [c.name for c in sorted(sub.iterdir()) if c.is_file()][:5]
            except OSError:
                names = []
            # filenames already inside are the best description Jev can get without you writing one
            entries.append((sub.name, f"Files like: {', '.join(names)}." if names
                            else f"The folder named {sub.name!r}. Describe what belongs here."))
        if not entries:
            messagebox.showinfo(APP_NAME, "This folder has no subfolders yet.")
            return
        picked = dlg.PickDialog(
            self, "From subfolders", "These are this folder's subfolders, each described by files already "
            "inside it. Untick any you do not want as a category.",
            {"Subfolders": entries}, {r[0] for r in self.cat_rows}, "Add").show()
        self._cat_add(picked)

    def _cat_add(self, picked):
        if not picked:
            return
        self.cat_rows += [[n, d] for n, d in picked]
        self._cat_render()
        self.cat_info.configure(text=f"Added {len(picked)}. Press Save categories to keep them.")

    def _cat_save(self):
        folder = self._cat_dir()
        if not folder:
            return
        if not self.cat_rows:
            messagebox.showwarning(APP_NAME, "Add at least one category, or use 'Delete file'.")
            return
        data = dict(self.cat_raw)  # keep any _note or other keys the user wrote
        data["categories"] = {n: d for n, d in self.cat_rows}
        try:
            (folder / engine.CONFIG_NAME).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Could not save: {exc}")
            return
        self.cat_raw = data
        self.cat_info.configure(text=f"Saved {engine.CONFIG_NAME}. Folders are created on first move.")

    def _cat_delete(self):
        folder = self._cat_dir()
        f = folder / engine.CONFIG_NAME if folder else None
        if f and f.exists() and self.confirm(
                "delete_categories", f"Delete {f}?\n\nThis folder will use its existing subfolders as categories again.",
                "Delete file"):
            f.unlink()
            self._cat_load()

    # ------------------------------------------------------------ history page

    def _build_history(self):
        page = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        self.pages["History"] = page
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        page.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(page, text="Every move is recorded. Pick a run to see its files or put them back.", anchor="w").grid(row=0, column=0, sticky="ew")
        frame, self.hist_tree = self._tree(page, [("when", "When"), ("count", "Files"), ("id", "Run")], [220, 80, -200], height=6)
        frame.grid(row=1, column=0, sticky="nsew", pady=8)
        self.hist_tree.bind("<<TreeviewSelect>>", self._hist_select)
        frame2, self.hist_files = self._tree(page, [("src", "Original location"), ("dst", "Moved to"), ("conf", "Conf.")], [-380, -380, 70], height=8)
        frame2.grid(row=3, column=0, sticky="nsew")
        row = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
        row.grid(row=4, column=0, sticky="ew", pady=10)
        th.button(row, "Undo this run", command=self._hist_undo).pack(side="right")
        th.button(row, "Open log folder", width=120, kind="secondary",
                      command=lambda: engine.open_path(engine.log_path().parent) if engine.log_path().parent.exists() else None).pack(side="right", padx=8)

    def _hist_refresh(self):
        self.hist_tree.delete(*self.hist_tree.get_children())
        for r in engine.list_runs():
            try:
                when = datetime.fromisoformat(r["ts"]).astimezone().strftime("%d %b %Y, %H:%M")
            except ValueError:
                when = r["ts"]
            self.hist_tree.insert("", "end", iid=r["run_id"], values=(when, r["count"], r["run_id"]))
        self.hist_files.delete(*self.hist_files.get_children())

    def _hist_select(self, _e=None):
        sel = self.hist_tree.selection()
        self.hist_files.delete(*self.hist_files.get_children())
        if sel:
            for i, rec in enumerate(r for r in engine.read_log() if r.get("run_id") == sel[0]):
                self.hist_files.insert("", "end", iid=str(i), values=(rec["src"], rec["dst"], f"{rec.get('confidence', 0):.0%}"))

    def _hist_undo(self):
        sel = self.hist_tree.selection()
        if sel and self.confirm("undo", "Put every file in this run back where it was?", "Undo run"):
            self._undo(sel[0])

    # ------------------------------------------------------------ settings page

    def _build_settings(self):
        page = ctk.CTkScrollableFrame(self, fg_color="transparent", border_width=0)
        self.pages["Settings"] = page
        page.grid_columnconfigure(0, minsize=270)
        page.grid_columnconfigure(1, weight=1)
        r = 0

        def label(text, row, bold=False):
            lbl = ctk.CTkLabel(page, text=text, font=th.font(14, th.BOLD if bold else th.BODY))
            lbl.grid(row=row, column=0, sticky="nw", padx=6, pady=6)
            return lbl

        label("Connection", r, True)
        self.provider = th.Segmented(page, values=["Jev (TypeSafe cloud)", "Custom / local API"],
                                               command=lambda _: self._provider_changed())
        self.provider.grid(row=r, column=1, sticky="w", pady=6)
        r += 1
        label("API key", r)
        keyrow = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
        keyrow.grid(row=r, column=1, sticky="ew", pady=4)
        keyrow.grid_columnconfigure(0, weight=1)
        self.key_entry = ctk.CTkEntry(keyrow, show="•")
        self.key_entry.grid(row=0, column=0, sticky="ew")
        self.key_entry._entry.bind("<FocusIn>", lambda e: self.key_entry.get() == KEY_MASK and self.key_entry.delete(0, "end"), add="+")
        th.button(keyrow, "Show", width=60, kind="secondary", command=self._toggle_key).grid(row=0, column=1, padx=4)
        th.button(keyrow, "Clear", width=60, kind="secondary", command=self._clear_key).grid(row=0, column=2)
        r += 1
        self.key_note = ctk.CTkLabel(page, text="", text_color=th.MUTED, anchor="w")
        self.key_note.grid(row=r, column=1, sticky="w")
        r += 1
        url_lbl = label("API URL", r)
        self.url_entry = ctk.CTkEntry(page)
        self.url_entry.grid(row=r, column=1, sticky="ew", pady=4)
        r += 1
        model_lbl = label("Model", r)
        self.model_entry = ctk.CTkEntry(page)
        self.model_entry.grid(row=r, column=1, sticky="ew", pady=4)
        r += 1
        self.custom_only = (url_lbl, self.url_entry, model_lbl, self.model_entry)  # shown for Custom only
        tests = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
        tests.grid(row=r, column=1, sticky="w", pady=6)
        self.btn_test = th.button(tests, "Test connection", width=140, command=self._test_connection)
        self.btn_test.pack(side="left")
        self.test_lbl = ctk.CTkLabel(tests, text="", anchor="w")
        self.test_lbl.pack(side="left", padx=10)
        r += 1

        label("Sorting", r, True)
        r += 1

        def hint(text, row):
            th.muted(page, text, 12, anchor="w", justify="left", wraplength=560).grid(
                row=row, column=1, sticky="w", pady=(0, 8))

        self.sliders = {}
        for key, text, lo, hi, steps, note in (
                ("min_confidence", "Minimum confidence", 0.3, 0.95, 65,
                 "How sure Jev must be before a file moves. Lower moves more files but makes more "
                 "mistakes; higher is more careful and leaves more files where they are. "
                 "Recommended: 0.60 to 0.75. If good files stay put, improve the category "
                 "descriptions before lowering this."),
                ("margin", "Re-check margin", 0.0, 0.5, 50,
                 "Only used by \"Re-check filed\". A file already in a folder moves only if the new "
                 "folder scores this much higher than its current one. Higher keeps filed files "
                 "where they are. Recommended: 0.10 to 0.20.")):
            label(text, r)
            row = ctk.CTkFrame(page, fg_color="transparent", border_width=0)
            row.grid(row=r, column=1, sticky="ew")
            val = ctk.CTkLabel(row, width=44)
            sl = ctk.CTkSlider(row, from_=lo, to=hi, number_of_steps=steps,
                               command=lambda v, lbl=val: lbl.configure(text=f"{v:.2f}"))
            sl.pack(side="left", fill="x", expand=True)
            val.pack(side="left", padx=8)
            self.sliders[key] = (sl, val)
            r += 1
            hint(note, r)
            r += 1
        self.spin = {}
        for key, text, note in (
                ("min_age", "Skip files newer than (seconds)",
                 "Leaves files alone that changed this recently, so a download or save in progress "
                 "is never moved. Recommended: 30 to 120."),
                ("max_depth", "Subfolder depth",
                 "How many levels down \"Subfolders too\" goes. Recommended: 2 or 3."),
                ("watch_minutes", "Watch: rescan every (minutes)",
                 "How often Watch looks for new files while Jev Sorter is running. Recommended: 5 to 30.")):
            label(text, r)
            e = ctk.CTkEntry(page, width=80)
            e.grid(row=r, column=1, sticky="w", pady=4)
            self.spin[key] = e
            r += 1
            hint(note, r)
            r += 1
        label("Unattended Watch", r)
        self.auto_apply = ctk.CTkSwitch(page, text="Move files without asking")
        self.auto_apply.grid(row=r, column=1, sticky="w", pady=4)
        r += 1
        hint("Off: Watch only shows a preview for you to approve. On: it moves files by itself. "
             "Every move is still logged and can be undone. Recommended: off.", r)
        r += 1

        label("Background", r, True)
        self.tray_sw = ctk.CTkSwitch(page, text=f"Keep running in the {WHERE}", command=self._tray_toggled)
        self.tray_sw.grid(row=r, column=1, sticky="w", pady=4)
        r += 1
        hint("On: the close button hides the window and Jev Sorter keeps running (and watching) in the "
             + ("Dock. Click the Dock icon to reopen it, or press Cmd+Q to quit. "
                if MAC else "tray. Right-click the tray icon to open it or quit. ")
             + "Off: closing the window exits. Recommended: on."
             + ("" if sys.platform != "linux" else " On GNOME you need the AppIndicator extension to see the icon."), r)
        r += 1
        label("Startup", r)
        self.autostart_sw = ctk.CTkSwitch(page, text="Start when I sign in, hidden")
        self.autostart_sw.grid(row=r, column=1, sticky="w", pady=4)
        r += 1
        hint("Needs the background option above. Starts quietly at sign-in with no window, ready for Watch.", r)
        r += 1

        label("Ask before", r, True)
        self.confirm_sw = {}
        for key, text in CONFIRMS.items():
            sw = ctk.CTkSwitch(page, text=text)
            sw.grid(row=r, column=1, sticky="w", pady=3)
            self.confirm_sw[key] = sw
            r += 1
        hint("Turn a question off to skip it. You can also tick \"Don't ask me again\" in the question itself.", r)
        r += 1

        label("Appearance", r, True)
        self.theme = th.Segmented(page, values=["System", "Light", "Dark"])
        self.theme.grid(row=r, column=1, sticky="w", pady=6)
        r += 1
        th.button(page, "Save settings", command=self._save_settings).grid(row=r, column=1, sticky="e", pady=16)

        self._load_settings_into_form()

    def _load_settings_into_form(self):
        s = self.s
        self.provider.set("Custom / local API" if s["provider"] == "custom" else "Jev (TypeSafe cloud)")
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, s["custom_url"])
        self.model_entry.delete(0, "end")
        self.model_entry.insert(0, s["model"])
        self.key_entry.delete(0, "end")
        # the key is never shown back, so say plainly that it is still there
        if s["key"]:
            self.key_entry.insert(0, KEY_MASK)
            self.key_entry.configure(show="•")
        self.key_note.configure(text="Key saved, encrypted for this Windows user. Click the box to replace it, or Show to reveal it."
                                if s["key"] else "Paste your key from typesafe.ai. It is stored encrypted on this PC.",
                                text_color=th.OK if s["key"] else th.MUTED)
        for k, (sl, val) in self.sliders.items():
            sl.set(s[k])
            val.configure(text=f"{s[k]:.2f}")
        for k, e in self.spin.items():
            e.delete(0, "end")
            e.insert(0, str(s[k]))
        self.auto_apply.select() if s["auto_apply"] else self.auto_apply.deselect()
        self.theme.set(s["theme"])
        self.tray_sw.select() if s["tray"] else self.tray_sw.deselect()
        for k, sw in self.confirm_sw.items():
            sw.select() if s["confirm"].get(k, True) else sw.deselect()
        # the registry is the truth: the user can also turn this off in Task Manager > Startup
        self.autostart_sw.select() if tray_mod.autostart_enabled() and s["tray"] else self.autostart_sw.deselect()
        self._tray_toggled()
        self._provider_changed()

    def _tray_toggled(self):
        on = bool(self.tray_sw.get())
        if not on:
            self.autostart_sw.deselect()  # a hidden start with no tray icon would be an invisible app
        self.autostart_sw.configure(state="normal" if on else "disabled")

    def _provider_changed(self):
        custom = self.provider.get().startswith("Custom")
        for w in self.custom_only:
            w.grid() if custom else w.grid_remove()  # grid_remove remembers the cell for grid()
        if not self.s["key"]:
            self.key_note.configure(text="Optional for a local server. Stored encrypted on this PC."
                                    if custom else "Paste your key from typesafe.ai. It is stored encrypted on this PC.")

    def _toggle_key(self):
        if self.key_entry.get() in ("", KEY_MASK) and self.s["key"]:
            self.key_entry.delete(0, "end")
            self.key_entry.insert(0, cfg.decrypt_key(self.s["key"]))  # your own key, on your own screen
            self.key_entry.configure(show="")
            return
        self.key_entry.configure(show="" if self.key_entry.cget("show") else "•")

    def _clear_key(self):
        if not self.confirm("clear_key", "Remove the saved API key from this PC?", "Remove key"):
            return
        cfg.forget_key(self.s["key"])
        self.s["key"] = ""
        self.key_entry.delete(0, "end")
        self._save()
        self.key_note.configure(text="Key removed.", text_color=th.MUTED)

    def _form_settings(self) -> dict:
        s = dict(self.s)
        s["provider"] = "custom" if self.provider.get().startswith("Custom") else "typesafe"
        s["custom_url"] = self.url_entry.get().strip()
        s["model"] = self.model_entry.get().strip() or engine.MODEL
        typed = self.key_entry.get().strip()
        if typed and typed != KEY_MASK:
            s["key"] = cfg.encrypt_key(typed)
        for k, (sl, _) in self.sliders.items():
            s[k] = round(sl.get(), 2)
        for k, e in self.spin.items():
            try:
                s[k] = max(0 if k == "min_age" else 1, int(e.get()))
            except ValueError:
                raise ValueError(f"'{e.get()}' is not a whole number.")
        s["auto_apply"] = bool(self.auto_apply.get())
        s["tray"] = bool(self.tray_sw.get())
        s["confirm"] = {k: bool(sw.get()) for k, sw in self.confirm_sw.items()}
        s["autostart"] = bool(self.autostart_sw.get()) and s["tray"]
        s["theme"] = self.theme.get()
        return s

    def _save_settings(self):
        try:
            new = self._form_settings()
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc))
            return
        if new["provider"] == "custom" and not new["custom_url"].lower().startswith(("http://", "https://")):
            messagebox.showwarning(APP_NAME, "The API URL must start with http:// or https://")
            return
        if new["auto_apply"] and not self.s["auto_apply"] and not messagebox.askyesno(
                APP_NAME, "Watch mode will move files on its own, with no preview.\n"
                          "Every move is still logged and can be undone. Turn it on?"):
            new["auto_apply"] = False
        if new["tray"] and not MAC and not self.tray.active and not self.tray.start():
            messagebox.showwarning(APP_NAME, "The system tray is not available on this desktop, so the tray option is off.")
            new["tray"] = new["autostart"] = False
        if not new["tray"]:
            self.tray.stop()
        try:
            tray_mod.set_autostart(new["autostart"])
        except OSError as exc:
            messagebox.showwarning(APP_NAME, f"Could not change the Windows startup entry: {exc}")
            new["autostart"] = False
        self.tray.set_watching(self.watch_var.get())
        self.s = new
        self._save()
        ctk.set_appearance_mode(self.s["theme"])
        self._style_tree()
        self._load_settings_into_form()
        self.watch_lbl.configure(text=f"every {self.s['watch_minutes']} min (Settings)")
        self._note("Settings saved.")

    def _test_connection(self):
        try:
            s = self._form_settings()
        except ValueError as exc:
            self.test_lbl.configure(text=str(exc), text_color=th.DANGER)
            return
        url, model = cfg.endpoint(s)
        typed = self.key_entry.get().strip()
        key = cfg.api_key(s) if typed in ("", KEY_MASK) else typed
        self.btn_test.configure(state="disabled")
        self.test_lbl.configure(text="Testing ...", text_color=th.MUTED)

        def work():
            try:
                ans = engine.jev_choice(
                    {"name": "invoice_march.pdf", "ext": ".pdf"},
                    {"Invoices": "Bills and invoices.", "Photos": "Pictures.", engine.STAY: engine.STAY_DESC},
                    key, timeout=20, url=url, model=model)
                self._post("tested", f"Connected. Test file judged: {'no folder fits' if ans['choice'] == engine.STAY else ans['choice']} ({float(ans.get('confidence', 0)):.0%}).", True)
            except engine.JevError as exc:
                self._post("tested", str(exc), False)
            except Exception as exc:
                self._post("tested", f"{type(exc).__name__}: {exc}", False)

        threading.Thread(target=work, daemon=True).start()

    def _on_tested(self, msg, ok):
        self.btn_test.configure(state="normal")
        self.test_lbl.configure(text=msg, text_color=th.OK if ok else th.DANGER)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    folders = [str(Path(a).resolve()) for a in args if Path(a).is_dir()]
    box: list = []
    # one instance only: a second launch hands its folders to the running one and exits
    server = tray_mod.claim_instance(folders, lambda f: box and box[0]._post("instance", f))
    if server is None:
        return 0
    app = App(folders, start_hidden="--tray" in args)
    box.append(app)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
