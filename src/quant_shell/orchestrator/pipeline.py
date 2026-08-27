"""七层流水线编排 — 唯一编排入口。"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime

from quant_shell.common import audit
from quant_shell.common.constants import EvaluationMode, LayerId, LayerStatus
from quant_shell.common.interfaces import (
    DataSource,
    ExecutionEngine,
    HumanReviewGate,
    IntelligenceFusion,
    RiskEngine,
    SignalGenerator,
    StrategyEngine,
)
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import (
    Action,
    AIDecision,
    LayerResult,
    MonitorAlert,
    OrderRequest,
    PipelineContext,
    SentimentFactors,
)
from quant_shell.config.settings import settings
from quant_shell.data.symbol import asset_type
from quant_shell.data.unified_source import UnifiedMarketDataSource
from quant_shell.intelligence.noop import build_default_intelligence_fusion
from quant_shell.signals.fusion import SignalFusionGenerator
from quant_shell.factory import create_strategy_engine, create_signal_generator, create_commit_decision
from quant_shell.common.policy_types import TradeSleeve
from quant_shell.risk.enricher import RiskContextEnricher
from quant_shell.risk.gate import HardRiskGate
from quant_shell.execution.paper_engine import PaperTradingEngine
from quant_shell.human.llm_gate import LlmHumanReviewGate, build_default_human_gate

logger = get_logger(__name__)

_EXECUTABLE_ACTIONS = (Action.BUY, Action.SELL, Action.REDUCE, Action.EXIT)

_LAYER_CODE = {
    LayerId.L1_DATA: "L1",
    LayerId.L2_INTELLIGENCE: "L2",
    LayerId.L3_SIGNALS: "L3",
    LayerId.L4_STRATEGY: "L4",
    LayerId.L5_RISK: "L5",
    LayerId.L6_EXECUTION: "L6",
    LayerId.L7_AI_REASON: "L7",
    LayerId.L7_HUMAN: "L7",
}


def _intel_cache_is_fresh(cached: SentimentFactors) -> bool:
    """按 settings.intel_cache_max_age_min 判断缓存是否仍有效。"""
    max_age = settings.intel_cache_max_age_min
    if max_age <= 0:
        return True
    age_min = (datetime.now() - cached.timestamp).total_seconds() / 60.0
    return age_min <= max_age


def _record_layer(
    ctx: PipelineContext,
    layer: LayerId,
    status: LayerStatus,
    message: str = "",
    *,
    event: str = "layer_ok",
    data: dict | None = None,
) -> None:
    """写入内存 audit_trail 并 emit 唯一审计钩子。"""
    ctx.audit_trail.append(LayerResult(layer, status, message))
    if status == LayerStatus.ERROR:
        severity = "ERROR"
        error_code = "PIPELINE_ERROR"
        event = "layer_error"
    elif status == LayerStatus.BLOCKED:
        severity = "WARN"
        error_code = ""
        if event == "layer_ok":
            event = "layer_blocked"
    else:
        severity = "INFO"
        error_code = ""
    audit.emit(
        layer=_LAYER_CODE.get(layer, layer.value),
        event=event,
        severity=severity,
        run_id=ctx.run_id,
        symbol=ctx.symbol,
        error_code=error_code,
        message=message,
        data=data or {},
    )


class TradingPipeline:
    """七层流水线 — 依赖注入，每层单一实现。"""

    def __init__(
        self,
        data_source: DataSource | None = None,
        intelligence: IntelligenceFusion | None = None,
        signal_gen: SignalGenerator | None = None,
        strategy: StrategyEngine | None = None,
        risk: RiskEngine | None = None,
        risk_enricher: RiskContextEnricher | None = None,
        execution: ExecutionEngine | None = None,
        human_gate: HumanReviewGate | None = None,
        commit_fn=None,
    ) -> None:
        self._source = data_source or UnifiedMarketDataSource()
        self._intelligence = intelligence or build_default_intelligence_fusion()
        self._signal_gen = signal_gen or create_signal_generator()
        self._strategy = strategy or create_strategy_engine()
        self.risk = risk or HardRiskGate()
        self._risk_enricher = risk_enricher or RiskContextEnricher()
        self._execution = execution or PaperTradingEngine()
        self._human_gate = human_gate or build_default_human_gate()
        self._commit = commit_fn or create_commit_decision()

    def run(
        self,
        symbol: str,
        *,
        auto_approve: bool = False,
        intel_cache: dict[str, SentimentFactors] | None = None,
        monitor_alerts: list[MonitorAlert] | None = None,
        evaluation_mode: str = EvaluationMode.ENTRY.value,
        entry_eligible: bool = True,
        entry_block_reason: str = "",
    ) -> PipelineContext:
        """执行完整七层流水线。"""
        ctx = PipelineContext(
            symbol=symbol,
            run_id=audit.current_run_id() or str(uuid.uuid4())[:8],
            timestamp=datetime.now(),
            intel_cache=intel_cache or {},
            monitor_alerts=list(monitor_alerts or []),
            evaluation_mode=evaluation_mode,
            entry_eligible=entry_eligible,
            entry_block_reason=entry_block_reason,
        )
        pipeline_id = str(uuid.uuid4())[:8]
        logger.info(
            "pipeline start run_id=%s pipeline_id=%s symbol=%s mode=%s",
            ctx.run_id,
            pipeline_id,
            symbol,
            evaluation_mode,
        )
        audit.emit(
            layer="orch",
            event="phase_start",
            run_id=ctx.run_id,
            symbol=symbol,
            message="pipeline_start",
            data={
                "pipeline_id": pipeline_id,
                "asset_type": asset_type(symbol),
                "intel_cached": symbol in (intel_cache or {}),
                "evaluation_mode": evaluation_mode,
            },
        )

        self._run_data_layer(ctx)
        self._run_intelligence_layer(ctx)
        self._run_signal_layer(ctx)
        self._run_strategy_layer(ctx)
        self._run_risk_enrich_layer(ctx)
        self._run_policy_finalize(ctx)
        self._apply_entry_gate(ctx)
        self._run_ai_reason_layer(ctx)
        self._run_risk_gate_layer(ctx)
        approved = self._run_human_gate(ctx, auto_approve)
        if approved:
            self._run_execution_layer(ctx)
        else:
            audit.emit(
                layer="L6",
                event="layer_skipped",
                run_id=ctx.run_id,
                symbol=symbol,
                message="not_approved",
                data={
                    "risk_approved": ctx.risk_verdict.approved if ctx.risk_verdict else None,
                },
            )

        audit.emit(
            layer="orch",
            event="phase_done",
            run_id=ctx.run_id,
            symbol=symbol,
            message="pipeline_done",
            data={
                "approved": approved,
                "action": ctx.ai_decision.action.value if ctx.ai_decision else None,
                "execution": ctx.execution_result.status if ctx.execution_result else "none",
            },
        )
        logger.info("pipeline done run_id=%s approved=%s", ctx.run_id, approved)
        return ctx

    def _run_data_layer(self, ctx: PipelineContext) -> None:
        ctx.market = self._source.fetch_market(ctx.symbol)
        _record_layer(
            ctx,
            LayerId.L1_DATA,
            LayerStatus.OK,
            "unified_market",
            data={
                "price": ctx.market.price if ctx.market else None,
                "asset_type": ctx.market.extra.get("asset_type") if ctx.market else None,
            },
        )

    def _run_intelligence_layer(self, ctx: PipelineContext) -> None:
        cached = ctx.intel_cache.get(ctx.symbol)
        if cached is not None and _intel_cache_is_fresh(cached):
            ctx.sentiment = cached
            msg = "intel_cache"
        else:
            if cached is not None:
                logger.info(
                    "intel_cache_stale symbol=%s max_age_min=%s",
                    ctx.symbol,
                    settings.intel_cache_max_age_min,
                )
            ctx.sentiment = self._intelligence.analyze(ctx.symbol, ctx.market)  # type: ignore[arg-type]
            ctx.intel_cache[ctx.symbol] = ctx.sentiment
            msg = "osint_collect"
        _record_layer(
            ctx,
            LayerId.L2_INTELLIGENCE,
            LayerStatus.OK,
            msg,
            data={
                "source": msg,
                "composite": round(ctx.sentiment.composite, 4) if ctx.sentiment else None,
            },
        )

    def _run_signal_layer(self, ctx: PipelineContext) -> None:
        ctx.signal = self._signal_gen.generate(
            ctx.symbol, ctx.market, ctx.sentiment  # type: ignore[arg-type]
        )
        _record_layer(
            ctx,
            LayerId.L3_SIGNALS,
            LayerStatus.OK,
            "math_alpha_fusion",
            data={
                "direction": ctx.signal.direction.value if ctx.signal else None,
                "opportunity": round(ctx.signal.opportunity, 4) if ctx.signal else None,
                "quality": (
                    round(ctx.signal.quality, 4)
                    if ctx.signal and ctx.signal.quality is not None
                    else None
                ),
            },
        )

    def _run_strategy_layer(self, ctx: PipelineContext) -> None:
        ctx.context_pack = self._strategy.build_context_pack(ctx)
        _record_layer(
            ctx,
            LayerId.L4_STRATEGY,
            LayerStatus.OK,
            "policy_pack",
            data={"has_context_pack": ctx.context_pack is not None},
        )

    def _run_policy_finalize(self, ctx: PipelineContext) -> None:
        """L5 enrich 后定稿 PolicyVerdict（唯一纪律出口）。"""
        verdict = self._strategy.evaluate_policy(ctx)
        logger.info(
            "policy_verdict symbol=%s sleeve=%s action=%s eligible=%s",
            ctx.symbol,
            verdict.sleeve.value,
            verdict.action.value,
            verdict.entry_eligible,
        )

    def _attach_linkage_meta(self, ctx: PipelineContext):
        """将监控告警与因子健康度注入 Context Pack。"""
        pack = ctx.context_pack
        if pack is None:
            return None
        alert_msgs = [
            f"{alert.level}: {alert.message}"
            for alert in ctx.monitor_alerts
            if alert.symbol == ctx.symbol
        ]
        fh = ctx.factor_health
        return replace(
            pack,
            monitor_alert_messages=alert_msgs,
            factor_degraded_count=fh.degraded_count if fh else 0,
            factor_disabled_count=fh.disabled_count if fh else 0,
            factor_active_count=fh.active_count if fh else 0,
            factor_usable_count=fh.usable_count if fh else 0,
            factor_coverage=fh.coverage if fh else 0.0,
        )

    def _apply_entry_gate(self, ctx: PipelineContext) -> None:
        """仅消费 PolicyVerdict；无 verdict 硬失败，不做双源 fallback。"""
        if ctx.evaluation_mode != EvaluationMode.ENTRY.value:
            return
        from quant_shell.common.exceptions import BusinessError

        verdict = ctx.policy_verdict
        if verdict is None:
            raise BusinessError(
                message="entry 门控缺少 policy_verdict",
                suggestion="确保 _run_policy_finalize 已执行",
            )
        if verdict.sleeve == TradeSleeve.BLOCKED or verdict.action == Action.WAIT:
            reason = (
                verdict.block_reason_text()
                or verdict.sleeve_reason
                or "不满足入场条件"
            )
            ctx.ai_decision = AIDecision(
                action=Action.WAIT,
                confidence=0.0,
                reasoning_chain=[f"策略政策: {reason}"],
                risk_flags=["POLICY_ENTRY_BLOCK", f"sleeve:{verdict.sleeve.value}"],
                # 机会/袖套未达标不是「需人审」；决策板仍因 WAIT 展示人工覆盖表单
                human_review_required=False,
            )

    def _run_risk_enrich_layer(self, ctx: PipelineContext) -> None:
        """L5 指标增强（在 AI 推理前填充真实 Sharpe/回撤）。"""
        self._risk_enricher.enrich(ctx)
        ctx.context_pack = self._attach_linkage_meta(ctx)
        _record_layer(
            ctx,
            LayerId.L5_RISK,
            LayerStatus.OK,
            "metrics_ic_enrich",
            data={
                "sharpe": round(ctx.context_pack.risk_metrics.sharpe_ratio, 4)
                if ctx.context_pack
                else None,
                "factor_usable": ctx.factor_health.usable_count if ctx.factor_health else 0,
                "factor_coverage": ctx.factor_health.coverage if ctx.factor_health else 0.0,
            },
        )

    def _run_ai_reason_layer(self, ctx: PipelineContext) -> None:
        if ctx.ai_decision is not None:
            return
        from quant_shell.common.exceptions import BusinessError

        verdict = ctx.policy_verdict
        if verdict is None:
            raise BusinessError(
                message="AI 推理缺少 policy_verdict",
                suggestion="确保 _run_policy_finalize 已执行",
            )
        signal_opp = abs(float(ctx.signal.opportunity)) if ctx.signal else 0.0
        narrated = None
        l7_msg = "policy_verdict"
        if not verdict.rule_resolved:
            narrated = self._human_gate.reason(ctx.context_pack)  # type: ignore[arg-type]
            l7_msg = (
                "llm_reason"
                if isinstance(self._human_gate, LlmHumanReviewGate)
                else "sim_signal_reason"
            )
        ctx.ai_decision = self._commit(
            verdict,
            narrated,
            ctx.context_pack,
            evaluation_mode=ctx.evaluation_mode,
            signal_confidence=signal_opp,
        )
        _record_layer(
            ctx,
            LayerId.L7_AI_REASON,
            LayerStatus.OK,
            l7_msg,
            data={
                "gate": l7_msg,
                "action": ctx.ai_decision.action.value if ctx.ai_decision else None,
            },
        )

    def _run_risk_gate_layer(self, ctx: PipelineContext) -> None:
        proposed = ctx.ai_decision.action.value if ctx.ai_decision else Action.HOLD.value
        ctx.risk_verdict = self.risk.evaluate(ctx, proposed)
        _record_layer(
            ctx,
            LayerId.L5_RISK,
            LayerStatus.OK,
            "hard_gate",
            data={
                "proposed": proposed,
                "approved": ctx.risk_verdict.approved,
                "violations": [v.value for v in ctx.risk_verdict.violations],
            },
        )

    def _run_human_gate(self, ctx: PipelineContext, auto_approve: bool) -> bool:
        approved = bool(
            ctx.risk_verdict
            and ctx.risk_verdict.approved
            and ctx.ai_decision
            and self._human_gate.confirm(ctx.ai_decision, auto_approve=auto_approve)
        )
        status = LayerStatus.OK if approved else LayerStatus.BLOCKED
        _record_layer(
            ctx,
            LayerId.L7_HUMAN,
            status,
            "" if approved else "not_approved",
            data={"approved": approved, "auto_approve": auto_approve},
        )
        return approved

    def _run_execution_layer(self, ctx: PipelineContext) -> None:
        if not ctx.ai_decision or ctx.ai_decision.action not in _EXECUTABLE_ACTIONS:
            return
        from quant_shell.common.exceptions import BusinessError

        if ctx.policy_verdict is None:
            raise BusinessError(
                message="执行层缺少 policy_verdict",
                suggestion="确保 _run_policy_finalize 已执行",
            )
        price = ctx.market.price if ctx.market else 0.0
        sleeve = ctx.policy_verdict.sleeve.value
        pos_pct = ctx.risk_verdict.max_allowed_position  # type: ignore[union-attr]
        if ctx.ai_decision.action == Action.BUY:
            caps = [pos_pct]
            if ctx.policy_verdict.max_position > 0:
                caps.append(ctx.policy_verdict.max_position)
            if ctx.ai_decision.suggested_position_change > 0:
                caps.append(ctx.ai_decision.suggested_position_change)
            pos_pct = min(caps)
        ctx.order = OrderRequest(
            symbol=ctx.symbol,
            action=ctx.ai_decision.action,
            quantity=0.0,
            position_pct=pos_pct,
            reason="; ".join(ctx.ai_decision.reasoning_chain),
            fill_price=price,
            sleeve=sleeve,
        )
        if isinstance(self._execution, PaperTradingEngine):
            ctx.execution_result = self._execution.execute(
                ctx.order,
                evaluation_mode=ctx.evaluation_mode,
                unrealized_pnl_pct=(
                    ctx.context_pack.risk_state.unrealized_pnl_pct
                    if ctx.context_pack
                    else 0.0
                ),
            )
        else:
            ctx.execution_result = self._execution.execute(ctx.order)
        if isinstance(self._execution, PaperTradingEngine):
            ctx.paper_portfolio = self._execution.get_portfolio()
        _record_layer(
            ctx,
            LayerId.L6_EXECUTION,
            LayerStatus.SIMULATED,
            data={
                "status": ctx.execution_result.status if ctx.execution_result else "skipped",
            },
        )
