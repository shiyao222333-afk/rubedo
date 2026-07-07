"""
Rubedo · 凝华 — API 路由模块
包含：全部 API 路由处理函数
从 app.py 重构拆分（2026-07-05）

修复：所有 API 处理函数返回 JSONResponse（Starlette 要求）
"""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import JSONResponse

from modules.shared.logging_cfg import get_logger
log = get_logger("rubedo.api")

from modules.shared.store import (
    create_project, list_projects, get_project, update_project,
    delete_project, bind_event_to_project, unbind_event_from_project,
)
from modules.shared.errors import DataAccessError

from utils import (
    read_day, write_day, read_schedules, write_schedules,
    write_occurrence_override, write_timelog_entry,
    all_timelog_in_range, all_events_in_range,
    calc_hourly_rate, expand_recurring_schedules, expand_preheat_schedules,
    get_special_days, strip_icon,
    read_custom_holidays, write_custom_holidays, load_sop,
    find_event_by_id, save_event_day,
    KIND_COLORS, EXEC_MODES
)
from holidays import (
    fetch_holidays, get_all_festivals_for_year, generate_overlay_events,
    get_solar_terms_for_year, SEMESTER_RANGES
)


# ====== Event API Routes ======

async def api_create_event(request: Request):
    """Create a new event."""
    try:
        data = await request.json()
        
        # ---- 输入验证 ----
        # 必需字段
        if "start" not in data:
            return JSONResponse({"ok": False, "error": "缺少必需字段: start"})
        if "end" not in data:
            return JSONResponse({"ok": False, "error": "缺少必需字段: end"})
        
        # 时间格式和逻辑
        try:
            start_dt = datetime.fromisoformat(data["start"])
            end_dt   = datetime.fromisoformat(data["end"])
        except ValueError:
            return JSONResponse({"ok": False, "error": "时间格式错误，请使用 ISO 格式 (YYYY-MM-DDTHH:MM:SS)"})
        
        if start_dt >= end_dt:
            return JSONResponse({"ok": False, "error": "开始时间必须早于结束时间"})
        
        # 枚举值验证
        kind = data.get("kind", "reminder")
        if kind not in KIND_COLORS:
            return JSONResponse({"ok": False, "error": f"无效的事件类型: {kind}"})
        
        exec_mode = data.get("exec_mode", "manual")
        if exec_mode not in EXEC_MODES:
            return JSONResponse({"ok": False, "error": f"无效的执行模式: {exec_mode}"})
        
        # ---- 创建事件 ----
        day = date.fromisoformat(data["start"][:10])
        events = read_day(day)
        new_id = str(uuid4())
        event = {
            "id":          new_id,
            "text":        data.get("text", ""),
            "start":       data["start"],
            "end":         data["end"],
            "kind":        kind,
            "description": data.get("description", ""),
            "reminder":    data.get("reminder", "none"),
            "exec_mode":   exec_mode,
            "status":      "pending",
            "locked":      False,
            "project_id":  data.get("project_id"),   # 大类一 P3：绑订单（可空）
        }
        events.append(event)
        write_day(day, events)
        return JSONResponse({"ok": True, "id": new_id, "event": event})
    except json.JSONDecodeError as e:
        log.error(f"api_create_event: JSON decode error: {e}")
        return JSONResponse({"ok": False, "error": "Invalid JSON"})
    except KeyError as e:
        log.error(f"api_create_event: Missing key: {e}")
        return JSONResponse({"ok": False, "error": f"Missing required field: {e}"})
    except ValueError as e:
        log.error(f"api_create_event: Value error: {e}")
        return JSONResponse({"ok": False, "error": f"Invalid value: {e}"})
    except Exception as e:
        log.exception(f"api_create_event: Unexpected error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_update_event(request: Request):
    """Update an existing event (text, kind, exec_mode, time, etc.).

    对重复事件（recurring=True），改 schedules 表模板（影响所有 occurrence）。
    对普通事件，改当天 events 表（SQLite DAL）。
    """
    try:
        data = await request.json()
        
        # ---- 输入验证 ----
        if not isinstance(data, dict):
            return JSONResponse({"ok": False, "error": "Invalid request body"})
        
        # 普通事件：需要 day + id
        if not data.get("recurring"):
            if "day" not in data:
                return JSONResponse({"ok": False, "error": "Missing required field: day"})
            if "id" not in data:
                return JSONResponse({"ok": False, "error": "Missing required field: id"})
            # 验证 day 格式
            try:
                date.fromisoformat(data["day"])
            except (ValueError, TypeError):
                return JSONResponse({"ok": False, "error": "Invalid day format, expected YYYY-MM-DD"})
        
        # 重复事件：需要 recurring=True + schedule_id
        else:
            if "schedule_id" not in data:
                return JSONResponse({"ok": False, "error": "Missing required field: schedule_id for recurring event"})
        
        # 验证 kind 枚举值（与 api_create_event 共用 KIND_COLORS 单一真相源，避免创建/更新允许值不一致）
        if "kind" in data and data["kind"] not in KIND_COLORS:
            return JSONResponse({"ok": False, "error": f"Invalid kind: {data['kind']}"})
        
        # 验证 exec_mode 枚举值
        if "exec_mode" in data and data["exec_mode"] not in ("manual", "auto"):
            return JSONResponse({"ok": False, "error": f"Invalid exec_mode: {data['exec_mode']}"})
        
        # 验证时间（如果提供）
        if "start" in data and "end" in data:
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(data["start"])
                end_dt   = datetime.fromisoformat(data["end"])
                if end_dt <= start_dt:
                    return JSONResponse({"ok": False, "error": "end must be after start"})
            except (ValueError, TypeError):
                return JSONResponse({"ok": False, "error": "Invalid time format, expected ISO 8601"})
        
        log.debug(f"api_update_event: recurring={data.get('recurring')}, schedule_id={data.get('schedule_id')}")
        
        # ---- 重复事件：改模板（schedules 表，SQLite）----
        if data.get("recurring") and data.get("schedule_id"):
            log.debug(f"Updating recurring event, schedule_id={data['schedule_id']}")
            schedules = read_schedules()

            for sch in schedules:
                if sch["id"] == data["schedule_id"]:
                    # 改模板字段（影响所有 occurrence）
                    if "text" in data:
                        sch["title"] = strip_icon(data["text"])
                    if "kind" in data:
                        sch["kind"] = data["kind"]
                    if "exec_mode" in data:
                        sch["exec_mode"] = data["exec_mode"]
                    if "description" in data:
                        sch["description"] = data["description"]
                    if "reminder" in data:
                        sch["reminder"] = data["reminder"]
                    # 时间字段 → 改 start_time 和 duration_minutes
                    if "start" in data and "end" in data:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(data["start"])
                        end_dt   = datetime.fromisoformat(data["end"])
                        sch["start_time"] = start_dt.strftime("%H:%M")
                        sch["duration_minutes"] = int((end_dt - start_dt).total_seconds() / 60)
                    if "project_id" in data:
                        sch["project_id"] = data["project_id"]
                    break
            write_schedules(schedules)
            return JSONResponse({"ok": True})
        
        # ---- 普通事件：改当天 events 表（SQLite DAL）----
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
                if "start" in data and "end" in data:
                    ev["start"] = data["start"]
                    ev["end"]   = data["end"]
                if "project_id" in data:
                    ev["project_id"] = data["project_id"]
                break
        write_day(day, events)
        return JSONResponse({"ok": True})
    except json.JSONDecodeError as e:
        log.error(f"api_update_event: JSON decode error: {e}")
        return JSONResponse({"ok": False, "error": "Invalid JSON"})
    except KeyError as e:
        log.error(f"api_update_event: Missing key: {e}")
        return JSONResponse({"ok": False, "error": f"Missing required field: {e}"})
    except ValueError as e:
        log.error(f"api_update_event: Value error: {e}")
        return JSONResponse({"ok": False, "error": f"Invalid value: {e}"})
    except Exception as e:
        log.exception(f"api_update_event: Unexpected error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_list_events(request: Request):
    """List events in a date range."""
    try:
        start_str = request.query_params.get("start", "")
        end_str   = request.query_params.get("end", "")
        if not start_str or not end_str:
            return JSONResponse([])
        start = date.fromisoformat(start_str)
        end   = date.fromisoformat(end_str)
        events = all_events_in_range(start, end)
        preheat_events = expand_preheat_schedules(start, end)
        events.extend(preheat_events)
        recurring_events = expand_recurring_schedules(start, end)
        events.extend(recurring_events)
        # 防御：缺 start/id 的坏事件直接跳过并告警，避免单条坏数据让 DayPilot 整页崩溃
        clean = []
        for ev in events:
            if ev.get("id") and ev.get("start"):
                clean.append(ev)
            else:
                log.warning(f"api_list_events: 跳过缺 start/id 的坏事件: {ev!r}")
        return JSONResponse(clean)
    except Exception as e:
        log.exception(f"api_list_events: {e}")
        return JSONResponse([])


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
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_update_status: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


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
            return JSONResponse({"ok": True, "event": moved})
        # 没找到目标事件：明确报错，避免前端静默"没反应"
        log.warning(f"api_move_event: 找不到事件 old_id={data.get('old_id')} old_day={old_day}")
        return JSONResponse({"ok": False, "error": "Event not found"})
    except Exception as e:
        log.exception(f"api_move_event: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_delete_event(request: Request):
    """Delete an event."""
    try:
        data  = await request.json()
        day   = date.fromisoformat(data["day"])
        events = read_day(day)
        events = [ev for ev in events if ev["id"] != data["id"]]
        write_day(day, events)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_delete_event: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


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
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_lock_event: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


# ====== Cell Backgrounds API ======

async def api_cell_backgrounds(request: Request):
    """Return special dates as cell background colors."""
    PRIORITY = {"custom": 1, "holiday": 2, "fest": 3, "solar": 4, "sem": 5}
    COLORS   = {"custom": "#B2DFDB", "holiday": "#BBDEFB", "fest": "#DCEDC8", "solar": "", "sem": ""}

    try:
        start_str = request.query_params.get("start", "")
        end_str   = request.query_params.get("end", "")
        if not start_str or not end_str:
            return JSONResponse({"dates": {}})
        start = date.fromisoformat(start_str)
        end   = date.fromisoformat(end_str)
        year  = start.year
        raw   = {}

        def add(ds, ptype, text):
            if ds not in raw:
                raw[ds] = []
            raw[ds].append((PRIORITY[ptype], COLORS[ptype], text, ptype))

        # 1. 节气
        for name, mmdd in get_solar_terms_for_year(year):
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

        # 5. 自定义重要日子 (v0.4 T3: 改走 SQLite DAL)
        for h in read_custom_holidays():
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

        return JSONResponse({"dates": dates})
    except Exception as e:
        log.exception(f"api_cell_backgrounds: {e}")
        return JSONResponse({"dates": {}})


# ====== Timelog API ======

async def api_write_timelog(request: Request):
    """Write a timelog entry."""
    try:
        data = await request.json()
        
        # ---- 输入验证 ----
        if not isinstance(data, dict):
            return JSONResponse({"ok": False, "error": "Invalid request body"})
        
        # 验证必需字段
        if "sop_id" not in data:
            return JSONResponse({"ok": False, "error": "Missing required field: sop_id"})
        if not data["sop_id"] or not isinstance(data["sop_id"], str):
            return JSONResponse({"ok": False, "error": "sop_id must be a non-empty string"})
        
        # 验证时间格式（如果提供）
        for time_field in ["start_time", "end_time"]:
            if time_field in data and data[time_field]:
                try:
                    from datetime import datetime
                    datetime.fromisoformat(data[time_field])
                except (ValueError, TypeError):
                    return JSONResponse({"ok": False, "error": f"Invalid {time_field} format, expected ISO 8601"})
        
        # 验证 duration_min 非负
        if "duration_min" in data:
            try:
                duration = int(data["duration_min"])
                if duration < 0:
                    return JSONResponse({"ok": False, "error": "duration_min must be non-negative"})
            except (ValueError, TypeError):
                return JSONResponse({"ok": False, "error": "duration_min must be an integer"})
        
        # 验证 income 非负
        if "income" in data:
            try:
                income = float(data["income"])
                if income < 0:
                    return JSONResponse({"ok": False, "error": "income must be non-negative"})
            except (ValueError, TypeError):
                return JSONResponse({"ok": False, "error": "income must be a number"})
        
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
        return JSONResponse({"ok": True, "entry": entry})
    except Exception as e:
        log.exception(f"api_write_timelog: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


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

        return JSONResponse({"ok": True, "stats": stats, "entries": entries})
    except Exception as e:
        log.exception(f"api_timelog_report: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


# ====== Custom Holidays API (v0.4 T3: 改走 SQLite DAL) ======

async def api_list_custom_holidays(request: Request):
    """List all custom holidays."""
    try:
        return JSONResponse({"ok": True, "holidays": read_custom_holidays()})
    except Exception as e:
        log.exception(f"api_list_custom_holidays: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_add_custom_holiday(request: Request):
    """Add a custom holiday."""
    try:
        data = await request.json()
        
        # ---- 输入验证 ----
        if not isinstance(data, dict):
            return JSONResponse({"ok": False, "error": "Invalid request body"})
        
        name = data.get("name", "").strip()
        date_str = data.get("date", "").strip()
        if not name or not date_str:
            return JSONResponse({"ok": False, "error": "名称和日期不能为空"})
        if len(name) > 50:
            return JSONResponse({"ok": False, "error": "名称不能超过50个字符"})
        from datetime import datetime as dt
        try:
            dt.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return JSONResponse({"ok": False, "error": "日期格式错误，应为 YYYY-MM-DD"})
        holidays = read_custom_holidays()
        holidays.append({"name": name, "date": date_str})
        write_custom_holidays(holidays)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_add_custom_holiday: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_delete_custom_holiday(request: Request):
    """Delete a custom holiday by name and date."""
    try:
        data = await request.json()
        name = data.get("name", "")
        date_str = data.get("date", "")
        if not name or not date_str:
            return JSONResponse({"ok": False, "error": "参数不完整"})
        holidays = read_custom_holidays()
        holidays = [h for h in holidays if not (h["name"] == name and h["date"] == date_str)]
        write_custom_holidays(holidays)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_delete_custom_holiday: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


# ====== Schedules API (重复事件模板) ======

async def api_list_schedules(request: Request):
    """List all schedule templates."""
    try:
        schedules = read_schedules()
        return JSONResponse({"ok": True, "schedules": schedules})
    except Exception as e:
        log.exception(f"api_list_schedules: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


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
        return JSONResponse({"ok": True, "id": new_id, "schedule": schedule})
    except Exception as e:
        log.exception(f"api_create_schedule: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_update_schedule(request: Request):
    """Update a schedule template."""
    try:
        schedule_id = request.path_params["schedule_id"]
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
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_update_schedule: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_delete_schedule(request: Request):
    """Delete a schedule template."""
    try:
        schedule_id = request.path_params["schedule_id"]
        schedules = read_schedules()
        schedules = [s for s in schedules if s["id"] != schedule_id]
        write_schedules(schedules)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_delete_schedule: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_get_schedule(request: Request):
    """Get a single schedule template."""
    try:
        schedule_id = request.path_params["schedule_id"]
        schedules = read_schedules()
        for sch in schedules:
            if sch["id"] == schedule_id:
                return JSONResponse({"ok": True, "schedule": sch})
        return JSONResponse({"ok": False, "error": "Schedule not found"})
    except Exception as e:
        log.exception(f"api_get_schedule: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_set_occurrence_status(request: Request):
    """Set completion status for a recurring event occurrence."""
    try:
        schedule_id = request.path_params["schedule_id"]
        data = await request.json()
        date_str = data.get("date", "")
        status   = data.get("status", "pending")
        event_id = data.get("id", f"recurring-{schedule_id}-{date_str}")
        write_occurrence_override(date_str, event_id, status=status)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_set_occurrence_status: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


async def api_set_occurrence_lock(request: Request):
    """Set lock status for a recurring event occurrence."""
    try:
        schedule_id = request.path_params["schedule_id"]
        data = await request.json()
        date_str = data.get("date", "")
        locked   = data.get("locked", False)
        event_id = data.get("id", f"recurring-{schedule_id}-{date_str}")
        write_occurrence_override(date_str, event_id, locked=locked)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_set_occurrence_lock: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


# ====== Special Days API ======

async def api_list_special_days(request: Request):
    """List all special days for a year."""
    try:
        year_str = request.query_params.get("year", str(date.today().year))
        year = int(year_str)
        special_days = get_special_days(year)
        return JSONResponse({"ok": True, "special_days": special_days})
    except Exception as e:
        log.exception(f"api_list_special_days: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


# ====== SOP API Routes ======

async def api_get_sop(request: Request):
    """Get SOP JSON by sop_id (from SQLite)."""
    try:
        sop_id = request.path_params["sop_id"]
        sop_data = load_sop(sop_id)
        if sop_data is None:
            return JSONResponse({"ok": False, "error": f"SOP {sop_id} 不存在"})
        return JSONResponse({"ok": True, "sop": sop_data})
    except Exception as e:
        log.exception(f"api_get_sop: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


# ====== Event SOP Step API Routes ======

async def api_update_sop_step(request: Request):
    """Update event's sop_current_step."""
    try:
        from datetime import datetime
        event_id = request.path_params["event_id"]
        data = await request.json()
        new_step = data.get("step")
        started_at = data.get("started_at")
        duration_sec = data.get("duration_sec")
        mode = data.get("mode")

        if new_step is None:
            return JSONResponse({"ok": False, "error": "缺少 step 参数"})

        # 计时：前端传了 started_at + duration_sec 时，记录这一步的耗时
        # （存进事件自身的 sop_step_timings，不新建表，符合"只做计时按钮"的最小改动）
        timing_entry = None
        if started_at is not None and duration_sec is not None:
            step_idx = new_step - 1
            timing_entry = {
                str(step_idx): {
                    "started_at": started_at,
                    "duration_sec": duration_sec,
                    "mode": mode or "manual",
                    "recorded_at": datetime.now().isoformat(),
                }
            }

        # 限制1 fix: 重复事件（运行时展开，不在 events 表）的 SOP 步骤进度
        # 存进 occurrence_overrides（按 日期+event_id），与完成/锁定状态同表
        if event_id.startswith("recurring-"):
            # event_id 形如 recurring-{schedule_id}-{YYYY-MM-DD}，末尾三段为日期
            parts = event_id.split("-")
            date_str = "-".join(parts[-3:])
            try:
                datetime.fromisoformat(date_str)  # 仅校验格式
            except ValueError:
                return JSONResponse({"ok": False, "error": "无效的重复事件 id"})
            write_occurrence_override(
                date_str, event_id,
                sop_current_step=new_step,
                sop_step_timings=timing_entry,
            )
            return JSONResponse({"ok": True})

        # 普通事件：找到并更新 sop_current_step (v0.4 T3: 改走 SQLite DAL)
        found = False
        day, events = find_event_by_id(event_id)
        if day is not None:
            for ev in events:
                if ev.get("id") == event_id:
                    ev["sop_current_step"] = new_step
                    if timing_entry:
                        ev.setdefault("sop_step_timings", {}).update(timing_entry)
                    found = True
                    break
            if found:
                save_event_day(day, events)
        
        if not found:
            return JSONResponse({"ok": False, "error": f"事件 {event_id} 未找到"})
        
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_update_sop_step: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


# ====== Route Registration ======

async def api_report_client_error(request: Request):
    """前端把浏览器里发生的错误上报到这里，写入 data/rubedo_client_errors.log。

    这样用户（非程序员）无需复制粘贴，后端可直接读取定位问题。
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    message = str(payload.get("message", ""))
    url = str(payload.get("url", ""))
    ts = str(payload.get("time", ""))
    entry = f"[{ts}] {url}\n{message}\n{'-' * 60}\n"
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "rubedo_client_errors.log"), "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        log.error(f"api_report_client_error: 写入日志失败: {e}")
    return JSONResponse({"ok": True})


# ====== Project (订单) API Routes ======
async def api_list_projects(request: Request):
    try:
        status = request.query_params.get("status")
        items = list_projects(status)
        return JSONResponse({"ok": True, "projects": items})
    except Exception as e:
        log.exception(f"api_list_projects: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

async def api_create_project(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"})
    try:
        pid = create_project(data)
        return JSONResponse({"ok": True, "id": pid})
    except DataAccessError as e:
        return JSONResponse({"ok": False, "error": str(e)})
    except Exception as e:
        log.exception(f"api_create_project: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

async def api_get_project(request: Request):
    pid = request.path_params["project_id"]
    try:
        p = get_project(pid)
        if not p:
            return JSONResponse({"ok": False, "error": "项目不存在"})
        return JSONResponse({"ok": True, "project": p})
    except Exception as e:
        log.exception(f"api_get_project: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

async def api_update_project(request: Request):
    pid = request.path_params["project_id"]
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"})
    try:
        ok = update_project(pid, data)
        return JSONResponse({"ok": ok})
    except DataAccessError as e:
        return JSONResponse({"ok": False, "error": str(e)})
    except Exception as e:
        log.exception(f"api_update_project: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

async def api_delete_project(request: Request):
    pid = request.path_params["project_id"]
    try:
        delete_project(pid)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_delete_project: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

async def api_bind_event_to_project(request: Request):
    pid = request.path_params["project_id"]
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"})
    eid = (data or {}).get("event_id")
    if not eid:
        return JSONResponse({"ok": False, "error": "缺少 event_id"})
    try:
        bind_event_to_project(pid, eid)
        return JSONResponse({"ok": True})
    except DataAccessError as e:
        return JSONResponse({"ok": False, "error": str(e)})
    except Exception as e:
        log.exception(f"api_bind_event_to_project: {e}")
        return JSONResponse({"ok": False, "error": str(e)})

async def api_unbind_event_from_project(request: Request):
    pid = request.path_params["project_id"]
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"})
    eid = (data or {}).get("event_id")
    if not eid:
        return JSONResponse({"ok": False, "error": "缺少 event_id"})
    try:
        unbind_event_from_project(pid, eid)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.exception(f"api_unbind_event_from_project: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


def register_api_routes(app):
    """Register all API routes with the NiceGUI app object.

    Call this once from app.py after `app` is created.
    """
    # 客户端错误上报（前端红字自动飞到这里）
    app.router.add_route("/api/client-error",        api_report_client_error,  methods=["POST"])
    # Event routes
    app.router.add_route("/api/events/create",        api_create_event,        methods=["POST"])
    app.router.add_route("/api/events/update",        api_update_event,        methods=["PUT"])
    app.router.add_route("/api/events",               api_list_events,          methods=["GET"])
    app.router.add_route("/api/events/status",        api_update_status,        methods=["POST"])
    app.router.add_route("/api/events/move",          api_move_event,           methods=["POST"])
    app.router.add_route("/api/events/delete",        api_delete_event,         methods=["POST"])
    app.router.add_route("/api/events/lock",          api_lock_event,           methods=["POST"])
    app.router.add_route("/api/events/{event_id}/sop-step", api_update_sop_step,  methods=["POST"])

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

    # SOP
    app.router.add_route("/api/sop/{sop_id}",        api_get_sop,             methods=["GET"])

    # Projects（大类一 P4：订单 CRUD + 绑/解绑事件）
    app.router.add_route("/api/projects",                  api_list_projects,          methods=["GET"])
    app.router.add_route("/api/projects",                  api_create_project,         methods=["POST"])
    app.router.add_route("/api/projects/{project_id}",     api_get_project,            methods=["GET"])
    app.router.add_route("/api/projects/{project_id}",     api_update_project,         methods=["PUT"])
    app.router.add_route("/api/projects/{project_id}",     api_delete_project,         methods=["DELETE"])
    app.router.add_route("/api/projects/{project_id}/bind",   api_bind_event_to_project,  methods=["POST"])
    app.router.add_route("/api/projects/{project_id}/unbind", api_unbind_event_from_project, methods=["POST"])

    # Special days
    app.router.add_route("/api/special-days",         api_list_special_days,     methods=["GET"])
