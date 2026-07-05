"""
Rubedo · 凝华 — 时间审计页面
"""

from nicegui import ui
from utils import *
from datetime import date, timedelta


@ui.page("/audit")
def audit_page():
    """Time audit page — shows hourly rate and time breakdown."""
    ui.label("⏱ 时间审计").classes("text-2xl font-bold text-white")
    ui.label("查看你的时薪和时间分配").classes("text-gray-400 mb-4")

    # Date range inputs
    today = date.today()
    first_day = today.replace(day=1)
    if first_day.month < 12:
        last_day = (first_day.replace(month=first_day.month + 1, day=1) - timedelta(days=1))
    else:
        last_day = (first_day.replace(year=first_day.year + 1, month=1, day=1) - timedelta(days=1))

    start_input = ui.date_input("开始日期", value=first_day)
    end_input   = ui.date_input("结束日期", value=last_day)

    report_container = ui.column().classes("w-full gap-4 mt-4")

    def generate_report():
        """Generate report for the selected date range."""
        try:
            start = date.fromisoformat(start_input.value)
            end   = date.fromisoformat(end_input.value)
        except (ValueError, TypeError):
            ui.notify("日期格式错误", type="negative")
            return

        report_container.clear()
        with report_container:
            ui.label("计算中...").classes("text-gray-400")

        # Read data and calculate
        entries = all_timelog_in_range(start, end)
        events  = all_events_in_range(start, end)
        stats   = calc_hourly_rate(entries, events)

        # Display results
        report_container.clear()
        with report_container:
            if stats["total_minutes"] == 0:
                ui.label("该时间段没有时间记录。").classes("text-gray-400 text-lg")
                ui.label("去 SOP 页面点「开始计时」来记录时间。").classes("text-gray-500")
                return

            # Summary cards
            with ui.row().classes("gap-4 w-full"):
                with ui.card().classes("flex-1 p-4 bg-gray-800"):
                    ui.label("总时长").classes("text-sm text-gray-400")
                    ui.label(f"{stats['total_minutes']} 分钟").classes("text-2xl font-bold text-white")
                with ui.card().classes("flex-1 p-4 bg-gray-800"):
                    ui.label("总收入").classes("text-sm text-gray-400")
                    ui.label(f"¥{stats['total_income']:.2f}").classes("text-2xl font-bold text-green-400")
                with ui.card().classes("flex-1 p-4 bg-gray-800"):
                    ui.label("时薪").classes("text-sm text-gray-400")
                    ui.label(f"¥{stats['hourly_rate']:.2f}/小时").classes("text-2xl font-bold text-yellow-400")

            # By SOP breakdown
            if stats.get("by_sop"):
                ui.label("按 SOP 统计").classes("text-lg font-bold text-white mt-4")
                for sop_id, sop_stats in stats["by_sop"].items():
                    with ui.card().classes("w-full p-3 bg-gray-700"):
                        with ui.row().classes("justify-between"):
                            ui.label(sop_id).classes("text-white font-bold")
                            ui.label(f"{sop_stats['minutes']} 分钟 / ¥{sop_stats['income']:.2f}").classes("text-gray-300")

            # Recent entries
            if entries:
                ui.label("最近记录").classes("text-lg font-bold text-white mt-4")
                for entry in entries[-10:]:
                    with ui.card().classes("w-full p-2 bg-gray-800"):
                        with ui.row().classes("justify-between"):
                            ui.label(entry.get("step_name", "")).classes("text-white")
                            ui.label(f"{entry.get('duration_min', 0)} 分钟").classes("text-gray-400")
                        if entry.get("note"):
                            ui.label(entry["note"]).classes("text-xs text-gray-500")

    ui.button("生成报告", on_click=lambda: generate_report()).classes("mt-2")

    # Generate report on page load
    generate_report()
