"""袖套分类 — 唯一路由入口。"""
from __future__ import annotations

from quant_shell.common.types import AnalystReport, TradingSignal
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
    """个股一律走延续袖套。高估只在入场缩仓，不再改道到够不着的主题门槛。"""
    del sentiment_composite, signal, catalyst_ok
    if config.pick_filter_board_permission and requires_board_permission(symbol):
        return TradeSleeve.BLOCKED, BOARD_PERMISSION_BLOCK_REASON

    if is_etf(symbol):
        return TradeSleeve.ETF_BETA, "ETF→etf_beta"

    if pe_reliable and pe_percentile >= config.core_pe_block_percentile:
        return (
            TradeSleeve.CORE,
            f"高估PE={pe_percentile:.0%}只缩仓，不改道",
        )
    return TradeSleeve.CORE, "个股延续袖套"


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
