"""统一日志配置。

集中所有日志输出（替代散落的 print）。调用方在启动时传入日志文件路径。
不依赖上层模块（utils），避免循环依赖——路径由调用方传入。
对应 ARCHITECTURE.md 第 8 节 L5（可观测性缺失）的修复基础。
"""

import logging
import sys
from pathlib import Path


def setup_logging(log_file: Path, *, level: int = logging.INFO) -> logging.Logger:
    """配置并返回 rubedo 根 logger。

    log_file: 日志文件路径（如 DATA_DIR / "rubedo.log"），由调用方传入。
    输出：文件（utf-8）+ 控制台。
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger("rubedo")
    root.setLevel(level)
    # 防止重复添加 handler（多次调用 setup_logging 时）
    for h in list(root.handlers):
        root.removeHandler(h)

    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setFormatter(formatter)
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    return root


def get_logger(name: str) -> logging.Logger:
    """获取带 rubedo 前缀的子 logger。"""
    return logging.getLogger(f"rubedo.{name}")
