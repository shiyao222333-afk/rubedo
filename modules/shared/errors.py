"""凝华领域异常层级。

所有「可预期的、业务层面」的错误都应继承 RubedoError，
便于在 API 层统一捕获并返回结构化错误，取代散落的 print。
对应 ARCHITECTURE.md 第 8 节 L5（可观测性缺失）的修复基础。
"""

from typing import Optional


class RubedoError(Exception):
    """所有领域错误的基类。"""

    code = "RUBEDO_ERROR"
    http_status = 500

    def __init__(self, message: str, *, cause: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.cause = cause

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message}


class DataAccessError(RubedoError):
    """存储读写失败（JSON 或 SQLite）。"""

    code = "DATA_ACCESS"
    http_status = 500


class MigrationError(RubedoError):
    """JSON -> SQLite 迁移失败。"""

    code = "MIGRATION"
    http_status = 500


class ValidationError(RubedoError):
    """输入数据不合法。"""

    code = "VALIDATION"
    http_status = 400
