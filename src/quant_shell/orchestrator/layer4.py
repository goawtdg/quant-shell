"""L4 门面 — 策略引擎 + 截面选股；默认 picker 可经 PICKER_MODULE 替换。"""
from __future__ import annotations

from quant_shell.common.interfaces import StockPicker, StrategyEngine
from quant_shell.common.types import DecisionContextPack, PipelineContext, StockPickResult
from quant_shell.factory import create_stock_picker, create_strategy_engine
from quant_shell.factors.registry import FactorRegistry
from quant_shell.factors.state_store import load_registry


class Layer4Service:
    """L4 门面：委托策略插件与截面选股。"""

    def __init__(
        self,
        pipeline_engine: StrategyEngine,
        stock_picker: StockPicker,
    ) -> None:
        self._pipeline_engine = pipeline_engine
        self._stock_picker = stock_picker

    @property
    def pipeline_engine(self) -> StrategyEngine:
        return self._pipeline_engine

    def build_context_pack(self, ctx: PipelineContext) -> DecisionContextPack:
        return self._pipeline_engine.build_context_pack(ctx)

    def evaluate_policy(self, ctx: PipelineContext):
        return self._pipeline_engine.evaluate_policy(ctx)

    def pick_stocks(
        self,
        universe: str = "csi300",
        top_n: int = 20,
        max_symbols: int | None = None,
    ) -> StockPickResult:
        return self._stock_picker.pick_stocks(
            universe=universe,
            top_n=top_n,
            max_symbols=max_symbols,
        )

    @classmethod
    def create_default(
        cls,
        registry: FactorRegistry | None = None,
        portfolio_store: object | None = None,
    ) -> Layer4Service:
        shared = registry or load_registry(scope="stock")
        kwargs: dict = {}
        if portfolio_store is not None:
            kwargs["portfolio_store"] = portfolio_store
        return cls(
            pipeline_engine=create_strategy_engine(**kwargs),
            stock_picker=create_stock_picker(registry=shared),
        )
