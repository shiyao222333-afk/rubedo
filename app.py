"""
Rubedo · 凝华 — v0.3.0 酷家乐 SOP + 时间审计
NiceGUI 桌面应用入口

架构：
  app.py          → 主入口（路由 + API + 数据层 + APScheduler）
  data/           → JSON 文件存储
    YYYY-MM-DD.json     → 每日事件数据
    schedules.json      → 重复事件模板
    markers.json        → 手动标记日（购物节等）
    holidays_YYYY.json  → 法定节假日缓存
    sops/               → SOP 环节定义
    timelog/            → 时间审计记录（v0.3.0 启用）
  pages/          → 未来多页面拆分预留
"""

import asyncio
import calendar
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

# ====== Paths ======
BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
SOPS_DIR  = DATA_DIR / "sops"
TIMELOG_DIR = DATA_DIR / "timelog"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
SOPS_DIR.mkdir(parents=True, exist_ok=True)
TIMELOG_DIR.mkdir(parents=True, exist_ok=True)

# ====== NiceGUI ======
import sys; sys.dont_write_bytecode = True
from nicegui import app, ui, run
from starlette.requests import Request

# Mount static/ directory → serves /static/*.js and *.css
app.add_static_files('/static', str(BASE_DIR / 'static'))

# ====== Constants ======
KIND_COLORS = {
    "sop":      {"back": "#4CAF50", "bar": "#388E3C"},   # 绿 — SOP 工作流
    "tool":      {"back": "#2196F3", "bar": "#1976D2"},   # 蓝 — 共用工具
    "reminder":  {"back": "#9E9E9E", "bar": "#757575"},   # 灰 — 提醒
    "external":  {"back": "#FF9800", "bar": "#F57C00"},   # 橙 — 外部事件
    "marker":    {"back": "#F44336", "bar": "#D32F2F"},   # 红 — 标记日
}

REPEAT_MODES = ["none", "daily", "weekly", "weekday", "monthly", "yearly", "preheat"]
EXEC_MODES  = ["auto", "manual"]
STATUSES     = ["pending", "done", "skipped"]

# ====== Schedules (重复事件模板) ======
SCHEDULES_FILE = DATA_DIR / "schedules.json"
OCCURRENCE_OVERRIDES_FILE = DATA_DIR / "occurrence_overrides.json"

def read_schedules() -> list[dict]:
    """Read all schedule templates."""
    if not SCHEDULES_FILE.exists():
        return []
    try:
        data = json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        # 防御：如果 JSON 顶层是 dict（格式错误），安全返回空列表
        return []
    except (json.JSONDecodeError, OSError):
        return []

def write_schedules(schedules: list[dict]) -> None:
    """Write schedule templates."""
    SCHEDULES_FILE.write_text(json.dumps(schedules, ensure_ascii=False, indent=2), encoding="utf-8")

