"""Application tracker (Phase 9): the Kanban pipeline + funnel metrics + export.

Backs the `application` table (Phase 2). Applications are keyed by job — the
results screen creates them (saved/applied/dismissed); the tracker fleshes out the
full lifecycle: pipeline stages, notes, next actions, contacts, timeline, and
conversion metrics.
"""
from __future__ import annotations

import csv
import json
from contextlib import closing
from datetime import datetime, timezone

from db.connection import connect

# Kanban columns, in order. 'dismissed' is intentionally NOT a column (it's a
# hide flag, not a pipeline stage).
STAGES = ["saved", "applied", "screening", "interview", "offer", "rejected", "withdrawn"]
STAGE_LABELS = {"saved": "Saved", "applied": "Applied", "screening": "Screening",
                "interview": "Interview", "offer": "Offer", "rejected": "Rejected",
                "withdrawn": "Withdrawn"}
# Stages that count as "the employer responded".
_RESPONDED = {"screening", "interview", "offer", "rejected"}


def _job_id(conn, fingerprint: str) -> int | None:
    row = conn.execute("SELECT id FROM job WHERE fingerprint=?", (fingerprint,)).fetchone()
    return row["id"] if row else None


def board() -> dict[str, list[dict]]:
    """Applications grouped by stage, each joined with its job for display."""
    out: dict[str, list[dict]] = {s: [] for s in STAGES}
    with closing(connect()) as conn:
        rows = conn.execute(
            """SELECT a.id AS app_id, a.status, a.applied_at, a.notes, a.next_action,
                      a.next_action_due, a.contact_json, a.updated_at,
                      j.fingerprint, j.title, j.company_name, j.apply_url,
                      s.slug AS source
                 FROM application a
                 JOIN job j ON j.id = a.job_id
                 LEFT JOIN source s ON s.id = j.source_id
                WHERE a.status IN ({})""".format(",".join("?" * len(STAGES))),
            STAGES).fetchall()
    for r in rows:
        d = dict(r)
        out.setdefault(d["status"], []).append(d)
    return out


def set_stage(fingerprint: str, stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    with closing(connect()) as conn, conn:
        jid = _job_id(conn, fingerprint)
        if jid is None:
            return
        applied_at = datetime.now(timezone.utc).isoformat(timespec="seconds") \
            if stage == "applied" else None
        conn.execute(
            """INSERT INTO application (job_id, status, applied_at)
               VALUES (?, ?, ?)
               ON CONFLICT(job_id) DO UPDATE SET
                   status=excluded.status,
                   applied_at=COALESCE(application.applied_at, excluded.applied_at),
                   updated_at=datetime('now')""",
            (jid, stage, applied_at))


def update(fingerprint: str, *, notes: str | None = None, next_action: str | None = None,
           next_action_due: str | None = None, contact: dict | None = None,
           resume_version_id: int | None = None) -> None:
    sets, vals = [], []
    if notes is not None:
        sets.append("notes=?"); vals.append(notes)
    if next_action is not None:
        sets.append("next_action=?"); vals.append(next_action)
    if next_action_due is not None:
        sets.append("next_action_due=?"); vals.append(next_action_due)
    if contact is not None:
        sets.append("contact_json=?"); vals.append(json.dumps(contact))
    if resume_version_id is not None:
        sets.append("resume_version_id=?"); vals.append(resume_version_id)
    if not sets:
        return
    sets.append("updated_at=datetime('now')")
    with closing(connect()) as conn, conn:
        jid = _job_id(conn, fingerprint)
        if jid is None:
            return
        conn.execute(f"UPDATE application SET {', '.join(sets)} WHERE job_id=?", (*vals, jid))


def upcoming_actions(limit: int = 20) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            """SELECT j.title, j.company_name, a.next_action, a.next_action_due, j.fingerprint
                 FROM application a JOIN job j ON j.id=a.job_id
                WHERE a.next_action != '' AND a.next_action_due IS NOT NULL
                ORDER BY a.next_action_due ASC LIMIT ?""", (limit,)).fetchall()
    return [dict(r) for r in rows]


def metrics() -> dict:
    """Funnel + conversion metrics for the dashboard/tracker."""
    with closing(connect()) as conn:
        rows = conn.execute(
            """SELECT a.status, a.applied_at, a.updated_at, s.slug AS source
                 FROM application a JOIN job j ON j.id=a.job_id
                 LEFT JOIN source s ON s.id=j.source_id""").fetchall()
    total = len(rows)
    by_stage = {s: 0 for s in STAGES}
    by_source: dict[str, dict] = {}
    applied = responded = interviewed = offered = 0
    response_days: list[float] = []
    for r in rows:
        by_stage[r["status"]] = by_stage.get(r["status"], 0) + 1
        src = r["source"] or "unknown"
        by_source.setdefault(src, {"applied": 0, "responded": 0})
        if r["status"] != "saved":
            applied += 1
            by_source[src]["applied"] += 1
        if r["status"] in _RESPONDED:
            responded += 1
            by_source[src]["responded"] += 1
            if r["applied_at"] and r["updated_at"]:
                try:
                    d = (datetime.fromisoformat(r["updated_at"].replace(" ", "T"))
                         - datetime.fromisoformat(r["applied_at"])).days
                    if d >= 0:
                        response_days.append(d)
                except ValueError:
                    pass
        if r["status"] in ("interview", "offer"):
            interviewed += 1
        if r["status"] == "offer":
            offered += 1

    def pct(n, d):
        return round(100 * n / d) if d else 0
    return {
        "total": total,
        "by_stage": by_stage,
        "applied": applied,
        "response_rate": pct(responded, applied),
        "interview_rate": pct(interviewed, applied),
        "offer_rate": pct(offered, applied),
        "avg_days_to_response": round(sum(response_days) / len(response_days), 1)
        if response_days else None,
        "by_source": {s: {**v, "response_rate": pct(v["responded"], v["applied"])}
                      for s, v in by_source.items()},
    }


def export(path: str, fmt: str = "csv") -> str:
    from pathlib import Path
    data = board()
    flat = [row for stage in STAGES for row in data.get(stage, [])]
    p = Path(path).with_suffix(f".{fmt}")
    if fmt == "json":
        p.write_text(json.dumps({"applications": flat, "metrics": metrics()},
                                indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        cols = ["status", "title", "company_name", "source", "applied_at",
                "next_action", "next_action_due", "notes", "apply_url"]
        with p.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for row in flat:
                w.writerow(row)
    return str(p.resolve())
