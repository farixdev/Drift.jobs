"""Shared plumbing for components: theme-reactivity + a few paint helpers.

`Themed` wires a widget to `themeChanged` so it restyles automatically; every
component either regenerates its per-widget stylesheet or repaints in `restyle()`.
Keeping styling per-component (rather than in the global QSS) makes each one
self-contained and theme-reactive without a monolithic sheet.
"""
from __future__ import annotations

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect, QWidget

from ui.theme import theme, tokens
from ui.theme.tokens import Palette


class Themed:
    """Mixin. Call `self._themed()` at the end of __init__."""

    def _themed(self) -> None:
        theme().themeChanged.connect(self._on_theme_changed)
        self.restyle()

    def _on_theme_changed(self) -> None:
        try:
            self.restyle()
            self.update()
        except RuntimeError:
            pass  # underlying C++ widget was deleted

    def restyle(self) -> None:  # override
        ...

    @staticmethod
    def pal() -> Palette:
        return theme().palette()

    @staticmethod
    def accent() -> str:
        return theme().accent()


def card_shadow(widget: QWidget, palette: Palette) -> QGraphicsDropShadowEffect:
    """Elevation shadow for cards/sheets, tuned per palette (dark drops opacity)."""
    eff = QGraphicsDropShadowEffect(widget)
    r, g, b, a = palette.shadow_rgba
    eff.setColor(QColor(r, g, b, a))
    eff.setBlurRadius(palette.shadow_blur)
    eff.setOffset(0, palette.shadow_y)
    widget.setGraphicsEffect(eff)
    return eff


def qcolor(css: str) -> QColor:
    """Parse '#rrggbb' or 'rgba(r, g, b, a)' into a QColor."""
    css = css.strip()
    if css.startswith("#"):
        c = QColor(css)
        return c
    if css.startswith("rgba"):
        nums = css[css.index("(") + 1: css.index(")")].split(",")
        r, g, b = (int(float(nums[i])) for i in range(3))
        a = float(nums[3]) if len(nums) > 3 else 1.0
        return QColor(r, g, b, int(a * 255))
    if css.startswith("rgb"):
        nums = css[css.index("(") + 1: css.index(")")].split(",")
        r, g, b = (int(float(nums[i])) for i in range(3))
        return QColor(r, g, b)
    return QColor(css)
