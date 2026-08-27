"""第 2 层 OSINT + DeepSeek 分析师融合 — Sprint 4B。"""
from __future__ import annotations

from datetime import datetime

from quant_shell.common import audit
from quant_shell.common.exceptions import QuantSystemError, ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import MarketSnapshot, SentimentFactors
from quant_shell.config.settings import settings
from quant_shell.intelligence.analyst.parser import report_to_key_events
from quant_shell.intelligence.analyst.scorer import blend_sentiment_scores
from quant_shell.intelligence.analyst.service import DeepSeekAnalyst
from quant_shell.intelligence.brief import (
    brief_to_key_events,
    build_brief,
    compute_sentiment_scores,
    filter_relevant_items,
)
from quant_shell.intelligence.collector import IntelligenceCollector
from quant_shell.intelligence.osint_fusion import OsintIntelligenceFusion

logger = get_logger(__name__)


class DeepSeekIntelligenceFusion(OsintIntelligenceFusion):
    """OSINT 采集 + DeepSeek 威胁情报分析 + capped 情绪因子。"""

    def __init__(
        self,
        collector: IntelligenceCollector | None = None,
        analyst: DeepSeekAnalyst | None = None,
        *,
        persist_reports: bool = False,
    ) -> None:
        super().__init__(collector=collector)
        self._analyst = analyst or DeepSeekAnalyst()
        self._persist_reports = persist_reports

    def analyze(self, symbol: str, market: MarketSnapshot) -> SentimentFactors:
        """采集 OSINT，调用 DeepSeek 分析。LLM 失败不假装分析师成功。"""
        if market.symbol != symbol:
            raise ValidationError(
                message=f"symbol 不一致: {symbol} vs {market.symbol}",
                suggestion="确保 orchestrator 传递的 symbol 与 market 一致",
            )

        items = self._collect_items(symbol)
        relevant = filter_relevant_items(items, symbol, market)
        brief = build_brief(symbol, relevant)
        rule_scores = compute_sentiment_scores(relevant, brief)

        try:
            report = self._analyst.analyze(
                brief,
                market,
                persist=self._persist_reports,
            )
        except (QuantSystemError, OSError) as exc:
            audit.emit(
                layer="L2",
                event="intel_llm_fail",
                severity="ERROR",
                symbol=symbol,
                error_code="INTEL_LLM_FAIL",
                message=str(exc),
            )
            return self._factors_from_items(symbol, market, items)

        scores = blend_sentiment_scores(rule_scores, report, brief)
        key_events = brief_to_key_events(brief) + report_to_key_events(report)
        logger.info(
            "DeepSeekIntelligenceFusion symbol=%s confidence=%.2f human=%s",
            symbol,
            report.confidence,
            report.human_review_required,
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
            key_events=key_events,
            intelligence_brief=brief,
            analyst_report=report,
        )


def build_default_intelligence_fusion(
    collector: IntelligenceCollector | None = None,
) -> OsintIntelligenceFusion:
    """有 DeepSeek Key 时用 DeepSeek，否则纯 OSINT。禁止静默 fallback_on_error。"""
    if settings.has_deepseek:
        return DeepSeekIntelligenceFusion(collector=collector)
    return OsintIntelligenceFusion(collector=collector)
