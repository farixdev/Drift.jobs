"""DataTable — a virtualised, sortable table with a sticky header.

Built on QTableView + a lightweight model so it stays smooth at thousands of
rows (Qt only realises visible cells). Zebra-free, tabular figures, sortable by
clicking a header (Phase 8/10 feed it real job data)."""
from __future__ import annotations

from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from ui.components.base import Themed
from ui.theme import theme, tokens


class _Model(QAbstractTableModel):
    def __init__(self, headers, rows, numeric_cols=()):
        super().__init__()
        self._headers = headers
        self._rows = rows
        self._numeric = set(numeric_cols)

    def rowCount(self, _=None):
        return len(self._rows)

    def columnCount(self, _=None):
        return len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        value = self._rows[index.row()][index.column()]
        if role == Qt.DisplayRole:
            return str(value)
        if role == Qt.TextAlignmentRole and index.column() in self._numeric:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._headers[section]
        return QVariant()

    def sort(self, col, order=Qt.AscendingOrder):
        self.layoutAboutToBeChanged.emit()
        numeric = col in self._numeric

        def key(r):
            v = r[col]
            if numeric:
                try:
                    return float(str(v).replace("%", "").replace("$", "").replace(",", ""))
                except ValueError:
                    return 0
            return str(v).lower()
        self._rows.sort(key=key, reverse=(order == Qt.DescendingOrder))
        self.layoutChanged.emit()


class DataTable(QTableView, Themed):
    def __init__(self, headers, rows, numeric_cols=(), parent=None):
        super().__init__(parent)
        self.setModel(_Model(headers, rows, numeric_cols))
        self.setSortingEnabled(True)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setHighlightSections(False)
        self.setFont(theme().font("subhead"))
        self.verticalHeader().setDefaultSectionSize(38)
        self._themed()

    def restyle(self):
        p = self.pal()
        self.setStyleSheet(f"""
            QTableView {{ background:{p.bg_elevated}; alternate-background-color:{p.bg_elevated};
                border:1px solid {p.separator_nonopaque}; border-radius:{tokens.RADIUS['card']}px;
                gridline-color:transparent; color:{p.label_primary};
                selection-background-color:{theme().focus_ring().replace('0.40','0.16')};
                selection-color:{p.label_primary}; }}
            QTableView::item {{ padding:6px 10px; border-bottom:1px solid {p.separator_nonopaque}; }}
            QHeaderView::section {{ background:{p.bg_sidebar_solid}; color:{p.label_secondary};
                border:none; border-bottom:1px solid {p.separator_opaque};
                padding:8px 10px; font-weight:600; }}
        """)
