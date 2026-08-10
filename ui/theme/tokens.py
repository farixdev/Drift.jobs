"""Design tokens — the single source of truth for every color, size, and timing.

Modeled on the macOS Sonoma / iOS 17 semantic system: layered backgrounds,
four label levels, translucent fills, opaque + non-opaque separators, and the
eight system accent colors. Light and dark are true, hand-tuned pairs — dark is
a real near-black (#1C1C1E), not an inverted gray.

Nothing in the app hardcodes a hex outside this file (Phase 1 rule). Widgets read
the resolved palette via `ui.theme.manager` and never these raw values directly.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    name: str  # "light" | "dark"

    # Layered backgrounds
    bg_base: str
    bg_elevated: str
    bg_overlay: str
    bg_sidebar: str          # translucent (material fallback)
    bg_sidebar_solid: str    # opaque fallback where blur is unsupported

    # Labels (text)
    label_primary: str
    label_secondary: str
    label_tertiary: str
    label_quaternary: str

    # Fills (translucent grays: chips, toggles, inactive states)
    fill_primary: str
    fill_secondary: str
    fill_tertiary: str
    fill_quaternary: str

    # Separators
    separator_opaque: str
    separator_nonopaque: str

    # Semantic (foreground + subtle background)
    success: str
    success_bg: str
    warning: str
    warning_bg: str
    danger: str
    danger_bg: str
    info: str
    info_bg: str

    # Control chrome
    control_bg: str          # inputs/select background
    control_border: str
    field_focus_ring: str    # derived from accent at runtime; placeholder here

    # Shadow (used by QGraphicsDropShadowEffect, not QSS)
    shadow_rgba: tuple       # (r, g, b, a-int-0-255)
    shadow_blur: int
    shadow_y: int


LIGHT = Palette(
    name="light",
    bg_base="#F5F5F7",
    bg_elevated="#FFFFFF",
    bg_overlay="#FFFFFF",
    bg_sidebar="rgba(246, 246, 248, 0.72)",
    bg_sidebar_solid="#ECECEF",
    label_primary="#1D1D1F",
    label_secondary="rgba(60, 60, 67, 0.60)",
    label_tertiary="rgba(60, 60, 67, 0.30)",
    label_quaternary="rgba(60, 60, 67, 0.18)",
    fill_primary="rgba(120, 120, 128, 0.20)",
    fill_secondary="rgba(120, 120, 128, 0.16)",
    fill_tertiary="rgba(120, 120, 128, 0.12)",
    fill_quaternary="rgba(120, 120, 128, 0.08)",
    separator_opaque="#C6C6C8",
    separator_nonopaque="rgba(60, 60, 67, 0.29)",
    success="#248A3D",
    success_bg="rgba(52, 199, 89, 0.14)",
    warning="#C05600",
    warning_bg="rgba(255, 149, 0, 0.16)",
    danger="#D70015",
    danger_bg="rgba(255, 59, 48, 0.12)",
    info="#0071E3",
    info_bg="rgba(0, 122, 255, 0.12)",
    control_bg="#FFFFFF",
    control_border="rgba(60, 60, 67, 0.22)",
    field_focus_ring="#007AFF",
    shadow_rgba=(0, 0, 0, 28),
    shadow_blur=24,
    shadow_y=6,
)

DARK = Palette(
    name="dark",
    bg_base="#1C1C1E",
    bg_elevated="#2C2C2E",
    bg_overlay="#2C2C2E",
    bg_sidebar="rgba(30, 30, 32, 0.72)",
    bg_sidebar_solid="#242426",
    label_primary="#F5F5F7",
    label_secondary="rgba(235, 235, 245, 0.60)",
    label_tertiary="rgba(235, 235, 245, 0.30)",
    label_quaternary="rgba(235, 235, 245, 0.16)",
    fill_primary="rgba(120, 120, 128, 0.36)",
    fill_secondary="rgba(120, 120, 128, 0.32)",
    fill_tertiary="rgba(120, 120, 128, 0.24)",
    fill_quaternary="rgba(120, 120, 128, 0.18)",
    separator_opaque="#38383A",
    separator_nonopaque="rgba(84, 84, 88, 0.60)",
    success="#30D158",
    success_bg="rgba(48, 209, 88, 0.18)",
    warning="#FF9F0A",
    warning_bg="rgba(255, 159, 10, 0.20)",
    danger="#FF453A",
    danger_bg="rgba(255, 69, 58, 0.18)",
    info="#0A84FF",
    info_bg="rgba(10, 132, 255, 0.18)",
    control_bg="rgba(120, 120, 128, 0.24)",
    control_border="rgba(120, 120, 128, 0.40)",
    field_focus_ring="#0A84FF",
    shadow_rgba=(0, 0, 0, 110),
    shadow_blur=28,
    shadow_y=8,
)


# The eight system accent colors, each with a light/dark value + an "on" text
# color for filled controls. Key is the id stored in Settings.
ACCENTS: dict[str, dict[str, str]] = {
    "blue":   {"light": "#007AFF", "dark": "#0A84FF", "on": "#FFFFFF"},
    "purple": {"light": "#AF52DE", "dark": "#BF5AF2", "on": "#FFFFFF"},
    "pink":   {"light": "#FF2D55", "dark": "#FF375F", "on": "#FFFFFF"},
    "red":    {"light": "#FF3B30", "dark": "#FF453A", "on": "#FFFFFF"},
    "orange": {"light": "#FF9500", "dark": "#FF9F0A", "on": "#FFFFFF"},
    "yellow": {"light": "#FFCC00", "dark": "#FFD60A", "on": "#1D1D1F"},
    "green":  {"light": "#34C759", "dark": "#30D158", "on": "#FFFFFF"},
    "teal":   {"light": "#5AC8FA", "dark": "#64D2FF", "on": "#1D1D1F"},
}
DEFAULT_ACCENT = "blue"


# Typography — semantic roles: (size_px, line_height_px, weight, letter_spacing_em).
# Letter-spacing tightens as size grows (-0.022em at largeTitle → 0 at body).
# Weights are QFont weights (400 normal, 500 medium, 600 semibold, 700 bold).
TYPE_SCALE: dict[str, tuple] = {
    "largeTitle": (34, 41, 700, -0.022),
    "title1":     (28, 34, 700, -0.020),
    "title2":     (22, 28, 700, -0.016),
    "title3":     (20, 25, 600, -0.012),
    "headline":   (17, 22, 600, -0.006),
    "body":       (17, 22, 400,  0.0),
    "callout":    (16, 21, 400, -0.003),
    "subhead":    (15, 20, 400, -0.002),
    "footnote":   (13, 18, 400,  0.0),
    "caption1":   (12, 16, 400,  0.0),
    "caption2":   (11, 13, 500,  0.006),
}
FONT_STACK = ['-apple-system', 'BlinkMacSystemFont', 'SF Pro Text',
              'SF Pro Display', 'Inter', 'Segoe UI', 'system-ui', 'sans-serif']

# 8pt spacing grid.
SPACE = {"xs": 4, "sm": 8, "md": 12, "base": 16, "lg": 20, "xl": 24,
         "2xl": 32, "3xl": 40, "4xl": 48, "5xl": 64}

# Corner radii.
RADIUS = {"chip": 4, "control": 8, "card": 12, "sheet": 16, "modal": 20, "pill": 999}

# Control heights.
CONTROL_H = {"sm": 28, "md": 32, "lg": 40}
MIN_TOUCH = 44

# Motion — spring cubic-bezier + durations (ms). Nothing over 500ms.
SPRING = (0.32, 0.72, 0.0, 1.0)
DURATION = {"micro": 150, "standard": 250, "large": 400}
PRESS_SCALE = 0.97
