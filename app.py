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

# ====== Timelog ======
import timelog

# ====== APScheduler ======
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.jobstores.base import JobLookupError

# ====== Paths ======
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SOPS_DIR = DATA_DIR / "sops"
TIMELOG_DIR = DATA_DIR / "timelog"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
SOPS_DIR.mkdir(parents=True, exist_ok=True)
TIMELOG_DIR.mkdir(parents=True, exist_ok=True)

# ====== NiceGUI ======
from nicegui import app, ui, run
from starlette.requests import Request

# ====== CSP Headers for DayPilot CDN ======
@app.on_connect
def add_csp_headers():
    """Allow DayPilot CDN scripts and styles."""
    pass  # NiceGUI native 模式默认不限制 CDN

# ====== Constants ======
KIND_COLORS = {
    "sop":       {"back": "#4CAF50", "bar": "#388E3C"},  # 绿 — SOP 工作流
    "tool":      {"back": "#2196F3", "bar": "#1976D2"},  # 蓝 — 共用工具
    "reminder":  {"back": "#9E9E9E", "bar": "#757575"},  # 灰 — 提醒
    "external":  {"back": "#FF9800", "bar": "#F57C00"},  # 橙 — 外部事件
    "marker":    {"back": "#F44336", "bar": "#D32F2F"},  # 红 — 标记日
}

REPEAT_MODES = ["none", "daily", "weekly", "weekday", "monthly", "yearly", "preheat"]
EXEC_MODES = ["auto", "manual"]
STATUSES = ["pending", "done", "skipped"]


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


def save_event(event: dict) -> dict:
    """
    Save or update a single event.
    The event is stored in the file matching its start date.
    Returns the saved event (with id generated if new).
    """
    if "id" not in event:
        import uuid
        event["id"] = str(uuid.uuid4())[:8]

    day = date.fromisoformat(event["start"][:10])
    day_events = read_day(day)

    # Update existing or append
    updated = False
    for i, ev in enumerate(day_events):
        if ev.get("id") == event["id"]:
            day_events[i] = event
            updated = True
            break
    if not updated:
        day_events.append(event)

    write_day(day, day_events)
    return event


def delete_event(event_id: str, day_str: str) -> bool:
    """Delete an event by id from a specific day's file."""
    day = date.fromisoformat(day_str)
    day_events = read_day(day)
    original_len = len(day_events)
    day_events = [ev for ev in day_events if ev.get("id") != event_id]
    if len(day_events) < original_len:
        write_day(day, day_events)
        return True
    return False


def read_schedules() -> dict:
    """Read repeat event templates."""
    fp = DATA_DIR / "schedules.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_schedules(schedules: dict) -> None:
    """Write repeat event templates."""
    fp = DATA_DIR / "schedules.json"
    fp.write_text(json.dumps(schedules, ensure_ascii=False, indent=2), encoding="utf-8")


def read_markers() -> list[dict]:
    """Read manually created marker days (shopping festivals, etc.)."""
    fp = DATA_DIR / "markers.json"
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def write_markers(markers: list[dict]) -> None:
    """Write marker days."""
    fp = DATA_DIR / "markers.json"
    fp.write_text(json.dumps(markers, ensure_ascii=False, indent=2), encoding="utf-8")


# ====== Repeat Event Expansion ======

def expand_repeat(event: dict, start: date, end: date) -> list[dict]:
    """
    Expand a repeat event template into concrete events within [start, end].
    Does NOT produce events beyond `repeat_until` if set.
    For 'preheat' mode: expand backward from anchor_date, does not exceed anchor.
    """
    repeat = event.get("repeat", "none")
    if repeat == "none":
        return []

    ev_start = date.fromisoformat(event["start"][:10])
    repeat_until_str = event.get("repeat_until")
    repeat_until = date.fromisoformat(repeat_until_str) if repeat_until_str else end

    # Clamp to visible range
    range_end = min(end, repeat_until)

    expanded = []
    current = max(ev_start, start)

    if repeat == "daily":
        while current <= range_end:
            expanded.append(_make_instance(event, current))
            current += timedelta(days=1)

    elif repeat == "weekly":
        # Find next occurrence matching the same weekday
        target_wday = ev_start.weekday()
        while current <= range_end:
            if current.weekday() == target_wday:
                expanded.append(_make_instance(event, current))
            current += timedelta(days=1)

    elif repeat == "weekday":
        while current <= range_end:
            if current.weekday() < 5:  # Mon-Fri
                expanded.append(_make_instance(event, current))
            current += timedelta(days=1)

    elif repeat == "monthly":
        # Same day of month
        target_day = ev_start.day
        while current <= range_end:
            # Handle month-end edge case (31st → last day of shorter months)
            try:
                instance_date = current.replace(day=target_day)
            except ValueError:
                continue
            if instance_date >= start and instance_date >= ev_start:
                expanded.append(_make_instance(event, instance_date))
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    elif repeat == "yearly":
        target_month = ev_start.month
        target_day = ev_start.day
        while current <= range_end:
            try:
                instance_date = current.replace(month=target_month, day=target_day)
                if instance_date >= ev_start and instance_date >= start:
                    expanded.append(_make_instance(event, instance_date))
            except ValueError:
                pass
            current = current.replace(year=current.year + 1)

    elif repeat == "preheat":
        # Expand backward from anchor_date, NOT exceeding anchor
        interval_days = event.get("preheat_interval", 1)  # every N days
        anchor_str = event.get("preheat_anchor")
        if not anchor_str:
            return []
        anchor = date.fromisoformat(anchor_str)
        # Don't go past anchor
        effective_end = min(range_end, anchor)
        cursor = anchor
        while cursor >= start and cursor >= ev_start:
            if cursor <= effective_end:
                expanded.append(_make_instance(event, cursor))
            cursor -= timedelta(days=interval_days)

    return expanded


