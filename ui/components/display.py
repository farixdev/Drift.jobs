"""Display components: Label, Chip, Badge, Avatar, Card, DisclosureGroup,
ProgressBar, Spinner, Skeleton."""
from __future__ import annotations

from PyQt5.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QConicalGradient, QPainter, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.components.base import Themed, card_shadow, qcolor
from ui.theme import theme, tokens
from ui.theme.motion import reduced_motion


# --------------------------------------------------------------------------- #
class Label(QLabel, Themed):
    """Type-scale label. role sets font; tone picks a label color."""

    def __init__(self, text="", role="body", tone="primary", parent=None):
        super().__init__(text, parent)
        self._role, self._tone = role, tone
        self.setFont(theme().font(role))
        self.setWordWrap(True)
        self._themed()

    def restyle(self):
        p = self.pal()
        color = {"primary": p.label_primary, "secondary": p.label_secondary,
                 "tertiary": p.label_tertiary, "accent": self.accent(),
                 "success": p.success, "danger": p.danger}.get(self._tone, p.label_primary)
        self.setStyleSheet(f"color:{color}; background:transparent;")


# --------------------------------------------------------------------------- #
class Chip(QFrame, Themed):
    """Small rounded token/tag. tone: neutral|accent|success|warning|danger."""

    removed = pyqtSignal()

    def __init__(self, text="", tone="neutral", removable=False, parent=None):
        super().__init__(parent)
        self._tone = tone
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 3, 8 if not removable else 4, 3)
        row.setSpacing(4)
        self._label = QLabel(text)
        self._label.setFont(theme().font("caption1", weight=500))
        row.addWidget(self._label)
        if removable:
            x = QPushButton("×")
            x.setCursor(Qt.PointingHandCursor)
            x.setFixedSize(16, 16)
            x.setStyleSheet("QPushButton{border:none;background:transparent;font-size:14px;}")
            x.clicked.connect(self.removed.emit)
            row.addWidget(x)
        self._themed()

    def _colors(self):
        p = self.pal()
        return {
            "neutral": (p.fill_tertiary, p.label_secondary),
            "accent": (theme().focus_ring().replace("0.40", "0.16"), self.accent()),
            "success": (p.success_bg, p.success),
            "warning": (p.warning_bg, p.warning),
            "danger": (p.danger_bg, p.danger),
        }.get(self._tone, (p.fill_tertiary, p.label_secondary))

    def restyle(self):
        bg, fg = self._colors()
        self.setStyleSheet(f"QFrame{{background:{bg}; border-radius:{tokens.RADIUS['pill']}px;}}")
        self._label.setStyleSheet(f"color:{fg}; background:transparent;")


class Badge(QLabel, Themed):
    """Count/status badge (a filled pill)."""

    def __init__(self, text="", tone="accent", parent=None):
        super().__init__(text, parent)
        self._tone = tone
        self.setAlignment(Qt.AlignCenter)
        self.setFont(theme().font("caption2", weight=700))
        self.setMinimumWidth(18)
        self._themed()

    def restyle(self):
        p = self.pal()
        bg = {"accent": self.accent(), "danger": p.danger, "success": p.success,
              "neutral": p.fill_primary}.get(self._tone, self.accent())
        fg = theme().accent_on() if self._tone == "accent" else "#FFFFFF"
        if self._tone == "neutral":
            fg = p.label_secondary
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:9px; padding:1px 6px;")


class Avatar(QLabel, Themed):
    """Circular initials avatar."""

    def __init__(self, name="", size=36, parent=None):
        super().__init__(parent)
        self._name = name
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(theme().font("subhead", weight=600))
        self._themed()

    def _initials(self):
        parts = [w for w in self._name.split() if w]
        if not parts:
            return "?"
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(qcolor(self.accent()))
        painter.drawEllipse(self.rect())
        painter.setPen(QColor(theme().accent_on()))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, self._initials())


# --------------------------------------------------------------------------- #
class Card(QFrame, Themed):
    def __init__(self, parent=None, elevated=True):
        super().__init__(parent)
        self._elevated = elevated
        self.setObjectName("Card")
        self._themed()
        if elevated:
            card_shadow(self, self.pal())

    def restyle(self):
        p = self.pal()
        self.setStyleSheet(
            f"QFrame#Card{{background:{p.bg_elevated}; border:1px solid {p.separator_nonopaque};"
            f" border-radius:{tokens.RADIUS['card']}px;}}")


class DisclosureGroup(QWidget, Themed):
    """A header row that expands/collapses its content."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self._btn = QPushButton(f"  ▸  {title}")
        self._title = title
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setCheckable(True)
        self._btn.setFont(theme().font("headline"))
        self._btn.clicked.connect(self._toggle)
        col.addWidget(self._btn)
        self._body = QWidget()
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(16, 8, 8, 8)
        self._body.setVisible(False)
        col.addWidget(self._body)
        self._themed()

    def body_layout(self):
        return self._body_lay

    def add(self, w):
        self._body_lay.addWidget(w)

    def _toggle(self):
        on = self._btn.isChecked()
        self._btn.setText(f"  {'▾' if on else '▸'}  {self._title}")
        self._body.setVisible(on)

    def restyle(self):
        p = self.pal()
        self._btn.setStyleSheet(
            f"QPushButton{{text-align:left; border:none; background:transparent;"
            f" color:{p.label_primary}; padding:8px 4px;}}"
            f"QPushButton:hover{{color:{self.accent()};}}")


# --------------------------------------------------------------------------- #
class ProgressBar(QFrame, Themed):
    def __init__(self, value=0, parent=None):
        super().__init__(parent)
        self._value = value
        self.setFixedHeight(6)
        self._themed()

    def set_value(self, v):
        self._value = max(0, min(100, v))
        self.update()

    def paintEvent(self, _):
        p = self.pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(qcolor(p.fill_tertiary))
        painter.drawRoundedRect(self.rect(), 3, 3)
        w = int(self.width() * self._value / 100)
        if w > 0:
            painter.setBrush(qcolor(self.accent()))
            painter.drawRoundedRect(QRectF(0, 0, w, self.height()), 3, 3)


class Spinner(QWidget, Themed):
    """Indeterminate spinner."""

    def __init__(self, size=24, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if not reduced_motion():
            self._timer.start(16)
        self._themed()

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(3, 3, -3, -3)
        grad = QConicalGradient(rect.center(), -self._angle)
        a = qcolor(self.accent())
        grad.setColorAt(0.0, QColor(a.red(), a.green(), a.blue(), 0))
        grad.setColorAt(1.0, a)
        pen = QPen()
        pen.setBrush(grad)
        pen.setWidth(3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)


class Skeleton(QFrame, Themed):
    """Shimmering placeholder block."""

    def __init__(self, height=16, radius=6, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._radius = radius
        self._shimmer = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if not reduced_motion():
            self._timer.start(30)
        self._themed()

    def _tick(self):
        self._shimmer = (self._shimmer + 0.03) % 1.0
        self.update()

    def paintEvent(self, _):
        p = self.pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        base = qcolor(p.fill_tertiary)
        painter.setPen(Qt.NoPen)
        painter.setBrush(base)
        painter.drawRoundedRect(self.rect(), self._radius, self._radius)
        # moving highlight
        hi = qcolor(p.fill_secondary)
        x = int(self._shimmer * self.width())
        painter.setBrush(hi)
        painter.drawRoundedRect(QRectF(x, 0, self.width() * 0.3, self.height()),
                                self._radius, self._radius)

    def restyle(self):
        self.update()
