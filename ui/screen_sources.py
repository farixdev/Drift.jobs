"""Sources health page (Phase 10): every adapter with health, success rate,
latency, avg jobs, and a manual live test."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from core import dashboard
from ui.components import Button, Card, Chip, Label
from ui.theme import theme
from ui.widgets import TopBar

_TONE = {"healthy": "success", "degraded": "warning", "disabled": "danger",
         "blocked": "warning", "unknown": "neutral"}


class _TestWorker(QThread):
    done = pyqtSignal(str, str, int)   # slug, status, jobs

    def __init__(self, slug):
        super().__init__()
        self.slug = slug

    def run(self):
        try:
            from core.sources import DEFINITIONS, LEGACY_DEFINITIONS, run_source, SearchCriteria
            from core.sources.runner import run_legacy
            defn = DEFINITIONS.get(self.slug) or LEGACY_DEFINITIONS.get(self.slug)
            if not defn:
                self.done.emit(self.slug, "unknown", 0); return
            crit = SearchCriteria(keywords_required=["engineer"], max_per_source=5)
            r = (run_legacy if defn.legacy_slug else run_source)(defn, crit)
            self.done.emit(self.slug, r.status, len(r.jobs))
        except Exception:
            self.done.emit(self.slug, "failed", 0)


class SourcesScreen(QWidget):
    back = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._build()
        self.reload()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.topbar = TopBar(0)
        root.addWidget(self.topbar)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        host = QWidget()
        self._body = QVBoxLayout(host)
        self._body.setContentsMargins(24, 18, 24, 24)
        self._body.setSpacing(8)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

    def reload(self):
        while self._body.count():
            it = self._body.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
            elif it.layout():
                self._clear(it.layout())
        head = QHBoxLayout()
        head.addWidget(Label("Sources", "title2", "primary"), 1)
        back = Button("← Back", "plain", "md"); back.clicked.connect(self.back.emit)
        head.addWidget(back)
        self._body.addLayout(head)

        for h in dashboard.source_health():
            self._body.addWidget(self._row(h))
        self._body.addStretch()

    def _row(self, h):
        card = Card()
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)
        left = QVBoxLayout()
        left.addWidget(Label(h["display_name"] or h["slug"], "subhead", "primary"))
        meta = f"{h['category'] or '—'} · {h['adapter_type']}"
        if h["last_success_at"]:
            meta += f" · last ok {h['last_success_at'][:16]}"
        left.addWidget(Label(meta, "caption1", "tertiary"))
        row.addLayout(left, 1)

        stats = []
        if h["success_rate"] is not None:
            stats.append(f"{h['success_rate']}% ok")
        if h["avg_ms"] is not None:
            stats.append(f"{h['avg_ms']}ms")
        if h["avg_jobs"] is not None:
            stats.append(f"~{h['avg_jobs']} jobs")
        if stats:
            row.addWidget(Label(" · ".join(stats), "footnote", "secondary"))
        row.addWidget(Chip(h["health_status"], _TONE.get(h["health_status"], "neutral")))
        test = Button("Test", "secondary", "sm")
        test.clicked.connect(lambda _=False, slug=h["slug"]: self._test(slug, test))
        row.addWidget(test)
        return card

    def _test(self, slug, btn):
        btn.setText("Testing…")
        btn.setEnabled(False)
        w = _TestWorker(slug)
        w.done.connect(lambda s, st, n: (btn.setText(f"{st} ({n})"), btn.setEnabled(True), self.reload()))
        self._workers.append(w)
        w.start()

    def _clear(self, layout):
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._clear(it.layout())
