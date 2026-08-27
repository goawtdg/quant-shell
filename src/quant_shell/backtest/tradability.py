"""A 股回测可交易性 — 涨跌停与 T+1。"""
from __future__ import annotations

import pandas as pd

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
