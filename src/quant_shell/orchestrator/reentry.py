"""再入场冷却 — 禁止同跑 EXIT 后立刻再买。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import Action, PipelineContext
from quant_shell.config.settings import settings
from quant_shell.execution.constants import (
    EXECUTION_STATUS_FILLED,
    PAPER_DATA_DIR,
    TRADES_FILENAME,
)

logger = get_logger(__name__)

_EXIT_ACTIONS = {Action.EXIT.value, Action.SELL.value}


def collect_exited_this_run(hold_runs: list[PipelineContext]) -> set[str]:
    """本轮 hold 审查中已成交 EXIT/SELL 的标的。"""
    exited: set[str] = set()
    for ctx in hold_runs:
        if not ctx.ai_decision or not ctx.execution_result:
            continue
        action = ctx.ai_decision.action.value
        status = str(ctx.execution_result.status or "")
        if action in _EXIT_ACTIONS and status == EXECUTION_STATUS_FILLED:
            exited.add(ctx.symbol)
    return exited


def symbols_in_reentry_cooldown(
    *,
    trades_path: Path | None = None,
    as_of: datetime | None = None,
    cooldown_days: int | None = None,
) -> set[str]:
    """最近 N 个日历日内有 EXIT/SELL 成交的标的。"""
    days = settings.reentry_cooldown_days if cooldown_days is None else cooldown_days
    if days <= 0:
        return set()
    path = trades_path or (PAPER_DATA_DIR / TRADES_FILENAME)
    if not path.exists():
        return set()
    now = as_of or datetime.now()
    cutoff = now - timedelta(days=days)
    blocked: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("reentry_cooldown read fail err=%s", exc)
        return set()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("reentry skip bad trade line err=%s", exc)
            continue
        action = str(row.get("action", ""))
        if action not in _EXIT_ACTIONS:
            continue
        ts_raw = row.get("timestamp")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw))
        except ValueError as exc:
            logger.warning("reentry skip bad timestamp ts=%s err=%s", ts_raw, exc)
            continue
        if ts >= cutoff:
            sym = str(row.get("symbol", "")).zfill(6)
            if sym:
                blocked.add(sym)
    return blocked


def entry_block_set(
    hold_runs: list[PipelineContext],
    *,
    held_set: set[str],
) -> set[str]:
    """本轮不可再买入的标的：已持仓 ∪ 本轮已出清 ∪ 冷却期。"""
    blocked = set(held_set)
    blocked |= collect_exited_this_run(hold_runs)
    blocked |= symbols_in_reentry_cooldown()
    return blocked
