"""第 5 层硬风控 — L1 规则，AI 不可绕过。"""
from __future__ import annotations

from quant_shell.common.constants import (
    EvaluationMode,
    RiskAction,
    RiskViolation,
)
from quant_shell.common.interfaces import RiskEngine
from quant_shell.common.types import Action, DecisionContextPack, PipelineContext, RiskVerdict
from quant_shell.config.settings import settings

_DE_RISK_ACTIONS = frozenset(
    {Action.SELL.value, Action.REDUCE.value, Action.EXIT.value}
)

# 单票 ATH 回撤软降仓下限
_SYMBOL_DD_SCALE_FLOOR = 0.35


class HardRiskGate(RiskEngine):
    """基于规则的硬风控门控（入场/持有双模式）。"""

    def evaluate(self, ctx: PipelineContext, proposed_action: str) -> RiskVerdict:
        """评估是否允许执行 proposed_action。

        Args:
            ctx: 含 context_pack 的流水线上下文。
            proposed_action: AI 或策略建议的动作。

        Returns:
            风控裁决，含违规列表与最大允许仓位。
        """
        if ctx.context_pack is None:
            return self._blocked([RiskViolation.NO_CONTEXT_PACK])
        violations = self._collect_violations(ctx.context_pack, ctx)
        approved = self._approve(ctx, proposed_action, violations)
        return RiskVerdict(
            approved=approved,
            violations=violations,
            max_allowed_position=self._max_allowed_position(ctx),
            action=RiskAction.EXECUTE if approved else RiskAction.BLOCK,
        )

    def _approve(
        self,
        ctx: PipelineContext,
        proposed_action: str,
        violations: list[RiskViolation],
    ) -> bool:
        """按评估模式决定是否放行。"""
        mode = ctx.evaluation_mode
        action = proposed_action
        pack = ctx.context_pack
        has_position = bool(pack and pack.risk_state.current_position > 0)

        if mode == EvaluationMode.HOLD.value:
            if action == Action.BUY.value:
                return False
            if action in _DE_RISK_ACTIONS:
                return has_position
            return True

        if action == Action.BUY.value:
            if not ctx.entry_eligible:
                return False
            # 单票 ATH 回撤不再硬拦；组合回撤 / 总仓 / 因子可用 / 入场资格 仍硬拦
            blocking = {
                RiskViolation.PORTFOLIO_DRAWDOWN_BREACH,
                RiskViolation.TOTAL_POSITION_LIMIT,
                RiskViolation.FACTOR_HEALTH_CRITICAL,
                RiskViolation.ENTRY_NOT_ELIGIBLE,
            }
            return not any(v in violations for v in blocking)

        if action in _DE_RISK_ACTIONS:
            return has_position

        return True

    def _collect_violations(
        self, pack: DecisionContextPack, ctx: PipelineContext
    ) -> list[RiskViolation]:
        """收集触发的违规项。

        单票 current_drawdown 超 MAX_DRAWDOWN 不再记 DRAWDOWN_BREACH（改软缩仓）。
        """
        violations: list[RiskViolation] = []
        if pack.risk_state.portfolio_drawdown >= settings.portfolio_max_drawdown:
            violations.append(RiskViolation.PORTFOLIO_DRAWDOWN_BREACH)
        if pack.risk_state.total_position_pct > settings.total_position_limit:
            violations.append(RiskViolation.TOTAL_POSITION_LIMIT)
        if self._factor_health_critical(ctx):
            violations.append(RiskViolation.FACTOR_HEALTH_CRITICAL)
        if (
            ctx.evaluation_mode == EvaluationMode.ENTRY.value
            and not ctx.entry_eligible
        ):
            violations.append(RiskViolation.ENTRY_NOT_ELIGIBLE)
        if (
            ctx.evaluation_mode == EvaluationMode.HOLD.value
            and ctx.ai_decision
            and ctx.ai_decision.action == Action.BUY
        ):
            violations.append(RiskViolation.ADD_TO_POSITION_BLOCKED)
        return violations

    def _factor_health_critical(self, ctx: PipelineContext) -> bool:
        """可用因子过少时硬拦（禁用数量本身不拦截）。"""
        if settings.paper_relax_factor_gate:
            return False
        fh = ctx.factor_health
        if fh is None:
            return False
        return fh.usable_count < settings.factor_min_usable

    def _max_allowed_position(self, ctx: PipelineContext) -> float:
        """计算最大允许仓位（因子 YELLOW + 单票 DD 软降）。"""
        pack = ctx.context_pack
        if pack is None:
            return 0.0
        rs = pack.risk_state
        if rs.portfolio_drawdown >= settings.portfolio_max_drawdown:
            return 0.0
        base = min(
            settings.kelly_cap,
            rs.kelly_suggested_position,
            settings.single_stock_limit,
        )
        if ctx.policy_verdict is None:
            from quant_shell.common.exceptions import BusinessError

            raise BusinessError(
                message="HardRiskGate 缺少 policy_verdict",
                suggestion="确保 evaluate_policy 已定稿",
            )
        vmax = float(ctx.policy_verdict.max_position)
        if vmax > 0:
            base = min(base, vmax)
        return base * self._symbol_drawdown_scale(pack)

    def _symbol_drawdown_scale(self, pack: DecisionContextPack) -> float:
        """单票相对 ATH 回撤超 MAX_DRAWDOWN 时软降仓，不硬拦。"""
        dd = pack.risk_metrics.current_drawdown
        limit = settings.max_drawdown
        if dd <= limit:
            return 1.0
        overrun = dd - limit
        return max(_SYMBOL_DD_SCALE_FLOOR, 1.0 - overrun)

    def _blocked(self, violations: list[RiskViolation]) -> RiskVerdict:
        """构造拦截裁决。"""
        return RiskVerdict(approved=False, violations=violations, action=RiskAction.BLOCK)
