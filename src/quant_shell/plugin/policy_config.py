"""SleevePolicyConfig — 框架侧策略阈值 schema（与具体 playbook 解耦）。"""
from __future__ import annotations

from dataclasses import dataclass

from quant_shell.config.settings import Settings


@dataclass(frozen=True)
class SleevePolicyConfig:
    """策略政策阈值 — 唯一读取 settings 的入口。"""

    core_pe_block_percentile: float
    core_min_hold_days: int
    theme_enabled: bool
    theme_max_position: float
    theme_sleeve_budget: float
    theme_max_hold_days: int
    theme_exit_dd: float
    theme_min_sentiment: float
    theme_min_signal_conf: float
    signal_threshold_moderate: float
    signal_threshold_strong: float
    signal_moderate_buy_scale: float
    single_stock_limit: float
    factor_min_coverage: float
    pick_filter_board_permission: bool
    take_profit_partial_pct: float
    take_profit_scale_pct: float
    take_profit_full_pct: float
    take_profit_trail_pct: float
    take_profit_pe_rich: float
    take_profit_pe_exit: float


def load_policy_config(src: Settings | None = None) -> SleevePolicyConfig:
    """从全局或注入的 Settings 构建配置。"""
    if src is None:
        from quant_shell.config import settings as settings_mod

        s = settings_mod.settings
    else:
        s = src
    return SleevePolicyConfig(
        core_pe_block_percentile=s.core_pe_block_percentile,
        core_min_hold_days=s.core_min_hold_days,
        theme_enabled=s.theme_swing_enabled,
        theme_max_position=s.theme_max_position,
        theme_sleeve_budget=s.theme_sleeve_budget,
        theme_max_hold_days=s.theme_max_hold_days,
        theme_exit_dd=s.theme_exit_dd,
        theme_min_sentiment=s.theme_min_sentiment,
        theme_min_signal_conf=s.theme_min_signal_conf,
        signal_threshold_moderate=s.signal_threshold_moderate,
        signal_threshold_strong=s.signal_threshold_strong,
        signal_moderate_buy_scale=s.signal_moderate_buy_scale,
        single_stock_limit=s.single_stock_limit,
        factor_min_coverage=s.factor_min_coverage,
        pick_filter_board_permission=s.pick_filter_board_permission,
        take_profit_partial_pct=s.take_profit_partial_pct,
        take_profit_scale_pct=s.take_profit_scale_pct,
        take_profit_full_pct=s.take_profit_full_pct,
        take_profit_trail_pct=s.take_profit_trail_pct,
        take_profit_pe_rich=s.take_profit_pe_rich,
        take_profit_pe_exit=s.take_profit_pe_exit,
    )
