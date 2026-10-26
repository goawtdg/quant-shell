"""63 日收益开仓：情绪、便宜和空因子库不再把分数对冲成无法开仓。"""
from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd
import pytest

from quant_shell.backtest.tradability import count_untradable
from quant_shell.common.constants import EvaluationMode
from quant_shell.common.exceptions import ValidationError
from quant_shell.common.policy_types import TradeSleeve
from quant_shell.common.types import (
    Action,
    AnalystReport,
    DecisionContextPack,
    FactorHealthReport,
    IntelligenceBrief,
    IntelligenceItem,
    MarketSnapshot,
    ModelComparison,
    PaperPosition,
    RiskMetrics,
    RiskState,
    SentimentFactors,
    SignalStrength,
    TradingSignal,
)
from quant_shell.data.constants import MOMENTUM_3M_DAYS
from quant_shell.execution.outcome import summarize_loss_boundary
from quant_shell.factors.registry import FactorRegistry
from quant_shell.intelligence.analyst.scorer import blend_sentiment_scores
from quant_shell.intelligence.brief import compute_sentiment_scores
from quant_shell.plugin.policy_config import SleevePolicyConfig
from quant_shell.risk.gate import HardRiskGate
from quant_shell.signals.fusion import SignalFusionGenerator
from quant_shell.signals.trailing_return import trailing_return
from reference_policy.picker.factor_scorer import FactorScorer
from reference_policy.picker.fundamental_factors import (
    evaluate_fundamentals_snapshot,
    save_fundamental_health_report,
)
from reference_policy.policy.hard_risk import HardCode, tighten_action
from reference_policy.policy.playbooks import (
    EntryContext,
    ThemeSwingPlaybook,
    decide_entry,
    decide_hold,
)
from reference_policy.picker.universe_filter import apply_universe_gates
from quant_shell.data.stock_yjbb import fetch_stock_roe, latest_announced


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
    return TradingSignal(
        symbol="600000",
        direction=Action.BUY if opportunity > 0 else Action.SELL,
        strength=SignalStrength.MODERATE,
        opportunity=opportunity,
    )


def _position() -> PaperPosition:
    return PaperPosition(
        symbol="600000",
        quantity=100,
        avg_cost=10.0,
        peak_price=10.0,
        sleeve="core",
    )


def test_trailing_return_is_close_to_close() -> None:
    closes = pd.Series([100.0] * MOMENTUM_3M_DAYS + [107.0])
    assert trailing_return(closes) == pytest.approx(0.07)


def test_short_history_is_not_a_flat_return() -> None:
    with pytest.raises(ValidationError, match="不足以计算"):
        trailing_return(pd.Series([10.0, 11.0, 12.0]))


def test_opportunity_is_the_return_not_the_sentiment(monkeypatch) -> None:
    closes = pd.Series([100.0] * MOMENTUM_3M_DAYS + [107.0])
    monkeypatch.setattr(
        "quant_shell.signals.fusion.fetch_daily_closes",
        lambda symbol: closes,
    )
    now = datetime(2026, 10, 26)
    signal = SignalFusionGenerator().generate(
        "600000",
        MarketSnapshot(symbol="600000", timestamp=now, price=107.0),
        SentimentFactors(symbol="600000", timestamp=now, composite=0.80),
    )
    assert signal.opportunity == pytest.approx(0.07)
    assert signal.direction == Action.BUY
    assert signal.components["sentiment"] == pytest.approx(0.80)
    assert "math" not in signal.components


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


def test_reduce_action_does_not_halve_the_language_score() -> None:
    now = datetime(2026, 10, 26)
    brief = IntelligenceBrief(
        symbol="600000",
        timestamp=now,
        items=[],
        source_count=0,
        corroboration_count=0,
    )
    report = AnalystReport(
        symbol="600000",
        timestamp=now,
        confidence=1.0,
        sentiment_score=-0.90,
        recommended_action="REDUCE",
        novelty="black_swan",
    )
    scores = blend_sentiment_scores(
        {
            "nlp_score": 0.50,
            "cross_validation": 0.50,
            "policy_risk": 0.0,
            "social_buzz": 0.80,
        },
        report,
        brief,
    )
    assert scores["composite"] == pytest.approx(-0.07)
    assert scores["social_buzz"] == pytest.approx(0.80)


def test_analyst_flags_do_not_block_an_entry_and_reduce_a_hold() -> None:
    codes = frozenset({HardCode.INTEL_REVIEW_HARD, HardCode.MONITOR_CRITICAL})
    opened = tighten_action(
        Action.BUY,
        codes,
        evaluation_mode=EvaluationMode.ENTRY.value,
        has_position=False,
    )
    reduced = tighten_action(
        Action.HOLD,
        codes,
        evaluation_mode=EvaluationMode.HOLD.value,
        has_position=True,
    )
    assert opened == Action.BUY
    assert reduced == Action.REDUCE


