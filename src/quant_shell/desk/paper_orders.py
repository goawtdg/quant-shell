"""Desk 人工纸面下单 — 只走 quant_shell PaperTradingEngine。"""
from __future__ import annotations

import re
from typing import Any

from quant_shell.common import audit
from quant_shell.common.types import Action, OrderRequest
from quant_shell.desk.paths import paper_dir
from quant_shell.execution.mark_prices import mark_portfolio_prices
from quant_shell.execution.paper_engine import PaperTradingEngine
from quant_shell.execution.portfolio import PaperPortfolioStore

_SYMBOL_RE = re.compile(r"^\d{6}$")
_ALLOWED = frozenset({Action.BUY, Action.SELL, Action.REDUCE, Action.EXIT})
_MAX_NOTIONAL_PCT = 0.25


def place_manual_order(
    *,
    symbol: str,
    action: str,
    quantity: float,
    reason: str,
    confirm: bool,
    run_id: str = "",
    sleeve: str = "catalyst",
) -> dict[str, Any]:
    if not confirm:
        raise PermissionError("confirm must be true")
    code = str(symbol or "").strip()
    if not _SYMBOL_RE.match(code):
        raise ValueError("symbol 须为 6 位数字代码")
    try:
        act = Action(str(action or "").upper())
    except ValueError as exc:
        raise ValueError(f"unsupported action: {action}") from exc
    if act not in _ALLOWED:
        raise ValueError(f"action 须为 {[a.value for a in _ALLOWED]}")
    qty = float(quantity)
    if qty <= 0:
        raise ValueError("quantity 须 > 0")
    note = str(reason or "").strip()
    if not note:
        raise ValueError("reason 必填")

    store = PaperPortfolioStore(base_dir=paper_dir())
    engine = PaperTradingEngine(store=store)
    portfolio = store.load()
    if act == Action.BUY:
        marked = mark_portfolio_prices(portfolio, prefer={}, fetch_live=True)
        equity = float(portfolio.total_equity(marked.prices))
        px = float(marked.prices.get(code) or 0.0)
        if px <= 0:
            raise ValueError("无法取得现价，拒绝人工买入")
        notional = qty * px
        if equity > 0 and notional > equity * _MAX_NOTIONAL_PCT:
            raise ValueError(
                f"单笔名义 {notional:.0f} 超过权益 {_MAX_NOTIONAL_PCT:.0%} 上限"
            )

    order = OrderRequest(
        symbol=code,
        action=act,
        quantity=qty,
        position_pct=0.0,
        reason=f"HUMAN_OVERRIDE: {note}",
        sleeve=(sleeve or "catalyst").strip() or "catalyst",
    )
    result = engine.execute(order, evaluation_mode="manual", unrealized_pnl_pct=0.0)
    audit.emit(
        layer="L6",
        event="human_override",
        severity="INFO" if result.status == "filled" else "WARN",
        symbol=code,
        run_id=str(run_id or ""),
        message=result.message,
        data={
            "action": act.value,
            "quantity": result.quantity,
            "status": result.status,
            "fill_price": result.fill_price,
            "reason": note,
        },
    )
    return {
        "status": result.status,
        "symbol": result.symbol,
        "action": result.action,
        "quantity": result.quantity,
        "fill_price": result.fill_price,
        "message": result.message,
        "cash_after": result.cash_after,
        "equity": result.equity,
        "run_id": run_id or "",
    }
