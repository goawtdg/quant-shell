"""组合级风险指标 — 权益、回撤、总仓位。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from quant_shell.common.types import PaperPortfolio
from quant_shell.config.settings import settings


@dataclass(frozen=True)
class PortfolioRiskSnapshot:
    """组合风险快照。"""

    equity: float
    portfolio_drawdown: float
    total_position_pct: float
    high_water_mark: float


def compute_portfolio_risk(
    portfolio: PaperPortfolio,
    prices: dict[str, float],
) -> PortfolioRiskSnapshot:
    """计算组合权益与回撤。

    Args:
        portfolio: 模拟账户。
        prices: symbol -> 最新价。

    Returns:
        组合风险快照。
    """
    equity = portfolio.mark_equity(prices)
    hwm = max(portfolio.high_water_mark, portfolio.initial_cash, equity)
    drawdown = 0.0
    if hwm > 0 and equity < hwm:
        drawdown = (hwm - equity) / hwm
    total_pct = portfolio.total_position_pct(prices)
    return PortfolioRiskSnapshot(
        equity=equity,
        portfolio_drawdown=drawdown,
        total_position_pct=total_pct,
        high_water_mark=hwm,
    )


def portfolio_drawdown_breached(snapshot: PortfolioRiskSnapshot) -> bool:
    """组合回撤是否触及上限。"""
    return snapshot.portfolio_drawdown >= settings.portfolio_max_drawdown


def holding_days(position_opened_at: datetime | None, now: datetime) -> int:
    """计算持有天数。

    ``opened_at`` 缺失时按新人（0 日），禁止假装已满最短持有期。
    """
    if position_opened_at is None:
        return 0
    delta = now.date() - position_opened_at.date()
    return max(delta.days, 0)