def test_rich_valuation_stays_on_continuation_book() -> None:
    verdict = decide_entry(
        symbol="600000",
        pe_percentile=0.95,
        pe_reliable=True,
        sentiment_composite=0.0,
        signal=_signal(0.12),
        theme_sleeve_exposure=0.0,
        microstructure_extra={},
        config=_policy(),
    )
    assert verdict.sleeve.value == "core"
    assert verdict.action == Action.BUY
    assert verdict.suggested_position == pytest.approx(0.05)
    assert any("估值分位" in reason for reason in verdict.block_reasons)


def test_return_thresholds_open_without_a_factor_library() -> None:
    blocked = decide_entry(
        symbol="600000",
        pe_percentile=0.40,
        pe_reliable=True,
        sentiment_composite=0.0,
        signal=_signal(0.04),
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
        theme_sleeve_exposure=0.0,
        microstructure_extra={},
        config=_policy(),
    )
    assert blocked.action == Action.WAIT
    assert opened.action == Action.BUY
    assert opened.suggested_position == pytest.approx(0.10)


def test_old_theme_entry_ignores_the_045_gate() -> None:
    verdict = ThemeSwingPlaybook().decide_entry(
        EntryContext(
            symbol="600000",
            sleeve=TradeSleeve.THEME_SWING,
            sleeve_reason="旧主题仓",
            pe_percentile=0.40,
            pe_reliable=True,
            sentiment_composite=0.0,
            signal=_signal(0.12),
            theme_sleeve_exposure=0.0,
            microstructure_extra={"symbol": "600000"},
            cross_validation=0.5,
            catalyst_ok=False,
            analyst=None,
            config=_policy(),
        )
    )
    assert verdict.action == Action.BUY
    assert verdict.suggested_position == pytest.approx(0.05)


def test_negative_return_reduces_inside_min_hold_and_drawdown_exits_first() -> None:
    reduced = decide_hold(
        sleeve=TradeSleeve.CORE,
        position=_position(),
        current_price=10.0,
        holding_days=1,
        analyst=None,
        monitor_alerts=[],
        pe_percentile=0.40,
        pe_reliable=True,
        signal_sell_pressure=0.03,
        volatility_annual=0.20,
        market_volatility_annual=0.20,
        config=_policy(),
    )
    held = decide_hold(
        sleeve=TradeSleeve.CORE,
        position=_position(),
        current_price=10.0,
        holding_days=1,
        analyst=None,
        monitor_alerts=[],
        pe_percentile=0.40,
        pe_reliable=True,
        signal_sell_pressure=0.0,
        volatility_annual=0.20,
        market_volatility_annual=0.20,
        config=_policy(),
    )
    stopped = decide_hold(
        sleeve=TradeSleeve.CORE,
        position=_position(),
        current_price=7.0,
        holding_days=1,
        analyst=None,
        monitor_alerts=[],
        pe_percentile=0.40,
        pe_reliable=True,
        signal_sell_pressure=0.20,
        volatility_annual=0.20,
        market_volatility_annual=0.20,
        config=_policy(),
    )
    assert reduced.action == Action.REDUCE
    assert any("63日收益已为负" in reason for reason in reduced.block_reasons)
    assert held.action == Action.HOLD
    assert stopped.action == Action.EXIT


def test_picker_ranks_industry_relative_return_not_cheapness() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["600000", "600001", "600002", "600003"],
            "name": ["强", "便宜", "缺收益", "*ST缺"],
            "price": [10.0, 10.0, 10.0, 10.0],
            "market_cap": [2e10, 2e10, 2e10, 2e10],
            "pe": [80.0, 8.0, 15.0, 15.0],
            "roe": [0.01, 0.30, 0.20, 0.20],
            "volume": [100.0, 100.0, 100.0, 100.0],
            "volume_ma20": [400.0, 400.0, 400.0, 400.0],
            "return_3m": [0.30, -0.20, None, 0.90],
            "return_5d": [0.01, 0.01, 0.01, 0.01],
            "return_10d": [0.01, 0.01, 0.01, 0.01],
            "at_limit_up": [False, False, False, False],
            "industry": ["银行", "银行", "银行", "银行"],
        }
    )
    kept = apply_universe_gates(frame)
    assert set(kept["symbol"]) == {"600000", "600001", "600002"}
    result = FactorScorer(FactorRegistry()).score("csi300", frame, top_n=5)
    assert [pick.symbol for pick in result.picks] == ["600000", "600001"]
    assert result.picks[0].score > result.picks[1].score
    assert result.picks[0].factor_scores["return_3m"] == pytest.approx(0.30)
    assert result.gate_diagnostics["missing_return_3m"] == 1


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
    ctx = type("Ctx", (), {})()
    ctx.context_pack = pack
    ctx.evaluation_mode = EvaluationMode.ENTRY.value
    ctx.entry_eligible = True
    ctx.ai_decision = None
    ctx.factor_health = FactorHealthReport(
        symbol="600000",
        timestamp=now,
        factors=[],
        usable_count=0,
        active_count=0,
        disabled_count=6,
    )
    ctx.policy_verdict = type("Verdict", (), {"max_position": 0.1})()
    verdict = HardRiskGate().evaluate(ctx, Action.BUY.value)  # type: ignore[arg-type]
    assert verdict.approved


