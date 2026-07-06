"""统一数据访问层（DAL）：SQLite 实现（WAL 模式）。

提供与 utils.py 等价的读写接口，供 T3 切换使用。本文件不修改任何现有调用方。
对应 ARCHITECTURE.md ADR-001。

设计取舍：
- 存 JSON blob 列（data TEXT）+ 索引 day：事件/计时结构易变，避免将来加字段就要迁移 schema。
- 用标准库 sqlite3，不引入 SQLAlchemy（APScheduler 已自带，但主数据层不依赖它，保持轻）。
- 连接用上下文管理器，自动 commit / rollback。
- 依赖方向：shared 是最底层，绝不 import 上层 utils（避免循环依赖）。
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from .errors import DataAccessError

_DB_PATH: Optional[Path] = None


def init_store(db_path: Path) -> None:
    """初始化数据库：建文件、开 WAL、建表。幂等，可重复调用。"""
    global _DB_PATH
    _DB_PATH = Path(db_path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        _create_schema(conn)


@contextmanager
def _connect():
    if _DB_PATH is None:
        raise DataAccessError("store 未初始化：请先调用 init_store()")
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise DataAccessError(f"数据库操作失败: {e}") from e
    finally:
        conn.close()


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            day TEXT NOT NULL,
            seq INTEGER NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (day, seq)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS timelog (
            day TEXT NOT NULL,
            seq INTEGER NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (day, seq)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sops (
            sop_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS occurrence_overrides (
            date_str TEXT NOT NULL,
            event_id TEXT NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (date_str, event_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_day ON events(day)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timelog_day ON timelog(day)")


# ====== Events ======
def read_day(day: date) -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT data FROM events WHERE day=? ORDER BY seq", (day.isoformat(),)
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]


def write_day(day: date, events: list) -> None:
    d = day.isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM events WHERE day=?", (d,))
        for i, ev in enumerate(events):
            conn.execute(
                "INSERT INTO events (day, seq, data) VALUES (?,?,?)",
                (d, i, json.dumps(ev, ensure_ascii=False)),
            )


def all_event_days() -> list:
    """返回 events 表中所有不同的 day（ISO 字符串），升序。供按 id 定位事件等场景。"""
    with _connect() as conn:
        rows = conn.execute("SELECT DISTINCT day FROM events ORDER BY day").fetchall()
        return [r["day"] for r in rows]


# ====== Timelog ======
def read_timelog(day: date) -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT data FROM timelog WHERE day=? ORDER BY seq", (day.isoformat(),)
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]


def write_timelog_entry(entry: dict) -> None:
    today = date.today()
    d = today.isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM timelog WHERE day=?", (d,)
        ).fetchone()
        seq = cur["n"]
        conn.execute(
            "INSERT INTO timelog (day, seq, data) VALUES (?,?,?)",
            (d, seq, json.dumps(entry, ensure_ascii=False)),
        )


def all_timelog_in_range(start: date, end: date) -> list:
    result = []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT data FROM timelog WHERE day>=? AND day<=? ORDER BY day, seq",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        for r in rows:
            result.append(json.loads(r["data"]))
    return result


# ====== SOPs ======
def load_sop(sop_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT data FROM sops WHERE sop_id=?", (sop_id,)).fetchone()
        return json.loads(row["data"]) if row else None


def save_sop(sop_id: str, data: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sops (sop_id, data) VALUES (?, ?) "
            "ON CONFLICT(sop_id) DO UPDATE SET data=excluded.data",
            (sop_id, json.dumps(data, ensure_ascii=False)),
        )


# ====== Schedules ======
def read_schedules() -> list:
    with _connect() as conn:
        rows = conn.execute("SELECT data FROM schedules ORDER BY id").fetchall()
        return [json.loads(r["data"]) for r in rows]


def write_schedules(schedules: list) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM schedules")
        for s in schedules:
            sid = s.get("id", "")
            conn.execute(
                "INSERT INTO schedules (id, data) VALUES (?, ?)",
                (sid, json.dumps(s, ensure_ascii=False)),
            )


# ====== Occurrence Overrides ======
def read_occurrence_overrides() -> dict:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date_str, event_id, data FROM occurrence_overrides"
        ).fetchall()
        out = {}
        for r in rows:
            out.setdefault(r["date_str"], {})[r["event_id"]] = json.loads(r["data"])
        return out


def write_occurrence_override(
    date_str: str,
    event_id: str,
    status=None,
    locked=None,
    start=None,
    end=None,
    deleted=None,
) -> None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM occurrence_overrides WHERE date_str=? AND event_id=?",
            (date_str, event_id),
        ).fetchone()
        override = json.loads(row["data"]) if row else {}
        if status is not None:
            override["status"] = status
        if locked is not None:
            override["locked"] = locked
        if start is not None:
            override["start"] = start
        if end is not None:
            override["end"] = end
        if deleted is not None:
            override["deleted"] = deleted
        conn.execute(
            "INSERT INTO occurrence_overrides (date_str, event_id, data) VALUES (?, ?, ?) "
            "ON CONFLICT(date_str, event_id) DO UPDATE SET data=excluded.data",
            (date_str, event_id, json.dumps(override, ensure_ascii=False)),
        )


# ====== Custom Holidays ======
def read_custom_holidays() -> list:
    with _connect() as conn:
        rows = conn.execute("SELECT data FROM custom_holidays").fetchall()
        return [json.loads(r["data"]) for r in rows]


def write_custom_holidays(items: list) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM custom_holidays")
        for it in items:
            conn.execute(
                "INSERT INTO custom_holidays (data) VALUES (?)",
                (json.dumps(it, ensure_ascii=False),),
            )