def read_occurrence_overrides() -> dict:
    """Read all occurrence overrides. Returns {date_str: {event_id: {status, locked}}}."""
    if not OCCURRENCE_OVERRIDES_FILE.exists():
        return {}
    try:
        return json.loads(OCCURRENCE_OVERRIDES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def write_occurrence_override(date_str: str, event_id: str, status: str = None, locked: bool = None) -> None:
    """Write an override for a recurring event occurrence."""
    all_overrides = read_occurrence_overrides()
    overrides = all_overrides.get(date_str, {})
    override = overrides.get(event_id, {})
    if status is not None:
        override["status"] = status
    if locked is not None:
        override["locked"] = locked
    overrides[event_id] = override
    all_overrides[date_str] = overrides
    OCCURRENCE_OVERRIDES_FILE.write_text(
        json.dumps(all_overrides, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def get_special_days(year: int) -> dict:
    """Get all special days for a given year.
    Returns dict with keys: shopping_festivals, holidays, custom_holidays
    Each is a list of dicts with name, date (YYYY-MM-DD), type
    """
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

def expand_preheat_schedules(start: date, end: date) -> list[dict]:
    """Expand preheat schedules into events for the given date range."""
    events = []
    schedules = read_schedules()
    
    for schedule in schedules:
        if not schedule.get("enabled", True):
            continue
        if schedule.get("repeat_mode") != "preheat":
            continue
        
        target_type = schedule.get("target_type", "")
        target_mmdd = schedule.get("target_date", "")  # MM-DD format
        preheat_days = schedule.get("preheat_days", 7)
        scope = schedule.get("scope", "yearly")  # yearly or once
        schedule_year = schedule.get("year", 0)
        
        if not target_mmdd:
            continue
        
        # Parse target date
        try:
            tm, td = int(target_mmdd[:2]), int(target_mmdd[3:])
        except (ValueError, IndexError):
            continue
        
        # For "once" scope, only generate for the specified year
        if scope == "once":
            if start.year != schedule_year and end.year != schedule_year:
                continue
            try:
                target_date = date(schedule_year, tm, td)
            except ValueError:
                continue
        else:
            # Yearly: generate for each year in the range
            target_date = None
            for yr in range(start.year, end.year + 1):
                try:
                    d = date(yr, tm, td)
                    if start <= d <= end:
                        target_date = d
                        break
                except ValueError:
                    continue
            if target_date is None:
                continue
        
        # Calculate preheat date
        if scope == "once":
            years_to_check = [schedule_year]
        else:
            years_to_check = range(start.year, end.year + 1)
        
        for yr in years_to_check:
            try:
                target_date = date(yr, tm, td)
                preheat_date = target_date - timedelta(days=preheat_days)
                
                if start <= preheat_date <= end:
                    # Generate event
                    start_time = schedule.get("start_time", "09:00")
                    duration = schedule.get("duration_minutes", 60)
                    sh, sm = int(start_time[:2]), int(start_time[3:])
                    end_dt = datetime.combine(preheat_date, datetime.min.time().replace(hour=sh, minute=sm)) + timedelta(minutes=duration)
                    
                    event = {
                        "id": f"preheat-{schedule['id']}-{preheat_date.isoformat()}",
                        "start": preheat_date.isoformat() + f"T{start_time}:00",
                        "end": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                        "text": schedule.get("title", "预热事件"),
                        "backColor": "#FF5722",
                        "barColor": "#D84315",
                        "kind": schedule.get("kind", "reminder"),
                        "description": schedule.get("description", ""),
                        "reminder": schedule.get("reminder", "none"),
                        "exec_mode": schedule.get("exec_mode", "manual"),
                        "status": "pending",
                        "locked": False,
                        "schedule_id": schedule["id"],
                        "preheat": True,
                        "target_date": target_date.isoformat(),
                        "target_name": schedule.get("target_name", ""),
                    }
                    events.append(event)
            except ValueError:
                continue
    
    return events


def expand_recurring_schedules(start: date, end: date) -> list[dict]:
    """Expand recurring schedules (daily/weekly/monthly/yearly) into events."""
    events = []
    schedules = read_schedules()

    for schedule in schedules:
        if not schedule.get("enabled", True):
            continue

        repeat_mode = schedule.get("repeat_mode", "")
        if repeat_mode not in ("daily", "weekly", "monthly", "yearly"):
            continue

        start_date_str = schedule.get("start_date", "")
        if not start_date_str:
            continue

        try:
            sched_start = date.fromisoformat(start_date_str)
        except (ValueError, TypeError):
            continue

        start_time = schedule.get("start_time", "09:00")
        duration = schedule.get("duration_minutes", 60)
        title = schedule.get("title", "重复事件")
        sid = schedule.get("id", "unknown")

        try:
            sh, sm = int(start_time[:2]), int(start_time[3:])
        except (ValueError, IndexError):
            sh, sm = 9, 0

        occurrences = []

        if repeat_mode == "daily":
            days_diff = (start - sched_start).days
            if days_diff < 0:
                d = sched_start
            else:
                d = sched_start + timedelta(days=days_diff)
            while d <= end:
                if d >= start:
                    occurrences.append(d)
                d += timedelta(days=1)

        elif repeat_mode == "weekly":
            days_diff = (start - sched_start).days
            if days_diff < 0:
                d = sched_start
            else:
                weeks = days_diff // 7
                d = sched_start + timedelta(weeks=weeks)
                if d < start:
                    d += timedelta(days=7)
            while d <= end:
                if d >= start:
                    occurrences.append(d)
                d += timedelta(days=7)

        elif repeat_mode == "monthly":
            y, m, day = sched_start.year, sched_start.month, sched_start.day
            while (y, m) < (start.year, start.month):
                m += 1
                if m > 12:
                    m = 1
                    y += 1
            while True:
                try:
                    d = date(y, m, day)
                except ValueError:
                    pass
                else:
                    if d > end:
                        break
                    if d >= start:
                        occurrences.append(d)
                m += 1
                if m > 12:
                    m = 1
                    y += 1
                if y > end.year + 1:
                    break

        elif repeat_mode == "yearly":
            m, day = sched_start.month, sched_start.day
            y = max(sched_start.year, start.year)
            while True:
                try:
                    d = date(y, m, day)
                except ValueError:
                    y += 1
                    continue
                if d > end:
                    break
                if d >= start:
                    occurrences.append(d)
                y += 1
                if y > end.year + 1:
                    break

        overrides_by_date = read_occurrence_overrides()

        for d in occurrences:
            start_dt = datetime.combine(d, datetime.min.time().replace(hour=sh, minute=sm))
            end_dt = start_dt + timedelta(minutes=duration)
            event_id = f"recurring-{sid}-{d.isoformat()}"
            date_overrides = overrides_by_date.get(d.isoformat(), {})
            occurrence_override = date_overrides.get(event_id, {})
            events.append({
                "id": event_id,
                "start": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "end": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "text": title,
                "kind": schedule.get("kind", "reminder"),
                "description": schedule.get("description", ""),
                "reminder": schedule.get("reminder", "none"),
                "exec_mode": schedule.get("exec_mode", "manual"),
                "status": occurrence_override.get("status", "pending"),
                "locked": occurrence_override.get("locked", False),
                "readonly": True,
                "schedule_id": sid,
                "recurring": True,
            })

    return events


# ====== Data Layer ======

def daily_file(day: date) -> Path:
    """Get the JSON file path for a given date."""
    return DATA_DIR / f"{day.isoformat()}.json"


def read_day(day: date) -> list[dict]:
    """Read all events for a given day."""
    fp = daily_file(day)
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def write_day(day: date, events: list[dict]) -> None:
    """Write events for a given day."""
    fp = daily_file(day)
    fp.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


def timelog_file(day: date) -> Path:
    """Get the timelog JSON file path for a given date."""
    return TIMELOG_DIR / f"{day.isoformat()}.json"


def read_timelog(day: date) -> list[dict]:
    """Read timelog entries for a given day."""
    fp = timelog_file(day)
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def write_timelog_entry(entry: dict) -> None:
    """Append a timelog entry to today's timelog file."""
    today = date.today()
    fp = timelog_file(today)
    entries = read_timelog(today)
    entries.append(entry)
    fp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def all_timelog_in_range(start: date, end: date) -> list[dict]:
    """Read all timelog entries from start to end (inclusive)."""
    entries = []
    d = start
    while d <= end:
        entries.extend(read_timelog(d))
        d += timedelta(days=1)
    return entries


def calc_hourly_rate(timelog_entries: list[dict], events: list[dict]) -> dict:
    """Calculate hourly rate from timelog and event data.
    
    Returns dict with:
    - total_minutes: total tracked time
    - total_income: estimated income (from sop events with 'income' field)
    - hourly_rate: total_income / (total_minutes / 60)
    - by_sop: dict of sop_id -> {minutes, income, rate}
    """
    total_minutes = 0
    total_income = 0.0
    by_sop = {}
    
    for entry in timelog_entries:
        minutes = entry.get("duration_min", 0)
        sop_id = entry.get("sop_id", "unknown")
        # Estimate income from associated event (if available)
        income = entry.get("income", 0.0)
        
        total_minutes += minutes
        total_income += income
        
        if sop_id not in by_sop:
            by_sop[sop_id] = {"minutes": 0, "income": 0.0, "count": 0}
        by_sop[sop_id]["minutes"] += minutes
        by_sop[sop_id]["income"] += income
        by_sop[sop_id]["count"] += 1
    
    hourly_rate = 0.0
    if total_minutes > 0:
        hourly_rate = (total_income / (total_minutes / 60))
    
    return {
        "total_minutes": total_minutes,
        "total_income": total_income,
        "hourly_rate": round(hourly_rate, 2),
        "by_sop": by_sop,
    }


def all_events_in_range(start: date, end: date) -> list[dict]:
    """Read all events from start to end (inclusive)."""
    events = []
    d = start
    while d <= end:
        events.extend(read_day(d))
        d += timedelta(days=1)
    return events


# ====== SOP Loader ======

def load_sop(sop_id: str) -> Optional[dict]:
    """Load a SOP definition from data/sops/<sop_id>.json."""
    fp = SOPS_DIR / f"{sop_id}.json"
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def list_sops() -> list[dict]:
    """List all available SOPs."""
    results = []
    for fp in SOPS_DIR.glob("*.json"):
        try:
            sop = json.loads(fp.read_text(encoding="utf-8"))
            results.append(sop)
        except (json.JSONDecodeError, OSError):
            continue
    return results


# ====== Holiday & Solar Term (reuse from v0.2.0) ======

import urllib.request
import urllib.error
import ssl

def _normalize_holiday_data(data: dict) -> dict:
    """Normalize holiday API data to legacy format.
    Handles 3 input formats:
      1. Already normalized: {"holidays": [{"name":"元旦","date":"2026-01-01"},...]}
      2. timor.tech v2: {"code":0, "holiday":{"01-01":{...},...}}
      3. Old legacy:     {"2026-01-01": {"name":"元旦","isOffDay":true},...}
    Always returns: {"holidays": [...]}
    """
    # Already normalized — return as-is
    if "holidays" in data:
        return data

    # timor.tech v2 format: {"code":0, "holiday":{...}}
    if data.get("code") == 0 and isinstance(data.get("holiday"), dict):
        holidays_list = []
        for mmdd, info in data["holiday"].items():
            if info.get("holiday"):  # Only actual holidays, skip makeup workdays
                holidays_list.append({
                    "name": info.get("name", "节假日"),
                    "date": info.get("date", ""),
                })
        return {"holidays": holidays_list}

    # Old legacy format: {"2026-01-01": {"name":"元旦","isOffDay":true},...}
    holidays_list = []
    for date_str, info in data.items():
        if isinstance(info, dict) and info.get("isOffDay", True):
            holidays_list.append({
                "name": info.get("name", "节假日"),
                "date": date_str,
            })
    if holidays_list:
        return {"holidays": holidays_list}

    # Unknown format — return empty
    return {"holidays": []}


def _compute_lunar_holidays(year: int) -> dict:
    """Compute major lunar holidays using lunar-python (API fallback).
    Returns: {"holidays": [{"name":"春节","date":"2027-01-28"},...]}
    """
    try:
        from lunar_python import Lunar

        # Map: (lunar_month, lunar_day, name, display_name)
        LUNAR_HOLIDAYS = [
            (1, 1, "春节"),
            (1, 15, "元宵节"),
            (5, 5, "端午节"),
            (8, 15, "中秋节"),
            (9, 9, "重阳节"),
        ]

        holidays = []
        for lm, ld, name in LUNAR_HOLIDAYS:
            try:
                lunar = Lunar.fromYmd(year, lm, ld)
                solar = lunar.getSolar()
                date_str = f"{solar.getYear()}-{solar.getMonth():02d}-{solar.getDay():02d}"
                holidays.append({"name": name, "date": date_str})
            except Exception:
                pass

        if holidays:
            return {"holidays": holidays}
    except ImportError:
        pass

    return {"holidays": []}


_holiday_cache: dict[int, dict] = {}  # In-memory cache to avoid spamming the API


def fetch_holidays(year: int) -> dict:
    """Fetch Chinese holidays from timor.tech. Cached in memory per session."""
    # Hit memory cache — no disk I/O, no API call
    if year in _holiday_cache:
        return _holiday_cache[year]

    fp = DATA_DIR / f"holidays_{year}.json"
    if fp.exists():
        try:
            cached = json.loads(fp.read_text(encoding="utf-8"))
            normalized = _normalize_holiday_data(cached)
            if normalized.get("holidays"):
                _holiday_cache[year] = normalized
                return normalized
        except (json.JSONDecodeError, OSError):
            pass

    # API call — only once per year per session
    def _do_api_call():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = f"https://timor.tech/api/holiday/year/{year}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Rubedo-Calendar/1.0"
        })
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    last_error = None
    for attempt in (1, 2):
        try:
            data = _do_api_call()
            normalized = _normalize_holiday_data(data)
            # If API returns empty (e.g., 2027 not published yet), fall back to lunar
            if not normalized.get("holidays"):
                normalized = _compute_lunar_holidays(year)
            _holiday_cache[year] = normalized
            fp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
            return normalized
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 and attempt == 1:
                time.sleep(2)  # Rate limited, wait and retry once
                continue
            break
        except Exception as e:
            last_error = e
            break

    print(f"[WARN] Failed to fetch holidays for {year}: {last_error}")
    # Fall back to lunar computation on API failure
    fallback = _compute_lunar_holidays(year)
    if fallback.get("holidays"):
        _holiday_cache[year] = fallback
    return _holiday_cache.get(year, {"holidays": []})


SOLAR_TERMS_2025 = [
    ("小寒", "01-05"), ("大寒", "01-20"), ("立春", "02-03"), ("雨水", "02-18"),
    ("惊蛰", "03-05"), ("春分", "03-20"), ("清明", "04-04"), ("谷雨", "04-20"),
    ("立夏", "05-05"), ("小满", "05-21"), ("芒种", "06-05"), ("夏至", "06-21"),
    ("小暑", "07-07"), ("大暑", "07-22"), ("立秋", "08-07"), ("处暑", "08-23"),
    ("白露", "09-07"), ("秋分", "09-23"), ("寒露", "10-08"), ("霜降", "10-23"),
    ("立冬", "11-07"), ("小雪", "11-22"), ("大雪", "12-07"), ("冬至", "12-21"),
]

SHOPPING_FESTIVALS_2025 = [
    ("年货节", "01-06", "01-18"),
    ("情人节", "02-14", "02-14"),
    ("38女神节", "03-01", "03-08"),
    ("415家装节", "04-01", "04-15"),
    ("51劳动节", "05-01", "05-05"),
    ("520", "05-20", "05-20"),
    ("618大促", "06-01", "06-18"),
    ("88会员节", "08-08", "08-08"),
    ("818金石家博会", "08-10", "08-18"),
    ("99家装节", "09-01", "09-09"),
    ("教师节", "09-10", "09-10"),
    ("双11", "11-01", "11-11"),
    ("双12", "12-01", "12-12"),
    ("圣诞节", "12-25", "12-25"),
    ("年货节返场", "12-20", "12-31"),
]


def nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> Optional[date]:
    """Return the nth occurrence of a weekday in a given month.
    
    weekday: 0=Monday ... 6=Sunday (matches calendar module)
    nth: 1=first, 2=second, etc.
    Returns None if the month doesn't have that many occurrences.
    """
    cal = calendar.monthcalendar(year, month)
    count = 0
    for week in cal:
        if week[weekday] != 0:  # 0 means day belongs to adjacent month
            count += 1
            if count == nth:
                return date(year, month, week[weekday])
    return None


def get_all_festivals_for_year(year: int) -> list[tuple]:
    """Return unified list of (name, start_mmdd, end_mmdd) for all festivals.
    
    Combines static SHOPPING_FESTIVALS_2025 with dynamically computed dates
    (Mother's Day, Father's Day, 七夕). Single source of truth.
    """
    festivals = list(SHOPPING_FESTIVALS_2025)

    # Mother's Day — 5月第2个周日
    d = nth_weekday_of_month(year, 5, 6, 2)
    if d:
        festivals.append(("母亲节", d.strftime("%m-%d"), d.strftime("%m-%d")))

    # Father's Day — 6月第3个周日
    d = nth_weekday_of_month(year, 6, 6, 3)
    if d:
        festivals.append(("父亲节", d.strftime("%m-%d"), d.strftime("%m-%d")))

    # 七夕 — 农历七月初七，用 lunar-python 转换
    try:
        from lunar_python import Lunar
        lunar = Lunar.fromYmd(year, 7, 7)
        solar = lunar.getSolar()
        mmdd = f"{solar.getMonth():02d}-{solar.getDay():02d}"
        festivals.append(("七夕", mmdd, mmdd))
    except ImportError:
        print("[WARN] lunar-python not installed — 七夕 will not appear on calendar")
    except Exception as e:
        print(f"[ERROR] Failed to compute 七夕 date: {e}")

    return festivals


SEMESTER_RANGES = [
    ("寒假", "01-15", "02-28"), ("春季", "03-01", "06-30"),
    ("暑假", "07-01", "08-31"), ("秋季", "09-01", "12-31"),
]


def get_solar_term_overlays(target_date: date) -> list[str]:
    """Return solar term names that overlay the given date."""
    overlays = []
    for name, mmdd in SOLAR_TERMS_2025:
        m, d = int(mmdd[:2]), int(mmdd[3:])
        if target_date.month == m and target_date.day == d:
            overlays.append(name)
    return overlays


def get_shopping_festival_overlays(target_date: date) -> list[str]:
    """Return shopping festival names that overlay the given date."""
    overlays = []
    for name, start_mmdd, end_mmdd in get_all_festivals_for_year(target_date.year):
        start_m, start_d = int(start_mmdd[:2]), int(start_mmdd[3:])
        end_m, end_d     = int(end_mmdd[:2]), int(end_mmdd[3:])
        target_m, target_d = target_date.month, target_date.day
        if (start_m < end_m) or (start_m == end_m and start_d <= end_d):
            if start_m <= target_m <= end_m:
                t = target_d if target_m == start_m else 99
                s = start_d if target_m == start_m else 1
                e = end_d if target_m == end_m else 99
                if s <= t <= e:
                    overlays.append(name)
        else:
            if target_m >= start_m or target_m <= end_m:
                overlays.append(name)
    return overlays


def get_semester_overlays(target_date: date) -> list[str]:
    """Return semester names that overlay the given date."""
    overlays = []
    month = target_date.month
    for name, start_mmdd, end_mmdd in SEMESTER_RANGES:
        start_m, _ = int(start_mmdd[:2]), int(start_mmdd[3:])
        end_m, _   = int(end_mmdd[:2]), int(end_mmdd[3:])
        if start_m <= month <= end_m:
            overlays.append(name)
    return overlays


def generate_overlay_events(start: date, end: date) -> list[dict]:
    """生成只读叠加层事件（节气/购物节/法定节假日/学期）"""
    overlay_events = []
    year = start.year

    # 1. 节气 — 节气日期每年基本固定（±1-2天），直接用2025年数据
    solar_terms = SOLAR_TERMS_2025
    for name, mmdd in solar_terms:
        m, d = int(mmdd[:2]), int(mmdd[3:])
        try:
            term_date = date(year, m, d)
            if start <= term_date <= end:
                overlay_events.append({
                    "id": f"overlay-solar-{term_date.isoformat()}",
                    "start": term_date.isoformat() + "T00:00:00",
                    "end": term_date.isoformat() + "T23:59:59",
                    "text": f"🌿{name}",
                    "backColor": "#FF9800",
                    "barColor": "#F57C00",
                    "kind": "overlay-solar",
                    "readonly": True,
                })
        except ValueError:
            pass

    # 2. 购物节 — 包含固定日期 + 动态节日
    shopping_fests = get_all_festivals_for_year(year)
    for name, start_mmdd, end_mmdd in shopping_fests:
        sm, sd = int(start_mmdd[:2]), int(start_mmdd[3:])
        em, ed = int(end_mmdd[:2]), int(end_mmdd[3:])
        try:
            fest_start = date(year, sm, sd)
            fest_end = date(year, em, ed)
            d = fest_start
            while d <= fest_end and d <= end:
                if d >= start:
                    overlay_events.append({
                        "id": f"overlay-fest-{name}-{d.isoformat()}",
                        "start": d.isoformat() + "T00:00:00",
                        "end": d.isoformat() + "T23:59:59",
                        "text": f"🛒{name}",
                        "backColor": "#E91E63",
                        "barColor": "#C2185B",
                        "kind": "overlay-fest",
                        "readonly": True,
                    })
                d += timedelta(days=1)
        except ValueError:
            pass

    # 3. 法定节假日 — 从 holidays_YYYY.json
    holiday_data = fetch_holidays(year)
    if holiday_data and "holidays" in holiday_data:
        for h in holiday_data["holidays"]:
            h_date_str = h.get("date", "")
            if not h_date_str:
                continue
            try:
                h_date = date.fromisoformat(h_date_str)
                if start <= h_date <= end:
                    overlay_events.append({
                        "id": f"overlay-holiday-{h_date_str}",
                        "start": h_date_str + "T00:00:00",
                        "end": h_date_str + "T23:59:59",
                        "text": f"🎌{h.get('name', '节假日')}",
                        "backColor": "#F44336",
                        "barColor": "#D32F2F",
                        "kind": "overlay-holiday",
                        "readonly": True,
                    })
            except (ValueError, TypeError):
                pass

    # 4. 学期 — 开学第一天全天事件（直接用 2025 年数据）
    semesters = SEMESTER_RANGES
    for name, start_mmdd, end_mmdd in semesters:
        sm = int(start_mmdd[:2])
        sd = int(start_mmdd[3:])
        em = int(end_mmdd[:2])
        ed = int(end_mmdd[3:])
        try:
            sem_start = date(year, sm, sd)
            if start <= sem_start <= end:
                overlay_events.append({
                    "id": f"overlay-sem-{name}-{sem_start.isoformat()}",
                    "start": sem_start.isoformat() + "T00:00:00",
                    "end": sem_start.isoformat() + "T23:59:59",
                    "text": f"📚{name}",
                    "backColor": "#9C27B0",
                    "barColor": "#7B1FA2",
                    "kind": "overlay-sem",
                    "readonly": True,
                })
        except ValueError:
            pass

    # 5. 自定义节假日 — 从 data/custom_holidays.json 读取
    try:
        custom_file = DATA_DIR / "custom_holidays.json"
        if custom_file.exists():
            with open(custom_file, "r", encoding="utf-8") as f:
                custom_holidays = json.load(f)
            for h in custom_holidays:
                h_date_str = h.get("date", "")
                h_name = h.get("name", "自定义节假日")
                if not h_date_str:
                    continue
                try:
                    h_date = date.fromisoformat(h_date_str)
                    if start <= h_date <= end:
                        overlay_events.append({
                            "id": f"overlay-custom-{h_date_str}",
                            "start": h_date_str + "T00:00:00",
                            "end": h_date_str + "T23:59:59",
                            "text": f"⭐{h_name}",
                            "backColor": "#00BCD4",
                            "barColor": "#0097A7",
                            "kind": "overlay-custom",
                            "readonly": True,
                        })
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    return overlay_events


# ====== APScheduler ======
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.jobstores.base import JobLookupError

_scheduler = None

def get_scheduler():
    """Get or create the global scheduler (lazy init)."""
    global _scheduler
    if _scheduler is None:
        db_path = DATA_DIR / "apscheduler.db"
        _scheduler = AsyncIOScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")},
        )
    return _scheduler


