"""数学信号引擎 — 从 L1 历史数据计算子指标并合成。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_shell.common.logging_config import get_logger
from quant_shell.data.symbol import fetch_daily_closes
from reference_policy.signals.constants import (
    MATH_WEIGHT_BOLLINGER,
    MATH_WEIGHT_DUAL_MA,
    MATH_WEIGHT_MACD,
    MATH_WEIGHT_RSI,
)
from reference_policy.signals.indicators import (
    bollinger_score,
    dual_ma_score,
    macd_score,
    rsi_score,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class MathSignalResult:
    """数学信号计算结果。"""

    composite: float
    components: dict[str, float]


class MathSignalEngine:
    """拉取历史收盘价并计算数学信号。"""

    def compute(self, symbol: str) -> MathSignalResult:
        """计算数学信号合成值。

        Args:
            symbol: 6 位 ETF 代码。

        Returns:
            合成得分与子指标分解，范围 [-1, 1]。
        """
        logger.info("MathSignalEngine.compute symbol=%s", symbol)
        closes = fetch_daily_closes(symbol)
        components = self._compute_components(closes)
        composite = self._weighted_sum(components)
        logger.info(
            "math_signal symbol=%s composite=%.4f components=%s",
            symbol,
            composite,
            components,
        )
        return MathSignalResult(composite=composite, components=components)

    def _compute_components(self, closes: pd.Series) -> dict[str, float]:
        """计算各子指标得分。"""
        return {
            "dual_ma": dual_ma_score(closes),
            "macd": macd_score(closes),
            "rsi": rsi_score(closes),
            "bollinger": bollinger_score(closes),
        }

    def _weighted_sum(self, components: dict[str, float]) -> float:
        """按层内权重合成数学信号。"""
        return (
            components["dual_ma"] * MATH_WEIGHT_DUAL_MA
            + components["macd"] * MATH_WEIGHT_MACD
            + components["rsi"] * MATH_WEIGHT_RSI
            + components["bollinger"] * MATH_WEIGHT_BOLLINGER
        )
