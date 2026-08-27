"""Alpha 因子引擎 — 计算、适配、加权合成。"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from quant_shell.common.exceptions import ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import MarketSnapshot
from quant_shell.config.settings import settings
from quant_shell.data.pe_quality import is_pe_percentile_reliable
from quant_shell.data.symbol import fetch_daily_ohlcv
from quant_shell.signals.adapter import rank_to_score, ts_rank
from quant_shell.factors.constants import (
    MIN_OHLCV_BARS,
    VALUE_REGIME_BLEND_STRENGTH,
)
from quant_shell.factors.registry import FactorRegistry, FactorSpec
from quant_shell.factors.state_store import FactorScope, load_registry

logger = get_logger(__name__)


@dataclass(frozen=True)
class FactorValue:
    """单因子计算结果。"""

    name: str
    category: str
    raw: float
    adapted_score: float
    weight: float


@dataclass
class AlphaFactorResult:
    """Alpha 因子合成结果。"""

    composite: float
    factors: list[FactorValue] = field(default_factory=list)

    @property
    def components(self) -> dict[str, float]:
        """因子得分字典，供 TradingSignal.components 使用。"""
        return {f"alpha_{item.name}": item.adapted_score for item in self.factors}


class AlphaFactorEngine:
    """WorldQuant 风格因子库：注册 → 计算 → 适配 → 合成。"""

    def __init__(
        self,
        registry: FactorRegistry | None = None,
        *,
        scope: FactorScope | None = None,
    ) -> None:
        """必须显式传入 ``registry`` 或 ``scope``（走 load_registry），禁止无状态默认。"""
        if registry is not None:
            self._registry = registry
            self._scope: FactorScope = scope or "etf"
        elif scope is not None:
            self._registry = load_registry(scope=scope)
            self._scope = scope
        else:
            raise ValidationError(
                message="AlphaFactorEngine 需要 registry 或 scope",
                suggestion="生产用 scope='etf'|'stock'；测试传入 load_registry(scope=...) 或显式 registry",
            )

    @property
    def scope(self) -> FactorScope:
        """当前引擎绑定的 registry scope。"""
        return self._scope

    @property
    def registry(self) -> FactorRegistry:
        """当前因子注册表。"""
        return self._registry

    def compute(self, symbol: str, market: MarketSnapshot | None = None) -> AlphaFactorResult:
        """计算 symbol 的 Alpha 合成得分。

        Args:
            symbol: 6 位 ETF 或股票代码。
            market: 可选 L1 快照（估值体制 blend）。

        Returns:
            合成得分 [-1, 1] 与各因子分解。
        """
        logger.info("AlphaFactorEngine.compute symbol=%s scope=%s", symbol, self._scope)
        ohlcv = fetch_daily_ohlcv(symbol)
        if len(ohlcv) < MIN_OHLCV_BARS:
            raise ValidationError(
                message=f"OHLCV 不足 {MIN_OHLCV_BARS} 根",
                suggestion="增大 HISTORY_CALENDAR_DAYS 或换更长历史标的",
            )

        factors = self._compute_active_factors(ohlcv)
        composite = self._weighted_composite(factors)
        if market is not None and is_pe_percentile_reliable(market):
            composite = self._blend_value_regime(composite, market.pe_percentile)
        elif market is not None:
            logger.info(
                "alpha skip value_regime blend symbol=%s pe_source=%s",
                symbol,
                (market.extra or {}).get("pe_percentile_source"),
            )

        logger.info(
            "alpha_factor symbol=%s scope=%s composite=%.4f count=%d",
            symbol,
            self._scope,
            composite,
            len(factors),
        )
        return AlphaFactorResult(composite=composite, factors=factors)

    def _compute_active_factors(self, ohlcv: pd.DataFrame) -> list[FactorValue]:
        """计算所有 ACTIVE 因子。"""
        results: list[FactorValue] = []
        for spec in self._registry.active_specs():
            results.append(self._compute_one(spec, ohlcv))
        return results

    def _compute_one(self, spec: FactorSpec, ohlcv: pd.DataFrame) -> FactorValue:
        """计算单个因子并做时序适配。"""
        series = spec.compute(ohlcv)
        clean = pd.to_numeric(series, errors="coerce").dropna()
        if clean.empty:
            return FactorValue(spec.name, spec.category.value, 0.0, 0.0, spec.weight)

        raw = float(clean.iloc[-1])
        percentile = ts_rank(clean)
        adapted = rank_to_score(percentile)
        if spec.category.value in ("volatility", "overheat"):
            adapted = -adapted
        if spec.category.value == "reversal":
            adapted = rank_to_score(1.0 - percentile)
        # 门禁最佳符号（与 category 固定反转正交）
        adapted = adapted * float(spec.sign)

        return FactorValue(
            spec.name,
            spec.category.value,
            raw,
            adapted,
            self._registry.effective_weight(spec),
        )

    def _weighted_composite(self, factors: list[FactorValue]) -> float:
        """按有效权重加权合成。"""
        total_weight = sum(item.weight for item in factors if item.weight > 0)
        if total_weight == 0:
            return 0.0
        weighted = sum(item.adapted_score * item.weight for item in factors)
        return float(weighted / total_weight)

    def _blend_value_regime(self, composite: float, pe_percentile: float) -> float:
        """低估加分、高估减分（与买入侧对称的估值体制）。"""
        under = settings.pe_undervalue_blend
        over = settings.pe_overvalue_blend
        strength = VALUE_REGIME_BLEND_STRENGTH
        if pe_percentile < under:
            boost = (under - pe_percentile) * strength
            return max(-1.0, min(1.0, composite + boost))
        if pe_percentile > over:
            penalty = (pe_percentile - over) * strength
            return max(-1.0, min(1.0, composite - penalty))
        return max(-1.0, min(1.0, composite))
