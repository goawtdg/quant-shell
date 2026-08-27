"""策略政策引擎 — L4 唯一 StrategyEngine 实现。"""
from __future__ import annotations

from datetime import datetime

from quant_shell.common.constants import EvaluationMode, MarketRegime
from quant_shell.common.exceptions import BusinessError
from quant_shell.common.interfaces import StrategyEngine
from quant_shell.common.types import (
    Action,
    DecisionContextPack,
    ModelComparison,
    PipelineContext,
    RiskMetrics,
    RiskState,
)
from quant_shell.data.pe_quality import is_pe_percentile_reliable
from reference_policy.policy.config import SleevePolicyConfig, load_policy_config
from reference_policy.policy.playbooks import (
    compute_take_profit_pressure,
    decide_entry,
    decide_hold,
    resolve_position_sleeve,
    size_limits,
    stored_peak_price,
    touch_position_peak,
)
from reference_policy.policy.router import compute_catalyst_ok
from reference_policy.policy.types import (
    THEME_BUDGET_SLEEVES,
    PolicyVerdict,
    TradeSleeve,
)
from quant_shell.risk.portfolio_risk import compute_portfolio_risk, holding_days
from quant_shell.execution.mark_prices import mark_portfolio_prices
from quant_shell.execution.portfolio import PaperPortfolioStore


