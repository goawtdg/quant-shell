"""数学信号引擎 — 从 L1 历史数据计算子指标并合成。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_shell.common.logging_config import get_logger
from quant_shell.data.symbol import fetch_daily_closes
from quant_shell.signals.constants import (
    MATH_WEIGHT_BOLLINGER,
    MATH_WEIGHT_DUAL_MA,
    MATH_WEIGHT_MACD,
    MATH_WEIGHT_RSI,
)
from quant_shell.signals.indicators import (
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
            趋势得分（composite）与子指标。RSI / 布林只写入 reversion，不进入 composite。
        """
        logger.info("MathSignalEngine.compute symbol=%s", symbol)
        closes = fetch_daily_closes(symbol)
        components = self._compute_components(closes)
        composite = float(components["trend"])
        logger.info(
            "math_signal symbol=%s trend=%.4f reversion=%.4f",
            symbol,
            composite,
            components["reversion"],
        )
        return MathSignalResult(composite=composite, components=components)

    def _compute_components(self, closes: pd.Series) -> dict[str, float]:
        """趋势与反转分开计分。composite 只取趋势，反转不参与开仓分。"""
        dual_ma = dual_ma_score(closes)
        macd = macd_score(closes)
        rsi = rsi_score(closes)
        bollinger = bollinger_score(closes)
        trend_w = MATH_WEIGHT_DUAL_MA + MATH_WEIGHT_MACD
        reversion_w = MATH_WEIGHT_RSI + MATH_WEIGHT_BOLLINGER
        trend = (
            0.0
            if trend_w <= 0
            else (dual_ma * MATH_WEIGHT_DUAL_MA + macd * MATH_WEIGHT_MACD) / trend_w
        )
        reversion = (
            0.0
            if reversion_w <= 0
            else (rsi * MATH_WEIGHT_RSI + bollinger * MATH_WEIGHT_BOLLINGER) / reversion_w
        )
        return {
            "dual_ma": dual_ma,
            "macd": macd,
            "rsi": rsi,
            "bollinger": bollinger,
            "trend": trend,
            "reversion": reversion,
        }
