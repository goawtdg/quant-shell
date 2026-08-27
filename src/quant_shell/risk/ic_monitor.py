"""因子 IC / IR 监控 — 单标的时序 Pearson 滚动相关。"""
from __future__ import annotations

import pandas as pd

from quant_shell.factors.registry import FactorSpec
from quant_shell.risk.constants import (
    FORWARD_RETURN_DAYS,
    IC_LOOKBACK_DAYS,
    MIN_IC_SAMPLES,
)
from quant_shell.risk.ic_common import forward_returns, ic_summary


def rolling_ic_series(
    factor: pd.Series,
    close: pd.Series,
    *,
    forward_days: int = FORWARD_RETURN_DAYS,
    lookback: int = IC_LOOKBACK_DAYS,
) -> pd.Series:
    """滚动 IC 序列（单标的时序）。"""
    aligned = pd.DataFrame(
        {
            "factor": pd.to_numeric(factor, errors="coerce"),
            "forward": forward_returns(close, forward_days),
        }
    ).dropna()
    if len(aligned) < MIN_IC_SAMPLES:
        return pd.Series(dtype=float)
    return aligned["factor"].rolling(lookback).corr(aligned["forward"])


def evaluate_factor_ic(
    ohlcv: pd.DataFrame,
    spec: FactorSpec,
    *,
    forward_days: int = FORWARD_RETURN_DAYS,
    lookback: int = IC_LOOKBACK_DAYS,
) -> tuple[float, float, int]:
    """评估单因子 IC/IR。"""
    factor = spec.compute(ohlcv)
    close = pd.to_numeric(ohlcv["close"], errors="coerce")
    ic_series = rolling_ic_series(
        factor,
        close,
        forward_days=forward_days,
        lookback=lookback,
    )
    return ic_summary(ic_series, lookback=IC_LOOKBACK_DAYS)
