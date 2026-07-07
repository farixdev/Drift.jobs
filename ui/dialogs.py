import webbrowser

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from core import ai_engine
from core.config import (
    GROQ_MODELS,
    get_groq_api_key,
    get_groq_model,
    get_max_jobs_to_score,
    save_settings,
)
from ui import styles


class SettingsDialog(QDialog):
    """Configure the Groq API key, model, and scoring depth — writes to .env."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self.setStyleSheet(styles.APP_STYLESHEET)
        self._build()

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{styles.TEXT_SECONDARY}; font-size:12px; font-weight:500;"
        )
        return lbl

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(8)

        heading = QLabel("Settings")
        heading.setStyleSheet(
            f"color:{styles.TEXT_PRIMARY}; font-size:16px; font-weight:600;"
        )
        root.addWidget(heading)
        sub = QLabel("Add a free Groq key for AI scoring & cover letters. "
                     "Without one, Drift still works with local scoring.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{styles.TEXT_TERTIARY}; font-size:12px;")
        root.addWidget(sub)
        root.addSpacing(8)

        root.addWidget(self._label("Groq API key"))
        key_row = QHBoxLayout()
        self.key_input = QLineEdit(get_groq_api_key())
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setPlaceholderText("gsk_…")
        self.key_input.setFixedHeight(34)
        self.show_btn = QPushButton("Show")
        self.show_btn.setFixedWidth(60)
        self.show_btn.setCursor(Qt.PointingHandCursor)
        self.show_btn.clicked.connect(self._toggle_echo)
        key_row.addWidget(self.key_input, 1)
        key_row.addWidget(self.show_btn)
        root.addLayout(key_row)

        get_key = QLabel(
            f'<a style="color:{styles.MATCH_TEXT};text-decoration:none;" '
            f'href="https://console.groq.com/keys">→ Get a free key</a>'
        )
        get_key.setOpenExternalLinks(False)
        get_key.linkActivated.connect(lambda _: webbrowser.open("https://console.groq.com/keys"))
        get_key.setStyleSheet("font-size:11px;")
        root.addWidget(get_key)
        root.addSpacing(8)

        root.addWidget(self._label("Model"))
        self.model_input = QComboBox()
        self.model_input.setEditable(True)
        self.model_input.addItems(list(GROQ_MODELS))
        self.model_input.setCurrentText(get_groq_model())
        self.model_input.setFixedHeight(34)
        root.addWidget(self.model_input)
        root.addSpacing(8)

        root.addWidget(self._label("Jobs to score with AI per scan"))
        self.max_jobs = QSpinBox()
        self.max_jobs.setRange(1, 60)
        self.max_jobs.setValue(get_max_jobs_to_score())
        self.max_jobs.setFixedHeight(34)
        root.addWidget(self.max_jobs)
        root.addSpacing(16)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setCursor(Qt.PointingHandCursor)
        save.setStyleSheet(
            f"QPushButton {{ background:{styles.ACCENT}; color:{styles.ACCENT_TEXT};"
            f" border:none; border-radius:8px; padding:8px 18px; font-weight:500; }}"
            f"QPushButton:hover {{ background:{styles.ACCENT_HOVER}; }}"
        )
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def _toggle_echo(self) -> None:
        if self.key_input.echoMode() == QLineEdit.Password:
            self.key_input.setEchoMode(QLineEdit.Normal)
            self.show_btn.setText("Hide")
        else:
            self.key_input.setEchoMode(QLineEdit.Password)
            self.show_btn.setText("Show")

    def _save(self) -> None:
        save_settings(
            api_key=self.key_input.text(),
            model=self.model_input.currentText(),
            max_jobs=self.max_jobs.value(),
        )
        ai_engine.reset_client()
        self.accept()


class _CoverLetterWorker(QThread):
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, resume_text, job, tone, parent=None):
        super().__init__(parent)
        self.resume_text = resume_text
        self.job = job
        self.tone = tone

    def run(self) -> None:
        try:
            text = ai_engine.generate_cover_letter(
                self.resume_text, self.job.title, self.job.company,
                self.job.summary or "", tone=self.tone,
            )
            self.done.emit(text)
        except Exception as exc:
            self.failed.emit(str(exc))


def local_cover_letter(job, skills: list[str]) -> str:
    """Offline fallback when no API key is set."""
    top = ", ".join((job.matched_skills or skills)[:4]) or "my background"
    company = job.company or "your team"
    return (
        f"Dear Hiring Manager,\n\n"
        f"I'm writing to express my strong interest in the {job.title} role at "
        f"{company}. The position aligns closely with my experience, and I'm "
        f"confident I can contribute quickly.\n\n"
        f"My background in {top} maps directly to what this role calls for. I "
        f"enjoy taking ownership of problems end to end and collaborating with a "
        f"team to ship work that matters.\n\n"
        f"I'd welcome the chance to discuss how I can help {company}. Thank you "
        f"for your time and consideration.\n\n"
        f"Best regards,\n[Your name]\n\n"
        f"— Draft generated by Drift. Add a Groq API key in Settings for a "
        f"tailored, AI-written letter."
    )


class CoverLetterDialog(QDialog):
    def __init__(self, resume_text: str, job, skills: list[str], parent=None):
        super().__init__(parent)
        self.resume_text = resume_text
        self.job = job
        self.skills = skills
        self._worker: _CoverLetterWorker | None = None
        self.setWindowTitle("Cover letter")
        self.setMinimumSize(560, 560)
        self.setStyleSheet(styles.APP_STYLESHEET)
        self._build()
        self._generate()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(10)

        heading = QLabel(f"Cover letter — {self.job.title}")
        heading.setStyleSheet(
            f"color:{styles.TEXT_PRIMARY}; font-size:15px; font-weight:600;"
        )
        heading.setWordWrap(True)
        root.addWidget(heading)
        sub = QLabel(f"{self.job.company} · tailored to your resume")
        sub.setStyleSheet(f"color:{styles.TEXT_TERTIARY}; font-size:12px;")
        root.addWidget(sub)

        tone_row = QHBoxLayout()
        tone_row.addWidget(QLabel("Tone"))
        self.tone = QComboBox()
        self.tone.addItems(["professional", "warm", "enthusiastic", "concise"])
        self.tone.setFixedHeight(30)
        tone_row.addWidget(self.tone)
        tone_row.addStretch()
        root.addLayout(tone_row)

        self.editor = QPlainTextEdit()
        self.editor.setStyleSheet(
            f"QPlainTextEdit {{ background:{styles.SURFACE}; color:{styles.TEXT_PRIMARY};"
            f" border:1px solid {styles.BORDER}; border-radius:10px; padding:12px;"
            f" font-size:13px; }}"
        )
        root.addWidget(self.editor, 1)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{styles.TEXT_TERTIARY}; font-size:11px;")
        root.addWidget(self.status)

        actions = QHBoxLayout()
        self.regen_btn = QPushButton("↻ Regenerate")
        self.regen_btn.setCursor(Qt.PointingHandCursor)
        self.regen_btn.clicked.connect(self._generate)
        copy_btn = QPushButton("Copy")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self._copy)
        save_btn = QPushButton("Save .txt")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        actions.addWidget(self.regen_btn)
        actions.addStretch()
        actions.addWidget(copy_btn)
        actions.addWidget(save_btn)
        actions.addWidget(close_btn)
        root.addLayout(actions)

    def _generate(self) -> None:
        if not ai_engine.has_api_key():
            self.editor.setPlainText(local_cover_letter(self.job, self.skills))
            self.status.setText("Local draft — add a Groq key in Settings for AI tailoring.")
            return
        self.regen_btn.setEnabled(False)
        self.status.setText("Writing your letter…")
        self.editor.setPlainText("")
        self._worker = _CoverLetterWorker(self.resume_text, self.job, self.tone.currentText())
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, text: str) -> None:
        self.editor.setPlainText(text)
        self.status.setText("Edit freely, then copy or save.")
        self.regen_btn.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.editor.setPlainText(local_cover_letter(self.job, self.skills))
        self.status.setText(f"AI unavailable ({message[:60]}) — showing a local draft.")
        self.regen_btn.setEnabled(True)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.editor.toPlainText())
        self.status.setText("Copied to clipboard.")

    def _save(self) -> None:
        safe = "".join(c for c in self.job.title if c.isalnum() or c in " -_")[:40].strip()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save cover letter", f"cover_letter_{safe or 'job'}.txt", "Text (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.editor.toPlainText())
            self.status.setText(f"Saved to {path}")
