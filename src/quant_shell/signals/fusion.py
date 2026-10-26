"""第 3 层信号融合 — 延续趋势 + 动量因子 + 有方向的情绪。

反转指标、估值、新闻条数和多源印证不进入 opportunity。
没有方向证据的轨道不占权重，避免把趋势分稀释到开仓线以下。
"""
from __future__ import annotations

from quant_shell.common.interfaces import SignalGenerator
from quant_shell.common.types import (
    Action,
    MarketSnapshot,
    SentimentFactors,
    TradingSignal,
)
from quant_shell.config.settings import settings
from quant_shell.data.symbol import asset_type
from quant_shell.factors.engine import AlphaFactorEngine, AlphaFactorResult
from quant_shell.signals.math_signal import MathSignalEngine
from quant_shell.signals.strength import classify_strength

_INACTIVE_EPS = 1e-9
_CONTINUATION_CATEGORIES = frozenset({"momentum"})


def continuation_alpha(result: AlphaFactorResult) -> tuple[float, bool]:
    """动量因子加权分。没有动量因子时视为缺席，而不是一张 0 分选票。"""
    chosen = [
        item
        for item in result.factors
        if item.category in _CONTINUATION_CATEGORIES and item.weight > 0
    ]
    if not chosen:
        return 0.0, False
    total = sum(item.weight for item in chosen)
    score = sum(item.adapted_score * item.weight for item in chosen) / total
    return float(score), True


class SignalFusionGenerator(SignalGenerator):
    """延续趋势 + 动量因子 + 有方向的情绪。

    唯一构造路径：``etf_engine`` + ``stock_engine``（缺省时各自 ``load_registry``）。
    反转类因子、RSI、布林和印证次数不进入 opportunity。
    """

    def __init__(
        self,
        math_engine: MathSignalEngine | None = None,
        *,
        etf_engine: AlphaFactorEngine | None = None,
        stock_engine: AlphaFactorEngine | None = None,
    ) -> None:
        self._math_engine = math_engine or MathSignalEngine()
        self._etf_engine = etf_engine or AlphaFactorEngine(scope="etf")
        self._stock_engine = stock_engine or AlphaFactorEngine(scope="stock")

    def generate(
        self,
        symbol: str,
        market: MarketSnapshot,
        sentiment: SentimentFactors,
    ) -> TradingSignal:
        """生成融合交易信号。"""
        tech_result = self._math_engine.compute(symbol)
        engine = self._engine_for(symbol)
        alpha_result = engine.compute(symbol, market)
        scope = engine.scope

        trend = float(tech_result.composite)
        cont_alpha, alpha_active = continuation_alpha(alpha_result)
        w_tech = float(settings.tech_weight_in_math)
        w_alpha = float(settings.alpha_weight_in_math) if alpha_active else 0.0
        math_den = w_tech + w_alpha
        if math_den <= 0:
            math_combined = 0.0
        else:
            math_combined = (trend * w_tech + cont_alpha * w_alpha) / math_den

        sentiment_signal = float(sentiment.composite)
        # 印证次数衡量消息是否重复，不是涨跌方向。保留原值仅供审计。
        corroboration_bias = (float(sentiment.cross_validation) - 0.5) * 2.0

        w_math = float(settings.signal_weight_math)
        w_sent = float(settings.signal_weight_sentiment)
        w_intel = 0.0
        if settings.fusion_renormalize_inactive and abs(sentiment_signal) < _INACTIVE_EPS:
            w_sent = 0.0
        total = w_math + w_sent + w_intel
        if total > 0:
            w_math, w_sent, w_intel = w_math / total, w_sent / total, w_intel / total

        opportunity = math_combined * w_math + sentiment_signal * w_sent

        components: dict[str, float] = {
            "opportunity": opportunity,
            "math": math_combined,
            "tech": tech_result.composite,
            "alpha": cont_alpha,
            "alpha_all_factors": alpha_result.composite,
            "sentiment": sentiment_signal,
            "intelligence": 0.0,
            "corroboration_bias_ignored": corroboration_bias,
            "reversion": float(tech_result.components.get("reversion", 0.0)),
            "continuation_alpha": cont_alpha,
            "w_math": w_math,
            "w_sent": w_sent,
            "w_intel": w_intel,
            "w_tech": w_tech / math_den if math_den else 0.0,
            "w_alpha": w_alpha / math_den if math_den else 0.0,
            **{f"tech_{k}": v for k, v in tech_result.components.items()},
            **alpha_result.components,
        }

        return TradingSignal(
            symbol=symbol,
            direction=Action.BUY if opportunity > 0 else Action.SELL,
            strength=classify_strength(abs(opportunity)),
            opportunity=opportunity,
            quality=None,
            components=components,
            alpha_registry_scope=scope,
        )

    def _engine_for(self, symbol: str) -> AlphaFactorEngine:
        if asset_type(symbol) == "etf":
            return self._etf_engine
        return self._stock_engine
