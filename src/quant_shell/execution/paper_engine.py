"""模拟盘执行引擎 — 虚拟成交、持仓与 P&L。"""
from __future__ import annotations

import copy
from datetime import datetime

from quant_shell.common import audit
from quant_shell.common.atomic_io import file_lock
from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.interfaces import ExecutionEngine
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import Action, ExecutionResult, OrderRequest, PaperPosition
from quant_shell.config.settings import settings
from quant_shell.data.live_price import fetch_live_fill_price
from quant_shell.risk.portfolio_risk import compute_portfolio_risk
from quant_shell.execution.constants import (
    EXECUTION_STATUS_FILLED,
    EXECUTION_STATUS_SKIPPED,
    LOT_SIZE,
    STAMP_DUTY_RATE,
)
from quant_shell.execution.mark_prices import mark_portfolio_prices
from quant_shell.execution.portfolio import PaperPortfolioStore

logger = get_logger(__name__)

_FILL_PRICE_DRIFT_WARN = 0.02


class PaperTradingEngine(ExecutionEngine):
    """纸面交易：按**实时市价**模拟成交，更新虚拟账户。"""

    def __init__(self, store: PaperPortfolioStore | None = None) -> None:
        self._store = store or PaperPortfolioStore()

    def execute(
        self,
        order: OrderRequest,
        *,
        evaluation_mode: str = "entry",
        unrealized_pnl_pct: float = 0.0,
    ) -> ExecutionResult:
        """模拟提交订单并更新持仓（成交价只认实时行情；账户与日志同锁同成败）。"""
        with file_lock(self._store.portfolio_path):
            return self._execute_locked(
                order,
                evaluation_mode=evaluation_mode,
                unrealized_pnl_pct=unrealized_pnl_pct,
            )

    def _execute_locked(
        self,
        order: OrderRequest,
        *,
        evaluation_mode: str,
        unrealized_pnl_pct: float,
    ) -> ExecutionResult:
        portfolio = self._store.load()
        snapshot = copy.deepcopy(portfolio)
        price = self._resolve_fill_price(order)
        if price <= 0:
            return self._skipped(order, portfolio, "NO_LIVE_PRICE: 无实时成交价", 0.0)

        qty = self._resolve_quantity(order, portfolio, price)
        if qty <= 0:
            return self._skipped(order, portfolio, "数量不足或未达最小成交额", price)

        commission_rate = settings.paper_commission_rate
        commission = 0.0
        stamp_duty = 0.0
        if order.action == Action.BUY:
            gross = qty * price
            commission = gross * commission_rate
            cost = gross + commission
            if cost > portfolio.cash:
                return self._skipped(order, portfolio, "现金不足", price)
            portfolio.cash -= cost
            self._apply_buy(portfolio, order.symbol, qty, price, sleeve=order.sleeve)
            message = f"模拟买入 {qty:.0f} 股 @ {price:.4f}"
        elif order.action in (Action.SELL, Action.REDUCE, Action.EXIT):
            pos = portfolio.positions.get(order.symbol)
            if not pos or pos.quantity < qty:
                return self._skipped(order, portfolio, "持仓不足", price)
            gross = qty * price
            commission = gross * commission_rate
            stamp_duty = gross * STAMP_DUTY_RATE
            portfolio.cash += gross - commission - stamp_duty
            self._apply_sell(portfolio, order.symbol, qty)
            message = f"模拟卖出 {qty:.0f} 股 @ {price:.4f}"
        else:
            return self._skipped(
                order, portfolio, f"不支持的动作 {order.action.value}", price
            )

        portfolio.updated_at = datetime.now()
        marked = mark_portfolio_prices(
            portfolio,
            prefer={order.symbol: price},
            force_refresh=False,
        )
        snap = compute_portfolio_risk(portfolio, marked.prices)
        portfolio.high_water_mark = max(portfolio.high_water_mark, snap.equity)
        record = {
            "timestamp": portfolio.updated_at.isoformat(),
            "symbol": order.symbol,
            "action": order.action.value,
            "quantity": qty,
            "fill_price": price,
            "commission": commission,
            "stamp_duty": stamp_duty,
            "cash_after": portfolio.cash,
            "equity": snap.equity,
            "reason": order.reason,
            "evaluation_mode": evaluation_mode,
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 4),
        }
        self._store.save(portfolio)
        try:
            self._store.append_trade(record)
        except OSError as exc:
            self._store.save(snapshot)
            audit.emit(
                layer="L6",
                event="fill_rollback",
                severity="ERROR",
                symbol=order.symbol,
                error_code="TRADE_LOG_FAIL",
                message=str(exc),
            )
            raise
        audit.emit(
            layer="L6",
            event="fill_ok",
            symbol=order.symbol,
            message=message,
            data={"qty": qty, "price": price, "equity": snap.equity},
        )
        logger.info(
            "paper fill %s %s qty=%.0f price=%.4f equity=%.2f",
            order.symbol,
            order.action.value,
            qty,
            price,
            snap.equity,
        )
        return ExecutionResult(
            status=EXECUTION_STATUS_FILLED,
            symbol=order.symbol,
            action=order.action.value,
            quantity=qty,
            message=message,
            fill_price=price,
            commission=commission,
            cash_after=portfolio.cash,
            equity=snap.equity,
        )

    def get_portfolio(self):
        """返回当前模拟账户。"""
        return self._store.load()

    def _resolve_fill_price(self, order: OrderRequest) -> float:
        """成交价只认实时市价；失败返回 0（调用方 skipped + NO_LIVE_PRICE）。"""
        try:
            live = fetch_live_fill_price(order.symbol)
        except (DataFetchError, ValidationError, OSError) as exc:
            audit.emit(
                layer="L6",
                event="fill_skipped",
                severity="ERROR",
                symbol=order.symbol,
                error_code="NO_LIVE_PRICE",
                message=str(exc),
            )
            return 0.0
        if order.fill_price > 0:
            drift = abs(live - order.fill_price) / live
            if drift >= _FILL_PRICE_DRIFT_WARN:
                logger.warning(
                    "fill price corrected symbol=%s pipeline=%.4f live=%.4f drift=%.1f%%",
                    order.symbol,
                    order.fill_price,
                    live,
                    drift * 100,
                )
        return live

    def _resolve_quantity(self, order: OrderRequest, portfolio, price: float) -> float:
        """按仓位目标或显式数量计算股数（100 股一手）。"""
        if order.quantity > 0:
            return _round_lot(order.quantity)

        marked = mark_portfolio_prices(
            portfolio,
            prefer={order.symbol: price},
            fetch_live=True,
            force_refresh=False,
        )
        equity = portfolio.total_equity(marked.prices)

        if order.action == Action.BUY:
            target_value = equity * order.position_pct
            current_value = portfolio.position_value(order.symbol, price)
            delta_value = target_value - current_value
            if delta_value < settings.paper_min_trade_value:
                return 0.0
            affordable = portfolio.cash / (price * (1 + settings.paper_commission_rate))
            qty = min(delta_value / price, affordable)
            return _round_lot(qty)

        pos = portfolio.positions.get(order.symbol)
        if not pos or pos.quantity <= 0:
            return 0.0
        if order.action == Action.EXIT:
            return pos.quantity
        if order.action == Action.REDUCE:
            frac = settings.paper_reduce_fraction
            return _round_lot(pos.quantity * frac) or pos.quantity
        return pos.quantity

    def _apply_buy(
        self,
        portfolio,
        symbol: str,
        qty: float,
        price: float,
        *,
        sleeve: str = "core",
    ) -> None:
        now = datetime.now()
        sleeve_val = (sleeve or "").strip()
        if not sleeve_val:
            raise ValueError(f"开仓 {symbol} 必须指定 sleeve")
        pos = portfolio.positions.get(symbol)
        if pos is None:
            portfolio.positions[symbol] = PaperPosition(
                symbol=symbol,
                quantity=qty,
                avg_cost=price,
                opened_at=now,
                peak_price=price,
                sleeve=sleeve_val,
            )
            return
        total_cost = pos.avg_cost * pos.quantity + price * qty
        pos.quantity += qty
        pos.avg_cost = total_cost / pos.quantity if pos.quantity else 0.0
        pos.peak_price = max(pos.peak_price, price, pos.avg_cost)
        if pos.opened_at is None:
            pos.opened_at = now
        if not pos.sleeve:
            raise ValueError(f"持仓 {symbol} 缺少 sleeve，拒绝加仓")

    def _apply_sell(self, portfolio, symbol: str, qty: float) -> None:
        pos = portfolio.positions[symbol]
        pos.quantity -= qty
        if pos.quantity <= 0:
            del portfolio.positions[symbol]

    def _skipped(
        self, order: OrderRequest, portfolio, reason: str, price: float
    ) -> ExecutionResult:
        equity = (
            portfolio.total_equity({order.symbol: price}) if price else portfolio.cash
        )
        logger.info("paper skip %s: %s", order.symbol, reason)
        return ExecutionResult(
            status=EXECUTION_STATUS_SKIPPED,
            symbol=order.symbol,
            action=order.action.value,
            quantity=0.0,
            message=reason,
            fill_price=price,
            cash_after=portfolio.cash,
            equity=equity,
        )


def _round_lot(qty: float) -> float:
    """向下取整至整手。"""
    if qty < LOT_SIZE:
        return 0.0
    return float(int(qty // LOT_SIZE) * LOT_SIZE)
