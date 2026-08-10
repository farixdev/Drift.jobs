import webbrowser
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core import report
import db
from models import (
    STATUS_APPLIED,
    STATUS_DISMISSED,
    STATUS_NEW,
    STATUS_SAVED,
    Job,
)
from ui import styles
from ui.dialogs import CoverLetterDialog
from ui.widgets import TopBar, chip


class ScoreLabel(QLabel):
    def __init__(self, target: int, parent=None):
        super().__init__(parent)
        target = max(0, min(100, target))
        self.setAlignment(Qt.AlignRight)
        color = styles.verdict_colors(target)[1]
        self.setStyleSheet(f"font-size:20px; font-weight:600; color:{color};")
        # Render the real score immediately — no count-up animation. A grid of
        # numbers spinning up from 0 at once reads as glitchy, not lively.
        self.setText(f"{target}%")


class JobCard(QFrame):
    def __init__(self, job: Job, on_status, on_cover, on_tailor=None, on_breakdown=None, parent=None):
        super().__init__(parent)
        self.job = job
        self._on_status = on_status
        self._on_cover = on_cover
        self._on_tailor = on_tailor
        self._on_breakdown = on_breakdown
        self.setStyleSheet(
            f"QFrame {{ background:{styles.RAISED}; border:1px solid {styles.BORDER};"
            f" border-radius:12px; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel(job.title)
        title.setStyleSheet(f"font-size:14px; font-weight:600; color:{styles.TEXT_PRIMARY};")
        title.setWordWrap(True)
        title_row.addWidget(title, 1)
        if job.is_new:
            title_row.addWidget(chip("NEW", styles.NEW_BG, styles.NEW_TEXT), 0, Qt.AlignTop)
        if getattr(job, "seen_count", 1) > 1:
            title_row.addWidget(
                chip(f"seen on {job.seen_count} sites", styles.LOC_BG, styles.LOC_TEXT),
                0, Qt.AlignTop)
        left.addLayout(title_row)

        meta_parts = [job.company, job.location or ("Remote" if job.remote else "")]
        if job.salary:
            meta_parts.append(job.salary)
        if job.posted:
            meta_parts.append(job.posted)
        meta = QLabel(" · ".join(p for p in meta_parts if p))
        meta.setStyleSheet(f"font-size:12px; color:{styles.TEXT_SECONDARY};")
        meta.setWordWrap(True)
        left.addWidget(meta)
        top.addLayout(left, 1)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignTop | Qt.AlignRight)
        right.addWidget(ScoreLabel(job.score), 0, Qt.AlignRight)
        vb, vt = styles.verdict_colors(job.score)
        if job.verdict:
            right.addWidget(chip(job.verdict, vb, vt), 0, Qt.AlignRight)
        top.addLayout(right)
        outer.addLayout(top)

        # Explainable score: per-dimension sub-scores (lexical/semantic/LLM).
        subs = getattr(job, "subscores", None) or {}
        parts = []
        for key, label in (("lexical", "Lex"), ("semantic", "Sem"), ("llm", "AI")):
            if key in subs:
                parts.append(f"{label} {subs[key]}")
        if "freshness" in subs:
            parts.append(f"Fresh ×{subs['freshness']}")
        if parts:
            breakdown = QLabel("  ·  ".join(parts))
            breakdown.setStyleSheet(f"font-size:11px; color:{styles.TEXT_TERTIARY};")
            outer.addWidget(breakdown)

        # Skill chips: matched (green) + gaps (amber).
        if job.matched_skills or job.missing_skills:
            tags = QHBoxLayout()
            tags.setSpacing(6)
            for skill in job.matched_skills[:6]:
                tags.addWidget(chip(skill, styles.MATCH_BG, styles.MATCH_TEXT))
            for skill in job.missing_skills[:4]:
                tags.addWidget(chip(f"− {skill}", styles.GAP_BG, styles.GAP_TEXT))
            tags.addStretch()
            wrap = QWidget()
            wrap.setLayout(tags)
            outer.addWidget(wrap)

        if job.summary:
            summ = QLabel(job.summary)
            summ.setWordWrap(True)
            summ.setStyleSheet(f"font-size:12px; color:{styles.TEXT_TERTIARY};")
            outer.addWidget(summ)

        # Action row.
        actions = QHBoxLayout()
        actions.setSpacing(8)
        apply_btn = self._ghost("Apply ↗")
        apply_btn.clicked.connect(lambda: webbrowser.open(self.job.url))
        cover_btn = self._ghost("✎ Cover letter")
        cover_btn.clicked.connect(lambda: self._on_cover(self.job))
        actions.addWidget(apply_btn)
        actions.addWidget(cover_btn)
        if self._on_breakdown:
            bd = self._ghost("≡ Breakdown")
            bd.clicked.connect(lambda: self._on_breakdown(self.job))
            actions.addWidget(bd)
        if self._on_tailor:
            tl = self._ghost("⎘ Tailor")
            tl.clicked.connect(lambda: self._on_tailor(self.job))
            actions.addWidget(tl)
        actions.addStretch()

        self.save_btn = self._ghost("★ Save")
        self.save_btn.clicked.connect(self._toggle_save)
        self.applied_btn = self._ghost("✓ Applied")
        self.applied_btn.clicked.connect(self._mark_applied)
        dismiss_btn = self._ghost("✕", danger=True)
        dismiss_btn.setToolTip("Dismiss — hide from future scans")
        dismiss_btn.clicked.connect(self._dismiss)
        actions.addWidget(self.save_btn)
        actions.addWidget(self.applied_btn)
        actions.addWidget(dismiss_btn)
        outer.addLayout(actions)
        self._refresh_state()

    def _ghost(self, text: str, danger: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        color = styles.DANGER if danger else styles.TEXT_PRIMARY
        btn.setStyleSheet(
            f"QPushButton {{ font-size:12px; padding:5px 12px; border:0.5px solid "
            f"{styles.BORDER}; border-radius:8px; background:transparent; color:{color}; }}"
            f"QPushButton:hover {{ background:{styles.LOG_BG}; border-color:{styles.TEXT_TERTIARY}; }}"
        )
        return btn

    def _refresh_state(self) -> None:
        saved = self.job.status == STATUS_SAVED
        applied = self.job.status == STATUS_APPLIED
        self.save_btn.setText("★ Saved" if saved else "★ Save")
        self.applied_btn.setText("✓ Applied" if applied else "✓ Applied")
        self.applied_btn.setEnabled(not applied)

    def _toggle_save(self) -> None:
        new = STATUS_NEW if self.job.status == STATUS_SAVED else STATUS_SAVED
        self._on_status(self.job, new)
        self._refresh_state()

    def _mark_applied(self) -> None:
        self._on_status(self.job, STATUS_APPLIED)
        self._refresh_state()

    def _dismiss(self) -> None:
        self._on_status(self.job, STATUS_DISMISSED)


class ResultsScreen(QWidget):
    back_to_setup = pyqtSignal()

    FILTERS = [("All", None), ("New", STATUS_NEW), ("Saved", STATUS_SAVED),
               ("Applied", STATUS_APPLIED)]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._jobs: list[Job] = []
        self._threshold = 0          # show everything by default; scoring is a sort
        self._resume_text = ""
        self._skills: list[str] = []
        self._active_filter = None
        self._query = ""
        self._build_ui()

    # --- layout ---
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.topbar = TopBar(2)
        root.addWidget(self.topbar)

        shell = QWidget()
        shell.setStyleSheet(f"background:{styles.SHELL};")
        body = QVBoxLayout(shell)
        body.setContentsMargins(24, 22, 24, 22)
        body.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        self.count_title = QLabel("0 jobs matched")
        self.count_title.setStyleSheet(
            f"font-size:15px; font-weight:600; color:{styles.TEXT_PRIMARY};"
        )
        self.count_sub = QLabel("sorted by match score")
        self.count_sub.setStyleSheet(f"font-size:12px; color:{styles.TEXT_SECONDARY};")
        titles.addWidget(self.count_title)
        titles.addWidget(self.count_sub)
        header.addLayout(titles)
        header.addStretch()
        self.export_combo = QComboBox()
        self.export_combo.addItems(["Export ▾", "CSV", "JSON", "HTML"])
        self.export_combo.setFixedHeight(32)
        self.export_combo.activated.connect(self._on_export)
        header.addWidget(self.export_combo)
        body.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title, company, or skill…")
        self.search.setFixedHeight(34)
        self.search.textChanged.connect(self._on_search)
        body.addWidget(self.search)

        # Threshold slider (live) — optional. 0 = show every matched job.
        thr_row = QHBoxLayout()
        thr_lbl = QLabel("Min score")
        thr_lbl.setStyleSheet(f"color:{styles.TEXT_SECONDARY}; font-size:12px;")
        self.thr_slider = QSlider(Qt.Horizontal)
        self.thr_slider.setRange(0, 95)
        self.thr_slider.setValue(0)
        self.thr_slider.valueChanged.connect(self._on_threshold)
        self.thr_value = QLabel("All")
        self.thr_value.setStyleSheet(
            f"color:{styles.TEXT_PRIMARY}; font-size:12px; font-weight:600; min-width:34px;"
        )
        thr_row.addWidget(thr_lbl)
        thr_row.addWidget(self.thr_slider, 1)
        thr_row.addWidget(self.thr_value)
        body.addLayout(thr_row)

        # Status filter pills.
        self.filter_row = QHBoxLayout()
        self.filter_row.setSpacing(6)
        self._filter_btns: list[QPushButton] = []
        for i, (label, _) in enumerate(self.FILTERS):
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(lambda _=False, idx=i: self._set_filter(idx))
            self._filter_btns.append(btn)
            self.filter_row.addWidget(btn)
        self.filter_row.addStretch()
        body.addLayout(self.filter_row)
        self._style_filters()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()
        scroll.setWidget(self.cards_host)
        body.addWidget(scroll, 1)

        self.back_footer_btn = QPushButton("New scan")
        self.back_footer_btn.setCursor(Qt.PointingHandCursor)
        self.back_footer_btn.setFixedHeight(40)
        self.back_footer_btn.setStyleSheet(
            f"QPushButton {{ background:{styles.ACCENT}; color:{styles.ACCENT_TEXT};"
            f" border:none; border-radius:8px; font-size:14px; font-weight:500; }}"
            f"QPushButton:hover {{ background:{styles.ACCENT_HOVER}; }}"
        )
        self.back_footer_btn.clicked.connect(self.back_to_setup.emit)
        body.addWidget(self.back_footer_btn)
        root.addWidget(shell, 1)

    def _style_filters(self) -> None:
        for btn in self._filter_btns:
            on = btn.isChecked()
            btn.setStyleSheet(
                f"QPushButton {{ font-size:12px; padding:5px 12px; border-radius:14px;"
                f" border:0.5px solid {styles.ACCENT if on else styles.BORDER};"
                f" background:{styles.INFO_BG if on else 'transparent'};"
                f" color:{styles.TEXT_PRIMARY if on else styles.TEXT_SECONDARY}; }}"
            )

    # --- data ---
    def set_results(self, jobs, threshold, resume_text="", skills=None) -> None:
        self._jobs = jobs
        self._threshold = threshold
        self._resume_text = resume_text
        self._skills = skills or []
        self.thr_slider.blockSignals(True)
        self.thr_slider.setValue(threshold)
        self.thr_slider.blockSignals(False)
        self.thr_value.setText("All" if threshold <= 0 else f"{threshold}%")
        self._rebuild()

    def _visible_jobs(self) -> list[Job]:
        _, status = self.FILTERS[self._active_index()]
        q = self._query.lower().strip()
        out = []
        for j in self._jobs:
            if j.status == STATUS_DISMISSED:
                continue
            if j.score < self._threshold:
                continue
            if status is not None and j.status != status:
                continue
            if q:
                hay = f"{j.title} {j.company} {' '.join(j.matched_skills)}".lower()
                if q not in hay:
                    continue
            out.append(j)
        return out

    def _active_index(self) -> int:
        for i, btn in enumerate(self._filter_btns):
            if btn.isChecked():
                return i
        return 0

    def _rebuild(self) -> None:
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        visible = self._visible_jobs()
        total_active = sum(1 for j in self._jobs if j.status != STATUS_DISMISSED)
        new_count = sum(1 for j in visible if j.is_new)
        noun = "job" if len(visible) == 1 else "jobs"
        if self._threshold <= 0:
            self.count_title.setText(f"{len(visible)} {noun}")
        else:
            self.count_title.setText(f"{len(visible)} {noun} · {self._threshold}%+ match")
        if self._jobs:
            filtered = total_active - len(visible)
            tail = f" · {filtered} below cutoff" if filtered > 0 and self._threshold > 0 else ""
            self.count_sub.setText(f"{new_count} new · sorted by match score{tail}")
        else:
            self.count_sub.setText("no jobs scored")
        self.export_combo.setEnabled(bool(visible))

        if not visible:
            empty = QLabel(
                "Nothing to show here.\n"
                "Drag the Min score slider to All, clear the search, or try another "
                "source / a different /jobs URL."
            )
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color:{styles.TEXT_SECONDARY}; font-size:13px;")
            self.cards_layout.insertWidget(0, empty)
            return

        for job in visible:
            card = JobCard(job, self._change_status, self._open_cover,
                          on_tailor=self._open_tailor, on_breakdown=self._open_breakdown)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    # --- interactions ---
    def _change_status(self, job: Job, status: str) -> None:
        job.status = status
        db.set_status(job.job_id, status)
        if status == STATUS_DISMISSED:
            self._rebuild()  # remove it from view
        else:
            self._rebuild()  # refresh counts/filters

    def _open_cover(self, job: Job) -> None:
        dlg = CoverLetterDialog(self._resume_text, job, self._skills, self)
        dlg.exec_()

    def _parsed_resume(self):
        """Resolve a ParsedResume for tailoring/breakdown: the saved default if
        any, else a quick local parse of the current résumé text (no LLM call)."""
        if getattr(self, "_parsed_cache", None) is not None:
            return self._parsed_cache
        from core.resume import default_resume, extract_structured
        got = default_resume()
        if got:
            self._parsed_cache = got["parsed"]
        else:
            self._parsed_cache, _ = extract_structured(self._resume_text, use_llm=False)
        return self._parsed_cache

    def _open_tailor(self, job: Job) -> None:
        from ui.dialogs_resume import TailorDialog
        TailorDialog(self._parsed_resume(), job, self).exec_()

    def _open_breakdown(self, job: Job) -> None:
        from ui.dialogs_resume import RubricDialog
        RubricDialog(self._parsed_resume(), job, parent=self).exec_()

    def _on_search(self, text: str) -> None:
        self._query = text
        self._rebuild()

    def _on_threshold(self, value: int) -> None:
        self._threshold = value
        self.thr_value.setText("All" if value <= 0 else f"{value}%")
        self._rebuild()

    def _set_filter(self, idx: int) -> None:
        for i, btn in enumerate(self._filter_btns):
            btn.setChecked(i == idx)
        self._style_filters()
        self._rebuild()

    def _on_export(self, index: int) -> None:
        fmt = {1: "csv", 2: "json", 3: "html"}.get(index)
        self.export_combo.setCurrentIndex(0)
        if not fmt:
            return
        visible = self._visible_jobs()
        if not visible:
            return
        default = f"drift_jobs_{datetime.now().strftime('%Y%m%d_%H%M')}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export results", default, f"{fmt.upper()} (*.{fmt})"
        )
        if path:
            saved = report.export(visible, self._threshold, path, fmt)
            QMessageBox.information(
                self, "Exported", f"Saved {len(visible)} jobs to:\n{saved}"
            )
