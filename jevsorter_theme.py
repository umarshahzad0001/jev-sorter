"""umarca.com brand tokens for the Jev Sorter window. Every colour is a
(light, dark) pair so customtkinter swaps it with the appearance mode."""

from __future__ import annotations

import ctypes
import sys
import tkinter.font as tkfont
from pathlib import Path

import customtkinter as ctk

# (light, dark). rgba tokens from the site are flattened onto their usual ground.
BG = ("#F6F6F4", "#0D0F10")
SURFACE = ("#FFFFFF", "#16191A")
SURFACE_2 = ("#EFEFEC", "#121516")
TEXT = ("#001219", "#ECEFEF")
MUTED = ("#5A6063", "#9AA1A3")
BORDER = ("#E4E5E3", "#2A2D2E")
SCROLL = ("#C9CCCB", "#3B4042")  # scrollbar thumb: visible on a card, quieter than text
ACCENT = ("#005F73", "#94D2BD")
ACCENT_SOFT = ("#E5EEF0", "#283331")
CTA = ("#005F73", "#94D2BD")
CTA_HOVER = ("#0B7C8E", "#B4E2D1")
ON_CTA = ("#FFFFFF", "#001219")
DANGER = ("#AE2012", "#F0856B")
OK = ("#0A9396", "#94D2BD")
MARK = "#EE9B00"
# Drawn-title strokes, one per page like the site's hand-drawn layer.
STROKES = {"mark": MARK, "wave": "#0A9396", "circle": "#BB3E03", "brush": "#005F73"}

BODY, SEMI, BOLD, HEAVY, HAND = (
    "Plus Jakarta Sans", "Plus Jakarta Sans SemiBold", "Plus Jakarta Sans Bold",
    "Plus Jakarta Sans ExtraBold", "Caveat Bold")


def assets() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets"


def register_fonts() -> None:
    """Load the bundled fonts for this process only (no install, no admin)."""
    fonts = sorted((assets() / "fonts").glob("*.ttf"))
    try:
        if sys.platform == "win32":
            for ttf in fonts:
                ctypes.windll.gdi32.AddFontResourceExW(str(ttf), 0x10, 0)  # FR_PRIVATE
        elif sys.platform == "darwin":
            ct = ctypes.CDLL("/System/Library/Frameworks/CoreText.framework/CoreText")
            cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
            ct.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
            for ttf in fonts:
                raw = str(ttf).encode()
                url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
                ct.CTFontManagerRegisterFontsForURL(url, 1, None)  # kCTFontManagerScopeProcess
        else:
            fc = ctypes.CDLL("libfontconfig.so.1")
            fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            for ttf in fonts:
                fc.FcConfigAppFontAddFile(None, str(ttf).encode())
    except Exception:
        pass  # this system will not take private fonts: Tk falls back to its default font


def set_window_icon(win) -> None:
    """The app icon for a window. Windows wants an .ico, the others a PNG."""
    try:
        if sys.platform == "win32":
            win.iconbitmap(str(assets().parent / "jevsorter.ico"))
        else:
            import tkinter
            win._icon_image = tkinter.PhotoImage(file=str(assets().parent / "jevsorter.png"))  # keep a reference
            win.iconphoto(True, win._icon_image)
    except Exception:
        pass


def font(size: int = 14, family: str = BODY) -> ctk.CTkFont:
    return ctk.CTkFont(family=family, size=size)


def pick(pair: tuple[str, str]) -> str:
    return pair[1] if ctk.get_appearance_mode() == "Dark" else pair[0]


def apply_theme() -> None:
    """Overwrite customtkinter's default theme with the brand."""
    ctk.set_default_color_theme("blue")
    t = ctk.ThemeManager.theme
    t["CTkFont"].update(family=BODY, size=14)
    t["CTk"]["fg_color"] = BG
    t["CTkToplevel"]["fg_color"] = BG
    t["CTkFrame"].update(corner_radius=12, border_width=1, fg_color=SURFACE,
                         top_fg_color=SURFACE, border_color=BORDER)
    t["CTkLabel"].update(text_color=TEXT)
    t["CTkButton"].update(corner_radius=19, border_width=0, fg_color=CTA, hover_color=CTA_HOVER,
                          text_color=ON_CTA, text_color_disabled=MUTED, border_color=BORDER)
    t["CTkEntry"].update(corner_radius=9, border_width=1, fg_color=SURFACE, border_color=BORDER,
                         text_color=TEXT, placeholder_text_color=MUTED)
    t["CTkTextbox"].update(corner_radius=9, border_width=1, fg_color=SURFACE, border_color=BORDER,
                           text_color=TEXT, scrollbar_button_color=SCROLL)
    t["CTkCheckBox"].update(corner_radius=5, border_width=2, fg_color=CTA, hover_color=CTA_HOVER,
                            border_color=MUTED, checkmark_color=ON_CTA, text_color=TEXT,
                            text_color_disabled=MUTED)
    t["CTkSwitch"].update(fg_color=BORDER, progress_color=CTA, button_color=SURFACE,
                          button_hover_color=SURFACE_2, text_color=TEXT, text_color_disabled=MUTED)
    t["CTkProgressBar"].update(fg_color=BORDER, progress_color=ACCENT, border_color=BORDER)
    t["CTkSlider"].update(fg_color=BORDER, progress_color=ACCENT, button_color=CTA,
                          button_hover_color=CTA_HOVER)
    t["CTkOptionMenu"].update(corner_radius=9, fg_color=SURFACE, button_color=ACCENT_SOFT,
                              button_hover_color=BORDER, text_color=TEXT, text_color_disabled=MUTED)
    t["DropdownMenu"].update(fg_color=SURFACE, hover_color=ACCENT_SOFT, text_color=TEXT)
    t["CTkSegmentedButton"].update(corner_radius=19, fg_color=SURFACE_2, selected_color=CTA,
                                   selected_hover_color=CTA_HOVER, unselected_color=SURFACE_2,
                                   unselected_hover_color=BORDER, text_color=TEXT,
                                   text_color_disabled=MUTED)
    t["CTkScrollbar"].update(button_color=SCROLL, button_hover_color=MUTED)


