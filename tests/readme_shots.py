"""Regenerate the README screenshots from a scripted demo run (no real key, no real files).
Run from the project root: py tests/readme_shots.py"""

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

tmp = Path(tempfile.mkdtemp())
os.environ["JEVSORTER_HOME"] = str(tmp / "home")
os.environ["JEVSORTER_LOG"] = str(tmp / "moves.jsonl")
os.environ.pop("JEV_API_KEY", None)

import stub_server  # noqa: E402

stub_server.VARY = True
srv = stub_server.serve(0)
threading.Thread(target=srv.serve_forever, daemon=True).start()

DEMO = Path(r"D:\Demo\Downloads")  # a short, believable path for the screenshots
shutil.rmtree(DEMO.parent, ignore_errors=True)
DEMO.mkdir(parents=True)

import jevsorter as engine  # noqa: E402
import jevsorter_presets as presets  # noqa: E402
import jevsorter_settings as cfg  # noqa: E402

pack = presets.PACKS["Downloads cleanup"]
(DEMO / engine.CONFIG_NAME).write_text(
    '{"categories": ' + __import__("json").dumps({n: d for n, d in pack}, indent=2) + "}", encoding="utf-8")
old = time.time() - 9999


def drop(names):
    for n in names:
        p = DEMO / n
        p.write_text("x")
        os.utime(p, (old, old))


drop(["report-Q3-2026.pdf", "budget_2027.xlsx", "pitch-deck-v3.pptx", "IMG_4821.jpg",
      "Screenshot_20261004-101530.png", "team-offsite.mp4", "voice-note-0412.m4a",
      "VSCodeSetup-x64-1.99.exe", "project-backup.zip", "meeting-notes.txt", "untitled-3"])

s = cfg.load()
s.update(provider="custom", custom_url=f"http://127.0.0.1:{srv.server_address[1]}/v1/systemone",
         model="jev-latest", key=cfg.encrypt_key("demo-key-not-real"), theme="Dark", tray=False)
s["folders"] = [{"path": str(DEMO), "recursive": False, "resort": False}]
cfg.save(s)

import customtkinter as ctk  # noqa: E402
import jevsorter_gui as gui  # noqa: E402
from shotutil import grab  # noqa: E402

gui.messagebox.showinfo = gui.messagebox.showwarning = gui.messagebox.showerror = lambda *a, **k: None
app = gui.App()
errors = []
app.report_callback_exception = lambda e, v, t: errors.append(v)


def pump(until, secs=20):
    end = time.time() + secs
    while time.time() < end:
        app.update()
        if until():
            return
        time.sleep(0.02)
    raise AssertionError("timeout")


def shot(name, win=None):
    app.update()
    grab(win or app, OUT / f"{name}.png")


def modal(cls, action, delay=700):
    def find():
        for w in app.winfo_children():
            if isinstance(w, cls):
                action(w)
                return
        app.after(100, find)
    app.after(delay, find)


def look(mode):
    ctk.set_appearance_mode(mode)
    app._style_tree()
    app.update()


app.update()
app._start_preview()
pump(lambda: not app.busy and app.props)
app.show_stay.set(True)
app._render_rows()
first = next(i for i, p in app.props.items() if p.path.name == "report-Q3-2026.pdf")
app.tree.selection_set(first)
app.update()
look("Dark")
shot("sort-dark")
look("Light")
shot("sort-light")

look("Dark")
app.show_stay.set(False)
app._render_rows()
app._start_apply(confirm=False)
pump(lambda: not app.busy and app.last_run)
drop(["invoice_ACME_0412.pdf", "holiday-photo.jpg", "logo-final.png"])
app._start_preview()
pump(lambda: not app.busy and app.props)
app._start_apply(confirm=False)
pump(lambda: not app.busy)

app.show("History")
app.update()
newest = app.hist_tree.get_children()[0]
app.hist_tree.selection_set(newest)
app.update()
shot("history")

app.show("Categories")
app._cat_load()
app.update()
shot("categories")
modal(gui.dlg.PickDialog, lambda d: (d.tree.selection_set("3"), d.update(), shot("presets", d), d.close(None)))
app._cat_preset()

app.show("Settings")
app.provider.set("Jev (TypeSafe cloud)")
app._provider_changed()
app.update()
shot("settings")


assert not errors, errors
app.destroy()
shutil.rmtree(DEMO.parent, ignore_errors=True)
print("screenshots written to", OUT)
