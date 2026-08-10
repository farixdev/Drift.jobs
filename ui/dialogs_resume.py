"""Resume dialogs (Phase 4): tailored-résumé diff view + rubric breakdown."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.resume import (
    check_ats,
    export as export_resume,
    gap_report,
    score_against_job,
    tailor_bullets,
)
from ui.components import Button, Chip, InlineBanner, Label, ProgressBar, Spinner
from ui.theme import theme


def _job_dict(job) -> dict:
    return {"title": job.title, "description": job.description,
            "work_mode": "remote" if job.remote else "unspecified",
            "location_country": "", "salary_min": None, "salary_max": None}


class _TailorWorker(QThread):
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, parsed, job):
        super().__init__()
        self.parsed, self.job = parsed, job

    def run(self):
        try:
            self.done.emit(tailor_bullets(self.parsed, _job_dict(self.job)))
        except Exception as exc:
            self.failed.emit(str(exc))


class TailorDialog(QDialog):
    """Shows each bullet's honest rewrite as a diff; flagged (would-fabricate)
    rewrites are reverted and labelled. Export the approved variant."""

    def __init__(self, parsed, job, parent=None):
        super().__init__(parent)
        self._parsed = parsed
        self._job = job
        self._diffs = []
        self.setWindowTitle("Tailor résumé")
        self.setMinimumSize(620, 620)
        self.setStyleSheet(f"background:{theme().palette().bg_base};")
        self._build()
        self._generate()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)
        root.addWidget(Label(f"Tailor résumé — {self._job.title}", "title3", "primary"))
        root.addWidget(Label("Bullets are rephrased to surface matched keywords. "
                             "Nothing is invented — any rewrite that would add a metric "
                             "or skill you don't have is reverted and flagged.",
                             "footnote", "secondary"))
        self._status = QHBoxLayout()
        self._spinner = Spinner(18)
        self._status.addWidget(self._spinner)
        self._status_lbl = Label("Generating…", "subhead", "secondary")
        self._status.addWidget(self._status_lbl, 1)
        root.addLayout(self._status)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._host = QWidget()
        self._list = QVBoxLayout(self._host)
        self._list.setSpacing(8)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, 1)

        acts = QHBoxLayout()
        acts.addStretch()
        for fmt in ("txt", "docx"):
            b = Button(f"Export {fmt.upper()}", "secondary", "md")
            b.clicked.connect(lambda _=False, f=fmt: self._export(f))
            acts.addWidget(b)
        close = Button("Close", "plain", "md")
        close.clicked.connect(self.accept)
        acts.addWidget(close)
        root.addLayout(acts)

    def _generate(self):
        self._worker = _TailorWorker(self._parsed, self._job)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(lambda m: self._status_lbl.setText(f"Failed: {m}"))
        self._worker.start()

    def _on_done(self, diffs):
        self._diffs = diffs
        self._spinner.setVisible(False)
        changed = sum(1 for d in diffs if d.changed)
        flagged = sum(1 for d in diffs if d.flagged)
        self._status_lbl.setText(
            f"{changed} bullet(s) improved · {flagged} reverted to protect against fabrication")
        p = theme().palette()
        for d in diffs:
            card = QFrame()
            card.setStyleSheet(f"QFrame{{background:{p.bg_elevated}; border:1px solid "
                               f"{p.separator_nonopaque}; border-radius:10px;}}")
            cl = QVBoxLayout(card)
            cl.addWidget(Label(d.role, "caption1", "tertiary"))
            if d.flagged:
                cl.addWidget(InlineBanner(f"Reverted — {d.flag_reason}", "warning"))
                cl.addWidget(Label(d.original, "subhead", "primary"))
            elif d.changed:
                orig = Label(d.original, "footnote", "tertiary")
                orig.setStyleSheet(f"color:{p.label_tertiary}; text-decoration:line-through;")
                cl.addWidget(orig)
                cl.addWidget(Label(d.rewritten, "subhead", "success"))
            else:
                cl.addWidget(Label(d.original, "subhead", "secondary"))
            self._list.addWidget(card)
        self._list.addStretch()

    def _tailored(self):
        """Apply approved rewrites into a copy of the parsed résumé."""
        import copy
        out = copy.deepcopy(self._parsed)
        idx = 0
        for e in out.experience or []:
            new_bullets = []
            for _ in (e.bullets or []):
                if idx < len(self._diffs):
                    new_bullets.append(self._diffs[idx].rewritten)
                    idx += 1
            e.bullets = new_bullets
        return out

    def _export(self, fmt):
        path, _ = QFileDialog.getSaveFileName(self, "Export tailored résumé",
                                             f"resume_tailored.{fmt}", f"{fmt.upper()} (*.{fmt})")
        if path:
            export_resume(self._tailored(), path, fmt)
            self._status_lbl.setText(f"Exported to {path}")


class RubricDialog(QDialog):
    """The transparent per-dimension score breakdown for one job."""

    def __init__(self, parsed, job, criteria=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Match breakdown")
        self.setMinimumSize(520, 560)
        self.setStyleSheet(f"background:{theme().palette().bg_base};")
        ats = check_ats(parsed, parsed.summary + " " + " ".join(parsed.all_skills()), "")
        r = score_against_job(parsed, _job_dict(job), criteria=criteria, ats_result=ats)
        self._build(r, job)

    def _build(self, r, job):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(Label(f"{job.title}", "title3", "primary"), 1)
        head.addWidget(Label(f"{r['composite']}", "largeTitle", "accent"))
        root.addLayout(head)

        labels = {"hard_skills": "Hard-skill coverage", "experience_years": "Years of experience",
                  "seniority": "Seniority alignment", "domain": "Domain overlap",
                  "education": "Education / certs", "location": "Location / work-mode",
                  "salary": "Salary band", "ats": "ATS mechanics"}
        for key, dim in r["dimensions"].items():
            box = QWidget()
            row = QVBoxLayout(box)
            row.setContentsMargins(0, 4, 0, 4)
            row.setSpacing(4)
            top = QHBoxLayout()
            top.addWidget(Label(labels.get(key, key), "subhead", "primary"), 1)
            score = dim["score"]
            top.addWidget(Label("n/a" if score is None else str(score), "subhead",
                               "secondary" if score is None else "primary"))
            row.addLayout(top)
            if score is not None:
                row.addWidget(ProgressBar(score))
            detail = Label(dim["detail"], "caption1", "tertiary")
            detail.setWordWrap(True)
            row.addWidget(detail)
            root.addWidget(box)

        if r["strengths"]:
            root.addWidget(Label("Strengths", "footnote", "secondary"))
            sr = QHBoxLayout()
            for s in r["strengths"][:8]:
                sr.addWidget(Chip(s, "success"))
            sr.addStretch()
            root.addLayout(sr)
        if r["missing"]:
            root.addWidget(Label("Gaps", "footnote", "secondary"))
            mr = QHBoxLayout()
            for m in r["missing"][:8]:
                mr.addWidget(Chip(m, "warning"))
            mr.addStretch()
            root.addLayout(mr)

        close = Button("Close", "primary", "md")
        close.clicked.connect(self.accept)
        root.addWidget(close, 0, Qt.AlignRight)
