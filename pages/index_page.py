"""
Rubedo · 凝华 — 主页（日历页面）
上下分栏布局：上方日历，下方详情面板
"""

from nicegui import ui

from utils import DATA_DIR
from pathlib import Path
import time


@ui.page("/")
def index():
    """Main calendar page (DayPilot week view) with detail panel."""
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
        .main-layout {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        #calendar {
            width: calc(100% - 32px);
            flex: 1;
            margin: 16px;
            min-height: 0;
        }
        #detail-panel {
            display: none;
            background: #16213e;
            border-top: 1px solid #0f3460;
            overflow: auto;
            flex-shrink: 0;
        }
        #detail-panel.show {
            display: flex;
            flex-direction: column;
            height: 40vh;
        }
        #detail-loading {
            text-align: center;
            padding: 40px;
            color: #888;
        }
        #detail-content {
            padding: 20px;
        }
        .detail-header {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 16px 20px;
            border-bottom: 1px solid #0f3460;
        }
        .detail-title {
            font-size: 18px;
            font-weight: bold;
            color: #eee;
        }
        .detail-kind {
            font-size: 12px;
            padding: 4px 10px;
            border-radius: 12px;
            background: #0f3460;
            color: #e94560;
        }
        .detail-body {
            padding: 20px;
        }
        .detail-time {
            font-size: 14px;
            color: #aaa;
            margin-bottom: 12px;
        }
        .detail-desc {
            font-size: 14px;
            color: #ccc;
            line-height: 1.6;
            margin-bottom: 20px;
            padding: 12px;
            background: #1a1a2e;
            border-radius: 8px;
        }
        .detail-actions {
            display: flex;
            gap: 10px;
        }
        .detail-actions button {
            padding: 8px 16px;
            border: 1px solid #0f3460;
            border-radius: 6px;
            background: #0f3460;
            color: #eee;
            cursor: pointer;
            font-size: 13px;
        }
        .detail-actions button:hover {
            background: #e94560;
            color: #fff;
        }
        .nav-bar {
            display: flex; align-items: center; gap: 12px;
            padding: 8px 16px;
            background: #16213e;
            border-bottom: 1px solid #0f3460;
            flex-shrink: 0;
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

    # ---- Main layout（上下分栏）----
    ui.html("""<div class="main-layout">
        <div id="calendar"></div>
        <div id="detail-panel">
            <div id="detail-loading" style="display:none;text-align:center;padding:40px;color:#888;">
                ⏳ 加载中...
            </div>
            <div id="detail-content"></div>
        </div>
        <div id="empty-guide" class="empty-guide">
            <div class="icon">📅</div>
            <div class="title">空空如也，等待你的第一个计划</div>
            <div class="hint">
                在日历上拖选时间段来创建新事项<br>
                点击事项查看详情<br>
                右键事项可快速标记完成、编辑或删除<br>
                试试创建你的第一条待办吧！
            </div>
        </div>
    </div>""", sanitize=False)

    # ---- DayPilot init ----
    ui.add_body_html(f'<script src="/static/init.js?v={int(time.time())}"></script>')