# ====== Routes ======

@ui.page("/")
def index():
    """Main calendar page (DayPilot week view)."""
    # ---- CSS ----
    ui.add_head_html('<link href="/static/daypilot-theme.css" rel="stylesheet">')

    # ---- Page-specific CSS ----
    ui.add_head_html("""
    <style>
        html, body {
            margin:0; padding:0;
            font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
            background: #1a1a2e;
            color: #eee;
            height: 100%;
            overflow: hidden;
        }
        #calendar {
            width: calc(100% - 32px);
            height: calc(100vh - 120px);
            margin: 16px;
        }
        .nav-bar {
            display: flex; align-items: center; gap: 12px;
            padding: 8px 16px;
            background: #16213e;
            border-bottom: 1px solid #0f3460;
        }
        .nav-bar button {
            background: #0f3460; color: #e94560;
            border: 1px solid #e94560; border-radius: 6px;
            padding: 6px 16px; cursor: pointer; font-size: 14px;
        }
        .nav-bar button:hover {
            background: #e94560; color: #fff;
        }
        .nav-bar .title {
            font-size: 18px; font-weight: bold; color: #e94560;
        }
        #week-range {
            color: #aaa; font-size: 14px; margin-left: 12px;
        }
        .empty-guide {
            display: none;
            position: absolute; top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            text-align: center; color: #888;
            z-index: 10; pointer-events: none;
        }
        .empty-guide .icon { font-size: 48px; margin-bottom: 12px; }
        .empty-guide .title { font-size: 18px; margin-bottom: 8px; color: #aaa; }
        .empty-guide .hint { font-size: 13px; line-height: 1.8; }
    </style>
    """)

    # ---- JS: dayjs + DayPilot ----
    ui.add_head_html('<script src="/static/dayjs.min.js"></script>')
    ui.add_head_html('<script src="/static/daypilot-all.min.js"></script>')

    # ---- Navigation bar (pure HTML, works inside DayPilot page) ----
    ui.html("""<div class="nav-bar">
        <span class="title">凝华 · Rubedo</span>
        <span id="week-range"></span>
        <button onclick="navWeek(-1)">← 上周</button>
        <button onclick="navToday()">今天</button>
        <button onclick="navWeek(1)">下周 →</button>
        <button onclick="showSettings()" style="margin-left:auto;">设置</button>
        <button onclick="window.open('/audit', '_self')">审计</button>
    </div>""", sanitize=False)

    # ---- Calendar container ----
    ui.html('<div id="calendar"></div>')

    # ---- Empty guide ----
    ui.html("""
    <div id="empty-guide" class="empty-guide" style="display:block !important;">
        <div class="icon">&#128197;</div>
        <div class="title">空空如也，等待你的第一个计划</div>
        <div class="hint">
            在日历上拖选时间段来创建新事项<br>
            点击事项查看详情<br>
            右键事项可快速标记完成、编辑或删除<br>
            试试创建你的第一条待办吧！
        </div>
    </div>
    """)

    # ---- DayPilot init ----

    ui.add_body_html(f'<script src="/static/init.js?v={int(__import__("time").time())}"></script>')


