"""各层抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from quant_shell.common.types import (
    AIDecision,
    DecisionContextPack,
    ExecutionResult,
    MarketSnapshot,
    OrderRequest,
    PipelineContext,
    RiskVerdict,
    SentimentFactors,
    StockPickResult,
    TradingSignal,
)


class DataSource(ABC):
    """第 1 层：数据采集。"""

    @abstractmethod
    def fetch_market(self, symbol: str) -> MarketSnapshot:
        """采集市场快照。"""


class IntelligenceFusion(ABC):
    """第 2 层：情报融合。"""

    @abstractmethod
    def analyze(self, symbol: str, market: MarketSnapshot) -> SentimentFactors:
        """生成情绪因子。"""


class SignalGenerator(ABC):
    """第 3 层：信号生成。"""

    @abstractmethod
    def generate(
        self,
        symbol: str,
        market: MarketSnapshot,
        sentiment: SentimentFactors,
    ) -> TradingSignal:
        """融合数学、情绪、情报信号。"""


class StrategyEngine(ABC):
    """第 4 层：策略政策引擎。"""

    @abstractmethod
    def build_context_pack(self, ctx: PipelineContext) -> DecisionContextPack:
        """组装 DecisionContextPack。"""

    @abstractmethod
    def evaluate_policy(self, ctx: PipelineContext):
        """定稿 PolicyVerdict（袖套/入场/持有）。"""


class StockPicker(ABC):
    """第 4 层：截面选股。"""

    @abstractmethod
    def pick_stocks(
        self,
        universe: str = "csi300",
        top_n: int = 20,
        max_symbols: int | None = None,
    ) -> StockPickResult:
        """截面多因子选股。"""


class RiskEngine(ABC):
    """第 5 层：动态风控。"""

    @abstractmethod
    def evaluate(self, ctx: PipelineContext, proposed_action: str) -> RiskVerdict:
        """硬风控裁决。"""


class ExecutionEngine(ABC):
    """第 6 层：智能执行。"""

    @abstractmethod
    def execute(self, order: OrderRequest) -> ExecutionResult:
        """提交订单（模拟或实盘）。"""


class HumanReviewGate(ABC):
    """第 7 层：人机协同 + AI 推理。"""

    @abstractmethod
    def reason(self, pack: DecisionContextPack) -> AIDecision:
        """结构化推理。"""

    @abstractmethod
    def confirm(self, decision: AIDecision, auto_approve: bool = False) -> bool:
        """人工确认 gate。"""
