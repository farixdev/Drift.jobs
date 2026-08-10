"""Resume persistence (Phase 4): resumes + tailored versions.

Backs the `resume` and `resume_version` tables (Phase 2). Multiple resumes per
profile, one default; parsed corrections persist; tailored variants never
overwrite the base (they land in resume_version)."""
from __future__ import annotations

import json
from contextlib import closing

from core.resume.schema import ParsedResume
from db.connection import connect


def save_resume(label: str, raw_text: str, parsed: ParsedResume, *,
                source_path: str = "", is_default: bool = False,
                resume_id: int | None = None) -> int:
    payload = json.dumps(parsed.to_dict())
    with closing(connect()) as conn, conn:
        if resume_id:
            conn.execute(
                "UPDATE resume SET label=?, raw_text=?, parsed_json=?, source_path=?, "
                "updated_at=datetime('now') WHERE id=?",
                (label, raw_text, payload, source_path, resume_id))
            rid = resume_id
        else:
            cur = conn.execute(
                "INSERT INTO resume (label, raw_text, parsed_json, source_path, is_default) "
                "VALUES (?, ?, ?, ?, ?)",
                (label, raw_text, payload, source_path, 1 if is_default else 0))
            rid = cur.lastrowid
        if is_default:
            conn.execute("UPDATE resume SET is_default=CASE WHEN id=? THEN 1 ELSE 0 END", (rid,))
        elif conn.execute("SELECT count(*) c FROM resume WHERE is_default=1").fetchone()["c"] == 0:
            conn.execute("UPDATE resume SET is_default=1 WHERE id=?", (rid,))
    return rid


def update_parsed(resume_id: int, parsed: ParsedResume) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE resume SET parsed_json=?, updated_at=datetime('now') WHERE id=?",
                     (json.dumps(parsed.to_dict()), resume_id))


def list_resumes() -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT id, label, is_default, created_at FROM resume ORDER BY is_default DESC, created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_resume(resume_id: int) -> dict | None:
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT id, label, raw_text, parsed_json, is_default FROM resume WHERE id=?",
            (resume_id,)).fetchone()
    if not row:
        return None
    try:
        parsed = ParsedResume.from_dict(json.loads(row["parsed_json"]))
    except (ValueError, TypeError):
        parsed = ParsedResume()
    return {"id": row["id"], "label": row["label"], "raw_text": row["raw_text"],
            "parsed": parsed, "is_default": bool(row["is_default"])}


def default_resume() -> dict | None:
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT id FROM resume ORDER BY is_default DESC, created_at DESC LIMIT 1").fetchone()
    return get_resume(row["id"]) if row else None


def set_default(resume_id: int) -> None:
    with closing(connect()) as conn, conn:
        # Guard existence — a bad id must not clear the default from every row.
        if conn.execute("SELECT 1 FROM resume WHERE id=?", (resume_id,)).fetchone():
            conn.execute("UPDATE resume SET is_default=CASE WHEN id=? THEN 1 ELSE 0 END",
                         (resume_id,))


def delete_resume(resume_id: int) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM resume WHERE id=?", (resume_id,))
        # If we deleted the default, promote the most recent survivor so there is
        # always exactly one default while any résumé remains.
        if not conn.execute("SELECT 1 FROM resume WHERE is_default=1").fetchone():
            row = conn.execute("SELECT id FROM resume ORDER BY created_at DESC LIMIT 1").fetchone()
            if row:
                conn.execute("UPDATE resume SET is_default=1 WHERE id=?", (row["id"],))


def save_version(resume_id: int, content: ParsedResume, *, tailored_for_job_id: int | None = None,
                 label: str = "") -> int:
    with closing(connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO resume_version (resume_id, tailored_for_job_id, label, content_json) "
            "VALUES (?, ?, ?, ?)",
            (resume_id, tailored_for_job_id, label, json.dumps(content.to_dict())))
        return cur.lastrowid


def list_versions(resume_id: int) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT id, label, tailored_for_job_id, generated_at FROM resume_version "
            "WHERE resume_id=? ORDER BY generated_at DESC", (resume_id,)).fetchall()
    return [dict(r) for r in rows]