# ====== API Routes ======

@app.post("/api/events/create")
async def api_create_event(request: Request):
    """Create a new event."""
    try:
        data = await request.json()
        day = date.fromisoformat(data["start"][:10])
        events = read_day(day)
        new_id = str(uuid4())
        event = {
            "id":          new_id,
            "text":        data.get("text", ""),
            "start":       data["start"],
            "end":         data["end"],
            "kind":        data.get("kind", "reminder"),
            "description": data.get("description", ""),
            "reminder":    data.get("reminder", "none"),
            "exec_mode":   data.get("exec_mode", "manual"),
            "status":      "pending",
            "locked":      False,
        }
        events.append(event)
        write_day(day, events)
        return {"ok": True, "id": new_id, "event": event}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.put("/api/events/update")
async def api_update_event(request: Request):
    """Update an existing event (text, kind, exec_mode)."""
    try:
        data = await request.json()
        day = date.fromisoformat(data["day"])
        events = read_day(day)
        for ev in events:
            if ev["id"] == data["id"]:
                if "text" in data:
                    ev["text"] = data["text"]
                if "kind" in data:
                    ev["kind"] = data["kind"]
                if "exec_mode" in data:
                    ev["exec_mode"] = data["exec_mode"]
                if "description" in data:
                    ev["description"] = data["description"]
                if "reminder" in data:
                    ev["reminder"] = data["reminder"]
                break
        write_day(day, events)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/events")
