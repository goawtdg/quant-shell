"""大 A 适配的单票清仓回撤阈值 — 随波动动态计算。"""
from __future__ import annotations

import math

from quant_shell.config.settings import settings

# 沪深300 平静期年化波动参考，用于市况应激放大
_MARKET_VOL_BASELINE = 0.18


def compute_hold_exit_drawdown_limit(
    volatility_annual: float,
    *,
    market_volatility_annual: float | None = None,
) -> float:
    """按个股年化波动计算 hold 清仓回撤红线。

    公式：clip(k * σ * sqrt(T/252), floor, ceiling)。
    大盘波动高于基线时略放大 k，避免熊市误杀；无波动数据时退回 floor。

    Args:
        volatility_annual: 标的年化波动率（如 L5 RiskMetrics）。
        market_volatility_annual: 可选大盘年化波动（如 510300）。

    Returns:
        回撤阈值 [floor, ceiling]。
    """
    floor = settings.hold_exit_dd_floor
    ceiling = settings.hold_exit_dd_ceiling
    window = max(1, settings.hold_exit_dd_window_days)
    k = settings.hold_exit_dd_k

    if market_volatility_annual is not None and market_volatility_annual > 0:
        stress = max(1.0, market_volatility_annual / _MARKET_VOL_BASELINE)
        k *= min(stress, 1.35)

    vol = max(0.0, float(volatility_annual))
    if vol <= 0:
        return float(floor)

    raw = k * vol * math.sqrt(window / 252.0)
    return float(min(ceiling, max(floor, raw)))
