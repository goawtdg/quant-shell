"""标的类型识别与统一 OHLCV 入口。"""
from __future__ import annotations

import pandas as pd

from quant_shell.data.akshare_client import (
    fetch_etf_daily_closes,
    fetch_etf_daily_ohlcv,
)
from quant_shell.data.stock_client import fetch_stock_daily_ohlcv

ETF_PREFIXES: tuple[str, ...] = ("51", "15", "56", "58")

# 普通 A 股账户需额外开通权限的板块（创业板 / 科创板 / 北交所）
BOARD_PERMISSION_PREFIXES: tuple[str, ...] = (
    "300",
    "301",
    "688",
    "689",
    "4",
    "8",
    "92",
)

BOARD_PERMISSION_BLOCK_REASON: str = "需板块权限(创业板/科创板/北交所)"


def is_etf(symbol: str) -> bool:
    """是否为 ETF 代码。"""
    return len(symbol) == 6 and symbol.startswith(ETF_PREFIXES)


def requires_board_permission(symbol: str) -> bool:
    """个股是否属于有准入门槛的板块（ETF 视为无门槛）。"""
    code = str(symbol).strip().zfill(6)
    if len(code) != 6 or not code.isdigit():
        return False
    if is_etf(code):
        return False
    return code.startswith(BOARD_PERMISSION_PREFIXES)


def filter_no_board_permission(symbols: list[str]) -> list[str]:
    """保留无需板块权限即可交易的标的。"""
    return [str(s).zfill(6) for s in symbols if not requires_board_permission(str(s))]


def is_stock(symbol: str) -> bool:
    """是否为 A 股个股代码（非 ETF）。"""
    return len(symbol) == 6 and not is_etf(symbol)


def asset_type(symbol: str) -> str:
    """返回 ``etf`` 或 ``stock``。"""
    return "etf" if is_etf(symbol) else "stock"


def fetch_daily_ohlcv(symbol: str) -> pd.DataFrame:
    """按标的类型拉取日 K OHLCV。"""
    if is_etf(symbol):
        return fetch_etf_daily_ohlcv(symbol)
    return fetch_stock_daily_ohlcv(symbol)


def fetch_daily_closes(symbol: str) -> pd.Series:
    """按标的类型拉取收盘价序列。"""
    if is_etf(symbol):
        return fetch_etf_daily_closes(symbol)
    return fetch_daily_ohlcv(symbol)["close"]
