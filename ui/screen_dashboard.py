"""Dashboard home (Phase 10): the at-a-glance overview + quick actions."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from core import dashboard
from ui.components import Button, Card, Chip, Label
from ui.theme import theme


class DashboardScreen(QWidget):
    navigate = pyqtSignal(str)     # route key
    run_all = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._host = QWidget()
        self._body = QVBoxLayout(self._host)
        self._body.setContentsMargins(28, 24, 28, 28)
        self._body.setSpacing(16)
        scroll.setWidget(self._host)
        root.addWidget(scroll)

    def reload(self):
        while self._body.count():
            it = self._body.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._clear_layout(it.layout())
        s = dashboard.summary()

        header = QHBoxLayout()
        title = QVBoxLayout()
        title.addWidget(Label("Dashboard", "largeTitle", "primary"))
        lr = s["last_run"]
        sub = (f"{s['active_searches']} active search(es) · last run "
               f"{(lr['started_at'][:16] if lr else 'never')}")
        title.addWidget(Label(sub, "subhead", "secondary"))
        header.addLayout(title, 1)
        run = Button("Run all searches", "primary", "lg")
        run.clicked.connect(self.run_all.emit)
        header.addWidget(run)
        self._body.addLayout(header)

        # Metric tiles
        m = s["application_metrics"]
        tiles = [("Jobs found", s["jobs_total"]),
                 ("Applications", m["applied"]),
                 ("Response rate", f"{m['response_rate']}%"),
                 ("Spend today", f"${s['spend_today']['cost_usd']:.2f}")]
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (label, val) in enumerate(tiles):
            grid.addWidget(self._tile(label, val), 0, i)
        self._body.addLayout(grid)

        # Two columns: source health + recent jobs
        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.addWidget(self._source_health_card(s["source_health"]), 1)
        cols.addWidget(self._recent_jobs_card(), 1)
        self._body.addLayout(cols)

        # Upcoming follow-ups
        self._body.addWidget(self._upcoming_card(s["upcoming"]))

        # Quick actions
        qa = QHBoxLayout()
        for label, route in [("New search", "search"), ("Upload résumé", "resume"),
                             ("Applications", "tracker"), ("Sources", "sources")]:
            b = Button(label, "tinted", "md")
            b.clicked.connect(lambda _=False, r=route: self.navigate.emit(r))
            qa.addWidget(b)
        qa.addStretch()
        self._body.addLayout(qa)
        self._body.addStretch()

    # -- widgets ----------------------------------------------------------- #
    def _tile(self, label, val):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.addWidget(Label(str(val), "title1", "primary"))
        lay.addWidget(Label(label, "footnote", "secondary"))
        return card

    def _source_health_card(self, health):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(Label("Source health", "headline", "primary"), 1)
        view = Button("View", "plain", "sm")
        view.clicked.connect(lambda: self.navigate.emit("sources"))
        top.addWidget(view)
        lay.addLayout(top)
        problem = [h for h in health if h["health_status"] in ("degraded", "disabled")]
        if not problem:
            lay.addWidget(Label("All sources healthy.", "subhead", "success"))
        else:
            for h in problem[:6]:
                row = QHBoxLayout()
                row.addWidget(Label(h["display_name"] or h["slug"], "subhead", "primary"), 1)
                tone = "danger" if h["health_status"] == "disabled" else "warning"
                row.addWidget(Chip(h["health_status"], tone))
                lay.addLayout(row)
        return card

    def _recent_jobs_card(self):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(Label("Recent jobs", "headline", "primary"), 1)
        view = Button("View", "plain", "sm")
        view.clicked.connect(lambda: self.navigate.emit("jobs"))
        top.addWidget(view)
        lay.addLayout(top)
        jobs = dashboard.recent_jobs(6)
        if not jobs:
            lay.addWidget(Label("No jobs yet — run a search.", "subhead", "secondary"))
        for j in jobs:
            row = QHBoxLayout()
            t = Label(f"{j['title']}  ·  {j['company_name']}", "subhead", "primary")
            row.addWidget(t, 1)
            if j.get("score") is not None:
                row.addWidget(Chip(str(round(j["score"])), "accent"))
            lay.addLayout(row)
        return card

    def _upcoming_card(self, upcoming):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        lay.addWidget(Label("Upcoming follow-ups", "headline", "primary"))
        if not upcoming:
            lay.addWidget(Label("Nothing scheduled.", "subhead", "secondary"))
        for u in upcoming:
            row = QHBoxLayout()
            row.addWidget(Label(f"{u['next_action']} — {u['company_name']}", "subhead", "primary"), 1)
            row.addWidget(Label(u["next_action_due"] or "", "footnote", "tertiary"))
            lay.addLayout(row)
        return card

    def _clear_layout(self, layout):
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._clear_layout(it.layout())
