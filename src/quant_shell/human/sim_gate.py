"""模拟盘叙述门 — 只产软叙述；成交由 commit_decision 定稿。"""
from __future__ import annotations

from quant_shell.common.constants import EvaluationMode
from quant_shell.common.interfaces import HumanReviewGate
from quant_shell.common.types import AIDecision, Action, DecisionContextPack
from quant_shell.config.settings import settings
from quant_shell.data.pe_quality import pe_unreliable_reason

_SIM_REASON_SOFT_REVIEW = "情报建议人工关注（软标），不阻断信号驱动入场"
_SIM_REASON_NO_SIGNAL = "分析师结论：无融合信号，证据不足，维持空仓（HOLD）"
_SIM_REASON_NARRATE = "开平仓纪律以 PolicyVerdict / commit 为准，本门仅软叙述"


class SimHumanReviewGate(HumanReviewGate):
    """入场/持有：软叙述；硬风险由 hard_risk.derive_hard_codes 唯一派生。"""

    def reason(self, pack: DecisionContextPack) -> AIDecision:
        if pack.evaluation_mode == EvaluationMode.HOLD.value:
            return AIDecision(
                action=Action.HOLD,
                confidence=0.0,
                reasoning_chain=["持有裁决应由 PolicyVerdict 提供"],
                risk_flags=["EXPECT_POLICY_HOLD"],
                human_review_required=False,
            )
        return self._reason_entry(pack)

    def _reason_entry(self, pack: DecisionContextPack) -> AIDecision:
        chain: list[str] = []
        risk_flags: list[str] = []
        human_review = False
        if pack.trade_sleeve:
            chain.append(f"袖套={pack.trade_sleeve} {pack.sleeve_reason}".strip())
            risk_flags.append(f"sleeve:{pack.trade_sleeve}")

        analyst = pack.sentiment.analyst_report
        if analyst and analyst.human_review_required:
            chain.append(_SIM_REASON_SOFT_REVIEW)
            risk_flags.append("INTEL_REVIEW_SOFT")
            human_review = True

        signal = pack.signal
        if not signal:
            chain.append(_SIM_REASON_NO_SIGNAL)
            return AIDecision(
                action=Action.HOLD,
                confidence=0.0,
                reasoning_chain=chain,
                risk_flags=risk_flags,
                human_review_required=human_review,
            )

        chain.append(
            f"融合信号 {signal.direction.value}, "
            f"strength={signal.strength.value}, opportunity={signal.opportunity:.2f}"
        )
        alpha = signal.components.get("alpha", 0.0)
        math = signal.components.get("math", 0.0)
        chain.append(f"因子分量 math={math:.2f} alpha={alpha:.2f}")
        unreliable = pe_unreliable_reason(pack.market)
        if unreliable:
            chain.append(unreliable)
            risk_flags.append("PE_UNRELIABLE")

        chain.append(_SIM_REASON_NARRATE)
        if pack.factor_degraded_count > 0:
            risk_flags.append(f"FACTOR_DEGRADED:{pack.factor_degraded_count}")
            chain.append(f"因子降级 {pack.factor_degraded_count} 个，信号权重已下调")

        return AIDecision(
            action=Action.HOLD,
            confidence=abs(float(signal.opportunity)),
            reasoning_chain=chain,
            risk_flags=risk_flags,
            suggested_position_change=0.0,
            human_review_required=human_review,
        )

    def confirm(self, decision: AIDecision, auto_approve: bool = False) -> bool:
        """纸面：auto_approve 时对可执行动作放行；人审旗不挡成交。"""
        if not (settings.paper_auto_approve or auto_approve):
            return False
        return decision.action in (
            Action.BUY,
            Action.SELL,
            Action.REDUCE,
            Action.EXIT,
        )
