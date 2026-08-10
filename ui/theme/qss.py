"""Global Qt Style Sheet builder.

Generates one application-level stylesheet from the active palette + accent.
Covers the base widgets (scrollbars, tooltips, menus, generic controls) and the
`.role`-style object properties the component library sets via `setProperty`.
Custom-painted components (toggle, segmented control, spinner, …) read tokens
directly and don't rely on this sheet.
"""
from __future__ import annotations

from ui.theme import tokens
from ui.theme.tokens import Palette


def build(p: Palette, accent: str, accent_on: str, focus_ring: str) -> str:
    R = tokens.RADIUS
    return f"""
* {{
    outline: none;
}}
QWidget {{
    color: {p.label_primary};
    background: transparent;
    font-size: 17px;
}}
QMainWindow, QDialog {{
    background: {p.bg_base};
}}
QToolTip {{
    background: {p.bg_overlay};
    color: {p.label_primary};
    border: 1px solid {p.separator_nonopaque};
    border-radius: {R['control']}px;
    padding: 6px 10px;
    font-size: 13px;
}}

/* Scrollbars — thin, translucent, macOS-like */
QScrollArea, QAbstractScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {p.fill_secondary}; border-radius: 5px; min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.fill_primary}; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {p.fill_secondary}; border-radius: 5px; min-width: 32px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Menus / context menus */
QMenu {{
    background: {p.bg_overlay};
    border: 1px solid {p.separator_nonopaque};
    border-radius: {R['card']}px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px; border-radius: {R['control']}px; font-size: 15px;
}}
QMenu::item:selected {{ background: {accent}; color: {accent_on}; }}
QMenu::separator {{ height: 1px; background: {p.separator_nonopaque}; margin: 6px 8px; }}

/* Generic line edits (component TextField refines these) */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {p.control_bg};
    color: {p.label_primary};
    border: 1px solid {p.control_border};
    border-radius: {R['control']}px;
    padding: 0 12px;
    selection-background-color: {accent};
    selection-color: {accent_on};
    font-size: 15px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {accent};
}}
QLineEdit:disabled {{ color: {p.label_tertiary}; }}

/* Generic combo box */
QComboBox {{
    background: {p.control_bg};
    border: 1px solid {p.control_border};
    border-radius: {R['control']}px;
    padding: 0 12px; min-height: 30px; font-size: 15px;
}}
QComboBox:focus {{ border: 1px solid {accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {p.bg_overlay};
    border: 1px solid {p.separator_nonopaque};
    border-radius: {R['control']}px;
    selection-background-color: {accent};
    selection-color: {accent_on};
    padding: 4px;
}}

/* Generic spin box */
QSpinBox, QDoubleSpinBox {{
    background: {p.control_bg};
    border: 1px solid {p.control_border};
    border-radius: {R['control']}px;
    padding: 0 8px; min-height: 30px; font-size: 15px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {accent}; }}

/* Sliders */
QSlider::groove:horizontal {{ height: 4px; background: {p.fill_tertiary}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::add-page:horizontal {{ background: {p.fill_tertiary}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 20px; height: 20px; margin: -8px 0; border-radius: 10px;
    background: #FFFFFF; border: 0.5px solid {p.separator_opaque};
}}

/* Message boxes */
QMessageBox {{ background: {p.bg_elevated}; }}
QMessageBox QLabel {{ color: {p.label_primary}; }}
"""
