"""JSON -> SQLite 迁移工具。

用法：python migrate.py
  - 先自动备份 data/ -> data_backup_<时间戳>/
  - 读现有 JSON（复用 utils 的读函数）
  - 写进 rubedo.db（modules.shared.store）
  - 记录每一步到 data/migrate.log

对应 ARCHITECTURE.md ADR-001 + 局限 L2（迁错可退，rollback.py 一键还原）。

注意：迁移后程序仍读 JSON（平行副本），T3 才切换读取源。
"""

import shutil
import sys
from datetime import date, datetime
from pathlib import Path

# 让脚本能 import 项目模块（运行时 cwd = rubedo 根）
sys.path.insert(0, str(Path(__file__).parent))

from modules.shared import store
from modules.shared.logging_cfg import setup_logging, get_logger
from modules.shared.errors import MigrationError

import utils  # 读 JSON 的源函数

log = get_logger("migrate")


def _migrate_events(data_dir: Path) -> None:
    days = sorted(p.stem for p in data_dir.glob("20[0-9][0-9]-*.json"))
    total = 0
    for day in days:
        y, m, d = day.split("-")
        dt = date(int(y), int(m), int(d))
        evs = utils.read_day(dt)
        if evs:
            store.write_day(dt, evs)
            total += len(evs)
    log.info(f"events: {len(days)} 天 / {total} 条")


def _migrate_timelog(data_dir: Path) -> None:
    tl_dir = data_dir / "timelog"
    if not tl_dir.exists():
        return
    days = sorted(p.stem for p in tl_dir.glob("20[0-9][0-9]-*.json"))
    total = 0
    for day in days:
        y, m, d = day.split("-")
        dt = date(int(y), int(m), int(d))
        ents = utils.read_timelog(dt)
        for e in ents:
            store.write_timelog_entry(e)
        total += len(ents)
    log.info(f"timelog: {len(days)} 天 / {total} 条")


def main() -> None:
    base = Path(__file__).parent
    data_dir = utils.DATA_DIR
    db_path = base / "rubedo.db"

    setup_logging(base / "data" / "migrate.log")

    # 1. 自动备份（即使测试数据也备份，验证迁移脚本本身不崩）
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = base / f"data_backup_{ts}"
    if data_dir.exists():
        shutil.copytree(data_dir, backup_dir)
        log.info(f"已备份 data/ -> {backup_dir}")
    else:
        log.warning("data/ 不存在，跳过备份")

    # 2. 初始化 store
    store.init_store(db_path)
    log.info(f"目标数据库: {db_path}")

    # 3. 逐表迁移
    _migrate_events(data_dir)

    scheds = utils.read_schedules()
    if scheds:
        store.write_schedules(scheds)
    log.info(f"schedules: {len(scheds)} 条")

    ov = utils.read_occurrence_overrides()
    for ds, evmap in ov.items():
        for eid, ovr in evmap.items():
            store.write_occurrence_override(
                ds,
                eid,
                status=ovr.get("status"),
                locked=ovr.get("locked"),
                start=ovr.get("start"),
                end=ovr.get("end"),
                deleted=ovr.get("deleted"),
            )
    log.info(f"occurrence_overrides: {sum(len(v) for v in ov.values())} 条")

    sop_dir = data_dir / "sops"
    if sop_dir.exists():
        for sf in sop_dir.glob("*.json"):
            sop = utils.load_sop(sf.stem)
            if sop:
                store.save_sop(sf.stem, sop)
        log.info(f"sops: {len(list(sop_dir.glob('*.json')))} 个")

    _migrate_timelog(data_dir)

    ch_file = data_dir / "custom_holidays.json"
    if ch_file.exists():
        import json

        ch = json.loads(ch_file.read_text(encoding="utf-8"))
        if ch:
            store.write_custom_holidays(ch)
        log.info(f"custom_holidays: {len(ch)} 条")

    log.info("迁移完成 (程序仍读 JSON，SQLite 为平行副本；T3 切换读取源)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error(f"迁移失败: {e}", exc_info=True)
        raise MigrationError(str(e)) from e
