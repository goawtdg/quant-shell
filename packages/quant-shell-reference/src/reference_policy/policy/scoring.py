"""入场机会门槛 + 质量缩仓 — 唯一评分入口（禁止他处再写一套）。"""
from __future__ import annotations

from quant_shell.common.exceptions import BusinessError
from quant_shell.common.types import Action, TradingSignal
from quant_shell.config.settings import settings
from reference_policy.policy.config import SleevePolicyConfig


def apply_entry_score(
    signal: TradingSignal | None,
    *,
    factor_coverage: float,
    factor_active: int,
    factor_usable: int,
    cross_validation: float,
    sleeve_max: float,
    config: SleevePolicyConfig,
) -> tuple[Action, float, list[str]]:
    """机会门槛 → WAIT/BUY；质量只缩 suggested。缺信号或非法质量输入则显式失败。"""
    if signal is None:
        return Action.WAIT, 0.0, ["无融合信号，维持空仓"]

    opp = float(signal.opportunity)
    abs_opp = abs(opp)
    moderate = float(config.signal_threshold_moderate)
    strong = float(config.signal_threshold_strong)
    chain: list[str] = []

    if abs_opp < moderate:
        chain.append(f"机会强度{abs_opp:.4f}<开仓线{moderate:.4f}")
        signal.quality = _compute_quality(
            factor_coverage=factor_coverage,
            factor_active=factor_active,
            factor_usable=factor_usable,
            cross_validation=cross_validation,
            coverage_floor=float(settings.factor_coverage_scale_floor),
        )
        return Action.WAIT, 0.0, chain

    if opp <= 0:
        chain.append(f"机会方向非买入 opportunity={opp:.2f}")
        signal.quality = _compute_quality(
            factor_coverage=factor_coverage,
            factor_active=factor_active,
            factor_usable=factor_usable,
            cross_validation=cross_validation,
            coverage_floor=float(settings.factor_coverage_scale_floor),
        )
        return Action.WAIT, 0.0, chain

    if abs_opp >= strong:
        suggested = float(sleeve_max)
        chain.append(f"机会强度{abs_opp:.2f}达强档，满袖套上限")
    else:
        suggested = float(sleeve_max) * float(config.signal_moderate_buy_scale)
        chain.append(
            f"机会强度{abs_opp:.2f}中档，仓位×{config.signal_moderate_buy_scale:.2f}"
        )

    quality = _compute_quality(
        factor_coverage=factor_coverage,
        factor_active=factor_active,
        factor_usable=factor_usable,
        cross_validation=cross_validation,
        coverage_floor=float(settings.factor_coverage_scale_floor),
    )
    signal.quality = quality
    if quality < 1.0 - 1e-12:
        suggested *= quality
        chain.append(
            f"QUALITY_SCALE: coverage={factor_coverage:.2f} "
            f"active={factor_active} usable={factor_usable} → size×{quality:.2f}"
        )
    return Action.BUY, suggested, chain


def _compute_quality(
    *,
    factor_coverage: float,
    factor_active: int,
    factor_usable: int,
    cross_validation: float,
    coverage_floor: float,
) -> float:
    if factor_coverage < 0 or factor_coverage > 1.0 + 1e-9:
        raise BusinessError(
            message=f"factor_coverage 非法: {factor_coverage}",
            suggestion="检查 FactorHealth / ContextPack.factor_coverage",
        )
    if factor_active < 0 or factor_usable < 0:
        raise BusinessError(
            message=f"因子计数非法 active={factor_active} usable={factor_usable}",
            suggestion="检查 FactorHealth 计数",
        )
    if cross_validation < 0 or cross_validation > 1.0 + 1e-9:
        raise BusinessError(
            message=f"cross_validation 非法: {cross_validation}",
            suggestion="检查 SentimentFactors.cross_validation",
        )
    if _is_factor_green(factor_active, factor_usable, factor_coverage):
        return 1.0
    # 质量 = coverage 地板缩放 × CV 轻量缩放（公式仅此一份）
    cov_q = max(coverage_floor, min(1.0, factor_coverage))
    cv_q = 0.5 + 0.5 * float(cross_validation)
    return max(coverage_floor, min(1.0, cov_q * cv_q))


def _is_factor_green(active: int, usable: int, coverage: float) -> bool:
    return (
        active >= settings.factor_min_active
        and usable >= settings.factor_green_min_usable
        and coverage >= settings.factor_min_coverage
    )
