"""Application tracker (Phase 9): Kanban board with drag-between-columns,
funnel metrics, per-application notes/next-action, and CSV/JSON export.
"""
from __future__ import annotations

from PyQt5.QtCore import QMimeData, Qt, pyqtSignal
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core import tracker
from ui.components import Button, Card, Label, TextField
from ui.theme import theme, tokens
from ui.widgets import TopBar

_MIME = "application/x-drift-fingerprint"


class _AppCard(QFrame):
    def __init__(self, data: dict, on_edit):
        super().__init__()
        self.data = data
        self._on_edit = on_edit
        self._drag_start = None
        self.setCursor(Qt.OpenHandCursor)
        p = theme().palette()
        self.setStyleSheet(f"QFrame{{background:{p.bg_elevated}; border:1px solid "
                           f"{p.separator_nonopaque}; border-radius:10px;}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        lay.addWidget(Label(data.get("title", "") or "—", "subhead", "primary"))
        lay.addWidget(Label(data.get("company_name", ""), "caption1", "secondary"))
        if data.get("next_action"):
            due = f" · {data['next_action_due']}" if data.get("next_action_due") else ""
            lay.addWidget(Label(f"▸ {data['next_action']}{due}", "caption2", "accent"))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_start = e.pos()

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.LeftButton) or self._drag_start is None:
            return
        if (e.pos() - self._drag_start).manhattanLength() < 12:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_MIME, (self.data.get("fingerprint") or "").encode("utf-8"))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.exec_(Qt.MoveAction)

    def mouseDoubleClickEvent(self, e):
        self._on_edit(self.data)


class _Column(QFrame):
    dropped = pyqtSignal(str, str)   # fingerprint, stage

    def __init__(self, stage: str):
        super().__init__()
        self.stage = stage
        self.setAcceptDrops(True)
        self.setFixedWidth(210)
        p = theme().palette()
        self.setStyleSheet(f"QFrame{{background:{p.bg_sidebar_solid}; border-radius:12px;}}")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 8, 8, 8)
        self._lay.setSpacing(6)
        self._header = Label(tracker.STAGE_LABELS[stage], "footnote", "secondary")
        self._lay.addWidget(self._header)
        self._cards = QVBoxLayout()
        self._cards.setSpacing(6)
        self._lay.addLayout(self._cards)
        self._lay.addStretch()

    def set_cards(self, rows, on_edit):
        while self._cards.count():
            it = self._cards.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for r in rows:
            self._cards.addWidget(_AppCard(r, on_edit))
        self._header.setText(f"{tracker.STAGE_LABELS[self.stage]}  ({len(rows)})")

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(_MIME):
            e.acceptProposedAction()

    def dropEvent(self, e):
        fp = bytes(e.mimeData().data(_MIME)).decode("utf-8")
        if fp:
            self.dropped.emit(fp, self.stage)
            e.acceptProposedAction()


class _EditDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("Application")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background:{theme().palette().bg_base};")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(8)
        root.addWidget(Label(data.get("title", ""), "title3", "primary"))
        root.addWidget(Label(data.get("company_name", ""), "subhead", "secondary"))
        self.next_action = TextField("Next action", "e.g. Follow up with recruiter")
        self.next_action.set_text(data.get("next_action") or "")
        root.addWidget(self.next_action)
        self.due = TextField("Due (YYYY-MM-DD)", "")
        self.due.set_text(data.get("next_action_due") or "")
        root.addWidget(self.due)
        root.addWidget(Label("Notes", "footnote", "secondary"))
        self.notes = QPlainTextEdit(data.get("notes") or "")
        self.notes.setFixedHeight(120)
        p = theme().palette()
        self.notes.setStyleSheet(f"QPlainTextEdit{{background:{p.control_bg}; color:{p.label_primary};"
                                 f" border:1px solid {p.control_border}; border-radius:8px; padding:8px;}}")
        root.addWidget(self.notes)
        row = QHBoxLayout()
        row.addStretch()
        cancel = Button("Cancel", "secondary", "md"); cancel.clicked.connect(self.reject)
        save = Button("Save", "primary", "md"); save.clicked.connect(self.accept)
        row.addWidget(cancel); row.addWidget(save)
        root.addLayout(row)


class TrackerScreen(QWidget):
    back = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns: dict[str, _Column] = {}
        self._build()
        self.reload()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.topbar = TopBar(0)
        root.addWidget(self.topbar)

        body = QVBoxLayout()
        body.setContentsMargins(20, 16, 20, 16)
        body.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(Label("Applications", "title2", "primary"), 1)
        exp = Button("Export CSV", "secondary", "sm"); exp.clicked.connect(lambda: self._export("csv"))
        expj = Button("Export JSON", "secondary", "sm"); expj.clicked.connect(lambda: self._export("json"))
        head.addWidget(exp); head.addWidget(expj)
        body.addLayout(head)

        self._metrics_row = QHBoxLayout()
        body.addLayout(self._metrics_row)

        cols_scroll = QScrollArea()
        cols_scroll.setWidgetResizable(True)
        cols_host = QWidget()
        self._cols_lay = QHBoxLayout(cols_host)
        self._cols_lay.setSpacing(10)
        for stage in tracker.STAGES:
            col = _Column(stage)
            col.dropped.connect(self._on_drop)
            self._columns[stage] = col
            self._cols_lay.addWidget(col)
        self._cols_lay.addStretch()
        cols_scroll.setWidget(cols_host)
        body.addWidget(cols_scroll, 1)

        back = Button("← Back", "plain", "md"); back.clicked.connect(self.back.emit)
        body.addWidget(back, 0, Qt.AlignLeft)

        wrap = QWidget(); wrap.setLayout(body)
        root.addWidget(wrap, 1)

    def reload(self):
        data = tracker.board()
        for stage, col in self._columns.items():
            col.set_cards(data.get(stage, []), self._edit)
        self._render_metrics()

    def _render_metrics(self):
        while self._metrics_row.count():
            it = self._metrics_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        m = tracker.metrics()
        tiles = [("Applications", m["applied"]), ("Response rate", f"{m['response_rate']}%"),
                 ("Interview rate", f"{m['interview_rate']}%"),
                 ("Avg days to reply", m["avg_days_to_response"] if m["avg_days_to_response"] is not None else "—")]
        for label, val in tiles:
            card = Card()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 10)
            cl.addWidget(Label(str(val), "title2", "primary"))
            cl.addWidget(Label(label, "caption1", "secondary"))
            self._metrics_row.addWidget(card)
        self._metrics_row.addStretch()

    def _on_drop(self, fingerprint, stage):
        tracker.set_stage(fingerprint, stage)
        self.reload()

    def _edit(self, data):
        dlg = _EditDialog(data, self)
        if dlg.exec_() == QDialog.Accepted:
            tracker.update(data.get("fingerprint", ""),
                          notes=dlg.notes.toPlainText(),
                          next_action=dlg.next_action.text(),
                          next_action_due=dlg.due.text() or None)
            self.reload()

    def _export(self, fmt):
        path, _ = QFileDialog.getSaveFileName(self, "Export applications",
                                             f"applications.{fmt}", f"{fmt.upper()} (*.{fmt})")
        if path:
            tracker.export(path, fmt)
