"""Phase 9 — application tracker: board, stage moves, metrics, export."""
from __future__ import annotations

from contextlib import closing

import pytest

import db
from core import tracker


@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    from db import connection
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(db, "DB_PATH", p, raising=False)
    db.init_db()
    return p


def _seed_job(fp, title="Engineer", company="Acme", source="greenhouse"):
    with closing(db.connection.connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO source(slug, display_name) VALUES (?, ?)",
                     (source, source.title()))
        sid = conn.execute("SELECT id FROM source WHERE slug=?", (source,)).fetchone()["id"]
        conn.execute("INSERT INTO job(fingerprint, title, company_name, source_id) VALUES (?,?,?,?)",
                     (fp, title, company, sid))


class TestBoard:
    def test_set_stage_and_board(self, dbpath):
        _seed_job("fp1")
        tracker.set_stage("fp1", "applied")
        b = tracker.board()
        assert len(b["applied"]) == 1 and b["applied"][0]["title"] == "Engineer"
        assert b["applied"][0]["applied_at"] is not None      # stamped on 'applied'

    def test_move_between_stages(self, dbpath):
        _seed_job("fp1")
        tracker.set_stage("fp1", "applied")
        tracker.set_stage("fp1", "interview")
        b = tracker.board()
        assert len(b["applied"]) == 0 and len(b["interview"]) == 1
        # applied_at is preserved across the move
        assert b["interview"][0]["applied_at"] is not None

    def test_update_notes_and_next_action(self, dbpath):
        _seed_job("fp1")
        tracker.set_stage("fp1", "saved")
        tracker.update("fp1", notes="called back", next_action="Send thank-you",
                       next_action_due="2026-09-01")
        b = tracker.board()
        card = b["saved"][0]
        assert card["notes"] == "called back" and card["next_action"] == "Send thank-you"
        assert any(a["next_action"] == "Send thank-you" for a in tracker.upcoming_actions())

    def test_bad_stage_rejected(self, dbpath):
        _seed_job("fp1")
        with pytest.raises(ValueError):
            tracker.set_stage("fp1", "not_a_stage")


class TestMetrics:
    def test_funnel(self, dbpath):
        for i, stage in enumerate(["applied", "applied", "screening", "interview", "offer"]):
            _seed_job(f"fp{i}", title=f"Role {i}")
            tracker.set_stage(f"fp{i}", stage)
        m = tracker.metrics()
        assert m["applied"] == 5                    # all non-saved
        # responded = screening+interview+offer = 3 of 5
        assert m["response_rate"] == 60
        assert m["interview_rate"] == 40            # interview+offer = 2 of 5
        assert m["offer_rate"] == 20
        assert "greenhouse" in m["by_source"]

    def test_saved_not_counted_as_applied(self, dbpath):
        _seed_job("fp1"); tracker.set_stage("fp1", "saved")
        assert tracker.metrics()["applied"] == 0


class TestExport:
    def test_csv_and_json(self, dbpath, tmp_path):
        _seed_job("fp1"); tracker.set_stage("fp1", "applied")
        csv_path = tracker.export(str(tmp_path / "apps"), "csv")
        assert csv_path.endswith(".csv")
        import os
        assert os.path.getsize(csv_path) > 0
        json_path = tracker.export(str(tmp_path / "apps"), "json")
        import json as _json
        data = _json.loads(open(json_path, encoding="utf-8").read())
        assert data["applications"] and "metrics" in data
