"""ThemeManager — resolves the active palette + accent and drives restyling.

A single QObject instance holds the mode (light / dark / auto), the chosen accent,
and hands out the resolved `Palette`, accent colors, and `QFont`s. Calling
`apply(app)` installs the generated global stylesheet and base font; any change
emits `themeChanged`, which custom-painted widgets connect to in order to repaint.

Preferences persist in the `setting` table (best-effort — the theme still works
before the DB exists). On Windows it also syncs the title-bar to the theme and
requests a DWM Mica backdrop; where that's unsupported the solid background
fallback in the QSS carries the look.
"""
from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QFont

from ui.theme import tokens
from ui.theme.tokens import ACCENTS, DARK, DEFAULT_ACCENT, LIGHT, Palette

_WEIGHT_MAP = {400: QFont.Normal, 500: QFont.Medium, 600: QFont.DemiBold,
               700: QFont.Bold, 800: QFont.ExtraBold}


def _os_prefers_dark() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return val == 0
    except Exception:
        return False


class ThemeManager(QObject):
    themeChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._mode = "auto"          # light | dark | auto
        self._accent = DEFAULT_ACCENT
        self._load()

    # -- persistence ------------------------------------------------------- #
    def _load(self):
        try:
            from db import get_setting
            self._mode = get_setting("ui.theme_mode", "auto") or "auto"
            self._accent = get_setting("ui.accent", DEFAULT_ACCENT) or DEFAULT_ACCENT
            if self._accent not in ACCENTS:
                self._accent = DEFAULT_ACCENT
        except Exception:
            pass

    def _save(self):
        try:
            from db import set_setting
            set_setting("ui.theme_mode", self._mode)
            set_setting("ui.accent", self._accent)
        except Exception:
            pass

    # -- resolved state ---------------------------------------------------- #
    @property
    def mode(self) -> str:
        return self._mode

    def is_dark(self) -> bool:
        if self._mode == "auto":
            return _os_prefers_dark()
        return self._mode == "dark"

    def palette(self) -> Palette:
        return DARK if self.is_dark() else LIGHT

    @property
    def accent_id(self) -> str:
        return self._accent

    def accent(self) -> str:
        return ACCENTS[self._accent]["dark" if self.is_dark() else "light"]

    def accent_on(self) -> str:
        return ACCENTS[self._accent]["on"]

    def focus_ring(self) -> str:
        """Accent at 40% for the focus ring (rgba from the accent hex)."""
        return _hex_to_rgba(self.accent(), 0.40)

    # -- mutation ---------------------------------------------------------- #
    def set_mode(self, mode: str):
        if mode in ("light", "dark", "auto") and mode != self._mode:
            self._mode = mode
            self._save()
            self._apply_current()
            self.themeChanged.emit()

    def toggle(self):
        self.set_mode("light" if self.is_dark() else "dark")

    def set_accent(self, accent_id: str):
        if accent_id in ACCENTS and accent_id != self._accent:
            self._accent = accent_id
            self._save()
            self._apply_current()
            self.themeChanged.emit()

    # -- fonts ------------------------------------------------------------- #
    def font(self, role: str = "body", *, weight: int | None = None) -> QFont:
        size, _line, w, spacing_em = tokens.TYPE_SCALE.get(role, tokens.TYPE_SCALE["body"])
        f = QFont()
        try:
            f.setFamilies(tokens.FONT_STACK)
        except AttributeError:  # very old Qt
            f.setFamily(tokens.FONT_STACK[0])
        f.setPixelSize(size)
        f.setWeight(_WEIGHT_MAP.get(weight or w, QFont.Normal))
        if spacing_em:
            f.setLetterSpacing(QFont.AbsoluteSpacing, spacing_em * size)
        return f

    def line_height(self, role: str) -> int:
        return tokens.TYPE_SCALE.get(role, tokens.TYPE_SCALE["body"])[1]

    # -- application ------------------------------------------------------- #
    def stylesheet(self) -> str:
        from ui.theme import qss
        return qss.build(self.palette(), self.accent(), self.accent_on(), self.focus_ring())

    def apply(self, app):
        self._app = app
        app.setFont(self.font("body"))
        app.setStyleSheet(self.stylesheet())

    def _apply_current(self):
        app = getattr(self, "_app", None)
        if app is not None:
            app.setFont(self.font("body"))
            app.setStyleSheet(self.stylesheet())

    # -- Windows DWM backdrop + titlebar ----------------------------------- #
    def apply_backdrop(self, window):
        """Best-effort Mica backdrop + themed title bar. Solid QSS bg is the
        fallback wherever this is unavailable, so failure is invisible."""
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = int(window.winId())
            dwm = ctypes.windll.dwmapi
            # Dark title bar to match the theme.
            dark = ctypes.c_int(1 if self.is_dark() else 0)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            # Mica system backdrop (build >= 22621).
            backdrop = ctypes.c_int(2)
            dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
        except Exception:
            pass


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


_instance: ThemeManager | None = None


def manager() -> ThemeManager:
    global _instance
    if _instance is None:
        _instance = ThemeManager()
    return _instance