async def api_list_events(request: Request):
    """List events in a date range."""
    try:
        start_str = request.query_params.get("start", "")
        end_str   = request.query_params.get("end", "")
        if not start_str or not end_str:
            return []
        start = date.fromisoformat(start_str)
        end   = date.fromisoformat(end_str)
        events = all_events_in_range(start, end)
        # Expand preheat schedules
        preheat_events = expand_preheat_schedules(start, end)
        events.extend(preheat_events)
        # Expand recurring schedules (daily/weekly/monthly/yearly)
        recurring_events = expand_recurring_schedules(start, end)
        events.extend(recurring_events)
        return events
    except Exception:
        return []


@app.post("/api/events/status")
async def api_update_status(request: Request):
    """Update event status (done/skipped)."""
    try:
        data  = await request.json()
        day   = date.fromisoformat(data["day"])
        events = read_day(day)
        for ev in events:
            if ev["id"] == data["id"]:
                ev["status"] = data["status"]
                break
        write_day(day, events)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/events/move")
async def api_move_event(request: Request):
    """Move an event to a new time."""
    try:
        data    = await request.json()
        old_day = date.fromisoformat(data["old_day"])
        events  = read_day(old_day)
        moved   = None
        for i, ev in enumerate(events):
            if ev["id"] == data["old_id"]:
                moved = events.pop(i)
                break
        if moved:
            moved["start"] = data["event"]["start"]
            moved["end"]   = data["event"]["end"]
            new_day = date.fromisoformat(moved["start"][:10])
            write_day(old_day, events)
            new_events = read_day(new_day)
            new_events.append(moved)
            write_day(new_day, new_events)
        return {"ok": True, "event": moved}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/events/delete")
async def api_delete_event(request: Request):
    """Delete an event."""
    try:
        data  = await request.json()
        day   = date.fromisoformat(data["day"])
        events = read_day(day)
        events = [ev for ev in events if ev["id"] != data["id"]]
        write_day(day, events)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/events/lock")
async def api_lock_event(request: Request):
    """Lock/unlock an event."""
    try:
        data  = await request.json()
        day   = date.fromisoformat(data["day"])
        events = read_day(day)
        for ev in events:
            if ev["id"] == data["id"]:
                ev["locked"] = data.get("locked", False)
                break
        write_day(day, events)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/cell-backgrounds")
