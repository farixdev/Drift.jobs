"""Buttons and small interactive controls: Button, KeyboardHint, Toggle,
Checkbox, Radio, SegmentedControl, Stepper."""
from __future__ import annotations

from PyQt5.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ui.components.base import Themed, qcolor
from ui.theme import theme, tokens
from ui.theme.motion import reduced_motion


# --------------------------------------------------------------------------- #
# Button — variants: primary | secondary | tinted | plain | destructive
# --------------------------------------------------------------------------- #
class Button(QPushButton, Themed):
    def __init__(self, text="", variant="secondary", size="md", parent=None):
        super().__init__(text, parent)
        self._variant = variant
        self._size = size
        self.setCursor(Qt.PointingHandCursor)
        h = tokens.CONTROL_H[size]
        self.setMinimumHeight(h)
        self.setFont(theme().font("subhead" if size != "lg" else "headline",
                                  weight=600 if variant in ("primary", "destructive") else 500))
        self._themed()

    def set_variant(self, variant: str):
        self._variant = variant
        self.restyle()

    def restyle(self):
        p = self.pal()
        a = self.accent()
        on = theme().accent_on()
        R = tokens.RADIUS["control"]
        pad = {"sm": "4px 12px", "md": "6px 16px", "lg": "8px 20px"}[self._size]
        v = self._variant
        if v == "primary":
            base = f"background:{a}; color:{on}; border:none;"
            hover = f"background:{_shade(a, -8)};"
            press = f"background:{_shade(a, -16)};"
        elif v == "destructive":
            d = p.danger
            base = f"background:{d}; color:#FFFFFF; border:none;"
            hover = f"background:{_shade(d, -8)};"
            press = f"background:{_shade(d, -16)};"
        elif v == "tinted":
            base = f"background:{theme().focus_ring().replace('0.40','0.16')}; color:{a}; border:none;"
            hover = f"background:{theme().focus_ring().replace('0.40','0.24')};"
            press = f"background:{theme().focus_ring().replace('0.40','0.30')};"
        elif v == "plain":
            base = f"background:transparent; color:{a}; border:none;"
            hover = f"background:{p.fill_quaternary};"
            press = f"background:{p.fill_tertiary};"
        else:  # secondary
            base = f"background:{p.fill_tertiary}; color:{p.label_primary}; border:none;"
            hover = f"background:{p.fill_secondary};"
            press = f"background:{p.fill_primary};"
        self.setStyleSheet(f"""
            QPushButton {{ {base} border-radius:{R}px; padding:{pad};
                           font-size:{15 if self._size!='lg' else 17}px; }}
            QPushButton:hover {{ {hover} }}
            QPushButton:pressed {{ {press} }}
            QPushButton:disabled {{ background:{p.fill_quaternary}; color:{p.label_quaternary}; }}
        """)


class KeyboardHint(QLabel, Themed):
    """A '⌘K' style key-combo chip."""

    def __init__(self, keys="⌘K", parent=None):
        super().__init__(keys, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(theme().font("caption1", weight=600))
        self._themed()

    def restyle(self):
        p = self.pal()
        self.setStyleSheet(
            f"background:{p.fill_tertiary}; color:{p.label_secondary};"
            f"border-radius:{tokens.RADIUS['chip']}px; padding:2px 6px;")


# --------------------------------------------------------------------------- #
# Toggle switch (custom-painted, animated thumb)
# --------------------------------------------------------------------------- #
class Toggle(QAbstractButton, Themed):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(51, 31)
        self._pos = 1.0 if checked else 0.0
        self.toggled.connect(self._animate)
        self._themed()

    def _animate(self, on):
        target = 1.0 if on else 0.0
        if reduced_motion():
            self._pos = target
            self.update()
            return
        anim = QPropertyAnimation(self, b"thumb", self)
        anim.setStartValue(self._pos)
        anim.setEndValue(target)
        anim.setDuration(tokens.DURATION["micro"])
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _get_thumb(self):
        return self._pos

    def _set_thumb(self, v):
        self._pos = v
        self.update()

    thumb = pyqtProperty(float, _get_thumb, _set_thumb)

    def paintEvent(self, _):
        p = self.pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track_off = qcolor(p.fill_primary)
        track_on = qcolor(self.accent())
        track = _mix(track_off, track_on, self._pos)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(self.rect(), 15.5, 15.5)
        d = 27
        x = 2 + self._pos * (self.width() - d - 2)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(x, 2, d, d))


