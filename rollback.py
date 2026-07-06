"""迁移回滚工具。

用法：python rollback.py <data_backup_YYYYMMDD_HHMMSS>
  - 删除 rubedo.db（及 -wal / -shm 附属文件）
  - 将 data/ 恢复为指定备份目录

对应 ARCHITECTURE.md ADR-001 的可逆性原则（迁错一键退）。
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.shared.logging_cfg import setup_logging, get_logger

log = get_logger("rollback")


def main() -> None:
    base = Path(__file__).parent
    if len(sys.argv) < 2:
        print("用法: python rollback.py <data_backup_YYYYMMDD_HHMMSS>")
        sys.exit(1)

    backup_dir = base / sys.argv[1]
    if not backup_dir.exists():
        print(f"备份目录不存在: {backup_dir}")
        sys.exit(1)

    setup_logging(base / "data" / "rollback.log")

    # 1. 删除数据库及附属文件
    for suffix in ("", "-wal", "-shm"):
        db = base / f"rubedo.db{suffix}"
        if db.exists():
            db.unlink()
            log.info(f"删除 {db}")

    # 2. 恢复 data/
    data_dir = base / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    shutil.copytree(backup_dir, data_dir)
    log.info(f"已恢复 data/ <- {backup_dir}")
    print("回滚完成")


if __name__ == "__main__":
    main()
