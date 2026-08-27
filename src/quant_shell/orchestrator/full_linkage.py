"""全链路联动编排 — 情报 + ETF/个股七层模拟盘 + 持仓重评。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from quant_shell.common import audit
from quant_shell.common.atomic_io import append_text, write_text_atomic
from quant_shell.common.constants import EvaluationMode, LayerId, LayerStatus
from quant_shell.common.exceptions import DataFetchError, QuantSystemError, ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.common.retry import call_with_retry
from quant_shell.common.types import (
    Action,
    AIDecision,
    FullLinkageResult,
    LayerResult,
    MonitorAlert,
    PipelineContext,
    SentimentFactors,
)
from quant_shell.config.settings import settings
from quant_shell.data.live_price import refresh_live_spot_caches
from quant_shell.data.ohlcv_cache import consume_ohlcv_session_lag_hits
from quant_shell.intelligence.collector import clear_global_intel_cache
from quant_shell.intelligence.monitor.service import IntelligenceMonitor
from quant_shell.orchestrator.constants import DEFAULT_PICK_TOP_N
from quant_shell.orchestrator.layer4 import Layer4Service
from quant_shell.execution.portfolio import PaperPortfolioStore
from quant_shell.orchestrator.paper_pipeline import PaperTradingPipeline
from quant_shell.orchestrator.progress import LinkageProgress
from quant_shell.orchestrator.reentry import entry_block_set

logger = get_logger(__name__)

_LINKAGE_DIR = Path("data/linkage")
_EQUITY_HISTORY_PATH = Path("data/paper/equity_history.jsonl")
_ISOLATED = (QuantSystemError, OSError)
# 记入 phase_errors 且令 CLI/Desk job 非 0 退出；INTEL_SOURCE_FAIL 等为软降级
HARD_PHASE_ERROR_CODES = frozenset(
    {
        "PIPELINE_ERROR",
        "SPOT_PREFETCH",
        "OHLCV_SESSION_LAG",
    }
)


def is_desk_archive_run(symbols: list[str] | None) -> bool:
    """Desk 报告目录只收日常全量跑；`--symbol`/`--symbols` 调试不归档。"""
    return symbols is None


class FullLinkageOrchestrator:
    """串联 L2 监控 → ETF 七层 → 持仓重评 → 选股 → 个股入场七层。"""

    def __init__(
        self,
        pipeline: PaperTradingPipeline | None = None,
        layer4: Layer4Service | None = None,
        intel_monitor_factory: type[IntelligenceMonitor] | None = None,
        portfolio_store: PaperPortfolioStore | None = None,
    ) -> None:
        self._portfolio_store = portfolio_store or PaperPortfolioStore()
        self._pipeline = pipeline or PaperTradingPipeline.create_integrated(
            portfolio_store=self._portfolio_store,
        )
        self._layer4 = layer4 or self._pipeline.layer4
        self._intel_monitor_cls = intel_monitor_factory or IntelligenceMonitor
        self._etf_symbols = settings.monitor_symbol_list or [settings.default_symbol]

    def run(
        self,
        *,
        symbols: list[str] | None = None,
        auto_approve: bool | None = None,
        run_intel: bool = True,
        run_stock_pick: bool = True,
        run_hold_review: bool | None = None,
    ) -> FullLinkageResult:
        """执行一轮全链路联动。"""
        run_id = str(uuid.uuid4())[:8]
        now = datetime.now()
        audit.reset()
        audit.bind(run_id=run_id)
        sym_list = symbols or self._etf_symbols
        approve = settings.paper_auto_approve if auto_approve is None else auto_approve
        do_hold = (
            settings.linkage_reeval_holdings
            if run_hold_review is None
            else run_hold_review
        )

        audit.emit(
            layer="orch",
            event="phase_start",
            run_id=run_id,
            message="linkage_start",
            data={
                "etf_symbols": sym_list,
                "run_intel": run_intel,
                "run_stock_pick": run_stock_pick,
                "run_hold_review": do_hold,
            },
        )

        intel_cache: dict[str, SentimentFactors] = {}
        alerts: list[MonitorAlert] = []
        stock_intel_symbols: list[str] = []
        phase_errors: list[dict[str, str]] = []
        held = list(self._portfolio_store.load().positions.keys()) if do_hold else []
        # 丢弃同进程残留滞后标记，避免污染本趟硬错误判定
        consume_ohlcv_session_lag_hits()

        plan: list[tuple[str, str, int]] = []
        if run_intel:
            plan.append(("intel", "情报", 1))
        plan.append(("etf", "ETF入场", max(1, len(sym_list))))
        if do_hold:
            plan.append(("hold", "持仓重评", max(1, len(held))))
        if run_stock_pick:
            plan.append(("pick", "截面选股", 1))
            plan.append(("stock", "个股入场", settings.linkage_stock_top_n))
        prog = LinkageProgress.from_plan(plan)
        prog.begin()

        try:
            call_with_retry(
                lambda: refresh_live_spot_caches(etfs=True),
                layer="L1",
                op="spot_prefetch",
            )
        except (DataFetchError, ValidationError, OSError) as exc:
            audit.emit(
                layer="L1",
                event="layer_error",
                severity="ERROR",
                run_id=run_id,
                error_code="SPOT_PREFETCH",
                message=str(exc),
            )
            phase_errors.append(_phase_error("prefetch", "*", exc, "SPOT_PREFETCH"))

        etf_runs: list[PipelineContext] = []
        hold_runs: list[PipelineContext] = []
        stock_runs: list[PipelineContext] = []
        stock_pick = None
        aborted: BaseException | None = None
        try:
            clear_global_intel_cache()
            if run_intel:
                intel_symbols = list(dict.fromkeys([*sym_list, *held]))
                with prog.phase("intel") as p:
                    try:
                        intel_cache, alerts, intel_fails = call_with_retry(
                            lambda: self._run_intel(intel_symbols),
                            layer="orch",
                            op="intel",
                        )
                        for fail in intel_fails:
                            phase_errors.append(
                                {
                                    "phase": "intel",
                                    "symbol": fail.get("symbol") or "*",
                                    "error": (
                                        f"{fail.get('source', 'source')}: "
                                        f"{fail.get('error', '')}"
                                    ),
                                    "error_code": "INTEL_SOURCE_FAIL",
                                }
                            )
                        p.tick(f"{len(intel_symbols)}票")
                    except _ISOLATED as exc:
                        _record_phase_error(phase_errors, "intel", "*", exc, run_id)
                        p.tick("失败")
                audit.emit(
                    layer="orch",
                    event="intel_done",
                    run_id=run_id,
                    data={
                        "symbols": intel_symbols,
                        "alerts": len(alerts),
                        "cached": len(intel_cache),
                    },
                )

            with prog.phase("etf", units=max(1, len(sym_list))) as p:
                for symbol in sym_list:
                    ctx = self._safe_pipeline_run(
                        symbol,
                        phase="etf",
                        auto_approve=approve,
                        intel_cache=intel_cache,
                        monitor_alerts=alerts,
                        evaluation_mode=EvaluationMode.ENTRY.value,
                        phase_errors=phase_errors,
                    )
                    etf_runs.append(ctx)
                    p.tick(symbol)

            if do_hold:
                held = list(self._portfolio_store.load().positions.keys())
                with prog.phase("hold", units=max(1, len(held))) as p:
                    for symbol in held:
                        ctx = self._safe_pipeline_run(
                            symbol,
                            phase="hold",
                            auto_approve=approve,
                            intel_cache=intel_cache,
                            monitor_alerts=alerts,
                            evaluation_mode=EvaluationMode.HOLD.value,
                            phase_errors=phase_errors,
                        )
                        hold_runs.append(ctx)
                        p.tick(symbol)

            if run_stock_pick:
                with prog.phase("pick") as p:
                    try:
                        stock_pick = call_with_retry(
                            lambda: self._layer4.pick_stocks(
                                universe=settings.pick_universe,
                                max_symbols=settings.pick_max_symbols_resolved,
                                top_n=DEFAULT_PICK_TOP_N,
                            ),
                            layer="orch",
                            op="pick",
                        )
                        p.tick(stock_pick.universe)
                    except _ISOLATED as exc:
                        _record_phase_error(phase_errors, "pick", "*", exc, run_id)
                        p.tick("失败")
                if stock_pick is not None:
                    held_set = set(self._portfolio_store.load().positions.keys())
                    blocked = entry_block_set(hold_runs, held_set=held_set)
                    top_picks = [
                        p
                        for p in stock_pick.picks[: settings.linkage_stock_top_n]
                        if p.symbol not in blocked
                    ]
                    stock_intel_symbols = [p.symbol for p in top_picks]

                    if (
                        run_intel
                        and settings.linkage_intel_prefetch_stocks
                        and stock_intel_symbols
                    ):
                        try:
                            stock_cache, stock_alerts, stock_fails = call_with_retry(
                                lambda: self._run_intel(stock_intel_symbols),
                                layer="orch",
                                op="stock_intel",
                            )
                            intel_cache.update(stock_cache)
                            alerts = self._merge_alerts(alerts, stock_alerts)
                            for fail in stock_fails:
                                phase_errors.append(
                                    {
                                        "phase": "stock_intel",
                                        "symbol": fail.get("symbol") or "*",
                                        "error": (
                                            f"{fail.get('source', 'source')}: "
                                            f"{fail.get('error', '')}"
                                        ),
                                        "error_code": "INTEL_SOURCE_FAIL",
                                    }
                                )
                        except _ISOLATED as exc:
                            _record_phase_error(
                                phase_errors, "stock_intel", "*", exc, run_id
                            )

                    with prog.phase("stock", units=max(1, len(top_picks) or 1)) as p:
                        for pick in top_picks:
                            ctx = self._safe_pipeline_run(
                                pick.symbol,
                                phase="stock",
                                auto_approve=approve,
                                intel_cache=intel_cache,
                                monitor_alerts=alerts,
                                evaluation_mode=EvaluationMode.ENTRY.value,
                                entry_eligible=pick.entry_eligible,
                                entry_block_reason=pick.entry_block_reason,
                                phase_errors=phase_errors,
                            )
                            stock_runs.append(ctx)
                            p.tick(pick.symbol)
        except (KeyboardInterrupt, SystemExit) as exc:
            aborted = exc

        prog.finish()
        _append_ohlcv_session_lag_errors(phase_errors, run_id)
        result = FullLinkageResult(
            run_id=run_id,
            timestamp=now,
            etf_runs=etf_runs,
            hold_runs=hold_runs,
            stock_runs=stock_runs,
            stock_pick=stock_pick,
            monitor_alerts=alerts,
            stock_intel_symbols=stock_intel_symbols,
            intel_ran=bool(run_intel),
            phase_errors=phase_errors,
        )
        try:
            result.summary_path = str(
                call_with_retry(
                    lambda: self._persist_summary(
                        result, archive_report=is_desk_archive_run(symbols)
                    ),
                    layer="orch",
                    op="persist",
                )
            )
        except (QuantSystemError, OSError) as exc:
            _record_phase_error(result.phase_errors, "persist", "*", exc, run_id)
        audit.emit(
            layer="orch",
            event="phase_done",
            run_id=run_id,
            message="linkage_done",
            data={
                "etf_runs": len(etf_runs),
                "hold_runs": len(hold_runs),
                "stock_runs": len(stock_runs),
                "phase_errors": len(result.phase_errors),
            },
        )
        logger.info(
            "linkage done run_id=%s etf=%d hold=%d stock=%d errors=%d report=%s",
            run_id,
            len(etf_runs),
            len(hold_runs),
            len(stock_runs),
            len(result.phase_errors),
            result.report_path or "-",
        )
        if aborted is not None:
            raise aborted
        return result

    def _run_intel(
        self, symbols: list[str]
    ) -> tuple[dict[str, SentimentFactors], list[MonitorAlert], list[dict[str, str]]]:
        """对指定标的批量采集情报。"""
        if not symbols:
            return {}, [], []
        monitor = self._intel_monitor_cls(symbols=symbols)
        run = monitor.run_once()
        alerts = [
            MonitorAlert(symbol=a.symbol, level=a.level, message=a.message)
            for a in run.alerts
        ]
        failures = getattr(run, "intel_source_failures", [])
        if not isinstance(failures, list):
            failures = []
        logger.info(
            "linkage intel symbols=%d alerts=%d source_fail=%d",
            len(run.results),
            len(alerts),
            len(failures),
        )
        return run.results, alerts, failures

    def _safe_pipeline_run(
        self,
        symbol: str,
        *,
        phase: str,
        auto_approve: bool,
        intel_cache: dict[str, SentimentFactors],
        monitor_alerts: list[MonitorAlert],
        evaluation_mode: str,
        phase_errors: list[dict[str, str]],
        entry_eligible: bool = True,
        entry_block_reason: str = "",
    ) -> PipelineContext:
        """单票偶发错误先重试一次；仍失败则记 phase_errors。其它异常冒泡。"""
        try:
            return call_with_retry(
                lambda: self._pipeline.run(
                    symbol,
                    auto_approve=auto_approve,
                    intel_cache=intel_cache,
                    monitor_alerts=monitor_alerts,
                    evaluation_mode=evaluation_mode,
                    entry_eligible=entry_eligible,
                    entry_block_reason=entry_block_reason,
                ),
                layer="orch",
                op=phase,
                symbol=symbol,
            )
        except _ISOLATED as exc:
            rid = audit.current_run_id()
            _record_phase_error(phase_errors, phase, symbol, exc, rid)
            return _failed_pipeline_ctx(
                symbol,
                evaluation_mode,
                exc,
                intel_cache=intel_cache,
                run_id=rid,
            )

    @staticmethod
    def _merge_alerts(
        existing: list[MonitorAlert], new: list[MonitorAlert]
    ) -> list[MonitorAlert]:
        """合并告警，同 symbol+level+message 去重。"""
        seen = {(a.symbol, a.level, a.message) for a in existing}
        merged = list(existing)
        for alert in new:
            key = (alert.symbol, alert.level, alert.message)
            if key not in seen:
                merged.append(alert)
                seen.add(key)
        return merged

    def _persist_summary(
        self, result: FullLinkageResult, *, archive_report: bool
    ) -> Path:
        from quant_shell.orchestrator.linkage_report import (
            build_and_write_linkage_report,
            payload_from_result,
        )

        _LINKAGE_DIR.mkdir(parents=True, exist_ok=True)
        payload = payload_from_result(result)
        path = _LINKAGE_DIR / "latest.json"
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        write_text_atomic(path, text)
        archive = _LINKAGE_DIR / f"{result.timestamp:%Y%m%d_%H%M%S}_{result.run_id}.json"
        write_text_atomic(archive, text)
        equity_ok, equity_snapshot = self._append_equity_history(result.run_id)
        result.equity_ok = equity_ok
        result.equity_snapshot = equity_snapshot
        if archive_report:
            report_path = build_and_write_linkage_report(
                payload,
                equity_snapshot=equity_snapshot,
                equity_ok=equity_ok,
            )
            result.report_path = str(report_path)
        else:
            result.report_path = ""
            logger.info("skip desk report archive run_id=%s (scoped debug)", result.run_id)
        return path

    def _append_equity_history(
        self, run_id: str
    ) -> tuple[bool, dict[str, float | str] | None]:
        """追加权益快照；失败返回 equity_ok=False（不吞成成功）。"""
        from quant_shell.execution.mark_prices import mark_portfolio_prices

        attempt = {"n": 0}

        def _once() -> tuple[bool, dict[str, float | str] | None]:
            attempt["n"] += 1
            force = True if attempt["n"] > 1 else None
            portfolio = self._portfolio_store.load()
            marked = mark_portfolio_prices(
                portfolio, prefer={}, fetch_live=True, force_refresh=force
            )
            if marked.missing:
                raise DataFetchError(
                    message=f"equity mark missing {marked.missing}",
                    suggestion="刷新 TTL 现价后重试",
                )
            equity = portfolio.mark_equity(marked.prices)
            position_value = max(0.0, equity - portfolio.cash)
            hist_path = _EQUITY_HISTORY_PATH
            row: dict[str, float | str] = {
                "timestamp": datetime.now().isoformat(),
                "run_id": run_id,
                "equity": round(float(equity), 2),
                "cash": round(float(portfolio.cash), 2),
                "position_value": round(float(position_value), 2),
            }
            append_text(hist_path, json.dumps(row, ensure_ascii=False))
            return True, row

        try:
            return call_with_retry(
                _once, layer="store", op="equity_history"
            )
        except (OSError, DataFetchError, ValidationError, ValueError, TypeError, KeyError) as exc:
            audit.emit(
                layer="store",
                event="layer_error",
                severity="ERROR",
                run_id=run_id,
                error_code="EQUITY_HISTORY",
                message=str(exc),
            )
            return False, None


def _record_phase_error(
    phase_errors: list[dict[str, str]],
    phase: str,
    symbol: str,
    exc: BaseException,
    run_id: str,
    error_code: str = "",
) -> None:
    code = error_code or (
        "PIPELINE_ERROR" if symbol != "*" else phase.upper()
    )
    audit.emit(
        layer="orch",
        event="layer_error",
        severity="ERROR",
        run_id=run_id,
        symbol="" if symbol == "*" else symbol,
        error_code=code,
        message=f"{phase} {symbol}: {type(exc).__name__}: {exc}",
    )
    phase_errors.append(_phase_error(phase, symbol, exc, code))


def _phase_error(
    phase: str,
    symbol: str,
    exc: BaseException,
    error_code: str = "PIPELINE_ERROR",
) -> dict[str, str]:
    return {
        "phase": phase,
        "symbol": symbol,
        "error": f"{type(exc).__name__}: {exc}",
        "error_code": error_code,
    }


def _failed_pipeline_ctx(
    symbol: str,
    evaluation_mode: str,
    exc: BaseException,
    *,
    intel_cache: dict[str, SentimentFactors] | None = None,
    run_id: str = "",
) -> PipelineContext:
    """单票失败占位：WAIT + PIPELINE_ERROR；已采集情报不得丢掉。"""
    cache = intel_cache or {}
    ctx = PipelineContext(
        symbol=symbol,
        run_id=run_id or audit.current_run_id() or "failed",
        evaluation_mode=evaluation_mode,
        intel_cache=cache,
        sentiment=cache.get(symbol),
    )
    msg = f"{type(exc).__name__}: {exc}"[:240]
    ctx.audit_trail.append(LayerResult(LayerId.L1_DATA, LayerStatus.ERROR, msg))
    ctx.ai_decision = AIDecision(
        action=Action.WAIT,
        confidence=0.0,
        reasoning_chain=[f"PIPELINE_ERROR: {msg}"],
        risk_flags=["PIPELINE_ERROR"],
        human_review_required=True,
    )
    return ctx


def hard_phase_errors(
    phase_errors: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """硬错误子集 — CLI/Desk 据此非 0 退出。"""
    return [
        e
        for e in (phase_errors or [])
        if str(e.get("error_code") or "") in HARD_PHASE_ERROR_CODES
    ]


def linkage_has_hard_errors(result: FullLinkageResult) -> bool:
    return bool(hard_phase_errors(result.phase_errors))


def _append_ohlcv_session_lag_errors(
    phase_errors: list[dict[str, str]],
    run_id: str,
) -> None:
    hits = consume_ohlcv_session_lag_hits()
    if not hits:
        return
    from quant_shell.data.market_session import is_ohlcv_session_lag_hard

    sample = ",".join(hits[:8])
    more = f" 等共{len(hits)}标的" if len(hits) > 8 else f"（{len(hits)}标的）"
    hard = is_ohlcv_session_lag_hard()
    code = "OHLCV_SESSION_LAG" if hard else "OHLCV_SESSION_LAG_SOFT"
    msg = (
        f"收盘后日 K 未覆盖应完成交易日{more}；例: {sample}"
        + ("" if hard else "（宽限内软降级，过 OHLCV_LAG_HARD_AFTER 后硬失败）")
    )
    audit.emit(
        layer="L1",
        event="layer_error",
        severity="ERROR" if hard else "WARN",
        run_id=run_id,
        error_code=code,
        message=msg,
        data={"symbols": hits[:50], "count": len(hits), "hard": hard},
    )
    phase_errors.append(
        {
            "phase": "ohlcv",
            "symbol": "*",
            "error": msg,
            "error_code": code,
        }
    )


def format_linkage_summary(result: FullLinkageResult) -> str:
    """人类可读联动摘要 — 委托唯一报告模块。"""
    from quant_shell.orchestrator.linkage_report import (
        build_linkage_report,
        payload_from_result,
        render_linkage_report_markdown,
    )

    payload = payload_from_result(result)
    report = build_linkage_report(
        payload,
        equity_snapshot=result.equity_snapshot,
        equity_ok=bool(result.equity_ok),
    )
    text = render_linkage_report_markdown(report)
    if result.summary_path:
        text += f"\n已保存 linkage: {result.summary_path}"
    if result.report_path:
        text += f"\n已保存 report: {result.report_path}"
    return text
