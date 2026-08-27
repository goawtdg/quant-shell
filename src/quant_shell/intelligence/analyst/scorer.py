"""规则分 + DeepSeek 分析师分融合。"""
from __future__ import annotations

from quant_shell.common.types import AnalystReport, IntelligenceBrief
from quant_shell.intelligence.analyst.constants import (
    ANALYST_WEIGHT_IN_BLEND,
    MAX_ANALYST_SENTIMENT_ABS,
    RULE_WEIGHT_IN_BLEND,
)

_HARD_DAMPEN_ACTIONS = frozenset({"HUMAN_ONLY", "REDUCE"})


def blend_sentiment_scores(
    rule_scores: dict[str, float],
    report: AnalystReport,
    brief: IntelligenceBrief,
) -> dict[str, float]:
    """融合规则情绪分与分析师输出（带权重上限）。

    分析师 sentiment 始终按 confidence 加权进入，不再因低置信整段丢弃。
    仅硬拦类（黑天鹅 / HUMAN_ONLY / REDUCE）半折 composite；普通 human_review 不暗折。
    fund_sentiment 无真实源，固定 0 且不参与 composite。
    """
    rule_cross = rule_scores["cross_validation"]
    analyst_cross = min(1.0, report.confidence * (1.0 + brief.corroboration_count / 5.0))
    # 分析师无印证时不要把 rule 的中性 0.5 压成更低的“伪空头”
    if brief.corroboration_count <= 0 and report.confidence < 0.55:
        cross_val = rule_cross
    else:
        cross_val = min(1.0, max(rule_cross, analyst_cross))

    analyst_sentiment = _cap_abs(report.sentiment_score, MAX_ANALYST_SENTIMENT_ABS)
    nlp = (
        rule_scores["nlp_score"] * RULE_WEIGHT_IN_BLEND
        + analyst_sentiment * ANALYST_WEIGHT_IN_BLEND * report.confidence
    )

    policy_risk = max(rule_scores["policy_risk"], report.policy_risk_score)
    buzz = rule_scores["social_buzz"]

    composite = _build_composite(nlp, cross_val, policy_risk, buzz, report)
    if _should_halve_composite(report):
        composite *= 0.5

    return {
        "nlp_score": max(-1.0, min(1.0, nlp)),
        "social_buzz": buzz,
        "policy_risk": policy_risk,
        "fund_sentiment": 0.0,
        "composite": max(-1.0, min(1.0, composite)),
        "cross_validation": cross_val,
    }


def _build_composite(
    nlp: float,
    cross_val: float,
    policy_risk: float,
    buzz: float,
    report: AnalystReport,
) -> float:
    """合成 composite（含 social_buzz；不含 fund_sentiment）。"""
    base = nlp * 0.40 + cross_val * 0.30 + buzz * 0.10 - policy_risk * 0.20
    if report.recommended_action == "REDUCE":
        base = min(base, -0.05)
    if report.recommended_action == "INCREASE":
        base = max(base, 0.15)
    return _cap_abs(base, MAX_ANALYST_SENTIMENT_ABS)


def _should_halve_composite(report: AnalystReport) -> bool:
    """仅硬拦类半折；普通 human_review / MONITOR 保持原生分数。"""
    novelty = (report.novelty or "").lower()
    action = (report.recommended_action or "").upper()
    if novelty == "black_swan":
        return True
    return action in _HARD_DAMPEN_ACTIONS


def _cap_abs(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))
