"""Phase 1 — design-system logic tests.

Visual correctness is verified by the rendered gallery (light + dark); these
cover the pure logic underneath: the spring curve, color parsing, and token
completeness. A headless QApplication (offscreen) backs the few Qt objects.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# --------------------------------------------------------------------------- #
# Motion — the cubic-bezier spring
# --------------------------------------------------------------------------- #
class TestSpring:
    def test_endpoints_and_monotonic(self):
        from ui.theme.motion import _cubic_bezier
        from ui.theme import tokens
        f = _cubic_bezier(*tokens.SPRING)
        assert f(0.0) == 0.0
        assert f(1.0) == 1.0
        prev = -1.0
        for i in range(0, 101):
            v = f(i / 100)
            assert v >= prev - 1e-6  # non-decreasing
            prev = v

    def test_front_loaded_ease_out(self):
        # cubic-bezier(0.32,0.72,0,1) rises fast then settles: midpoint well past 0.5.
        from ui.theme.motion import _cubic_bezier
        from ui.theme import tokens
        f = _cubic_bezier(*tokens.SPRING)
        assert f(0.5) > 0.8


# --------------------------------------------------------------------------- #
# Color parsing
# --------------------------------------------------------------------------- #
class TestColor:
    def test_hex_to_rgba(self):
        from ui.theme.manager import _hex_to_rgba
        assert _hex_to_rgba("#0A84FF", 0.4) == "rgba(10, 132, 255, 0.40)"

    def test_qcolor_parses_hex_and_rgba(self, qapp):
        from ui.components.base import qcolor
        c = qcolor("#FF3B30")
        assert (c.red(), c.green(), c.blue()) == (255, 59, 48)
        c2 = qcolor("rgba(120, 120, 128, 0.2)")
        assert (c2.red(), c2.green(), c2.blue()) == (120, 120, 128)
        assert c2.alpha() == int(0.2 * 255)


# --------------------------------------------------------------------------- #
# Token completeness
# --------------------------------------------------------------------------- #
class TestTokens:
    def test_light_and_dark_have_same_fields(self):
        from dataclasses import fields
        from ui.theme.tokens import DARK, LIGHT
        lf = {f.name for f in fields(LIGHT)}
        df = {f.name for f in fields(DARK)}
        assert lf == df
        assert LIGHT.bg_base != DARK.bg_base  # genuinely different palettes

    def test_eight_accents_each_with_light_dark(self):
        from ui.theme.tokens import ACCENTS
        assert len(ACCENTS) == 8
        for spec in ACCENTS.values():
            assert {"light", "dark", "on"} <= set(spec)

    def test_type_scale_and_geometry(self):
        from ui.theme import tokens
        assert set(tokens.TYPE_SCALE) >= {"largeTitle", "body", "caption2"}
        assert tokens.RADIUS["pill"] == 999
        assert tokens.MIN_TOUCH == 44


# --------------------------------------------------------------------------- #
# Manager resolution
# --------------------------------------------------------------------------- #
class TestManager:
    def test_mode_and_accent_resolution(self, qapp, monkeypatch):
        from ui.theme.manager import ThemeManager
        from ui.theme.tokens import DARK, LIGHT
        tm = ThemeManager()
        tm._save = lambda: None  # don't touch the real DB
        tm.set_mode("dark")
        assert tm.is_dark() and tm.palette() is DARK
        tm.set_mode("light")
        assert not tm.is_dark() and tm.palette() is LIGHT
        tm.set_accent("green")
        assert tm.accent() == "#34C759"  # green, light value

    def test_styles_bridge_maps_legacy_names(self, qapp):
        from ui import styles
        # legacy names resolve to live token strings, not AttributeError
        assert isinstance(styles.BG, str) and styles.BG.startswith("#")
        assert isinstance(styles.ACCENT, str)
        bg, fg = styles.verdict_colors(85)
        assert isinstance(bg, str) and isinstance(fg, str)
        with pytest.raises(AttributeError):
            _ = styles.NOT_A_REAL_TOKEN
