"""日 K 长度门槛 — L1 唯一入口；短序列禁止入缓存、禁止当成功。"""
from __future__ import annotations

import pandas as pd

from quant_shell.common.exceptions import ValidationError
from quant_shell.data.constants import MOMENTUM_3M_DAYS


def required_ohlcv_bars() -> int:
    """63 日收益需要区间两端的收盘价。"""
    return MOMENTUM_3M_DAYS + 1


def ensure_ohlcv_length(symbol: str, frame: pd.DataFrame | None) -> pd.DataFrame:
    """根数不足则 ValidationError；调用方不得 store。"""
    need = required_ohlcv_bars()
    n = 0 if frame is None or not isinstance(frame, pd.DataFrame) else len(frame)
    if n < need:
        raise ValidationError(
            message=f"{symbol} 历史 K 线不足 {need} 根，当前 {n}",
            suggestion="偶发截断会由联动层重试一次；仍不足则检查日 K 源",
        )
    return frame
