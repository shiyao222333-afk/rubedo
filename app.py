"""
Rubedo (凝华) — 副业操作系统
v0.2.0 平台基建：主界面 + 时间审计
"""

import os
import json
import logging
from datetime import date, datetime, timedelta

from nicegui import app, ui

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger

# ── 项目根目录 ──
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
SOPS_DIR = os.path.join(DATA_DIR, "sops")
TIMELOG_DIR = os.path.join(DATA_DIR, "timelog")
SCHEDULES_PATH = os.path.join(DATA_DIR, "schedules.json")

# ── 日历颜色方案 ──
COLOR_AUTO = {"back": "#7F77DD", "bar": "#534AB7"}   # 紫色 — 自动程序
COLOR_SOP  = {"back": "#4CAF50", "bar": "#388E3C"}   # 绿色 — SOP 工具包


# ═══════════════════════════════════════════════════════════════
# 数据层 (T3)
# ═══════════════════════════════════════════════════════════════

def load_events_for_range(start_str: str, end_str: str) -> list[dict]:
    """读取指定日期范围内所有事件（每日文件 + 重复事件展开）"""
    events = []
    try:
        start_dt = datetime.fromisoformat(start_str)
        end_dt = datetime.fromisoformat(end_str)
    except ValueError:
        return events

    # 1. 读取每日 JSON 事件
    d = start_dt.date()
    end_date = end_dt.date()
    while d <= end_date:
        fpath = os.path.join(DATA_DIR, f"{d.isoformat()}.json")
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    day_events = json.load(f)
                    if isinstance(day_events, list):
                        events.extend(day_events)
            except (json.JSONDecodeError, OSError):
                pass
        d += timedelta(days=1)

    # 2. 展开重复事件（schedules 展开的实例若已有覆盖则自动使用覆盖版）
    schedule_instances = expand_schedules(start_str, end_str)

    # 合并：每日 JSON 中的事件优先（覆盖 schedules 生成的实例）
    existing_ids = {e["id"] for e in events}
    for si in schedule_instances:
        if si["id"] not in existing_ids:
            events.append(si)

    return events


def load_events_for_today() -> list[dict]:
    """读取今日事件"""
    today = date.today().isoformat()
    fpath = os.path.join(DATA_DIR, f"{today}.json")
    if not os.path.exists(fpath):
        return []
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_event(event: dict):
    """保存单个事件到对应日期的 JSON 文件"""
    event_date = event["start"][:10]
    fpath = os.path.join(DATA_DIR, f"{event_date}.json")

    existing = []
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []

    # 更新或追加
    updated = False
    for i, e in enumerate(existing):
        if e.get("id") == event["id"]:
            existing[i] = event
            updated = True
            break
    if not updated:
        existing.append(event)

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def delete_event(event_id: str, event_date: str):
    """删除事件"""
    fpath = os.path.join(DATA_DIR, f"{event_date}.json")
    if not os.path.exists(fpath):
        return
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing = [e for e in existing if e.get("id") != event_id]
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, OSError):
        pass


# ── 重复事件模板 (T6) ──

