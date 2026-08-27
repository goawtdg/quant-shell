"""DeepSeek 威胁情报分析师。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import AnalystReport, IntelligenceBrief, MarketSnapshot
from quant_shell.config.env_loader import project_root
from quant_shell.intelligence.analyst.deepseek_client import chat_json
from quant_shell.intelligence.analyst.parser import parse_analyst_report
from quant_shell.intelligence.analyst.prompt import build_analyst_messages

logger = get_logger(__name__)


def _default_report_dir() -> Path:
    return project_root() / "data" / "analyst_reports"


class DeepSeekAnalyst:
    """调用 DeepSeek 对 IntelligenceBrief 做威胁情报分析。"""

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key

    def analyze(
        self,
        brief: IntelligenceBrief,
        market: MarketSnapshot,
        *,
        persist: bool = False,
    ) -> AnalystReport:
        """生成 AnalystReport。"""
        messages = build_analyst_messages(brief, market)
        payload = chat_json(messages, api_key=self._api_key)
        report = parse_analyst_report(brief.symbol, payload)
        if persist:
            self.save_report(report)
        logger.info(
            "DeepSeekAnalyst symbol=%s confidence=%.2f action=%s novelty=%s",
            report.symbol,
            report.confidence,
            report.recommended_action,
            report.novelty,
        )
        return report

    @staticmethod
    def save_report(report: AnalystReport, base_dir: Path | None = None) -> Path:
        """持久化分析师报告。"""
        root = base_dir or _default_report_dir()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{report.symbol}_{report.timestamp:%Y%m%d_%H%M%S}.json"
        path.write_text(
            json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def _report_to_dict(report: AnalystReport) -> dict[str, object]:
    return {
        "symbol": report.symbol,
        "timestamp": report.timestamp.isoformat(),
        "executive_summary": report.executive_summary,
        "facts": report.facts,
        "affected_assets": report.affected_assets,
        "transmission_chain": report.transmission_chain,
        "corroboration_assessment": report.corroboration_assessment,
        "confidence": report.confidence,
        "sentiment_score": report.sentiment_score,
        "policy_risk_score": report.policy_risk_score,
        "novelty": report.novelty,
        "recommended_action": report.recommended_action,
        "uncertainties": report.uncertainties,
        "human_review_required": report.human_review_required,
    }
