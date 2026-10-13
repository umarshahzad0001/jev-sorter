"""Per-user settings for the Jev Sorter GUI. The API key is never stored in plain text
where the OS offers a vault: Windows DPAPI, macOS Keychain, or the Linux Secret
Service (through the optional `keyring` package). With no vault it falls back to the
settings file, readable only by your own user."""

from __future__ import annotations

import base64
import copy
import json
import os
import sys
from pathlib import Path

import jevsorter

DEFAULTS = {
    "provider": "typesafe",         # "typesafe" or "custom"
    "custom_url": "http://localhost:8080/v1/systemone",
    "model": jevsorter.MODEL,
    "key": "",                      # a marker such as "dpapi:<base64>"; see encrypt_key
    "folders": [],                  # [{"path": str, "recursive": bool, "resort": bool}]
    "min_confidence": 0.6,
    "margin": 0.15,
    "min_age": 30,
    "max_depth": 3,
    "watch_minutes": 10,
    "auto_apply": False,
    "theme": "System",
    "tray": sys.platform != "linux",  # close hides the window; off on Linux, where GNOME has no tray
    "autostart": False,             # start at sign-in, hidden
    "confirm": {"move": True, "undo": True, "remove_folder": True,
                "clear_key": True, "delete_categories": True},   # ask before each action
}

KEYRING_SERVICE = "Jev Sorter"
KEYRING_USER = "api-key"


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    src = Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                      ctypes.POINTER(ctypes.c_char)))
    out = Blob()
    fn = (ctypes.windll.crypt32.CryptProtectData if protect
          else ctypes.windll.crypt32.CryptUnprotectData)
    args = (ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out))
    if protect:
        args = (ctypes.byref(src), "Jev Sorter API key", None, None, None, 0, ctypes.byref(out))
    if not fn(*args):
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _keyring():
    """The keyring module, or None when it is missing, disabled, or has no usable vault."""
    if os.environ.get("JEVSORTER_NO_KEYRING"):
        return None
    try:
        import keyring
        from keyring.backends import fail
        return None if isinstance(keyring.get_keyring(), fail.Keyring) else keyring
    except Exception:
        return None


def encrypt_key(key: str) -> str:
    """Store the key and return the marker saved in settings.json."""
    if not key:
        return ""
    if sys.platform == "win32":
        return "dpapi:" + base64.b64encode(_dpapi(key.encode("utf-8"), True)).decode("ascii")
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(KEYRING_SERVICE, KEYRING_USER, key)
            return "keyring:"
        except Exception:
            pass  # a locked or unavailable vault: fall through to the file
    return "file:" + base64.b64encode(key.encode("utf-8")).decode("ascii")


def decrypt_key(stored: str) -> str:
    try:
        if stored.startswith("dpapi:") and sys.platform == "win32":
            return _dpapi(base64.b64decode(stored[6:]), False).decode("utf-8")
        if stored == "keyring:":
            kr = _keyring()
            return (kr.get_password(KEYRING_SERVICE, KEYRING_USER) or "") if kr else ""
        if stored.startswith("file:"):
            return base64.b64decode(stored[5:]).decode("utf-8")
    except Exception:
        pass  # another user or machine, or a damaged file: ask for the key again
    return ""


def forget_key(stored: str) -> None:
    """Remove a key from the vault it was saved in (the settings marker is cleared by the caller)."""
    if stored == "keyring:":
        kr = _keyring()
        if kr is not None:
            try:
                kr.delete_password(KEYRING_SERVICE, KEYRING_USER)
            except Exception:
                pass


def settings_path() -> Path:
    return jevsorter.app_dir() / "settings.json"


def load() -> dict:
    # a shallow copy would let the app mutate DEFAULTS (its folders list and confirm dict)
    s = copy.deepcopy(DEFAULTS)
    try:
        s.update(json.loads(settings_path().read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
    return s


def save(s: dict) -> None:
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)  # the "file:" fallback keeps the key here, so only this user may read it
    os.replace(tmp, p)  # a crash mid-write must not wipe the settings


def api_key(s: dict) -> str:
    """Key from settings, else the JEV_API_KEY variable the CLI uses."""
    return decrypt_key(s.get("key", "")) or os.environ.get(jevsorter.KEY_ENV, "")


def endpoint(s: dict) -> tuple[str, str]:
    """(url, model) for the chosen provider."""
    if s["provider"] == "custom":
        return s["custom_url"].strip(), s["model"].strip() or jevsorter.MODEL
    return jevsorter.API_URL, jevsorter.MODEL


if __name__ == "__main__":
    import tempfile
    os.environ["JEVSORTER_NO_KEYRING"] = "1"   # a CI keychain may be locked; test the vault-free path
    enc = encrypt_key("sk-test-123")
    want = "dpapi:" if sys.platform == "win32" else "file:"
    assert enc.startswith(want), enc
    assert decrypt_key(enc) == "sk-test-123"
    if sys.platform == "win32":
        assert "sk-test-123" not in enc, "DPAPI output must not contain the key"
    assert decrypt_key("garbage") == "" and decrypt_key("dpapi:!!!") == "" and decrypt_key("keyring:") == ""
    assert decrypt_key("file:" + base64.b64encode(b"k").decode()) == "k"
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["JEVSORTER_HOME"] = tmp
        s = load()
        assert s == DEFAULTS
        s["key"] = enc
        s["folders"] = [{"path": "C:/x", "recursive": True, "resort": False}]
        save(s)
        assert load()["folders"][0]["path"] == "C:/x" and api_key(load()) == "sk-test-123"
        assert endpoint(load())[0] == jevsorter.API_URL
        if sys.platform != "win32":
            assert oct(settings_path().stat().st_mode & 0o777) == "0o600", "settings must be owner-only"
        forget_key(enc)  # a no-op for non-keyring markers; must not raise
    print("settings OK")
