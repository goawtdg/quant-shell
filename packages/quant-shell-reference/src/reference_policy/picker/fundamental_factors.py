"""第 4 层基本面因子健康报告（仅诊断，不自动 disable）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant_shell.common.logging_config import get_logger
from quant_shell.data.fundamentals import build_universe_frame
from quant_shell.risk.cross_section_ic import (
    CrossSectionICResult,
    evaluate_factor_cross_section,
)
from quant_shell.risk.ic_common import forward_returns

logger = get_logger(__name__)

_FUNDAMENTAL_DIR = Path("data/factor_fundamental_health")
_LATEST_PATH = _FUNDAMENTAL_DIR / "latest.json"

FUNDAMENTAL_FACTOR_NAMES: tuple[str, ...] = (
    "value_ep",
    "quality_roe",
    "momentum_3m",
    "industry_rel_momentum",
    "liquidity",
)


def evaluate_fundamentals_snapshot(frame: pd.DataFrame) -> list[CrossSectionICResult]:
    """对当前 universe 快照计算基本面因子截面统计（轻量）。"""
    if frame.empty or len(frame) < 5:
        return [
            CrossSectionICResult(name, 0.0, 0.0, 0)
            for name in FUNDAMENTAL_FACTOR_NAMES
        ]

    working = frame.set_index("symbol")
    pe_positive = working["pe"].where(working["pe"] > 0)
    ep = 1.0 / pe_positive
    ep_median = float(ep.median() or 0.05)
    if "industry" in working.columns:
        ind_median = working.groupby("industry")["return_3m"].transform("median")
        industry_rel = working["return_3m"] - ind_median
    else:
        industry_rel = working["return_3m"] * 0.0
    if "turnover_rate" in working.columns:
        liquidity = working["turnover_rate"].where(
            working["turnover_rate"] > 0,
            working["volume"] / working["volume_ma20"].replace(0, 1),
        )
    else:
        liquidity = working["volume"] / working["volume_ma20"].replace(0, 1)
    factor_map = {
        "value_ep": ep.fillna(ep_median),
        "quality_roe": working["roe"],
        "momentum_3m": working["return_3m"],
        "industry_rel_momentum": industry_rel,
        "liquidity": liquidity,
    }

    results: list[CrossSectionICResult] = []
    date_idx = pd.DatetimeIndex([datetime.now().date(), datetime.now().date()])
    for name in FUNDAMENTAL_FACTOR_NAMES:
        series = factor_map[name]
        factor_df = pd.DataFrame(
            {sym: [series[sym], series[sym]] for sym in series.index},
            index=date_idx,
        ).T
        ret_df = pd.DataFrame(
            {
                sym: [working.loc[sym, "return_3m"], working.loc[sym, "return_3m"]]
                for sym in working.index
            },
            index=date_idx,
        ).T
        mean_ic, ir, count, spread = evaluate_factor_cross_section(
            factor_df,
            ret_df,
            lookback=2,
        )
        results.append(
            CrossSectionICResult(
                name=name,
                mean_ic=mean_ic,
                ir=ir,
                sample_count=count,
                q5_q1_spread_annual=spread,
            )
        )
    return results


def save_fundamental_health_report(
    results: list[CrossSectionICResult],
    *,
    universe: str,
    symbol_count: int,
) -> Path:
    """持久化基本面因子健康报告。"""
    _FUNDAMENTAL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "universe": universe,
        "evaluated_at": datetime.now().isoformat(),
        "symbol_count": symbol_count,
        "factors": [
            {
                "name": r.name,
                "mean_ic": round(r.mean_ic, 4),
                "ir": round(r.ir, 4),
                "sample_count": r.sample_count,
                "q5_q1_spread_annual": round(r.q5_q1_spread_annual, 4),
            }
            for r in results
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    _LATEST_PATH.write_text(text, encoding="utf-8")
    logger.info("save_fundamental_health path=%s factors=%d", _LATEST_PATH, len(results))
    return _LATEST_PATH


def refresh_fundamental_health_report(
    universe: str,
    symbols: list[str],
    *,
    max_symbols: int | None = None,
    frame: pd.DataFrame | None = None,
    skip_industry: bool = False,
) -> list[CrossSectionICResult]:
    """拉取 universe 基本面并写入基本面因子健康报告。"""
    data = frame if frame is not None else build_universe_frame(
        symbols,
        max_symbols=max_symbols,
        skip_industry=skip_industry,
    )
    results = evaluate_fundamentals_snapshot(data)
    save_fundamental_health_report(
        results,
        universe=universe,
        symbol_count=len(data),
    )
    return results
