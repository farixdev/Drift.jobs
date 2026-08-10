"""Search screen — pick a résumé (upload or saved), review the skills/location
we'll search for, choose sources, and start. Built on the design system so it
matches the rest of the shell."""
import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core import parser
from core.scraper import SOURCES
from core.url_utils import InvalidJobsUrlError, normalize_jobs_url
from ui.components import (
    Button,
    Card,
    Checkbox,
    ChipInput,
    Label,
    SegmentedControl,
    Select,
    TextField,
)
from ui.components.base import Themed
from ui.components.navigation import icon_font
from ui.theme import theme, tokens
from ui.widgets import TopBar

# Segoe icon-font (MDL2/Fluent) codepoints — kept as string-literal escapes so the
# source file stays plain ASCII (raw glyphs are fragile in editors/tools).
_ICON_DOC = ""     # Document
_ICON_CHECK = ""   # CheckMark
_STAR = "★"

# Employer-direct ATS providers vs. remote/aggregator feeds — used only to group
# the source pickers into two tidy sections.
_ATS_KEYS = {"greenhouse", "lever", "ashby", "workable",
             "smartrecruiters", "recruitee", "personio"}


class _DropZone(QFrame, Themed):
    """Clickable, drag-target résumé upload area."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")   # id-selector so the border can't cascade
        self.setCursor(Qt.PointingHandCursor)  # to child QLabels (QLabel is a QFrame)
        self.setMinimumHeight(116)
        self._state = "idle"
        col = QVBoxLayout(self)
        col.setContentsMargins(20, 20, 20, 20)
        col.setSpacing(3)
        col.setAlignment(Qt.AlignCenter)
        self._icon = Label(_ICON_DOC)
        self._icon.setFont(icon_font(26))
        self._icon.setAlignment(Qt.AlignCenter)
        self._title = Label("Drop your résumé or click to browse", "headline", "primary")
        self._title.setAlignment(Qt.AlignCenter)
        self._sub = Label("PDF, DOC, or DOCX", "footnote", "tertiary")
        self._sub.setAlignment(Qt.AlignCenter)
        col.addWidget(self._icon)
        col.addWidget(self._title)
        col.addWidget(self._sub)
        self._themed()

    def set_idle(self):
        self._state = "idle"
        self._icon.setText(_ICON_DOC)
        self._title.setText("Drop your résumé or click to browse")
        self._title._tone = "primary"
        self._sub.setText("PDF, DOC, or DOCX")
        self.restyle()

    def set_done(self, filename, subtitle="Résumé ready"):
        self._state = "done"
        self._icon.setText(_ICON_CHECK)
        self._title.setText(filename)
        self._title._tone = "primary"
        self._sub.setText(subtitle)
        self.restyle()

    def mousePressEvent(self, _e):
        self.clicked.emit()

    def restyle(self):
        p = self.pal()
        self._icon.restyle()
        self._title.restyle()
        self._sub.restyle()
        r = tokens.RADIUS["card"]
        if self._state == "done":
            self.setStyleSheet(
                f"QFrame#DropZone{{background:{p.success_bg}; border:1px solid {p.success};"
                f" border-radius:{r}px;}}")
            self._icon.setStyleSheet(f"color:{p.success}; background:transparent;")
        else:
            self.setStyleSheet(
                f"QFrame#DropZone{{background:{p.fill_tertiary}; border:1.5px dashed {p.control_border};"
                f" border-radius:{r}px;}}")
            self._icon.setStyleSheet(f"color:{p.label_tertiary}; background:transparent;")


class _SourceItem(QFrame, Themed):
    """One source row: a checkbox + a muted one-line note."""

    def __init__(self, key, label, note, checked, recommended, parent=None):
        super().__init__(parent)
        self.key = key
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.cb = Checkbox(label + (f"   {_STAR}" if recommended else ""), checked)
        row.addWidget(self.cb, 0)
        self.note = Label(note, "caption1", "tertiary")
        row.addWidget(self.note, 1)
        self._themed()

    def is_on(self) -> bool:
        return self.cb.isChecked()

    def set_on(self, on: bool):
        self.cb.setChecked(on)

    def set_source_enabled(self, enabled: bool):
        self.cb.setEnabled(enabled)
        if not enabled:
            self.cb.setChecked(False)
        self.note.setEnabled(enabled)

    def restyle(self):
        pass


class SetupScreen(QWidget):
    # emits: resume_path, source_keys, threshold, resume_text, custom_url, criteria
    start_scan = pyqtSignal(str, list, int, str, str, object)
    open_builder = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._resume_path = ""
        self._resume_text = ""
        self._parsed = False
        self._parsed_obj = None      # ParsedResume when a saved résumé is chosen
        self._resume_label = ""
        self._custom_url = ""
        self._saved: list[dict] = []
        self.sources: dict[str, _SourceItem] = {}
        self._build_ui()

    # ------------------------------------------------------------------ build #
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.topbar = TopBar(0)
        root.addWidget(self.topbar)

        p = theme().palette()
        shell = QWidget()
        shell.setStyleSheet(f"background:{p.bg_base};")
        body = QVBoxLayout(shell)
        body.setContentsMargins(28, 22, 28, 28)
        body.setSpacing(16)

        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(Label("Search", "title2", "primary"))
        head.addWidget(Label("Find roles that match your résumé.", "subhead", "secondary"))
        body.addLayout(head)

        body.addWidget(self._resume_card())
        body.addWidget(self._terms_card())
        body.addWidget(self._sources_card())
        body.addWidget(self._options_card())

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.advanced_btn = Button("Advanced builder", "plain", "md")
        self.advanced_btn.clicked.connect(self.open_builder.emit)
        footer.addWidget(self.advanced_btn)
        footer.addStretch()
        self.start_btn = Button("Start scanning", "primary", "lg")
        self.start_btn.setMinimumWidth(180)
        self.start_btn.clicked.connect(self._on_start)
        footer.addWidget(self.start_btn)
        body.addLayout(footer)
        body.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(shell)
        root.addWidget(scroll, 1)
        self.setAcceptDrops(True)

    def _resume_card(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(Label("Résumé", "headline", "primary"), 1)
        self.resume_mode = SegmentedControl(["Upload", "Saved"], 0)
        self.resume_mode.setFixedWidth(180)
        self.resume_mode.changed.connect(self._on_resume_mode)
        top.addWidget(self.resume_mode)
        lay.addLayout(top)

        self.resume_stack = QStackedWidget()

        # -- Upload page --------------------------------------------------- #
        up = QWidget()
        upc = QVBoxLayout(up)
        upc.setContentsMargins(0, 0, 0, 0)
        upc.setSpacing(10)
        self.dropzone = _DropZone()
        self.dropzone.clicked.connect(self._browse_resume)
        upc.addWidget(self.dropzone)
        self.save_lib_cb = Checkbox("Save to my résumés for next time", True)
        self.save_lib_cb.setVisible(False)
        upc.addWidget(self.save_lib_cb)
        self.resume_stack.addWidget(up)

        # -- Saved page ---------------------------------------------------- #
        sv = QWidget()
        svc = QVBoxLayout(sv)
        svc.setContentsMargins(0, 0, 0, 0)
        svc.setSpacing(8)
        self.saved_select = Select([])
        self.saved_select.currentIndexChanged.connect(self._on_pick_saved)
        svc.addWidget(self.saved_select)
        self.saved_hint = Label("", "footnote", "tertiary")
        svc.addWidget(self.saved_hint)
        self.resume_stack.addWidget(sv)

        lay.addWidget(self.resume_stack)
        return card

    def _terms_card(self) -> Card:
        self.terms_card = Card()
        lay = QVBoxLayout(self.terms_card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        lay.addWidget(Label("What we'll search for", "headline", "primary"))
        lay.addWidget(Label("Pulled from your résumé — edit anything.", "caption1", "tertiary"))
        self.location_input = TextField("Location", "e.g. Remote, Toronto, London")
        lay.addWidget(self.location_input)
        lay.addWidget(Label("Skills & keywords", "footnote", "secondary"))
        self.skills_input = ChipInput("Add a skill and press Enter")
        lay.addWidget(self.skills_input)
        self.terms_card.setVisible(False)
        return self.terms_card

    def _sources_card(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        lay.addWidget(Label("Where to search", "headline", "primary"))

        ats = [s for s in SOURCES if s["key"] in _ATS_KEYS]
        feeds = [s for s in SOURCES if s["key"] not in _ATS_KEYS]
        for title, group in (("Employer boards (ATS)", ats),
                             ("Remote & aggregator feeds", feeds)):
            if not group:
                continue
            lay.addWidget(Label(title.upper(), "caption2", "tertiary"))
            for src in group:
                item = _SourceItem(src["key"], src["label"], src["note"],
                                   src["recommended"], src["recommended"])
                self.sources[src["key"]] = item
                lay.addWidget(item)

        lay.addSpacing(2)
        self.custom_url_input = TextField(
            "Custom job site (optional)", "company.com/jobs",
            "Must end with /jobs — e.g. company.com/jobs")
        self.custom_url_input.line_edit().textChanged.connect(self._on_custom_url_changed)
        lay.addWidget(self.custom_url_input)
        return card

    def _options_card(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)
        lay.addWidget(Label("Minimum match score — optional", "headline", "primary"))
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(Label("All", "caption1", "tertiary"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 95)
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._update_threshold_label)
        row.addWidget(self.slider, 1)
        row.addWidget(Label("High", "caption1", "tertiary"))
        self.threshold_label = Label("All", "subhead", "accent")
        self.threshold_label.setFixedWidth(44)
        self.threshold_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.threshold_label)
        lay.addLayout(row)
        lay.addWidget(Label("Leave at All to see every job matching your skills + location.",
                           "caption1", "tertiary"))
        return card

    # -------------------------------------------------------------- résumé UX #
    def _on_resume_mode(self, index: int) -> None:
        self.resume_stack.setCurrentIndex(index)
        if index == 1:
            self._refresh_saved()

    def _refresh_saved(self) -> None:
        from core.resume import list_resumes
        self._saved = list_resumes()
        self.saved_select.blockSignals(True)
        self.saved_select.clear()
        if self._saved:
            self.saved_select.addItem("Choose a saved résumé…")
            for r in self._saved:
                self.saved_select.addItem(r["label"] + (f"  {_STAR}" if r["is_default"] else ""))
            self.saved_hint.setText("Saved résumés come from the Résumés section.")
        else:
            self.saved_select.addItem("No saved résumés yet")
            self.saved_hint.setText("Upload one here, or create one in the Résumés section.")
        self.saved_select.blockSignals(False)

    def _on_pick_saved(self, index: int) -> None:
        idx = index - 1
        if not (0 <= idx < len(self._saved)):
            return
        from core.resume import get_resume
        got = get_resume(self._saved[idx]["id"])
        if not got:
            return
        self._resume_text = got["raw_text"]
        self._resume_path = f"saved:{got['id']}"
        self._parsed_obj = got["parsed"]
        self._parsed = True
        self._resume_label = got["label"]
        loc = (got["parsed"].contact or {}).get("location", "")
        skills = got["parsed"].all_skills()
        self._fill_terms(loc, skills, got["raw_text"], force=True)
        self.dropzone.set_done(got["label"], "Saved résumé")
        self.start_btn.setText("Start scanning")

    def _browse_resume(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select résumé", "", "Résumés (*.pdf *.doc *.docx)")
        if path:
            self._load_resume(path)

    def _load_resume(self, path: str) -> None:
        try:
            text = parser.extract(path)
            if len(text.strip()) < 20:
                raise ValueError("Could not extract enough text. Try a text-based PDF or DOCX.")
            self._resume_text = text
            self._resume_path = path
            self._parsed_obj = None
            self._parsed = True
            self._resume_label = os.path.basename(path)
            self.dropzone.set_done(os.path.basename(path))
            self.save_lib_cb.setVisible(True)
            self.start_btn.setText("Start scanning")
            self._fill_terms("", [], text)          # local extract fills the fields
        except Exception as exc:
            self._parsed = False
            self._resume_path = ""
            self._resume_text = ""
            self.terms_card.setVisible(False)
            self.dropzone.set_idle()
            self.save_lib_cb.setVisible(False)
            self.start_btn.setText("Start scanning")
            self.dropzone.setToolTip(str(exc))

    def _fill_terms(self, location: str, skills: list, text: str, force: bool = False) -> None:
        """Populate the editable location + skills, falling back to a local parse.

        `force` replaces whatever is there (used when the user deliberately picks a
        saved résumé); otherwise existing edits are preserved.
        """
        if not location or not skills:
            try:
                from core import local_engine
                parsed = local_engine.parse_resume(text)
            except Exception:
                parsed = {}
            location = location or parsed.get("location") or ""
            skills = skills or parsed.get("skills") or []
        if force or not self.location_input.text().strip():
            self.location_input.set_text(location)
        if force or not self.skills_input.tokens():
            self.skills_input.set_tokens(list(skills)[:24])
        self.terms_card.setVisible(True)

    # ----------------------------------------------------------- sources UX #
    def _on_custom_url_changed(self, text: str) -> None:
        raw = text.strip()
        using_custom = bool(raw)
        for item in self.sources.values():
            item.set_source_enabled(not using_custom)
        if not raw:
            self._custom_url = ""
            self.custom_url_input.set_error("")
            return
        try:
            self._custom_url = normalize_jobs_url(raw)
            self.custom_url_input.set_valid(f"Will scan: {self._custom_url}")
        except InvalidJobsUrlError as exc:
            self._custom_url = ""
            self.custom_url_input.set_error(str(exc))

    def _update_threshold_label(self, value: int) -> None:
        self.threshold_label.setText("All" if value <= 0 else f"{value}%")
        self.threshold_label._tone = "accent" if value <= 0 else "primary"
        self.threshold_label.restyle()

    # --------------------------------------------------------------- drag/drop #
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".pdf", ".doc", ".docx")):
                self.resume_mode.set_index(0)
                self._load_resume(path)
                break

    # ------------------------------------------------------------------ start #
    def _on_start(self) -> None:
        if not self._resume_path or not self._parsed:
            self.start_btn.setText("Add a résumé first")
            return

        custom_raw = self.custom_url_input.text().strip()
        custom_url = ""
        if custom_raw:
            try:
                custom_url = normalize_jobs_url(custom_raw)
            except InvalidJobsUrlError as exc:
                self.custom_url_input.set_error(str(exc))
                return
            selected: list[str] = []
        else:
            selected = [k for k, w in self.sources.items() if w.is_on()]
            if not selected:
                self.start_btn.setText("Select at least one source")
                return

        # Persist a freshly-uploaded résumé to the library if asked.
        if (self._parsed_obj is None and not self._resume_path.startswith("saved:")
                and self.save_lib_cb.isVisible() and self.save_lib_cb.isChecked()):
            self._save_to_library()

        self.start_btn.setText("Start scanning")
        self.start_scan.emit(
            self._resume_path, selected, self.slider.value(),
            self._resume_text, custom_url, self._build_criteria(selected))

    def _save_to_library(self) -> None:
        try:
            from core.resume import extract_structured, save_resume
            parsed, _ = extract_structured(self._resume_text, use_llm=False)
            # honour the user's edits to location/skills
            loc = self.location_input.text().strip()
            if loc:
                parsed.contact = {**(parsed.contact or {}), "location": loc}
            edited = self.skills_input.tokens()
            if edited:
                parsed.skills["technical"] = edited
            label = (parsed.contact or {}).get("name") or self._resume_label or "My résumé"
            save_resume(label, self._resume_text, parsed)
            self.save_lib_cb.setChecked(False)
            self.save_lib_cb.setVisible(False)
        except Exception:
            pass  # saving is a convenience; never block a scan on it

    def _build_criteria(self, selected: list[str]):
        """Turn the edited location + skills into a SearchCriteria so the scan
        searches for exactly what the user sees (and can edit)."""
        skills = self.skills_input.tokens()
        location = self.location_input.text().strip()
        if not skills and not location:
            return None
        from core.sources.spec import SearchCriteria
        mode = "any"
        if location and location.strip().lower() in ("remote", "anywhere", "worldwide"):
            mode = "remote"
        # Skills go in keywords_NICE (ANY-match at the source), never
        # keywords_required (an AND filter that would hide almost every job).
        return SearchCriteria(
            keywords_nice=skills, keywords=skills, location=location,
            location_mode=mode, sources=list(selected))
