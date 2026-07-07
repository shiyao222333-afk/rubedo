"""
Rubedo · 凝华 — 工具函数模块
包含：路径定义、常量、通用工具函数

v0.4 T3：数据读写改走 modules.shared.store（SQLite DAL），见 docs/ARCHITECTURE.md ADR-001。
"""

import calendar
import json
import logging
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from modules.shared import store
from modules.shared.logging_cfg import get_logger

log = get_logger("rubedo.utils")

# 数据库路径：与 migrate.py / rollback.py 保持一致（rubedo 根目录）
DB_PATH = Path(__file__).parent / "rubedo.db"
store.init_store(DB_PATH)

# ====== Paths ======
BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
SOPS_DIR  = DATA_DIR / "sops"
TIMELOG_DIR = DATA_DIR / "timelog"

# ====== Constants ======
KIND_COLORS = {
    "sop":       {"back": "#4CAF50", "bar": "#388E3C"},
    "tool":      {"back": "#2196F3", "bar": "#1976D2"},
    "reminder":  {"back": "#9E9E9E", "bar": "#757575"},
    "external":  {"back": "#FF9800", "bar": "#F57C00"},
    "marker":    {"back": "#F44336", "bar": "#D32F2F"},
}

REPEAT_MODES = ["none", "daily", "weekly", "weekday", "monthly", "yearly", "preheat"]
EXEC_MODES  = ["auto", "manual"]
STATUSES   = ["pending", "done", "skipped"]

# ====== Schedules (重复事件模板) ======
# 注意：以下常量保留供 api.py 兼容导入；数据实际已迁到 SQLite（store）。
SCHEDULES_FILE = DATA_DIR / "schedules.json"
OCCURRENCE_OVERRIDES_FILE = DATA_DIR / "occurrence_overrides.json"

# ====== Schedules I/O (v0.4 T3: 改走 SQLite DAL) ======
def read_schedules() -> list[dict]:
    """Read all schedule templates (from SQLite)."""
    try:
        return store.read_schedules()
    except Exception as e:
        log.warning(f"read_schedules: {e}")
        return []

def write_schedules(schedules: list[dict]) -> None:
    """Write schedule templates (to SQLite)."""
    try:
        store.write_schedules(schedules)
    except Exception as e:
        log.error(f"write_schedules failed: {e}")

def read_occurrence_overrides() -> dict:
    """Read all occurrence overrides (from SQLite)."""
    try:
        return store.read_occurrence_overrides()
    except Exception as e:
        log.warning(f"read_occurrence_overrides: {e}")
        return {}

def write_occurrence_override(
    date_str: str,
    event_id: str,
    status: str = None,
    locked: bool = None,
    start: str = None,
    end: str = None,
    deleted: bool = None,
    sop_current_step: int = None
) -> None:
    """Write an override for a recurring event occurrence (to SQLite)."""
    try:
        store.write_occurrence_override(
            date_str, event_id,
            status=status, locked=locked, start=start, end=end, deleted=deleted,
            sop_current_step=sop_current_step
        )
    except Exception as e:
        log.error(f"write_occurrence_override failed: {e}")

# ====== Events I/O (v0.4 T3: 改走 SQLite DAL) ======
# daily_file 保留（路径约定参考），但读写已走 store。
def daily_file(day: date) -> Path:
    """Return path for a day's event file (legacy path reference)."""
    return DATA_DIR / f"{day.isoformat()}.json"

def read_day(day: date) -> list[dict]:
    """Read events for a specific day (from SQLite)."""
    try:
        return store.read_day(day)
    except Exception as e:
        log.warning(f"read_day {day}: {e}")
        return []

def write_day(day: date, events: list[dict]) -> None:
    """Write events for a specific day (to SQLite)."""
    try:
        store.write_day(day, events)
    except Exception as e:
        log.error(f"write_day {day} failed: {e}")

# ====== Timelog I/O (v0.4 T3: 改走 SQLite DAL) ======
def timelog_file(day: date) -> Path:
    """Return path for a day's timelog file (legacy path reference)."""
    return TIMELOG_DIR / f"{day.isoformat()}.json"

def read_timelog(day: date) -> list[dict]:
    """Read timelog entries for a specific day (from SQLite)."""
    try:
        return store.read_timelog(day)
    except Exception as e:
        log.warning(f"read_timelog {day}: {e}")
        return []

def write_timelog_entry(entry: dict) -> None:
    """Append a timelog entry (to SQLite)."""
    try:
        store.write_timelog_entry(entry)
    except Exception as e:
        log.error(f"write_timelog_entry failed: {e}")

