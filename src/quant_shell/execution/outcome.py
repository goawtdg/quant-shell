"""纸面成交的亏损边界。记录缺数字就失败，不用 0 填上。"""
from __future__ import annotations

from quant_shell.common.exceptions import ValidationError

_FILL_ACTIONS = frozenset({"BUY", "SELL", "REDUCE", "EXIT"})
_EXIT_ACTIONS = frozenset({"SELL", "REDUCE", "EXIT"})


def summarize_loss_boundary(records: list[dict[str, object]]) -> dict[str, object]:
    """开仓次数、最差单笔亏损、权益最大回撤、卖出印花税。

    单笔亏损用成交记录上的 unrealized_pnl_pct。没有卖出时最差亏损为 None。
    权益点少于 2 个时，最大回撤为 None。
    """
    buys = [row for row in records if row.get("action") == "BUY"]
    exits = [row for row in records if row.get("action") in _EXIT_ACTIONS]
    losses: list[float] = []
    equities: list[float] = []
    stamp_duty = 0.0
    for row in records:
        action = row.get("action")
        if action not in _FILL_ACTIONS:
            continue
        if "stamp_duty" not in row or "equity" not in row:
            raise ValidationError(
                message="成交记录缺少印花税或权益",
                suggestion="买入 stamp_duty 写 0，卖出写入实际税额和当时权益",
            )
        stamp_duty += float(row["stamp_duty"])
        equities.append(float(row["equity"]))
        if action in _EXIT_ACTIONS:
            if row.get("unrealized_pnl_pct") is None:
                raise ValidationError(
                    message="卖出记录缺少 unrealized_pnl_pct",
                    suggestion="写入卖出当时的持仓盈亏",
                )
            pnl = float(row["unrealized_pnl_pct"])
            if pnl < 0:
                losses.append(pnl)
    return {
        "buy_count": len(buys),
        "exit_count": len(exits),
        "worst_loss_pct": min(losses) if losses else None,
        "max_drawdown": _max_drawdown(equities) if len(equities) >= 2 else None,
        "stamp_duty": stamp_duty,
    }


def _max_drawdown(equities: list[float]) -> float:
    peak = equities[0]
    worst = 0.0
    for equity in equities:
        peak = max(peak, equity)
        if peak > 0:
            worst = min(worst, equity / peak - 1.0)
    return worst