async def api_cell_backgrounds(request: Request):
    """Return special dates as cell background colors.
    Each date supports multiple festivals (priority-sorted).
    Returns {dates: {"YYYY-MM-DD": {color, text, tooltip, type}, ...}}
    """
    # Priority: lower = higher priority
    PRIORITY = {"custom": 1, "holiday": 2, "fest": 3, "solar": 4, "sem": 5}
    COLORS   = {"custom": "#B2DFDB", "holiday": "#BBDEFB", "fest": "#DCEDC8", "solar": "", "sem": ""}

    try:
        start_str = request.query_params.get("start", "")
        end_str   = request.query_params.get("end", "")
        if not start_str or not end_str:
            return {"dates": {}}
        start = date.fromisoformat(start_str)
        end   = date.fromisoformat(end_str)
        year  = start.year
        raw   = {}  # {date_str: [(priority, color, text, type), ...]}

        def add(ds, ptype, text):
            if ds not in raw:
                raw[ds] = []
            raw[ds].append((PRIORITY[ptype], COLORS[ptype], text, ptype))

        # 1. 节气
        for name, mmdd in SOLAR_TERMS_2025:
            m, d = int(mmdd[:2]), int(mmdd[3:])
            try:
                term_date = date(year, m, d)
                if start <= term_date <= end:
                    add(term_date.isoformat(), "solar", f"\U0001F33F {name}")
            except ValueError:
                pass

        # 2. 购物节/特殊日
        for name, s_mmdd, e_mmdd in get_all_festivals_for_year(year):
            sm, sd = int(s_mmdd[:2]), int(s_mmdd[3:])
            em, ed = int(e_mmdd[:2]), int(e_mmdd[3:])
            try:
                d = max(date(year, sm, sd), start)
                while d <= date(year, em, ed) and d <= end:
                    ds = d.isoformat()
                    add(ds, "fest", f"\U0001F6D2 {name}")
                    d += timedelta(days=1)
            except ValueError:
                pass

        # 3. 法定节假日
        holiday_data = fetch_holidays(year)
        if holiday_data and "holidays" in holiday_data:
            for h in holiday_data["holidays"]:
                h_date_str = h.get("date", "")
                if not h_date_str:
                    continue
                try:
                    h_date = date.fromisoformat(h_date_str)
                    if start <= h_date <= end:
                        add(h_date_str, "holiday", f"\U0001F38C {h.get('name', '节假日')}")
                except (ValueError, TypeError):
                    pass

        # 4. 学期
        for name, s_mmdd, e_mmdd in SEMESTER_RANGES:
            sm, sd = int(s_mmdd[:2]), int(s_mmdd[3:])
            em, ed = int(e_mmdd[:2]), int(e_mmdd[3:])
            d = start
            while d <= end:
                try:
                    sem_start = date(d.year, sm, sd)
                    sem_end   = date(d.year, em, ed)
                except ValueError:
                    d += timedelta(days=1)
                    continue
                if sem_start <= d <= sem_end:
                    add(d.isoformat(), "sem", f"\U0001F4DA {name}")
                d += timedelta(days=1)

        # 5. 自定义重要日子（最高优先级）
        custom_file = DATA_DIR / "custom_holidays.json"
        if custom_file.exists():
            try:
                with open(custom_file, "r", encoding="utf-8") as f:
                    custom_holidays = json.load(f)
                for h in custom_holidays:
                    h_date_str = h.get("date", "")
                    h_name = h.get("name", "自定义")
                    if not h_date_str:
                        continue
                    try:
                        h_date = date.fromisoformat(h_date_str)
                        if start <= h_date <= end:
                            add(h_date_str, "custom", f"\U0001F4C5 {h_name}")
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass

        # Merge: sort by priority, take top for color/text, all for tooltip
        dates = {}
        for ds, entries in raw.items():
            entries.sort(key=lambda x: x[0])  # Sort by priority (lower=higher)
            top_priority, top_color, top_text, top_type = entries[0]
            all_texts = [e[2] for e in entries]
            dates[ds] = {
                "color": top_color,
                "text": top_text,
                "tooltip": "\n".join(all_texts),
                "type": top_type,
            }

        return {"dates": dates}
    except Exception:
        return {"dates": {}}


@app.post("/api/timelog/write")
async def api_write_timelog(request: Request):
    """Write a timelog entry."""
    try:
        data = await request.json()
        entry = {
            "id": data.get("id", str(uuid4())),
            "sop_id": data.get("sop_id", "unknown"),
            "sop_name": data.get("sop_name", ""),
            "step_name": data.get("step_name", ""),
            "start_time": data.get("start_time", ""),
            "end_time": data.get("end_time", ""),
            "duration_min": data.get("duration_min", 0),
            "income": data.get("income", 0.0),
            "note": data.get("note", ""),
            "created_at": datetime.now().isoformat(),
        }
        write_timelog_entry(entry)
        return {"ok": True, "entry": entry}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/timelog/report")
async def api_timelog_report(request: Request):
    """Generate a time audit report for a date range."""
    try:
        start_str = request.query_params.get("start", date.today().replace(day=1).isoformat())
        end_str = request.query_params.get("end", date.today().isoformat())
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        
        entries = all_timelog_in_range(start, end)
        events = all_events_in_range(start, end)
        
        # Calculate stats
        stats = calc_hourly_rate(entries, events)
        
        # Add date range info
        stats["start"] = start_str
        stats["end"] = end_str
        stats["entries_count"] = len(entries)
        
        return {"ok": True, "stats": stats, "entries": entries}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- Custom holidays API (top-level) ----
CUSTOM_HOLIDAYS_FILE = DATA_DIR / "custom_holidays.json"

@app.get("/api/custom-holidays")
async def api_list_custom_holidays():
    """List all custom holidays."""
    try:
        if CUSTOM_HOLIDAYS_FILE.exists():
            with open(CUSTOM_HOLIDAYS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"ok": True, "holidays": data}
        return {"ok": True, "holidays": []}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/custom-holidays")
async def api_add_custom_holiday(request: Request):
    """Add a custom holiday."""
    try:
        data = await request.json()
        name = data.get("name", "").strip()
        date_str = data.get("date", "").strip()
        if not name or not date_str:
            return {"ok": False, "error": "名称和日期不能为空"}
        # Validate date
        from datetime import datetime as dt
        dt.strptime(date_str, "%Y-%m-%d")
        holidays = []
        if CUSTOM_HOLIDAYS_FILE.exists():
            with open(CUSTOM_HOLIDAYS_FILE, "r", encoding="utf-8") as f:
                holidays = json.load(f)
        holidays.append({"name": name, "date": date_str})
        with open(CUSTOM_HOLIDAYS_FILE, "w", encoding="utf-8") as f:
            json.dump(holidays, f, ensure_ascii=False, indent=2)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.delete("/api/custom-holidays")
async def api_delete_custom_holiday(request: Request):
    """Delete a custom holiday by name and date."""
    try:
        data = await request.json()
        name = data.get("name", "")
        date_str = data.get("date", "")
        if not name or not date_str:
            return {"ok": False, "error": "参数不完整"}
        holidays = []
        if CUSTOM_HOLIDAYS_FILE.exists():
            with open(CUSTOM_HOLIDAYS_FILE, "r", encoding="utf-8") as f:
                holidays = json.load(f)
        holidays = [h for h in holidays if not (h["name"] == name and h["date"] == date_str)]
        with open(CUSTOM_HOLIDAYS_FILE, "w", encoding="utf-8") as f:
            json.dump(holidays, f, ensure_ascii=False, indent=2)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ====== Schedules API (重复事件模板) ======

@app.get("/api/schedules")
async def api_list_schedules():
    """List all schedule templates."""
    try:
        schedules = read_schedules()
        return {"ok": True, "schedules": schedules}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/schedules")
