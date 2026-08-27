"""第 2 层 OSINT 情报融合 — Sprint 4A。"""
from __future__ import annotations

from datetime import datetime

from quant_shell.common.exceptions import ValidationError
from quant_shell.common.interfaces import IntelligenceFusion
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import IntelligenceItem, MarketSnapshot, SentimentFactors
from quant_shell.intelligence.brief import (
    brief_to_key_events,
    build_brief,
    compute_sentiment_scores,
    filter_relevant_items,
)
from quant_shell.intelligence.collector import IntelligenceCollector

logger = get_logger(__name__)


class OsintIntelligenceFusion(IntelligenceFusion):
    """多源开源情报采集 + 去重 + 三角测量 + 规则情绪分。"""

    def __init__(self, collector: IntelligenceCollector | None = None) -> None:
        self._collector = collector or IntelligenceCollector()
        self._global_items: list[IntelligenceItem] | None = None

    def set_global_items(self, items: list[IntelligenceItem] | None) -> None:
        """注入本轮已采集的市场快讯，避免每标的重拉。"""
        self._global_items = list(items) if items is not None else None

    def analyze(self, symbol: str, market: MarketSnapshot) -> SentimentFactors:
        """采集 OSINT 并输出 SentimentFactors。"""
        if market.symbol != symbol:
            raise ValidationError(
                message=f"symbol 不一致: {symbol} vs {market.symbol}",
                suggestion="确保 orchestrator 传递的 symbol 与 market 一致",
            )
        items = self._collect_items(symbol)
        return self._factors_from_items(symbol, market, items)

    def _collect_items(self, symbol: str) -> list[IntelligenceItem]:
        if self._global_items is not None:
            return self._collector.collect_for_symbol(
                symbol, global_items=self._global_items
            )
        return self._collector.collect_for_symbol(symbol)

    def _factors_from_items(
        self,
        symbol: str,
        market: MarketSnapshot,
        items: list,
    ) -> SentimentFactors:
        """由已采集 raw items 生成情绪因子（供 DeepSeek 降级复用）。"""
        relevant = filter_relevant_items(items, symbol, market)
        brief = build_brief(symbol, relevant)
        scores = compute_sentiment_scores(relevant, brief)

        logger.info(
            "OsintIntelligenceFusion symbol=%s items=%d sources=%d corroboration=%d",
            symbol,
            len(relevant),
            brief.source_count,
            brief.corroboration_count,
        )
        return SentimentFactors(
            symbol=symbol,
            timestamp=datetime.now(),
            nlp_score=scores["nlp_score"],
            social_buzz=scores["social_buzz"],
            policy_risk=scores["policy_risk"],
            fund_sentiment=scores["fund_sentiment"],
            composite=scores["composite"],
            cross_validation=scores["cross_validation"],
            key_events=brief_to_key_events(brief),
            intelligence_brief=brief,
        )
