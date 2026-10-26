"""袖套剧本 — 开平仓唯一决策实现（四剧本 + 共享 helper）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quant_shell.common.types import (
    Action,
    AnalystReport,
    PaperPosition,
    TradingSignal,
)
from reference_policy.constants import (
    MAX_RETURN_5D_ENTRY,
    MAX_RETURN_10D_ENTRY,
)

# 高估不再改道。同一延续假设下，估值只把仓位打到这个比例。
_RICH_PE_ENTRY_SCALE = 0.5
from reference_policy.drawdown_threshold import compute_hold_exit_drawdown_limit
from reference_policy.policy.config import SleevePolicyConfig
from reference_policy.policy.router import classify_sleeve, compute_catalyst_ok
from reference_policy.policy.scoring import apply_entry_score
from reference_policy.policy.types import (
    THEME_BUDGET_SLEEVES,
    PolicyVerdict,
    SleeveLimits,
    TradeSleeve,
)


# ---------------------------------------------------------------------------
# 共享：微观结构 / 仓位 / 止盈 / 持仓袖套
# ---------------------------------------------------------------------------


def microstructure_entry_blocks(row: object) -> list[str]:
    """选股/入场共用的微观结构硬拦（涨停、短涨幅）。"""
    reasons: list[str] = []
    return_5d = float(_field(row, "return_5d", 0.0) or 0.0)
    return_10d = float(_field(row, "return_10d", 0.0) or 0.0)
    at_limit = bool(_field(row, "at_limit_up", False))
    if at_limit:
        reasons.append("涨停不可买")
    if return_5d > MAX_RETURN_5D_ENTRY:
        reasons.append(f"5日涨幅{return_5d:.0%}超限")
    if return_10d > MAX_RETURN_10D_ENTRY:
        reasons.append(f"10日涨幅{return_10d:.0%}超限")
    return reasons


def assess_pick_entry_eligibility(
    row: object, config: SleevePolicyConfig
) -> tuple[bool, str]:
    """截面选股入场标记：板块权限 + 微观结构（袖套在流水线再定）。"""
    symbol = str(_field(row, "symbol", "") or "")
    reasons: list[str] = []
    if config.pick_filter_board_permission and symbol:
        sleeve, reason = classify_sleeve(
            symbol=symbol,
            pe_percentile=0.5,
            pe_reliable=False,
            sentiment_composite=0.0,
            signal=None,
            config=config,
            catalyst_ok=False,
        )
        if sleeve == TradeSleeve.BLOCKED and "板块权限" in reason:
            reasons.append(reason)
    reasons.extend(microstructure_entry_blocks(row))
    if not reasons:
        return True, ""
    return False, "；".join(reasons)


def size_limits(sleeve: TradeSleeve, config: SleevePolicyConfig) -> SleeveLimits:
    """袖套仓位上限。"""
    if sleeve in (TradeSleeve.THEME_SWING, TradeSleeve.CATALYST):
        return SleeveLimits(
            max_position=config.theme_max_position,
            sleeve_budget=config.theme_sleeve_budget,
        )
    if sleeve == TradeSleeve.BLOCKED:
        return SleeveLimits(max_position=0.0, sleeve_budget=0.0)
    # core + etf_beta
    return SleeveLimits(
        max_position=config.single_stock_limit,
        sleeve_budget=1.0,
    )


def resolve_position_sleeve(position: PaperPosition | None) -> TradeSleeve:
    """持仓袖套；缺省或非法值视为错误，不静默回填。"""
    if position is None:
        raise ValueError("resolve_position_sleeve: position 为空")
    raw = (position.sleeve or "").strip()
    if not raw:
        raise ValueError(f"持仓 {position.symbol} 缺少 sleeve 字段")
    try:
        return TradeSleeve(raw)
    except ValueError as exc:
        raise ValueError(f"持仓 {position.symbol} 非法 sleeve={raw!r}") from exc


def touch_position_peak(position: PaperPosition, current_price: float) -> bool:
    """用现价刷新 peak_price；有变更返回 True。"""
    if current_price <= 0:
        return False
    new_peak = max(stored_peak_price(position), current_price)
    if abs(new_peak - position.peak_price) < 1e-9:
        return False
    position.peak_price = new_peak
    return True


def stored_peak_price(position: PaperPosition) -> float:
    if position.peak_price > 0:
        return position.peak_price
    return max(position.avg_cost, 0.0)


@dataclass(frozen=True)
class TakeProfitVerdict:
    action: Action
    reasons: list[str]
    pressure: float


def compute_take_profit_pressure(
    *,
    pnl_pct: float,
    pe_percentile: float,
    trail_drawdown: float = 0.0,
    pe_reliable: bool = True,
    config: SleevePolicyConfig,
) -> float:
    """综合止盈压力 [0, 1]。"""
    partial = config.take_profit_partial_pct
    full = config.take_profit_full_pct
    pnl_term = 0.0
    if full > 0 and pnl_pct > 0:
        pnl_term = min(1.0, pnl_pct / full)
    pe_term = 0.0
    rich = config.take_profit_pe_rich
    if pe_reliable and pe_percentile >= rich:
        pe_term = min(1.0, (pe_percentile - rich) / max(1e-6, 1.0 - rich))
    trail_term = 0.0
    if config.take_profit_trail_pct > 0 and pnl_pct >= partial * 0.5:
        trail_term = min(1.0, trail_drawdown / config.take_profit_trail_pct)
    return round(min(1.0, 0.55 * pnl_term + 0.30 * pe_term + 0.15 * trail_term), 4)


def _peak_reached_partial(
    position: PaperPosition, peak: float, config: SleevePolicyConfig
) -> bool:
    if position.avg_cost <= 0 or peak <= 0:
        return False
    return peak / position.avg_cost - 1.0 >= config.take_profit_partial_pct


def assess_take_profit_core(
    *,
    position: PaperPosition,
    current_price: float,
    pe_percentile: float,
    pe_reliable: bool,
    config: SleevePolicyConfig,
) -> TakeProfitVerdict | None:
    """core / etf：阶梯止盈 + PE 兑现。"""
    return _assess_take_profit(
        position=position,
        current_price=current_price,
        pe_percentile=pe_percentile,
        pe_reliable=pe_reliable,
        config=config,
        trail_first=False,
    )


def assess_take_profit_swing(
    *,
    position: PaperPosition,
    current_price: float,
    pe_percentile: float,
    pe_reliable: bool,
    config: SleevePolicyConfig,
) -> TakeProfitVerdict | None:
    """theme / catalyst：trailing 优先于『拿到目标价』。"""
    return _assess_take_profit(
        position=position,
        current_price=current_price,
        pe_percentile=pe_percentile,
        pe_reliable=pe_reliable,
        config=config,
        trail_first=True,
    )


def _assess_take_profit(
    *,
    position: PaperPosition,
    current_price: float,
    pe_percentile: float,
    pe_reliable: bool,
    config: SleevePolicyConfig,
    trail_first: bool,
) -> TakeProfitVerdict | None:
    if current_price <= 0 or position.avg_cost <= 0:
        return None
    pnl_pct = current_price / position.avg_cost - 1.0
    peak = stored_peak_price(position)
    trail_dd = (peak - current_price) / peak if peak > 0 else 0.0
    pe_for_rules = pe_percentile if pe_reliable else 0.5
    pressure = compute_take_profit_pressure(
        pnl_pct=pnl_pct,
        pe_percentile=pe_for_rules,
        trail_drawdown=trail_dd,
        pe_reliable=pe_reliable,
        config=config,
    )

    if pnl_pct >= config.take_profit_full_pct:
        return TakeProfitVerdict(
            action=Action.EXIT,
            reasons=[f"止盈:浮盈{pnl_pct:.0%}达目标清仓档"],
            pressure=pressure,
        )

    trail_hit = (
        _peak_reached_partial(position, peak, config)
        and trail_dd >= config.take_profit_trail_pct
    )
    if trail_first and trail_hit:
        return TakeProfitVerdict(
            action=Action.REDUCE,
            reasons=[f"止盈:相对持仓高点回撤{trail_dd:.0%}，短线保护利润"],
            pressure=pressure,
        )

    if (
        pe_reliable
        and pe_percentile >= config.take_profit_pe_exit
        and pnl_pct >= config.take_profit_partial_pct
    ):
        return TakeProfitVerdict(
            action=Action.EXIT,
            reasons=[
                f"止盈:PE百分位{pe_percentile:.0%}极高估且浮盈{pnl_pct:.0%}，清仓落袋"
            ],
            pressure=pressure,
        )

    if pnl_pct >= config.take_profit_scale_pct:
        return TakeProfitVerdict(
            action=Action.REDUCE,
            reasons=[f"止盈:浮盈{pnl_pct:.0%}达加码兑现档，分批减仓"],
            pressure=pressure,
        )

    if not trail_first and trail_hit:
        return TakeProfitVerdict(
            action=Action.REDUCE,
            reasons=[f"止盈:相对持仓高点回撤{trail_dd:.0%}，保护利润"],
            pressure=pressure,
        )

    if pnl_pct >= config.take_profit_partial_pct:
        return TakeProfitVerdict(
            action=Action.REDUCE,
            reasons=[f"止盈:浮盈{pnl_pct:.0%}达分批兑现档"],
            pressure=pressure,
        )

    if pe_reliable and pe_percentile >= config.take_profit_pe_rich and pnl_pct > 0:
        return TakeProfitVerdict(
            action=Action.REDUCE,
            reasons=[
                f"止盈:PE百分位{pe_percentile:.0%}高估且浮盈{pnl_pct:.0%}，减仓兑现"
            ],
            pressure=pressure,
        )
    return None


# ---------------------------------------------------------------------------
# Playbook 协议与入口
# ---------------------------------------------------------------------------


class SleevePlaybook(Protocol):
    def decide_entry(self, ctx: "EntryContext") -> PolicyVerdict: ...

    def decide_hold(self, ctx: "HoldContext") -> PolicyVerdict: ...


@dataclass(frozen=True)
class EntryContext:
    symbol: str
    sleeve: TradeSleeve
    sleeve_reason: str
    pe_percentile: float
    pe_reliable: bool
    sentiment_composite: float
    signal: TradingSignal | None
    theme_sleeve_exposure: float
    microstructure_extra: dict[str, object]
    cross_validation: float
    catalyst_ok: bool
    analyst: AnalystReport | None
    config: SleevePolicyConfig


@dataclass(frozen=True)
class HoldContext:
    sleeve: TradeSleeve
    position: PaperPosition
    current_price: float
    holding_days: int
    analyst: AnalystReport | None
    monitor_alerts: list[str]
    pe_percentile: float
    pe_reliable: bool
    signal_sell_pressure: float
    volatility_annual: float
    market_volatility_annual: float | None
    sentiment_composite: float
    cross_validation: float
    config: SleevePolicyConfig


def decide_entry(
    *,
    symbol: str,
    pe_percentile: float,
    pe_reliable: bool,
    sentiment_composite: float,
    signal: TradingSignal | None,
    theme_sleeve_exposure: float,
    microstructure_extra: dict[str, object] | None,
    config: SleevePolicyConfig,
    cross_validation: float = 0.5,
    analyst: AnalystReport | None = None,
    catalyst_ok: bool | None = None,
) -> PolicyVerdict:
    """入场：路由袖套后分派剧本。"""
    if catalyst_ok is None:
        catalyst_ok = compute_catalyst_ok(
            cross_validation=cross_validation,
            analyst=analyst,
        )
    sleeve, sleeve_reason = classify_sleeve(
        symbol=symbol,
        pe_percentile=pe_percentile,
        pe_reliable=pe_reliable,
        sentiment_composite=sentiment_composite,
        signal=signal,
        config=config,
        catalyst_ok=catalyst_ok,
    )
    if sleeve == TradeSleeve.BLOCKED:
        blocks = list(
            microstructure_entry_blocks(
                microstructure_extra or {"symbol": symbol}
            )
        )
        blocks.append(sleeve_reason)
        return PolicyVerdict(
            sleeve=sleeve,
            sleeve_reason=sleeve_reason,
            action=Action.WAIT,
            entry_eligible=False,
            block_reasons=blocks,
            max_position=0.0,
            suggested_position=0.0,
            rule_resolved=True,
        )
    ctx = EntryContext(
        symbol=symbol,
        sleeve=sleeve,
        sleeve_reason=sleeve_reason,
        pe_percentile=pe_percentile,
        pe_reliable=pe_reliable,
        sentiment_composite=sentiment_composite,
        signal=signal,
        theme_sleeve_exposure=theme_sleeve_exposure,
        microstructure_extra=dict(microstructure_extra or {"symbol": symbol}),
        cross_validation=cross_validation,
        catalyst_ok=catalyst_ok,
        analyst=analyst,
        config=config,
    )
    return playbook_for(sleeve).decide_entry(ctx)


def decide_hold(
    *,
    sleeve: TradeSleeve,
    position: PaperPosition,
    current_price: float,
    holding_days: int,
    analyst: AnalystReport | None,
    monitor_alerts: list[str],
    pe_percentile: float,
    pe_reliable: bool,
    signal_sell_pressure: float,
    volatility_annual: float,
    market_volatility_annual: float | None,
    config: SleevePolicyConfig,
    sentiment_composite: float = 0.0,
    cross_validation: float = 0.5,
) -> PolicyVerdict:
    """持有：按开仓袖套分派剧本（禁止重路由）。"""
    if sleeve == TradeSleeve.BLOCKED:
        return _hold_verdict(
            sleeve,
            Action.EXIT,
            ["blocked 袖套持仓强制退出"],
            0.0,
            size_limits(sleeve, config),
            True,
        )
    ctx = HoldContext(
        sleeve=sleeve,
        position=position,
        current_price=current_price,
        holding_days=holding_days,
        analyst=analyst,
        monitor_alerts=monitor_alerts,
        pe_percentile=pe_percentile,
        pe_reliable=pe_reliable,
        signal_sell_pressure=signal_sell_pressure,
        volatility_annual=volatility_annual,
        market_volatility_annual=market_volatility_annual,
        sentiment_composite=sentiment_composite,
        cross_validation=cross_validation,
        config=config,
    )
    return playbook_for(sleeve).decide_hold(ctx)


def playbook_for(sleeve: TradeSleeve) -> SleevePlaybook:
    try:
        return _PLAYBOOKS[sleeve]
    except KeyError as exc:
        raise ValueError(f"无剧本注册: {sleeve}") from exc


# ---------------------------------------------------------------------------
# 共享 hold 步骤
# ---------------------------------------------------------------------------


def _shared_alert_and_analyst_exits(ctx: HoldContext) -> PolicyVerdict | None:
    limits = size_limits(ctx.sleeve, ctx.config)
    reasons: list[str] = []
    pressure = _hold_pressure(ctx)
    if _has_reduce_alert(ctx.monitor_alerts):
        reasons.append("监控告警建议减仓")
        return _hold_verdict(ctx.sleeve, Action.REDUCE, reasons, pressure, limits, True)
    if ctx.analyst and ctx.analyst.recommended_action in ("REDUCE", "HUMAN_ONLY"):
        reasons.append(f"情报建议 {ctx.analyst.recommended_action}")
        if ctx.analyst.recommended_action == "HUMAN_ONLY":
            return _hold_verdict(ctx.sleeve, Action.HOLD, reasons, pressure, limits, True)
        return _hold_verdict(ctx.sleeve, Action.REDUCE, reasons, pressure, limits, True)
    return None


def _exit_drawdown_limit(ctx: HoldContext) -> float:
    dynamic = compute_hold_exit_drawdown_limit(
        ctx.volatility_annual,
        market_volatility_annual=ctx.market_volatility_annual,
    )
    if ctx.sleeve in (TradeSleeve.THEME_SWING, TradeSleeve.CATALYST):
        return min(dynamic, ctx.config.theme_exit_dd)
    return dynamic


def _position_drawdown(ctx: HoldContext) -> float:
    peak = stored_peak_price(ctx.position)
    if peak <= 0 or ctx.current_price <= 0:
        return 0.0
    return max(0.0, (peak - ctx.current_price) / peak)


def _hold_pressure(ctx: HoldContext) -> float:
    pnl = _unrealized_pnl_pct(ctx.position, ctx.current_price)
    return compute_take_profit_pressure(
        pnl_pct=pnl,
        pe_percentile=ctx.pe_percentile if ctx.pe_reliable else 0.5,
        trail_drawdown=_position_drawdown(ctx),
        pe_reliable=ctx.pe_reliable,
        config=ctx.config,
    )


def _hold_verdict(
    sleeve: TradeSleeve,
    action: Action,
    reasons: list[str],
    pressure: float,
    limits: SleeveLimits,
    rule_resolved: bool,
) -> PolicyVerdict:
    return PolicyVerdict(
        sleeve=sleeve,
        sleeve_reason=f"hold:{sleeve.value}",
        action=action,
        entry_eligible=False,
        block_reasons=list(reasons),
        max_position=limits.max_position,
        suggested_position=0.0,
        rule_resolved=rule_resolved,
        take_profit_pressure=pressure,
    )


def _has_reduce_alert(messages: list[str]) -> bool:
    for msg in messages:
        upper = msg.upper()
        if "ACTION:" in upper and "REDUCE" in upper:
            return True
        if upper.startswith("REDUCE:"):
            return True
    return False


def _unrealized_pnl_pct(position: PaperPosition, price: float) -> float:
    if position.avg_cost <= 0:
        return 0.0
    return price / position.avg_cost - 1.0


def _field(row: object, key: str, default: object) -> object:
    if isinstance(row, dict):
        val = row.get(key, default)
    else:
        val = getattr(row, key, default)
    if val is None:
        return default
    return val


def _entry_micro_or_budget_blocks(ctx: EntryContext) -> list[str]:
    blocks = list(microstructure_entry_blocks(ctx.microstructure_extra))
    if (
        ctx.sleeve in THEME_BUDGET_SLEEVES
        and ctx.theme_sleeve_exposure >= ctx.config.theme_sleeve_budget
    ):
        blocks.append(
            f"主题袖套暴露{ctx.theme_sleeve_exposure:.0%}已达预算"
            f"{ctx.config.theme_sleeve_budget:.0%}"
        )
    return blocks


def _finish_entry(ctx: EntryContext, blocks: list[str]) -> PolicyVerdict:
    """微结构/预算硬拦 → scoring 机会门槛+质量缩仓（唯一评分入口）。"""
    limits = size_limits(ctx.sleeve, ctx.config)
    if blocks:
        return PolicyVerdict(
            sleeve=ctx.sleeve,
            sleeve_reason=ctx.sleeve_reason,
            action=Action.WAIT,
            entry_eligible=False,
            block_reasons=blocks,
            max_position=limits.max_position,
            suggested_position=0.0,
            rule_resolved=True,
        )
    action, suggested, chain = apply_entry_score(
        ctx.signal,
        sleeve_max=limits.max_position,
        config=ctx.config,
    )
    if action == Action.HOLD:
        action = Action.WAIT
        if not chain:
            chain = ["入场未达开仓条件"]
    eligible = action == Action.BUY
    if eligible:
        suggested = _apply_rich_pe_haircut(ctx, suggested, chain)
        reasons = [r for r in chain if "QUALITY_SCALE" in r or "估值分位" in r]
    else:
        reasons = chain
    return PolicyVerdict(
        sleeve=ctx.sleeve,
        sleeve_reason=ctx.sleeve_reason,
        action=action,
        entry_eligible=eligible if action != Action.WAIT else False,
        block_reasons=reasons,
        max_position=limits.max_position,
        suggested_position=suggested if action == Action.BUY else 0.0,
        rule_resolved=action == Action.WAIT and not eligible,
    )


def _apply_rich_pe_haircut(
    ctx: EntryContext, suggested: float, chain: list[str]
) -> float:
    """高估只缩仓。不把股票送进另一套开仓条件。"""
    if not ctx.pe_reliable:
        return suggested
    if ctx.pe_percentile < ctx.config.core_pe_block_percentile:
        return suggested
    chain.append(
        f"估值分位{ctx.pe_percentile:.0%}≥{ctx.config.core_pe_block_percentile:.0%}"
        f"，仓位×{_RICH_PE_ENTRY_SCALE:.2f}"
    )
    return suggested * _RICH_PE_ENTRY_SCALE


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


class CorePlaybook:
    """个股因子/估值中长期。"""

    def decide_entry(self, ctx: EntryContext) -> PolicyVerdict:
        return _finish_entry(ctx, _entry_micro_or_budget_blocks(ctx))

    def decide_hold(self, ctx: HoldContext) -> PolicyVerdict:
        early = _shared_alert_and_analyst_exits(ctx)
        if early is not None:
            return early
        limits = size_limits(ctx.sleeve, ctx.config)
        pressure = _hold_pressure(ctx)
        dd = _position_drawdown(ctx)
        exit_dd = _exit_drawdown_limit(ctx)
        if dd >= exit_dd:
            return _hold_verdict(
                ctx.sleeve,
                Action.EXIT,
                [
                    f"持仓高点回撤 {dd:.0%} 超阈值 {exit_dd:.0%}"
                    f"（sleeve={ctx.sleeve.value} σ={ctx.volatility_annual:.0%}）"
                ],
                pressure,
                limits,
                True,
            )
        if ctx.signal_sell_pressure > 0:
            return _hold_verdict(
                ctx.sleeve,
                Action.REDUCE,
                ["63日收益已为负，不受最短持有限制"],
                pressure,
                limits,
                True,
            )
        pnl = _unrealized_pnl_pct(ctx.position, ctx.current_price)
        sentiment = ctx.analyst.sentiment_score if ctx.analyst else 0.0
        if pnl < -0.10 and ctx.analyst and sentiment < -0.2:
            return _hold_verdict(
                ctx.sleeve,
                Action.REDUCE,
                ["浮亏且情绪转弱，逻辑可能破坏"],
                pressure,
                limits,
                True,
            )
        tp = assess_take_profit_core(
            position=ctx.position,
            current_price=ctx.current_price,
            pe_percentile=ctx.pe_percentile,
            pe_reliable=ctx.pe_reliable,
            config=ctx.config,
        )
        if tp is not None:
            return _hold_verdict(
                ctx.sleeve, tp.action, tp.reasons, tp.pressure, limits, True
            )
        if ctx.holding_days < ctx.config.core_min_hold_days:
            return _hold_verdict(
                ctx.sleeve,
                Action.HOLD,
                [f"持有未满{ctx.config.core_min_hold_days}日，纪律性扛波动"],
                pressure,
                limits,
                True,
            )
        return _hold_verdict(
            ctx.sleeve,
            Action.HOLD,
            ["基本面未破坏，正常波动继续持有"],
            pressure,
            limits,
            False,
        )


# ---------------------------------------------------------------------------
# Theme swing
# ---------------------------------------------------------------------------


class ThemeSwingPlaybook:
    """高估 + 主题/故事动能短持。"""

    def decide_entry(self, ctx: EntryContext) -> PolicyVerdict:
        return _finish_entry(ctx, _entry_micro_or_budget_blocks(ctx))

    def decide_hold(self, ctx: HoldContext) -> PolicyVerdict:
        early = _shared_alert_and_analyst_exits(ctx)
        if early is not None:
            return early
        limits = size_limits(ctx.sleeve, ctx.config)
        pressure = _hold_pressure(ctx)
        # 叙事失效优先（禁止最短持有扛波动）
        sentiment = ctx.analyst.sentiment_score if ctx.analyst else ctx.sentiment_composite
        if sentiment < -0.15 or (
            ctx.analyst and ctx.analyst.recommended_action == "MONITOR" and sentiment < 0.05
        ):
            return _hold_verdict(
                ctx.sleeve,
                Action.REDUCE,
                ["主题叙事转弱，短线减仓"],
                pressure,
                limits,
                True,
            )
        if ctx.holding_days >= ctx.config.theme_max_hold_days:
            return _hold_verdict(
                ctx.sleeve,
                Action.EXIT,
                [f"主题短线持有满{ctx.config.theme_max_hold_days}日，到期退出"],
                pressure,
                limits,
                True,
            )
        dd = _position_drawdown(ctx)
        exit_dd = _exit_drawdown_limit(ctx)
        if dd >= exit_dd:
            return _hold_verdict(
                ctx.sleeve,
                Action.EXIT,
                [
                    f"持仓高点回撤 {dd:.0%} 超阈值 {exit_dd:.0%}"
                    f"（sleeve={ctx.sleeve.value}）"
                ],
                pressure,
                limits,
                True,
            )
        if ctx.signal_sell_pressure > 0:
            return _hold_verdict(
                ctx.sleeve,
                Action.REDUCE,
                ["63日收益已为负，主题仓同样减仓"],
                pressure,
                limits,
                True,
            )
        tp = assess_take_profit_swing(
            position=ctx.position,
            current_price=ctx.current_price,
            pe_percentile=ctx.pe_percentile,
            pe_reliable=ctx.pe_reliable,
            config=ctx.config,
        )
        if tp is not None:
            return _hold_verdict(
                ctx.sleeve, tp.action, tp.reasons, tp.pressure, limits, True
            )
        return _hold_verdict(
            ctx.sleeve,
            Action.HOLD,
            ["主题短线持有中，继续监控"],
            pressure,
            limits,
            False,
        )


# ---------------------------------------------------------------------------
# ETF beta
# ---------------------------------------------------------------------------


class EtfBetaPlaybook:
    """宽基/行业 ETF：再平衡式进出，无个股扛波动。"""

    def decide_entry(self, ctx: EntryContext) -> PolicyVerdict:
        blocks = list(microstructure_entry_blocks(ctx.microstructure_extra))
        return _finish_entry(ctx, blocks)

    def decide_hold(self, ctx: HoldContext) -> PolicyVerdict:
        early = _shared_alert_and_analyst_exits(ctx)
        if early is not None:
            return early
        limits = size_limits(ctx.sleeve, ctx.config)
        pressure = _hold_pressure(ctx)
        dd = _position_drawdown(ctx)
        exit_dd = _exit_drawdown_limit(ctx)
        if dd >= exit_dd:
            return _hold_verdict(
                ctx.sleeve,
                Action.EXIT,
                [
                    f"ETF高点回撤 {dd:.0%} 超阈值 {exit_dd:.0%}，再平衡退出"
                ],
                pressure,
                limits,
                True,
            )
        tp = assess_take_profit_core(
            position=ctx.position,
            current_price=ctx.current_price,
            pe_percentile=ctx.pe_percentile,
            pe_reliable=ctx.pe_reliable,
            config=ctx.config,
        )
        if tp is not None:
            return _hold_verdict(
                ctx.sleeve, tp.action, tp.reasons, tp.pressure, limits, True
            )
        if ctx.signal_sell_pressure > 0:
            return _hold_verdict(
                ctx.sleeve,
                Action.REDUCE,
                ["63日收益已为负，再平衡减仓"],
                pressure,
                limits,
                True,
            )
        return _hold_verdict(
            ctx.sleeve,
            Action.HOLD,
            ["ETF beta 持有，等待再平衡信号"],
            pressure,
            limits,
            False,
        )


# ---------------------------------------------------------------------------
# Catalyst
# ---------------------------------------------------------------------------


class CatalystPlaybook:
    """事件/催化剂驱动：事件生命周期优先于价值叙事。"""

    def decide_entry(self, ctx: EntryContext) -> PolicyVerdict:
        blocks = _entry_micro_or_budget_blocks(ctx)
        # 事件证据与路由同源：仅 catalyst_ok，禁止摘要 key_events
        if not ctx.catalyst_ok:
            blocks.append("催化剂证据不足（印证/事实）")
        return _finish_entry(ctx, blocks)

    def decide_hold(self, ctx: HoldContext) -> PolicyVerdict:
        early = _shared_alert_and_analyst_exits(ctx)
        if early is not None:
            return early
        limits = size_limits(ctx.sleeve, ctx.config)
        pressure = _hold_pressure(ctx)
        # 事件失效即出
        if ctx.analyst and ctx.analyst.recommended_action in ("MONITOR", "REDUCE"):
            if ctx.analyst.recommended_action == "REDUCE":
                return _hold_verdict(
                    ctx.sleeve,
                    Action.REDUCE,
                    ["催化剂失效：情报建议 REDUCE"],
                    pressure,
                    limits,
                    True,
                )
            sentiment = ctx.analyst.sentiment_score
            if sentiment < 0.1 or ctx.cross_validation < 0.55:
                return _hold_verdict(
                    ctx.sleeve,
                    Action.EXIT,
                    ["催化剂窗口结束：MONITOR 且印证/情绪回落"],
                    pressure,
                    limits,
                    True,
                )
        sentiment = ctx.analyst.sentiment_score if ctx.analyst else ctx.sentiment_composite
        if sentiment < -0.1:
            return _hold_verdict(
                ctx.sleeve,
                Action.EXIT,
                ["催化剂情绪骤降，事件驱动退出"],
                pressure,
                limits,
                True,
            )
        max_days = max(1, ctx.config.theme_max_hold_days - 2)
        if ctx.holding_days >= max_days:
            return _hold_verdict(
                ctx.sleeve,
                Action.EXIT,
                [f"催化剂最长持有{max_days}日到期退出"],
                pressure,
                limits,
                True,
            )
        dd = _position_drawdown(ctx)
        exit_dd = _exit_drawdown_limit(ctx)
        if dd >= exit_dd:
            return _hold_verdict(
                ctx.sleeve,
                Action.EXIT,
                [f"催化剂回撤 {dd:.0%} 超阈值 {exit_dd:.0%}"],
                pressure,
                limits,
                True,
            )
        tp = assess_take_profit_swing(
            position=ctx.position,
            current_price=ctx.current_price,
            pe_percentile=ctx.pe_percentile,
            pe_reliable=ctx.pe_reliable,
            config=ctx.config,
        )
        if tp is not None:
            return _hold_verdict(
                ctx.sleeve, tp.action, tp.reasons, tp.pressure, limits, True
            )
        return _hold_verdict(
            ctx.sleeve,
            Action.HOLD,
            ["催化剂事件仍成立，继续持有"],
            pressure,
            limits,
            False,
        )


_PLAYBOOKS: dict[TradeSleeve, SleevePlaybook] = {
    TradeSleeve.CORE: CorePlaybook(),
    TradeSleeve.THEME_SWING: ThemeSwingPlaybook(),
    TradeSleeve.ETF_BETA: EtfBetaPlaybook(),
    TradeSleeve.CATALYST: CatalystPlaybook(),
}