def all_timelog_in_range(start: date, end: date) -> list[dict]:
    """Read all timelog entries in a date range (from SQLite)."""
    try:
        return store.all_timelog_in_range(start, end)
    except Exception as e:
        log.warning(f"all_timelog_in_range {start}~{end}: {e}")
        return []

# ====== Utility Functions ======
def strip_icon(text: str) -> str:
    """Strip emoji/icon prefix from event text."""
    if not text:
        return ''
    result = []
    started = False
    for ch in text:
        if started:
            result.append(ch)
        else:
            # 跳过 emoji/符号字符（宽字符且非字母数字）
            if unicodedata.category(ch).startswith(('S', 'P')) and ord(ch) > 127:
                continue
            if ch.strip():
                started = True
                result.append(ch)
    return ''.join(result).strip()

def get_special_days(year: int) -> dict:
    """Get all special days for a given year.
    Returns dict with keys: shopping_festivals, holidays, custom_holidays
    Each is a list of dicts with name, date (YYYY-MM-DD), type
    """
    # Lazy import to avoid circular dependency
    from holidays import get_all_festivals_for_year, fetch_holidays
    
    result = {
        "shopping_festivals": [],
        "holidays": [],
        "custom_holidays": []
    }
    
    # Shopping festivals (assume same dates each year)
    for name, start_mmdd, end_mmdd in get_all_festivals_for_year(year):
        sm, sd = int(start_mmdd[:2]), int(start_mmdd[3:])
        try:
            fest_date = date(year, sm, sd)
            result["shopping_festivals"].append({
                "name": name,
                "date": fest_date.isoformat(),
                "type": "shopping_festival",
                "mmdd": start_mmdd
            })
        except ValueError:
            pass
    
    # Holidays (from API)
    holiday_data = fetch_holidays(year)
    if holiday_data and "holidays" in holiday_data:
        for h in holiday_data["holidays"]:
            h_date_str = h.get("date", "")
            if h_date_str:
                result["holidays"].append({
                    "name": h.get("name", "节假日"),
                    "date": h_date_str,
                    "type": "holiday"
                })
    
    # Custom holidays (v0.4 T3: 改走 SQLite DAL)
    try:
        custom_holidays = store.read_custom_holidays()
    except Exception as e:
        log.warning(f"read custom holidays: {e}")
        custom_holidays = []
    for h in custom_holidays:
        h_date_str = h.get("date", "")
        if h_date_str:
            result["custom_holidays"].append({
                "name": h.get("name", "自定义节假日"),
                "date": h_date_str,
                "type": "custom_holiday"
            })

    return result

def all_events_in_range(start: date, end: date) -> list[dict]:
    """Read all non-recurring events in a date range from daily JSON files."""
    result = []
    current = start
    while current <= end:
        result.extend(read_day(current))
        current += timedelta(days=1)
    return result


def load_sop(sop_id: str) -> Optional[dict]:
    """Load a SOP definition (from SQLite)."""
    try:
        return store.load_sop(sop_id)
    except Exception as e:
        log.warning(f"load_sop {sop_id}: {e}")
        return None


# ====== Custom Holidays (v0.4 T3: 包装 DAL，供 api/holidays 复用) ======
def read_custom_holidays() -> list:
    """Read custom holidays (from SQLite)."""
    try:
        return store.read_custom_holidays()
    except Exception as e:
        log.warning(f"read_custom_holidays: {e}")
        return []


def write_custom_holidays(items: list) -> None:
    """Write custom holidays (to SQLite)."""
    try:
        store.write_custom_holidays(items)
    except Exception as e:
        log.error(f"write_custom_holidays failed: {e}")


# ====== Event lookup helper (v0.4 T3: 供 api_update_sop_step 在 SQLite 中定位/写回事件) ======
def find_event_by_id(event_id: str):
    """在 SQLite 中按 id 查找事件，返回 (day: date, events: list) 或 (None, None)。

    返回整天的事件列表（而非单个事件），与 save_event_day(day, events) 契约一致，
    供调用方修改 sop_current_step 等字段后整体写回。

    限制3 fix: 走 store.find_day_by_event_id（event_id 索引，O(1)），
    不再遍历每一天开连接做全表天扫描。
    """
    day_str = store.find_day_by_event_id(event_id)
    if day_str:
        try:
            d = date.fromisoformat(day_str)
        except ValueError:
            return None, None
        return d, store.read_day(d)
    return None, None


def save_event_day(day: date, events: list[dict]) -> None:
    """写回某天的全部事件（to SQLite）。"""
    try:
        store.write_day(day, events)
    except Exception as e:
        log.error(f"save_event_day {day} failed: {e}")


