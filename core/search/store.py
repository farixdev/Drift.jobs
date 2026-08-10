"""Saved searches — CRUD on the `search` table.

A saved search is a named SearchCriteria (stored as query_json) plus an optional
schedule. Supports duplicate-and-edit and marking the last run time.
"""
from __future__ import annotations

import json
from contextlib import closing

from core.sources.spec import SearchCriteria
from db.connection import connect


def save_search(name: str, criteria: SearchCriteria, *, search_id: int | None = None,
                schedule_cron: str | None = None) -> int:
    payload = json.dumps(criteria.to_dict())
    with closing(connect()) as conn, conn:
        if search_id:
            conn.execute(
                "UPDATE search SET name=?, query_json=?, schedule_cron=? WHERE id=?",
                (name, payload, schedule_cron, search_id))
            return search_id
        cur = conn.execute(
            "INSERT INTO search (name, query_json, schedule_cron) VALUES (?, ?, ?)",
            (name, payload, schedule_cron))
        return cur.lastrowid


def list_searches() -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT id, name, schedule_cron, is_active, last_run_at, created_at "
            "FROM search ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_search(search_id: int) -> tuple[str, SearchCriteria] | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT name, query_json FROM search WHERE id=?",
                           (search_id,)).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["query_json"])
    except (ValueError, TypeError):
        data = {}
    return row["name"], SearchCriteria.from_dict(data)


def duplicate_search(search_id: int) -> int | None:
    got = get_search(search_id)
    if not got:
        return None
    name, criteria = got
    return save_search(f"{name} (copy)", criteria)


def delete_search(search_id: int) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM search WHERE id=?", (search_id,))


def mark_run(search_id: int) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE search SET last_run_at=datetime('now') WHERE id=?",
                     (search_id,))


def set_active(search_id: int, active: bool) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE search SET is_active=? WHERE id=?",
                     (1 if active else 0, search_id))
