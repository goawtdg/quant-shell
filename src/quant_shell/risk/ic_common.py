"""IC 计算公共工具 — 时序 / 截面共用。"""
from __future__ import annotations

import pandas as pd

from quant_shell.risk.constants import FORWARD_RETURN_DAYS, IC_LOOKBACK_DAYS


def forward_returns(close: pd.Series, days: int = FORWARD_RETURN_DAYS) -> pd.Series:
    """计算 N 日前瞻收益率。"""
    return close.pct_change(days).shift(-days)


def ic_summary(
    ic_series: pd.Series,
    *,
    lookback: int | None = IC_LOOKBACK_DAYS,
) -> tuple[float, float, int]:
    """汇总 IC 均值、IR 与样本数。

    Args:
        ic_series: 逐期 IC 序列。
        lookback: 时序模式取最近 N 期；截面模式传 ``None`` 用全样本。
    """
    clean = ic_series.dropna()
    if len(clean) < 5:
        return 0.0, 0.0, len(clean)
    recent = clean.iloc[-lookback:] if lookback else clean
    mean_ic = float(recent.mean())
    std = float(recent.std())
    ir = float(mean_ic / std) if std > 0 else 0.0
    return mean_ic, ir, len(recent)
