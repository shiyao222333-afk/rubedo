"""
Rubedo · 凝华 — v0.3.0 酷家乐 SOP + 时间审计
NiceGUI 桌面应用入口（薄入口，重构 2026-07-05）

架构：
  app.py           → 薄入口（路由注册 + 配置 + 启动）
  api.py           → 全部 API 路由处理函数
  pages/index_page.py → 主页（日历）
  pages/sop_page.py  → SOP 页面
  pages/audit_page.py → 时间审计页面
  utils.py         → 工具函数（数据层）
  holidays.py      → 节假日计算
  data/            → JSON 文件存储
"""

import time
from pathlib import Path
from datetime import date, timedelta

from modules.shared.logging_cfg import setup_logging, get_logger

# ====== NiceGUI ======
from nicegui import app, ui
from starlette.requests import Request

# ====== Module Imports ======
from utils import *
from holidays import *

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
SOPS_DIR.mkdir(parents=True, exist_ok=True)
TIMELOG_DIR.mkdir(parents=True, exist_ok=True)

# 初始化统一日志（T3 修复：日志底座接线，让所有 rubedo.* logger 写 data/rubedo.log）
setup_logging(DATA_DIR / "rubedo.log")
app_log = get_logger("rubedo.app")

# Mount static/ directory → serves /static/*.js and *.css
app.add_static_files('/static', str(BASE_DIR / 'static'))


# ====== APScheduler ======

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.stores.sqlalchemy import SQLAlchemyJobStore
    _has_aps = True
except Exception:
    _has_aps = False


def get_scheduler():
    """Lazily initialize and return the APScheduler instance."""
    if not hasattr(app, '_rubedo_scheduler'):
        if not _has_aps:
            app._rubedo_scheduler = None
            return None
        scheduler = BackgroundScheduler()
        db_path = DATA_DIR / 'apscheduler.db'
        scheduler.add_jobstore(
            SQLAlchemyJobStore(url=f'sqlite:///{db_path}'),
            alias='default'
        )
        app._rubedo_scheduler = scheduler
    return app._rubedo_scheduler


# ====== Import Page Modules（触发 @ui.page() 装饰器）======

import pages.index_page   # @ui.page("/")
import pages.sop_page    # @ui.page("/sop/{sop_id}")
import pages.audit_page  # @ui.page("/audit")


# ====== Register API Routes ======

from api import register_api_routes
register_api_routes(app)


# ====== Startup / Shutdown ======

def on_startup():
    """Runs when the NiceGUI app starts."""
    scheduler = get_scheduler()
    if scheduler is not None and not scheduler.running:
        scheduler.start()
        app_log.info("[Rubedo] APScheduler 已启动 (SQLite 持久化)")

    # 后台获取节假日数据（当前年 + 明年，间隔2秒避免限流）
    import threading

    def _fetch_holidays_bg():
        from datetime import datetime
        current_year = datetime.now().year
        for yr in (current_year, current_year + 1):
            try:
                data = fetch_holidays(yr)
                if data and data.get("holidays"):
                    app_log.info(f"[Rubedo] 节假日数据已获取 ({yr}年, {len(data['holidays'])}天)")
                else:
                    app_log.info(f"[Rubedo] 节假日数据为空 ({yr}年)")
            except Exception as e:
                app_log.warning(f"[Rubedo] 节假日获取异常 ({yr}年): {e}")
            if yr < current_year + 1:
                time.sleep(1.5)  # 间隔防限流

    t = threading.Thread(target=_fetch_holidays_bg, daemon=True)
    t.start()


def on_shutdown():
    """Runs when the NiceGUI app stops."""
    scheduler = get_scheduler()
    if scheduler is not None and scheduler.running:
        scheduler.shutdown()
        app_log.info("[Rubedo] APScheduler 已关闭")


app.on_startup(on_startup)
app.on_shutdown(on_shutdown)


# ====== Main ======

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title      = "凝华 v0.3.0",
        native     = True,
        window_size = (1400, 900),
        port       = 8081,
        reload     = False,
        show       = True,
    )
