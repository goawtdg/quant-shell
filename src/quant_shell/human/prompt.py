"""L7 DeepSeek 决策推理 Prompt。"""
from __future__ import annotations

import json

from quant_shell.common.types import DecisionContextPack


def build_decision_messages(pack: DecisionContextPack) -> list[dict[str, str]]:
    """将 Context Pack 转为 DeepSeek chat messages。"""
    payload = _pack_payload(pack)
    system = (
        "你是 A 股量化系统的 L7 决策分析师，负责阅读 Context Pack 并给出结构化解释。"
        "成交动作唯一真相是 L4 PolicyVerdict + commit_decision（硬风险从 ContextPack 派生）；"
        "你没有成交决定权，只解释证据。"
        "原则："
        "1) 综合 L1–L5 证据写推理链；"
        "2) risk_flags 只许软标签（如 INTEL_REVIEW_SOFT、PE_UNRELIABLE、FACTOR_DEGRADED:*）；"
        "禁止输出 MONITOR_CRITICAL / INTEL_REVIEW_HARD / STRATEGY_DEGRADED（硬码由代码注入）；"
        "3) evaluation_mode=hold 时叙述倾向不要写成强买；"
        "4) 服从 trade_sleeve 语义："
        "core / theme_swing / etf_beta / catalyst / blocked；"
        "5) 不得编造未提供的数据；不确定时 human_review_required=true；"
        "6) action 字段仅作叙述倾向，最终以政策定稿为准。"
    )
    user = (
        "请基于以下 Context Pack 输出 JSON（不要 markdown）：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "JSON 字段（必须全部包含）：\n"
        "{\n"
        '  "action": "BUY|SELL|HOLD|REDUCE|EXIT|WAIT",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "reasoning_chain": ["推理步骤1", "..."],\n'
        '  "risk_flags": ["风险标签"],\n'
        '  "suggested_position_change": 0.0-0.25,\n'
        '  "human_review_required": true/false\n'
        "}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _pack_payload(pack: DecisionContextPack) -> dict[str, object]:
    signal = pack.signal
    analyst = pack.sentiment.analyst_report
    return {
        "symbol": pack.symbol,
        "trade_sleeve": pack.trade_sleeve,
        "sleeve_reason": pack.sleeve_reason,
        "asset_type": pack.market.extra.get("asset_type", "unknown"),
        "market": {
            "price": pack.market.price,
            "pe_percentile": pack.market.pe_percentile,
            "pe_ttm": pack.market.extra.get("pe_ttm"),
            "pe_percentile_source": pack.market.extra.get("pe_percentile_source", ""),
            "pe_reliable": pack.market.extra.get("pe_reliable", False),
            "pe_unreliable_reason": pack.market.extra.get("pe_unreliable_reason", ""),
            "pe_proxy_over_200": pack.market.extra.get("pe_proxy_over_200"),
            "name": pack.market.extra.get("name", pack.market.extra.get("index_name", "")),
            "note": (
                "若 pe_reliable=false：禁止把 pe_percentile 说成历史低估/高估；"
                "pe_proxy_over_200 仅诊断，不得作为买入理由。"
            ),
        },
        "signal": {
            "direction": signal.direction.value if signal else "HOLD",
            "strength": signal.strength.value if signal else "WEAK",
            "opportunity": signal.opportunity if signal else 0.0,
            "quality": signal.quality if signal else None,
            "components": signal.components if signal else {},
        },
        "sentiment": {
            "composite": pack.sentiment.composite,
            "cross_validation": pack.sentiment.cross_validation,
            "policy_risk": pack.sentiment.policy_risk,
            "key_events": pack.sentiment.key_events[:5],
        },
        "analyst": {
            "executive_summary": analyst.executive_summary[:300] if analyst else "",
            "confidence": analyst.confidence if analyst else 0.0,
            "human_review_required": analyst.human_review_required if analyst else False,
            "recommended_action": analyst.recommended_action if analyst else "MONITOR",
            "novelty": analyst.novelty if analyst else "uncertain",
        },
        "risk_metrics": {
            "sharpe_ratio": pack.risk_metrics.sharpe_ratio,
            "current_drawdown": pack.risk_metrics.current_drawdown,
            "max_drawdown": pack.risk_metrics.max_drawdown,
            "volatility_annual": pack.risk_metrics.volatility_annual,
        },
        "model_comparison": {
            "strategy": pack.model_comparison.current_strategy,
            "regime": pack.model_comparison.regime,
            "deviation": pack.model_comparison.deviation,
            "live_sharpe_30d": pack.model_comparison.live_sharpe_30d,
            "backtest_sharpe": pack.model_comparison.backtest_sharpe,
        },
        "risk_state": {
            "current_position": pack.risk_state.current_position,
            "total_position_pct": pack.risk_state.total_position_pct,
            "kelly_suggested_position": pack.risk_state.kelly_suggested_position,
            "drawdown_limit_remaining": pack.risk_state.drawdown_limit_remaining,
            "portfolio_drawdown": pack.risk_state.portfolio_drawdown,
            "cost_basis": pack.risk_state.cost_basis,
            "unrealized_pnl_pct": pack.risk_state.unrealized_pnl_pct,
            "holding_days": pack.risk_state.holding_days,
            "take_profit_pressure": pack.risk_state.take_profit_pressure,
        },
        "evaluation_mode": pack.evaluation_mode,
        "factor_health": {
            "active_count": pack.factor_active_count,
            "usable_count": pack.factor_usable_count,
            "coverage": pack.factor_coverage,
            "degraded_count": pack.factor_degraded_count,
            "disabled_count": pack.factor_disabled_count,
        },
        "monitor_alerts": pack.monitor_alert_messages[:5],
    }