# --------------------------------------------------------------------------- #
# Checkbox + Radio (custom-painted for crisp accent fills)
# --------------------------------------------------------------------------- #
class Checkbox(QAbstractButton, Themed):
    def __init__(self, text="", checked=False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(24)
        self.setFont(theme().font("subhead"))
        self._themed()

    def sizeHint(self):
        from PyQt5.QtCore import QSize
        fm = self.fontMetrics()
        return QSize(24 + fm.horizontalAdvance(self.text()), 24)

    def paintEvent(self, _):
        p = self.pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(0, (self.height() - 20) / 2, 20, 20)
        if self.isChecked():
            painter.setBrush(qcolor(self.accent()))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(box, 6, 6)
            pen = QPen(QColor(theme().accent_on()), 2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(box.left()+5), int(box.center().y()+1),
                             int(box.left()+8.5), int(box.center().y()+4))
            painter.drawLine(int(box.left()+8.5), int(box.center().y()+4),
                             int(box.left()+15), int(box.center().y()-4))
        else:
            painter.setBrush(qcolor(p.control_bg))
            painter.setPen(QPen(qcolor(p.control_border), 1.5))
            painter.drawRoundedRect(box, 6, 6)
        painter.setPen(qcolor(p.label_primary))
        painter.setFont(self.font())
        painter.drawText(QRectF(28, 0, self.width()-28, self.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, self.text())


class Radio(QAbstractButton, Themed):
    def __init__(self, text="", checked=False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(24)
        self.setFont(theme().font("subhead"))
        self._themed()

    def paintEvent(self, _):
        p = self.pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        c = self.height() / 2
        if self.isChecked():
            painter.setBrush(qcolor(self.accent()))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(0, c-10, 20, 20))
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(QRectF(6, c-4, 8, 8))
        else:
            painter.setBrush(qcolor(p.control_bg))
            painter.setPen(QPen(qcolor(p.control_border), 1.5))
            painter.drawEllipse(QRectF(1, c-9, 18, 18))
        painter.setPen(qcolor(p.label_primary))
        painter.setFont(self.font())
        painter.drawText(QRectF(28, 0, self.width()-28, self.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, self.text())


# --------------------------------------------------------------------------- #
# SegmentedControl
# --------------------------------------------------------------------------- #
class SegmentedControl(QWidget, Themed):
    changed = pyqtSignal(int)

    def __init__(self, segments, index=0, parent=None):
        super().__init__(parent)
        self._segments = list(segments)
        self._index = index
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self.setFont(theme().font("subhead", weight=500))
        self._themed()

    def current_index(self):
        return self._index

    def set_index(self, i):
        if 0 <= i < len(self._segments) and i != self._index:
            self._index = i
            self.update()
            self.changed.emit(i)

    def mousePressEvent(self, e):
        w = self.width() / max(1, len(self._segments))
        self.set_index(int(e.x() // w))

    def paintEvent(self, _):
        p = self.pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(qcolor(p.fill_tertiary))
        painter.drawRoundedRect(self.rect(), 9, 9)
        n = max(1, len(self._segments))
        w = self.width() / n
        # selected pill
        sel = QRectF(self._index * w + 2, 2, w - 4, self.height() - 4)
        painter.setBrush(qcolor(p.bg_elevated))
        painter.drawRoundedRect(sel, 7, 7)
        painter.setFont(self.font())
        for i, seg in enumerate(self._segments):
            painter.setPen(qcolor(p.label_primary if i == self._index else p.label_secondary))
            painter.drawText(QRectF(i * w, 0, w, self.height()), Qt.AlignCenter, seg)


# --------------------------------------------------------------------------- #
# Stepper
# --------------------------------------------------------------------------- #
class Stepper(QWidget, Themed):
    changed = pyqtSignal(int)

    def __init__(self, value=0, minimum=0, maximum=99, parent=None):
        super().__init__(parent)
        self._value, self._min, self._max = value, minimum, maximum
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(1)
        self._minus = Button("−", "secondary", "sm")
        self._value_lbl = QLabel(str(value))
        self._value_lbl.setAlignment(Qt.AlignCenter)
        self._value_lbl.setFixedWidth(44)
        self._value_lbl.setFont(theme().font("subhead", weight=600))
        self._plus = Button("+", "secondary", "sm")
        for b in (self._minus, self._plus):
            b.setFixedWidth(36)
        self._minus.clicked.connect(lambda: self._step(-1))
        self._plus.clicked.connect(lambda: self._step(1))
        row.addWidget(self._minus)
        row.addWidget(self._value_lbl)
        row.addWidget(self._plus)
        self._themed()

    def _step(self, d):
        v = max(self._min, min(self._max, self._value + d))
        if v != self._value:
            self._value = v
            self._value_lbl.setText(str(v))
            self.changed.emit(v)

    def value(self) -> int:
        return self._value

    def set_value(self, v: int):
        self._value = max(self._min, min(self._max, int(v)))
        self._value_lbl.setText(str(self._value))

    def restyle(self):
        self._value_lbl.setStyleSheet(f"color:{self.pal().label_primary};")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _shade(hex_color, pct):
    c = QColor(hex_color)
    f = 1 + pct / 100.0
    return QColor(max(0, min(255, int(c.red()*f))),
                  max(0, min(255, int(c.green()*f))),
                  max(0, min(255, int(c.blue()*f)))).name()


def _mix(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(int(c1.red()+(c2.red()-c1.red())*t),
                  int(c1.green()+(c2.green()-c1.green())*t),
                  int(c1.blue()+(c2.blue()-c1.blue())*t),
                  int(c1.alpha()+(c2.alpha()-c1.alpha())*t))
