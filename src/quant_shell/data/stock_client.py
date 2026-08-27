"""A 股 L1 对外 API — 薄门面，实现见 stock_spot / stock_ohlcv / stock_yjbb。"""
from __future__ import annotations

from functools import lru_cache

import akshare as ak
import pandas as pd

from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.data.akshare_client import _run_fetch
from quant_shell.data.constants import PE_HISTORY_MIN_ROWS
from quant_shell.data.stock_ohlcv import fetch_stock_daily_ohlcv
from quant_shell.data.stock_spot import (
    fetch_a_share_spot_batch,
    fetch_stock_spot,
    fetch_stock_spot_quote,
)
from quant_shell.data.stock_yjbb import (
    fetch_stock_roe,
    fetch_yjbb_frame,
    lookup_yjbb_industry,
    prefetch_yjbb_frame,
)

logger = get_logger(__name__)

__all__ = [
    "fetch_a_share_spot_batch",
    "fetch_stock_daily_ohlcv",
    "fetch_stock_pe_percentile",
    "fetch_stock_roe",
    "fetch_stock_spot",
    "fetch_stock_spot_quote",
    "fetch_yjbb_frame",
    "lookup_yjbb_industry",
    "prefetch_yjbb_frame",
]


@lru_cache(maxsize=64)
def fetch_stock_pe_percentile(symbol: str) -> dict[str, float]:
    """个股 PE(TTM) 历史分位（东财 stock_value_em）。"""
    if not symbol or len(symbol) != 6:
        raise ValidationError(
            message=f"无效股票代码: {symbol}",
            suggestion="使用 6 位 A 股代码",
        )
    frame = _run_fetch(
        "stock_value_em",
        lambda: ak.stock_value_em(symbol=symbol),
    )
    if frame is None or frame.empty:
        raise DataFetchError(
            message=f"个股估值历史为空: {symbol}",
            suggestion="检查东财 stock_value_em 是否可访问",
        )
    pe_col = _resolve_pe_ttm_column(frame)
    pe = pd.to_numeric(frame[pe_col], errors="coerce")
    pe = pe[(pe > 0) & pe.notna()]
    if len(pe) < PE_HISTORY_MIN_ROWS:
        raise DataFetchError(
            message=f"个股 {symbol} PE 历史不足 {PE_HISTORY_MIN_ROWS} 行",
            suggestion="换更长上市历史的标的或稍后重试",
        )
    current = float(pe.iloc[-1])
    percentile = float((pe <= current).mean())
    logger.info(
        "stock_pe_percentile symbol=%s pe_ttm=%.2f pct=%.4f n=%d",
        symbol,
        current,
        percentile,
        len(pe),
    )
    return {
        "pe_ttm": current,
        "pe_percentile": percentile,
        "sample_size": float(len(pe)),
    }


def _resolve_pe_ttm_column(frame: pd.DataFrame) -> str:
    for col in frame.columns:
        name = str(col).upper().replace(" ", "")
        if "PE(TTM)" in name or name == "PE（TTM）":
            return str(col)
        if "PE" in name and "TTM" in name:
            return str(col)
    if frame.shape[1] >= 8:
        return str(frame.columns[7])
    raise DataFetchError(
        message="stock_value_em 缺少 PE(TTM) 列",
        suggestion="检查东财估值字段是否变更",
    )