def load_schedules() -> list[dict]:
    """读取重复事件模板"""
    if not os.path.exists(SCHEDULES_PATH):
        return []
    try:
        with open(SCHEDULES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_schedules(schedules: list[dict]):
    """保存重复事件模板"""
    with open(SCHEDULES_PATH, "w", encoding="utf-8") as f:
        json.dump(schedules, f, ensure_ascii=False, indent=2)


def expand_schedules(start_str: str, end_str: str) -> list[dict]:
    """展开重复事件模板为指定日期范围内的具体事件"""
    schedules = load_schedules()
    if not schedules:
        return []

    try:
        range_start = datetime.fromisoformat(start_str).date()
        range_end = datetime.fromisoformat(end_str).date()
    except ValueError:
        return []

    expanded = []
    for sched in schedules:
        # 解析锚点时间（模板中 start/end 的时间部分作为每天的时段）
        anchor_start = datetime.fromisoformat(sched["start"])
        anchor_end = datetime.fromisoformat(sched["end"])
        duration = anchor_end - anchor_start

        repeat_type = sched.get("repeat", "none")
        sched_id = sched["id"]
        tags = sched.get("tags", {})

        d = range_start
        while d <= range_end:
            if _matches_repeat(repeat_type, anchor_start.date(), d):
                instance_id = f"sched-{sched_id}-{d.isoformat()}"

                # 检查是否有单次覆盖
                override = _load_override(instance_id, d)
                if override is not None:
                    expanded.append(override)
                else:
                    event_start = datetime(d.year, d.month, d.day,
                                           anchor_start.hour, anchor_start.minute,
                                           anchor_start.second)
                    event_end = event_start + duration
                    expanded.append({
                        "id": instance_id,
                        "start": event_start.isoformat(),
                        "end": event_end.isoformat(),
                        "text": sched["text"],
                        "tags": tags,
                        "scheduleId": sched_id
                    })
            d += timedelta(days=1)

    return expanded


def _matches_repeat(repeat_type: str, anchor_date, target_date) -> bool:
    """判断目标日期是否匹配重复规则"""
    if repeat_type == "daily":
        return True
    elif repeat_type == "weekly":
        # 每周同一天（星期几相同）
        return target_date.weekday() == anchor_date.weekday()
    elif repeat_type == "weekday":
        # 工作日（周一至周五）
        return target_date.weekday() < 5
    elif repeat_type == "monthly":
        # 每月同一天（号数相同）
        return target_date.day == anchor_date.day
    return False


def _load_override(instance_id: str, target_date) -> dict | None:
    """检查某天是否有该 schedule 实例的覆盖版本"""
    fpath = os.path.join(DATA_DIR, f"{target_date.isoformat()}.json")
    if not os.path.exists(fpath):
        return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            day_events = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    for evt in day_events:
        if evt.get("id") == instance_id:
            return evt
    return None


# ── 全局计时器状态 (T7) ──

class TimeTracker:
    """全局计时器：追踪当前任务耗时"""
    def __init__(self):
        self.task_name = ""
        self.start_time: datetime | None = None
        self.accumulated_seconds = 0.0
        self.running = False
        self.paused = False
        self.started_at: datetime | None = None  # 首次开始时间（用于记录）

    @property
    def elapsed_seconds(self) -> float:
        if self.running and not self.paused and self.start_time:
            return self.accumulated_seconds + (datetime.now() - self.start_time).total_seconds()
        return self.accumulated_seconds

    @property
    def elapsed_str(self) -> str:
        total = int(self.elapsed_seconds)
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def start(self, task_name: str):
        self.task_name = task_name
        self.started_at = datetime.now()
        self.start_time = datetime.now()
        self.accumulated_seconds = 0.0
        self.running = True
        self.paused = False

    def pause(self):
        if self.running and not self.paused and self.start_time:
            self.accumulated_seconds += (datetime.now() - self.start_time).total_seconds()
            self.start_time = None
            self.paused = True

    def resume(self):
        if self.running and self.paused:
            self.start_time = datetime.now()
            self.paused = False

    def stop(self) -> dict:
        """停止计时，返回 timelog 记录"""
        if self.running:
            if not self.paused and self.start_time:
                self.accumulated_seconds += (datetime.now() - self.start_time).total_seconds()
        record = {
            "id": f"tl-{int(datetime.now().timestamp())}",
            "taskName": self.task_name,
            "startedAt": self.started_at.isoformat() if self.started_at else "",
            "endedAt": datetime.now().isoformat(),
            "durationMin": round(self.accumulated_seconds / 60, 1),
            "revenue": 0,
            "hourlyRate": 0,
        }
        self.reset()
        return record

    def reset(self):
        self.task_name = ""
        self.start_time = None
        self.accumulated_seconds = 0.0
        self.running = False
        self.paused = False
        self.started_at = None


timer_tracker = TimeTracker()


def save_timelog(entry: dict):
    """保存计时记录到当日 timelog 文件"""
    today = date.today().isoformat()
    fpath = os.path.join(TIMELOG_DIR, f"{today}.json")
    existing = []
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []

    existing.append(entry)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# 主页面：时间日程日历
# ═══════════════════════════════════════════════════════════════

@ui.page("/")
def home():
    """主界面 — 周视图时间日程表"""

    # ── 加载 DayPilot CSS + JS (CDN) ──
    ui.add_head_html("""
    <link rel="stylesheet" href="https://javascript.daypilot.org/daypilot-all.min.css">
    <script src="https://javascript.daypilot.org/daypilot-all.min.js" defer></script>
    <style>
        /* 日立高度适配 */
        .dp-calendar-container { width: 100%; height: calc(100vh - 50px - 40px); }
        /* 自定义右键菜单 */
        .rubedo-context-item { padding: 6px 16px; cursor: pointer; font-size: 13px; }
        .rubedo-context-item:hover { background: #f0f0f0; }
        /* 重置按钮样式 */
        .rubedo-timer-btn { transition: all 0.2s; }
        .rubedo-timer-btn:hover { transform: scale(1.05); }
    </style>
    """)

    # ── 页面顶部 ──
    with ui.header(elevated=True).classes("bg-indigo-900"):
        ui.label("凝华 · Rubedo").classes("text-lg font-bold")
        ui.space()
        ui.label("").classes("text-sm opacity-70").bind_text_from(
            target_obj=None  # placeholder, updated by timer below
        )

    # ── 日历容器 ──
    ui.html("""
    <div class="dp-calendar-container">
        <div id="dp" style="width:100%; height:100%;"></div>
    </div>
    """)

    # ── DayPilot 初始化脚本 ──
    ui.add_body_html("""
    <script>
    (function() {
        function initCalendar() {
            if (typeof DayPilot === 'undefined') {
                // CDN 加载失败降级提示
                const dpEl = document.getElementById('dp');
                if (dpEl && !dpEl.querySelector('.rubedo-error')) {
                    dpEl.innerHTML = 
                        '<div class="rubedo-error" style="color:#e57373; text-align:center; padding-top:200px;">' +
                        '<p style="font-size:48px; margin-bottom:16px;">🔌</p>' +
                        '<p style="font-size:18px; font-weight:bold;">无法加载日历组件</p>' +
                        '<p style="font-size:14px; color:#999; margin-top:8px;">请检查网络连接后重启应用</p>' +
                        '<p style="font-size:12px; color:#666; margin-top:4px;">若持续出现此问题，请确认能访问 javascript.daypilot.org</p>' +
                        '</div>';
                }
                // 继续重试（最多 10 次约 1 秒）
                if (!window.__rubedo_dp_retries) window.__rubedo_dp_retries = 0;
                window.__rubedo_dp_retries++;
                if (window.__rubedo_dp_retries < 10) {
                    setTimeout(initCalendar, 100);
                }
                return;
            }

            window.__rubedo_nav = null;

            const dp = new DayPilot.Calendar("dp", {
                viewType: "Week",
                cellDuration: 30,
                cellHeight: 30,
                dayBeginsHour: 0,
                dayEndsHour: 24,
                timeRangeSelectedHandling: "Enabled",
                eventDeleteHandling: "Update",
                eventMoveHandling: "Update",
                eventResizeHandling: "Update",
                onTimeRangeSelected: async function(args) {
                    // 第一步：输入名称
                    const modal = await DayPilot.Modal.prompt(
                        "新建事项", 
                        "请输入事项名称：",
                        { okText: "继续 →", cancelText: "取消" }
                    );
                    if (modal.canceled) return;
                    if (!modal.result || !modal.result.trim()) return;

                    const eventText = modal.result.trim();
                    const eventStart = args.start.toString("yyyy-MM-ddTHH:mm:ss");
                    const eventEnd = args.end.toString("yyyy-MM-ddTHH:mm:ss");
                    const baseId = "evt-" + Date.now();

                    // 第二步：选择是否重复
                    const repeatModal = await DayPilot.Modal.prompt(
                        "重复事件", 
                        "输入重复方式（留空 = 不重复）：\n" +
                        "daily = 每天  |  weekly = 每周\n" +
                        "weekday = 工作日(周一~五)  |  monthly = 每月",
                        { okText: "创建", cancelText: "跳过（不重复）" }
                    );

                    const repeatType = repeatModal.canceled ? "" : (repeatModal.result || "").trim().toLowerCase();
                    const validRepeats = ["daily", "weekly", "weekday", "monthly"];

                    if (validRepeats.includes(repeatType)) {
                        // 创建重复事件模板
                        const schedule = {
                            id: baseId,
                            start: eventStart,
                            end: eventEnd,
                            text: eventText,
                            repeat: repeatType,
                            tags: { type: "sop", sopPage: "kujiale", sopId: baseId, status: "pending" }
                        };

                        await fetch('/api/schedules', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(schedule)
                        });

                        // 重新加载日历事件（让后端展开 schedule）
                        loadEvents();
                    } else {
                        // 创建一次性事件
                        const newEvent = {
                            id: baseId,
                            start: eventStart,
                            end: eventEnd,
                            text: eventText,
                            tags: { type: "sop", sopPage: "kujiale", sopId: baseId, status: "pending" }
                        };

                        await fetch('/api/events', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(newEvent)
                        });

                        dp.events.list.push(newEvent);
                        dp.update();
                    }
                },
                onEventClick: function(args) {
                    const tags = args.e.tags || {};
                    window.__rubedo_nav = {
                        page: tags.sopPage || "general",
                        id: tags.sopId || args.e.id
                    };
                },
                onEventMoved: async function(args) {
                    const evt = args.e;
                    const updated = {
                        id: evt.id,
                        start: evt.start.toString("yyyy-MM-ddTHH:mm:ss"),
                        end: evt.end.toString("yyyy-MM-ddTHH:mm:ss"),
                        text: evt.text,
                        tags: evt.tags
                    };
                    await fetch('/api/events', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(updated)
                    });
                },
                onEventResized: async function(args) {
                    const evt = args.e;
                    const updated = {
                        id: evt.id,
                        start: evt.start.toString("yyyy-MM-ddTHH:mm:ss"),
                        end: evt.end.toString("yyyy-MM-ddTHH:mm:ss"),
                        text: evt.text,
                        tags: evt.tags
                    };
                    await fetch('/api/events', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(updated)
                    });
                },
                onBeforeEventRender: function(args) {
                    const tags = args.data.tags || {};
                    if (tags.type === "auto") {
                        args.data.backColor = "#7F77DD";
                        args.data.barColor = "#534AB7";
                    } else {
                        args.data.backColor = "#4CAF50";
                        args.data.barColor = "#388E3C";
                    }
                }
            });

            // ── 右键菜单 ──
            const contextMenu = new DayPilot.Menu({
                items: [
                    {
                        text: "✓ 完成",
                        onclick: function(args) {
                            args.source.tags.status = "done";
                            dp.update();
                            // 更新后端
                            fetch('/api/events', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({
                                    id: args.source.id,
                                    start: args.source.start.toString("yyyy-MM-ddTHH:mm:ss"),
                                    end: args.source.end.toString("yyyy-MM-ddTHH:mm:ss"),
                                    text: args.source.text,
                                    tags: args.source.tags
                                })
                            });
                        }
                    },
                    {
                        text: "⏭ 跳过",
                        onclick: function(args) {
                            args.source.tags.status = "skipped";
                            args.source.backColor = "#9e9e9e";
                            dp.update();
                        }
                    },
                    { text: "-" },
                    {
                        text: "✎ 编辑",
                        onclick: async function(args) {
                            const modal = await DayPilot.Modal.prompt(
                                "编辑事项",
                                "修改名称：",
                                { okText: "保存", cancelText: "取消", defaultValue: args.source.text }
                            );
                            if (modal.canceled || !modal.result) return;
                            args.source.text = modal.result.trim();
                            dp.update();
                            fetch('/api/events', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({
                                    id: args.source.id,
                                    start: args.source.start.toString("yyyy-MM-ddTHH:mm:ss"),
                                    end: args.source.end.toString("yyyy-MM-ddTHH:mm:ss"),
                                    text: args.source.text,
                                    tags: args.source.tags
                                })
                            });
                        }
                    },
                    {
                        text: "✕ 删除",
                        onclick: function(args) {
                            if (!confirm("确定删除「" + args.source.text + "」？")) return;
                            const dateStr = args.source.start.toString("yyyy-MM-dd");
                            fetch('/api/events/delete', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({
                                    id: args.source.id,
                                    date: dateStr
                                })
                            });
                            dp.events.list = dp.events.list.filter(
                                e => e.id !== args.source.id
                            );
                            dp.update();
                        }
                    }
                ]
            });
            dp.contextMenu = contextMenu;

            // ── 加载事件 ──
            function loadEvents() {
                const start = dp.visibleStart().toString("yyyy-MM-ddTHH:mm:ss");
                const end = dp.visibleEnd().toString("yyyy-MM-ddTHH:mm:ss");

                fetch(`/api/events?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`)
                    .then(r => r.json())
                    .then(events => {
                        dp.events.list = events;
                        dp.update();

                        // 空日历引导 (T8)
                        if (events.length === 0) {
                            const dpEl = document.getElementById('dp');
                            if (dpEl) {
                                const existing = dpEl.querySelector('.rubedo-welcome');
                                if (!existing) {
                                    const welcome = document.createElement('div');
                                    welcome.className = 'rubedo-welcome';
                                    welcome.style.cssText = 'position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); text-align:center; pointer-events:none;';
                                    welcome.innerHTML = 
                                        '<p style="font-size:36px; margin-bottom:12px;">📅</p>' +
                                        '<p style="font-size:16px; color:#bbb; font-weight:bold;">暂无日程安排</p>' +
                                        '<p style="font-size:13px; color:#999; margin-top:4px;">点击任意时间段创建你的第一个事项</p>' +
                                        '<p style="font-size:12px; color:#777; margin-top:8px;">支持创建重复事件：每天 / 每周 / 工作日 / 每月</p>';
                                    dpEl.style.position = 'relative';
                                    dpEl.appendChild(welcome);
                                }
                            }
                        } else {
                            // 有事件时移除引导
                            const existing = document.getElementById('dp').querySelector('.rubedo-welcome');
                            if (existing) existing.remove();
                        }
                    })
                    .catch(err => {
                        console.error("加载事件失败:", err);
                        document.getElementById("dp").innerHTML = 
                            '<p style="color:#999; text-align:center; padding-top:200px;">⚠ 无法加载日历数据<br><small>请检查应用是否正常运行</small></p>';
                    });
            }

            dp.onAfterRender = function() {
                if (dp.events.list.length === 0) {
                    loadEvents();
                }
            };

            dp.init();
            loadEvents();

            window.__dp = dp;
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initCalendar);
        } else {
            initCalendar();
        }
    })();
    </script>
    """)

    # ── 导航桥：JS → Python (T5) ──
    async def check_navigation():
        result = await ui.run_javascript("""
            if (window.__rubedo_nav) {
                const nav = window.__rubedo_nav;
                window.__rubedo_nav = null;
                return JSON.stringify(nav);
            }
            return null;
        """)
        if result and result != "null":
            try:
                nav = json.loads(result)
                page = nav.get("page", "general")
                sop_id = nav.get("id", "")
                ui.navigate.to(f"/sop/{page}?id={sop_id}")
            except (json.JSONDecodeError, KeyError):
                pass

    ui.timer(0.5, check_navigation)

    # ── 底部计时器栏 (T7) ──
    with ui.footer().classes("bg-gray-900 text-white p-2"):
        with ui.row().classes("items-center gap-3 w-full flex-nowrap"):

            # 状态图标 + 任务名
            timer_icon = ui.label("⏱").classes("text-lg")
            timer_label = ui.label("无计时任务").classes("text-sm opacity-60")

            # 耗时显示
            timer_display = ui.label("00:00:00").classes("font-mono text-lg font-bold text-green-400")

            # 任务名输入框（空闲时显示）
            def update_task_input_visibility():
                is_idle = not timer_tracker.running
                task_input.set_visibility(is_idle)
                action_btn.set_visibility(is_idle)
                pause_btn.set_visibility(False)
                stop_btn.set_visibility(False)
                resume_btn.set_visibility(False)
                timer_display.set_visibility(not is_idle)

            task_input = ui.input("任务名", value="").props("dense dark").classes("w-48")
            task_input.set_visibility(True)

            # 操作按钮
            action_btn = ui.button("▶ 开始", on_click=lambda: None).props("flat size=sm color=green").classes("rubedo-timer-btn")
            pause_btn = ui.button("⏸ 暂停", on_click=lambda: None).props("flat size=sm color=amber").classes("rubedo-timer-btn")
            pause_btn.set_visibility(False)
            resume_btn = ui.button("▶ 继续", on_click=lambda: None).props("flat size=sm color=green").classes("rubedo-timer-btn")
            resume_btn.set_visibility(False)
            stop_btn = ui.button("■ 结束", on_click=lambda: None).props("flat size=sm color=red").classes("rubedo-timer-btn")
            stop_btn.set_visibility(False)

            ui.space()

            # ── 收入输入对话框 ──
            revenue_dialog = ui.dialog()
            with revenue_dialog, ui.card().classes("p-4"):
                ui.label("输入本单收入").classes("text-lg font-bold mb-2")
                revenue_input = ui.number("收入金额 (¥)", value=0, min=0).props("autofocus")
                ui.label("").classes("text-xs text-gray-400").bind_text_from(
                    revenue_input, backward=lambda v: f"预计时薪: ¥{_calc_hourly(v, timer_tracker.elapsed_seconds)}/小时" if v else ""
                )
                with ui.row().classes("gap-2 mt-3"):
                    ui.button("取消", on_click=lambda: revenue_dialog.close()).props("flat")
                    ui.button("✅ 确认保存", on_click=lambda: _save_timelog_with_revenue()).props("color=green")

            # ── 按钮回调 ──
            def on_start():
                name = (task_input.value or "").strip()
                if not name:
                    ui.notify("请输入任务名称", type="warning", position="bottom")
                    return
                timer_tracker.start(name)
                timer_label.set_text(name)
                timer_label.classes("text-sm text-white")
                timer_display.set_text("00:00:00")
                task_input.set_visibility(False)
                action_btn.set_visibility(False)
                pause_btn.set_visibility(True)
                stop_btn.set_visibility(True)
                resume_btn.set_visibility(False)
                timer_display.set_visibility(True)

            def on_pause():
                timer_tracker.pause()
                pause_btn.set_visibility(False)
                resume_btn.set_visibility(True)

            def on_resume():
                timer_tracker.resume()
                pause_btn.set_visibility(True)
                resume_btn.set_visibility(False)

            def on_stop():
                timer_tracker.pause()  # 先暂停计时
                pause_btn.set_visibility(False)
                resume_btn.set_visibility(False)
                revenue_input.value = 0
                revenue_dialog.open()

            def _save_timelog_with_revenue():
                record = timer_tracker.stop()
                rev = revenue_input.value or 0
                record["revenue"] = rev
                dur_hours = record["durationMin"] / 60 if record["durationMin"] > 0 else 0
                record["hourlyRate"] = round(rev / dur_hours, 1) if dur_hours > 0 else 0
                save_timelog(record)
                revenue_dialog.close()
                # 恢复空闲状态
                timer_label.set_text("无计时任务")
                timer_label.classes("text-sm opacity-60")
                timer_display.set_text("00:00:00")
                update_task_input_visibility()
                ui.notify(
                    f"已保存: {record['taskName']} | {record['durationMin']}分钟 | ¥{rev} | 时薪¥{record['hourlyRate']}/h",
                    type="positive", position="bottom", timeout=3000
                )

            def _calc_hourly(revenue_val, seconds):
                if not seconds or seconds <= 0:
                    return "0.00"
                return round(revenue_val / (seconds / 3600), 2)

            action_btn.on("click", on_start)
            pause_btn.on("click", on_pause)
            resume_btn.on("click", on_resume)
            stop_btn.on("click", on_stop)

            # ── 计时刷新 (每 0.5s 更新显示) ──
            timer_tick = ui.timer(0.5, lambda: (
                timer_display.set_text(timer_tracker.elapsed_str)
                if timer_tracker.running else None
            ))
            timer_tick.active = True


# ═══════════════════════════════════════════════════════════════
# SOP 页面
# ═══════════════════════════════════════════════════════════════

@ui.page("/sop/kujiale")
def sop_kujiale(sop_id: str = ""):
    """酷家乐 SOP 页面"""
    with ui.header(elevated=True).classes("bg-green-800"):
        ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props("flat")
        ui.label("酷家乐 SOP — 需求确认").classes("text-lg font-bold")
        ui.space()
        if sop_id:
            ui.label(f"#{sop_id}").classes("text-sm opacity-70")

    with ui.column().classes("p-4"):
        ui.label("酷家乐 SOP 流程").classes("text-xl font-bold")
        ui.separator()
        ui.label("即将在 v0.3.0 实装").classes("text-gray-500 mt-4")


@ui.page("/sop/general")
def sop_general(sop_id: str = ""):
    """通用 SOP 页面"""
    with ui.header(elevated=True).classes("bg-gray-800"):
        ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props("flat")
        ui.label("通用任务").classes("text-lg font-bold")

    with ui.column().classes("p-4"):
        ui.label("通用 SOP 页面").classes("text-xl font-bold")
        ui.separator()
        ui.label("即将在 v0.3.0 实装").classes("text-gray-500 mt-4")


# ═══════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════

@app.get("/api/events")
def api_events(start: str = "", end: str = ""):
    """返回日历事件数据 (DayPilot 格式)"""
    return load_events_for_range(start, end)


@app.post("/api/events")
async def api_events_create(request: dict):
    """创建/更新事件"""
    save_event(request)
    return {"ok": True}


@app.post("/api/events/delete")
async def api_events_delete(request: dict):
    """删除事件"""
    event_id = request.get("id", "")
    event_date = request.get("date", date.today().isoformat())
    delete_event(event_id, event_date)
    return {"ok": True}


@app.get("/api/schedules")
def api_schedules():
    """返回所有重复事件模板"""
    return load_schedules()


@app.post("/api/schedules")
async def api_schedules_create(request: dict):
    """创建/更新重复事件模板"""
    schedules = load_schedules()
    sched_id = request.get("id", "")
    if not sched_id:
        return {"ok": False, "error": "缺少 id"}

    # 更新或追加
    updated = False
    for i, s in enumerate(schedules):
        if s.get("id") == sched_id:
            schedules[i] = request
            updated = True
            break
    if not updated:
        schedules.append(request)

    save_schedules(schedules)
    sync_schedules_to_scheduler()  # 同步 APScheduler
    return {"ok": True}


@app.post("/api/schedules/delete")
async def api_schedules_delete(request: dict):
    """删除重复事件模板"""
    sched_id = request.get("id", "")
    schedules = [s for s in load_schedules() if s.get("id") != sched_id]
    save_schedules(schedules)
    sync_schedules_to_scheduler()  # 同步 APScheduler
    return {"ok": True}


@app.get("/api/timelog/today")
def api_timelog_today():
    """返回今日时间审计数据"""
    today = date.today().isoformat()
    fpath = os.path.join(TIMELOG_DIR, f"{today}.json")
    if not os.path.exists(fpath):
        return {"entries": [], "total_hours": 0, "total_revenue": 0, "avg_hourly_rate": 0}
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"entries": [], "total_hours": 0, "total_revenue": 0, "avg_hourly_rate": 0}

    entries = entries if isinstance(entries, list) else []
    total_min = sum(e.get("durationMin", 0) for e in entries)
    total_rev = sum(e.get("revenue", 0) for e in entries)
    return {
        "entries": entries,
        "total_hours": round(total_min / 60, 1),
        "total_revenue": total_rev,
        "avg_hourly_rate": round(total_rev / (total_min / 60), 1) if total_min > 0 else 0
    }


