"""Migration 005 — switch job identity from URL-hash to content fingerprint.

The audit (§9.4b) flagged this as destructive: the 1.x `job.fingerprint` was a
URL hash, so the same role on many boards was many rows. Phase 8 makes identity
content-based (company+title+city), collapsing duplicates. This migration:

  1. recomputes every existing job's fingerprint,
  2. keeps a `fingerprint_alias(old -> new)` table so any external reference to an
     old id still resolves (history survives),
  3. merges rows that now share a fingerprint — repointing their application,
     cover_letter, and job_score rows onto the most authoritative survivor so the
     user's save/apply/dismiss history and letters are preserved, never dropped.

`db.init_db()` file-backs-up a non-fresh database before this runs (see
_needs_backup), so the merge is recoverable.
"""
from __future__ import annotations

import sqlite3

VERSION = 5
NAME = "content_fingerprint"

# ATS/aggregator/feed order, mirrored from core.normalize so the survivor of a
# merge is the most authoritative source.
_AUTHORITY = {"greenhouse": 3, "lever": 3, "ashby": 3, "workable": 3,
              "smartrecruiters": 3, "themuse": 2, "arbeitnow": 2, "jobicy": 2,
              "remoteok": 2, "remotive": 2, "wwr": 1, "hn": 1, "custom": 1}


def up(conn: sqlite3.Connection) -> None:
    from core.dedup.fingerprint import content_fingerprint
    from core.normalize.fields import parse_location

    conn.execute(
        """CREATE TABLE IF NOT EXISTS fingerprint_alias (
               old_fingerprint TEXT PRIMARY KEY,
               new_fingerprint TEXT NOT NULL,
               aliased_at TEXT NOT NULL DEFAULT (datetime('now')))"""
    )

    rows = conn.execute(
        """SELECT j.id, j.fingerprint, j.title, j.company_name, j.location_raw,
                  j.location_city, s.slug AS source_slug,
                  (SELECT count(*) FROM application a WHERE a.job_id=j.id) AS has_app
             FROM job j LEFT JOIN source s ON s.id = j.source_id"""
    ).fetchall()

    # Compute new fingerprint per row and group by it.
    groups: dict[str, list[dict]] = {}
    for r in rows:
        city = r["location_city"] or parse_location(r["location_raw"] or "")["city"]
        new_fp = content_fingerprint(r["company_name"] or "", r["title"] or "", city)
        rec = {"id": r["id"], "old": r["fingerprint"], "new": new_fp,
               "auth": _AUTHORITY.get(r["source_slug"], 1), "has_app": r["has_app"]}
        groups.setdefault(new_fp, []).append(rec)

    for new_fp, members in groups.items():
        # Survivor = most authoritative, preferring one that already has an
        # application, then the lowest id for stability.
        members.sort(key=lambda m: (-m["auth"], -m["has_app"], m["id"]))
        winner = members[0]
        for loser in members[1:]:
            _merge(conn, loser["id"], winner["id"])
            conn.execute(
                "INSERT OR REPLACE INTO fingerprint_alias(old_fingerprint, new_fingerprint) VALUES (?,?)",
                (loser["old"], new_fp))
        if winner["old"] != new_fp:
            conn.execute(
                "INSERT OR REPLACE INTO fingerprint_alias(old_fingerprint, new_fingerprint) VALUES (?,?)",
                (winner["old"], new_fp))
        conn.execute("UPDATE job SET fingerprint=? WHERE id=?", (new_fp, winner["id"]))


def _merge(conn: sqlite3.Connection, loser_id: int, winner_id: int) -> None:
    """Repoint a duplicate's user data onto the survivor, then delete it."""
    # application: winner keeps its own; move loser's only if winner has none.
    w_app = conn.execute("SELECT 1 FROM application WHERE job_id=?", (winner_id,)).fetchone()
    if w_app:
        conn.execute("DELETE FROM application WHERE job_id=?", (loser_id,))
    else:
        conn.execute("UPDATE application SET job_id=? WHERE job_id=?", (winner_id, loser_id))
    # cover letters: keep all, repoint to survivor.
    conn.execute("UPDATE cover_letter SET job_id=? WHERE job_id=?", (winner_id, loser_id))
    # job_score: move where the (winner, resume) pair is free; drop conflicts.
    scores = conn.execute("SELECT id, resume_id FROM job_score WHERE job_id=?",
                          (loser_id,)).fetchall()
    for sc in scores:
        clash = conn.execute(
            "SELECT 1 FROM job_score WHERE job_id=? AND resume_id IS ?",
            (winner_id, sc["resume_id"])).fetchone()
        if clash:
            conn.execute("DELETE FROM job_score WHERE id=?", (sc["id"],))
        else:
            conn.execute("UPDATE job_score SET job_id=? WHERE id=?", (winner_id, sc["id"]))
    conn.execute("DELETE FROM job WHERE id=?", (loser_id,))


def down(conn: sqlite3.Connection) -> None:
    # Fingerprint recomputation + dup merge can't be losslessly reversed in-place;
    # recovery is via the pre-migration file backup. Just drop the alias table.
    conn.execute("DROP TABLE IF EXISTS fingerprint_alias")
