"""A 股价量衍生指标 — 涨幅、涨跌停判定。"""
from __future__ import annotations

import pandas as pd


def calc_return_n(close: pd.Series, days: int) -> float:
    """计算 N 日收益率。"""
    if len(close) <= days:
        return 0.0
    base = float(close.iloc[-days - 1])
    if base == 0:
        return 0.0
    return float(close.iloc[-1] / base - 1)


def limit_up_ratio(symbol: str, name: str) -> float:
    """涨跌幅限制比例（近似）。"""
    upper_name = name.upper()
    if "ST" in upper_name:
        return 0.05
    if symbol.startswith(("30", "688")):
        return 0.20
    return 0.10


def is_at_limit_up(
    symbol: str,
    name: str,
    close: float,
    prev_close: float,
    high: float,
) -> bool:
    """是否收盘涨停（不可买入代理）。"""
    if prev_close <= 0 or close <= 0:
        return False
    pct = close / prev_close - 1
    limit = limit_up_ratio(symbol, name)
    near_limit = pct >= limit - 0.005
    at_high = high > 0 and abs(close - high) / high < 0.001
    return near_limit and at_high


def is_at_limit_down(
    symbol: str,
    name: str,
    close: float,
    prev_close: float,
    low: float,
) -> bool:
    """是否收盘跌停（不可卖出代理）。"""
    if prev_close <= 0 or close <= 0:
        return False
    pct = close / prev_close - 1
    limit = limit_up_ratio(symbol, name)
    near_limit = pct <= -limit + 0.005
    at_low = low > 0 and abs(close - low) / low < 0.001
    return near_limit and at_low


def enrich_ohlcv_metrics(
    symbol: str,
    name: str,
    ohlcv: pd.DataFrame,
    *,
    return_5d_days: int = 5,
    return_10d_days: int = 10,
) -> dict[str, float | bool]:
    """从日 K 提取涨幅与涨停标志。"""
    close = ohlcv["close"]
    return {
        "return_5d": calc_return_n(close, return_5d_days),
        "return_10d": calc_return_n(close, return_10d_days),
        "at_limit_up": is_at_limit_up(
            symbol,
            name,
            float(close.iloc[-1]),
            float(close.iloc[-2]) if len(close) >= 2 else 0.0,
            float(ohlcv["high"].iloc[-1]),
        ),
    }