def calc_hourly_rate(entries: list[dict], events: list[dict]) -> dict:
    """Calculate hourly rate and time breakdown from timelog entries."""
    total_minutes = sum(e.get("duration_min", 0) for e in entries)
    total_income = sum(e.get("income", 0.0) for e in entries)
    hourly_rate = (total_income / (total_minutes / 60)) if total_minutes > 0 else 0.0

    by_sop = {}
    for e in entries:
        sid = e.get("sop_id", "unknown")
        if sid not in by_sop:
            by_sop[sid] = {"minutes": 0, "income": 0.0}
        by_sop[sid]["minutes"] += e.get("duration_min", 0)
        by_sop[sid]["income"] += e.get("income", 0.0)

    return {
        "total_minutes": total_minutes,
        "total_income": total_income,
        "hourly_rate": round(hourly_rate, 2),
        "by_sop": by_sop,
    }


# ====== Expand Recurring Schedules ======
def expand_recurring_schedules(start: date, end: date) -> list[dict]:
    """Expand all recurring schedules into concrete events."""
    schedules = read_schedules()
    events = []
    overrides_by_date = read_occurrence_overrides()

    for s in schedules:
        try:
            sid = s["id"]
            title = s.get("title", "未命名")
            kind = s.get("kind", "reminder")
            description = s.get("description", "")
            reminder = s.get("reminder", "none")
            exec_mode = s.get("exec_mode", "manual")
            start_time = s.get("start_time", "09:00")
            duration_minutes = s.get("duration_minutes", 60)
            repeat_mode = s.get("repeat_mode", "none")
            repeat_until = s.get("repeat_until", "")

            if repeat_mode == "none":
                continue

            # Calculate occurrences
            occurrences = []
            if repeat_mode == "daily":
                current = start
                while current <= end:
                    occurrences.append(current)
                    current += timedelta(days=1)
            elif repeat_mode == "weekly":
                weekdays = s.get("weekdays", [start.weekday()])
                current = start
                while current <= end:
                    if current.weekday() in weekdays:
                        occurrences.append(current)
                    current += timedelta(days=1)
            elif repeat_mode == "weekday":
                current = start
                while current <= end:
                    if current.weekday() < 5:
                        occurrences.append(current)
                    current += timedelta(days=1)
            elif repeat_mode == "monthly":
                day_of_month = s.get("day_of_month", start.day)
                current = start.replace(day=1)
                while current <= end:
                    try:
                        target = current.replace(day=day_of_month)
                        if start <= target <= end:
                            occurrences.append(target)
                    except ValueError:
                        pass
                    # Move to next month
                    if current.month == 12:
                        current = current.replace(year=current.year + 1, month=1)
                    else:
                        current = current.replace(month=current.month + 1)
            elif repeat_mode == "yearly":
                month = s.get("month", start.month)
                day = s.get("day", start.day)
                current = start.replace(month=month, day=day)
                while current <= end:
                    if current >= start:
                        occurrences.append(current)
                    current = current.replace(year=current.year + 1)

            # Parse start_time
            sh, sm = 9, 0
            if start_time and ":" in start_time:
                parts = start_time.split(":")
                sh = int(parts[0]) if parts[0].isdigit() else 9
                sm = int(parts[1]) if parts[1].isdigit() else 0

            for d in occurrences:
                start_dt = datetime.combine(d, datetime.min.time().replace(hour=sh, minute=sm))
                end_dt = start_dt + timedelta(minutes=duration_minutes)
                event_id = f"recurring-{sid}-{d.isoformat()}"
                date_overrides = overrides_by_date.get(d.isoformat(), {})
                occurrence_override = date_overrides.get(event_id, {})

                # Skip deleted occurrences
                if occurrence_override.get("deleted", False):
                    continue

                events.append({
                    "id": event_id,
                    "start": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "end": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "text": title,
                    "kind": kind,
                    "description": description,
                    "reminder": reminder,
                    "exec_mode": exec_mode,
                    "status": occurrence_override.get("status", "pending"),
                    "locked": occurrence_override.get("locked", False),
                    "readonly": True,
                    "schedule_id": sid,
                    "recurring": True,
                    "sop_id": s.get("sop_id", "kujiale"),
                    "sop_current_step": occurrence_override.get("sop_current_step", 0),
                })
        except Exception as e:
            # 单条模板配置异常（缺 id / 非法字段）不应拖垮整本日历
            log.error(f"expand_recurring_schedules: 跳过异常模板 {s.get('id', '?')}: {e}")
            continue

    return events

def expand_preheat_schedules(start: date, end: date) -> list[dict]:
    """Expand preheat (预热) schedules (placeholder)."""
    return []
