"""Capture one window to a PNG with PrintWindow, so other apps covering it never end up in the image."""

import ctypes
from ctypes import wintypes
from pathlib import Path

from PIL import Image


def grab(win, path: Path) -> None:
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
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    img.save(path, optimize=True)
    g.DeleteObject(bmp)
    g.DeleteDC(mdc)
    u.ReleaseDC(0, sdc)
