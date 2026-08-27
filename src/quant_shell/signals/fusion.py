"""第 3 层信号融合 — 技术指标 + Alpha 因子 + 情绪/情报。"""
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
from quant_shell.factors.engine import AlphaFactorEngine
from quant_shell.signals.math_signal import MathSignalEngine
from quant_shell.signals.strength import classify_strength

_INACTIVE_EPS = 1e-9


class SignalFusionGenerator(SignalGenerator):
    """技术指标 + 按资产分流的 Alpha 因子库 + L2 情绪。

    唯一构造路径：``etf_engine`` + ``stock_engine``（缺省时各自 ``load_registry``）。
    融合权重运行时读 ``settings``（可用 env 消融，默认与历史常量一致）。
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

        w_tech = float(settings.tech_weight_in_math)
        w_alpha = float(settings.alpha_weight_in_math)
        math_den = w_tech + w_alpha
        if math_den <= 0:
            math_combined = 0.0
        else:
            math_combined = (
                tech_result.composite * w_tech + alpha_result.composite * w_alpha
            ) / math_den

        sentiment_signal = float(sentiment.composite)
        # 未知印证 = 0.5 → intel 0；禁止把默认 0 映射成强空头
        intel_signal = (float(sentiment.cross_validation) - 0.5) * 2.0

        w_math = float(settings.signal_weight_math)
        w_sent = float(settings.signal_weight_sentiment)
        w_intel = float(settings.signal_weight_intelligence)

        if settings.fusion_renormalize_inactive:
            # 验证/intel_off：信号近零的轨不占权重，避免空权压扁 opportunity
            if abs(sentiment_signal) < _INACTIVE_EPS:
                w_sent = 0.0
            if abs(intel_signal) < _INACTIVE_EPS:
                w_intel = 0.0
            total = w_math + w_sent + w_intel
            if total > 0:
                w_math, w_sent, w_intel = w_math / total, w_sent / total, w_intel / total

        opportunity = (
            math_combined * w_math
            + sentiment_signal * w_sent
            + intel_signal * w_intel
        )

        components: dict[str, float] = {
            "opportunity": opportunity,
            "math": math_combined,
            "tech": tech_result.composite,
            "alpha": alpha_result.composite,
            "sentiment": sentiment_signal,
            "intelligence": intel_signal,
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
