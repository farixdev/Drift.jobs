"""Live run view (Phase 7) — per-source status, streaming counts, cancel.

Consumes the engine's event stream (forwarded by ScanWorker) and renders each
source's queued → running → done/failed/blocked transition with a live job count,
an overall progress bar, elapsed time, and a collapsible log. Built on the Phase-1
component library.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.scraper import SOURCES as _CATALOG
from ui.components import Button, Card, Chip, Label, ProgressBar, Spinner
from ui.components.base import Themed
from ui.theme import theme, tokens
from ui.widgets import TopBar

_NAMES = {s["key"]: s["label"] for s in _CATALOG}
_TONE = {"queued": "neutral", "running": "accent", "done": "success",
         "failed": "danger", "blocked": "warning", "skipped": "neutral"}


class _SourceRow(QWidget, Themed):
    def __init__(self, slug, parent=None):
        super().__init__(parent)
        self.slug = slug
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)
        self._spinner = Spinner(16)
        self._spinner.setVisible(False)
        row.addWidget(self._spinner)
        self._name = Label(_NAMES.get(slug, slug.title()), "subhead", "primary")
        row.addWidget(self._name, 1)
        self._count = Label("", "footnote", "tertiary")
        row.addWidget(self._count)
        self._chip = Chip("queued", "neutral")
        row.addWidget(self._chip)
        self._themed()

    def set_status(self, status, count):
        self._spinner.setVisible(status == "running")
        # replace chip
        self._chip.setParent(None)
        self._chip.deleteLater()
        self._chip = Chip(status, _TONE.get(status, "neutral"))
        self.layout().addWidget(self._chip)
        self._count.setText(f"{count} jobs" if count else "")

    def restyle(self):
        pass


class RunScreen(QWidget):
    stop_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: dict[str, _SourceRow] = {}
        self._elapsed = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._build()
        theme().themeChanged.connect(self._restyle)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.topbar = TopBar(1)
        root.addWidget(root_widget := QWidget())  # placeholder to keep ref simple
        root.removeWidget(root_widget)
        root.addWidget(self.topbar)

        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(24, 24, 24, 24)
        self._body.setSpacing(14)

        self.title = Label("Scanning jobs for you", "title3", "primary")
        self._body.addWidget(self.title)
        self.subtitle = Label("Based on your résumé", "subhead", "secondary")
        self._body.addWidget(self.subtitle)

        self.progress = ProgressBar(0)
        self._body.addWidget(self.progress)

        stat_row = QHBoxLayout()
        self.elapsed_lbl = Label("0s elapsed", "footnote", "tertiary")
        stat_row.addWidget(self.elapsed_lbl)
        stat_row.addStretch()
        self.found_lbl = Label("", "footnote", "secondary")
        stat_row.addWidget(self.found_lbl)
        self._body.addLayout(stat_row)

        # Per-source card
        self._sources_card = Card()
        self._sources_lay = QVBoxLayout(self._sources_card)
        self._sources_lay.setContentsMargins(4, 4, 4, 4)
        self._sources_lay.setSpacing(2)
        self._body.addWidget(self._sources_card)

        # Collapsible log
        self._log_card = Card()
        log_wrap = QVBoxLayout(self._log_card)
        log_wrap.setContentsMargins(12, 10, 12, 10)
        log_wrap.setSpacing(4)
        self._log_lay = log_wrap
        self._log_lines: list[Label] = []
        log_scroll = QScrollArea()
        log_scroll.setWidgetResizable(True)
        log_scroll.setFixedHeight(120)
        log_host = QWidget()
        log_host.setLayout(self._log_lay)
        log_scroll.setWidget(log_host)
        self._body.addWidget(log_scroll)

        self.stop_btn = Button("Stop scan", "secondary", "md")
        self.stop_btn.clicked.connect(self._on_stop)
        self._body.addWidget(self.stop_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    # -- lifecycle --------------------------------------------------------- #
    def reset(self, source_keys, threshold):
        self._elapsed = 0
        self.progress.set_value(0)
        self.found_lbl.setText("")
        self.elapsed_lbl.setText("0s elapsed")
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("Stop scan")
        while self._sources_lay.count():
            item = self._sources_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows = {}
        for key in (source_keys or []):
            row = _SourceRow(key)
            self._rows[key] = row
            self._sources_lay.addWidget(row)
        while self._log_lay.count():
            item = self._log_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._log_lines = []
        self._timer.start(1000)

    def _tick(self):
        self._elapsed += 1
        self.elapsed_lbl.setText(f"{self._elapsed}s elapsed")

    # -- slots (connected to worker signals) ------------------------------- #
    def set_subtitle(self, text):
        self.subtitle.setText(f"Based on your résumé · {text}")

    def set_progress(self, value):
        self.progress.set_value(value)
        if value >= 100:
            self._timer.stop()

    def update_source(self, slug, status, count):
        row = self._rows.get(slug)
        if row is None:
            row = _SourceRow(slug)
            self._rows[slug] = row
            self._sources_lay.addWidget(row)
        row.set_status(status, count)
        total = sum(int(r._count.text().split()[0]) if r._count.text() else 0
                    for r in self._rows.values())
        if total:
            self.found_lbl.setText(f"{total} jobs found")

    def update_stats(self, done, total, jobs_total):
        pass  # progress bar already reflects done/total

    def update_log(self, message, status):
        lbl = Label(message, "caption1", "secondary")
        self._log_lay.addWidget(lbl)
        self._log_lines.append(lbl)

    def _on_stop(self):
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Stopping…")
        self._timer.stop()
        self.stop_clicked.emit()

    def _restyle(self):
        pass
