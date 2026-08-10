"""Migration 006 — embedding cache for the semantic ranking stage.

Embeddings are expensive, so each job's description embedding is cached by content
fingerprint + model and reused across scans (Phase 8 ranking stage 2). Additive.
"""
from __future__ import annotations

import sqlite3

VERSION = 6
NAME = "job_embedding"


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE job_embedding (
            fingerprint TEXT NOT NULL,
            model TEXT NOT NULL,
            vector_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (fingerprint, model)
        )
        """
    )


def down(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS job_embedding")
