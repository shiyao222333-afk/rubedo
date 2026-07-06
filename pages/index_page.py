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
            overflow: hidden;
        }
        #calendar {
            flex: 1;
            min-height: 0;
            overflow: hidden;
        }
        #detail-panel {
            flex: 0 0 25vh;
            min-height: 120px;
            max-height: 35vh;
            background: #16213e;
            border-top: 1px solid #0f3460;
            overflow: auto;
            display: flex;
            flex-direction: column;
        }
        #detail-panel.hide {
            display: none;
        }
        #sop-empty {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: #666;
            font-size: 14px;
        }
        #sop-content {
            display: none;
            flex-direction: column;
            height: 100%;
        }
        #sop-content.show {
            display: flex;
        }
        #sop-header {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 16px;
            border-bottom: 1px solid #0f3460;
            flex-shrink: 0;
        }
        #sop-name {
            font-size: 14px;
            font-weight: bold;
            color: #e94560;
        }
        #sop-progress {
            font-size: 12px;
            color: #aaa;
        }
        #sop-progress-bar {
            width: 100px;
            height: 4px;
            background: #0f3460;
            border-radius: 2px;
            overflow: hidden;
            display: inline-block;
            vertical-align: middle;
            margin-left: 8px;
        }
        #sop-progress-fill {
            height: 100%;
            background: #e94560;
            transition: width 0.3s;
        }
        #sop-steps {
            display: flex;
            gap: 4px;
            padding: 8px 16px;
            border-bottom: 1px solid #0f3460;
            overflow-x: auto;
            flex-shrink: 0;
        }
        .sop-step {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 6px;
            background: #1a1a2e;
            border: 1px solid #0f3460;
            cursor: pointer;
            white-space: nowrap;
            font-size: 12px;
            color: #aaa;
            transition: all 0.2s;
        }
        .sop-step:hover {
            border-color: #e94560;
            color: #eee;
        }
        .sop-step.active {
            background: #0f3460;
            border-color: #e94560;
            color: #e94560;
            font-weight: bold;
        }
        .sop-step.done {
            border-color: #2ecc71;
            color: #2ecc71;
        }
        .sop-step-status {
            font-size: 14px;
        }
        #sop-tool-area {
            flex: 1;
            overflow: auto;
            padding: 16px;
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
        /* ---- 诊断浮窗 ---- */
        .diag-overlay {
            display: none;
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); z-index: 9999;
            align-items: center; justify-content: center;
        }
        .diag-overlay.show { display: flex; }
        .diag-panel {
            background: #16213e; border: 1px solid #0f3460; border-radius: 12px;
            width: 640px; max-height: 80vh; overflow: auto;
            padding: 20px; color: #eee; font-size: 13px;
        }
        .diag-panel h3 { margin: 0 0 12px; color: #e94560; font-size: 16px; }
        .diag-panel table { width: 100%; border-collapse: collapse; margin: 8px 0; }
        .diag-panel th, .diag-panel td {
            text-align: left; padding: 6px 10px; border-bottom: 1px solid #0f3460;
        }
        .diag-panel th { color: #e94560; font-size: 12px; }
        .diag-panel td { color: #ccc; font-family: monospace; }
        .diag-panel .ok { color: #4caf50; }
        .diag-panel .warn { color: #ff9800; }
        .diag-panel .bad { color: #f44336; }
        .diag-actions { display: flex; gap: 8px; margin-top: 12px; }
        .diag-actions button {
            padding: 8px 16px; border: 1px solid #0f3460; border-radius: 6px;
            background: #0f3460; color: #eee; cursor: pointer; font-size: 13px;
        }
        .diag-actions button:hover { background: #e94560; color: #fff; }
    </style>
    """)

    # ---- JS: dayjs + DayPilot ----
    ui.add_head_html('<script src="/static/dayjs.min.js"></script>')
    ui.add_head_html('<script src="/static/daypilot-all.min.js"></script>')

    # ---- 诊断工具（同步加载，确保函数一定可用）----
    ui.add_head_html('<script src="/static/diag.js"></script>')

    # ---- Navigation bar ----
    ui.html("""<div class="nav-bar">
        <span class="title">凝华 · Rubedo</span>
        <span id="week-range"></span>
        <button onclick="navWeek(-1)">← 上周</button>
        <button onclick="navToday()">今天</button>
        <button onclick="navWeek(1)">下周 →</button>
        <button onclick="showSettings()" style="margin-left:auto;">设置</button>
        <button onclick="window.open('/audit', '_self')">审计</button>
        <button onclick="showDiag()">🔧 诊断</button>
    </div>""", sanitize=False)

    # ---- Main layout（上下分栏）----
    ui.html("""<div class="main-layout">
        <div id="calendar"></div>
        <div id="detail-panel">
            <div id="sop-empty">⚙️ 请点击日历事件加载 SOP</div>
            <div id="sop-content">
                <div id="sop-header">
                    <span id="sop-name"></span>
                    <span id="sop-progress"></span>
                    <div id="sop-progress-bar"><div id="sop-progress-fill"></div></div>
                </div>
                <div id="sop-steps"></div>
                <div id="sop-tool-area"></div>
            </div>
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

    # ---- 诊断浮窗（JS 在 static/diag.js 里同步加载）----
    ui.html("""<div class="diag-overlay" id="diag-overlay" onclick="if(event.target===this)this.classList.remove('show')">
        <div class="diag-panel">
            <h3>🔬 日历布局诊断</h3>
            <div id="diag-body">运行中...</div>
            <div class="diag-actions">
                <button onclick="copyDiag()">📋 一键复制</button>
                <button onclick="document.getElementById('diag-overlay').classList.remove('show')">关闭</button>
            </div>
        </div>
    </div>""", sanitize=False)

    # ---- DayPilot init ----
    ui.add_body_html(f'<script src="/static/init.js?v={int(time.time())}"></script>')