class StrategyPolicyEngine(StrategyEngine):
    """袖套路由 + 入场/持有剧本；产出 PolicyVerdict。"""

    def __init__(
        self,
        portfolio_store: PaperPortfolioStore | None = None,
        config: SleevePolicyConfig | None = None,
    ) -> None:
        self._portfolio_store = portfolio_store or PaperPortfolioStore()
        self._config = config or load_policy_config()

    def build_context_pack(self, ctx: PipelineContext) -> DecisionContextPack:
        """组装决策包；仓位读模拟盘。袖套裁决见 evaluate_policy。"""
        self._ensure_upstream(ctx)
        price = ctx.market.price if ctx.market else 0.0
        pe = ctx.market.pe_percentile if ctx.market else 0.5
        pe_ok = is_pe_percentile_reliable(ctx.market)
        portfolio = self._portfolio_store.load()
        prices = self._portfolio_prices(portfolio, ctx.symbol, price)
        risk_snap = compute_portfolio_risk(portfolio, prices)
        pos = portfolio.positions.get(ctx.symbol)
        if pos is not None and pos.quantity > 0:
            sleeve_value = resolve_position_sleeve(pos).value
        else:
            from quant_shell.data.symbol import is_etf

            sleeve_value = (
                TradeSleeve.ETF_BETA.value
                if is_etf(ctx.symbol)
                else TradeSleeve.CORE.value
            )
        current_position = portfolio.position_pct(ctx.symbol, prices)
        cost_basis = pos.avg_cost if pos else 0.0
        pnl_pct = (price / cost_basis - 1.0) if cost_basis > 0 else 0.0
        as_of = ctx.timestamp or datetime.now()
        hold_days = holding_days(pos.opened_at if pos else None, as_of)
        trail_dd = 0.0
        if pos and price > 0:
            peak = stored_peak_price(pos)
            if peak > 0:
                trail_dd = max(0.0, (peak - price) / peak)
        tp_pressure = compute_take_profit_pressure(
            pnl_pct=pnl_pct,
            pe_percentile=pe,
            trail_drawdown=trail_dd,
            pe_reliable=pe_ok,
            config=self._config,
        )
        ctx.paper_portfolio = portfolio
        kelly = self._suggest_kelly(ctx)
        regime = self._infer_regime(ctx)
        return DecisionContextPack(
            symbol=ctx.symbol,
            timestamp=as_of,
            market=ctx.market,  # type: ignore[arg-type]
            risk_metrics=RiskMetrics(),
            sentiment=ctx.sentiment,  # type: ignore[arg-type]
            model_comparison=ModelComparison(
                current_strategy=sleeve_value,
                regime=regime,
            ),
            risk_state=RiskState(
                kelly_suggested_position=kelly,
                current_position=current_position,
                total_position_pct=risk_snap.total_position_pct,
                portfolio_drawdown=risk_snap.portfolio_drawdown,
                cost_basis=cost_basis,
                unrealized_pnl_pct=pnl_pct,
                holding_days=hold_days,
                take_profit_pressure=tp_pressure,
            ),
            signal=ctx.signal,
            evaluation_mode=ctx.evaluation_mode,
            trade_sleeve=sleeve_value,
        )

    def evaluate_policy(self, ctx: PipelineContext) -> PolicyVerdict:
        """在 L5 enrich 之后定稿袖套与动作（唯一纪律出口）。"""
        if ctx.context_pack is None or ctx.market is None or ctx.sentiment is None:
            raise BusinessError(
                message="evaluate_policy 缺少 context_pack/market/sentiment",
                suggestion="先执行 build_context_pack 与风险 enrich",
            )
        pack = ctx.context_pack
        pe_ok = is_pe_percentile_reliable(ctx.market)
        portfolio = ctx.paper_portfolio or self._portfolio_store.load()
        prices = self._portfolio_prices(
            portfolio, ctx.symbol, ctx.market.price
        )
        theme_exposure = _theme_exposure_pct(portfolio, prices)
        sentiment = ctx.sentiment
        analyst = sentiment.analyst_report
        cross_validation = float(sentiment.cross_validation)
        catalyst_ok = compute_catalyst_ok(
            cross_validation=cross_validation,
            analyst=analyst,
        )

        if ctx.evaluation_mode == EvaluationMode.HOLD.value:
            pos = portfolio.positions.get(ctx.symbol)
            if not pos or pos.quantity <= 0:
                verdict = PolicyVerdict(
                    sleeve=TradeSleeve.CORE,
                    sleeve_reason="无持仓",
                    action=Action.HOLD,
                    entry_eligible=False,
                    block_reasons=["无持仓，持有审查跳过"],
                    rule_resolved=True,
                )
            else:
                sleeve = resolve_position_sleeve(pos)
                sell_pressure = 0.0
                if ctx.signal and ctx.signal.direction == Action.SELL:
                    sell_pressure = abs(float(ctx.signal.opportunity))
                alerts = list(pack.monitor_alert_messages)
                verdict = decide_hold(
                    sleeve=sleeve,
                    position=pos,
                    current_price=ctx.market.price,
                    holding_days=pack.risk_state.holding_days,
                    analyst=analyst,
                    monitor_alerts=alerts,
                    pe_percentile=ctx.market.pe_percentile,
                    pe_reliable=pe_ok,
                    signal_sell_pressure=sell_pressure,
                    volatility_annual=pack.risk_metrics.volatility_annual,
                    market_volatility_annual=pack.risk_state.market_volatility_annual,
                    config=self._config,
                    sentiment_composite=sentiment.composite,
                    cross_validation=cross_validation,
                )
                if touch_position_peak(pos, ctx.market.price):
                    self._portfolio_store.save(portfolio)
                pack.risk_state.take_profit_pressure = max(
                    pack.risk_state.take_profit_pressure,
                    verdict.take_profit_pressure,
                )
        else:
            extra = dict(ctx.market.extra or {})
            extra.setdefault("symbol", ctx.symbol)
            coverage = pack.factor_coverage
            active = pack.factor_active_count
            usable = pack.factor_usable_count
            if ctx.factor_health is not None:
                coverage = ctx.factor_health.coverage
                active = ctx.factor_health.active_count
                usable = ctx.factor_health.usable_count
            verdict = decide_entry(
                symbol=ctx.symbol,
                pe_percentile=ctx.market.pe_percentile,
                pe_reliable=pe_ok,
                sentiment_composite=sentiment.composite,
                signal=ctx.signal,
                factor_coverage=coverage,
                factor_active=active,
                factor_usable=usable,
                theme_sleeve_exposure=theme_exposure,
                microstructure_extra=extra,
                config=self._config,
                cross_validation=cross_validation,
                analyst=analyst,
                catalyst_ok=catalyst_ok,
            )
            if verdict.action == Action.BUY:
                kelly = pack.risk_state.kelly_suggested_position
                limits = size_limits(verdict.sleeve, self._config)
                base = verdict.suggested_position or kelly
                verdict.suggested_position = min(base, kelly, limits.max_position)
                verdict.max_position = limits.max_position

        pack.trade_sleeve = verdict.sleeve.value
        pack.sleeve_reason = verdict.sleeve_reason
        pack.model_comparison.current_strategy = verdict.sleeve.value
        ctx.policy_verdict = verdict
        if ctx.evaluation_mode == EvaluationMode.ENTRY.value:
            ctx.entry_eligible = verdict.entry_eligible
            if not verdict.entry_eligible and verdict.block_reasons:
                ctx.entry_block_reason = verdict.block_reason_text()
        return verdict

    def _portfolio_prices(self, portfolio, symbol: str, price: float) -> dict[str, float]:
        prefer = {symbol: price} if price > 0 else {}
        return mark_portfolio_prices(
            portfolio, prefer=prefer, fetch_live=True, force_refresh=None
        ).prices

    def _infer_regime(self, ctx: PipelineContext) -> str:
        signal = ctx.signal
        if not signal:
            return MarketRegime.CONSOLIDATION
        if abs(signal.opportunity) >= self._config.signal_threshold_strong:
            return MarketRegime.WEAK_BULL
        return MarketRegime.CONSOLIDATION

    def _suggest_kelly(self, ctx: PipelineContext) -> float:
        signal = ctx.signal
        if not signal:
            return 0.08
        abs_opp = abs(signal.opportunity)
        base = 0.08 + abs_opp * 0.12
        if abs_opp < self._config.signal_threshold_moderate:
            base *= 0.5
        return min(base, 0.25)

    def _ensure_upstream(self, ctx: PipelineContext) -> None:
        if not ctx.market or not ctx.sentiment or not ctx.signal:
            raise BusinessError(
                message="build_context_pack 缺少上游数据",
                suggestion="确保 L1–L3 已成功执行",
            )


def _theme_exposure_pct(portfolio, prices: dict[str, float]) -> float:
    from quant_shell.common.exceptions import BusinessError

    equity = portfolio.total_equity(prices)
    if equity <= 0:
        return 0.0
    themed = 0.0
    for sym, pos in portfolio.positions.items():
        try:
            sleeve = resolve_position_sleeve(pos)
        except ValueError as exc:
            raise BusinessError(
                message=f"主题暴露计算失败: {exc}",
                suggestion="补全持仓 sleeve 为合法 TradeSleeve",
            ) from exc
        if sleeve not in THEME_BUDGET_SLEEVES:
            continue
        themed += pos.quantity * prices.get(sym, 0.0)
    return themed / equity