def button(master, text: str, kind: str = "primary", **kw) -> ctk.CTkButton:
    """Pill button. primary is the one call to action, secondary the alternate, soft the tertiary."""
    style = {
        "primary": {},
        "secondary": dict(fg_color=SURFACE, hover_color=SURFACE_2, text_color=TEXT, border_width=1),
        "soft": dict(fg_color=ACCENT_SOFT, hover_color=BORDER, text_color=ACCENT),
    }[kind]
    if kind == "primary":  # muted-grey on a solid fill is unreadable, so dim the on-colour instead
        style = dict(text_color_disabled=("#8FB9C2", "#5E8076"))
    kw = {**dict(height=38, font=font(14, SEMI)), **style, **kw}
    return ctk.CTkButton(master, text=text, **kw)


def eyebrow(master, text: str, **kw) -> ctk.CTkLabel:
    """The site's one uppercase element."""
    return ctk.CTkLabel(master, text=text.upper(), text_color=MUTED, font=font(12, BOLD), **kw)


def muted(master, text: str = "", size: int = 13, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text, text_color=MUTED, font=font(size), **kw)


class PageTitle(ctk.CTkFrame):
    """Caveat title with one hand-drawn word, like the site's page headers."""

    def __init__(self, master, text: str, kind: str = "mark", **kw):
        super().__init__(master, fg_color="transparent", border_width=0, **kw)
        self.text, self.kind = text, kind
        self.f = tkfont.Font(family=HAND, size=-40)
        self.h = self.f.metrics("linespace") + 14
        self.canvas = ctk.CTkCanvas(self, height=self.h, highlightthickness=0, bd=0,
                                    width=self.f.measure(text) + 24)
        self.canvas.pack(anchor="w")
        self.redraw()

    def redraw(self):
        c, f = self.canvas, self.f
        c.configure(bg=pick(BG))
        c.delete("all")
        head, _, word = self.text.rpartition(" ")
        head = head + " " if head else ""
        x0 = 4 + f.measure(head)
        x1 = x0 + f.measure(word)
        base = self.h - 8
        top = base - f.metrics("ascent")
        col = STROKES[self.kind]
        if self.kind == "mark":
            if ctk.get_appearance_mode() == "Dark":  # light ink on full-strength gold would wash out
                col = "#8A5C00"
            c.create_rectangle(x0 - 3, base - (base - top) * 0.42, x1 + 3, base - 2, fill=col, outline="")
        c.create_text(4, base, text=self.text, font=f, fill=pick(TEXT), anchor="sw")
        y = base + 3
        if self.kind == "wave":
            pts = [(x, y + (3 if i % 2 else -2)) for i, x in enumerate(range(int(x0), int(x1) + 6, 7))]
            c.create_line(pts, fill=col, width=3, smooth=True, capstyle="round")
        elif self.kind == "brush":
            c.create_line(x0, y, x1, y - 2, fill=col, width=6, capstyle="round")
        elif self.kind == "circle":
            c.create_oval(x0 - 10, top - 2, x1 + 10, base + 6, outline=col, width=3)


class Segmented(ctk.CTkSegmentedButton):
    """customtkinter has one text colour for every segment, so the selected one
    (light fill) and the others (dark fill) cannot both be readable. Colour per state."""

    def _select_button_by_value(self, value):
        super()._select_button_by_value(value)
        self._buttons_dict[value].configure(text_color=ON_CTA)

    def _unselect_button_by_value(self, value):
        super()._unselect_button_by_value(value)
        self._buttons_dict[value].configure(text_color=TEXT)
