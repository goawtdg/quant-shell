"""候选池硬过滤 — 指南 §12.2。"""
from __future__ import annotations

import pandas as pd

from quant_shell.common.logging_config import get_logger
from quant_shell.config.settings import settings
from quant_shell.data.symbol import requires_board_permission
from reference_policy.picker.constants import (
    MAX_PE_SANITY,
    MAX_RETURN_10D_GATE,
    MAX_RETURN_5D_GATE,
    MIN_MARKET_CAP_YUAN,
    MIN_PE_SANITY,
)

logger = get_logger(__name__)


def _is_st_name(name: str) -> bool:
    """ST / *ST 名称检测。"""
    upper = name.upper()
    return "ST" in upper


def _board_permission_ok(symbol: object) -> bool:
    """无板块准入门槛（或过滤关闭）时为 True。"""
    if not settings.pick_filter_board_permission:
        return True
    return not requires_board_permission(str(symbol))


def _gate_pass_counts(frame: pd.DataFrame) -> dict[str, int]:
    """统计各硬门槛在候选池中的通过数量。"""
    working = frame.copy()
    counts = {
        "market_cap": int((working["market_cap"] >= MIN_MARKET_CAP_YUAN).sum()),
        "pe_positive": int((working["pe"] > MIN_PE_SANITY).sum()),
        "pe_sane": int((working["pe"] <= MAX_PE_SANITY).sum()),
        "no_board_permission": int(
            working["symbol"].map(_board_permission_ok).astype(bool).sum()
        )
        if "symbol" in working.columns
        else len(working),
    }
    if "return_5d" in working.columns:
        counts["return_5d"] = int((working["return_5d"] <= MAX_RETURN_5D_GATE).sum())
    if "return_10d" in working.columns:
        counts["return_10d"] = int((working["return_10d"] <= MAX_RETURN_10D_GATE).sum())
    if "at_limit_up" in working.columns:
        counts["not_limit_up"] = int((~working["at_limit_up"].astype(bool)).sum())
    if "name" in working.columns:
        counts["not_st"] = int(
            (~working["name"].astype(str).map(_is_st_name)).sum()
        )
    return counts


def summarize_universe_gates(frame: pd.DataFrame) -> dict[str, int]:
    """返回候选池各硬门槛通过数（用于 latest.json 诊断）。"""
    if frame.empty:
        return {}
    return _gate_pass_counts(frame)


def apply_universe_gates(frame: pd.DataFrame) -> pd.DataFrame:
    """对基本面 DataFrame 应用硬过滤。

    Args:
        frame: 含 symbol / market_cap / pe / volume 等。ROE 和成交量不参与资格。

    Returns:
        过滤后的副本。
    """
    if frame.empty:
        return frame.copy()

    working = frame.copy()
    mask = (
        (working["market_cap"] >= MIN_MARKET_CAP_YUAN)
        & (working["pe"] > MIN_PE_SANITY)
        & (working["pe"] <= MAX_PE_SANITY)
    )
    if "symbol" in working.columns:
        mask &= working["symbol"].map(_board_permission_ok).astype(bool)
    if "return_5d" in working.columns:
        mask &= working["return_5d"] <= MAX_RETURN_5D_GATE
    if "return_10d" in working.columns:
        mask &= working["return_10d"] <= MAX_RETURN_10D_GATE
    if "at_limit_up" in working.columns:
        mask &= ~working["at_limit_up"].astype(bool)
    if "name" in working.columns:
        mask &= ~working["name"].astype(str).map(_is_st_name)

    filtered = working.loc[mask].reset_index(drop=True)
    logger.info(
        "apply_universe_gates in=%d out=%d board_filter=%s",
        len(frame),
        len(filtered),
        settings.pick_filter_board_permission,
    )
    if filtered.empty and len(frame) > 0:
        logger.warning("apply_universe_gates all rejected gate_pass=%s", _gate_pass_counts(frame))
    return filtered
