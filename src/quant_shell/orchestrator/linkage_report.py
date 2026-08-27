"""交易龙联动报告 — 唯一叙事组装点（含决策依据与情报来源）。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from quant_shell.common.atomic_io import write_text_atomic
from quant_shell.common.logging_config import get_logger
from quant_shell.common.hard_codes import is_hard_code
from quant_shell.config.env_loader import project_root

logger = get_logger(__name__)

_KEY_EVENTS_CAP = 5
_SCHEMA_VERSION = "1.0"

TAB_KEYS: tuple[tuple[str, str], ...] = (
    ("etf_runs", "etf"),
    ("hold_runs", "hold"),
    ("stock_runs", "stock"),
)


def report_dir() -> Path:
    return project_root() / "data" / "reports" / "linkage"


def report_artifact_path(run_id: str | None, suffix: str) -> Path:
    name = f"{run_id}{suffix}" if run_id else f"latest{suffix}"
    return report_dir() / name


def latest_report_path() -> Path:
    return report_artifact_path(None, ".json")


def report_path_for_run(run_id: str) -> Path:
    return report_artifact_path(run_id, ".json")


def require_report_artifact(run_id: str | None, suffix: str) -> Path:
    path = report_artifact_path(run_id, suffix)
    if not path.is_file():
        raise FileNotFoundError(f"report not found: {path.name}")
    return path


def _read_json_dict(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("linkage_report json fail path=%s err=%s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def build_linkage_report(
    linkage: dict[str, Any],
    *,
    equity_snapshot: dict[str, Any] | None = None,
    equity_ok: bool = True,
) -> dict[str, Any]:
    """从 linkage payload 组装冻结 schema 报告（不做二次 L2）。"""
    run_id = str(linkage.get("run_id") or "")
    generated_at = str(linkage.get("timestamp") or "")
    alerts = list(linkage.get("alerts") or [])
    stock_intel = [str(s) for s in (linkage.get("stock_intel_symbols") or [])]
    intel_ran = bool(linkage.get("intel_ran", True))

    actions: list[dict[str, Any]] = []
    holdings_health: list[dict[str, Any]] = []
    action_counter: Counter[str] = Counter()
    factor_bits: list[str] = []
    name_map = {
        str(p.get("symbol") or "").zfill(6): str(p.get("name") or "")
        for p in ((linkage.get("stock_pick") or {}).get("picks") or [])
        if isinstance(p, dict)
    }

    for key, tab in TAB_KEYS:
        for row in linkage.get(key) or []:
            if not isinstance(row, dict):
                continue
            item = _action_item(row, tab=tab, alerts=alerts, intel_ran=intel_ran)
            sym = str(item.get("symbol") or "")
            if not item.get("name") and sym in name_map:
                item["name"] = name_map[sym]
            actions.append(item)
            action_counter[str(item.get("trade_action") or "HOLD")] += 1
            if tab == "hold":
                holdings_health.append(
                    {
                        "symbol": item["symbol"],
                        "unrealized_pnl_pct": row.get("unrealized_pnl_pct"),
                        "trade_sleeve": item.get("trade_sleeve"),
                        "decision_logic": item.get("decision_logic"),
                    }
                )
            if row.get("factor_active") is not None:
                factor_bits.append(
                    f"{row.get('symbol')}:active={row.get('factor_active')}"
                    f"/usable={row.get('factor_usable')}"
                    f"/cov={row.get('factor_coverage')}"
                )

    covered = sorted(
        {
            str(a.get("symbol") or "")
            for a in alerts
            if isinstance(a, dict) and a.get("symbol")
        }
        | set(stock_intel)
    )

    report: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "action_summary": {
            "BUY": int(action_counter.get("BUY", 0)),
            "REDUCE": int(action_counter.get("REDUCE", 0)),
            "EXIT": int(action_counter.get("EXIT", 0)),
            "SELL": int(action_counter.get("SELL", 0)),
            "HOLD": int(action_counter.get("HOLD", 0)),
            "WAIT": int(action_counter.get("WAIT", 0)),
            "total": len(actions),
        },
        "factor_health": _factor_health_blurb(actions),
        "equity_ok": bool(equity_ok),
        "equity_snapshot": equity_snapshot if equity_ok else None,
        "intel_overview": {
            "intel_ran": intel_ran,
            "source_hint": "L2 monitor/analyst" if intel_ran else "skipped_intel",
            "alert_count": len(alerts),
            "stock_intel_symbols": stock_intel,
            "symbols_covered": covered,
        },
        "alerts": [
            {
                "symbol": str(a.get("symbol") or ""),
                "level": str(a.get("level") or ""),
                "message": str(a.get("message") or "")[:200],
            }
            for a in alerts
            if isinstance(a, dict)
        ],
        "actions": actions,
        "holdings_health": holdings_health,
        "stock_pick": linkage.get("stock_pick") or {},
        "phase_errors": list(linkage.get("phase_errors") or []),
        "audit_error_codes": list(linkage.get("audit_error_codes") or []),
    }
    return report


def render_linkage_report_markdown(report: dict[str, Any]) -> str:
    """晨报备忘录 Markdown（结论先行，客户可读）。"""
    from quant_shell.orchestrator.linkage_report_brief import (
        action_blurb,
        evidence_lines,
        headline_sentence,
        one_line_rest,
        split_action_buckets,
    )

    need, watch, rest = split_action_buckets(list(report.get("actions") or []))
    summary = report.get("action_summary") or {}
    lines = [
        f"# 模拟盘晨报 · {report.get('generated_at')}",
        f"run `{report.get('run_id')}`",
        "",
        "## 今日一句话",
        "",
        f"> {headline_sentence(report)}",
        "",
        "| 要动手 | 可稍后看 |",
        "|--------|----------|",
        (
            f"| BUY {int(summary.get('BUY') or 0)} · "
            f"REDUCE {int(summary.get('REDUCE') or 0)} · "
            f"EXIT/SELL {int(summary.get('EXIT') or 0) + int(summary.get('SELL') or 0)} | "
            f"WAIT {int(summary.get('WAIT') or 0)} |"
        ),
    ]
    if report.get("equity_ok") and report.get("equity_snapshot"):
        eq = report["equity_snapshot"]
        lines.append("")
        lines.append(
            f"权益 **{eq.get('equity')}**（现金 {eq.get('cash')} / "
            f"持仓市值 {eq.get('position_value')}）"
        )
    lines.append(f"因子：{report.get('factor_health')}")

    lines.extend(["", "## 需要动手", ""])
    if not need:
        lines.append("_本轮没有必须动手的买卖。_")
    for item in need:
        lines.append(f"### {action_blurb(item)}")
        lines.append("")
        lines.append("<details><summary>依据</summary>")
        lines.append("")
        for ev in evidence_lines(item):
            lines.append(f"- {ev}")
        intel = item.get("intel") or {}
        if intel.get("analyst_summary"):
            lines.append(f"- 情报：{intel.get('analyst_summary')}")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if watch:
        lines.extend(["## 差一点 / 被硬拦", ""])
        for item in watch:
            lines.append(f"### {action_blurb(item)}")
            lines.append("")
            lines.append("<details><summary>依据</summary>")
            lines.append("")
            for ev in evidence_lines(item):
                lines.append(f"- {ev}")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    if rest:
        lines.extend(["## 其余观望", "", "| 标的 | 一句话 |", "|------|--------|"])
        for item in rest:
            lines.append(f"| {item.get('symbol')} | {one_line_rest(item)} |")

    intel = report.get("intel_overview") or {}
    lines.extend(
        [
            "",
            "## 页脚",
            "",
            f"情报：{'已采集' if intel.get('intel_ran') else '未采集'} · "
            f"告警 {intel.get('alert_count')} · "
            f"预采集 {', '.join(intel.get('stock_intel_symbols') or []) or '无'}",
            "",
            "仅供模拟盘参考，不构成投资建议。",
        ]
    )
    errors = report.get("phase_errors") or []
    if errors:
        lines.extend(["", "## 阶段错误", ""])
        for err in errors[:20]:
            lines.append(
                f"- [{err.get('phase')}] {err.get('symbol')}: {err.get('error')}"
            )
    return "\n".join(lines)


def build_and_write_linkage_report(
    linkage: dict[str, Any],
    *,
    equity_snapshot: dict[str, Any] | None = None,
    equity_ok: bool = True,
) -> Path:
    """组装并写入 latest + run_id 归档（JSON + Markdown + HTML + PDF）。"""
    from quant_shell.orchestrator.linkage_report_pdf import (
        write_linkage_report_html,
        write_linkage_report_pdf,
    )

    report = build_linkage_report(
        linkage, equity_snapshot=equity_snapshot, equity_ok=equity_ok
    )
    report_dir().mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    latest = latest_report_path()
    write_text_atomic(latest, text)
    run_id = str(report.get("run_id") or "unknown")
    run_path = report_path_for_run(run_id)
    write_text_atomic(run_path, text)
    md = render_linkage_report_markdown(report)
    write_text_atomic(report_artifact_path(None, ".md"), md)
    write_text_atomic(report_artifact_path(run_id, ".md"), md)
    write_linkage_report_html(report, report_artifact_path(None, ".html"))
    write_linkage_report_html(report, report_artifact_path(run_id, ".html"))
    try:
        write_linkage_report_pdf(report, report_artifact_path(None, ".pdf"))
        write_linkage_report_pdf(report, report_artifact_path(run_id, ".pdf"))
    except RuntimeError as exc:
        logger.warning("linkage_report pdf skipped: %s", exc)
    logger.info("linkage_report written run_id=%s path=%s", run_id, run_path)
    return run_path


def load_linkage_report(run_id: str | None = None) -> dict[str, Any] | None:
    """读取报告；run_id 空则 latest。"""
    return _read_json_dict(report_artifact_path(run_id, ".json"))


def list_linkage_reports(limit: int = 40) -> dict[str, Any]:
    """列出归档 JSON（不含 latest.json 别名）。"""
    report_dir().mkdir(parents=True, exist_ok=True)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for path in report_dir().glob("*.json"):
        if path.name == "latest.json":
            continue
        data = _read_json_dict(path)
        if data is None:
            continue
        rid = str(data.get("run_id") or path.stem)
        generated = str(data.get("generated_at") or "")
        summary = data.get("action_summary") if isinstance(data.get("action_summary"), dict) else {}
        day = generated[:10] if len(generated) >= 10 else generated or "未知日期"
        ranked.append(
            (
                path.stat().st_mtime,
                {
                    "run_id": rid,
                    "generated_at": generated,
                    "label": f"{day} · {rid}",
                    "has_pdf": report_artifact_path(rid, ".pdf").is_file(),
                    "has_html": report_artifact_path(rid, ".html").is_file(),
                    "buy": int(summary.get("BUY") or 0),
                    "reduce": int(summary.get("REDUCE") or 0),
                    "hold": int(summary.get("HOLD") or 0),
                    "wait": int(summary.get("WAIT") or 0),
                },
            )
        )
    ranked.sort(key=lambda x: x[0], reverse=True)
    items = [row for _, row in ranked[: max(1, min(limit, 100))]]
    return {"items": items, "count": len(items)}


def delete_linkage_report(run_id: str) -> dict[str, Any]:
    """删除某次联动报告落盘（json/pdf/html/md）；若指向 latest 一并清掉。"""
    rid = (run_id or "").strip()
    if not rid or rid in {"latest", ".", ".."} or "/" in rid or "\\" in rid or ".." in rid:
        raise ValueError("invalid run_id")

    deleted: list[str] = []
    for ext in (".json", ".pdf", ".html", ".md"):
        path = report_artifact_path(rid, ext)
        if path.is_file():
            path.unlink()
            deleted.append(path.name)

    if not deleted:
        raise FileNotFoundError(f"report not found: {rid}")

    latest = _read_json_dict(latest_report_path())
    if latest and str(latest.get("run_id") or "") == rid:
        for ext in (".json", ".pdf", ".html", ".md"):
            path = report_artifact_path(None, ext)
            if path.is_file():
                path.unlink()
                deleted.append(path.name)

    return {"run_id": rid, "deleted": deleted, "ok": True}


def payload_from_result(result) -> dict[str, Any]:
    """唯一 raw payload 组装（linkage JSON / 报告输入）。"""
    from quant_shell.data.symbol import asset_type as resolve_asset_type

    pick_meta = _pick_lookup(result.stock_pick)
    error_codes = sorted(
        {
            str(e.get("error_code") or "PIPELINE_ERROR")
            for e in (result.phase_errors or [])
            if e.get("error") or e.get("error_code")
        }
    )
    return {
        "run_id": result.run_id,
        "timestamp": result.timestamp.isoformat(),
        "intel_ran": bool(result.intel_ran),
        "etf_runs": [_ctx_summary(ctx, resolve_asset_type) for ctx in result.etf_runs],
        "hold_runs": [_ctx_summary(ctx, resolve_asset_type) for ctx in result.hold_runs],
        "stock_runs": [
            _ctx_summary(ctx, resolve_asset_type, pick_meta)
            for ctx in result.stock_runs
        ],
        "stock_pick": _stock_pick_summary(result.stock_pick),
        "stock_intel_symbols": result.stock_intel_symbols,
        "alerts": [
            {"symbol": a.symbol, "level": a.level, "message": a.message[:120]}
            for a in result.monitor_alerts
        ],
        "phase_errors": list(result.phase_errors),
        "audit_error_codes": error_codes,
    }


def _pick_lookup(stock_pick) -> dict[str, object]:
    if stock_pick is None:
        return {}
    return {
        p.symbol: {
            "pick_rank": p.rank,
            "pick_score": p.score,
            "entry_eligible": p.entry_eligible,
            "entry_block_reason": p.entry_block_reason,
        }
        for p in stock_pick.picks
    }


def _ctx_summary(ctx, resolve_asset_type, pick_meta: dict[str, object] | None = None) -> dict[str, object]:
    from quant_shell.common.constants import LayerStatus

    at = (
        ctx.market.extra.get("asset_type", "")
        if ctx.market
        else resolve_asset_type(ctx.symbol)
    )
    fh = ctx.factor_health
    if ctx.signal and getattr(ctx.signal, "alpha_registry_scope", ""):
        alpha_scope = str(ctx.signal.alpha_registry_scope)
    elif fh and getattr(fh, "scope", ""):
        alpha_scope = str(fh.scope)
    else:
        alpha_scope = "etf" if at == "etf" else "stock"
    pnl = 0.0
    if ctx.context_pack:
        pnl = ctx.context_pack.risk_state.unrealized_pnl_pct
    action = ctx.ai_decision.action.value if ctx.ai_decision else "HOLD"
    mode = ctx.evaluation_mode
    signal_direction = ""
    if ctx.signal is not None and getattr(ctx.signal, "direction", None) is not None:
        signal_direction = str(ctx.signal.direction.value)
    summary: dict[str, object] = {
        "symbol": ctx.symbol,
        "asset_type": at,
        "evaluation_mode": mode,
        "verdict": _decision_verdict(action, mode),
        "trade_action": action,
        "execution": ctx.execution_result.status if ctx.execution_result else "none",
        "opportunity": round(ctx.signal.opportunity, 4) if ctx.signal else 0.0,
        "quality": (
            round(ctx.signal.quality, 4)
            if ctx.signal and ctx.signal.quality is not None
            else None
        ),
        "suggested_position": (
            round(float(ctx.policy_verdict.suggested_position), 4)
            if ctx.policy_verdict is not None
            else None
        ),
        "signal_direction": signal_direction,
        "unrealized_pnl_pct": round(pnl, 4),
        "reasons": list(ctx.ai_decision.reasoning_chain) if ctx.ai_decision else [],
        "risk_flags": list(ctx.ai_decision.risk_flags) if ctx.ai_decision else [],
        "human_review_required": bool(
            ctx.ai_decision.human_review_required if ctx.ai_decision else False
        ),
        "factor_scope": alpha_scope,
        "alpha_registry_scope": alpha_scope,
        "factor_active": fh.active_count if fh else 0,
        "factor_usable": fh.usable_count if fh else 0,
        "factor_coverage": round(fh.coverage if fh else 0.0, 4),
        "factor_disabled": fh.disabled_count if fh else 0,
        "trade_sleeve": ctx.policy_verdict.sleeve.value
        if ctx.policy_verdict is not None
        else "",
        "sleeve_reason": ctx.policy_verdict.sleeve_reason
        if ctx.policy_verdict is not None
        else "",
        "pipeline_error": next(
            (r.message for r in ctx.audit_trail if r.status == LayerStatus.ERROR),
            "",
        ),
    }
    if ctx.policy_verdict is None:
        summary["sleeve_reason"] = "MISSING_POLICY_VERDICT"
    _attach_intel_snapshot(summary, ctx)
    if ctx.market:
        extra = ctx.market.extra or {}
        summary["pe_percentile"] = round(float(ctx.market.pe_percentile), 4)
        summary["pe_reliable"] = bool(extra.get("pe_reliable", False))
        if extra.get("pe_ttm") is not None:
            summary["pe_ttm"] = round(float(extra["pe_ttm"]), 4)
        if extra.get("pe_percentile_source"):
            summary["pe_percentile_source"] = extra["pe_percentile_source"]
        if extra.get("pe_unreliable_reason"):
            summary["pe_unreliable_reason"] = extra["pe_unreliable_reason"]
    meta = (pick_meta or {}).get(ctx.symbol)
    if isinstance(meta, dict):
        summary["pick_rank"] = meta.get("pick_rank")
        summary["pick_score"] = round(float(meta.get("pick_score", 0)), 4)
        summary["entry_eligible"] = meta.get("entry_eligible")
        if meta.get("entry_block_reason"):
            summary["entry_block_reason"] = meta.get("entry_block_reason")
    return summary


def _attach_intel_snapshot(summary: dict[str, object], ctx) -> None:
    sent = getattr(ctx, "sentiment", None)
    if sent is None:
        summary["intel_available"] = False
        return
    summary["intel_available"] = True
    summary["sentiment_composite"] = round(float(sent.composite), 4)
    summary["cross_validation"] = round(float(sent.cross_validation), 4)
    events = list(sent.key_events or [])[:5]
    analyst = sent.analyst_report
    if analyst is not None:
        summary["analyst_action"] = str(analyst.recommended_action or "")
        summary["analyst_confidence"] = round(float(analyst.confidence), 4)
        summary["analyst_summary"] = str(analyst.executive_summary or "")[:240]
        if not events and analyst.facts:
            events = [str(f) for f in analyst.facts[:5]]
    summary["key_events"] = events
    brief = sent.intelligence_brief
    if brief is not None:
        summary["intel_source_count"] = int(brief.source_count)
        summary["intel_headline"] = str(brief.headline or "")[:160]


def _decision_verdict(action: str, evaluation_mode: str) -> str:
    mode = (evaluation_mode or "").lower()
    if mode == "entry":
        if action == "BUY":
            return "可买"
        if action in ("WAIT", "HOLD"):
            return "观望"
        return "不可买"
    mapping = {
        "HOLD": "持有",
        "REDUCE": "减仓",
        "EXIT": "清仓",
        "SELL": "卖出",
        "WAIT": "观望",
        "BUY": "加仓",
    }
    return mapping.get(action, action)


def _stock_pick_summary(stock_pick) -> dict[str, object]:
    if stock_pick is None:
        return {"status": "skipped", "picks": []}
    picks = [
        {
            "rank": p.rank,
            "symbol": p.symbol,
            "name": p.name,
            "score": round(p.score, 4),
            "entry_eligible": p.entry_eligible,
            "entry_block_reason": p.entry_block_reason,
        }
        for p in stock_pick.picks
    ]
    summary: dict[str, object] = {
        "status": "ok" if picks else "empty_after_gates",
        "universe": stock_pick.universe,
        "candidate_count": stock_pick.candidate_count,
        "filtered_count": stock_pick.filtered_count,
        "pick_count": len(picks),
        "note": "pick_rank 为截面排序；trade_action 见 stock_runs（七层决策）",
        "picks": picks,
    }
    if not picks and stock_pick.filtered_count == 0 and stock_pick.candidate_count > 0:
        summary["hint"] = (
            "候选股全部被 L4 硬过滤淘汰（市值/ROE/PE/量能/涨幅/涨停）；"
            "检查 build_universe_frame 字段是否有效"
        )
        if stock_pick.gate_diagnostics:
            summary["gate_diagnostics"] = stock_pick.gate_diagnostics
    return summary


def _factor_health_blurb(actions: list[dict[str, Any]]) -> str:
    if not actions:
        return "本轮无标的"
    candidates: list[tuple[float, object]] = []
    for item in actions:
        if item.get("pipeline_error"):
            continue
        gates = (item.get("decision_logic") or {}).get("gates") or {}
        flags = [str(f) for f in (gates.get("hard_risk_flags") or [])]
        if "PIPELINE_ERROR" in flags:
            continue
        cov = gates.get("factor_coverage")
        if cov is None:
            continue
        candidates.append((float(cov), gates.get("factor_usable")))
    if not candidates:
        return "本轮无可用因子覆盖（失败票不计入）"
    cov, usable = max(candidates, key=lambda row: row[0])
    return (
        f"覆盖 coverage={cov} usable={usable} "
        f"（详见各票 decision_logic.gates）"
    )


def _action_item(
    row: dict[str, Any],
    *,
    tab: str,
    alerts: list[Any],
    intel_ran: bool,
) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "")
    mode = str(row.get("evaluation_mode") or "")
    sleeve = str(row.get("trade_sleeve") or "")
    reasons = list(row.get("reasons") or [])
    risk_flags = list(row.get("risk_flags") or [])
    hard_flags = [
        f
        for f in risk_flags
        if is_hard_code(str(f))
        or "CRITICAL" in str(f).upper()
        or str(f).upper() == "PIPELINE_ERROR"
    ]
    signal_dir = row.get("signal_direction")
    decision_logic = {
        "reasoning_chain": reasons,
        "policy_path": f"{mode or 'unknown'}:{sleeve or 'n/a'}",
        "signal": {
            "opportunity": row.get("opportunity"),
            "quality": row.get("quality"),
            "suggested_position": row.get("suggested_position"),
            "direction": signal_dir,
        },
        "gates": {
            "factor_coverage": row.get("factor_coverage"),
            "factor_usable": row.get("factor_usable"),
            "factor_active": row.get("factor_active"),
            "entry_eligible": row.get("entry_eligible"),
            "entry_block_reason": row.get("entry_block_reason") or "",
            "hard_risk_flags": hard_flags,
        },
        "risk_flags": risk_flags,
        "valuation": {
            "pe_percentile": row.get("pe_percentile"),
            "pe_reliable": row.get("pe_reliable"),
            "pe_percentile_source": row.get("pe_percentile_source"),
        },
    }
    sym_alerts = [
        {
            "level": str(a.get("level") or ""),
            "message": str(a.get("message") or "")[:200],
        }
        for a in alerts
        if isinstance(a, dict) and str(a.get("symbol") or "") == symbol
    ]
    available = bool(row.get("intel_available"))
    if not intel_ran:
        source_hint = "skipped_intel"
        available = False
    elif available:
        source_hint = "L2 monitor/analyst"
    else:
        source_hint = "no_intel_for_symbol"

    key_events = list(row.get("key_events") or [])[:_KEY_EVENTS_CAP]
    intel = {
        "available": available,
        "source_hint": source_hint,
        "symbols_covered": [symbol] if available or sym_alerts else [],
        "alerts_for_symbol": sym_alerts,
        "analyst_summary": row.get("analyst_summary") or "",
        "analyst_action": row.get("analyst_action") or "",
        "analyst_confidence": row.get("analyst_confidence"),
        "cross_validation": row.get("cross_validation"),
        "sentiment_composite": row.get("sentiment_composite"),
        "key_events": key_events,
        "intel_headline": row.get("intel_headline") or "",
        "intel_source_count": row.get("intel_source_count"),
    }
    return {
        "symbol": symbol,
        "name": str(row.get("name") or ""),
        "tab": tab,
        "verdict": row.get("verdict"),
        "trade_action": row.get("trade_action"),
        "execution": row.get("execution"),
        "trade_sleeve": sleeve,
        "sleeve_reason": row.get("sleeve_reason") or "",
        "pipeline_error": row.get("pipeline_error") or "",
        "decision_logic": decision_logic,
        "intel": intel,
    }
