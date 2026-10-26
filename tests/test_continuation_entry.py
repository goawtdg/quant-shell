"""延续假设单独开仓：反转、空新闻、高估路由不再把分数对冲成无法开仓。"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from quant_shell.common.constants import EvaluationMode
from quant_shell.common.types import (
    Action,
    DecisionContextPack,
    FactorHealthReport,
    MarketSnapshot,
    ModelComparison,
    RiskMetrics,
    RiskState,
    SentimentFactors,
    SignalStrength,
    TradingSignal,
    IntelligenceBrief,
    IntelligenceItem,
)
from quant_shell.config.settings import settings
from quant_shell.factors.engine import AlphaFactorResult, FactorValue
from quant_shell.factors.registry import FactorCategory, FactorRegistry, FactorSpec
from quant_shell.intelligence.brief import compute_sentiment_scores
from quant_shell.plugin.policy_config import SleevePolicyConfig
from quant_shell.risk.gate import HardRiskGate
from quant_shell.signals.fusion import SignalFusionGenerator
from quant_shell.signals.math_signal import MathSignalEngine, MathSignalResult
from reference_policy.picker.factor_scorer import FactorScorer
from reference_policy.policy.playbooks import decide_entry


def _policy(**overrides: object) -> SleevePolicyConfig:
    base = dict(
        core_pe_block_percentile=0.85,
        core_min_hold_days=5,
        theme_enabled=True,
        theme_max_position=0.05,
        theme_sleeve_budget=0.15,
        theme_max_hold_days=10,
        theme_exit_dd=0.08,
        theme_min_sentiment=0.25,
        theme_min_signal_conf=0.45,
        signal_threshold_moderate=0.07,
        signal_threshold_strong=0.10,
        signal_moderate_buy_scale=0.5,
        single_stock_limit=0.10,
        factor_min_coverage=0.70,
        pick_filter_board_permission=False,
        take_profit_partial_pct=0.15,
        take_profit_scale_pct=0.25,
        take_profit_full_pct=0.40,
        take_profit_trail_pct=0.08,
        take_profit_pe_rich=0.70,
        take_profit_pe_exit=0.85,
    )
    base.update(overrides)
    return SleevePolicyConfig(**base)  # type: ignore[arg-type]


def _signal(opportunity: float) -> TradingSignal:
    direction = Action.BUY if opportunity > 0 else Action.SELL
    return TradingSignal(
        symbol="600000",
        direction=direction,
        strength=SignalStrength.MODERATE,
        opportunity=opportunity,
    )


class _Math:
    def __init__(self, result: MathSignalResult) -> None:
        self._result = result

    def compute(self, symbol: str) -> MathSignalResult:
        del symbol
        return self._result


class _Alpha:
    scope = "stock"

    def __init__(self, result: AlphaFactorResult) -> None:
        self._result = result

    def compute(self, symbol: str, market: object = None) -> AlphaFactorResult:
        del symbol, market
        return self._result


def test_trend_score_ignores_overbought_indicators() -> None:
    closes = pd.Series([100.0 + i * 0.4 for i in range(160)], dtype=float)
    components = MathSignalEngine()._compute_components(closes)
    blend = (
        components["dual_ma"] * 0.30
        + components["macd"] * 0.25
        + components["rsi"] * 0.25
        + components["bollinger"] * 0.20
    )
    assert components["reversion"] < 0
    assert components["trend"] > 0
    assert components["trend"] > blend


def test_inactive_news_does_not_dilute_trend(monkeypatch) -> None:
    monkeypatch.setattr(
        "quant_shell.signals.fusion.settings",
        replace(
            settings,
            fusion_renormalize_inactive=True,
            signal_weight_math=0.40,
            signal_weight_sentiment=0.35,
            signal_weight_intelligence=0.25,
            tech_weight_in_math=0.45,
            alpha_weight_in_math=0.55,
            signal_threshold_moderate=0.07,
            signal_threshold_strong=0.10,
        ),
    )
    tech = MathSignalResult(
        composite=0.40,
        components={"trend": 0.40, "reversion": -0.80, "dual_ma": 0.5, "macd": 0.28},
    )
    alpha = AlphaFactorResult(
        composite=-0.6,
        factors=[
            FactorValue("rev", "reversal", 1.0, -0.9, 1.0),
            FactorValue("vol", "volatility", 1.0, -0.4, 1.0),
        ],
    )
    now = datetime(2026, 10, 26)
    signal = SignalFusionGenerator(
        math_engine=_Math(tech),  # type: ignore[arg-type]
        etf_engine=_Alpha(alpha),  # type: ignore[arg-type]
        stock_engine=_Alpha(alpha),  # type: ignore[arg-type]
    ).generate(
        "600000",
        MarketSnapshot(symbol="600000", timestamp=now, price=10.0),
        SentimentFactors(
            symbol="600000",
            timestamp=now,
            composite=0.0,
            cross_validation=1.0,
        ),
    )
    assert signal.opportunity == 0.40
    assert signal.direction == Action.BUY
    assert signal.components["intelligence"] == 0.0
    assert signal.components["corroboration_bias_ignored"] == 1.0


def test_news_count_is_not_a_bullish_score() -> None:
    now = datetime(2026, 10, 26)
    items = [
        IntelligenceItem(
            item_id=f"n{i}",
            source="cls",
            source_tier=1,
            title="公司召开董事会",
            content="审议日常议案",
            published_at=now,
        )
        for i in range(6)
    ]
    brief = IntelligenceBrief(
        symbol="600000",
        timestamp=now,
        items=items,
        source_count=1,
        corroboration_count=2,
    )
    scores = compute_sentiment_scores(items, brief)
    assert scores["social_buzz"] > 0
    assert scores["cross_validation"] > 0.5
    assert scores["composite"] == 0.0


def test_rich_valuation_stays_on_continuation_book(monkeypatch) -> None:
    monkeypatch.setattr(
        "reference_policy.policy.scoring.settings",
        replace(
            settings,
            factor_min_active=3,
            factor_green_min_usable=4,
            factor_min_coverage=0.70,
            factor_coverage_scale_floor=0.35,
        ),
    )
    verdict = decide_entry(
        symbol="600000",
        pe_percentile=0.95,
        pe_reliable=True,
        sentiment_composite=0.0,
        signal=_signal(0.12),
        factor_coverage=0.9,
        factor_active=4,
        factor_usable=4,
        theme_sleeve_exposure=0.0,
        microstructure_extra={},
        config=_policy(),
    )
    assert verdict.sleeve.value == "core"
    assert verdict.action == Action.BUY
    assert verdict.suggested_position == 0.05
    assert any("估值分位" in reason for reason in verdict.block_reasons)


def test_moderate_trend_can_open(monkeypatch) -> None:
    monkeypatch.setattr(
        "reference_policy.policy.scoring.settings",
        replace(
            settings,
            factor_min_active=3,
            factor_green_min_usable=4,
            factor_min_coverage=0.70,
            factor_coverage_scale_floor=0.35,
        ),
    )
    blocked = decide_entry(
        symbol="600000",
        pe_percentile=0.40,
        pe_reliable=True,
        sentiment_composite=0.0,
        signal=_signal(0.04),
        factor_coverage=0.9,
        factor_active=4,
        factor_usable=4,
        theme_sleeve_exposure=0.0,
        microstructure_extra={},
        config=_policy(),
    )
    opened = decide_entry(
        symbol="600000",
        pe_percentile=0.40,
        pe_reliable=True,
        sentiment_composite=0.0,
        signal=_signal(0.12),
        factor_coverage=0.9,
        factor_active=4,
        factor_usable=4,
        theme_sleeve_exposure=0.0,
        microstructure_extra={},
        config=_policy(),
    )
    assert blocked.action == Action.WAIT
    assert opened.action == Action.BUY
    assert opened.suggested_position == 0.10


def test_picker_ranks_momentum_not_cheapness() -> None:
    def _noop(frame: pd.DataFrame) -> pd.Series:
        return frame["close"]

    registry = FactorRegistry()
    registry.register(
        FactorSpec("momentum_20", FactorCategory.MOMENTUM, "", 1.0, _noop)
    )
    registry.register(
        FactorSpec("low_vol", FactorCategory.VOLATILITY, "", 1.0, _noop)
    )
    adapted = pd.DataFrame(
        {
            "momentum_20": {"cheap": -0.8, "strong": 0.8},
            "low_vol": {"cheap": 0.9, "strong": -0.9},
            "value_ep": {"cheap": 1.0, "strong": -1.0},
            "quality_roe": {"cheap": 0.7, "strong": -0.2},
            "momentum_3m": {"cheap": -0.5, "strong": 0.6},
            "industry_rel_momentum": {"cheap": -0.4, "strong": 0.5},
            "liquidity": {"cheap": 0.2, "strong": 0.2},
        }
    )
    total = FactorScorer(registry)._continuation_total(
        adapted, ["momentum_20", "low_vol"]
    )
    assert total["strong"] > 0
    assert total["strong"] > total["cheap"]


def test_dead_factor_book_does_not_block_buy() -> None:
    now = datetime(2026, 10, 26)
    market = MarketSnapshot(symbol="600000", timestamp=now, price=10.0)
    pack = DecisionContextPack(
        symbol="600000",
        timestamp=now,
        market=market,
        risk_metrics=RiskMetrics(),
        sentiment=SentimentFactors(symbol="600000", timestamp=now),
        model_comparison=ModelComparison(),
        risk_state=RiskState(kelly_suggested_position=0.1),
    )
    ctx = SimpleNamespace(
        context_pack=pack,
        evaluation_mode=EvaluationMode.ENTRY.value,
        entry_eligible=True,
        ai_decision=None,
        factor_health=FactorHealthReport(
            symbol="600000",
            timestamp=now,
            factors=[],
            usable_count=0,
            active_count=0,
            disabled_count=6,
        ),
        policy_verdict=SimpleNamespace(max_position=0.1),
    )
    verdict = HardRiskGate().evaluate(ctx, Action.BUY.value)  # type: ignore[arg-type]
    assert verdict.approved
