"""用户因子示例 — 仅 20 日动量（演示 FACTOR_MODULE）。"""
from __future__ import annotations

import pandas as pd

from quant_shell.factors.registry import FactorCategory, FactorRegistry, FactorSpec


def _momentum_20(frame: pd.DataFrame) -> pd.Series:
    close = frame["close"].astype(float)
    return close / close.shift(20) - 1.0


def build_registry(scope: str = "etf") -> FactorRegistry:
    """FACTOR_MODULE=examples.user_factors.registry:build_registry"""
    reg = FactorRegistry()
    reg.register(
        FactorSpec(
            name="momentum_20",
            category=FactorCategory.MOMENTUM,
            description="20日收盘价动量（用户示例）",
            weight=1.0,
            compute=_momentum_20,
        )
    )
    return reg
