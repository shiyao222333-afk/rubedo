"""
Rubedo · 凝华 — 工具函数模块
包含：路径定义、常量、通用工具函数
"""

import calendar
import json
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

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
SCHEDULES_FILE = DATA_DIR / "schedules.json"
OCCURRENCE_OVERRIDES_FILE = DATA_DIR / "occurrence_overrides.json"

# ====== Schedules I/O ======
def read_schedules() -> list[dict]:
    """Read all schedule templates."""
    if not SCHEDULES_FILE.exists():
        return []
    try:
        data = json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []

def write_schedules(schedules: list[dict]) -> None:
    """Write schedule templates."""
    SCHEDULES_FILE.write_text(json.dumps(schedules, ensure_ascii=False, indent=2), encoding="utf-8")

def read_occurrence_overrides() -> dict:
    """Read all occurrence overrides."""
    if not OCCURRENCE_OVERRIDES_FILE.exists():
        return {}
    try:
        return json.loads(OCCURRENCE_OVERRIDES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def write_occurrence_override(
    date_str: str,
    event_id: str,
    status: str = None,
    locked: bool = None,
    start: str = None,
    end: str = None,
    deleted: bool = None
) -> None:
    """Write an override for a recurring event occurrence."""
    all_overrides = read_occurrence_overrides()
    overrides = all_overrides.get(date_str, {})
    override = overrides.get(event_id, {})
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
    overrides[event_id] = override
    all_overrides[date_str] = overrides
    OCCURRENCE_OVERRIDES_FILE.write_text(
        json.dumps(all_overrides, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# ====== Events I/O ======
def daily_file(day: date) -> Path:
    """Return path for a day's event file."""
    return DATA_DIR / f"{day.isoformat()}.json"

def read_day(day: date) -> list[dict]:
    """Read events for a specific day."""
    f = daily_file(day)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

def write_day(day: date, events: list[dict]) -> None:
    """Write events for a specific day."""
    daily_file(day).write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")

# ====== Timelog I/O ======
def timelog_file(day: date) -> Path:
    """Return path for a day's timelog file."""
    return TIMELOG_DIR / f"{day.isoformat()}.json"

def read_timelog(day: date) -> list[dict]:
    """Read timelog entries for a specific day."""
    f = timelog_file(day)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

def write_timelog_entry(entry: dict) -> None:
    """Append a timelog entry to today's file."""
    today = date.today()
    entries = read_timelog(today)
    entries.append(entry)
    timelog_file(today).write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

def all_timelog_in_range(start: date, end: date) -> list[dict]:
    """Read all timelog entries in a date range."""
    result = []
    current = start
    while current <= end:
        result.extend(read_timelog(current))
        current += timedelta(days=1)
    return result

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
    
    # Custom holidays
    custom_file = DATA_DIR / "custom_holidays.json"
    if custom_file.exists():
        try:
            with open(custom_file, "r", encoding="utf-8") as f:
                custom_holidays = json.load(f)
            for h in custom_holidays:
                h_date_str = h.get("date", "")
                if h_date_str:
                    result["custom_holidays"].append({
                        "name": h.get("name", "自定义节假日"),
                        "date": h_date_str,
                        "type": "custom_holiday"
                    })
        except Exception:
            pass
    
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
    """Load a SOP definition from data/sops/ directory."""
    sop_file = SOPS_DIR / f"{sop_id}.json"
    if not sop_file.exists():
        return None
    try:
        return json.loads(sop_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


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
            })

    return events

def expand_preheat_schedules(start: date, end: date) -> list[dict]:
    """Expand preheat (预热) schedules (placeholder)."""
    return []
