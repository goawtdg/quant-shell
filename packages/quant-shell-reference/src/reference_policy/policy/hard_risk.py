"""硬风险唯一源 — 只从 ContextPack 派生；LLM/Sim 不得发明或抹掉。"""
from __future__ import annotations

from quant_shell.common.constants import EvaluationMode
from quant_shell.common.hard_codes import HardCode, HARD_CODE_VALUES, is_hard_code, strip_hard_codes
from quant_shell.common.policy_types import TradeSleeve
from quant_shell.common.types import Action, AnalystReport, DecisionContextPack
from quant_shell.config.settings import settings

_HARD_ANALYST_ACTIONS = frozenset({"HUMAN_ONLY", "REDUCE"})

__all__ = [
    "HardCode",
    "HARD_CODE_VALUES",
    "is_hard_code",
    "strip_hard_codes",
    "derive_hard_codes",
    "tighten_action",
]


def derive_hard_codes(pack: DecisionContextPack) -> frozenset[HardCode]:
    """从 pack 派生硬码；禁止读 LLM/Sim risk_flags。"""
    codes: set[HardCode] = set()
    for msg in pack.monitor_alert_messages:
        if str(msg).upper().startswith("CRITICAL:"):
            codes.add(HardCode.MONITOR_CRITICAL)
            break
    if _intel_hard_block(pack.sentiment.analyst_report):
        codes.add(HardCode.INTEL_REVIEW_HARD)
    thr = float(settings.strategy_degradation_threshold)
    if pack.model_comparison.deviation < thr:
        codes.add(HardCode.STRATEGY_DEGRADED)
    return frozenset(codes)


_BULL_EXEMPT_REGIMES = frozenset({"bull", "weak_bull"})


def tighten_action(
    action: Action,
    codes: frozenset[HardCode],
    *,
    evaluation_mode: str,
    has_position: bool,
    holding_days: int = 0,
    unrealized_pnl_pct: float = 0.0,
    trade_sleeve: str = TradeSleeve.CORE.value,
    portfolio_deviation: float = 0.0,
    regime: str = "range",
) -> Action:
    """硬码收紧政策动作。

    分析师 REDUCE、HUMAN_ONLY、黑天鹅：没持仓就保持原动作；已持仓则减仓。
    STRATEGY_DEGRADED：入场保留 BUY（仓位由 commit 软缩放）。
    持仓退化 REDUCE：默认标的偏离；portfolio 模式用组合偏离；regime 门控时 bull 豁免。
    """
    analyst_exit = bool(
        codes & {HardCode.MONITOR_CRITICAL, HardCode.INTEL_REVIEW_HARD}
    )
    if analyst_exit:
        if evaluation_mode == EvaluationMode.ENTRY.value or not has_position:
            return action
        if action in (Action.EXIT, Action.REDUCE, Action.SELL):
            return action
        return Action.REDUCE
    if evaluation_mode == EvaluationMode.ENTRY.value:
        return action

    hold_degraded = False
    if has_position and action in (Action.BUY, Action.HOLD):
        thr = float(settings.strategy_degradation_threshold)
        if settings.strategy_degraded_hold_use_portfolio_deviation:
            hold_degraded = float(portfolio_deviation) < thr
        elif (
            settings.strategy_degraded_hold_tighten
            and HardCode.STRATEGY_DEGRADED in codes
        ):
            hold_degraded = True

    if hold_degraded:
        if settings.strategy_degraded_hold_regime_gated:
            reg = str(regime or "range").lower()
            if reg in _BULL_EXEMPT_REGIMES:
                return action
        if (
            str(trade_sleeve) == TradeSleeve.ETF_BETA.value
            and not settings.strategy_degraded_etf_hold_tighten
        ):
            return action
        grace = int(settings.strategy_degraded_hold_min_days)
        if grace > 0 and int(holding_days) < grace:
            return action
        if (
            settings.strategy_degraded_hold_reduce_only_if_loss
            and float(unrealized_pnl_pct) >= 0.0
        ):
            return action
        return Action.REDUCE

    if HardCode.STRATEGY_DEGRADED in codes and action == Action.BUY:
        return Action.WAIT
    return action


def _intel_hard_block(analyst: AnalystReport | None) -> bool:
    if analyst is None:
        return False
    if not settings.paper_relax_intel_review:
        return bool(analyst.human_review_required)
    novelty = (analyst.novelty or "").lower()
    action = (analyst.recommended_action or "").upper()
    if novelty == "black_swan":
        return True
    return action in _HARD_ANALYST_ACTIONS
