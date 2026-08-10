"""Pytest bootstrap: make the repo root importable without installing the package.

The app is run as `python main.py` from the repo root, so modules import as
top-level (`from models import Job`, `from core import ...`). Tests mirror that.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
