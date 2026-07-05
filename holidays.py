"""
Rubedo · 凝华 — 节假日计算模块
包含：节假日获取、特殊叠加层计算
"""

import calendar
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from utils import DATA_DIR, read_schedules

# ====== Holiday Files ======
HOLIDAYS_DIR = DATA_DIR / "holidays"
HOLIDAYS_DIR.mkdir(parents=True, exist_ok=True)

# ====== Constants ======
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

SEMESTER_RANGES = [
    ("寒假", "01-15", "02-28"), ("春季", "03-01", "06-30"),
    ("暑假", "07-01", "08-31"), ("秋季", "09-01", "12-31"),
]

# ====== Helper Functions ======
_holiday_cache: dict[int, dict] = {}  # In-memory cache to avoid spamming the API

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
