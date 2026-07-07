from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPainter, QColor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import styles


def chip(text: str, bg: str, fg: str) -> QLabel:
    """A small rounded pill label (skill tags, badges, verdicts)."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background:{bg}; color:{fg}; font-size:11px; font-weight:500;"
        f" padding:2px 8px; border-radius:10px;"
    )
    return lbl


class TopBar(QFrame):
    settings_clicked = pyqtSignal()

    def __init__(self, active_step: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("topbar")
        self.setStyleSheet(
            f"""
            QFrame#topbar {{
                background: {styles.SHELL};
                border: none;
                border-bottom: 1px solid {styles.BORDER};
            }}
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)

        logo = QLabel(
            f'drift<span style="color:{styles.TEXT_TERTIARY};font-weight:400">.jobs</span>'
        )
        logo.setTextFormat(Qt.RichText)
        logo.setFont(QFont("Segoe UI", 11, QFont.Medium))
        layout.addWidget(logo)
        layout.addStretch()

        self._dots: list[QLabel] = []
        dots_wrap = QHBoxLayout()
        dots_wrap.setSpacing(6)
        for _ in range(3):
            dot = QLabel()
            self._dots.append(dot)
            dots_wrap.addWidget(dot)
        layout.addLayout(dots_wrap)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none; font-size:15px;"
            f" color:{styles.TEXT_TERTIARY}; padding:0; }}"
            f"QPushButton:hover {{ color:{styles.TEXT_PRIMARY}; }}"
        )
        self.settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addSpacing(8)
        layout.addWidget(self.settings_btn)
        self.set_active_step(active_step)

    def set_active_step(self, step: int) -> None:
        for i, dot in enumerate(self._dots):
            if i == step:
                dot.setFixedSize(18, 6)
                dot.setStyleSheet(f"background:{styles.ACCENT}; border-radius:3px;")
            else:
                dot.setFixedSize(6, 6)
                dot.setStyleSheet(f"background:{styles.DOT_PENDING}; border-radius:3px;")


class SourceCheckbox(QFrame):
    toggled_on = pyqtSignal(bool)

    def __init__(self, label: str, checked: bool = False, note: str = "",
                 recommended: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("SourceCheckbox")
        self._label_text = label
        self._note = note
        self._recommended = recommended
        self._on = checked
        self._enabled = True
        self.setCursor(Qt.PointingHandCursor)
        self._build_ui()
        self._refresh()

    def set_source_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        if not enabled:
            self._on = False
        self._refresh()

    def _build_ui(self) -> None:
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(8)
        self._dot = QFrame()
        self._dot.setFixedSize(14, 14)
        self._inner = QFrame()
        self._inner.setFixedSize(6, 6)
        dot_lay = QVBoxLayout(self._dot)
        dot_lay.setContentsMargins(4, 4, 4, 4)
        dot_lay.addWidget(self._inner, 0, Qt.AlignCenter)
        self._layout.addWidget(self._dot, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        star = f' <span style="color:{styles.STAR}">★</span>' if self._recommended else ""
        head = QLabel(f"{self._label_text}{star}")
        head.setTextFormat(Qt.RichText)
        self._label = head
        text_col.addWidget(head)
        if self._note:
            note = QLabel(self._note)
            note.setStyleSheet(f"color:{styles.TEXT_TERTIARY}; font-size:10px;")
            self._note_label = note
            text_col.addWidget(note)
        self._layout.addLayout(text_col, 1)
        self._layout.addStretch()

    def mousePressEvent(self, event):
        if not self._enabled:
            return
        self._on = not self._on
        self._refresh()
        self.toggled_on.emit(self._on)
        super().mousePressEvent(event)

    def is_on(self) -> bool:
        return self._on

    def _refresh(self) -> None:
        if not self._enabled:
            border = styles.BORDER
            bg = styles.LOG_BG
            label_color = styles.TEXT_TERTIARY
            dot_border = styles.TEXT_TERTIARY
            dot_bg = "transparent"
        else:
            border = styles.ACCENT if self._on else styles.BORDER
            bg = styles.INFO_BG if self._on else styles.SURFACE
            label_color = styles.TEXT_PRIMARY
            dot_border = styles.ACCENT if self._on else styles.TEXT_TERTIARY
            dot_bg = styles.ACCENT if self._on else "transparent"
        self.setStyleSheet(
            f"""
            SourceCheckbox {{
                background: {bg};
                border: 0.5px solid {border};
                border-radius: 8px;
            }}
            """
        )
        self._dot.setStyleSheet(
            f"""
            background: {dot_bg};
            border: 0.5px solid {dot_border};
            border-radius: 3px;
            """
        )
        inner_fill = styles.ACCENT_TEXT if self._on and self._enabled else "transparent"
        self._inner.setStyleSheet(
            f"background: {inner_fill}; border-radius: 1px;"
        )
        self._label.setStyleSheet(f"color: {label_color}; font-size: 13px;")


class ThinProgressBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self._value = 0
        self.setStyleSheet(f"background:{styles.BORDER}; border-radius:2px;")

    def set_value(self, value: int) -> None:
        self._value = max(0, min(100, value))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = int(self.width() * self._value / 100)
        painter.setBrush(QColor(styles.ACCENT))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, w, self.height(), 2, 2)


class LogLine(QWidget):
    def __init__(self, message: str = "", status: str = "pending", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.dot = QLabel()
        self.dot.setFixedSize(6, 6)
        self.label = QLabel(message)
        self.label.setStyleSheet(f"color:{styles.TEXT_SECONDARY}; font-size:12px;")
        layout.addWidget(self.dot, 0, Qt.AlignVCenter)
        layout.addWidget(self.label, 1)
        self.set_status(status)

    def set_message(self, message: str) -> None:
        self.label.setText(message)

    def set_status(self, status: str) -> None:
        color = {
            "pending": styles.DOT_PENDING,
            "active": styles.DOT_ACTIVE,
            "done": styles.DOT_DONE,
        }.get(status, styles.DOT_PENDING)
        self.dot.setStyleSheet(f"background:{color}; border-radius:3px;")
