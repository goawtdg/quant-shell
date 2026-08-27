"""层间数据契约 — 字段名联调前冻结。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from quant_shell.common.constants import (
    EvaluationMode,
    LayerId,
    LayerStatus,
    RiskAction,
    RiskViolation,
)


class Action(str, Enum):
    """交易动作。"""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    WAIT = "WAIT"


class SignalStrength(str, Enum):
    """信号强度。"""

    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"


@dataclass
class MarketSnapshot:
    """L1 输出的市场快照。"""

    symbol: str
    timestamp: datetime
    price: float
    volume: float = 0.0
    pe_percentile: float = 0.5
    extra: dict[str, str | float] = field(default_factory=dict)


@dataclass
class SentimentFactors:
    """L2 输出的情绪因子。"""

    symbol: str
    timestamp: datetime
    nlp_score: float = 0.0
    social_buzz: float = 0.0
    policy_risk: float = 0.0
    fund_sentiment: float = 0.0
    composite: float = 0.0
    cross_validation: float = 0.5
    key_events: list[str] = field(default_factory=list)
    intelligence_brief: IntelligenceBrief | None = None
    analyst_report: AnalystReport | None = None


@dataclass
class AnalystReport:
    """DeepSeek 威胁情报分析师输出。"""

    symbol: str
    timestamp: datetime
    executive_summary: str = ""
    facts: list[str] = field(default_factory=list)
    affected_assets: list[str] = field(default_factory=list)
    transmission_chain: list[str] = field(default_factory=list)
    corroboration_assessment: str = ""
    confidence: float = 0.0
    sentiment_score: float = 0.0
    policy_risk_score: float = 0.0
    novelty: str = "uncertain"
    recommended_action: str = "MONITOR"
    uncertainties: list[str] = field(default_factory=list)
    human_review_required: bool = False


@dataclass
class IntelligenceItem:
    """单条开源情报。"""

    item_id: str
    source: str
    source_tier: int
    title: str
    content: str
    published_at: datetime
    url: str = ""
    entities: list[str] = field(default_factory=list)
    event_tags: list[str] = field(default_factory=list)
    symbol_hint: str = ""
    importance: str = ""


@dataclass
class IntelligenceBrief:
    """多源整合情报摘要。"""

    symbol: str
    timestamp: datetime
    items: list[IntelligenceItem]
    source_count: int
    corroboration_count: int
    headline: str = ""


@dataclass
class TradingSignal:
    """L3 输出的融合信号 — opportunity 为机会分；quality 仅由 policy/scoring 写入。"""

    symbol: str
    direction: Action
    strength: SignalStrength
    opportunity: float
    quality: float | None = None
    components: dict[str, float] = field(default_factory=dict)
    alpha_registry_scope: str = ""


@dataclass
class RiskMetrics:
    """风险指标集合。"""

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    var_95_1d: float = 0.0
    volatility_annual: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0


@dataclass
class ModelComparison:
    """策略与基准对比。"""

    current_strategy: str = "index_dca"
    regime: str = "consolidation"
    backtest_sharpe: float = 0.0
    live_sharpe_30d: float = 0.0
    portfolio_backtest_sharpe_120d: float = 0.0
    portfolio_live_sharpe_30d: float = 0.0
    benchmark_alpha: float = 0.0

    @property
    def deviation(self) -> float:
        """标的近窗 vs 长窗 Sharpe 相对偏离（入场 DEGRADED 标记）。"""
        if self.backtest_sharpe == 0:
            return 0.0
        return (self.live_sharpe_30d - self.backtest_sharpe) / self.backtest_sharpe

    @property
    def portfolio_deviation(self) -> float:
        """组合近窗 vs 长窗 Sharpe 相对偏离（P4.hold_semantic_A 持仓 REDUCE）。"""
        if self.portfolio_backtest_sharpe_120d == 0:
            return 0.0
        return (
            self.portfolio_live_sharpe_30d - self.portfolio_backtest_sharpe_120d
        ) / self.portfolio_backtest_sharpe_120d


@dataclass
class RiskState:
    """当前风险状态。"""

    kelly_suggested_position: float = 0.1
    current_position: float = 0.0
    total_position_pct: float = 0.0
    drawdown_limit_remaining: float = 0.15
    portfolio_drawdown: float = 0.0
    cost_basis: float = 0.0
    unrealized_pnl_pct: float = 0.0
    holding_days: int = 0
    take_profit_pressure: float = 0.0
    black_swan_alerts: list[str] = field(default_factory=list)
    market_volatility_annual: float | None = None


@dataclass
class DecisionContextPack:
    """汇总量化上下文，供 AI 推理与人工审核。"""

    symbol: str
    timestamp: datetime
    market: MarketSnapshot
    risk_metrics: RiskMetrics
    sentiment: SentimentFactors
    model_comparison: ModelComparison
    risk_state: RiskState
    signal: TradingSignal | None = None
    evaluation_mode: str = EvaluationMode.ENTRY.value
    monitor_alert_messages: list[str] = field(default_factory=list)
    factor_degraded_count: int = 0
    factor_disabled_count: int = 0
    factor_active_count: int = 0
    factor_usable_count: int = 0
    factor_coverage: float = 0.0
    trade_sleeve: str = "core"
    sleeve_reason: str = ""


@dataclass
class FactorICRecord:
    """单因子 IC 监控记录。"""

    name: str
    mean_ic: float
    ir: float
    sample_count: int
    status: str
    action: str


@dataclass
class FactorHealthReport:
    """因子健康度报告。"""

    symbol: str
    timestamp: datetime
    factors: list[FactorICRecord]
    degraded_count: int = 0
    disabled_count: int = 0
    active_count: int = 0
    usable_count: int = 0
    coverage: float = 0.0
    scope: str = ""


@dataclass
class RiskVerdict:
    """L5 风控裁决。"""

    approved: bool
    violations: list[RiskViolation] = field(default_factory=list)
    max_allowed_position: float = 0.0
    action: RiskAction = RiskAction.BLOCK


@dataclass
class OrderRequest:
    """L6 订单请求。"""

    symbol: str
    action: Action
    quantity: float
    position_pct: float
    reason: str = ""
    fill_price: float = 0.0
    sleeve: str = "core"


@dataclass
class ExecutionResult:
    """L6 执行结果。"""

    status: str
    symbol: str
    action: str
    quantity: float
    message: str
    fill_price: float = 0.0
    commission: float = 0.0
    cash_after: float = 0.0
    equity: float = 0.0


@dataclass
class PaperPosition:
    """模拟持仓。"""

    symbol: str
    quantity: float
    avg_cost: float = 0.0
    opened_at: datetime | None = None
    peak_price: float = 0.0
    sleeve: str = "core"


@dataclass
class PaperPortfolio:
    """模拟账户。"""

    cash: float
    initial_cash: float
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=datetime.now)
    high_water_mark: float = 0.0

    def mark_equity(self, prices: dict[str, float]) -> float:
        """按市价计算账户总权益。"""
        return self.total_equity(prices)

    def position_value(self, symbol: str, price: float) -> float:
        """单标的持仓市值。"""
        pos = self.positions.get(symbol)
        if not pos or price <= 0:
            return 0.0
        return pos.quantity * price

    def total_equity(self, prices: dict[str, float]) -> float:
        """现金 + 持仓市值。"""
        holdings = sum(
            pos.quantity * prices.get(sym, 0.0)
            for sym, pos in self.positions.items()
        )
        return self.cash + holdings

    def position_pct(self, symbol: str, prices: dict[str, float]) -> float:
        """单标的仓位占权益比例（需传入全持仓市价）。"""
        equity = self.total_equity(prices)
        if equity <= 0:
            return 0.0
        return self.position_value(symbol, prices.get(symbol, 0.0)) / equity

    def total_position_pct(self, prices: dict[str, float]) -> float:
        """持仓总市值占权益比例。"""
        equity = self.total_equity(prices)
        if equity <= 0:
            return 0.0
        holdings = sum(
            pos.quantity * prices.get(sym, 0.0)
            for sym, pos in self.positions.items()
        )
        return holdings / equity


@dataclass
class AIDecision:
    """L7 AI 推理输出。"""

    action: Action
    confidence: float
    reasoning_chain: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    suggested_position_change: float = 0.0
    human_review_required: bool = True


@dataclass
class LayerResult:
    """单层审计记录。"""

    layer: LayerId
    status: LayerStatus
    message: str = ""


@dataclass
class PipelineContext:
    """流水线上下文 — orchestrator 在各层之间传递。"""

    symbol: str
    run_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    market: MarketSnapshot | None = None
    sentiment: SentimentFactors | None = None
    signal: TradingSignal | None = None
    context_pack: DecisionContextPack | None = None
    ai_decision: AIDecision | None = None
    risk_verdict: RiskVerdict | None = None
    order: OrderRequest | None = None
    execution_result: ExecutionResult | None = None
    paper_portfolio: PaperPortfolio | None = None
    factor_health: FactorHealthReport | None = None
    intel_cache: dict[str, SentimentFactors] = field(default_factory=dict)
    monitor_alerts: list[MonitorAlert] = field(default_factory=list)
    audit_trail: list[LayerResult] = field(default_factory=list)
    evaluation_mode: str = EvaluationMode.ENTRY.value
    entry_eligible: bool = True
    entry_block_reason: str = ""
    policy_verdict: object | None = None


@dataclass
class FullLinkageResult:
    """全链路联动运行结果。"""

    run_id: str
    timestamp: datetime
    etf_runs: list[PipelineContext] = field(default_factory=list)
    hold_runs: list[PipelineContext] = field(default_factory=list)
    stock_runs: list[PipelineContext] = field(default_factory=list)
    stock_pick: StockPickResult | None = None
    monitor_alerts: list[MonitorAlert] = field(default_factory=list)
    stock_intel_symbols: list[str] = field(default_factory=list)
    summary_path: str = ""
    report_path: str = ""
    intel_ran: bool = True
    equity_ok: bool = True
    equity_snapshot: dict[str, float | str] | None = None
    phase_errors: list[dict[str, str]] = field(default_factory=list)


@dataclass
class StockFundamentals:
    """单只股票基本面快照。"""

    symbol: str
    name: str = ""
    price: float = 0.0
    market_cap: float = 0.0
    pe: float = 0.0
    roe: float = 0.0
    volume: float = 0.0
    volume_ma20: float = 0.0
    return_3m: float = 0.0
    return_5d: float = 0.0
    return_10d: float = 0.0
    at_limit_up: bool = False
    turnover_rate: float = 0.0
    industry: str = "未知"

    def to_dict(self) -> dict[str, object]:
        """转为 dict，供 DataFrame 构建。"""
        return {
            "symbol": self.symbol,
            "name": self.name,
            "price": self.price,
            "market_cap": self.market_cap,
            "pe": self.pe,
            "roe": self.roe,
            "volume": self.volume,
            "volume_ma20": self.volume_ma20,
            "return_3m": self.return_3m,
            "return_5d": self.return_5d,
            "return_10d": self.return_10d,
            "at_limit_up": self.at_limit_up,
            "turnover_rate": self.turnover_rate,
            "industry": self.industry,
        }


@dataclass
class MonitorAlert:
    """情报监控告警（L2 monitor → 主链路）。"""

    symbol: str
    level: str
    message: str


@dataclass
class ScoredStock:
    """截面打分后的单只股票。"""

    symbol: str
    name: str
    score: float
    rank: int
    price: float = 0.0
    factor_scores: dict[str, float] = field(default_factory=dict)
    entry_eligible: bool = True
    entry_block_reason: str = ""


@dataclass
class StockPickResult:
    """L4 选股输出。"""

    universe: str
    strategy: str
    picks: list[ScoredStock]
    candidate_count: int
    filtered_count: int
    gate_diagnostics: dict[str, int] | None = None
    timestamp: datetime = field(default_factory=datetime.now)
