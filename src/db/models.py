"""SQLite database models for AgentCallCenter."""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import DB_CONFIG

logger = logging.getLogger(__name__)

_db_path: Path = DB_CONFIG["path"]
_local = threading.local()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sid        TEXT UNIQUE NOT NULL,
    phone_number    TEXT NOT NULL,
    direction       TEXT NOT NULL DEFAULT 'outbound',
    start_time      TEXT NOT NULL,
    end_time        TEXT,
    duration        INTEGER DEFAULT 0,
    backend_type    TEXT NOT NULL DEFAULT 'mock',
    recording_path  TEXT,
    status          TEXT NOT NULL DEFAULT 'initiated',
    stream_sid      TEXT,
    account_sid     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_calls_phone ON calls(phone_number);
CREATE INDEX IF NOT EXISTS idx_calls_start ON calls(start_time);
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);

CREATE TABLE IF NOT EXISTS devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    backend_type    TEXT NOT NULL,
    device_id       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'offline',
    last_active     TEXT,
    extra           TEXT,
    UNIQUE(backend_type, device_id)
);
"""


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _db_path.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(_db_path), timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


@contextmanager
def get_db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(_SCHEMA)
    logger.info("Database initialized at %s", _db_path)


def insert_call(
    call_sid: str,
    phone_number: str,
    direction: str = "outbound",
    backend_type: str = "mock",
    stream_sid: Optional[str] = None,
    account_sid: Optional[str] = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO calls
               (call_sid, phone_number, direction, start_time, backend_type,
                status, stream_sid, account_sid)
               VALUES (?, ?, ?, ?, ?, 'initiated', ?, ?)""",
            (call_sid, phone_number, direction, now, backend_type,
             stream_sid, account_sid),
        )
        return cur.lastrowid or 0


def update_call(call_sid: str, **fields: Any) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [call_sid]
    with get_db() as conn:
        conn.execute(
            f"UPDATE calls SET {set_clause} WHERE call_sid = ?", values
        )


def complete_call(call_sid: str, duration: int, recording_path: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """UPDATE calls SET status='completed', end_time=?, duration=?, recording_path=?
               WHERE call_sid=?""",
            (now, duration, recording_path, call_sid),
        )


def get_call(call_sid: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM calls WHERE call_sid = ?", (call_sid,)
        ).fetchone()
    return dict(row) if row else None


def list_calls(
    phone_number: Optional[str] = None,
    direction: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    backend_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if phone_number:
        conditions.append("phone_number LIKE ?")
        params.append(f"%{phone_number}%")
    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    if start_date:
        conditions.append("start_time >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("start_time <= ?")
        params.append(end_date)
    if backend_type:
        conditions.append("backend_type = ?")
        params.append(backend_type)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = " AND ".join(conditions) if conditions else "1=1"
    params.extend([limit, offset])

    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM calls WHERE {where} ORDER BY start_time DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def count_calls(
    phone_number: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> int:
    conditions: list[str] = []
    params: list[Any] = []
    if phone_number:
        conditions.append("phone_number LIKE ?")
        params.append(f"%{phone_number}%")
    if start_date:
        conditions.append("start_time >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("start_time <= ?")
        params.append(end_date)

    where = " AND ".join(conditions) if conditions else "1=1"
    with get_db() as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM calls WHERE {where}", params).fetchone()
    return row[0] if row else 0


def get_dashboard_stats() -> Dict[str, Any]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        today_total = conn.execute(
            "SELECT COUNT(*) FROM calls WHERE start_time >= ?", (today,)
        ).fetchone()[0]
        today_duration = conn.execute(
            "SELECT COALESCE(SUM(duration), 0) FROM calls WHERE start_time >= ?", (today,)
        ).fetchone()[0]
        today_completed = conn.execute(
            "SELECT COUNT(*) FROM calls WHERE start_time >= ? AND status='completed'",
            (today,),
        ).fetchone()[0]
        recent = conn.execute(
            "SELECT * FROM calls ORDER BY start_time DESC LIMIT 10"
        ).fetchall()
    return {
        "total_calls": total,
        "today_calls": today_total,
        "today_duration": today_duration,
        "today_success_rate": round(today_completed / today_total * 100, 1) if today_total else 0,
        "recent_calls": [dict(r) for r in recent],
    }


def upsert_device(backend_type: str, device_id: str, status: str, extra: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO devices (backend_type, device_id, status, last_active, extra)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(backend_type, device_id)
               DO UPDATE SET status=excluded.status, last_active=excluded.last_active,
                             extra=excluded.extra""",
            (backend_type, device_id, status, now, extra),
        )


def list_devices() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY backend_type").fetchall()
    return [dict(r) for r in rows]
