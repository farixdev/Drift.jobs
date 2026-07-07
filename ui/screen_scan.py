from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ui import styles
from ui.widgets import LogLine, ThinProgressBar, TopBar


class ScanScreen(QWidget):
    stop_clicked = pyqtSignal()

    LOG_KEYS = [
        "resume",
        "keywords",
        "search",
        "scoring",
        "filter",
        "report",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_lines: list[LogLine] = []
        self._search_line: LogLine | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.topbar = TopBar(1)
        root.addWidget(self.topbar)

        shell = QWidget()
        shell.setStyleSheet(f"background:{styles.SHELL};")
        body = QVBoxLayout(shell)
        body.setContentsMargins(24, 28, 24, 28)

        self.title = QLabel("Scanning jobs for you")
        self.title.setStyleSheet(
            f"font-size:14px; font-weight:500; color:{styles.TEXT_PRIMARY};"
        )
        body.addWidget(self.title)

        self.subtitle = QLabel("Based on your resume")
        self.subtitle.setStyleSheet(
            f"font-size:12px; color:{styles.TEXT_SECONDARY};"
        )
        body.addWidget(self.subtitle)
        body.addSpacing(16)

        self.progress = ThinProgressBar()
        body.addWidget(self.progress)
        body.addSpacing(20)

        self.log_box = QWidget()
        self.log_box.setStyleSheet(
            f"background:{styles.LOG_BG}; border-radius:8px;"
        )
        self.log_layout = QVBoxLayout(self.log_box)
        self.log_layout.setContentsMargins(16, 14, 16, 14)
        self.log_layout.setSpacing(8)
        body.addWidget(self.log_box, 1)

        hint = QLabel("Usually 20–60 seconds · sources run in parallel")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"font-size:11px; color:{styles.TEXT_TERTIARY};")
        body.addWidget(hint)
        body.addSpacing(8)

        self.stop_btn = QPushButton("Stop & score what we have")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setFixedHeight(34)
        self.stop_btn.setStyleSheet(
            f"QPushButton {{ font-size:13px; border:0.5px solid {styles.BORDER};"
            f" border-radius:8px; background:transparent; color:{styles.TEXT_SECONDARY}; }}"
            f"QPushButton:hover {{ background:{styles.LOG_BG}; color:{styles.TEXT_PRIMARY}; }}"
        )
        self.stop_btn.clicked.connect(self._on_stop)
        body.addWidget(self.stop_btn)

        root.addWidget(shell, 1)

    def _on_stop(self) -> None:
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Finishing up…")
        self.stop_clicked.emit()

    def reset(self, threshold: int) -> None:
        self._threshold = threshold
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("Stop & score what we have")
        self.progress.set_value(0)
        self.subtitle.setText("Based on your resume")
        while self.log_layout.count():
            item = self.log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._log_lines = []
        self._search_line = None

        placeholders = [
            "Resume parsed",
            "Keywords generated",
            "Searching job boards",
            "Scoring jobs against your profile",
            f"Filtering by {threshold}% threshold",
            "Generating report",
        ]

        for text in placeholders:
            line = LogLine(text, "pending")
            self.log_layout.addWidget(line)
            self._log_lines.append(line)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(f"Based on your resume · {text}")

    def set_progress(self, value: int) -> None:
        self.progress.set_value(value)

    def update_log(self, message: str, status: str) -> None:
        lower = message.lower()

        if "parsing resume" in lower or "resume parsed" in lower:
            self._set_line(0, message, status)
        elif "keyword" in lower:
            self._set_line(1, message, status)
        elif lower.startswith("searching") or "listings found" in lower or "—" in message:
            if self._search_line is None:
                self._search_line = LogLine(message, status)
                self.log_layout.insertWidget(2, self._search_line)
            else:
                self._search_line.set_message(message)
                self._search_line.set_status(status)
        elif "scoring" in lower:
            self._set_line(3, message, status)
        elif "filtering" in lower:
            self._set_line(4, message, status)
        elif "generating" in lower or lower.startswith("done"):
            self._set_line(5, message, status)
        else:
            line = LogLine(message, status)
            self.log_layout.addWidget(line)

    def _set_line(self, index: int, message: str, status: str) -> None:
        if 0 <= index < len(self._log_lines):
            self._log_lines[index].set_message(message)
            self._log_lines[index].set_status(status)