# ═══════════════════════════════════════════════════════════════
# APScheduler 持久化 (T8)
# ═══════════════════════════════════════════════════════════════

scheduler_db = os.path.join(DATA_DIR, "scheduler.db")

scheduler = AsyncIOScheduler()
scheduler.add_jobstore(
    SQLAlchemyJobStore(url=f"sqlite:///{scheduler_db}"),
    "default",
)

# 日志（避免 APScheduler 刷屏）
logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _schedule_to_cron(sched: dict) -> dict | None:
    """将 schedules.json 模板转为 cron 参数字典"""
    anchor = datetime.fromisoformat(sched["start"])
    repeat = sched.get("repeat", "")
    if repeat == "daily":
        return {"hour": anchor.hour, "minute": anchor.minute}
    elif repeat == "weekly":
        return {"day_of_week": anchor.strftime("%a").lower(), "hour": anchor.hour, "minute": anchor.minute}
    elif repeat == "weekday":
        return {"day_of_week": "mon-fri", "hour": anchor.hour, "minute": anchor.minute}
    elif repeat == "monthly":
        return {"day": anchor.day, "hour": anchor.hour, "minute": anchor.minute}
    return None


async def _on_schedule_trigger(sched_id: str, text: str):
    """定时触发的回调（v0.2.0 仅记录日志，v0.3.0+ 连接自动执行）"""
    print(f"[APScheduler] 🔔 定时触发: {text} (ID: {sched_id}) — {datetime.now():%H:%M:%S}")


