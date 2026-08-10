"""Overlays: Modal, Sheet, Popover, ConfirmDialog, CommandPalette (⌘K)."""
from __future__ import annotations

from PyQt5.QtCore import QEvent, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.components.base import Themed, card_shadow
from ui.components.controls import Button
from ui.components.display import Label
from ui.theme import theme, tokens
from ui.theme.motion import animate


class _Scrim(QDialog, Themed):
    """A dimmed modal backdrop hosting centered content."""

    def __init__(self, parent=None, radius=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._radius = radius or tokens.RADIUS["modal"]
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self.panel = QFrame()
        self.panel.setObjectName("Panel")
        card_shadow(self.panel, self.pal())
        self._themed()

    def restyle(self):
        p = self.pal()
        self.panel.setStyleSheet(
            f"QFrame#Panel{{background:{p.bg_overlay}; border:1px solid {p.separator_nonopaque};"
            f" border-radius:{self._radius}px;}}")

    def paintEvent(self, _):
        from PyQt5.QtGui import QColor, QPainter
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))

    def _center(self, w, h):
        if self.parent():
            g = self.parent().window().geometry()
            self.setGeometry(g)
        self.panel.setFixedSize(w, h)

    def showEvent(self, e):
        eff = QGraphicsOpacityEffect(self.panel)
        self.panel.setGraphicsEffect(eff)
        animate(eff, b"opacity", 0.0, 1.0, kind="standard")
        super().showEvent(e)


class Modal(_Scrim):
    def __init__(self, title="", parent=None, width=440, height=320):
        super().__init__(parent, radius=tokens.RADIUS["modal"])
        self._outer.addWidget(self.panel, 0, Qt.AlignCenter)
        self._center(width, height)
        col = QVBoxLayout(self.panel)
        col.setContentsMargins(24, 20, 24, 20)
        col.setSpacing(12)
        self._title = Label(title, "title3", "primary")
        col.addWidget(self._title)
        self.content = QVBoxLayout()
        col.addLayout(self.content, 1)

    def add(self, w):
        self.content.addWidget(w)


class Sheet(_Scrim):
    """Bottom-anchored sheet (slides up from the bottom edge)."""

    def __init__(self, title="", parent=None, height=360):
        super().__init__(parent, radius=tokens.RADIUS["sheet"])
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.addStretch()
        self._outer.addWidget(self.panel, 0, Qt.AlignBottom)
        if parent:
            self.panel.setFixedWidth(parent.window().width())
        self.panel.setFixedHeight(height)
        col = QVBoxLayout(self.panel)
        col.setContentsMargins(24, 16, 24, 24)
        col.setSpacing(12)
        grip = QFrame()
        grip.setFixedHeight(5)
        grip.setFixedWidth(40)
        grip.setStyleSheet(f"background:{self.pal().fill_primary}; border-radius:2px;")
        col.addWidget(grip, 0, Qt.AlignHCenter)
        self._title = Label(title, "title3", "primary")
        col.addWidget(self._title)
        self.content = QVBoxLayout()
        col.addLayout(self.content, 1)

    def add(self, w):
        self.content.addWidget(w)


class ConfirmDialog(Modal):
    """Destructive confirm with cancel + a destructive primary."""

    def __init__(self, title, message, confirm_text="Delete", parent=None):
        super().__init__(title, parent, width=400, height=200)
        self.add(Label(message, "subhead", "secondary"))
        row = QHBoxLayout()
        row.addStretch()
        cancel = Button("Cancel", "secondary", "md")
        cancel.clicked.connect(self.reject)
        confirm = Button(confirm_text, "destructive", "md")
        confirm.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(confirm)
        self.content.addStretch()
        self.content.addLayout(row)


class Popover(QFrame, Themed):
    """A small floating panel anchored near a widget (non-modal)."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("Popover")
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(10, 10, 10, 10)
        card_shadow(self, self.pal())
        self._themed()

    def add(self, w):
        self._col.addWidget(w)

    def restyle(self):
        p = self.pal()
        self.setStyleSheet(
            f"QFrame#Popover{{background:{p.bg_overlay}; border:1px solid {p.separator_nonopaque};"
            f" border-radius:{tokens.RADIUS['card']}px;}}")

    def show_at(self, global_pos):
        self.adjustSize()
        self.move(global_pos)
        self.show()


class CommandPalette(_Scrim):
    """⌘K / Ctrl+K palette: fuzzy-filter a list of commands, Enter to run."""

    def __init__(self, commands, parent=None):
        super().__init__(parent, radius=tokens.RADIUS["modal"])
        self._commands = list(commands)  # [(label, callback), ...]
        self._outer.setContentsMargins(0, 120, 0, 0)
        self._outer.addWidget(self.panel, 0, Qt.AlignTop | Qt.AlignHCenter)
        self.panel.setFixedSize(560, 400)
        col = QVBoxLayout(self.panel)
        col.setContentsMargins(12, 12, 12, 12)
        col.setSpacing(8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command…")
        self._input.setMinimumHeight(40)
        self._input.setFont(theme().font("title3"))
        self._input.textChanged.connect(self._filter)
        self._input.installEventFilter(self)
        col.addWidget(self._input)
        self._list = QListWidget()
        self._list.setFont(theme().font("subhead"))
        self._list.itemActivated.connect(self._run_item)
        col.addWidget(self._list, 1)
        self._filter("")
        self.restyle()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Down, Qt.Key_Up):
                self._list.setFocus()
                row = self._list.currentRow()
                self._list.setCurrentRow(max(0, row + (1 if event.key() == Qt.Key_Down else -1)))
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._run_item(self._list.currentItem())
                return True
            if event.key() == Qt.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(obj, event)

    def _filter(self, text):
        self._list.clear()
        q = text.lower().strip()
        for label, cb in self._commands:
            if all(part in label.lower() for part in q.split()):
                it = QListWidgetItem(label)
                it.setData(Qt.UserRole, cb)
                self._list.addItem(it)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _run_item(self, item):
        if item is None:
            return
        cb = item.data(Qt.UserRole)
        self.accept()
        if callable(cb):
            cb()

    def restyle(self):
        super().restyle()
        if not hasattr(self, "_input"):
            return  # base __init__ calls restyle before our widgets exist
        p = self.pal()
        self._input.setStyleSheet(
            f"QLineEdit{{background:transparent; border:none; border-bottom:1px solid "
            f"{p.separator_nonopaque}; color:{p.label_primary}; padding:6px 4px;}}")
        self._list.setStyleSheet(
            f"QListWidget{{background:transparent; border:none;}}"
            f"QListWidget::item{{padding:8px 10px; border-radius:{tokens.RADIUS['control']}px;"
            f" color:{p.label_primary};}}"
            f"QListWidget::item:selected{{background:{self.accent()}; color:{theme().accent_on()};}}")
