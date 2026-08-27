"""策略政策类型 — TradeSleeve 与 PolicyVerdict。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from quant_shell.common.types import Action


class TradeSleeve(StrEnum):
    """交易袖套 — 策略路由唯一轴。"""

    CORE = "core"
    THEME_SWING = "theme_swing"
    ETF_BETA = "etf_beta"
    CATALYST = "catalyst"
    BLOCKED = "blocked"


# 计入主题类暴露预算的袖套（theme + catalyst）
THEME_BUDGET_SLEEVES: frozenset[TradeSleeve] = frozenset(
    {TradeSleeve.THEME_SWING, TradeSleeve.CATALYST}
)


@dataclass(frozen=True)
class SleeveLimits:
    """单袖套仓位上限。"""

    max_position: float
    sleeve_budget: float


@dataclass
class PolicyVerdict:
    """L4 策略政策唯一输出 — 下游只消费、不重算纪律。"""

    sleeve: TradeSleeve
    sleeve_reason: str
    action: Action
    entry_eligible: bool
    block_reasons: list[str] = field(default_factory=list)
    max_position: float = 0.0
    suggested_position: float = 0.0
    rule_resolved: bool = False
    take_profit_pressure: float = 0.0

    def block_reason_text(self) -> str:
        """门控展示用拼接字符串。"""
        return "；".join(self.block_reasons)