async def api_create_schedule(request: Request):
    """Create a new schedule template."""
    try:
        data = await request.json()
        schedules = read_schedules()
        new_id = f"schedule-{uuid4().hex[:8]}"
        schedule = {
            "id": new_id,
            "title": data.get("title", ""),
            "repeat_mode": data.get("repeat_mode", "preheat"),
            "target_type": data.get("target_type", ""),
            "target_id": data.get("target_id", ""),
            "target_date": data.get("target_date", ""),
            "target_name": data.get("target_name", ""),
            "preheat_days": data.get("preheat_days", 7),
            "start_date": data.get("start_date", ""),
            "start_time": data.get("start_time", "09:00"),
            "duration_minutes": data.get("duration_minutes", 60),
            "kind": data.get("kind", "reminder"),
            "sop_page": data.get("sop_page", ""),
            "description": data.get("description", ""),
            "reminder": data.get("reminder", "none"),
            "exec_mode": data.get("exec_mode", "manual"),
            "scope": data.get("scope", "yearly"),
            "year": data.get("year", 0),
            "enabled": True,
        }
        schedules.append(schedule)
        write_schedules(schedules)
        return {"ok": True, "id": new_id, "schedule": schedule}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.put("/api/schedules/{schedule_id}")
async def api_update_schedule(schedule_id: str, request: Request):
    """Update a schedule template."""
    try:
        data = await request.json()
        schedules = read_schedules()
        for sch in schedules:
            if sch["id"] == schedule_id:
                if "title" in data:
                    sch["title"] = data["title"]
                if "repeat_mode" in data:
                    sch["repeat_mode"] = data["repeat_mode"]
                if "target_type" in data:
                    sch["target_type"] = data["target_type"]
                if "target_id" in data:
                    sch["target_id"] = data["target_id"]
                if "target_date" in data:
                    sch["target_date"] = data["target_date"]
                if "target_name" in data:
                    sch["target_name"] = data["target_name"]
                if "preheat_days" in data:
                    sch["preheat_days"] = data["preheat_days"]
                if "start_time" in data:
                    sch["start_time"] = data["start_time"]
                if "duration_minutes" in data:
                    sch["duration_minutes"] = data["duration_minutes"]
                if "kind" in data:
                    sch["kind"] = data["kind"]
                if "sop_page" in data:
                    sch["sop_page"] = data["sop_page"]
                if "description" in data:
                    sch["description"] = data["description"]
                if "reminder" in data:
                    sch["reminder"] = data["reminder"]
                if "exec_mode" in data:
                    sch["exec_mode"] = data["exec_mode"]
                if "scope" in data:
                    sch["scope"] = data["scope"]
                if "year" in data:
                    sch["year"] = data["year"]
                if "enabled" in data:
                    sch["enabled"] = data["enabled"]
                break
        write_schedules(schedules)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.delete("/api/schedules/{schedule_id}")
async def api_delete_schedule(schedule_id: str):
    """Delete a schedule template."""
    try:
        schedules = read_schedules()
        schedules = [s for s in schedules if s["id"] != schedule_id]
        write_schedules(schedules)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/schedules/{schedule_id}")
async def api_get_schedule(schedule_id: str):
    """Get a single schedule template."""
    try:
        schedules = read_schedules()
        for sch in schedules:
            if sch["id"] == schedule_id:
                return {"ok": True, "schedule": sch}
        return {"ok": False, "error": "Schedule not found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/schedules/{schedule_id}/occurrence-status")
async def api_set_occurrence_status(schedule_id: str, request: Request):
    """Set completion status for a recurring event occurrence."""
    try:
        data = await request.json()
        date_str = data.get("date", "")
        status = data.get("status", "pending")
        event_id = data.get("id", f"recurring-{schedule_id}-{date_str}")
        write_occurrence_override(date_str, event_id, status=status)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/schedules/{schedule_id}/occurrence-lock")
async def api_set_occurrence_lock(schedule_id: str, request: Request):
    """Set lock status for a recurring event occurrence."""
    try:
        data = await request.json()
        date_str = data.get("date", "")
        locked = data.get("locked", False)
        event_id = data.get("id", f"recurring-{schedule_id}-{date_str}")
        write_occurrence_override(date_str, event_id, locked=locked)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/special-days")
async def api_list_special_days(request: Request):
    """List all special days (shopping festivals, holidays, custom holidays) for a year."""
    try:
        year_str = request.query_params.get("year", str(date.today().year))
        year = int(year_str)
        special_days = get_special_days(year)
        return {"ok": True, "special_days": special_days}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@ui.page("/sop/{sop_id}")
def sop_page(sop_id: str):
    """Render a SOP page with timed steps."""
    sop = load_sop(sop_id)
    if not sop:
        ui.label(f"SOP 未找到: {sop_id}")
        return

    # Inject timer JavaScript
    timer_js = """
    <script>
    (function() {
        let timerStart = null;
        let timerStep = null;
        let timerSopId = null;
        let timerSopName = null;
        
        window.startRubedTimer = function(stepName, sopId, sopName) {
            if (timerStart) {
                alert("已有计时器在运行！");
                return;
            }
            timerStart = Date.now();
            timerStep = stepName;
            timerSopId = sopId;
            timerSopName = sopName;
            
            // Update button states
            document.querySelectorAll('[data-timer-btn]').forEach(function(btn) {
                if (btn.dataset.stepName === stepName) {
                    btn.textContent = "结束计时";
                    btn.style.background = "#F44336";
                }
            });
            
            // Show timer status
            let status = document.getElementById('timer-status');
            if (!status) {
                status = document.createElement('div');
                status.id = 'timer-status';
                document.querySelector('.q-page').appendChild(status);
            }
            status.style.cssText = 'position:fixed;top:10px;right:10px;background:#4CAF50;color:#fff;padding:8px 16px;border-radius:8px;z-index:9999;font-size:13px;';
            status.textContent = '⏱ ' + stepName + ' 计时中...';
            
            console.log('[Rubedo] Timer started:', stepName);
        };
        
        window.stopRubedTimer = function() {
            if (!timerStart) return null;
            
            let endTime = Date.now();
            let durationMs = endTime - timerStart;
            let durationMin = Math.round(durationMs / 60000);
            
            let result = {
                step_name: timerStep,
                sop_id: timerSopId,
                sop_name: timerSopName,
                start_time: new Date(timerStart).toISOString(),
                end_time: new Date(endTime).toISOString(),
                duration_min: durationMin,
            };
            
            // Reset timer
            timerStart = null;
            timerStep = null;
            
            // Reset buttons
            document.querySelectorAll('[data-timer-btn]').forEach(function(btn) {
                btn.textContent = "开始计时";
                btn.style.background = "";
            });
            
            // Remove status
            let status = document.getElementById('timer-status');
            if (status) status.remove();
            
            return result;
        };
        
        window.getTimerState = function() {
            return { running: timerStart !== null, step: timerStep };
        };
    })();
    </script>
    """
    ui.add_head_html(timer_js)
    
    ui.label(sop["name"]).classes("text-2xl font-bold text-white")
    ui.label(sop.get("desc", "")).classes("text-gray-400")
    
    steps_container = ui.column().classes("w-full gap-4 mt-4")
    
    def render_steps():
        steps_container.clear()
        for step in sop.get("steps", []):
            with steps_container:
                with ui.card().classes("w-full p-4 bg-gray-800"):
                    ui.label(step["name"]).classes("text-lg font-bold text-white")
                    ui.label(step.get("desc", "")).classes("text-sm text-gray-400")
                    if step.get("est_min", 0) > 0:
                        ui.label(f"预估: {step['est_min']} min").classes("text-xs text-yellow-400")
                    # Timer buttons (working)
                    if step.get("exec_mode") == "manual" and step.get("est_min", 0) > 0:
                        # Use HTML button with JS handler for timer
                        btn_html = f'<button data-timer-btn="1" data-step-name="{step["name"]}" onclick="window.handleTimerClick(this, \'{step["name"]}\', \'{sop_id}\', \'{sop["name"]}\')" style="padding:8px 16px;background:#e94560;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:13px;">开始计时</button>'
                        ui.html(btn_html, sanitize=False)
    
    # Add global JS handler for timer buttons
    handler_js = """
    <script>
    window.handleTimerClick = function(btn, stepName, sopId, sopName) {
        if (btn.textContent === "开始计时") {
            window.startRubedTimer(stepName, sopId, sopName);
        } else {
            let result = window.stopRubedTimer();
            if (result) {
                let income = prompt("本次收入（元，留空为0）：", "0");
                income = parseFloat(income) || 0;
                let note = prompt("备注（可选）：", "") || "";
                
                let entry = {
                    sop_id: result.sop_id,
                    sop_name: result.sop_name,
                    step_name: result.step_name,
                    start_time: result.start_time,
                    end_time: result.end_time,
                    duration_min: result.duration_min,
                    income: income,
                    note: note,
                };
                
                fetch("/api/timelog/write", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(entry)
                }).then(function(r) { return r.json(); }).then(function(data) {
                    if (data.ok) {
                        alert("✅ 计时已记录：" + result.duration_min + " 分钟");
                    } else {
                        alert("❌ 记录失败：" + (data.error || "未知错误"));
                    }
                });
            }
        }
    };
    </script>
    """
    ui.add_head_html(handler_js)
    
    render_steps()


