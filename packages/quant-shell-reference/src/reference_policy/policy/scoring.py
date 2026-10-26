"""入场只看 63 日收益是否过线。因子覆盖率不缩仓。"""
from __future__ import annotations

from quant_shell.common.types import Action, TradingSignal
from reference_policy.policy.config import SleevePolicyConfig


def apply_entry_score(
    signal: TradingSignal | None,
    *,
    sleeve_max: float,
    config: SleevePolicyConfig,
) -> tuple[Action, float, list[str]]:
    """收益达到开仓线才买。没有信号时明确观望。"""
    if signal is None:
        return Action.WAIT, 0.0, ["无 63 日收益，维持空仓"]

    opp = float(signal.opportunity)
    moderate = float(config.signal_threshold_moderate)
    strong = float(config.signal_threshold_strong)

    if opp < moderate:
        return Action.WAIT, 0.0, [f"63日收益{opp:.2%}<开仓线{moderate:.2%}"]

    if opp >= strong:
        return Action.BUY, float(sleeve_max), [f"63日收益{opp:.2%}达强档，满袖套上限"]

    suggested = float(sleeve_max) * float(config.signal_moderate_buy_scale)
    return (
        Action.BUY,
        suggested,
        [f"63日收益{opp:.2%}中档，仓位×{config.signal_moderate_buy_scale:.2f}"],
    )
