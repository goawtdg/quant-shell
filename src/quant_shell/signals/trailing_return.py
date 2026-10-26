"""63 日收益率。

Jegadeesh and Titman 的中期动量：区间首尾收盘价之比减 1。
不在这里做指标加权。历史不够就失败，不用 0 冒充「没有涨跌」。
"""
from __future__ import annotations

import pandas as pd

from quant_shell.common.exceptions import ValidationError
from quant_shell.data.constants import MOMENTUM_3M_DAYS


def trailing_return(closes: pd.Series, days: int = MOMENTUM_3M_DAYS) -> float:
    """过去 `days` 个交易日的收益率。"""
    series = pd.to_numeric(closes, errors="coerce").dropna()
    if len(series) <= days:
        raise ValidationError(
            message=f"收盘价不足以计算 {days} 日收益，当前 {len(series)} 根",
            suggestion="检查日 K 是否拉全，或换一只上市更久的标的",
        )
    base = float(series.iloc[-1 - days])
    if base == 0:
        raise ValidationError(
            message="区间起点收盘价为 0，无法计算收益率",
            suggestion="检查日 K 的 close 列",
        )
    return float(series.iloc[-1] / base - 1.0)
