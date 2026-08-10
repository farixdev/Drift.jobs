"""Search criteria builder (Phase 5) — a saved, reusable query object.

Every field is optional except role terms. Produces a SearchCriteria the scan
runs with; supports saving, loading, and duplicating named searches. Built on the
Phase-1 component library.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.search import (
    EMPLOYMENT_OPTIONS,
    FRESHNESS_OPTIONS,
    LOCATION_MODES,
    SENIORITY_OPTIONS,
    delete_search,
    get_search,
    list_searches,
    save_search,
)
from core.sources.spec import SearchCriteria
from ui.components import (
    Button,
    Checkbox,
    ChipInput,
    Label,
    SegmentedControl,
    Select,
    Stepper,
    TextField,
    Toggle,
)
from ui.theme import theme
from ui.widgets import TopBar


class SearchBuilderScreen(QWidget):
    run_search = pyqtSignal(object)   # emits a SearchCriteria
    back = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._refresh_saved()

    # -- helpers ----------------------------------------------------------- #
    def _section(self, title):
        self._body.addSpacing(6)
        self._body.addWidget(Label(title, "headline", "primary"))

    def _field(self, label, widget):
        self._body.addWidget(Label(label, "footnote", "secondary"))
        self._body.addWidget(widget)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.topbar = TopBar(0)
        root.addWidget(self.topbar)

        shell = QWidget()
        self._body = QVBoxLayout(shell)
        self._body.setContentsMargins(24, 20, 24, 24)
        self._body.setSpacing(8)

        # Saved-search bar
        self._body.addWidget(Label("Search builder", "title2", "primary"))
        saved_row = QHBoxLayout()
        self.saved_select = Select(["New search"])
        self.saved_select.activated.connect(self._on_load)
        saved_row.addWidget(self.saved_select, 1)
        dup = Button("Duplicate", "secondary", "sm")
        dup.clicked.connect(self._on_duplicate)
        saved_row.addWidget(dup)
        dele = Button("Delete", "plain", "sm")
        dele.clicked.connect(self._on_delete)
        saved_row.addWidget(dele)
        self._body.addLayout(saved_row)

        # Role
        self._section("Role")
        self.titles = ChipInput(placeholder="Job titles (e.g. Backend Engineer)")
        self._field("Titles", self.titles)
        self.kw_required = ChipInput(placeholder="Required keywords")
        self._field("Must include", self.kw_required)
        self.kw_nice = ChipInput(placeholder="Nice-to-have keywords")
        self._field("Nice to have", self.kw_nice)
        self.kw_excluded = ChipInput(placeholder="Excluded keywords")
        self._field("Exclude", self.kw_excluded)
        self._body.addWidget(Label("Seniority", "footnote", "secondary"))
        sen_row = QHBoxLayout()
        self.seniority = {}
        for s in SENIORITY_OPTIONS:
            cb = Checkbox(s.title())
            self.seniority[s] = cb
            sen_row.addWidget(cb)
        sen_row.addStretch()
        self._body.addLayout(sen_row)

        # Location
        self._section("Location")
        self.location_mode = SegmentedControl([m.title() for m in LOCATION_MODES], 0)
        self._field("Mode", self.location_mode)
        self.countries = ChipInput(placeholder="Countries (e.g. USA, Germany)")
        self._field("Countries", self.countries)
        reloc_row = QHBoxLayout()
        reloc_row.addWidget(Label("Open to relocation", "subhead", "primary"))
        self.relocation = Toggle(False)
        reloc_row.addWidget(self.relocation)
        reloc_row.addStretch()
        self._body.addLayout(reloc_row)

        # Compensation
        self._section("Compensation")
        comp_row = QHBoxLayout()
        self.salary_min = TextField("Min salary", "e.g. 120000")
        comp_row.addWidget(self.salary_min, 2)
        self.currency = Select(["USD", "GBP", "EUR", "CAD", "AUD"])
        cw = QWidget(); cl = QVBoxLayout(cw); cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(Label("Currency", "footnote", "secondary")); cl.addWidget(self.currency)
        comp_row.addWidget(cw, 1)
        self._body.addLayout(comp_row)
        inc_row = QHBoxLayout()
        inc_row.addWidget(Label("Include jobs with no stated salary", "subhead", "primary"))
        self.include_unstated = Toggle(True)
        inc_row.addWidget(self.include_unstated)
        inc_row.addStretch()
        self._body.addLayout(inc_row)

        # Employment
        self._section("Employment type")
        emp_grid = QGridLayout()
        self.employment = {}
        for i, e in enumerate(EMPLOYMENT_OPTIONS):
            cb = Checkbox(e.replace("_", " ").title())
            self.employment[e] = cb
            emp_grid.addWidget(cb, i // 3, i % 3)
        self._body.addLayout(emp_grid)

        # Company
        self._section("Company")
        self.only_companies = ChipInput(placeholder="Only these companies")
        self._field("Only", self.only_companies)
        self.exclude_companies = ChipInput(placeholder="Exclude companies")
        self._field("Exclude", self.exclude_companies)
        staff_row = QHBoxLayout()
        staff_row.addWidget(Label("Exclude staffing agencies", "subhead", "primary"))
        self.exclude_staffing = Toggle(False)
        staff_row.addWidget(self.exclude_staffing)
        staff_row.addStretch()
        self._body.addLayout(staff_row)

        # Freshness
        self._section("Freshness")
        self.freshness = SegmentedControl([lbl for _, lbl in FRESHNESS_OPTIONS], 0)
        self._body.addWidget(self.freshness)

        # Volume
        self._section("Volume")
        vol = QGridLayout()
        vol.setVerticalSpacing(6)
        self.min_results = Stepper(0, 0, 500)
        self.max_results = Stepper(0, 0, 1000)
        self.max_per_source = Stepper(60, 1, 200)
        self.max_per_company = Stepper(0, 0, 50)
        for r, (lbl, w) in enumerate([("Min results (widen until met)", self.min_results),
                                      ("Max results (hard cap)", self.max_results),
                                      ("Max per source", self.max_per_source),
                                      ("Max per company", self.max_per_company)]):
            vol.addWidget(Label(lbl, "subhead", "secondary"), r, 0)
            vol.addWidget(w, r, 1, Qt.AlignRight)
        self._body.addLayout(vol)

        # Save + Run
        self._body.addSpacing(10)
        save_row = QHBoxLayout()
        self.name_field = TextField("Save as", "Search name")
        save_row.addWidget(self.name_field, 1)
        savebtn = Button("Save search", "secondary", "md")
        savebtn.clicked.connect(self._on_save)
        save_row.addWidget(savebtn)
        self._body.addLayout(save_row)

        run_row = QHBoxLayout()
        backbtn = Button("← Back", "plain", "md")
        backbtn.clicked.connect(self.back.emit)
        run_row.addWidget(backbtn)
        run_row.addStretch()
        runbtn = Button("Run this search", "primary", "lg")
        runbtn.clicked.connect(lambda: self.run_search.emit(self.build_criteria()))
        run_row.addWidget(runbtn)
        self._body.addLayout(run_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(shell)
        root.addWidget(scroll, 1)

    # -- criteria <-> form ------------------------------------------------- #
    def build_criteria(self) -> SearchCriteria:
        salary = self.salary_min.text().replace(",", "").strip()
        return SearchCriteria(
            titles=self.titles.tokens(),
            keywords_required=self.kw_required.tokens(),
            keywords_nice=self.kw_nice.tokens(),
            keywords_excluded=self.kw_excluded.tokens(),
            seniority=[s for s, cb in self.seniority.items() if cb.isChecked()],
            location_mode=LOCATION_MODES[self.location_mode.current_index()],
            countries=self.countries.tokens(),
            relocation_ok=self.relocation.isChecked(),
            salary_min=int(salary) if salary.isdigit() else None,
            salary_currency=self.currency.currentText(),
            include_unstated_salary=self.include_unstated.isChecked(),
            employment_types=[e for e, cb in self.employment.items() if cb.isChecked()],
            only_companies=self.only_companies.tokens(),
            exclude_companies=self.exclude_companies.tokens(),
            exclude_staffing=self.exclude_staffing.isChecked(),
            posted_within_days=FRESHNESS_OPTIONS[self.freshness.current_index()][0],
            min_results=self.min_results._value,
            max_results=self.max_results._value,
            max_per_source=self.max_per_source._value,
            max_per_company=self.max_per_company._value,
        )

    def load_criteria(self, c: SearchCriteria):
        self.titles._tokens = list(c.titles); self.titles._rebuild()
        self.kw_required._tokens = list(c.keywords_required); self.kw_required._rebuild()
        self.kw_nice._tokens = list(c.keywords_nice); self.kw_nice._rebuild()
        self.kw_excluded._tokens = list(c.keywords_excluded); self.kw_excluded._rebuild()
        for s, cb in self.seniority.items():
            cb.setChecked(s in c.seniority)
        self.location_mode.set_index(LOCATION_MODES.index(c.location_mode)
                                     if c.location_mode in LOCATION_MODES else 0)
        self.countries._tokens = list(c.countries); self.countries._rebuild()
        self.relocation.setChecked(c.relocation_ok)
        self.salary_min.set_text(str(c.salary_min or ""))
        self.include_unstated.setChecked(c.include_unstated_salary)
        for e, cb in self.employment.items():
            cb.setChecked(e in c.employment_types)
        self.only_companies._tokens = list(c.only_companies); self.only_companies._rebuild()
        self.exclude_companies._tokens = list(c.exclude_companies); self.exclude_companies._rebuild()
        self.exclude_staffing.setChecked(c.exclude_staffing)
        fresh_vals = [v for v, _ in FRESHNESS_OPTIONS]
        self.freshness.set_index(fresh_vals.index(c.posted_within_days)
                                 if c.posted_within_days in fresh_vals else 0)
        self.min_results.set_value(c.min_results)
        self.max_results.set_value(c.max_results)
        self.max_per_source.set_value(c.max_per_source or 60)
        self.max_per_company.set_value(c.max_per_company)

    # -- saved searches ---------------------------------------------------- #
    def _refresh_saved(self):
        self._saved = list_searches()
        self.saved_select.blockSignals(True)
        self.saved_select.clear()
        self.saved_select.addItem("New search")
        for s in self._saved:
            self.saved_select.addItem(s["name"])
        self.saved_select.blockSignals(False)

    def _current_saved_id(self):
        idx = self.saved_select.currentIndex() - 1
        if 0 <= idx < len(self._saved):
            return self._saved[idx]["id"]
        return None

    def _on_load(self, index):
        sid = self._current_saved_id()
        if sid is None:
            return
        got = get_search(sid)
        if got:
            name, criteria = got
            self.name_field.set_text(name)
            self.load_criteria(criteria)

    def _on_save(self):
        name = self.name_field.text().strip() or "Untitled search"
        save_search(name, self.build_criteria(), search_id=self._current_saved_id())
        self._refresh_saved()

    def _on_duplicate(self):
        from core.search import duplicate_search
        sid = self._current_saved_id()
        if sid:
            duplicate_search(sid)
            self._refresh_saved()

    def _on_delete(self):
        sid = self._current_saved_id()
        if sid:
            delete_search(sid)
            self._refresh_saved()
