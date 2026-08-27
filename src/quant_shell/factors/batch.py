"""Alpha 因子批量原始值计算（截面选股）。"""
from __future__ import annotations

import pandas as pd

from quant_shell.factors.registry import FactorRegistry
from quant_shell.factors.state_store import load_registry


def compute_alpha_raws(
    ohlcv: pd.DataFrame,
    registry: FactorRegistry | None = None,
) -> dict[str, float]:
    """计算单标的各 ACTIVE 因子最新原始值。

    Args:
        ohlcv: OHLCV DataFrame。
        registry: 因子注册表，默认股票 scope 持久化状态。

    Returns:
        factor_name -> raw value。
    """
    reg = registry or load_registry(scope="stock")
    raws: dict[str, float] = {}
    for spec in reg.active_specs():
        series = spec.compute(ohlcv)
        clean = pd.to_numeric(series, errors="coerce").dropna()
        if not clean.empty:
            # 与引擎一致：选股截面使用验证门禁符号
            raws[spec.name] = float(clean.iloc[-1]) * float(spec.sign)
    return raws
