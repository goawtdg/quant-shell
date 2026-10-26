"""L3 信号：63 日收益率。

机会分就是这段收益本身。0.07 表示过去 63 个交易日上涨 7%。
情绪、均线组合、RSI、布林和印证次数不加入这个数。
"""
from __future__ import annotations

from quant_shell.common.interfaces import SignalGenerator
from quant_shell.common.types import (
    Action,
    MarketSnapshot,
    SentimentFactors,
    TradingSignal,
)
from quant_shell.data.symbol import fetch_daily_closes
from quant_shell.signals.strength import classify_strength
from quant_shell.signals.trailing_return import trailing_return


class SignalFusionGenerator(SignalGenerator):
    """单标的机会分 = 63 日收益率。"""

    def generate(
        self,
        symbol: str,
        market: MarketSnapshot,
        sentiment: SentimentFactors,
    ) -> TradingSignal:
        """用日 K 计算 63 日收益。行情和情绪只留在分量里，不改这个数。"""
        del market
        opportunity = trailing_return(fetch_daily_closes(symbol))
        return TradingSignal(
            symbol=symbol,
            direction=Action.BUY if opportunity > 0 else Action.SELL,
            strength=classify_strength(abs(opportunity)),
            opportunity=opportunity,
            quality=None,
            components={
                "trailing_return": opportunity,
                "sentiment": float(sentiment.composite),
            },
        )
