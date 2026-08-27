"""Dashboard / decisions / positions / assistant — 空数据返回空状态。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from quant_shell.common.logging_config import get_logger
from quant_shell.config.settings import settings
from quant_shell.desk.loaders import (
    all_decision_items,
    load_equity_history,
    load_latest_linkage,
    load_linkage_by_run_id,
    load_portfolio_raw,
    load_position_notes,
    load_trades,
    list_linkage_runs,
    parse_iso,
    pick_name_map,
    save_position_notes,
)

logger = get_logger(__name__)


def _empty_action_counts() -> dict[str, int]:
    return {"WAIT": 0, "HOLD": 0, "REDUCE": 0, "BUY": 0, "OTHER": 0}


def _action_counts(linkage: dict[str, Any]) -> dict[str, int]:
    counts = _empty_action_counts()
    for item in all_decision_items(linkage):
        action = str(item.get("trade_action") or "OTHER").upper()
        if action in counts:
            counts[action] += 1
        else:
            counts["OTHER"] += 1
    return counts


def _mark_prices_from_cost(
    positions: dict[str, Any],
) -> tuple[dict[str, float], bool, str | None]:
    """无外部行情时用成本价占位；标记 stale。"""
    prices: dict[str, float] = {}
    for sym, pos in positions.items():
        code = str(sym).zfill(6)
        cost = float(pos.get("avg_cost") or 0)
        if cost > 0:
            prices[code] = cost
    return prices, True, None


def build_snapshot(*, live: bool = False) -> dict[str, Any]:  # noqa: ARG001
    linkage = load_latest_linkage()
    portfolio = load_portfolio_raw()
    cash = float(portfolio.get("cash") or settings.paper_initial_cash)
    positions = portfolio.get("positions") or {}
    live_prices, stale, price_as_of = _mark_prices_from_cost(positions)

    position_value = 0.0
    for sym, pos in positions.items():
        code = str(sym).zfill(6)
        qty = float(pos.get("quantity") or 0)
        price = float(live_prices.get(code) or 0)
        position_value += qty * price

    equity = cash + position_value
    hist = load_equity_history(limit=60)
    return {
        "equity": round(equity, 2),
        "cash": round(cash, 2),
        "position_value": round(position_value, 2),
        "position_pct": round(position_value / equity, 4) if equity > 0 else 0.0,
        "initial_cash": float(portfolio.get("initial_cash") or settings.paper_initial_cash),
        "last_run_at": str(linkage.get("timestamp") or portfolio.get("updated_at") or ""),
        "run_id": linkage.get("run_id"),
        "action_counts": _action_counts(linkage) if linkage else _empty_action_counts(),
        "alerts": list(linkage.get("alerts") or [])[:3],
        "recent_trades": list(reversed(load_trades(limit=20)))[:3],
        "price_stale": stale,
        "price_as_of": price_as_of,
        "equity_change_pct": None,
        "equity_prev": None,
        "sim": True,
        "empty": not bool(linkage) and not positions and not hist,
    }


def build_positions(*, live: bool = False) -> dict[str, Any]:  # noqa: ARG001
    linkage = load_latest_linkage()
    portfolio = load_portfolio_raw()
    positions_raw = portfolio.get("positions") or {}
    prices, stale, price_as_of = _mark_prices_from_cost(positions_raw)
    names = pick_name_map(linkage)
    notes = load_position_notes()
    now = datetime.now()
    rows: list[dict[str, Any]] = []
    total_pnl = 0.0
    total_cost = 0.0

    for sym, pos in positions_raw.items():
        code = str(sym).zfill(6)
        qty = float(pos.get("quantity") or 0)
        cost = float(pos.get("avg_cost") or 0)
        peak = float(pos.get("peak_price") or 0)
        price = float(prices.get(code) or 0)
        mkt = qty * price
        cost_basis = qty * cost
        pnl = mkt - cost_basis
        pnl_pct = (price / cost - 1.0) if cost > 0 else 0.0
        opened = parse_iso(pos.get("opened_at"))
        hold_days = (now - opened).days if opened else 0
        peak_pct = (peak / cost - 1.0) if cost > 0 and peak > 0 else 0.0
        total_pnl += pnl
        total_cost += cost_basis
        rows.append(
            {
                "symbol": code,
                "name": names.get(code, ""),
                "quantity": qty,
                "avg_cost": round(cost, 4),
                "price": round(price, 4),
                "market_value": round(mkt, 2),
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_pct": round(pnl_pct, 4),
                "holding_days": hold_days,
                "peak_price": round(peak, 4),
                "peak_pct": round(peak_pct, 4),
                "opened_at": pos.get("opened_at"),
                "last_action": None,
                "last_verdict": None,
                "note": notes.get(code, ""),
                "weight": 0.0,
            }
        )

    cash = float(portfolio.get("cash") or settings.paper_initial_cash)
    equity = cash + sum(r["market_value"] for r in rows)
    for r in rows:
        r["weight"] = round(r["market_value"] / equity, 4) if equity > 0 else 0.0

    return {
        "positions": rows,
        "cash": round(cash, 2),
        "equity": round(equity, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / total_cost, 4) if total_cost > 0 else 0.0,
        "price_stale": stale,
        "price_as_of": price_as_of,
        "updated_at": portfolio.get("updated_at"),
        "run_id": linkage.get("run_id"),
        "generated_at": linkage.get("timestamp") or portfolio.get("updated_at"),
        "empty": len(rows) == 0,
    }


def build_overview(*, live: bool = False, runs_limit: int = 40) -> dict[str, Any]:
    return {
        "snapshot": build_snapshot(live=live),
        "positions": build_positions(live=live),
        "runs": list_linkage_runs(limit=runs_limit),
    }


def _slim_decision(item: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "symbol",
        "name",
        "tab",
        "asset_type",
        "evaluation_mode",
        "verdict",
        "trade_action",
        "execution",
        "opportunity",
        "quality",
        "suggested_position",
        "unrealized_pnl_pct",
        "reasons",
        "risk_flags",
        "pe_percentile",
        "human_review_required",
        "pick_rank",
        "pick_score",
        "entry_eligible",
        "trade_sleeve",
    )
    return {k: item[k] for k in keep if k in item}


def build_decisions(
    *,
    tab: str = "hold",
    filter_name: str = "all",
    run_id: str | None = None,
) -> dict[str, Any]:
    if run_id:
        linkage = load_linkage_by_run_id(run_id)
        if linkage is None:
            return {"error": "run_not_found", "items": [], "run_id": run_id}
    else:
        linkage = load_latest_linkage()

    items = [
        _slim_decision(i)
        for i in all_decision_items(linkage)
        if i.get("tab") == tab
    ]
    if filter_name == "buyable":
        items = [
            i
            for i in items
            if str(i.get("trade_action") or "").upper() == "BUY"
            or i.get("entry_eligible") is True
        ]
    elif filter_name == "executed":
        items = [i for i in items if str(i.get("execution") or "").lower() == "filled"]
    elif filter_name == "manual":
        items = [i for i in items if bool(i.get("human_review_required"))]

    return {
        "tab": tab,
        "filter": filter_name,
        "run_id": linkage.get("run_id") if linkage else None,
        "generated_at": linkage.get("timestamp") if linkage else None,
        "items": items,
        "empty": len(items) == 0,
    }


def build_runs() -> dict[str, Any]:
    return {"runs": list_linkage_runs(limit=40)}


def build_run_diff(base_run_id: str | None = None) -> dict[str, Any]:
    latest = load_latest_linkage()
    base = load_linkage_by_run_id(base_run_id) if base_run_id else None
    return {
        "base_run_id": base_run_id,
        "latest_run_id": latest.get("run_id"),
        "changes": [],
        "empty": not latest and not base,
        "message": "尚无可比对的历史 run" if not latest else "diff 精简版：仅返回 run 元数据",
    }


def build_ohlcv(code: str, limit: int = 120) -> dict[str, Any]:
    """尽力拉日 K；失败返回空数组。"""
    symbol = str(code).zfill(6)
    try:
        from quant_shell.data.symbol import fetch_daily_ohlcv

        frame = fetch_daily_ohlcv(symbol)
        if frame is None or getattr(frame, "empty", True):
            return {"symbol": symbol, "data": [], "error": "no data"}
        tail = frame.tail(limit)
        data = []
        for idx, row in tail.iterrows():
            data.append(
                {
                    "date": str(idx.date() if hasattr(idx, "date") else idx),
                    "open": float(row.get("open") or 0),
                    "high": float(row.get("high") or 0),
                    "low": float(row.get("low") or 0),
                    "close": float(row.get("close") or 0),
                    "volume": float(row.get("volume") or 0),
                }
            )
        return {"symbol": symbol, "data": data}
    except Exception as exc:  # noqa: BLE001 — desk soft fail
        logger.warning("ohlcv fail symbol=%s err=%s", symbol, exc)
        return {"symbol": symbol, "data": [], "error": str(exc)}


def update_note(code: str, note: str) -> dict[str, Any]:
    symbol = str(code).zfill(6)
    notes = load_position_notes()
    notes[symbol] = note
    save_position_notes(notes)
    return {"symbol": symbol, "note": note}


def ask_assistant(question: str) -> dict[str, Any]:
    """基于最近 linkage 缓存回答；无 Key / 无数据时软降级。"""
    linkage = load_latest_linkage()
    portfolio = load_portfolio_raw()
    generated_at = datetime.now().isoformat()
    if not linkage:
        return {
            "answer": (
                "当前还没有联动报告。请先在「交易想法」保存模型，"
                "再到「任务中心」跑一次纸面或 linkage。"
            ),
            "generated_at": generated_at,
            "sources": [],
        }

    summary = (
        f"最近 run={linkage.get('run_id') or '—'}，"
        f"时间={linkage.get('timestamp') or '—'}，"
        f"现金={float(portfolio.get('cash') or 0):,.0f}，"
        f"持仓数={len(portfolio.get('positions') or {})}。"
    )
    if not settings.has_deepseek:
        return {
            "answer": (
                f"{summary}\n\n未配置 DEEPSEEK_API_KEY，无法做深度问答。"
                f"你的问题：「{question.strip()}」"
            ),
            "generated_at": generated_at,
            "sources": ["linkage_cache"],
        }

    try:
        from quant_shell.intelligence.analyst.deepseek_client import chat_json

        messages = [
            {
                "role": "system",
                "content": (
                    "你是模拟盘助手。只根据给定 JSON 缓存回答，不要编造成交。"
                    "用中文简短回答。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"问题：{question.strip()}\n\n"
                    f"linkage 摘要字段：run_id={linkage.get('run_id')} "
                    f"timestamp={linkage.get('timestamp')} "
                    f"phase_errors={linkage.get('phase_errors')}\n"
                    f"portfolio cash={portfolio.get('cash')} "
                    f"positions={list((portfolio.get('positions') or {}).keys())}"
                ),
            },
        ]
        raw = chat_json(messages)
        answer = str(raw.get("answer") or raw.get("summary") or raw)
        return {
            "answer": answer if isinstance(answer, str) else str(raw),
            "generated_at": generated_at,
            "sources": ["linkage_cache", "deepseek"],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("assistant fail err=%s", exc)
        return {
            "answer": f"{summary}\n\n助手调用失败：{exc}",
            "generated_at": generated_at,
            "sources": ["linkage_cache"],
        }
