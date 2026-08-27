"""信号周期 profile — 按投资模式切换参数。"""
from __future__ import annotations

from quant_shell.config.settings import settings
from quant_shell.signals.constants import (
    MA_FAST_PERIOD,
    MA_FAST_PERIOD_LONG,
    MA_SLOW_PERIOD,
    MA_SLOW_PERIOD_LONG,
)


def resolve_ma_periods() -> tuple[int, int]:
    """返回当前投资模式下的双均线周期。

    Returns:
        (fast_period, slow_period)
    """
    if settings.investment_mode == "long_term":
        return MA_FAST_PERIOD_LONG, MA_SLOW_PERIOD_LONG
    return MA_FAST_PERIOD, MA_SLOW_PERIOD


def min_history_bars() -> int:
    """当前 profile 所需最少 K 线根数。"""
    _, slow = resolve_ma_periods()
    return slow + 5
