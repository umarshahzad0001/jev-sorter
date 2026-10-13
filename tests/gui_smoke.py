"""Drive the real GUI against the stub server: preview -> override -> apply -> undo.
Run: py tests/gui_smoke.py [screenshot_dir]"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None

tmp = Path(tempfile.mkdtemp())
os.environ["JEVSORTER_HOME"] = str(tmp / "home")
os.environ["JEVSORTER_LOG"] = str(tmp / "moves.jsonl")
os.environ.pop("JEV_API_KEY", None)  # the real key must not leak into the test

import stub_server  # noqa: E402

srv = stub_server.serve(0)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]

box = tmp / "Downloads"
for d in ("Documents", "Images", "Archives"):
    (box / d).mkdir(parents=True)
old = time.time() - 9999
for n in ("report.pdf", "photo.png", "bundle.zip", "notes.xyz", "half.crdownload"):
    p = box / n
    p.write_text("x")
    os.utime(p, (old, old))

import jevsorter_settings as cfg  # noqa: E402

s = cfg.load()
s.update(provider="custom", custom_url=f"http://127.0.0.1:{port}/v1/systemone", model="stub", key="")
s["folders"] = [{"path": str(box), "recursive": False, "resort": False}]
cfg.save(s)

import jevsorter_gui as gui  # noqa: E402
import jevsorter as engine  # noqa: E402

WIN = sys.platform == "win32"   # the tray icon is only exercised where pystray runs beside Tk
autostart_calls = []
gui.tray_mod.set_autostart = autostart_calls.append  # never touch the real Windows startup key
assert cfg.load()["tray"] is (sys.platform != "linux") and cfg.load()["autostart"] is False, "tray default: on, except on Linux"

app = gui.App()
assert app.tray.active or not WIN, "tray should start by default on Windows"
errors = []
app.report_callback_exception = lambda e, v, t: errors.append("".join(__import__("traceback").format_exception(e, v, t)))
gui.messagebox.askyesno = lambda *a, **k: True
gui.messagebox.showinfo = gui.messagebox.showwarning = gui.messagebox.showerror = lambda *a, **k: None


def pump(until, secs=15):
    end = time.time() + secs
    while time.time() < end:
        app.update()
        if until():
            return
        time.sleep(0.02)
    raise AssertionError("timeout")


def shot(name, win=None):
    """PrintWindow renders this window only, even when other apps cover it."""
    if not shots:
        return
    win = win or app
    import ctypes
    from ctypes import wintypes
    from PIL import Image
    app.update()
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = u.GetParent(win.winfo_id()) or win.winfo_id()
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    sdc = u.GetDC(0)
    mdc = g.CreateCompatibleDC(sdc)
    bmp = g.CreateCompatibleBitmap(sdc, w, h)
    g.SelectObject(mdc, bmp)
    u.PrintWindow(hwnd, mdc, 2)
    buf = ctypes.create_string_buffer(w * h * 4)
    bi = (ctypes.c_uint32 * 10)(40, w, -h, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
    g.GetDIBits(mdc, bmp, 0, h, buf, bi, 0)
    Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB").save(shots / f"{name}.png")
    g.DeleteObject(bmp)
    g.DeleteDC(mdc)
    u.ReleaseDC(0, sdc)


def modal(cls, action, delay=700):
    """Once a dialog of this class appears, call action(dialog). Lets a blocking show() return."""
    def find():
        for w in app.winfo_children():
            if isinstance(w, cls):
                action(w)
                return
        app.after(100, find)
    app.after(delay, find)


app.update()
assert not app._needs_setup()
assert app.dest_menu.cget("state") == "disabled" and app.dest_menu.get() == gui.NO_ROWS, "no rows selected yet"
assert app.empty.winfo_ismapped(), "empty state should be visible before the first preview"
shot("sort_empty")
app._start_preview()
pump(lambda: not app.busy and app.props)
moves = {p.path.name: p.target for p in app.props.values()}
assert moves == {"report.pdf": "Documents", "photo.png": "Images", "bundle.zip": "Archives", "notes.xyz": None}, moves
assert stub_server.Handler.last_auth is None, "no key set: no Authorization header"
assert len(app.checked) == 3
shot("sort_preview")

# override: send photo.png to Archives, uncheck report.pdf
iid_photo = next(i for i, p in app.props.items() if p.path.name == "photo.png")
iid_rep = next(i for i, p in app.props.items() if p.path.name == "report.pdf")
app.tree.selection_set(iid_photo)
app.update()
assert app.dest_menu.cget("state") == "normal"
assert set(app.dest_menu.cget("values")) >= {"Archives", "Images", "Documents", gui.STAY_LABEL}, app.dest_menu.cget("values")
assert not app.empty.winfo_ismapped()
app._override("Archives")
app._toggle(iid_rep)
app._start_apply(confirm=False)
pump(lambda: not app.busy and app.last_run)
assert (box / "Archives" / "photo.png").exists() and (box / "Archives" / "bundle.zip").exists()
assert (box / "report.pdf").exists(), "unchecked file must not move"
assert (box / "half.crdownload").exists()
shot("sort_applied")

run = app.last_run
app._undo(run)
assert (box / "photo.png").exists() and (box / "bundle.zip").exists()
assert len(engine.list_runs()) == 1

# settings: test connection + save round trip
app.show("Settings")
app._test_connection()
pump(lambda: app.test_lbl.cget("text").startswith("Connected"), 10)
shot("settings")
app.pages["Settings"]._parent_canvas.yview_moveto(0.45)
shot("settings_sorting")
app.pages["Settings"]._parent_canvas.yview_moveto(0)
app.key_entry.insert(0, "sk-abc")
app._save_settings()
assert cfg.api_key(cfg.load()) == "sk-abc" and "sk-abc" not in cfg.settings_path().read_text()
assert app.key_entry.get() == gui.KEY_MASK, "a saved key must show as a masked value, not an empty box"
shot("settings_saved_key")
app._save_settings()                    # saving again with the mask untouched must keep the key
assert cfg.api_key(cfg.load()) == "sk-abc" and app.key_entry.get() == gui.KEY_MASK
app._toggle_key()                       # Show reveals the saved key
assert app.key_entry.get() == "sk-abc" and app.key_entry.cget("show") == ""
app._load_settings_into_form()
# confirmations: the dialog answers, can switch itself off for good, and Cancel really cancels
app.s["confirm"]["move"] = True
modal(gui.dlg.ConfirmDialog, lambda d: (d.quiet.set(True), d.accept()))
assert app.confirm("move", "Move 1 file?", "Move files") is True
assert app.s["confirm"]["move"] is False and cfg.load()["confirm"]["move"] is False, "don't-ask-again must persist"
assert app.confirm("move", "never shown", "Move files") is True, "a switched-off question must not open"
app.s["confirm"]["undo"] = True
modal(gui.dlg.ConfirmDialog, lambda d: d.close((False, False)))
assert app.confirm("undo", "Undo?", "Undo run") is False
modal(gui.dlg.ConfirmDialog, lambda d: shot("confirm_dialog", d) or d.accept())
app.confirm("undo", "Put every file in this run back where it was?", "Undo run")

# presets are previewed first: nothing is added or written until the user accepts and saves
app.show("Categories")
app._cat_load()
assert not (box / engine.CONFIG_NAME).exists()
before = len(app.cat_rows)
modal(gui.dlg.PickDialog, lambda d: d.close(None))
app._cat_preset()
assert len(app.cat_rows) == before, "cancelling the preview must add nothing"
seen = {}
def pick(d):
    seen["packs"] = list(d.packs)
    seen["checked"] = len(d.checked)
    d._toggle("5")                      # untick one row (Videos) so the report.pdf flow below still has Documents
    d.tree.selection_set("1")
    d.update()
    shot("presets_dialog", d)
    d.accept()
modal(gui.dlg.PickDialog, pick)
app._cat_preset()
assert len(seen["packs"]) >= 5 and seen["checked"] == len(gui.presets.PACKS[seen["packs"][0]])
assert len(app.cat_rows) == len(gui.presets.PACKS[seen["packs"][0]]) - 1, "unticked row must not be added"
assert not (box / engine.CONFIG_NAME).exists(), "adding to the list must not write the file yet"
app._cat_save()
assert (box / engine.CONFIG_NAME).exists()
app.show("History")
shot("history")
shot_cat = None
app.show("Categories")
shot("categories")

# watch-mode safety: the auto flag must not leak into a later manual Preview
app.show("Sort")
app.s["auto_apply"] = True
saved = app.s["folders"]
app.s["folders"] = []
app._start_preview(auto=True)           # nothing to sort: must leave no state behind
app.s["folders"] = saved
app.watch_var.set(True)
app._start_preview()                    # manual, with auto-apply on
pump(lambda: not app.busy and app.props)
assert (box / "report.pdf").exists(), "manual preview must never move files"
app.watch_var.set(False)
app._start_preview(auto=True)           # tick, but Watch was switched off meanwhile
pump(lambda: not app.busy and app.props)
assert (box / "report.pdf").exists(), "auto tick applied while Watch was off"
app.watch_var.set(True)
app._start_preview(auto=True)           # a real tick with auto-apply on
pump(lambda: (box / "Documents" / "report.pdf").exists())

# tray: close hides, tray "open" restores, the Quit action exits; turning tray off makes close exit
pump(lambda: not app.busy)              # let the auto-apply above finish
if WIN:
    app._close()
    app.update()
    assert app.state() == "withdrawn", "close with tray on must only hide the window"
    app._on_instance([])                # a second launch shows the window again
    assert app.state() == "normal"
    app.watch_var.set(False)
    app._on_tray("watch")               # tray menu turns Watch on (and starts a tick)
    assert app.watch_var.get() and app.tray.watching
    pump(lambda: not app.busy)
    app._on_tray("watch")
    assert not app.watch_var.get() and not app.tray.watching
app.show("Settings")
app.pages["Settings"]._parent_canvas.yview_moveto(1.0)
shot("settings_background")
app.pages["Settings"]._parent_canvas.yview_moveto(0)
app.tray_sw.deselect()
app._tray_toggled()
assert app.autostart_sw.cget("state") == "disabled"
app._save_settings()
assert not app.tray.active and cfg.load()["tray"] is False and autostart_calls[-1] is False
app.tray_sw.select()
app._tray_toggled()
app.autostart_sw.select()
app._save_settings()
assert (app.tray.active or not WIN) and cfg.load()["autostart"] is True and autostart_calls[-1] is True
app.show("Sort")

gui.ctk.set_appearance_mode("Light")   # brand has both themes; look at the other one too
app._style_tree()
for name in ("Sort", "Settings"):
    app.show(name)
    shot(f"{name.lower()}_light")

assert not errors, errors
app.destroy()
print("gui smoke OK")
