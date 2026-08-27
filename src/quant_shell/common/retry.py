"""偶发失败唯一重试 — 再给一次机会，第二次原样抛出。

不吞 BusinessError / RuntimeError。调用方禁止再套一层重试。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from quant_shell.common import audit
from quant_shell.common.exceptions import DataFetchError, ValidationError

T = TypeVar("T")

TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    DataFetchError,
    ValidationError,
    OSError,
)


def call_with_retry(
    fn: Callable[[], T],
    *,
    layer: str,
    op: str,
    symbol: str = "",
) -> T:
    """第一次遇偶发错误则审计后立刻再跑一遍；仍失败则抛给隔离层。"""
    try:
        return fn()
    except TRANSIENT_ERRORS as exc:
        audit.emit(
            layer=layer,
            event="transient_retry",
            severity="WARN",
            error_code="TRANSIENT_RETRY",
            symbol=symbol,
            message=str(exc),
            data={"op": op, "exc_type": type(exc).__name__},
        )
        return fn()
