"""联动晨报叙事 — Markdown/HTML/PDF 共用的人话结构（唯一叙事入口）。"""
from __future__ import annotations

from typing import Any


_NEED_ACTIONS = frozenset({"BUY", "REDUCE", "EXIT", "SELL"})
_HARD_HINTS = ("STRATEGY_DEGRADED", "MONITOR_CRITICAL", "INTEL_REVIEW_HARD", "POLICY_HARD_TIGHTEN")


def split_action_buckets(
    actions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """需动手 / 值得看一眼 / 其余观望。"""
    need: list[dict[str, Any]] = []
    watch: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for item in actions:
        action = str(item.get("trade_action") or "").upper()
        if action in _NEED_ACTIONS:
            need.append(item)
            continue
        if _is_watch_worthy(item):
            watch.append(item)
            continue
        rest.append(item)
    return need, watch, rest


def headline_sentence(report: dict[str, Any]) -> str:
    """页首一句话结论（客户先读这行）。"""
    summary = report.get("action_summary") or {}
    buy = int(summary.get("BUY") or 0)
    reduce = int(summary.get("REDUCE") or 0)
    exit_n = int(summary.get("EXIT") or 0) + int(summary.get("SELL") or 0)
    wait = int(summary.get("WAIT") or 0)
    actions = report.get("actions") or []
    need, watch, _ = split_action_buckets(actions)

    parts: list[str] = []
    if buy == 0 and reduce == 0 and exit_n == 0:
        parts.append("本轮不建议新开仓")
    elif buy > 0:
        parts.append(f"系统建议买入 {buy} 笔")
    if reduce > 0:
        parts.append(f"建议减仓 {reduce} 笔")
    if exit_n > 0:
        parts.append(f"建议退出 {exit_n} 笔")
    if watch:
        parts.append(f"{len(watch)} 只接近门槛或被硬码拦住，值得扫一眼")
    elif wait and buy == 0:
        parts.append(f"其余 {wait} 只观望")
    if not parts:
        parts.append("本轮无显著动作")
    if need:
        syms = "、".join(_symbol_label(i) for i in need[:3])
        parts.append(f"优先处理：{syms}")
    return "。".join(parts) + "。"


def action_blurb(item: dict[str, Any]) -> str:
    """单票人话摘要（1–3 句）。"""
    action = str(item.get("trade_action") or "WAIT").upper()
    name = _symbol_label(item)
    logic = item.get("decision_logic") or {}
    sig = logic.get("signal") or {}
    gates = logic.get("gates") or {}
    intel = item.get("intel") or {}
    chain = [str(x) for x in (logic.get("reasoning_chain") or []) if x]
    hard = [str(f) for f in (gates.get("hard_risk_flags") or [])]

    opp = sig.get("opportunity")
    quality = sig.get("quality")
    head = f"**{name}** · {_action_cn(action)}"

    bits: list[str] = []
    if action in ("REDUCE", "EXIT", "SELL"):
        bits.append(_first_rule_reason(chain) or "持仓纪律触发")
    elif action == "BUY":
        bits.append(
            f"机会 {_fmt(opp)}，质量 {_fmt(quality)}，建议轻仓试探"
            if quality is not None
            else f"机会 {_fmt(opp)}，达到开仓线"
        )
    else:
        if hard:
            bits.append(f"本可偏多，但硬码收紧（{'/'.join(hard)}）")
        elif chain and "机会强度" in chain[0]:
            bits.append(chain[0].replace("策略政策: ", ""))
        else:
            bits.append(_first_rule_reason(chain) or "未达入场条件")

    # 长情报放依据折叠，正文保持短句
    tip = str(intel.get("analyst_action") or "").strip()
    if tip and tip.upper() not in ("", "MONITOR"):
        bits.append(f"分析师倾向 {tip}")

    return head + " — " + "；".join(bits) + "。"


def evidence_lines(item: dict[str, Any]) -> list[str]:
    """折叠区用的短依据列表。"""
    logic = item.get("decision_logic") or {}
    sig = logic.get("signal") or {}
    gates = logic.get("gates") or {}
    val = logic.get("valuation") or {}
    lines = [
        f"袖套 {item.get('trade_sleeve') or '—'} · {item.get('sleeve_reason') or ''}".strip(
            " ·"
        ),
        f"路径 {logic.get('policy_path') or '—'}",
    ]
    if sig.get("opportunity") is not None:
        lines.append(
            f"机会 { _fmt(sig.get('opportunity')) } · 质量 {_fmt(sig.get('quality'))} · "
            f"方向 {sig.get('direction') or '—'}"
        )
    if val.get("pe_percentile") is not None:
        rel = "可靠" if val.get("pe_reliable") else "不可靠"
        lines.append(f"PE 分位 {_fmt(val.get('pe_percentile'))}（{rel}）")
    if gates.get("factor_coverage") is not None:
        lines.append(
            f"因子 coverage={_fmt(gates.get('factor_coverage'))} "
            f"usable={gates.get('factor_usable')} active={gates.get('factor_active')}"
        )
    for r in (logic.get("reasoning_chain") or [])[:4]:
        lines.append(str(r))
    return [x for x in lines if x]


def one_line_rest(item: dict[str, Any]) -> str:
    logic = item.get("decision_logic") or {}
    chain = logic.get("reasoning_chain") or []
    sig = logic.get("signal") or {}
    tip = ""
    if chain:
        tip = str(chain[0]).replace("策略政策: ", "")
    elif sig.get("opportunity") is not None:
        tip = f"机会 {_fmt(sig.get('opportunity'))}"
    return f"{_symbol_label(item)} · {_action_cn(str(item.get('trade_action') or ''))} · {tip or '—'}"


def _is_watch_worthy(item: dict[str, Any]) -> bool:
    logic = item.get("decision_logic") or {}
    gates = logic.get("gates") or {}
    hard = gates.get("hard_risk_flags") or []
    if hard:
        return True
    flags = " ".join(str(f) for f in (logic.get("risk_flags") or []))
    if any(h in flags for h in _HARD_HINTS):
        return True
    chain0 = str((logic.get("reasoning_chain") or [""])[0])
    if "BUY → WAIT" in chain0 or "STRATEGY_DEGRADED" in chain0:
        return True
    sig = logic.get("signal") or {}
    opp = sig.get("opportunity")
    if opp is None:
        return False
    try:
        return abs(float(opp)) >= 0.30
    except (TypeError, ValueError):
        return False


def _symbol_label(item: dict[str, Any]) -> str:
    sym = str(item.get("symbol") or "")
    name = str(item.get("name") or "").strip()
    return f"{sym} {name}".strip() if name else sym


def _action_cn(action: str) -> str:
    return {
        "BUY": "买入",
        "REDUCE": "减仓",
        "EXIT": "清仓",
        "SELL": "卖出",
        "HOLD": "持有",
        "WAIT": "观望",
    }.get(action.upper(), action)


def _first_rule_reason(chain: list[str]) -> str:
    for r in chain:
        s = str(r)
        if s.startswith("POLICY_COMMIT:"):
            continue
        if s.startswith("QUALITY_SCALE:"):
            continue
        return s.replace("策略政策: ", "")
    return chain[0] if chain else ""


def _fmt(val: object) -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return str(val)


def _clip(text: str, n: int) -> str:
    t = " ".join(text.split())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"
