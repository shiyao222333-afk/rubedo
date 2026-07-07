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
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .errors import DataAccessError
from .logging_cfg import get_logger

log = get_logger("rubedo.store")

_DB_PATH: Optional[Path] = None


def init_store(db_path: Path) -> None:
    """初始化数据库：建文件、开 WAL、建表。幂等，可重复调用。"""
    global _DB_PATH
    _DB_PATH = Path(db_path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        _create_schema(conn)
    # 限制3 fix: event_id 列迁移用独立连接，避免 ALTER 落在 schema 建表事务内
    _migrate_event_id_column()


def _migrate_event_id_column() -> None:
    """为 events 加 event_id 列并回填旧数据，支持 O(1) 按 id 定位。幂等。"""
    with _connect() as conn:
        conn.commit()  # 结束任何隐式事务，确保 ALTER 不在事务中执行
        try:
            conn.execute("ALTER TABLE events ADD COLUMN event_id TEXT")
        except sqlite3.OperationalError:
            pass  # 列已存在
        conn.execute(
            "UPDATE events SET event_id = json_extract(data, '$.id') WHERE event_id IS NULL"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_event_id ON events(event_id)")


@contextmanager
def _connect():
    if _DB_PATH is None:
        raise DataAccessError("store 未初始化：请先调用 init_store()")
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA busy_timeout=5000")  # 并发写冲突时等待 5s，而非立即报 database is locked
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
    # 大类一 P1: 项目表（订单档案）。结构化列（非整块 JSON）便于按状态筛选/聚合。
    # sop_current_step 用 TEXT 存 step_id（如 "1.3"），不随 SOP 增删错位（ADR-002 D1）。
    # step_data 为 JSON 黑板：{step_id: {duration_sec, fields:{...}, active_timer:{...}}}。
    # status 含 on_hold/cancelled（G5）。
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            client TEXT,
            sop_id TEXT NOT NULL DEFAULT 'kujiale',
            income REAL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','active','review','done','paid','cancelled','on_hold')),
            sop_current_step TEXT DEFAULT '',
            step_data TEXT DEFAULT '{}',
            due_date TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_day ON events(day)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timelog_day ON timelog(day)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")


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
                "INSERT INTO events (day, seq, event_id, data) VALUES (?,?,?,?)",
                (d, i, ev.get("id"), json.dumps(ev, ensure_ascii=False)),
            )


def all_event_days() -> list:
    """返回 events 表中所有不同的 day（ISO 字符串），升序。供按 id 定位事件等场景。"""
    with _connect() as conn:
        rows = conn.execute("SELECT DISTINCT day FROM events ORDER BY day").fetchall()
        return [r["day"] for r in rows]


def find_day_by_event_id(event_id: str):
    """返回事件所在 day（ISO 字符串）或 None。走 event_id 索引，O(1)，替代全表天扫描。"""
    with _connect() as conn:
        row = conn.execute(
            "SELECT day FROM events WHERE event_id=? LIMIT 1", (event_id,)
        ).fetchone()
        return row["day"] if row else None


# ====== Timelog ======
def read_timelog(day: date) -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT data FROM timelog WHERE day=? ORDER BY seq", (day.isoformat(),)
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]


def write_timelog_entry(entry: dict) -> None:
    # 限制2 fix: 优先用 entry 自带日期（start_time 或 day），否则回退今天
    # —— 避免跨午夜记一笔时被写错天
    day_str = entry.get("day") or (entry.get("start_time") or "")[:10] or None
    if day_str:
        try:
            d = date.fromisoformat(day_str)
        except ValueError:
            d = date.today()
    else:
        d = date.today()
    d = d.isoformat()
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
            sid = s.get("id")
            if not sid:
                log.warning(
                    f"write_schedules: 跳过缺 id 的 schedule（title={s.get('title', '<无>')}），避免主键冲突"
                )
                continue
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
    sop_current_step=None,
    sop_step_timings=None,
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
        if sop_current_step is not None:
            override["sop_current_step"] = sop_current_step
        if sop_step_timings is not None:
            override.setdefault("sop_step_timings", {}).update(sop_step_timings)
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


# ====== Projects（大类一 P1：订单档案）======
def _row_to_project(row) -> dict:
    d = dict(row)
    try:
        d["step_data"] = json.loads(d["step_data"]) if d.get("step_data") else {}
    except (json.JSONDecodeError, TypeError):
        d["step_data"] = {}
    return d


def create_project(payload: dict) -> str:
    """新建项目（订单）。name 必填；返回项目 id。"""
    pid = payload.get("id") or str(uuid4())
    now = datetime.now().isoformat(timespec="seconds")
    name = (payload.get("name") or "").strip()
    if not name:
        raise DataAccessError("项目 name 不能为空")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO projects "
            "(id,name,client,sop_id,income,status,sop_current_step,step_data,due_date,notes,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pid, name, payload.get("client"),
                payload.get("sop_id", "kujiale"),
                float(payload.get("income") or 0),
                payload.get("status", "pending"),
                payload.get("sop_current_step", ""),
                json.dumps(payload.get("step_data") or {}, ensure_ascii=False),
                payload.get("due_date"), payload.get("notes"),
                now, now,
            ),
        )
    return pid


