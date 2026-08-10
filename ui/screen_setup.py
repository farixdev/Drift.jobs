import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core import parser
from core.scraper import SOURCES
from core.url_utils import InvalidJobsUrlError, normalize_jobs_url
from ui import styles
from ui.widgets import SourceCheckbox, TopBar


class SetupScreen(QWidget):
    # emits: resume_path, source_keys, threshold, resume_text, custom_url
    start_scan = pyqtSignal(str, list, int, str, str)
    open_builder = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._resume_path = ""
        self._resume_text = ""
        self._parsed = False
        self._custom_url = ""
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.topbar = TopBar(0)
        root.addWidget(self.topbar)

        shell = QWidget()
        shell.setStyleSheet(f"background:{styles.SHELL};")
        body = QVBoxLayout(shell)
        body.setContentsMargins(24, 28, 24, 28)

        self.upload_zone = QPushButton()
        self.upload_zone.setCursor(Qt.PointingHandCursor)
        self.upload_zone.setMinimumHeight(120)
        self.upload_zone.clicked.connect(self._browse_resume)
        self._set_upload_idle()
        body.addWidget(self.upload_zone)
        body.addSpacing(20)

        custom_label = QLabel("Custom job site (optional)")
        custom_label.setStyleSheet(
            f"color:{styles.TEXT_SECONDARY}; font-size:12px; font-weight:500;"
        )
        body.addWidget(custom_label)

        self.custom_url_input = QLineEdit()
        self.custom_url_input.setPlaceholderText("company.com/jobs")
        self.custom_url_input.setFixedHeight(36)
        self.custom_url_input.textChanged.connect(self._on_custom_url_changed)
        body.addWidget(self.custom_url_input)

        self.custom_url_hint = QLabel("Must end with /jobs only — e.g. company.com/jobs")
        self.custom_url_hint.setStyleSheet(
            f"color:{styles.TEXT_TERTIARY}; font-size:11px;"
        )
        body.addWidget(self.custom_url_hint)
        body.addSpacing(16)

        section = QLabel("Where to search")
        section.setStyleSheet(
            f"color:{styles.TEXT_SECONDARY}; font-size:12px; font-weight:500;"
        )
        body.addWidget(section)

        grid = QGridLayout()
        grid.setSpacing(8)
        # Keyed by scraper key; recommended (fast, key-free JSON) default ON.
        self.sources: dict[str, SourceCheckbox] = {}
        for i, src in enumerate(SOURCES):
            box = SourceCheckbox(
                src["label"],
                checked=src["recommended"],
                note=src["note"],
                recommended=src["recommended"],
            )
            self.sources[src["key"]] = box
            grid.addWidget(box, i // 2, i % 2)
        body.addLayout(grid)
        body.addSpacing(20)


        slider_label = QLabel("Minimum match score")
        slider_label.setStyleSheet(
            f"color:{styles.TEXT_SECONDARY}; font-size:12px; font-weight:500;"
        )
        body.addWidget(slider_label)

        slider_row = QHBoxLayout()
        low = QLabel("Low")
        low.setStyleSheet(f"color:{styles.TEXT_SECONDARY}; font-size:12px;")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(30)
        self.slider.setMaximum(95)
        self.slider.setValue(70)
        self.slider.valueChanged.connect(self._update_threshold_label)
        high = QLabel("High")
        high.setStyleSheet(f"color:{styles.TEXT_SECONDARY}; font-size:12px;")
        self.threshold_label = QLabel("70%")
        self.threshold_label.setStyleSheet(
            f"color:{styles.TEXT_PRIMARY}; font-size:13px; font-weight:500; min-width:36px;"
        )
        slider_row.addWidget(low)
        slider_row.addWidget(self.slider, 1)
        slider_row.addWidget(high)
        slider_row.addWidget(self.threshold_label)
        body.addLayout(slider_row)
        body.addSpacing(24)

        self.start_btn = QPushButton("Start scanning")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setFixedHeight(36)
        self.start_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {styles.ACCENT};
                color: {styles.ACCENT_TEXT};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background: {styles.ACCENT_HOVER}; }}
            """
        )
        self.start_btn.clicked.connect(self._on_start)
        body.addWidget(self.start_btn)

        self.advanced_btn = QPushButton("Advanced search builder →")
        self.advanced_btn.setCursor(Qt.PointingHandCursor)
        self.advanced_btn.setFixedHeight(32)
        self.advanced_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none; color:{styles.TEXT_SECONDARY};"
            f" font-size:13px; }} QPushButton:hover {{ color:{styles.ACCENT}; }}"
        )
        self.advanced_btn.clicked.connect(self.open_builder.emit)
        body.addWidget(self.advanced_btn)

        # Scrollable so the full source list + controls never overflow the window.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(shell)
        root.addWidget(scroll, 1)
        self.setAcceptDrops(True)

    def _on_custom_url_changed(self, text: str) -> None:
        raw = text.strip()
        using_custom = bool(raw)
        for checkbox in self.sources.values():
            checkbox.set_source_enabled(not using_custom)

        if not raw:
            self._custom_url = ""
            self.custom_url_hint.setText("Must end with /jobs only — e.g. company.com/jobs")
            self.custom_url_hint.setStyleSheet(
                f"color:{styles.TEXT_TERTIARY}; font-size:11px;"
            )
            return

        try:
            self._custom_url = normalize_jobs_url(raw)
            self.custom_url_hint.setText(f"Will scan: {self._custom_url}")
            self.custom_url_hint.setStyleSheet(
                f"color:{styles.MATCH_TEXT}; font-size:11px;"
            )
        except InvalidJobsUrlError as exc:
            self._custom_url = ""
            self.custom_url_hint.setText(str(exc))
            self.custom_url_hint.setStyleSheet(
                f"color:{styles.WARNING}; font-size:11px;"
            )

    def _set_upload_idle(self) -> None:
        self.upload_zone.setText("")
        layout = QVBoxLayout(self.upload_zone)
        layout.setContentsMargins(20, 28, 20, 28)
        icon = QLabel("📄")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:24px; border:none; background:transparent;")
        title = QLabel("Drop your resume here")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"font-size:14px; font-weight:500; color:{styles.TEXT_PRIMARY}; border:none; background:transparent;"
        )
        sub = QLabel("PDF, DOC, or DOCX · local + AI scoring")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(
            f"font-size:12px; color:{styles.TEXT_TERTIARY}; border:none; background:transparent;"
        )
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(sub)
        self.upload_zone.setStyleSheet(
            f"""
            QPushButton {{
                background: {styles.SURFACE};
                border: 1px dashed {styles.BORDER};
                color: {styles.TEXT_PRIMARY};
                border-radius: 12px;
            }}
            """
        )

    def _set_upload_done(self, filename: str) -> None:
        QWidget().setLayout(self.upload_zone.layout())
        layout = QVBoxLayout(self.upload_zone)
        layout.setContentsMargins(20, 28, 20, 28)
        check = QLabel("✓")
        check.setAlignment(Qt.AlignCenter)
        check.setStyleSheet(
            f"font-size:20px; color:{styles.SUCCESS}; border:none; background:transparent;"
        )
        name = QLabel(filename)
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet(
            f"font-size:14px; font-weight:500; color:{styles.TEXT_PRIMARY}; border:none; background:transparent;"
        )
        sub = QLabel("Resume ready")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(
            f"font-size:12px; color:{styles.TEXT_TERTIARY}; border:none; background:transparent;"
        )
        layout.addWidget(check)
        layout.addWidget(name)
        layout.addWidget(sub)
        self.upload_zone.setStyleSheet(
            f"""
            QPushButton {{
                background: {styles.SUCCESS_BG};
                border: 1px solid {styles.SUCCESS};
                color: {styles.TEXT_PRIMARY};
                border-radius: 12px;
            }}
            """
        )

    def _update_threshold_label(self, value: int) -> None:
        self.threshold_label.setText(f"{value}%")

    def _browse_resume(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select resume",
            "",
            "Resumes (*.pdf *.doc *.docx)",
        )
        if path:
            self._load_resume(path)

    def _load_resume(self, path: str) -> None:
        try:
            text = parser.extract(path)
            if len(text.strip()) < 20:
                raise ValueError(
                    "Could not extract enough text. Try a text-based PDF or DOCX."
                )
            self._resume_text = text
            self._resume_path = path
            self._parsed = True
            self._set_upload_done(os.path.basename(path))
            self.upload_zone.setToolTip("")
            self.start_btn.setText("Start scanning")
        except Exception as exc:
            self._parsed = False
            self._resume_path = ""
            self._resume_text = ""
            self._set_upload_idle()
            self.upload_zone.setToolTip(str(exc))
            self.start_btn.setText(str(exc)[:80])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".pdf", ".doc", ".docx")):
                self._load_resume(path)
                break

    def _on_start(self) -> None:
        if not self._resume_path or not self._parsed:
            self.start_btn.setText("Upload a resume first")
            return

        custom_raw = self.custom_url_input.text().strip()
        custom_url = ""
        if custom_raw:
            try:
                custom_url = normalize_jobs_url(custom_raw)
            except InvalidJobsUrlError as exc:
                self.start_btn.setText(str(exc)[:70])
                return
            selected: list[str] = []
        else:
            selected = [k for k, w in self.sources.items() if w.is_on()]
            if not selected:
                self.start_btn.setText("Select at least one source")
                return

        self.start_btn.setText("Start scanning")
        self.start_scan.emit(
            self._resume_path,
            selected,
            self.slider.value(),
            self._resume_text,
            custom_url,
        )
