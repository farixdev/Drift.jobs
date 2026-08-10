"""Per-source circuit breaker + health, persisted to the `source` table.

5 consecutive failures trips the breaker: the source is disabled for 1 hour, then
a half-open probe is allowed; a success closes it. Health (status, last success,
last error, consecutive failures) is written to the `source` row so the Phase 10
Sources page can render it. All timestamps are UTC ISO.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone

FAILURE_THRESHOLD = 5
OPEN_MINUTES = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def ensure_source(defn) -> None:
    """Upsert the source row from a definition (metadata only; never clobbers
    live health fields)."""
    from db.connection import connect
    with closing(connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO source (slug, display_name, category, adapter_type,
                                base_url, auth_required, rate_limit_rpm, is_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                display_name = excluded.display_name,
                category = excluded.category,
                adapter_type = excluded.adapter_type,
                base_url = excluded.base_url,
                rate_limit_rpm = excluded.rate_limit_rpm
            """,
            (defn.slug, defn.display_name, defn.category, defn.adapter_type,
             defn.base_url, 1 if defn.auth_type == "key" else 0,
             defn.rate_limit_rpm, 1 if defn.enabled else 0),
        )


def allow(slug: str) -> bool:
    """False when the breaker is open (disabled and still within the cool-off)."""
    from db.connection import connect
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT disabled_until FROM source WHERE slug=?", (slug,)
        ).fetchone()
    if not row or not row["disabled_until"]:
        return True
    try:
        until = datetime.fromisoformat(row["disabled_until"])
    except ValueError:
        return True
    return _now() >= until  # past cool-off -> half-open probe allowed


def record_success(slug: str) -> None:
    from db.connection import connect
    with closing(connect()) as conn, conn:
        conn.execute(
            """UPDATE source SET consecutive_failures=0, health_status='healthy',
               last_success_at=?, last_error='', disabled_until=NULL WHERE slug=?""",
            (_iso(_now()), slug),
        )


def record_failure(slug: str, error: str) -> None:
    from db.connection import connect
    with closing(connect()) as conn, conn:
        row = conn.execute(
            "SELECT consecutive_failures FROM source WHERE slug=?", (slug,)
        ).fetchone()
        fails = (row["consecutive_failures"] if row else 0) + 1
        if fails >= FAILURE_THRESHOLD:
            conn.execute(
                """UPDATE source SET consecutive_failures=?, health_status='disabled',
                   last_error=?, disabled_until=? WHERE slug=?""",
                (fails, error[:300], _iso(_now() + timedelta(minutes=OPEN_MINUTES)), slug),
            )
        else:
            conn.execute(
                """UPDATE source SET consecutive_failures=?, health_status='degraded',
                   last_error=? WHERE slug=?""",
                (fails, error[:300], slug),
            )


def health(slug: str) -> dict:
    from db.connection import connect
    with closing(connect()) as conn:
        row = conn.execute(
            """SELECT health_status, last_success_at, last_error,
                      consecutive_failures, disabled_until FROM source WHERE slug=?""",
            (slug,),
        ).fetchone()
    return dict(row) if row else {}
