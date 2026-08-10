"""Drift design system — tokens, theme manager, motion.

Usage:
    from ui.theme import theme, tokens
    theme().apply(app)                 # install global stylesheet + font
    lbl.setFont(theme().font("headline"))
    color = theme().palette().label_secondary
    theme().themeChanged.connect(widget.restyle)   # repaint on theme change
"""
from ui.theme import motion, tokens
from ui.theme.manager import ThemeManager, manager

# Short alias — `theme()` returns the process-wide ThemeManager.
theme = manager

__all__ = ["theme", "manager", "ThemeManager", "tokens", "motion"]
