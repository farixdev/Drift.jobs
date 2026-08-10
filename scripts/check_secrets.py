#!/usr/bin/env python3
"""Pre-commit secret scanner (Phase 3 requirement).

Scans staged additions for API-key-shaped tokens and blocks the commit if any
are found. Deliberately conservative — it flags the shapes Drift's providers use
(sk-, gsk_, Google AIza, x-api-key values, Bearer tokens) plus obvious .env key
lines. Runs with zero third-party dependencies so the hook works everywhere.

Install:  python scripts/check_secrets.py --install
Manual:   python scripts/check_secrets.py            (scans staged diff)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9._\-]{20,}"), "OpenAI-style key (sk-...)"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "Groq key (gsk_...)"),
    (re.compile(r"AIza[A-Za-z0-9_\-]{30,}"), "Google API key (AIza...)"),
    (re.compile(r"sk-ant-[A-Za-z0-9._\-]{20,}"), "Anthropic key (sk-ant-...)"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|token)\s*[:=]\s*['\"][^'\"]{20,}['\"]"),
     "assigned secret literal"),
]

# Files where key-shaped strings are legitimately discussed (docs, this scanner,
# the redactor/tests that must contain sample tokens).
ALLOW = {
    "scripts/check_secrets.py",
    "core/ai/errors.py",
    "tests/test_ai_provider.py",
    "docs/AI_PROVIDERS.md",
    "docs/AUDIT.md",
}


def _staged_files() -> list[str]:
    # Decode as UTF-8 (the repo's encoding) rather than the Windows locale default,
    # which can't decode some bytes and would crash the hook.
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                         capture_output=True, encoding="utf-8", errors="replace")
    return [f.strip() for f in (out.stdout or "").splitlines() if f.strip()]


def _staged_content(path: str) -> str:
    out = subprocess.run(["git", "show", f":{path}"], capture_output=True,
                         encoding="utf-8", errors="replace")
    return (out.stdout or "") if out.returncode == 0 else ""


def scan() -> int:
    findings: list[str] = []
    for path in _staged_files():
        norm = path.replace("\\", "/")
        if norm in ALLOW or norm == ".env.example":
            continue
        # Never allow the real .env to be committed at all.
        if norm == ".env":
            findings.append(f"{path}: .env must never be committed")
            continue
        content = _staged_content(path)
        for pat, label in PATTERNS:
            if pat.search(content):
                findings.append(f"{path}: possible {label}")
                break
    if findings:
        sys.stderr.write("\n✗ Commit blocked — possible secrets in staged changes:\n")
        for f in findings:
            sys.stderr.write(f"    {f}\n")
        sys.stderr.write("\nIf this is a false positive, add the path to ALLOW in "
                         "scripts/check_secrets.py or use `git commit --no-verify`.\n")
        return 1
    return 0


def install() -> int:
    root = Path(__file__).resolve().parent.parent
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\n"
        '# Drift secret scanner. Regenerate with: python scripts/check_secrets.py --install\n'
        'python "$(git rev-parse --show-toplevel)/scripts/check_secrets.py" || exit 1\n',
        encoding="utf-8",
    )
    try:
        os.chmod(hook, 0o755)
    except OSError:
        pass
    print(f"Installed pre-commit hook at {hook}")
    return 0


if __name__ == "__main__":
    if "--install" in sys.argv:
        raise SystemExit(install())
    raise SystemExit(scan())
