"""袖套分类 — 唯一路由入口。"""
from __future__ import annotations

from quant_shell.common.types import Action, AnalystReport, TradingSignal
from quant_shell.data.symbol import (
    BOARD_PERMISSION_BLOCK_REASON,
    is_etf,
    requires_board_permission,
)
from reference_policy.policy.config import SleevePolicyConfig
from reference_policy.policy.types import TradeSleeve

_CATALYST_MIN_CV = 0.75
_CATALYST_MIN_ANALYST_CONF = 0.55


def classify_sleeve(
    *,
    symbol: str,
    pe_percentile: float,
    pe_reliable: bool,
    sentiment_composite: float,
    signal: TradingSignal | None,
    config: SleevePolicyConfig,
    catalyst_ok: bool = False,
) -> tuple[TradeSleeve, str]:
    """按资产类型 / 估值 / 催化剂 / 叙事动能路由到四剧本或 blocked。"""
    if config.pick_filter_board_permission and requires_board_permission(symbol):
        return TradeSleeve.BLOCKED, BOARD_PERMISSION_BLOCK_REASON

    if is_etf(symbol):
        return TradeSleeve.ETF_BETA, "ETF→etf_beta"

    expensive = pe_reliable and pe_percentile >= config.core_pe_block_percentile
    if not expensive:
        return TradeSleeve.CORE, "估值未触发高估路由"

    if catalyst_ok:
        return (
            TradeSleeve.CATALYST,
            f"高估PE={pe_percentile:.0%}且强催化剂→catalyst",
        )

    theme_ok = _theme_momentum_ok(
        sentiment_composite=sentiment_composite,
        signal=signal,
        config=config,
    )
    if config.theme_enabled and theme_ok:
        return (
            TradeSleeve.THEME_SWING,
            f"高估PE={pe_percentile:.0%}且主题动能达标→theme_swing",
        )
    if not config.theme_enabled:
        return TradeSleeve.BLOCKED, "高估且主题短线未启用"
    return TradeSleeve.BLOCKED, f"高估PE={pe_percentile:.0%}但主题动能与催化剂不足"


def compute_catalyst_ok(
    *,
    cross_validation: float,
    analyst: AnalystReport | None,
) -> bool:
    """唯一催化剂证据（禁止用合成 key_events / 摘要行冒充）。"""
    if analyst is None:
        return False
    if cross_validation < _CATALYST_MIN_CV:
        return False
    if float(analyst.confidence) < _CATALYST_MIN_ANALYST_CONF:
        return False
    return len(analyst.facts) >= 1


def _theme_momentum_ok(
    *,
    sentiment_composite: float,
    signal: TradingSignal | None,
    config: SleevePolicyConfig,
) -> bool:
    if sentiment_composite >= config.theme_min_sentiment:
        return True
    if signal is None:
        return False
    return (
        signal.direction == Action.BUY
        and abs(float(signal.opportunity)) >= config.theme_min_signal_conf
    )
