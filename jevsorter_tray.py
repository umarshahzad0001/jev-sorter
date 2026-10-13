"""System tray icon, start-with-Windows entry, and single-instance forwarding for
the Jev Sorter window. Tray callbacks run on pystray's own thread, so they only
call the function they were given; the window posts that onto its Tk thread."""

from __future__ import annotations

import json
import os
import plistlib
import shlex
import socket
import subprocess
import sys
import threading
from pathlib import Path

import jevsorter_settings as cfg
import jevsorter_theme as th

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "JevSorter"


class Tray:
    """Notification-area icon: Open, Watch folders (checkbox), Quit."""

    def __init__(self, on_action):
        self.on_action = on_action          # called with "open" | "watch" | "quit"
        self.watching = False
        self.icon = None

    @property
    def active(self) -> bool:
        return self.icon is not None

    def start(self) -> bool:
        if self.icon is not None:
            return True
        if sys.platform == "darwin":
            return False  # pystray wants macOS's main thread, which Tk's main loop already owns
        try:
            import pystray
            from PIL import Image
            image = Image.open(th.assets().parent / "jevsorter.ico")
            menu = pystray.Menu(
                pystray.MenuItem("Open Jev Sorter", lambda i, m: self.on_action("open"), default=True),
                pystray.MenuItem("Watch folders", lambda i, m: self.on_action("watch"),
                                 checked=lambda m: self.watching),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda i, m: self.on_action("quit")))
            self.icon = pystray.Icon("JevSorter", image, "Jev Sorter", menu)
            # own daemon thread: run_detached()'s thread is not a daemon, so a crash in the
            # window would leave the process (and a ghost icon) alive
            threading.Thread(target=self.icon.run, daemon=True).start()
            return True
        except Exception:  # no tray (headless, missing backend): the window then closes normally
            self.icon = None
            return False

    def stop(self):
        icon, self.icon = self.icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def set_watching(self, on: bool):
        self.watching = on
        if self.icon is not None:
            self.icon.title = "Jev Sorter (watching)" if on else "Jev Sorter"
            self.icon.update_menu()

    def notify(self, message: str, title: str = "Jev Sorter"):
        if self.icon is not None:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass


# ---------------------------------------------------------------- start at sign-in

def autostart_argv() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--tray"]
    exe = Path(sys.executable).with_name("pythonw.exe")
    return [str(exe if exe.exists() else sys.executable), str(Path(__file__).with_name("jevsorter_gui.py")), "--tray"]


def autostart_command() -> str:
    return subprocess.list2cmdline(autostart_argv()) if sys.platform == "win32" else shlex.join(autostart_argv())


def _autostart_file() -> tuple[Path, bytes]:
    """The login item for macOS (LaunchAgent) or Linux (XDG autostart): where it goes, what it says."""
    if sys.platform == "darwin":
        path = Path.home() / "Library" / "LaunchAgents" / "com.umarca.jevsorter.plist"
        body = plistlib.dumps({"Label": "com.umarca.jevsorter", "ProgramArguments": autostart_argv(),
                               "RunAtLoad": True, "ProcessType": "Interactive"})
        return path, body
    path = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart" / "jevsorter.desktop"
    body = ("[Desktop Entry]\nType=Application\nName=Jev Sorter\n"
            f"Exec={autostart_command()}\nIcon=jevsorter\nTerminal=false\n"
            "X-GNOME-Autostart-enabled=true\n").encode()
    return path, body


def set_autostart(on: bool) -> None:
    if sys.platform == "win32":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if on:
                winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_NAME)
                except FileNotFoundError:
                    pass
        return
    path, body = _autostart_file()
    if on:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    else:
        path.unlink(missing_ok=True)


def autostart_enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return bool(winreg.QueryValueEx(key, RUN_NAME)[0])
        except OSError:
            return False
    return _autostart_file()[0].exists()


# ---------------------------------------------------------------- single instance

def _port_file() -> Path:
    return cfg.settings_path().with_name("instance.port")


def claim_instance(folders: list[str], on_message) -> socket.socket | None:
    """Become the one running instance, or hand `folders` to it and return None.
    on_message(list_of_folders) runs on a helper thread for each later launch."""
    try:
        port = int(_port_file().read_text())
        with socket.create_connection(("127.0.0.1", port), timeout=1) as c:
            c.sendall(json.dumps({"folders": folders}).encode() + b"\n")
        return None
    except (OSError, ValueError):
        pass  # no live instance (missing or stale port file): we are it
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    _port_file().parent.mkdir(parents=True, exist_ok=True)
    _port_file().write_text(str(srv.getsockname()[1]))

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return  # socket closed on exit
            with conn:
                try:
                    conn.settimeout(2)
                    data = json.loads(conn.makefile().readline())
                    on_message([f for f in data.get("folders", []) if isinstance(f, str)])
                except (OSError, ValueError):
                    pass

    threading.Thread(target=serve, daemon=True).start()
    return srv


if __name__ == "__main__":
    import tempfile
    os.environ["JEVSORTER_HOME"] = tempfile.mkdtemp()
    got = []
    ev = threading.Event()
    first = claim_instance(["a"], lambda f: (got.append(f), ev.set()))
    assert first is not None, "first launch must become the instance"
    assert claim_instance(["C:/x"], lambda f: None) is None, "second launch must forward and exit"
    assert ev.wait(3) and got == [["C:/x"]], got
    try:
        first.shutdown(socket.SHUT_RDWR)  # on Linux close() alone leaves the thread in accept() still listening
    except OSError:
        pass
    first.close()
    assert claim_instance([], lambda f: None) is not None, "a stale port file must not block startup"
    assert "--tray" in autostart_command()
    # the macOS and Linux login items must parse and carry the launch command
    real = sys.platform
    try:
        os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
        sys.platform = "darwin"
        path, body = _autostart_file()
        plist = plistlib.loads(body)
        assert path.name == "com.umarca.jevsorter.plist" and plist["RunAtLoad"] is True and "--tray" in plist["ProgramArguments"]
        sys.platform = "linux"
        path, body = _autostart_file()
        assert path.name == "jevsorter.desktop" and b"Exec=" in body and b"--tray" in body
        assert path.parent.parent == Path(os.environ["XDG_CONFIG_HOME"]), "must honour XDG_CONFIG_HOME"
        set_autostart(True)
        assert autostart_enabled() and path.exists()
        set_autostart(False)
        assert not autostart_enabled()
    finally:
        sys.platform = real
    print("tray OK")