def sync_schedules_to_scheduler():
    """将 schedules.json 同步到 APScheduler（新增/更新/删除 job）"""
    schedules = load_schedules()
    existing_jobs = {j.id for j in scheduler.get_jobs()}

    for sched in schedules:
        cron_fields = _schedule_to_cron(sched)
        if not cron_fields:
            continue
        job_id = f"rubedo-{sched['id']}"
        # 更新：重调度触发器 + 更新参数
        if job_id in existing_jobs:
            try:
                scheduler.reschedule_job(job_id, trigger=CronTrigger(**cron_fields))
                scheduler.modify_job(job_id, args=[sched["id"], sched["text"]])
            except Exception as e:
                print(f"[APScheduler] 更新 job 失败 {job_id}: {e}")
        else:
            try:
                scheduler.add_job(
                    _on_schedule_trigger,
                    trigger=CronTrigger(**cron_fields),
                    id=job_id,
                    args=[sched["id"], sched["text"]],
                    misfire_grace_time=300,
                    coalesce=True,
                    replace_existing=True,
                )
            except Exception as e:
                print(f"[APScheduler] 添加 job 失败 {job_id}: {e}")
        existing_jobs.discard(job_id)

    # 删除已移除的 schedule
    for job_id in existing_jobs:
        if job_id.startswith("rubedo-"):
            try:
                scheduler.remove_job(job_id)
            except Exception as e:
                print(f"[APScheduler] 删除 job 失败 {job_id}: {e}")


# ═══════════════════════════════════════════════════════════════
# 全局配置 + 启动
# ═══════════════════════════════════════════════════════════════

@app.on_startup
def on_startup():
    """应用启动初始化"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SOPS_DIR, exist_ok=True)
    os.makedirs(TIMELOG_DIR, exist_ok=True)

    # 启动 APScheduler
    if not scheduler.running:
        scheduler.start()
        sync_schedules_to_scheduler()
        print(f"[APScheduler] 调度器已启动，数据库: {scheduler_db}")


@app.on_shutdown
def on_shutdown():
    """应用关闭清理"""
    if scheduler.running:
        scheduler.shutdown(wait=False)


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="凝华 · Rubedo",
        host="127.0.0.1",
        port=8081,
        native=True,
        reload=False,
        show=False,
    )
