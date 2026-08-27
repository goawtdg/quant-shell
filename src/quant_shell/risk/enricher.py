"""L5 上下文增强 — 真实风险指标 + 因子 IC 健康度（live 只读 registry）。"""
from __future__ import annotations

from dataclasses import replace

from quant_shell.common import audit
from quant_shell.common.exceptions import DataFetchError, QuantSystemError, ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import PipelineContext
from quant_shell.config.settings import settings
from quant_shell.data.symbol import asset_type, fetch_daily_ohlcv
from quant_shell.risk.factor_health import FactorHealthMonitor
from quant_shell.risk.metrics import MetricsCalculator

logger = get_logger(__name__)


class RiskContextEnricher:
    """在 L5 风控前用真实历史数据填充 Context Pack。"""

    def __init__(
        self,
        etf_health_monitor: FactorHealthMonitor | None = None,
        stock_health_monitor: FactorHealthMonitor | None = None,
    ) -> None:
        self._etf_monitor = etf_health_monitor or FactorHealthMonitor(scope="etf")
        self._stock_monitor = stock_health_monitor or FactorHealthMonitor(scope="stock")

    def enrich(self, ctx: PipelineContext) -> PipelineContext:
        """填充 risk_metrics / model_comparison / factor_health。"""
        if ctx.context_pack is None:
            audit.emit(
                layer="L5",
                event="layer_skipped",
                severity="WARN",
                run_id=ctx.run_id,
                symbol=ctx.symbol,
                error_code="NO_CONTEXT_PACK",
                message="RiskContextEnricher skip: no context_pack",
            )
            return ctx

        ohlcv = fetch_daily_ohlcv(ctx.symbol)
        metrics = MetricsCalculator.build_risk_metrics(ohlcv)
        live_sharpe, backtest_sharpe = MetricsCalculator.live_and_backtest_sharpe(ohlcv)
        market_vol = self._market_volatility_annual()

        pack = ctx.context_pack
        model = replace(
            pack.model_comparison,
            backtest_sharpe=backtest_sharpe,
            live_sharpe_30d=live_sharpe,
        )
        risk_state = replace(
            pack.risk_state,
            drawdown_limit_remaining=max(
                0.0,
                settings.max_drawdown - metrics.current_drawdown,
            ),
            market_volatility_annual=market_vol,
        )
        ctx.context_pack = replace(
            pack,
            risk_metrics=metrics,
            model_comparison=model,
            risk_state=risk_state,
        )

        if asset_type(ctx.symbol) == "etf":
            ctx.factor_health = self._etf_monitor.report_registry_state(symbol=ctx.symbol)
            factor_mode = "etf_registry_readonly"
        else:
            ctx.factor_health = self._stock_monitor.report_registry_state(symbol=ctx.symbol)
            factor_mode = "stock_registry_readonly"

        audit.emit(
            layer="L5",
            event="factor_health_routed",
            run_id=ctx.run_id,
            symbol=ctx.symbol,
            data={
                "asset_type": asset_type(ctx.symbol),
                "factor_mode": factor_mode,
                "factor_usable": ctx.factor_health.usable_count if ctx.factor_health else 0,
                "factor_coverage": ctx.factor_health.coverage if ctx.factor_health else 0.0,
            },
        )
        logger.info(
            "RiskContextEnricher symbol=%s asset=%s sharpe=%.2f drawdown=%.2f mkt_vol=%s",
            ctx.symbol,
            asset_type(ctx.symbol),
            metrics.sharpe_ratio,
            metrics.current_drawdown,
            f"{market_vol:.2f}" if market_vol is not None else "na",
        )
        return ctx

    def _market_volatility_annual(self) -> float | None:
        """主监控 ETF 年化波动，供 hold 动态清仓应激放大。"""
        bench = settings.default_symbol or "510300"
        try:
            ohlcv = fetch_daily_ohlcv(bench)
            return MetricsCalculator.build_risk_metrics(ohlcv).volatility_annual
        except (DataFetchError, ValidationError, QuantSystemError, OSError) as exc:
            audit.emit(
                layer="L5",
                event="market_vol_skip",
                severity="WARN",
                symbol=bench,
                error_code="DATA_FETCH",
                message=str(exc),
            )
            return None
