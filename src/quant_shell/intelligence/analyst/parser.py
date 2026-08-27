"""DeepSeek JSON 解析为 AnalystReport。"""
from __future__ import annotations

from datetime import datetime

from quant_shell.common.types import AnalystReport
from quant_shell.intelligence.analyst.constants import (
    NOVELTY_LEVELS,
    RECOMMENDED_ACTIONS,
)


def parse_analyst_report(symbol: str, payload: dict[str, object]) -> AnalystReport:
    """解析 DeepSeek JSON 输出。"""
    return AnalystReport(
        symbol=symbol,
        timestamp=datetime.now(),
        executive_summary=str(payload.get("executive_summary", "")),
        facts=_as_str_list(payload.get("facts")),
        affected_assets=_as_str_list(payload.get("affected_assets")),
        transmission_chain=_as_str_list(payload.get("transmission_chain")),
        corroboration_assessment=str(payload.get("corroboration_assessment", "")),
        confidence=_clamp_float(payload.get("confidence"), 0.0, 1.0),
        sentiment_score=_clamp_float(payload.get("sentiment_score"), -1.0, 1.0),
        policy_risk_score=_clamp_float(payload.get("policy_risk_score"), 0.0, 1.0),
        novelty=_normalize_novelty(str(payload.get("novelty", "uncertain"))),
        recommended_action=_normalize_action(str(payload.get("recommended_action", "MONITOR"))),
        uncertainties=_as_str_list(payload.get("uncertainties")),
        human_review_required=bool(payload.get("human_review_required", False)),
    )


def report_to_key_events(report: AnalystReport) -> list[str]:
    """分析师报告摘要行。"""
    lines = [
        f"[analyst] {report.executive_summary[:120]}",
        f"confidence={report.confidence:.2f} action={report.recommended_action} novelty={report.novelty}",
    ]
    if report.human_review_required:
        lines.append("human_review_required=true")
    for fact in report.facts[:3]:
        lines.append(f"fact: {fact[:100]}")
    return lines


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _clamp_float(value: object, low: float, high: float) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(low, min(high, number))


def _normalize_novelty(value: str) -> str:
    lowered = value.lower().strip()
    if lowered in NOVELTY_LEVELS:
        return lowered
    if "black" in lowered or "swan" in lowered:
        return "black_swan"
    return "uncertain"


def _normalize_action(value: str) -> str:
    upper = value.upper().strip()
    if upper in RECOMMENDED_ACTIONS:
        return upper
    return "MONITOR"
