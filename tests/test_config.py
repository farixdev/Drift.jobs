"""Regression tests for config.load_env robustness.

A missing/unreadable .env or a broken python-dotenv install must never stop the
app from starting — load_env degrades to a manual parse and, failing that, a
clean no-op.
"""
from __future__ import annotations

import os

import pytest

from core import config


def test_missing_env_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "nope.env")
    config.load_env()  # must not raise


def test_manual_parse_when_dotenv_broken(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('FOO_KEY=bar123\n# comment\nQUOTED="baz"\n', encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env)
    monkeypatch.delenv("FOO_KEY", raising=False)

    # Simulate a broken/partial python-dotenv: importing raises.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "dotenv" or name.startswith("dotenv."):
            raise ModuleNotFoundError("No module named 'dotenv.parser'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    config.load_env()          # falls back to the manual parser, no crash
    assert os.environ.get("FOO_KEY") == "bar123"
    assert os.environ.get("QUOTED") == "baz"


def test_unreadable_env_is_noop(tmp_path, monkeypatch):
    # ENV_FILE points at a directory → is_file() False → clean return.
    monkeypatch.setattr(config, "ENV_FILE", tmp_path)
    config.load_env()
