"""第 4 层策略引擎 — 截面选股。"""
from __future__ import annotations

from quant_shell.common import audit
from quant_shell.common.interfaces import StockPicker
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import StockPickResult
from quant_shell.config.settings import settings
from quant_shell.data.fundamentals import build_universe_frame
from quant_shell.data.symbol import filter_no_board_permission
from quant_shell.data.universe import fetch_index_constituents
from reference_policy.picker.constants import DEFAULT_TOP_N
from reference_policy.picker.factor_scorer import FactorScorer
from reference_policy.picker.fundamental_factors import refresh_fundamental_health_report

logger = get_logger(__name__)


class FactorStrategyEngine(StockPicker):
    """截面多因子选股引擎。"""

    def __init__(self, scorer: FactorScorer | None = None) -> None:
        self._scorer = scorer or FactorScorer()

    @classmethod
    def from_registry(cls, registry: object, **_kwargs: object) -> FactorStrategyEngine:
        from quant_shell.factors.registry import FactorRegistry

        if not isinstance(registry, FactorRegistry):
            raise TypeError("from_registry expects FactorRegistry")
        return cls(FactorScorer(registry))

    def pick_stocks(
        self,
        universe: str | None = None,
        top_n: int = DEFAULT_TOP_N,
        max_symbols: int | None = None,
    ) -> StockPickResult:
        """拉取 universe、采集基本面、截面打分。"""
        uni = universe or settings.pick_universe
        cap = (
            max_symbols
            if max_symbols is not None
            else settings.pick_max_symbols_resolved
        )
        skip_industry = settings.linkage_skip_industry_fetch
        symbols = fetch_index_constituents(uni)
        if settings.pick_filter_board_permission:
            before = len(symbols)
            symbols = filter_no_board_permission(symbols)
            logger.info(
                "pick_stocks board_permission_filter dropped=%d remain=%d",
                before - len(symbols),
                len(symbols),
            )
        cap_label = cap if cap is not None else len(symbols)
        logger.info(
            "pick_stocks universe=%s top_n=%d max_symbols=%s skip_industry=%s",
            uni,
            top_n,
            cap_label,
            skip_industry,
        )
        frame = build_universe_frame(
            symbols,
            max_symbols=cap,
            skip_industry=skip_industry,
        )
        if settings.pick_refresh_fundamental_health:
            refresh_fundamental_health_report(
                uni,
                symbols,
                max_symbols=cap,
                frame=frame,
                skip_industry=skip_industry,
            )
        result = self._scorer.score(uni, frame, top_n)
        audit.emit(
            layer="L4",
            event="l4_pick_complete",
            data={
                "universe": uni,
                "candidate_count": result.candidate_count,
                "filtered_count": result.filtered_count,
                "pick_count": len(result.picks),
            },
        )
        return result
