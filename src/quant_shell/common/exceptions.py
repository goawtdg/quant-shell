"""项目统一异常体系 — 所有业务异常必须包含 suggestion。"""
from __future__ import annotations


class QuantSystemError(Exception):
    """量化系统基础异常。

    Attributes:
        message: 错误描述。
        suggestion: 给开发者/运维的修复建议。
    """

    def __init__(self, message: str, suggestion: str = "") -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class ValidationError(QuantSystemError):
    """输入或数据校验失败。"""


class BusinessError(QuantSystemError):
    """业务规则不满足。"""


class DataFetchError(QuantSystemError):
    """外部数据采集失败（AkShare、爬虫等）。"""


# 源边界可转成 DataFetchError 的具体类型（禁止业务路径万能 except）
EXTERNAL_IO_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    TimeoutError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    IndexError,
)
