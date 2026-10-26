"""A 股回测可交易性 — 涨跌停与 T+1。"""
from __future__ import annotations

import pandas as pd

from quant_shell.common.exceptions import ValidationError
from quant_shell.data.stock_metrics import is_at_limit_down, is_at_limit_up
from quant_shell.data.symbol import is_etf


def can_buy(
    symbol: str,
    row: pd.Series,
    prev_close: float,
    *,
    name: str = "",
) -> bool:
    """是否允许当日买入（非涨停；ETF 不限制）。"""
    if is_etf(symbol):
        return True
    close = float(row["close"])
    high = float(row["high"])
    return not is_at_limit_up(symbol, name, close, prev_close, high)


def can_sell(
    symbol: str,
    row: pd.Series,
    prev_close: float,
    *,
    name: str = "",
    bar_index: int = 0,
    last_buy_bar: int | None = None,
) -> bool:
    """是否允许当日卖出（非跌停、T+1；ETF 不限制）。"""
    if is_etf(symbol):
        return True
    if last_buy_bar is not None and bar_index <= last_buy_bar:
        return False
    close = float(row["close"])
    low = float(row["low"])
    return not is_at_limit_down(symbol, name, close, prev_close, low)


def count_untradable(symbol: str, bars: pd.DataFrame, *, name: str = "") -> int:
    """涨停买不进或跌停卖不出的交易日数。首日没有昨收，不计入。"""
    required = {"close", "high", "low"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValidationError(
            message=f"日 K 缺少 {', '.join(sorted(missing))}",
            suggestion="统计涨跌停需要 close、high、low",
        )
    blocked = 0
    prev_close: float | None = None
    for _, row in bars.iterrows():
        close = float(row["close"])
        if prev_close is None:
            prev_close = close
            continue
        buy_ok = can_buy(symbol, row, prev_close, name=name)
        sell_ok = can_sell(symbol, row, prev_close, name=name)
        if not buy_ok or not sell_ok:
            blocked += 1
        prev_close = close
    return blocked