def list_projects(status: Optional[str] = None) -> list:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM projects WHERE status=? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [_row_to_project(r) for r in rows]


def get_project(pid: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return _row_to_project(row) if row else None


def update_project(pid: str, fields: dict) -> bool:
    """更新项目字段（白名单）。返回是否更新到行。"""
    allowed = {"name", "client", "sop_id", "income", "status",
               "sop_current_step", "step_data", "due_date", "notes"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed or v is None and k not in ("income", "due_date", "notes"):
            if k not in allowed:
                continue
        if k == "step_data" and isinstance(v, dict):
            v = json.dumps(v, ensure_ascii=False)
        if k == "income":
            v = float(v or 0)
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return False
    sets.append("updated_at=?")
    vals.append(datetime.now().isoformat(timespec="seconds"))
    vals.append(pid)
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE projects SET {','.join(sets)} WHERE id=?", vals
        )
        return cur.rowcount > 0


def delete_project(pid: str) -> None:
    """删除项目（G20 解决）：级联把引用它的 project_id 置空，计时日志保留做历史。"""
    with _connect() as conn:
        erows = conn.execute(
            "SELECT day, seq, data FROM events WHERE json_extract(data,'$.project_id')=?", (pid,)
        ).fetchall()
        for r in erows:
            ev = json.loads(r["data"]); ev["project_id"] = None
            conn.execute("UPDATE events SET data=? WHERE day=? AND seq=?",
                         (json.dumps(ev, ensure_ascii=False), r["day"], r["seq"]))
        srows = conn.execute(
            "SELECT id, data FROM schedules WHERE json_extract(data,'$.project_id')=?", (pid,)
        ).fetchall()
        for r in srows:
            s = json.loads(r["data"]); s["project_id"] = None
            conn.execute("UPDATE schedules SET data=? WHERE id=?",
                         (json.dumps(s, ensure_ascii=False), r["id"]))
        orows = conn.execute(
            "SELECT date_str, event_id, data FROM occurrence_overrides "
            "WHERE json_extract(data,'$.project_id')=?", (pid,)
        ).fetchall()
        for r in orows:
            o = json.loads(r["data"]); o["project_id"] = None
            conn.execute("UPDATE occurrence_overrides SET data=? WHERE date_str=? AND event_id=?",
                         (json.dumps(o, ensure_ascii=False), r["date_str"], r["event_id"]))
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))


def _parse_occurrence_date_str(event_id: str) -> str:
    """recurring-{schedule_id}-{YYYY-MM-DD} -> YYYY-MM-DD"""
    parts = event_id.split("-")
    return "-".join(parts[-3:])


def bind_event_to_project(pid: str, event_id: str) -> None:
    """把事件/重复实例绑到项目；若为 pending 项目则自动转 active（G5）。"""
    if event_id.startswith("recurring-"):
        date_str = _parse_occurrence_date_str(event_id)
        row = None
        with _connect() as conn:
            row = conn.execute(
                "SELECT data FROM occurrence_overrides WHERE date_str=? AND event_id=?",
                (date_str, event_id),
            ).fetchone()
            if not row:
                raise DataAccessError("该重复实例不存在")
            o = json.loads(row["data"]); o["project_id"] = pid
            conn.execute(
                "INSERT INTO occurrence_overrides (date_str, event_id, data) VALUES (?,?,?) "
                "ON CONFLICT(date_str, event_id) DO UPDATE SET data=excluded.data",
                (date_str, event_id, json.dumps(o, ensure_ascii=False)),
            )
    else:
        day = find_day_by_event_id(event_id)
        if day is None:
            raise DataAccessError("该事件不存在")
        events = read_day(date.fromisoformat(day))
        found = False
        for ev in events:
            if ev.get("id") == event_id:
                ev["project_id"] = pid
                found = True
                break
        if not found:
            raise DataAccessError("该事件不存在")
        write_day(date.fromisoformat(day), events)
    # 自动流转 pending -> active（G5）
    proj = get_project(pid)
    if proj and proj["status"] == "pending":
        update_project(pid, {"status": "active"})


def unbind_event_from_project(pid: str, event_id: str) -> None:
    """解绑事件/重复实例（仅置空 project_id，不影响其它数据）。"""
    if event_id.startswith("recurring-"):
        date_str = _parse_occurrence_date_str(event_id)
        with _connect() as conn:
            row = conn.execute(
                "SELECT data FROM occurrence_overrides WHERE date_str=? AND event_id=?",
                (date_str, event_id),
            ).fetchone()
            if not row:
                return
            o = json.loads(row["data"]); o["project_id"] = None
            conn.execute(
                "INSERT INTO occurrence_overrides (date_str, event_id, data) VALUES (?,?,?) "
                "ON CONFLICT(date_str, event_id) DO UPDATE SET data=excluded.data",
                (date_str, event_id, json.dumps(o, ensure_ascii=False)),
            )
    else:
        day = find_day_by_event_id(event_id)
        if day is None:
            return
        events = read_day(date.fromisoformat(day))
        for ev in events:
            if ev.get("id") == event_id:
                ev["project_id"] = None
                break
        write_day(date.fromisoformat(day), events)
