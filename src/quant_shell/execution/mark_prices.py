"""纸面组合盯市 — 全持仓统一取价（TTL live）；缺价不得用成本冒充市值。"""
from __future__ import annotations

from dataclasses import dataclass

from quant_shell.common import audit
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import PaperPortfolio
from quant_shell.data.live_price import fetch_live_fill_prices

logger = get_logger(__name__)


@dataclass(frozen=True)
class MarkResult:
    """盯市结果：已知市价 + 缺失标的。"""

    prices: dict[str, float]
    missing: list[str]


def mark_portfolio_prices(
    portfolio: PaperPortfolio,
    prefer: dict[str, float] | None = None,
    *,
    fetch_live: bool = True,
    force_refresh: bool | None = None,
) -> MarkResult:
    """为全部持仓构建市价表。

    优先级：``prefer`` → 实时价。缺 live **不**回退成本价。

    Args:
        portfolio: 纸面账户。
        prefer: 已知价（如刚成交标的）。
        fetch_live: False 时跳过网络。
        force_refresh: True 强制刷新；False 只用缓存；None 按 TTL（默认）。
    """
    prefer = prefer or {}
    prices: dict[str, float] = {}
    need_live: list[str] = []

    for sym in portfolio.positions:
        if sym in prefer and prefer[sym] > 0:
            prices[sym] = float(prefer[sym])
        else:
            need_live.append(sym)

    missing: list[str] = []
    if fetch_live and need_live:
        live_map = fetch_live_fill_prices(need_live, force_refresh=force_refresh)
        for sym in need_live:
            if sym in live_map and live_map[sym] > 0:
                prices[sym] = float(live_map[sym])
            else:
                missing.append(sym)
    else:
        missing.extend(need_live)

    for sym, px in prefer.items():
        if sym not in prices and px > 0:
            prices[sym] = float(px)
            if sym in missing:
                missing.remove(sym)

    if missing:
        audit.emit(
            layer="L1",
            event="mark_missing",
            severity="ERROR",
            error_code="NO_LIVE_PRICE",
            message="mark prices missing symbols",
            data={"missing": missing},
        )

    logger.info(
        "mark_portfolio_prices n=%d missing=%d force_refresh=%s",
        len(prices),
        len(missing),
        force_refresh,
    )
    return MarkResult(prices=prices, missing=missing)