def test_forward_five_day_ic_is_not_the_same_day_return(tmp_path, monkeypatch) -> None:
    symbols = ["600001", "600002", "600003", "600004", "600005"]
    frame = pd.DataFrame(
        {
            "symbol": symbols,
            "pe": [10.0, 12.0, 15.0, 20.0, 25.0],
            "roe": [0.10, 0.12, 0.08, 0.20, 0.05],
            "return_3m": [0.50, 0.40, 0.30, 0.20, 0.10],
            "industry": ["银行"] * 5,
            "turnover_rate": [1.0, 2.0, 3.0, 4.0, 5.0],
            "forward_return_5d": [-0.50, -0.40, -0.30, -0.20, -0.10],
        }
    )
    with pytest.raises(ValidationError, match="随后5日收益"):
        evaluate_fundamentals_snapshot(frame.drop(columns=["forward_return_5d"]))

    results = evaluate_fundamentals_snapshot(frame)
    momentum = next(item for item in results if item.name == "momentum_3m")
    assert momentum.mean_ic == pytest.approx(-1.0)
    assert momentum.sample_count == 5
    assert momentum.ir != momentum.ir

    import reference_policy.picker.fundamental_factors as report_mod

    monkeypatch.setattr(report_mod, "_FUNDAMENTAL_DIR", tmp_path)
    monkeypatch.setattr(report_mod, "_LATEST_PATH", tmp_path / "latest.json")
    save_fundamental_health_report(results, universe="test", symbol_count=5)
    payload = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    saved = next(item for item in payload["factors"] if item["name"] == "momentum_3m")
    assert saved["ir"] is None
    assert saved["mean_ic"] == pytest.approx(-1.0)


def test_roe_uses_the_announcement_date(monkeypatch) -> None:
    history = pd.DataFrame(
        {
            "股票代码": ["600000", "600000"],
            "净资产收益率": [10.0, 20.0],
            "公告日": ["2024-04-30", "2025-04-30"],
            "所处行业": ["银行", "银行"],
        }
    )
    published = latest_announced(history, date(2024, 12, 31))
    assert float(published.iloc[0]["净资产收益率"]) == pytest.approx(10.0)
    with pytest.raises(ValidationError, match="公告日"):
        latest_announced(history.drop(columns=["公告日"]), date(2024, 12, 31))

    monkeypatch.setattr(
        "quant_shell.data.stock_yjbb._yjbb_history",
        lambda: history,
    )
    assert fetch_stock_roe("600000", date(2024, 6, 1)) == pytest.approx(0.10)
    assert fetch_stock_roe("600000", date(2024, 1, 1)) is None


def test_loss_boundary_counts_buys_losses_and_stamp() -> None:
    summary = summarize_loss_boundary(
        [
            {"action": "BUY", "equity": 100.0, "stamp_duty": 0.0},
            {
                "action": "SELL",
                "equity": 90.0,
                "stamp_duty": 0.05,
                "unrealized_pnl_pct": -0.12,
            },
            {
                "action": "REDUCE",
                "equity": 95.0,
                "stamp_duty": 0.02,
                "unrealized_pnl_pct": -0.03,
            },
        ]
    )
    assert summary["buy_count"] == 1
    assert summary["worst_loss_pct"] == pytest.approx(-0.12)
    assert summary["max_drawdown"] == pytest.approx(-0.10)
    assert summary["stamp_duty"] == pytest.approx(0.07)
    assert summarize_loss_boundary([])["worst_loss_pct"] is None
    with pytest.raises(ValidationError, match="印花税"):
        summarize_loss_boundary([{"action": "SELL", "equity": 1.0}])


def test_limit_up_day_is_untradable() -> None:
    bars = pd.DataFrame(
        {
            "close": [10.0, 11.0, 11.0],
            "high": [10.0, 11.0, 11.2],
            "low": [10.0, 10.9, 10.8],
        }
    )
    assert count_untradable("600000", bars, name="浦发银行") == 1
    with pytest.raises(ValidationError, match="high"):
        count_untradable("600000", bars.drop(columns=["high"]))
