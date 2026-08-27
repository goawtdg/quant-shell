"""日 K 长度门槛 — L1 唯一入口；短序列禁止入缓存、禁止当成功。"""
from __future__ import annotations

import pandas as pd

from quant_shell.common.exceptions import ValidationError


def required_ohlcv_bars() -> int:
    """信号 + Alpha 所需最少根数（随 investment_mode 变化）。"""
    from quant_shell.factors.constants import MIN_OHLCV_BARS
    from quant_shell.signals.signal_profile import min_history_bars

    return max(MIN_OHLCV_BARS, min_history_bars())


def ensure_ohlcv_length(symbol: str, frame: pd.DataFrame | None) -> pd.DataFrame:
    """根数不足则 ValidationError；调用方不得 store。"""
    need = required_ohlcv_bars()
    n = 0 if frame is None or not isinstance(frame, pd.DataFrame) else len(frame)
    if n < need:
        raise ValidationError(
            message=f"历史 K 线不足 {need} 根，当前 {n}",
            suggestion="偶发截断会由联动层重试一次；仍不足则检查日 K 源",
        )
    return frame
