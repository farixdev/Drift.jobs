"""Runs history page (Phase 10): recent scan runs with outcomes."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QScrollArea, QVBoxLayout, QHBoxLayout, QWidget

from core import dashboard
from ui.components import Button, Card, Chip, Label
from ui.widgets import TopBar

_TONE = {"completed": "success", "running": "accent", "cancelled": "warning",
         "timeout": "warning", "failed": "danger"}


class RunsScreen(QWidget):
    back = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.reload()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.topbar = TopBar(0)
        root.addWidget(self.topbar)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        root.addWidget(self._scroll, 1)

    def reload(self):
        host = QWidget()
        self._body = QVBoxLayout(host)
        self._body.setContentsMargins(24, 18, 24, 24)
        self._body.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(Label("Runs", "title2", "primary"), 1)
        back = Button("← Back", "plain", "md"); back.clicked.connect(self.back.emit)
        head.addWidget(back)
        self._body.addLayout(head)

        runs = dashboard.recent_runs(30)
        if not runs:
            self._body.addWidget(Label("No runs yet.", "subhead", "secondary"))
        for r in runs:
            card = Card()
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 10, 14, 10)
            left = QVBoxLayout()
            left.addWidget(Label(f"Run #{r['id']} · {r['started_at'][:16]}", "subhead", "primary"))
            left.addWidget(Label(
                f"{r['jobs_found']} jobs · {r['sources_succeeded']}/{r['sources']} sources ok"
                + (f" · {r['sources_failed']} failed" if r['sources_failed'] else ""),
                "caption1", "tertiary"))
            row.addLayout(left, 1)
            row.addWidget(Chip(r["status"], _TONE.get(r["status"], "neutral")))
            self._body.addWidget(card)
        self._body.addStretch()
        self._scroll.setWidget(host)
