"""模拟盘七层流水线 — 插件化策略 + 用户因子 + 纸面成交。"""
from __future__ import annotations

from quant_shell.common import audit
from quant_shell.execution.paper_engine import PaperTradingEngine
from quant_shell.execution.portfolio import PaperPortfolioStore
from quant_shell.factory import create_layer4_service, create_signal_generator, create_strategy_engine
from quant_shell.factors.engine import AlphaFactorEngine
from quant_shell.factors.registry import FactorRegistry
from quant_shell.factors.state_store import load_registry
from quant_shell.human.llm_gate import build_default_human_gate
from quant_shell.orchestrator.layer4 import Layer4Service
from quant_shell.orchestrator.pipeline import TradingPipeline
from quant_shell.risk.enricher import RiskContextEnricher
from quant_shell.risk.factor_health import FactorHealthMonitor


class PaperTradingPipeline(TradingPipeline):
    """默认纸面 L6 + Sim/LLM L7；策略与因子均通过 env 插件加载。"""

    layer4: Layer4Service

    def __init__(
        self,
        portfolio_store: PaperPortfolioStore | None = None,
        layer4: Layer4Service | None = None,
        **kwargs: object,
    ) -> None:
        store = portfolio_store or PaperPortfolioStore()
        kwargs.setdefault("strategy", create_strategy_engine(portfolio_store=store))
        kwargs.setdefault("execution", PaperTradingEngine(store=store))
        kwargs.setdefault("human_gate", build_default_human_gate(portfolio_store=store))
        super().__init__(**kwargs)
        self._portfolio_store = store
        self.layer4 = layer4 or create_layer4_service(portfolio_store=store)

    @classmethod
    def create_integrated(
        cls,
        etf_registry: FactorRegistry | None = None,
        stock_registry: FactorRegistry | None = None,
        portfolio_store: PaperPortfolioStore | None = None,
        **kwargs: object,
    ) -> PaperTradingPipeline:
        from quant_shell.studio.hydrate import hydrate_studio

        hydrate_studio()
        store = portfolio_store or PaperPortfolioStore()
        etf_reg = etf_registry or load_registry(scope="etf")
        stock_reg = stock_registry or load_registry(scope="stock")
        signal_gen = create_signal_generator(
            etf_engine=AlphaFactorEngine(registry=etf_reg, scope="etf"),
            stock_engine=AlphaFactorEngine(registry=stock_reg, scope="stock"),
        )
        enricher = RiskContextEnricher(
            etf_health_monitor=FactorHealthMonitor(etf_reg, scope="etf"),
            stock_health_monitor=FactorHealthMonitor(stock_reg, scope="stock"),
        )
        layer4 = create_layer4_service(registry=stock_reg, portfolio_store=store)
        return cls(
            portfolio_store=store,
            signal_gen=signal_gen,
            risk_enricher=enricher,
            layer4=layer4,
            **kwargs,
        )

    def run_symbol(
        self,
        symbol: str,
        *,
        evaluation_mode: str = "entry",
        auto_approve: bool = True,
    ):
        audit.reset()
        return self.run(
            symbol=symbol,
            evaluation_mode=evaluation_mode,
            auto_approve=auto_approve,
        )