def _make_instance(template: dict, d: date) -> dict:
    """Create a concrete event instance from a template for a given date."""
    start_time = template["start"][11:] if "T" in template["start"] else "09:00:00"
    end_time = template["end"][11:] if "T" in template["end"] else "10:00:00"
    return {
        **{k: v for k, v in template.items()
           if k not in ("repeat", "repeat_until", "preheat_interval", "preheat_anchor")},
        "id": f"{template.get('id', 'evt')}-{d.isoformat()}",
        "start": f"{d.isoformat()}T{start_time}",
        "end": f"{d.isoformat()}T{end_time}",
        "_repeat_parent": template.get("id"),
    }


# ====== Holiday Data ======

def load_holidays(year: int) -> dict:
    """
    Load Chinese holidays for a given year from cache or remote.
    Returns { "YYYY-MM-DD": { "name": "...", "isOffDay": true/false } }
    """
    cache_fp = DATA_DIR / f"holidays_{year}.json"
    if cache_fp.exists():
        try:
            return json.loads(cache_fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Try fetching from holiday-cn
    import urllib.request
    url = f"https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Rubedo/0.2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            holidays = {}
            for item in data.get("days", []):
                holidays[item["date"]] = {
                    "name": item.get("name", ""),
                    "isOffDay": item.get("isOffDay", False),
                }
            # Cache locally
            cache_fp.write_text(json.dumps(holidays, ensure_ascii=False, indent=2), encoding="utf-8")
            return holidays
    except Exception:
        return {}

    return {}


# ====== Season / Semester Overlay ======

SEASON_RANGES = [
    # (name, start_mmdd, end_mmdd)
    ("春", "03-01", "05-31"),
    ("夏", "06-01", "08-31"),
    ("秋", "09-01", "11-30"),
    ("冬", "12-01", "02-28"),  # handles leap year
]

SEMESTER_RANGES = [
    ("寒假", "01-15", "02-28"),
    ("暑假", "07-01", "08-31"),
]


def get_season_overlays(year: int, month: int) -> list[str]:
    """Get season/semester labels for a given month."""
    overlays = []
    for name, start_mmdd, end_mmdd in SEASON_RANGES:
        start_m, start_d = int(start_mmdd[:2]), int(start_mmdd[3:])
        end_m, end_d = int(end_mmdd[:2]), int(end_mmdd[3:])
        # Handle winter spanning year boundary
        if start_m > end_m:  # 冬: 12~2
            if month >= start_m or month <= end_m:
                overlays.append(name)
        elif start_m <= month <= end_m:
            overlays.append(name)

    for name, start_mmdd, end_mmdd in SEMESTER_RANGES:
        start_m, start_d = int(start_mmdd[:2]), int(start_mmdd[3:])
        end_m, end_d = int(end_mmdd[:2]), int(end_mmdd[3:])
        if start_m <= month <= end_m:
            overlays.append(name)

    return overlays


# ====== Routes ======

@ui.page("/")
def index():
    """Main calendar page (DayPilot week view)."""
    ui.add_head_html("""
    <script src="https://cdn.jsdelivr.net/npm/dayjs@1/dayjs.min.js"></script>
    <script src="https://cdn.daypilot.org/daypilot-all.min.js"></script>
    <style>
        html, body {
            margin: 0; padding: 0;
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
            margin-right: auto;
        }
        /* Empty calendar guide */
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
        /* CDN fallback warning */
        .cdn-warning {
            display: none;
            padding: 8px 16px; background: #e94560;
            color: #fff; font-size: 13px; text-align: center;
        }
        .cdn-warning a { color: #fff; text-decoration: underline; }
    </style>
    """)

    # Navigation bar
    with ui.row().classes("nav-bar"):
        ui.label("凝华 · Rubedo").classes("title")
        ui.button("← 上周", on_click=lambda: ui.run_javascript("navWeek(-1)"))
        ui.button("今天", on_click=lambda: ui.run_javascript("navToday()"))
        ui.button("下周 →", on_click=lambda: ui.run_javascript("navWeek(1)"))
        ui.button("月视图", on_click=lambda: ui.run_javascript("switchView()"))

    # CDN fallback warning (hidden by default)
    ui.html('<div id="cdn-warning" class="cdn-warning">⚠️ 日历组件加载失败。请检查网络连接。若网络正常，<a href="javascript:location.reload()">点击刷新</a></div>')

    # Empty calendar guide overlay
    ui.html("""
    <div id="empty-guide" class="empty-guide">
        <div class="icon">📅</div>
        <div class="title">空空如也，等待你的第一个计划</div>
        <div class="hint">
            在日历上拖选时间段来创建新事项<br>
            右键事项可以标记完成、编辑或删除<br>
            试试创建你的第一条待办吧！
        </div>
    </div>
    """)

    # Calendar container
    ui.html('<div id="calendar"></div>')

    # Side detail panel (hidden by default)
    ui.html('<div id="detail-panel" style="display:none; position:fixed; right:0; top:0; width:360px; height:100vh; background:#1a1a2e; border-left:1px solid #0f3460; padding:20px; overflow-y:auto; z-index:1000;"></div>')

    # DayPilot init script
    ui.add_body_html("""
    <script>
    // CDN fallback detection
    if (typeof DayPilot === "undefined") {
        document.getElementById("cdn-warning").style.display = "block";
        // Try backup CDN
        var fallback = document.createElement("script");
        fallback.src = "https://unpkg.com/daypilot-all@latest/daypilot-all.min.js";
        fallback.onload = function() { location.reload(); };
        document.head.appendChild(fallback);
    }

    function toggleEmptyGuide(show) {
        var guide = document.getElementById("empty-guide");
        if (guide) {
            guide.style.display = show ? "block" : "none";
        }
    }

    let currentView = "Week";
    let currentStart = dayjs().startOf("week");

    const dp = new DayPilot.Calendar("calendar", {
        viewType: "Week",
        cellDuration: 30,
        cellHeight: 30,
        dayBeginsHour: 0,
        dayEndsHour: 24,
        locale: "zh-cn",
        timeRangeSelectedHandling: "JavaScript",
        onTimeRangeSelected: function(args) {
            const text = prompt("新建事项标题：");
            if (!text) return;
            const kind = prompt("分类 (sop/tool/reminder/external/marker)：", "reminder");
            if (!kind) return;
            const start = args.start.toString("yyyy-MM-ddTHH:mm:ss");
            const end = args.end.toString("yyyy-MM-ddTHH:mm:ss");
            fetch("/api/events/create", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({text, start, end, kind, exec_mode: "manual"})
            }).then(r => r.json()).then(data => {
                if (data.ok) loadEvents();
            });
        },
        eventClickHandling: "JavaScript",
        eventDeleteHandling: "Disabled",
        contextMenu: new DayPilot.Menu({
            items: [
                { text: "✏️ 编辑", id: "edit" },
                { text: "✅ 完成", id: "done" },
                { text: "⏭️ 跳过", id: "skip" },
                { text: "-" },
                { text: "🗑️ 删除", id: "delete" },
                { text: "🔒 锁定/解锁", id: "toggle_lock" },
            ],
            onShow: function(args) {
                const ev = dp.events.find(args.source.value());
                if (ev && ev.data && ev.data.locked) {
                    args.menu.items[0].disabled = true;
                    args.menu.items[1].disabled = true;
                    args.menu.items[2].disabled = true;
                    args.menu.items[4].disabled = true;
                }
            }
        })
    });

    // --- Navigation ---
    window.navWeek = function(delta) {
        currentStart = currentStart.add(delta, "week");
        dp.startDate = currentStart.format("YYYY-MM-DD");
        loadEvents();
    };
    window.navToday = function() {
        currentStart = dayjs().startOf("week");
        dp.startDate = currentStart.format("YYYY-MM-DD");
        loadEvents();
    };
    window.switchView = function() {
        if (currentView === "Week") {
            currentView = "Month";
            dp.viewType = "Month";
        } else {
            currentView = "Week";
            dp.viewType = "Week";
        }
        loadEvents();
    };

    // --- Event Click → side detail panel ---
    dp.onEventClick = function(args) {
        const ev = args.e.data;
        showDetailPanel(ev);
    };

    // --- Context Menu ---
    dp.contextMenu.onSelect = function(args) {
        const ev = args.source.data;
        const action = args.item.id;
        if (action === "edit") {
            showDetailPanel(ev);
        } else if (action === "done" || action === "skip") {
            fetch("/api/events/status", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    id: ev.id,
                    day: ev.start.substring(0, 10),
                    status: action === "done" ? "done" : "skipped"
                })
            }).then(r => r.json()).then(() => loadEvents());
        } else if (action === "delete") {
            fetch("/api/events/delete", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({id: ev.id, day: ev.start.substring(0, 10)})
            }).then(r => r.json()).then(() => loadEvents());
        } else if (action === "toggle_lock") {
            const newLocked = !(ev.locked || false);
            fetch("/api/events/lock", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({id: ev.id, day: ev.start.substring(0, 10), locked: newLocked})
            }).then(r => r.json()).then(() => loadEvents());
        }
    };

    // --- Load events from API ---
    dp.onBeforeEventRender = function(args) {
        const ev = args.data;
        // Color by kind
        const kindColors = {
            "sop":      {back: "#4CAF50", bar: "#388E3C"},
            "tool":     {back: "#2196F3", bar: "#1976D2"},
            "reminder": {back: "#9E9E9E", bar: "#757575"},
            "external": {back: "#FF9800", bar: "#F57C00"},
            "marker":   {back: "#F44336", bar: "#D32F2F"},
        };
        const c = kindColors[ev.kind] || {back: "#9E9E9E", bar: "#757575"};
        args.e.backColor = ev.backColor || c.back;
        args.e.barColor = ev.barColor || c.bar;

        // Locked indicator
        if (ev.locked) {
            args.e.html = "🔒 " + args.e.text;
        }

        // Done styling
        if (ev.status === "done") {
            args.e.cssClass = "event-done";
        }
    };

    dp.onEventMoved = function(args) {
        const ev = args.e.data;
        if (ev.locked) {
            args.preventDefault();
            return;
        }
        const newEvent = {
            ...ev,
            start: args.newStart.toString("yyyy-MM-ddTHH:mm:ss"),
            end: args.newEnd.toString("yyyy-MM-ddTHH:mm:ss"),
        };
        fetch("/api/events/move", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                old_id: ev.id, old_day: ev.start.substring(0, 10),
                event: newEvent
            })
        }).then(r => r.json()).then(data => {
            if (data.ok) {
                args.e.data = data.event;
            }
            loadEvents();
        });
    };

    dp.onEventResized = function(args) {
        const ev = args.e.data;
        if (ev.locked) {
            args.preventDefault();
            return;
        }
        const newEvent = {
            ...ev,
            start: args.newStart.toString("yyyy-MM-ddTHH:mm:ss"),
            end: args.newEnd.toString("yyyy-MM-ddTHH:mm:ss"),
        };
        fetch("/api/events/resize", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                id: ev.id, day: ev.start.substring(0, 10),
                event: newEvent
            })
        }).then(r => r.json()).then(data => {
            if (data.ok) {
                args.e.data = data.event;
            }
            loadEvents();
        });
    };

    // --- Initial load ---
    function loadEvents() {
        const s = dp.visibleStart().toString("yyyy-MM-dd");
        const e = dp.visibleEnd().toString("yyyy-MM-dd");
        fetch("/api/events?start=" + s + "&end=" + e)
            .then(r => r.json())
            .then(events => {
                dp.events.list = events;
                dp.update();
                // Show empty guide if only holidays/markers (no user events)
                const userEvents = events.filter(function(ev) {
                    return ev.kind !== "marker" || ev.id.startsWith("marker-user-");
                });
                toggleEmptyGuide(userEvents.length === 0);
            });
    }

    dp.onBeforeCellRender = function(args) {
        const d = args.cell.start.toString("yyyy-MM-dd");
        // Mark holidays visually
    };

    dp.init();
    loadEvents();
    </script>
    """)

    # Side detail panel HTML
    ui.add_body_html("""
    <style>
        .event-done {
            opacity: 0.6;
            text-decoration: line-through;
        }
        #detail-panel h3 {
            color: #e94560;
            margin-top: 0;
        }
        #detail-panel label {
            display: block;
            margin-top: 12px;
            font-size: 13px;
            color: #888;
        }
        #detail-panel input, #detail-panel select {
            width: 100%;
            padding: 8px;
            margin-top: 4px;
            background: #16213e;
            color: #eee;
            border: 1px solid #0f3460;
            border-radius: 4px;
            font-size: 14px;
        }
        #detail-panel button {
            margin-top: 12px;
            padding: 8px 20px;
            background: #e94560;
            color: #fff;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        #detail-panel .close-btn {
            position: absolute;
            top: 10px;
            right: 10px;
            background: none;
            color: #e94560;
            font-size: 20px;
            padding: 4px 8px;
            cursor: pointer;
        }
    </style>
    <script>
    function showDetailPanel(ev) {
        const panel = document.getElementById("detail-panel");
        const isLocked = ev.locked || false;
        let html = `
            <span class="close-btn" onclick="hideDetailPanel()">&times;</span>
            <h3>${isLocked ? '🔒 ' : ''}事件详情</h3>
            <label>标题</label>
            <input id="dp-text" value="${ev.text || ''}" ${isLocked ? 'readonly' : ''}>
            <label>分类</label>
            <select id="dp-kind" ${isLocked ? 'disabled' : ''}>
                <option value="sop" ${ev.kind === 'sop' ? 'selected' : ''}>🟢 SOP</option>
                <option value="tool" ${ev.kind === 'tool' ? 'selected' : ''}>🔵 工具</option>
                <option value="reminder" ${ev.kind === 'reminder' ? 'selected' : ''}>⚪ 提醒</option>
                <option value="external" ${ev.kind === 'external' ? 'selected' : ''}>🟠 外部</option>
                <option value="marker" ${ev.kind === 'marker' ? 'selected' : ''}>🔴 标记</option>
            </select>
            <label>执行方式</label>
            <select id="dp-exec" ${isLocked ? 'disabled' : ''}>
                <option value="manual" ${ev.exec_mode === 'manual' ? 'selected' : ''}>手动打卡</option>
                <option value="auto" ${ev.exec_mode === 'auto' ? 'selected' : ''}>自动执行</option>
            </select>
            <label>来源项目</label>
            <input id="dp-source" value="${ev.source || ''}" placeholder="例如 citrinitas, nigredo" ${isLocked ? 'readonly' : ''}>
            ${!isLocked ? `<button onclick="saveEvent('${ev.id}', '${ev.start.substring(0, 10)}')">保存</button>` : ''}
            ${isLocked ? `<button onclick="unlockEvent('${ev.id}', '${ev.start.substring(0, 10)}')">🔓 解锁</button>` : ''}
            <hr style="border-color:#0f3460;margin-top:16px;">
            <label>当前状态</label>
            <div id="dp-status" style="margin-top:4px;">${ev.status || 'pending'}</div>
            <button onclick="toggleStatus('${ev.id}', '${ev.start.substring(0, 10)}', '${ev.status || 'pending'}')">
                ${ev.status === 'done' ? '↩️ 撤销打卡' : '✅ 打卡完成'}
            </button>
        `;
        panel.innerHTML = html;
        panel.style.display = "block";
    }

    function hideDetailPanel() {
        document.getElementById("detail-panel").style.display = "none";
    }

    function saveEvent(evId, day) {
        const text = document.getElementById("dp-text").value;
        const kind = document.getElementById("dp-kind").value;
        const exec = document.getElementById("dp-exec").value;
        const source = document.getElementById("dp-source").value;
        fetch("/api/events/update", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: evId, day, text, kind, exec_mode: exec, source})
        }).then(r => r.json()).then(() => {
            hideDetailPanel();
            loadEvents();
        });
    }

    function unlockEvent(evId, day) {
        fetch("/api/events/lock", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: evId, day, locked: false})
        }).then(r => r.json()).then(() => {
            hideDetailPanel();
            loadEvents();
        });
    }

    function toggleStatus(evId, day, currentStatus) {
        const newStatus = currentStatus === "done" ? "pending" : "done";
        fetch("/api/events/status", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: evId, day, status: newStatus})
        }).then(r => r.json()).then(() => {
            hideDetailPanel();
            loadEvents();
        });
    }

    function hideDetailPanel() {
        document.getElementById("detail-panel").style.display = "none";
    }
    </script>
    """)


# ====== API Endpoints ======

@app.get("/api/events")
def api_get_events(start: str = "", end: str = ""):
    """Return events in date range, with repeat expansion and holiday markers."""
    from datetime import date as date_cls
    try:
        s = date_cls.fromisoformat(start)
        e = date_cls.fromisoformat(end)
    except ValueError:
        return []

    # Load concrete events
    events = all_events_in_range(s, e)

    # Expand repeat templates
    schedules = read_schedules()
    for tpl in schedules.values():
        expanded = expand_repeat(tpl, s, e)
        events.extend(expanded)

    # Load holidays as marker events
    year = s.year
    holidays = load_holidays(year)
    if e.year != year:
        holidays.update(load_holidays(e.year))
    for day_str, info in holidays.items():
        d = date_cls.fromisoformat(day_str)
        if s <= d <= e:
            events.append({
                "id": f"holiday-{day_str}",
                "start": f"{day_str}T00:00:00",
                "end": f"{day_str}T23:59:59",
                "text": info["name"],
                "kind": "marker",
                "locked": True,
                "status": "done",
                "exec_mode": "manual",
                "backColor": "#F44336",
                "barColor": "#D32F2F",
            })

    # Load markers
    markers = read_markers()
    for m in markers:
        try:
            d = date_cls.fromisoformat(m["date"])
            if s <= d <= e:
                events.append({
                    "id": f"marker-{m.get('id', m['date'])}",
                    "start": f"{m['date']}T00:00:00",
                    "end": f"{m['date']}T23:59:59",
                    "text": m.get("name", ""),
                    "kind": "marker",
                    "locked": m.get("locked", True),
                    "status": "done",
                    "exec_mode": "manual",
                    "backColor": "#F44336",
                    "barColor": "#D32F2F",
                })
        except (ValueError, KeyError):
            continue

    # Add season/semester overlays (background events spanning the month)
    # Simple approach: add a note on the first day of each month
    for d in _date_range(s, e):
        if d.day == 1:
            overlays = get_season_overlays(d.year, d.month)
            for o in overlays:
                events.append({
                    "id": f"season-{d.year}-{d.month:02d}-{o}",
                    "start": f"{d.isoformat()}T00:00:00",
                    "end": f"{d.isoformat()}T01:00:00",
                    "text": f"{o}季" if len(o) == 1 else o,
                    "kind": "marker",
                    "locked": True,
                    "status": "done",
                    "exec_mode": "manual",
                    "backColor": "#9C27B0",
                    "barColor": "#7B1FA2",
                })

    return events


@app.get("/api/events/today")
def api_today():
    """Return today's events."""
    today = date.today()
    return api_get_events(start=today.isoformat(), end=today.isoformat())


@app.post("/api/events/create")
async def api_create_event(request: Request):
    """Create a new event."""
    data = await request.json()
    event = {
        "text": data.get("text", ""),
        "start": data.get("start", ""),
        "end": data.get("end", ""),
        "kind": data.get("kind", "reminder"),
        "exec_mode": data.get("exec_mode", "manual"),
        "source": data.get("source", ""),
        "sop_page": data.get("sop_page", ""),
        "status": data.get("status", "pending"),
        "locked": data.get("locked", False),
        "repeat": data.get("repeat", "none"),
        "repeat_until": data.get("repeat_until", ""),
        "preheat_interval": data.get("preheat_interval", 1),
        "preheat_anchor": data.get("preheat_anchor", ""),
        "tags": data.get("tags", []),
    }

    # If repeat mode set, store as template
    if event["repeat"] != "none":
        schedules = read_schedules()
        saved = save_event(event)
        schedules[saved["id"]] = saved
        write_schedules(schedules)
    else:
        saved = save_event(event)

    # Register auto-execution job if needed
    _register_auto_job(saved)

    return {"ok": True, "event": saved}


@app.post("/api/events/update")
async def api_update_event(request: Request):
    """Update event fields (for side panel editing)."""
    data = await request.json()
    ev_id = data.get("id", "")
    day_str = data.get("day", "")
    day = date.fromisoformat(day_str) if day_str else date.today()
    events = read_day(day)

    for ev in events:
        if ev.get("id") == ev_id:
            if ev.get("locked"):
                return {"ok": False, "error": "事件已锁定，不可编辑"}
            old_exec = ev.get("exec_mode")
            for field in ("text", "kind", "exec_mode", "source", "sop_page", "start", "end"):
                if field in data:
                    ev[field] = data[field]
            write_day(day, events)

            # Reschedule auto job if exec_mode or timing changed
            new_exec = ev.get("exec_mode")
            if old_exec != new_exec:
                if new_exec == "auto":
                    _register_auto_job(ev)
                else:
                    _unregister_auto_job(ev_id)
            elif new_exec == "auto":
                # Timing may have changed
                _unregister_auto_job(ev_id)
                _register_auto_job(ev)

            return {"ok": True, "event": ev}

    return {"ok": False, "error": "事件未找到"}


@app.post("/api/events/status")
async def api_toggle_status(request: Request):
    """Toggle event status (done ↔ pending)."""
    data = await request.json()
    ev_id = data.get("id", "")
    new_status = data.get("status", "pending")
    day_str = data.get("day", "")
    day = date.fromisoformat(day_str) if day_str else date.today()
    events = read_day(day)

    for ev in events:
        if ev.get("id") == ev_id:
            if ev.get("locked"):
                return {"ok": False, "error": "事件已锁定"}
            ev["status"] = new_status
            write_day(day, events)

            # Unregister auto job when marked done/skipped, re-register when reverting
            if ev.get("exec_mode") == "auto":
                if new_status == "done" or new_status == "skipped":
                    _unregister_auto_job(ev_id)
                elif new_status == "pending":
                    _register_auto_job(ev)
            return {"ok": True}

    # For repeat instances (_repeat_parent), try the parent template
    for ev in events:
        if ev.get("_repeat_parent") == ev_id or ev_id.startswith(ev.get("id", "") + "-"):
            if ev.get("locked"):
                return {"ok": False, "error": "重复事件已锁定"}
            ev["status"] = new_status
            write_day(day, events)
            return {"ok": True}

    return {"ok": False, "error": "事件未找到"}


@app.post("/api/events/delete")
async def api_delete_event(request: Request):
    """Delete an event."""
    data = await request.json()
    ev_id = data.get("id", "")
    day_str = data.get("day", "")
    ok = delete_event(ev_id, day_str)
    if ok:
        _unregister_auto_job(ev_id)
        return {"ok": True}
    # Also try as repeat instance
    day = date.fromisoformat(day_str) if day_str else date.today()
    events = read_day(day)
    for ev in events:
        if ev.get("_repeat_parent") == ev_id or ev_id.startswith(ev.get("id", "") + "-"):
            if ev.get("locked"):
                return {"ok": False, "error": "事件已锁定"}
            events.remove(ev)
            write_day(day, events)
            _unregister_auto_job(ev_id)
            return {"ok": True}
    return {"ok": False, "error": "事件未找到"}


@app.post("/api/events/move")
async def api_move_event(request: Request):
    """Move event (drag & drop) — deletes from old day, creates on new day."""
    data = await request.json()
    old_id = data.get("old_id", "")
    old_day = data.get("old_day", "")
    new_event = data.get("event", {})
    day_str = old_day or date.today().isoformat()
    day = date.fromisoformat(day_str)
    events = read_day(day)

    for ev in events:
        if ev.get("id") == old_id:
            if ev.get("locked"):
                return {"ok": False, "error": "事件已锁定，不可移动"}
            was_auto = ev.get("exec_mode") == "auto"
            events.remove(ev)
            write_day(day, events)
            if was_auto:
                _unregister_auto_job(old_id)
            break

    saved = save_event(new_event)
    if new_event.get("exec_mode") == "auto":
        _register_auto_job(saved)
    return {"ok": True, "event": saved}


@app.post("/api/events/resize")
async def api_resize_event(request: Request):
    """Resize event — update start/end times."""
    data = await request.json()
    ev_id = data.get("id", "")
    day_str = data.get("day", "")
    new_event = data.get("event", {})
    day = date.fromisoformat(day_str) if day_str else date.today()
    events = read_day(day)

    for ev in events:
        if ev.get("id") == ev_id:
            if ev.get("locked"):
                return {"ok": False, "error": "事件已锁定"}
            ev["start"] = new_event.get("start", ev["start"])
            ev["end"] = new_event.get("end", ev["end"])
            write_day(day, events)

            # Reschedule auto job if needed
            if ev.get("exec_mode") == "auto":
                _unregister_auto_job(ev_id)
                _register_auto_job(ev)

            return {"ok": True, "event": ev}

    return {"ok": False, "error": "事件未找到"}


@app.post("/api/events/lock")
async def api_lock_event(request: Request):
    """Toggle event lock state."""
    data = await request.json()
    ev_id = data.get("id", "")
    locked = data.get("locked", True)
    day_str = data.get("day", "")
    day = date.fromisoformat(day_str) if day_str else date.today()
    events = read_day(day)

    for ev in events:
        if ev.get("id") == ev_id:
            ev["locked"] = locked
            write_day(day, events)
            return {"ok": True}

    return {"ok": False, "error": "事件未找到"}


@app.post("/api/markers/create")
async def api_create_marker(request: Request):
    """Create a manual marker day (shopping festival, etc.)."""
    data = await request.json()
    markers = read_markers()
    import uuid
    marker = {
        "id": str(uuid.uuid4())[:8],
        "date": data.get("date", date.today().isoformat()),
        "name": data.get("name", ""),
        "locked": data.get("locked", True),
    }
    markers.append(marker)
    write_markers(markers)
    return {"ok": True, "marker": marker}


@app.get("/api/markers")
def api_get_markers():
    """Get all markers."""
    return read_markers()


# ====== SOP Pages ======

@ui.page("/sop/{name}")
def sop_page(name: str):
    """SOP workflow page — v0.3.0: stages + timer."""
    # CSS
    ui.add_head_html("""
    <style>
        .sop-container { max-width: 900px; margin: 0 auto; padding: 24px; color: #eee; }
        .sop-container h1 { color: #e94560; }
        .sop-container h2 { color: #e0e0e0; font-size: 1.1rem; margin: 28px 0 12px 0; }
        .sop-stage-header {
            background: #1a1a2e; border-left: 4px solid #e94560;
            border-radius: 6px; padding: 10px 16px; margin: 20px 0 0 0;
            font-weight: 600; font-size: 1rem; color: #e94560;
        }
        .sop-stage-header.pending { border-left-color: #9E9E9E; color: #9E9E9E; }
        .sop-step {
            background: #16213e; border: 1px solid #0f3460;
            border-radius: 8px; padding: 14px 16px; margin: 8px 0 0 20px;
            display: flex; align-items: center; justify-content: space-between;
            gap: 12px; transition: all 0.2s;
        }
        .sop-step.active { border-color: #2196F3; background: #1a2744; }
        .sop-step.done { border-color: #4CAF50; opacity: 0.8; }
        .sop-step-info { flex: 1; min-width: 0; }
        .sop-step-info .name { font-size: 0.95rem; font-weight: 500; }
        .sop-step-info .desc { font-size: 0.8rem; color: #8899aa; margin-top: 2px; }
        .mode-badge {
            display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 11px; font-weight: 500; margin-right: 8px;
        }
        .mode-badge.auto { background: #7B1FA2; color: #fff; }
        .mode-badge.manual { background: #F57C00; color: #fff; }
        .mode-badge.semi { background: #0288D1; color: #fff; }
        .sop-step-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .timer-display { font-size: 0.85rem; color: #4CAF50; font-weight: 500; min-width: 80px; text-align: right; }
        .top-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
        .order-info { font-size: 0.85rem; color: #8899aa; }
        .summary-bar {
            margin-top: 24px; padding: 12px 16px; background: #1a1a2e;
            border-radius: 8px; display: flex; align-items: center; justify-content: space-between;
        }
    </style>
    """)

    sop_label = {"kujiale": "酷家乐接单 SOP", "general": "通用 SOP"}.get(name, name)

    # Load SOP definition
    sop_file = SOPS_DIR / f"{name}.json"
    if not sop_file.exists():
        with ui.column().classes("sop-container"):
            ui.link("← 返回日历", "/")
            ui.label(f"「{sop_label}」SOP 尚未配置").classes("text-h5")
            ui.label("在 data/sops/ 目录下创建 JSON 文件即可定义环节")
        return

    try:
        sop_def = json.loads(sop_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        with ui.column().classes("sop-container"):
            ui.link("← 返回日历", "/")
            ui.label("SOP 定义文件格式错误").classes("text-negative")
        return

    # Check active order
    active_order = timelog.get_active_order(name)

    # Gather all steps into a flat list with stage info
    all_steps = []
    for stage in sop_def.get("stages", []):
        stage_name = stage.get("name", "")
        status = stage.get("status", "")
        for step in stage.get("steps", []):
            if step.get("id"):
                all_steps.append({
                    **step,
                    "stage_name": stage_name,
                    "stage_status": status,
                })

    # UI element references
    step_cards: dict[str, ui.card] = {}
    step_btns: dict[str, ui.button] = {}
    step_dur_labels: dict[str, ui.label] = {}
    step_info_labels: dict[str, ui.label] = {}

    with ui.column().classes("sop-container"):
        # Top bar
        with ui.row().classes("top-bar w-full"):
            ui.link("← 返回日历", "/")
            ui.link("📊 时间审计", f"/sop/{name}/stats")
            ui.space()
            if active_order:
                t = active_order["started_at"][:16].replace("T", " ")
                ui.label(f"本单开始：{t}").classes("order-info")
            else:
                ui.label("暂无活跃订单").classes("order-info")

        ui.label(sop_label).classes("text-h3 mb-4")

        # [Start new order] button
        new_order_btn = ui.button("🆕 开始新单", on_click=lambda: _start_new_order(name, sop_file))
        new_order_btn.visible = active_order is None

        # Build step UI for each stage
        current_stage = None
        for step_data in all_steps:
            sid = step_data["id"]
            stage_name = step_data.get("stage_name", "")

            # Stage header
            if stage_name != current_stage:
                current_stage = stage_name
                cls = "sop-stage-header pending" if step_data.get("stage_status") == "pending" else "sop-stage-header"
                ui.label(stage_name).classes(cls)

            # Get timelog step state
            tl_step = None
            if active_order:
                for s in active_order.get("steps", []):
                    if s["id"] == sid:
                        tl_step = s
                        break

            mode = step_data.get("mode", "manual")
            mode_text = {"auto": "自动", "manual": "手动", "semi": "半自动"}.get(mode, mode)
            is_started = tl_step and tl_step.get("started") is not None
            is_finished = tl_step and tl_step.get("duration_min") is not None
            has_button = mode in ("manual", "semi")
            is_auto = mode == "auto"

            # Determine card CSS class
            card_cls = "sop-step"
            if is_finished:
                card_cls += " done"
            elif is_started:
                card_cls += " active"

            with ui.card().classes(card_cls) as card:
                step_cards[sid] = card

                # Left: info
                with ui.column().classes("sop-step-info"):
                    with ui.row():
                        ui.label(f"{sid} {step_data['name']}").classes("name")
                        ui.label(mode_text).classes(f"mode-badge {mode}")
                    desc = step_data.get("description", "")
                    if desc:
                        ui.label(desc).classes("desc")

                # Right: actions
                with ui.row().classes("sop-step-actions"):
                    dur_label = ui.label("").classes("timer-display")
                    step_dur_labels[sid] = dur_label

                    if is_finished:
                        dur = tl_step["duration_min"]
                        dur_label.set_text(f"{dur} 分钟")
                        if has_button:
                            # Show a "done" indicator instead of button
                            ui.label("✓").classes("text-positive")
                    elif is_started:
                        dur_label.set_text("计时中...")
                        if has_button:
                            btn = ui.button("⏹ 完成", on_click=lambda sid=sid: _on_step_finish(sid, name))
                            step_btns[sid] = btn
                    else:
                        if has_button:
                            btn = ui.button("▶ 开始", on_click=lambda sid=sid: _on_step_start(sid, name))
                            step_btns[sid] = btn
                        if is_auto:
                            ui.label("—").classes("text-grey")

        # Bottom: summary + [完成本单]
        summary_label = ui.label("").classes("text-caption")
        finish_btn = ui.button("✅ 完成本单", on_click=lambda: _on_order_finish(name))
        finish_btn.visible = active_order is not None

        if active_order:
            _update_summary(active_order, summary_label)


# --- SOP callback helpers ---

def _start_new_order(sop_id: str, sop_file: Path):
    """Create a new order and refresh the page."""
    timelog.start_order(sop_id, sop_file)
    ui.notify("新单已开始！开始计时各环节", type="positive")
    ui.open(f"/sop/{sop_id}")


def _on_step_start(step_id: str, sop_id: str):
    """Handle [Start] button click."""
    order = timelog.get_active_order(sop_id)
    if not order:
        ui.notify("请先点击「开始新单」", type="warning")
        return
    timelog.start_step(order["order_id"], step_id)
    ui.open(f"/sop/{sop_id}")  # Refresh page to update UI


def _on_step_finish(step_id: str, sop_id: str):
    """Handle [Finish] button click."""
    order = timelog.get_active_order(sop_id)
    if not order:
        return
    result = timelog.finish_step(order["order_id"], step_id)
    if result:
        ui.notify(f"完成！用时 {result['duration_min']} 分钟", type="positive")
    ui.open(f"/sop/{sop_id}")


def _on_order_finish(sop_id: str):
    """Handle [Finish Order] button click."""
    order = timelog.get_active_order(sop_id)
    if not order:
        return
    timelog.finish_order(order["order_id"])
    total = sum(s.get("duration_min", 0) or 0 for s in order.get("steps", []))
    ui.notify(f"本单完成！总耗时 {total:.1f} 分钟", type="positive")
    ui.open(f"/sop/{sop_id}")


def _update_summary(order: dict, label: ui.label):
    """Update the bottom summary label with order stats."""
    done_count = sum(1 for s in order.get("steps", []) if s.get("duration_min") is not None)
    total_steps = len(order.get("steps", []))
    total_min = sum(s.get("duration_min", 0) or 0 for s in order.get("steps", []))
    label.set_text(f"已完成 {done_count}/{total_steps} 个步骤，累计耗时 {total_min:.1f} 分钟")


# ====== Stats Page ======

@ui.page("/sop/{name}/stats")
def sop_stats(name: str):
    """Time audit statistics page — v0.3.0."""
    sop_label = {"kujiale": "酷家乐接单 SOP", "general": "通用 SOP"}.get(name, name)

    ui.add_head_html("""
    <style>
        .stats-container { max-width: 900px; margin: 0 auto; padding: 24px; color: #eee; }
        .stats-container h1 { color: #e94560; }
        .stat-card {
            background: #16213e; border: 1px solid #0f3460;
            border-radius: 8px; padding: 16px;
        }
        .stat-table { width: 100%; border-collapse: collapse; margin: 12px 0; }
        .stat-table th {
            text-align: left; padding: 8px 12px; font-size: 0.8rem;
            color: #8899aa; border-bottom: 1px solid #0f3460;
        }
        .stat-table td {
            padding: 8px 12px; font-size: 0.9rem;
            border-bottom: 1px solid #0f3460;
        }
        .stat-table tr:hover td { background: #1a2744; }
        .bottleneck { color: #F44336; font-weight: 600; }
        .order-summary { font-size: 0.85rem; color: #8899aa; }
    </style>
    """)

    with ui.column().classes("stats-container"):
        with ui.row().classes("w-full items-center"):
            ui.link("← 返回 SOP", f"/sop/{name}")
            ui.space()
        ui.label(f"时间审计 — {sop_label}").classes("text-h3 mb-4")

        stats = timelog.get_step_stats(name)
        orders_summary = timelog.get_all_orders_summary(name)
        all_orders = timelog.get_all_orders(name)

        if not all_orders:
            ui.label("暂无数据，接单后回来查看").classes("text-caption")
            return

        total_orders = len(all_orders)
        finished_orders = sum(1 for o in all_orders if o.get("finished_at"))
        all_durations = []
        for o in all_orders:
            all_durations.extend(s.get("duration_min", 0) or 0 for s in o.get("steps", []))
        grand_total = sum(all_durations)

        with ui.row().classes("w-full gap-4"):
            with ui.card().classes("stat-card flex-1"):
                ui.label(f"{total_orders}").classes("text-h4")
                ui.label("总订单数").classes("text-caption")
            with ui.card().classes("stat-card flex-1"):
                ui.label(f"{finished_orders}").classes("text-h4")
                ui.label("已完成").classes("text-caption")
            with ui.card().classes("stat-card flex-1"):
                ui.label(f"{grand_total:.0f}").classes("text-h4")
                ui.label("累计耗时(分钟)").classes("text-caption")
            with ui.card().classes("stat-card flex-1"):
                avg = grand_total / total_orders if total_orders else 0
                ui.label(f"{avg:.0f}").classes("text-h4")
                ui.label("平均每单(分钟)").classes("text-caption")

        if stats:
            ui.label("各环节耗时统计").classes("text-h5 mt-6")
            with ui.card().classes("stat-card"):
                sorted_stats = sorted(stats.items(), key=lambda x: x[1].get("avg_min", 0), reverse=True)
                max_avg = sorted_stats[0][1].get("avg_min", 0) if sorted_stats else 0

                table_html = '<table class="stat-table"><tr><th>步骤</th><th>名称</th><th>执行次数</th><th>平均用时</th><th>最大用时</th><th>合计</th></tr>'
                for sid, s in sorted_stats:
                    is_bottleneck = s.get("avg_min", 0) >= max_avg * 0.7 and max_avg > 0
                    cls = 'bottleneck' if is_bottleneck else ''
                    table_html += (
                        f'<tr>'
                        f'<td>{sid}</td>'
                        f'<td>{s["name"]}</td>'
                        f'<td>{s["count"]}</td>'
                        f'<td class="{cls}">{s["avg_min"]} 分钟</td>'
                        f'<td>{s["max_min"]} 分钟</td>'
                        f'<td>{s["total_min"]} 分钟</td>'
                        f'</tr>'
                    )
                table_html += '</table>'
                ui.html(table_html)

        if orders_summary:
            ui.label("历史订单").classes("text-h5 mt-6")
            with ui.card().classes("stat-card"):
                for o in orders_summary:
                    t = o.get("finished_at") or o["started_at"]
                    t_short = t[:16].replace("T", " ") if t else "?"
                    status = "✅" if o.get("finished_at") else "🔄"
                    ui.label(
                        f"{status} {o['order_id']} — {t_short} — {o['step_count']} 步骤 — 总耗时 {o['total_min']} 分钟"
                    ).classes("order-summary")


# ====== Helper ======

def _date_range(start: date, end: date):
    """Yield dates from start to end inclusive."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ====== Startup ======

@ui.page("/sop/kujiale")
def sop_kujiale():
    sop_page("kujiale")


@ui.page("/sop/general")
def sop_general():
    sop_page("general")


# ====== Global Scheduler ======
_scheduler: Optional[AsyncIOScheduler] = None


def _get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler (lazy init for module import safety)."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        jobstore = SQLAlchemyJobStore(url="sqlite:///" + str(DATA_DIR / "scheduler.db"))
        _scheduler.add_jobstore(jobstore, alias="default")
    return _scheduler


async def _auto_mark_done(event_id: str, day_str: str):
    """Callback: mark an auto-exec event as done when end time is reached."""
    day = date.fromisoformat(day_str)
    events = read_day(day)
    for ev in events:
        if ev.get("id") == event_id and ev.get("status") == "pending":
            ev["status"] = "done"
            write_day(day, events)
            print(f"[Rubedo] 自动完成: {ev.get('text', event_id)}")
            return


def _register_auto_job(event: dict):
    """Register a scheduled job to auto-complete this event at its end time."""
    if event.get("exec_mode") != "auto":
        return
    if event.get("status") != "pending":
        return

    ev_id = event["id"]
    ev_start = event.get("start", "")
    if not ev_start:
        return

    try:
        end_dt = datetime.fromisoformat(event.get("end", ev_start))
    except ValueError:
        return

    # Don't schedule past events
    if end_dt <= datetime.now():
        return

    scheduler = _get_scheduler()
    if not scheduler.running:
        scheduler.start()

    job_id = f"auto-{ev_id}"
    day_str = ev_start[:10]

    try:
        scheduler.add_job(
            _auto_mark_done,
            trigger="date",
            run_date=end_dt,
            id=job_id,
            args=[ev_id, day_str],
            replace_existing=True,
        )
    except Exception as e:
        print(f"[Rubedo] 注册自动任务失败 ({ev_id}): {e}")


def _unregister_auto_job(event_id: str):
    """Remove a scheduled auto-complete job."""
    scheduler = _get_scheduler()
    job_id = f"auto-{event_id}"
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass  # Already removed or never existed
    except Exception as e:
        print(f"[Rubedo] 取消自动任务失败 ({event_id}): {e}")


def on_startup():
    """Initialize data files on first run."""
    # Ensure schedules.json exists
    sfp = DATA_DIR / "schedules.json"
    if not sfp.exists():
        sfp.write_text("{}", encoding="utf-8")

    # Ensure markers.json exists
    mfp = DATA_DIR / "markers.json"
    if not mfp.exists():
        mfp.write_text("[]", encoding="utf-8")

    # Start APScheduler (lazy init on first use)
    scheduler = _get_scheduler()
    if not scheduler.running:
        scheduler.start()
        print("[Rubedo] APScheduler 已启动 (SQLite 持久化)")

    print("[Rubedo] 数据目录初始化完成")


async def on_shutdown():
    """Clean up scheduler on app shutdown."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Rubedo] APScheduler 已关闭")


app.on_startup(on_startup)
app.on_shutdown(on_shutdown)


# ====== Main ======
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="凝华 · Rubedo",
        native=True,
        window_size=(1400, 900),
        port=8081,
        reload=False,
        show=True,
    )
