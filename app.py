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
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

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
import ssl

def fetch_holidays(year: int) -> dict:
    """Fetch Chinese holidays from timor.peanut"""
    fp = DATA_DIR / f"holidays_{year}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = f"https://timor.peanut.com/api/holidays?country=CN&year={year}"
        with urllib.request.urlopen(url, context=ctx, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
    except Exception:
        return {}


SOLAR_TERMS_2025 = [
    ("小寒", "01-05"), ("大寒", "01-20"), ("立春", "02-03"), ("雨水", "02-18"),
    ("惊蛰", "03-05"), ("春分", "03-20"), ("清明", "04-04"), ("谷雨", "04-20"),
    ("立夏", "05-05"), ("小满", "05-21"), ("芒种", "06-05"), ("夏至", "06-21"),
    ("小暑", "07-07"), ("大暑", "07-22"), ("立秋", "08-07"), ("处暑", "08-23"),
    ("白露", "09-07"), ("秋分", "09-23"), ("寒露", "10-08"), ("霜降", "10-23"),
    ("立冬", "11-07"), ("小雪", "11-22"), ("大雪", "12-07"), ("冬至", "12-21"),
]

SHOPPING_FESTIVALS_2025 = [
    ("年货节", "01-06", "01-18"), ("38女神节", "03-01", "03-08"),
    ("415家装节", "04-01", "04-15"), ("51劳动节", "05-01", "05-05"),
    ("618大促", "06-01", "06-18"), ("818金石家博会", "08-10", "08-18"),
    ("99家装节", "09-01", "09-09"), ("双11", "11-01", "11-11"),
    ("双12", "12-01", "12-12"), ("年货节返场", "12-20", "12-31"),
]

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
    for name, start_mmdd, end_mmdd in SHOPPING_FESTIVALS_2025:
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
        <button onclick="switchView()">月视图</button>
    </div>""")

    # ---- Calendar container ----
    ui.html('<div id="calendar"></div>')

    # ---- Empty guide ----
    ui.html("""
    <div id="empty-guide" class="empty-guide">
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

    ui.add_body_html('<script src="/static/init.js"></script>')


# ====== API Routes ======

@app.post("/api/events/create")
async def api_create_event(request: Request):
    """Create a new event."""
    try:
        data = await request.json()
        day = date.fromisoformat(data["start"][:10])
        events = read_day(day)
        import uuid
        new_id = str(uuid.uuid4())
        event = {
            "id":        new_id,
            "text":      data.get("text", ""),
            "start":     data["start"],
            "end":       data["end"],
            "kind":      data.get("kind", "reminder"),
            "exec_mode": data.get("exec_mode", "manual"),
            "status":    "pending",
            "locked":    False,
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
        # Attach holiday/solar-term overlays
        for ev in events:
            d = date.fromisoformat(ev["start"][:10])
            ev["overlays"] = (
                get_solar_term_overlays(d)
                + get_shopping_festival_overlays(d)
                + get_semester_overlays(d)
            )
        return events
    except Exception as e:
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


# ====== SOP Page ======

@ui.page("/sop/{sop_id}")
def sop_page(sop_id: str):
    """Render a SOP page with timed steps."""
    sop = load_sop(sop_id)
    if not sop:
        ui.label(f"SOP 未找到: {sop_id}")
        return

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
                    # Timer buttons (simplified)
                    if step.get("exec_mode") == "manual" and step.get("est_min", 0) > 0:
                        ui.button("开始计时", on_click=lambda s=step: start_step_timer(s))

    render_steps()


def start_step_timer(step: dict):
    """Start a timer for a manual step (simplified version)."""
    import time
    # This is a placeholder — full timer needs JS integration
    ui.notify(f"计时开始: {step['name']} (预计 {step['est_min']} min)")


# ====== Startup / Shutdown ======

def on_startup():
    """Runs when the NiceGUI app starts."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        print("[Rubedo] APScheduler 已启动 (SQLite 持久化)")


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
        title      = "凝华 · Rubedo",
        native     = True,
        window_size = (1400, 900),
        port       = 8081,
        reload     = False,
        show       = True,
    )
