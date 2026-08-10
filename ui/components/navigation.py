"""Navigation chrome: Sidebar (collapsible, sectioned), Toolbar, TabBar."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.components.base import Themed
from ui.components.display import Badge
from ui.theme import theme, tokens


class _NavItem(QPushButton, Themed):
    def __init__(self, key, label, glyph="", badge=None, parent=None):
        super().__init__(parent)
        self.key = key
        self._label = label
        self._glyph = glyph
        self._selected = False
        self._collapsed = False
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setMinimumHeight(34)
        self.setFont(theme().font("subhead", weight=500))
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(10)
        self._glyph_lbl = QLabel(glyph)
        self._glyph_lbl.setFixedWidth(18)
        self._glyph_lbl.setAlignment(Qt.AlignCenter)
        row.addWidget(self._glyph_lbl)
        self._text_lbl = QLabel(label)
        self._text_lbl.setFont(theme().font("subhead", weight=500))
        row.addWidget(self._text_lbl, 1)
        self._badge = None
        if badge is not None:
            self._badge = Badge(str(badge), "neutral")
            row.addWidget(self._badge)
        self._themed()

    def set_selected(self, on):
        self._selected = on
        self.setChecked(on)
        self.restyle()

    def set_collapsed(self, on):
        self._collapsed = on
        self._text_lbl.setVisible(not on)
        if self._badge:
            self._badge.setVisible(not on)

    def restyle(self):
        p = self.pal()
        bg = theme().focus_ring().replace("0.40", "0.16") if self._selected else "transparent"
        fg = self.accent() if self._selected else p.label_primary
        self.setStyleSheet(
            f"QPushButton{{background:{bg}; border:none; border-radius:{tokens.RADIUS['control']}px; text-align:left;}}"
            f"QPushButton:hover{{background:{p.fill_quaternary if not self._selected else bg};}}")
        self._glyph_lbl.setStyleSheet(f"color:{fg}; background:transparent;")
        self._text_lbl.setStyleSheet(f"color:{fg}; background:transparent;")


class Sidebar(QFrame, Themed):
    selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._items: dict[str, _NavItem] = {}
        self._collapsed = False
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(10, 14, 10, 14)
        self._col.setSpacing(2)
        self._sections: list[QLabel] = []
        self.setFixedWidth(220)
        self._themed()

    def add_section(self, title):
        lbl = QLabel(title.upper())
        lbl.setFont(theme().font("caption2", weight=700))
        lbl.setContentsMargins(12, 12, 0, 4)
        self._sections.append(lbl)
        self._col.addWidget(lbl)

    def add_item(self, key, label, glyph="", badge=None):
        item = _NavItem(key, label, glyph, badge)
        item.clicked.connect(lambda: self.select(key))
        self._items[key] = item
        self._col.addWidget(item)
        if len(self._items) == 1:
            self.select(key)
        return item

    def add_stretch(self):
        self._col.addStretch()

    def select(self, key):
        for k, item in self._items.items():
            item.set_selected(k == key)
        self.selected.emit(key)

    def toggle_collapsed(self):
        self._collapsed = not self._collapsed
        self.setFixedWidth(64 if self._collapsed else 220)
        for item in self._items.values():
            item.set_collapsed(self._collapsed)
        for s in self._sections:
            s.setVisible(not self._collapsed)

    def restyle(self):
        p = self.pal()
        self.setStyleSheet(
            f"QFrame#Sidebar{{background:{p.bg_sidebar_solid}; border:none;"
            f" border-right:1px solid {p.separator_nonopaque};}}")
        for s in self._sections:
            s.setStyleSheet(f"color:{p.label_tertiary}; background:transparent;")


class Toolbar(QFrame, Themed):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Toolbar")
        self.setFixedHeight(52)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(16, 8, 16, 8)
        self._row.setSpacing(10)
        self._themed()

    def row(self):
        return self._row

    def add_left(self, w):
        self._row.addWidget(w)

    def add_stretch(self):
        self._row.addStretch()

    def add_right(self, w):
        self._row.addWidget(w)

    def restyle(self):
        p = self.pal()
        self.setStyleSheet(
            f"QFrame#Toolbar{{background:{p.bg_sidebar_solid};"
            f" border-bottom:1px solid {p.separator_nonopaque};}}")


class TabBar(QWidget, Themed):
    changed = pyqtSignal(int)

    def __init__(self, tabs, index=0, parent=None):
        super().__init__(parent)
        self._index = index
        self._btns: list[QPushButton] = []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for i, t in enumerate(tabs):
            b = QPushButton(t)
            b.setCursor(Qt.PointingHandCursor)
            b.setCheckable(True)
            b.setChecked(i == index)
            b.setFont(theme().font("subhead", weight=600))
            b.clicked.connect(lambda _=False, idx=i: self.set_index(idx))
            self._btns.append(b)
            row.addWidget(b)
        row.addStretch()
        self._themed()

    def set_index(self, i):
        self._index = i
        for j, b in enumerate(self._btns):
            b.setChecked(j == i)
        self.restyle()
        self.changed.emit(i)

    def restyle(self):
        p = self.pal()
        for j, b in enumerate(self._btns):
            on = j == self._index
            b.setStyleSheet(
                f"QPushButton{{border:none; background:transparent; padding:6px 10px;"
                f" color:{self.accent() if on else p.label_secondary};"
                f" border-bottom:2px solid {self.accent() if on else 'transparent'};}}")
