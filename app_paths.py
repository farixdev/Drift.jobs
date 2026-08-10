"""Path resolution that works both in a dev checkout and a frozen PyInstaller exe.

- `resource_path()` finds read-only bundled assets (icon, fonts).
- `user_data_dir()` is a writable per-user location for the DB and .env when the
  app is frozen (the bundle itself is read-only / ephemeral). In a dev checkout
  nothing changes — callers keep their existing in-repo paths.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(rel: str) -> str:
    """Absolute path to a bundled read-only asset (e.g. 'assets/logo/drift.ico')."""
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base = _REPO_ROOT
    return str(base / rel)


def user_data_dir() -> Path:
    """Writable per-user data directory. Only diverges from the repo when frozen."""
    if is_frozen():
        root = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        d = Path(root) / "Drift"
    else:
        d = _REPO_ROOT
    d.mkdir(parents=True, exist_ok=True)
    return d
