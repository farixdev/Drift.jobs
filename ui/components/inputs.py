"""Text inputs: TextField (with inline validation), SearchField, Select,
ChipInput (token input)."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ui.components.base import Themed
from ui.components.display import Chip
from ui.theme import theme, tokens


class TextField(QWidget, Themed):
    """Labeled text field with helper text and an inline error/valid state."""

    textChanged = pyqtSignal(str)

    def __init__(self, label="", placeholder="", helper="", parent=None):
        super().__init__(parent)
        self._helper = helper
        self._state = "normal"  # normal | error | valid
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        self._label = QLabel(label)
        self._label.setFont(theme().font("footnote", weight=600))
        if not label:
            self._label.hide()
        col.addWidget(self._label)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._edit.setMinimumHeight(tokens.CONTROL_H["lg"])
        self._edit.setFont(theme().font("subhead"))
        self._edit.textChanged.connect(self.textChanged.emit)
        col.addWidget(self._edit)
        self._msg = QLabel(helper)
        self._msg.setFont(theme().font("caption1"))
        self._msg.setWordWrap(True)
        if not helper:
            self._msg.hide()
        col.addWidget(self._msg)
        self._themed()

    def text(self):
        return self._edit.text()

    def set_text(self, t):
        self._edit.setText(t)

    def line_edit(self):
        return self._edit

    def set_error(self, message=""):
        self._state = "error" if message else "normal"
        self._msg.setText(message or self._helper)
        self._msg.setVisible(bool(message or self._helper))
        self.restyle()

    def set_valid(self, message=""):
        self._state = "valid"
        self._msg.setText(message or self._helper)
        self._msg.setVisible(bool(message or self._helper))
        self.restyle()

    def restyle(self):
        p = self.pal()
        border = {"normal": p.control_border, "error": p.danger,
                  "valid": p.success}[self._state]
        focus = self.accent() if self._state == "normal" else border
        self._label.setStyleSheet(f"color:{p.label_secondary};")
        msg_color = {"normal": p.label_tertiary, "error": p.danger,
                     "valid": p.success}[self._state]
        self._msg.setStyleSheet(f"color:{msg_color};")
        self._edit.setStyleSheet(f"""
            QLineEdit {{ background:{p.control_bg}; color:{p.label_primary};
                border:1px solid {border}; border-radius:{tokens.RADIUS['control']}px;
                padding:0 12px; font-size:15px;
                selection-background-color:{self.accent()}; }}
            QLineEdit:focus {{ border:1px solid {focus}; }}
        """)


class SearchField(QLineEdit, Themed):
    def __init__(self, placeholder="Search", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(tokens.CONTROL_H["md"])
        self.setFont(theme().font("subhead"))
        self.setClearButtonEnabled(True)
        self.addAction(_magnifier(), QLineEdit.LeadingPosition)
        self._themed()

    def restyle(self):
        p = self.pal()
        self.setStyleSheet(f"""
            QLineEdit {{ background:{p.fill_tertiary}; color:{p.label_primary};
                border:1px solid transparent; border-radius:{tokens.RADIUS['control']}px;
                padding:0 10px; font-size:15px;
                selection-background-color:{self.accent()}; }}
            QLineEdit:focus {{ background:{p.control_bg}; border:1px solid {self.accent()}; }}
        """)


class Select(QComboBox, Themed):
    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        if items:
            self.addItems(items)
        self.setMinimumHeight(tokens.CONTROL_H["md"])
        self.setFont(theme().font("subhead"))
        self.setCursor(Qt.PointingHandCursor)
        self._themed()

    def restyle(self):
        p = self.pal()
        self.setStyleSheet(f"""
            QComboBox {{ background:{p.control_bg}; color:{p.label_primary};
                border:1px solid {p.control_border};
                border-radius:{tokens.RADIUS['control']}px; padding:0 12px; font-size:15px; }}
            QComboBox:focus {{ border:1px solid {self.accent()}; }}
            QComboBox::drop-down {{ border:none; width:22px; }}
            QComboBox QAbstractItemView {{ background:{p.bg_overlay};
                border:1px solid {p.separator_nonopaque};
                border-radius:{tokens.RADIUS['control']}px; padding:4px;
                selection-background-color:{self.accent()};
                selection-color:{theme().accent_on()}; }}
        """)


class ChipInput(QWidget, Themed):
    """Token input: type + Enter to add a chip; chips are removable."""

    changed = pyqtSignal(list)

    def __init__(self, placeholder="Add and press Enter", tokens_=None, parent=None):
        super().__init__(parent)
        self._tokens = list(tokens_ or [])
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(0, 0, 0, 0)
        self._col.setSpacing(8)
        self._chips_host = QWidget()
        self._chips_row = QHBoxLayout(self._chips_host)
        self._chips_row.setContentsMargins(0, 0, 0, 0)
        self._chips_row.setSpacing(6)
        self._chips_row.addStretch()
        self._col.addWidget(self._chips_host)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._edit.setMinimumHeight(tokens.CONTROL_H["md"])
        self._edit.setFont(theme().font("subhead"))
        self._edit.returnPressed.connect(self._add_current)
        self._col.addWidget(self._edit)
        self._themed()
        self._rebuild()

    def tokens(self):
        return list(self._tokens)

    def _add_current(self):
        t = self._edit.text().strip()
        if t and t not in self._tokens:
            self._tokens.append(t)
            self._edit.clear()
            self._rebuild()
            self.changed.emit(self.tokens())

    def _remove(self, t):
        if t in self._tokens:
            self._tokens.remove(t)
            self._rebuild()
            self.changed.emit(self.tokens())

    def _rebuild(self):
        while self._chips_row.count() > 1:
            item = self._chips_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for t in self._tokens:
            chip = Chip(t, removable=True)
            chip.removed.connect(lambda _=False, tok=t: self._remove(tok))
            self._chips_row.insertWidget(self._chips_row.count() - 1, chip)
        self._chips_host.setVisible(bool(self._tokens))

    def restyle(self):
        p = self.pal()
        self._edit.setStyleSheet(f"""
            QLineEdit {{ background:{p.control_bg}; color:{p.label_primary};
                border:1px solid {p.control_border};
                border-radius:{tokens.RADIUS['control']}px; padding:0 12px; font-size:15px; }}
            QLineEdit:focus {{ border:1px solid {self.accent()}; }}
        """)


def _magnifier():
    from PyQt5.QtGui import QIcon, QPixmap, QPainter, QPen, QColor
    from PyQt5.QtCore import QRectF, Qt
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    pr = QPainter(pm)
    pr.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(theme().palette().label_tertiary.replace("rgba", "").split(",")[0] if False else "#8E8E93"), 1.6)
    pr.setPen(pen)
    pr.drawEllipse(QRectF(2, 2, 8, 8))
    pr.drawLine(9, 9, 13, 13)
    pr.end()
    return QIcon(pm)
