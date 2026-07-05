"""
Rubedo · 凝华 — SOP 页面
"""

import json
from nicegui import ui
from utils import load_sop


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

        window.startRubedoTimer = function(stepName, sopId, sopName) {
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

        window.stopRubedoTimer = function() {
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
                        # 用 json.dumps() 转义 JS 字符串（防止单引号/双引号导致的语法错误）
                        step_name_js = json.dumps(step["name"])
                        sop_id_js = json.dumps(sop_id)
                        sop_name_js = json.dumps(sop["name"])
                        btn_html = (
                            f'<button data-timer-btn="1" data-step-name="{step["name"]}" '
                            f'onclick="window.handleTimerClick(this, {step_name_js}, {sop_id_js}, {sop_name_js})" '
                            f'style="padding:8px 16px;background:#e94560;color:#fff;border:none;border-radius:8px;'
                            f'cursor:pointer;font-size:13px;">开始计时</button>'
                        )
                        ui.html(btn_html, sanitize=False)

    # Add global JS handler for timer buttons
    handler_js = """
    <script>
    window.handleTimerClick = function(btn, stepName, sopId, sopName) {
        if (btn.textContent === "开始计时") {
            window.startRubedoTimer(stepName, sopId, sopName);
        } else {
            let result = window.stopRubedoTimer();
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
