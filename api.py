"""
Rubedo · 凝华 — API 路由模块
包含：全部 API 路由处理函数
从 app.py 重构拆分（2026-07-05）
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

from starlette.requests import Request

from utils import *
from holidays import *


# ====== Event API Routes ======

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


async def api_update_event(request: Request):
    """Update an existing event (text, kind, exec_mode, time, etc.)."""
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
                # 时间字段（普通事件）
                if "start" in data and "end" in data:
                    ev["start"] = data["start"]
                    ev["end"]   = data["end"]
                break
        write_day(day, events)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
        preheat_events = expand_preheat_schedules(start, end)
        events.extend(preheat_events)
        recurring_events = expand_recurring_schedules(start, end)
        events.extend(recurring_events)
        return events
    except Exception:
        return []


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


# ====== Cell Backgrounds API ======

async def api_cell_backgrounds(request: Request):
    """Return special dates as cell background colors."""
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
        raw   = {}

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

        # 5. 自定义重要日子
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

        dates = {}
        for ds, entries in raw.items():
            entries.sort(key=lambda x: x[0])
            top_priority, top_color, top_text, top_type = entries[0]
            all_texts = [e[2] for e in entries]
            dates[ds] = {
                "color":   top_color,
                "text":    top_text,
                "tooltip": "\n".join(all_texts),
                "type":    top_type,
            }

        return {"dates": dates}
    except Exception:
        return {"dates": {}}


# ====== Timelog API ======

async def api_write_timelog(request: Request):
    """Write a timelog entry."""
    try:
        data = await request.json()
        entry = {
            "id":         data.get("id", str(uuid4())),
            "sop_id":     data.get("sop_id", "unknown"),
            "sop_name":   data.get("sop_name", ""),
            "step_name":   data.get("step_name", ""),
            "start_time":  data.get("start_time", ""),
            "end_time":    data.get("end_time", ""),
            "duration_min": data.get("duration_min", 0),
            "income":      data.get("income", 0.0),
            "note":        data.get("note", ""),
            "created_at":  datetime.now().isoformat(),
        }
        write_timelog_entry(entry)
        return {"ok": True, "entry": entry}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def api_timelog_report(request: Request):
    """Generate a time audit report for a date range."""
    try:
        start_str = request.query_params.get("start", date.today().replace(day=1).isoformat())
        end_str   = request.query_params.get("end", date.today().isoformat())
        start = date.fromisoformat(start_str)
        end   = date.fromisoformat(end_str)

        entries = all_timelog_in_range(start, end)
        events  = all_events_in_range(start, end)
        stats   = calc_hourly_rate(entries, events)

        stats["start"] = start_str
        stats["end"]   = end_str
        stats["entries_count"] = len(entries)

        return {"ok": True, "stats": stats, "entries": entries}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ====== Custom Holidays API ======

CUSTOM_HOLIDAYS_FILE = DATA_DIR / "custom_holidays.json"

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


async def api_add_custom_holiday(request: Request):
    """Add a custom holiday."""
    try:
        data = await request.json()
        name = data.get("name", "").strip()
        date_str = data.get("date", "").strip()
        if not name or not date_str:
            return {"ok": False, "error": "名称和日期不能为空"}
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

async def api_list_schedules():
    """List all schedule templates."""
    try:
        schedules = read_schedules()
        return {"ok": True, "schedules": schedules}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def api_create_schedule(request: Request):
    """Create a new schedule template."""
    try:
        data = await request.json()
        schedules = read_schedules()
        new_id = f"schedule-{uuid4().hex[:8]}"
        schedule = {
            "id":             new_id,
            "title":          data.get("title", ""),
            "repeat_mode":     data.get("repeat_mode", "preheat"),
            "target_type":    data.get("target_type", ""),
            "target_id":      data.get("target_id", ""),
            "target_date":    data.get("target_date", ""),
            "target_name":    data.get("target_name", ""),
            "preheat_days":   data.get("preheat_days", 7),
            "start_date":     data.get("start_date", ""),
            "start_time":     data.get("start_time", "09:00"),
            "duration_minutes": data.get("duration_minutes", 60),
            "kind":           data.get("kind", "reminder"),
            "sop_page":       data.get("sop_page", ""),
            "description":    data.get("description", ""),
            "reminder":       data.get("reminder", "none"),
            "exec_mode":      data.get("exec_mode", "manual"),
            "scope":          data.get("scope", "yearly"),
            "year":           data.get("year", 0),
            "enabled":        True,
        }
        schedules.append(schedule)
        write_schedules(schedules)
        return {"ok": True, "id": new_id, "schedule": schedule}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def api_update_schedule(schedule_id: str, request: Request):
    """Update a schedule template."""
    try:
        data = await request.json()
        schedules = read_schedules()
        for sch in schedules:
            if sch["id"] == schedule_id:
                for key in ["title", "repeat_mode", "target_type", "target_id",
                            "target_date", "target_name", "preheat_days",
                            "start_time", "duration_minutes", "kind",
                            "sop_page", "description", "reminder",
                            "exec_mode", "scope", "year", "enabled"]:
                    if key in data:
                        sch[key] = data[key]
                break
        write_schedules(schedules)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def api_delete_schedule(schedule_id: str):
    """Delete a schedule template."""
    try:
        schedules = read_schedules()
        schedules = [s for s in schedules if s["id"] != schedule_id]
        write_schedules(schedules)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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


async def api_set_occurrence_status(schedule_id: str, request: Request):
    """Set completion status for a recurring event occurrence."""
    try:
        data = await request.json()
        date_str = data.get("date", "")
        status   = data.get("status", "pending")
        event_id = data.get("id", f"recurring-{schedule_id}-{date_str}")
        write_occurrence_override(date_str, event_id, status=status)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def api_set_occurrence_lock(schedule_id: str, request: Request):
    """Set lock status for a recurring event occurrence."""
    try:
        data = await request.json()
        date_str = data.get("date", "")
        locked   = data.get("locked", False)
        event_id = data.get("id", f"recurring-{schedule_id}-{date_str}")
        write_occurrence_override(date_str, event_id, locked=locked)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ====== Special Days API ======

async def api_list_special_days(request: Request):
    """List all special days for a year."""
    try:
        year_str = request.query_params.get("year", str(date.today().year))
        year = int(year_str)
        special_days = get_special_days(year)
        return {"ok": True, "special_days": special_days}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ====== Route Registration ======

def register_api_routes(app):
    """Register all API routes with the NiceGUI app object.

    Call this once from app.py after `app` is created.
    """
    # Event routes
    app.router.add_route("/api/events/create",        api_create_event,        methods=["POST"])
    app.router.add_route("/api/events/update",        api_update_event,        methods=["PUT"])
    app.router.add_route("/api/events",               api_list_events,          methods=["GET"])
    app.router.add_route("/api/events/status",        api_update_status,        methods=["POST"])
    app.router.add_route("/api/events/move",          api_move_event,           methods=["POST"])
    app.router.add_route("/api/events/delete",        api_delete_event,         methods=["POST"])
    app.router.add_route("/api/events/lock",          api_lock_event,           methods=["POST"])

    # Cell backgrounds
    app.router.add_route("/api/cell-backgrounds",     api_cell_backgrounds,     methods=["GET"])

    # Timelog
    app.router.add_route("/api/timelog/write",        api_write_timelog,       methods=["POST"])
    app.router.add_route("/api/timelog/report",        api_timelog_report,       methods=["GET"])

    # Custom holidays
    app.router.add_route("/api/custom-holidays",      api_list_custom_holidays,  methods=["GET"])
    app.router.add_route("/api/custom-holidays",      api_add_custom_holiday,    methods=["POST"])
    app.router.add_route("/api/custom-holidays",      api_delete_custom_holiday, methods=["DELETE"])

    # Schedules
    app.router.add_route("/api/schedules",            api_list_schedules,        methods=["GET"])
    app.router.add_route("/api/schedules",            api_create_schedule,        methods=["POST"])
    app.router.add_route("/api/schedules/{schedule_id}", api_update_schedule,    methods=["PUT"])
    app.router.add_route("/api/schedules/{schedule_id}", api_delete_schedule,    methods=["DELETE"])
    app.router.add_route("/api/schedules/{schedule_id}", api_get_schedule,       methods=["GET"])
    app.router.add_route("/api/schedules/{schedule_id}/occurrence-status", api_set_occurrence_status, methods=["POST"])
    app.router.add_route("/api/schedules/{schedule_id}/occurrence-lock",  api_set_occurrence_lock,   methods=["POST"])

    # Special days
    app.router.add_route("/api/special-days",         api_list_special_days,     methods=["GET"])
