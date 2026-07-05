"""
Rubedo · 凝华 — 主页（日历页面）
"""

from nicegui import ui

from utils import DATA_DIR
from pathlib import Path
import time


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

    # ---- Navigation bar ----
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
        <div class="icon"></div>
        <div class="title">空空如也，等待你的第一个计划</div>
        <div class="hint">
            在日历上拖选时间段来创建新事项<br>
            点击事项查看详情<br>
            右键事项可快速标记完成、编辑或删除<br>
            试试创建你的第一条待办吧！
        </div>
    </div>
    """, sanitize=False)

    # ---- DayPilot init ----
    ui.add_body_html(f'<script src="/static/init.js?v={int(time.time())}"></script>')
