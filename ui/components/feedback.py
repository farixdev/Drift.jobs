"""Feedback surfaces: InlineBanner, Toast (+ ToastHost), EmptyState, ErrorState."""
from __future__ import annotations

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.components.base import Themed, card_shadow
from ui.components.controls import Button
from ui.components.display import Label
from ui.theme import theme, tokens
from ui.theme.motion import animate

_ICONS = {"info": "ℹ", "success": "✓", "warning": "!", "danger": "✕"}


class InlineBanner(QFrame, Themed):
    def __init__(self, text="", tone="info", parent=None):
        super().__init__(parent)
        self._tone = tone
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        self._icon = QLabel(_ICONS.get(tone, "ℹ"))
        self._icon.setFont(theme().font("subhead", weight=700))
        row.addWidget(self._icon, 0, Qt.AlignTop)
        self._text = QLabel(text)
        self._text.setWordWrap(True)
        self._text.setFont(theme().font("subhead"))
        row.addWidget(self._text, 1)
        self._themed()

    def _tone_colors(self):
        p = self.pal()
        return {"info": (p.info, p.info_bg), "success": (p.success, p.success_bg),
                "warning": (p.warning, p.warning_bg), "danger": (p.danger, p.danger_bg)}[self._tone]

    def restyle(self):
        fg, bg = self._tone_colors()
        self.setStyleSheet(f"QFrame{{background:{bg}; border-radius:{tokens.RADIUS['control']}px;}}")
        self._icon.setStyleSheet(f"color:{fg}; background:transparent;")
        self._text.setStyleSheet(f"color:{self.pal().label_primary}; background:transparent;")


class Toast(QFrame, Themed):
    def __init__(self, text="", tone="info", parent=None):
        super().__init__(parent)
        self._tone = tone
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        self._icon = QLabel(_ICONS.get(tone, "ℹ"))
        self._icon.setFont(theme().font("subhead", weight=700))
        row.addWidget(self._icon)
        self._text = QLabel(text)
        self._text.setFont(theme().font("subhead", weight=500))
        row.addWidget(self._text)
        self._themed()
        card_shadow(self, self.pal())

    def restyle(self):
        p = self.pal()
        fg = {"info": p.info, "success": p.success, "warning": p.warning,
              "danger": p.danger}[self._tone]
        self.setStyleSheet(
            f"QFrame{{background:{p.bg_overlay}; border:1px solid {p.separator_nonopaque};"
            f" border-radius:{tokens.RADIUS['control']}px;}}")
        self._icon.setStyleSheet(f"color:{fg}; background:transparent;")
        self._text.setStyleSheet(f"color:{p.label_primary}; background:transparent;")


class ToastHost(QWidget):
    """Overlay that stacks transient toasts bottom-center of its parent."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(0, 0, 0, 16)
        self._col.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
        self._col.setSpacing(8)
        self.setGeometry(parent.rect())

    def show_toast(self, text, tone="info", duration=2600):
        toast = Toast(text, tone, self)
        self._col.addWidget(toast, 0, Qt.AlignHCenter)
        eff = QGraphicsOpacityEffect(toast)
        toast.setGraphicsEffect(eff)
        animate(eff, b"opacity", 0.0, 1.0, kind="standard")
        QTimer.singleShot(duration, lambda: self._dismiss(toast, eff))

    def _dismiss(self, toast, eff):
        animate(eff, b"opacity", 1.0, 0.0, kind="standard",
                on_finished=toast.deleteLater)

    def resizeEvent(self, _):
        if self.parent():
            self.setGeometry(self.parent().rect())


class EmptyState(QWidget, Themed):
    def __init__(self, title="Nothing here yet", subtitle="", glyph="✦",
                 action_text="", parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setAlignment(Qt.AlignCenter)
        col.setSpacing(8)
        self._glyph = QLabel(glyph)
        self._glyph.setAlignment(Qt.AlignCenter)
        self._glyph.setFont(theme().font("title1"))
        self._glyph.setFixedHeight(40)
        col.addWidget(self._glyph)
        self._title = Label(title, "title3", "primary")
        self._title.setAlignment(Qt.AlignCenter)
        col.addWidget(self._title)
        self._sub = Label(subtitle, "subhead", "secondary")
        self._sub.setAlignment(Qt.AlignCenter)
        self._sub.setVisible(bool(subtitle))
        col.addWidget(self._sub)
        if action_text:
            self.action = Button(action_text, "tinted", "md")
            col.addWidget(self.action, 0, Qt.AlignCenter)
        self._themed()

    def restyle(self):
        self._glyph.setStyleSheet(f"color:{self.pal().label_quaternary};")


class ErrorState(QWidget, Themed):
    def __init__(self, title="Something went wrong", detail="", retry_text="Try again",
                 parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setAlignment(Qt.AlignCenter)
        col.setSpacing(8)
        self._glyph = QLabel("⚠")
        self._glyph.setAlignment(Qt.AlignCenter)
        self._glyph.setFont(theme().font("title1"))
        self._glyph.setFixedHeight(40)
        col.addWidget(self._glyph)
        self._title = Label(title, "title3", "primary")
        self._title.setAlignment(Qt.AlignCenter)
        col.addWidget(self._title)
        self._detail = Label(detail, "footnote", "secondary")
        self._detail.setAlignment(Qt.AlignCenter)
        self._detail.setVisible(bool(detail))
        col.addWidget(self._detail)
        self.retry = Button(retry_text, "secondary", "md")
        col.addWidget(self.retry, 0, Qt.AlignCenter)
        self._themed()

    def restyle(self):
        self._glyph.setStyleSheet(f"color:{self.pal().warning};")
