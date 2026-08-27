"""信号强度分档 — L3 纯函数（不参与开平仓决策）。"""
from __future__ import annotations

from quant_shell.common.types import SignalStrength
from quant_shell.config.settings import settings


def classify_strength(opportunity: float) -> SignalStrength:
    """按 |opportunity| 分档（运行时读 settings）。"""
    abs_val = abs(opportunity)
    if abs_val >= settings.signal_threshold_strong:
        return SignalStrength.STRONG
    if abs_val >= settings.signal_threshold_moderate:
        return SignalStrength.MODERATE
    return SignalStrength.WEAK
