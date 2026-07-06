"""数据访问层（DAL）：统一存储接口 + SQLite 实现。

领域经此访问存储，不直接碰文件。对应 ARCHITECTURE.md ADR-001。

对外导出：
  - errors       领域异常层级（RubedoError 及其子类）
  - logging_cfg  统一日志配置（setup_logging / get_logger）
  - store        DAL 实现（SQLite + WAL，等价读写接口）

依赖铁律：shared 是最底层，绝不 import 上层（utils / api / pages），避免循环依赖。
"""

from . import errors
from . import logging_cfg
from . import store

__all__ = ["errors", "logging_cfg", "store"]
