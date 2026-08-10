"""Motion — the system spring, durations, and reduced-motion handling.

The standard curve is cubic-bezier(0.32, 0.72, 0, 1). Qt 5's built-in easing
enums don't include it, so we evaluate the CSS cubic-bezier exactly via
`QEasingCurve.setCustomType`. Every animation goes through `animate()`, which
collapses to an instant/opacity-only change when the OS asks for reduced motion.
"""
from __future__ import annotations

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, Qt

from ui.theme import tokens


def _cubic_bezier(p1x: float, p1y: float, p2x: float, p2y: float):
    """Return f(x)->y for a CSS cubic-bezier with endpoints (0,0),(1,1)."""
    def _bez(t, a, b):  # coordinate on one axis at parameter t
        return 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t ** 2 * b + t ** 3

    def _solve_t_for_x(x):
        lo, hi, t = 0.0, 1.0, x
        for _ in range(24):  # bisection is plenty for UI timing
            xt = _bez(t, p1x, p2x)
            if abs(xt - x) < 1e-4:
                return t
            if xt < x:
                lo = t
            else:
                hi = t
            t = (lo + hi) / 2
        return t

    def f(x: float) -> float:
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        return _bez(_solve_t_for_x(x), p1y, p2y)

    return f


def spring_curve() -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Custom)
    curve.setCustomType(_cubic_bezier(*tokens.SPRING))
    return curve


def reduced_motion() -> bool:
    """True when the OS requests reduced motion (Windows: 'show animations' off)."""
    try:
        import ctypes
        SPI_GETCLIENTAREAANIMATION = 0x1042
        val = ctypes.c_int()
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(val), 0)
        if ok:
            return not bool(val.value)
    except Exception:
        pass
    return False


def animate(target, prop: bytes, start, end, *, duration: int | None = None,
            kind: str = "standard", on_finished=None) -> QPropertyAnimation | None:
    """Animate `prop` on `target` with the system spring. Under reduced motion the
    value is set instantly (opacity-only surfaces still read fine)."""
    dur = duration if duration is not None else tokens.DURATION.get(kind, 250)
    if reduced_motion():
        target.setProperty(prop.decode() if isinstance(prop, bytes) else prop, end)
        if on_finished:
            on_finished()
        return None
    anim = QPropertyAnimation(target, prop)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setDuration(dur)
    anim.setEasingCurve(spring_curve())
    if on_finished:
        anim.finished.connect(on_finished)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim
