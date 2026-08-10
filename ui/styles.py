"""Compatibility bridge — maps the 1.x style constants onto the new design tokens.

The legacy screens (setup / scan / results) reference `styles.BG`, `styles.ACCENT`,
etc. inline. Rather than rewrite those screens now (they are replaced wholesale by
the Phase 10 dashboard/jobs views), this module resolves each old name to the
current theme's palette at access time via PEP 562 `__getattr__`. Existing screens
therefore adopt the macOS token system's colors immediately; full theme-reactivity
and the component library arrive when those screens are rebuilt in Phase 10.

New code should import from `ui.theme` and `ui.components`, not from here.
"""
from __future__ import annotations

from ui.theme import theme as _theme
from ui.theme import tokens as _tokens


def _fontstack() -> str:
    return ", ".join(f'"{f}"' if " " in f else f for f in _tokens.FONT_STACK)


def __getattr__(name: str):
    t = _theme()
    p = t.palette()
    tinted16 = t.focus_ring().replace("0.40", "0.16")
    mapping = {
        "BG": p.bg_base,
        "SHELL": p.bg_sidebar_solid,
        "SURFACE": p.bg_elevated,
        "RAISED": p.bg_elevated,
        "BORDER": p.separator_opaque,
        "BORDER_SUBTLE": p.separator_nonopaque,
        "TEXT_PRIMARY": p.label_primary,
        "TEXT_SECONDARY": p.label_secondary,
        "TEXT_TERTIARY": p.label_tertiary,
        "ACCENT": t.accent(),
        "ACCENT_TEXT": t.accent_on(),
        "ACCENT_HOVER": t.accent(),
        "SUCCESS": p.success,
        "SUCCESS_BG": p.success_bg,
        "WARNING": p.warning,
        "MATCH_BG": p.success_bg,
        "MATCH_TEXT": p.success,
        "LOC_BG": p.fill_tertiary,
        "LOC_TEXT": p.label_secondary,
        "DOT_PENDING": p.fill_secondary,
        "DOT_ACTIVE": t.accent(),
        "DOT_DONE": p.label_tertiary,
        "LOG_BG": p.bg_base,
        "INFO_BORDER": p.separator_nonopaque,
        "INFO_BG": p.fill_tertiary,
        "GAP_BG": p.warning_bg,
        "GAP_TEXT": p.warning,
        "NEW_BG": p.info_bg,
        "NEW_TEXT": p.info,
        "DANGER": p.danger,
        "DANGER_BG": p.danger_bg,
        "STAR": p.warning,
        "RECOMMENDED_TEXT": p.success,
        "FONT_FAMILY": _fontstack(),
        "APP_STYLESHEET": t.stylesheet(),
    }
    if name in mapping:
        return mapping[name]
    raise AttributeError(f"module 'ui.styles' has no attribute {name!r}")


def verdict_colors(score: int) -> tuple[str, str]:
    """(background, text) for a score's verdict pill, from the semantic palette."""
    t = _theme()
    p = t.palette()
    if score >= 80:
        return p.success_bg, p.success
    if score >= 60:
        return t.focus_ring().replace("0.40", "0.16"), t.accent()
    if score >= 40:
        return p.warning_bg, p.warning
    return p.fill_tertiary, p.label_secondary
