"""Resume screen (Phase 4): upload → editable parsed view → save + export.

Shows the structured parse in an editable form so the user corrects it once and
the corrections persist; lists saved resumes; exports to PDF/DOCX/TXT; and surfaces
detected target titles + seniority as suggestions for the search builder.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.resume import (
    ParsedResume,
    check_ats,
    export as export_resume,
    extract_structured,
    extract_text,
    list_resumes,
    save_resume,
    seniority_band,
    target_titles,
    update_parsed,
)
from ui.components import Button, Card, Chip, InlineBanner, Label, Select, Spinner, TextField
from ui.theme import theme
from ui.widgets import TopBar


class _ParseWorker(QThread):
    done = pyqtSignal(object, list)
    failed = pyqtSignal(str)

    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        try:
            parsed, warns = extract_structured(self.text)
            self.done.emit(parsed, warns)
        except Exception as exc:
            self.failed.emit(str(exc))


class ResumeScreen(QWidget):
    back = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parsed = ParsedResume()
        self._raw_text = ""
        self._resume_id = None
        self._worker = None
        self._build()
        self._refresh_saved()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.topbar = TopBar(0)
        root.addWidget(self.topbar)

        shell = QWidget()
        self._body = QVBoxLayout(shell)
        self._body.setContentsMargins(24, 20, 24, 24)
        self._body.setSpacing(10)

        self._body.addWidget(Label("Résumé", "title2", "primary"))

        top = QHBoxLayout()
        self.saved_select = Select(["No saved résumés"])
        self.saved_select.activated.connect(self._on_load_saved)
        top.addWidget(self.saved_select, 1)
        upload = Button("Upload file", "secondary", "md")
        upload.clicked.connect(self._on_upload)
        top.addWidget(upload)
        self._body.addLayout(top)

        self.status = QHBoxLayout()
        self._spinner = Spinner(18)
        self._spinner.setVisible(False)
        self.status.addWidget(self._spinner)
        self._status_lbl = Label("Upload a résumé or paste text below.", "footnote", "secondary")
        self.status.addWidget(self._status_lbl, 1)
        self._body.addLayout(self.status)

        self._banner_slot = QVBoxLayout()
        self._body.addLayout(self._banner_slot)

        # Editable fields
        self.name = TextField("Name", "Your name")
        self.email = TextField("Email", "you@example.com")
        self.location = TextField("Location", "City, Country")
        row = QHBoxLayout()
        row.addWidget(self.name); row.addWidget(self.email); row.addWidget(self.location)
        self._body.addLayout(row)

        self._body.addWidget(Label("Summary", "footnote", "secondary"))
        self.summary = QPlainTextEdit()
        self.summary.setFixedHeight(70)
        self.summary.setStyleSheet(self._edit_qss())
        self._body.addWidget(self.summary)

        self._body.addWidget(Label("Skills (comma-separated)", "footnote", "secondary"))
        self.skills = QPlainTextEdit()
        self.skills.setFixedHeight(60)
        self.skills.setStyleSheet(self._edit_qss())
        self._body.addWidget(self.skills)

        # Detected targets (search-builder suggestions)
        self._targets_row = QHBoxLayout()
        self._body.addLayout(self._targets_row)

        # Actions
        acts = QHBoxLayout()
        back = Button("← Back", "plain", "md")
        back.clicked.connect(self.back.emit)
        acts.addWidget(back)
        acts.addStretch()
        for fmt in ("txt", "docx", "pdf"):
            b = Button(f"Export {fmt.upper()}", "secondary", "sm")
            b.clicked.connect(lambda _=False, f=fmt: self._on_export(f))
            acts.addWidget(b)
        save = Button("Save résumé", "primary", "md")
        save.clicked.connect(self._on_save)
        acts.addWidget(save)
        self._body.addLayout(acts)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(shell)
        root.addWidget(scroll, 1)

    def _edit_qss(self):
        p = theme().palette()
        return (f"QPlainTextEdit{{background:{p.control_bg}; color:{p.label_primary};"
                f" border:1px solid {p.control_border}; border-radius:8px; padding:8px;"
                f" font-size:14px;}}")

    # -- parsing ----------------------------------------------------------- #
    def load_text(self, raw_text: str, resume_id=None):
        self._raw_text = raw_text
        self._resume_id = resume_id
        self._set_status("Parsing résumé…", busy=True)
        self._worker = _ParseWorker(raw_text)
        self._worker.done.connect(self._on_parsed)
        self._worker.failed.connect(lambda m: self._set_status(f"Parse failed: {m}", busy=False))
        self._worker.start()

    def _on_upload(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select résumé", "",
                                             "Résumés (*.pdf *.doc *.docx *.txt)")
        if not path:
            return
        if path.lower().endswith(".txt"):
            text = open(path, encoding="utf-8", errors="replace").read()
            warns = []
        else:
            text, warns = extract_text(path)
        self._clear_banners()
        for w in warns:
            self._banner_slot.addWidget(InlineBanner(w, "warning"))
        if text.strip():
            self.load_text(text)

    def _on_parsed(self, parsed, warns):
        self._parsed = parsed
        self._set_status("Parsed — review and correct below, then save.", busy=False)
        self._clear_banners()
        for w in warns:
            self._banner_slot.addWidget(InlineBanner(w, "warning"))
        c = parsed.contact or {}
        self.name.set_text(c.get("name", ""))
        self.email.set_text(c.get("email", ""))
        self.location.set_text(c.get("location", ""))
        self.summary.setPlainText(parsed.summary or "")
        self.skills.setPlainText(", ".join(parsed.all_skills()))
        self._render_targets()

    def _render_targets(self):
        while self._targets_row.count():
            it = self._targets_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        band = seniority_band(self._parsed)
        targets = target_titles(self._parsed)
        if targets or band:
            self._targets_row.addWidget(Label("Suggested targets:", "footnote", "tertiary"))
            for t in targets[:4]:
                self._targets_row.addWidget(Chip(t, "accent"))
            if band:
                self._targets_row.addWidget(Chip(band, "neutral"))
            self._targets_row.addStretch()

    # -- persistence ------------------------------------------------------- #
    def _collect(self) -> ParsedResume:
        self._parsed.contact = {"name": self.name.text(), "email": self.email.text(),
                                "location": self.location.text()}
        self._parsed.summary = self.summary.toPlainText().strip()
        skills = [s.strip() for s in self.skills.toPlainText().split(",") if s.strip()]
        self._parsed.skills["technical"] = skills
        return self._parsed

    def _on_save(self):
        parsed = self._collect()
        label = (self.name.text().strip() or "My résumé")
        if self._resume_id:
            update_parsed(self._resume_id, parsed)
        else:
            self._resume_id = save_resume(label, self._raw_text, parsed, is_default=True)
        self._set_status("Saved.", busy=False)
        self._refresh_saved()

    def _on_export(self, fmt):
        parsed = self._collect()
        default = f"resume.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "Export résumé", default,
                                             f"{fmt.upper()} (*.{fmt})")
        if path:
            saved = export_resume(parsed, path, fmt)
            self._set_status(f"Exported to {saved}", busy=False)

    def _refresh_saved(self):
        self._saved = list_resumes()
        self.saved_select.blockSignals(True)
        self.saved_select.clear()
        self.saved_select.addItem("New résumé")
        for r in self._saved:
            self.saved_select.addItem(r["label"] + (" ★" if r["is_default"] else ""))
        self.saved_select.blockSignals(False)

    def _on_load_saved(self, index):
        idx = index - 1
        if not (0 <= idx < len(self._saved)):
            return
        from core.resume import get_resume
        got = get_resume(self._saved[idx]["id"])
        if got:
            self._resume_id = got["id"]
            self._raw_text = got["raw_text"]
            self._on_parsed(got["parsed"], [])

    # -- helpers ----------------------------------------------------------- #
    def _set_status(self, text, busy=False):
        self._status_lbl.setText(text)
        self._spinner.setVisible(busy)

    def _clear_banners(self):
        while self._banner_slot.count():
            it = self._banner_slot.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
