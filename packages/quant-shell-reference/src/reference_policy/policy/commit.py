"""政策定稿 — 唯一成交动作入口（硬码来自 pack，叙述仅 soft）。"""
from __future__ import annotations

from quant_shell.common.constants import EvaluationMode
from quant_shell.common.types import AIDecision, Action, DecisionContextPack
from quant_shell.config.settings import settings
from reference_policy.policy.hard_risk import (
    HardCode,
    derive_hard_codes,
    strip_hard_codes,
    tighten_action,
)
from reference_policy.policy.types import PolicyVerdict


def commit_decision(
    verdict: PolicyVerdict,
    narrative: AIDecision | None,
    pack: DecisionContextPack | None,
    *,
    evaluation_mode: str,
    signal_confidence: float = 0.0,
) -> AIDecision:
    """以 PolicyVerdict.action 为默认；硬码从 pack 收紧；叙事 action 一律丢弃。"""
    flags: list[str] = [f"sleeve:{verdict.sleeve.value}"]
    chain: list[str] = []
    if verdict.block_reasons:
        chain.extend(verdict.block_reasons)
    elif verdict.sleeve_reason:
        chain.append(verdict.sleeve_reason)

    human_review = verdict.action in (Action.REDUCE, Action.EXIT, Action.WAIT)
    confidence = (
        max(0.5, verdict.take_profit_pressure)
        if evaluation_mode == EvaluationMode.HOLD.value
        else float(signal_confidence)
    )
    suggested = (
        verdict.suggested_position if verdict.action == Action.BUY else 0.0
    )

    if narrative is not None:
        chain.extend(narrative.reasoning_chain)
        for f in strip_hard_codes(list(narrative.risk_flags)):
            if f not in flags:
                flags.append(f)
        if narrative.confidence > 0:
            confidence = narrative.confidence
        human_review = human_review or narrative.human_review_required

    codes: frozenset[HardCode] = frozenset()
    has_position = False
    holding_days = 0
    unrealized_pnl_pct = 0.0
    if pack is not None:
        codes = derive_hard_codes(pack)
        has_position = pack.risk_state.current_position > 0
        holding_days = int(pack.risk_state.holding_days or 0)
        unrealized_pnl_pct = float(pack.risk_state.unrealized_pnl_pct or 0.0)
        for c in sorted(codes, key=lambda x: x.value):
            if c.value not in flags:
                flags.append(c.value)

    prior = verdict.action
    trade_sleeve = pack.trade_sleeve if pack is not None else ""
    portfolio_dev = (
        float(pack.model_comparison.portfolio_deviation) if pack is not None else 0.0
    )
    regime = pack.model_comparison.regime if pack is not None else "range"
    action = tighten_action(
        prior,
        codes,
        evaluation_mode=evaluation_mode,
        has_position=has_position,
        holding_days=holding_days,
        unrealized_pnl_pct=unrealized_pnl_pct,
        trade_sleeve=trade_sleeve,
        portfolio_deviation=portfolio_dev,
        regime=regime,
    )
    # 入场禁止 HOLD：无仓位时观望一律 WAIT（与 linkage 文案一致）
    if evaluation_mode == EvaluationMode.ENTRY.value and action == Action.HOLD:
        action = Action.WAIT
    if action != prior:
        if HardCode.MONITOR_CRITICAL in codes or HardCode.INTEL_REVIEW_HARD in codes:
            tag = "硬风险收紧"
        elif HardCode.STRATEGY_DEGRADED in codes:
            tag = "策略退化收紧"
        elif (
            evaluation_mode == EvaluationMode.ENTRY.value
            and prior == Action.HOLD
            and action == Action.WAIT
        ):
            tag = "入场观望"
        else:
            tag = "动作收紧"
        chain.insert(0, f"POLICY_COMMIT: {tag} {prior.value} → {action.value}")
        flags.append("POLICY_HARD_TIGHTEN")
        suggested = 0.0
        human_review = True

    if action == Action.BUY:
        suggested = _positive_min(
            suggested,
            verdict.suggested_position,
            verdict.max_position,
        )
        if suggested <= 0:
            suggested = max(verdict.suggested_position, 0.0)
        if HardCode.STRATEGY_DEGRADED in codes:
            scale = float(settings.strategy_degraded_entry_scale)
            suggested *= max(0.0, min(1.0, scale))
            chain.append(f"STRATEGY_DEGRADED: 入场软收紧仓位×{scale:.2f}")

    if verdict.rule_resolved and narrative is None:
        flags.append("RULE_RESOLVED")

    if codes:
        human_review = True

    return AIDecision(
        action=action,
        confidence=confidence,
        reasoning_chain=chain or [verdict.sleeve_reason or "policy"],
        risk_flags=flags,
        suggested_position_change=suggested if action == Action.BUY else 0.0,
        human_review_required=human_review,
    )


def _positive_min(*values: float) -> float:
    positives = [float(v) for v in values if v is not None and float(v) > 0]
    if not positives:
        return 0.0
    return min(positives)