# ====== Audit Page ======

@ui.page("/audit")
def audit_page():
    """Time audit page — shows hourly rate and time breakdown."""
    ui.label("⏱ 时间审计").classes("text-2xl font-bold text-white")
    ui.label("查看你的时薪和时间分配").classes("text-gray-400 mb-4")

    # Date range inputs
    today = date.today()
    first_day = today.replace(day=1)
    last_day = (first_day.replace(month=first_day.month % 12 + 1, day=1) - timedelta(days=1)) if first_day.month < 12 else first_day.replace(year=first_day.year + 1, month=1, day=1) - timedelta(days=1)

    start_input = ui.date_input("开始日期", value=first_day)
    end_input = ui.date_input("结束日期", value=last_day)

    report_container = ui.column().classes("w-full gap-4 mt-4")

    def generate_report():
        """Generate report for the selected date range."""
        try:
            start = date.fromisoformat(start_input.value)
            end = date.fromisoformat(end_input.value)
        except (ValueError, TypeError):
            ui.notify("日期格式错误", type="negative")
            return

        report_container.clear()
        with report_container:
            ui.label("计算中...").classes("text-gray-400")

        # Read data and calculate
        entries = all_timelog_in_range(start, end)
        events = all_events_in_range(start, end)
        stats = calc_hourly_rate(entries, events)

        # Display results
        report_container.clear()
        with report_container:
            if stats["total_minutes"] == 0:
                ui.label("该时间段没有时间记录。").classes("text-gray-400 text-lg")
                ui.label("去 SOP 页面点「开始计时」来记录时间。").classes("text-gray-500")
                return

            # Summary cards
            with ui.row().classes("gap-4 w-full"):
                with ui.card().classes("flex-1 p-4 bg-gray-800"):
                    ui.label("总时长").classes("text-sm text-gray-400")
                    ui.label(f"{stats['total_minutes']} 分钟").classes("text-2xl font-bold text-white")
                with ui.card().classes("flex-1 p-4 bg-gray-800"):
                    ui.label("总收入").classes("text-sm text-gray-400")
                    ui.label(f"¥{stats['total_income']:.2f}").classes("text-2xl font-bold text-green-400")
                with ui.card().classes("flex-1 p-4 bg-gray-800"):
                    ui.label("时薪").classes("text-sm text-gray-400")
                    ui.label(f"¥{stats['hourly_rate']:.2f}/小时").classes("text-2xl font-bold text-yellow-400")

            # By SOP breakdown
            if stats.get("by_sop"):
                ui.label("按 SOP 统计").classes("text-lg font-bold text-white mt-4")
                for sop_id, sop_stats in stats["by_sop"].items():
                    with ui.card().classes("w-full p-3 bg-gray-700"):
                        with ui.row().classes("justify-between"):
                            ui.label(sop_id).classes("text-white font-bold")
                            ui.label(f"{sop_stats['minutes']} 分钟 / ¥{sop_stats['income']:.2f}").classes("text-gray-300")

            # Recent entries
            if entries:
                ui.label("最近记录").classes("text-lg font-bold text-white mt-4")
                for entry in entries[-10:]:
                    with ui.card().classes("w-full p-2 bg-gray-800"):
                        with ui.row().classes("justify-between"):
                            ui.label(entry.get("step_name", "")).classes("text-white")
                            ui.label(f"{entry.get('duration_min', 0)} 分钟").classes("text-gray-400")
                        if entry.get("note"):
                            ui.label(entry["note"]).classes("text-xs text-gray-500")

    ui.button("生成报告", on_click=lambda: generate_report()).classes("mt-2")

    # Generate report on page load
    generate_report()


# ====== Startup / Shutdown ======

def on_startup():
    """Runs when the NiceGUI app starts."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        print("[Rubedo] APScheduler 已启动 (SQLite 持久化)")

    # 后台获取节假日数据（当前年 + 明年，间隔2秒避免限流）
    import threading
    def _fetch_holidays_bg():
        from datetime import datetime
        current_year = datetime.now().year
        for yr in (current_year, current_year + 1):
            try:
                data = fetch_holidays(yr)
                if data and data.get("holidays"):
                    print(f"[Rubedo] 节假日数据已获取 ({yr}年, {len(data['holidays'])}天)")
                else:
                    print(f"[Rubedo] 节假日数据为空 ({yr}年)")
            except Exception as e:
                print(f"[Rubedo] 节假日获取异常 ({yr}年): {e}")
            if yr < current_year + 1:
                time.sleep(1.5)  # 间隔防限流

    t = threading.Thread(target=_fetch_holidays_bg, daemon=True)
    t.start()


def on_shutdown():
    """Runs when the NiceGUI app stops."""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown()
        print("[Rubedo] APScheduler 已关闭")


app.on_startup(on_startup)
app.on_shutdown(on_shutdown)


# ====== Main ======
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title      = "凝华 v0704-fix7",
        native     = True,
        window_size = (1400, 900),
        port       = 8081,
        reload     = False,
        show       = True,
    )
