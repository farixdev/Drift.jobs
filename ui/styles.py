"""Dark minimal design tokens — drift.jobs"""

# Base
BG = "#09090B"
SHELL = "#0F0F11"
SURFACE = "#141416"
RAISED = "#1C1C1F"
BORDER = "#27272A"
BORDER_SUBTLE = "rgba(255, 255, 255, 0.06)"

# Text
TEXT_PRIMARY = "#FAFAFA"
TEXT_SECONDARY = "#A1A1AA"
TEXT_TERTIARY = "#71717A"

# Actions
ACCENT = "#FAFAFA"
ACCENT_TEXT = "#09090B"
ACCENT_HOVER = "#E4E4E7"

# Semantic
SUCCESS = "#34D399"
SUCCESS_BG = "rgba(52, 211, 153, 0.12)"
WARNING = "#FBBF24"
MATCH_BG = "rgba(52, 211, 153, 0.14)"
MATCH_TEXT = "#6EE7B7"
LOC_BG = "#27272A"
LOC_TEXT = "#A1A1AA"

# Progress / log
DOT_PENDING = "#3F3F46"
DOT_ACTIVE = "#34D399"
DOT_DONE = "#52525B"
LOG_BG = "#0C0C0E"
INFO_BORDER = "#52525B"
INFO_BG = "#1A1A1D"

# Gap (missing skills) chips
GAP_BG = "rgba(251, 191, 36, 0.12)"
GAP_TEXT = "#FCD34D"

# NEW badge + accents
NEW_BG = "rgba(96, 165, 250, 0.16)"
NEW_TEXT = "#93C5FD"
DANGER = "#F87171"
DANGER_BG = "rgba(248, 113, 113, 0.12)"
STAR = "#FBBF24"
RECOMMENDED_TEXT = "#6EE7B7"


def verdict_colors(score: int) -> tuple[str, str]:
    """(background, text) for a score's verdict pill."""
    if score >= 80:
        return "rgba(52, 211, 153, 0.14)", "#6EE7B7"
    if score >= 60:
        return "rgba(96, 165, 250, 0.16)", "#93C5FD"
    if score >= 40:
        return "rgba(251, 191, 36, 0.14)", "#FCD34D"
    return "rgba(148, 148, 158, 0.14)", "#A1A1AA"

FONT_FAMILY = '"Segoe UI", "Inter", system-ui, sans-serif'

APP_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    width: 6px;
    background: transparent;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_TERTIARY};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QLineEdit {{
    background: {SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 0 12px;
    font-size: 13px;
    selection-background-color: {INFO_BG};
}}
QLineEdit:focus {{
    border-color: {TEXT_TERTIARY};
}}
QLineEdit:disabled {{
    background: {SHELL};
    color: {TEXT_TERTIARY};
}}
QLineEdit::placeholder {{
    color: {TEXT_TERTIARY};
}}
QSlider::groove:horizontal {{
    height: 3px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -6px 0;
    background: {ACCENT};
    border: none;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::add-page:horizontal {{
    background: {BORDER};
    border-radius: 2px;
}}
QMessageBox {{
    background-color: {SURFACE};
}}
QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
}}
QPushButton {{
    background: {RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton:hover {{
    background: {INFO_BG};
    border-color: {TEXT_TERTIARY};
}}
QFileDialog {{
    background-color: {SURFACE};
    color: {TEXT_PRIMARY};
}}
"""
