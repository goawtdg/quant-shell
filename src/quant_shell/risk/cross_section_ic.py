"""截面 IC 计算 — 股票选股专用。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_shell.common.logging_config import get_logger
from quant_shell.data.stock_metrics import is_at_limit_up
from quant_shell.factors.registry import FactorRegistry
from quant_shell.risk.constants import (
    FORWARD_RETURN_DAYS,
    IC_LOOKBACK_DAYS,
    MIN_IC_SAMPLES,
)
from quant_shell.risk.ic_common import forward_returns, ic_summary

logger = get_logger(__name__)

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class CrossSectionICResult:
    """单因子截面 IC 汇总。"""

    name: str
    mean_ic: float
    ir: float
    sample_count: int
    q5_q1_spread_annual: float = 0.0


def _align_panel(
    factor_frames: dict[str, pd.DataFrame],
    return_frame: pd.DataFrame,
    lookback: int,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """对齐因子面板与收益面板到公共日期窗口。"""
    if not factor_frames or return_frame.empty:
        return factor_frames, return_frame

    common_dates = return_frame.index
    for frame in factor_frames.values():
        common_dates = common_dates.intersection(frame.index)
    if len(common_dates) == 0:
        return factor_frames, return_frame

    if len(common_dates) > lookback:
        common_dates = common_dates[-lookback:]

    trimmed_returns = return_frame.loc[common_dates]
    trimmed_factors = {
        name: frame.loc[common_dates] for name, frame in factor_frames.items()
    }
    return trimmed_factors, trimmed_returns


def daily_cross_section_ic(
    factor_values: pd.DataFrame,
    forward_returns_df: pd.DataFrame,
    *,
    limit_up_mask: pd.DataFrame | None = None,
) -> pd.Series:
    """逐日截面 Pearson IC（行=日期，列=标的）。"""
    ics: list[float] = []
    dates: list[object] = []
    for date in factor_values.index:
        f_row = pd.to_numeric(factor_values.loc[date], errors="coerce")
        r_row = pd.to_numeric(forward_returns_df.loc[date], errors="coerce")
        aligned = pd.DataFrame({"factor": f_row, "ret": r_row}).dropna()
        if limit_up_mask is not None and date in limit_up_mask.index:
            blocked = limit_up_mask.loc[date].astype(bool)
            aligned = aligned.loc[~blocked.reindex(aligned.index, fill_value=False)]
        if len(aligned) < 5:
            continue
        if aligned["factor"].std() == 0 or aligned["ret"].std() == 0:
            continue
        ic = float(aligned["factor"].corr(aligned["ret"]))
        if not np.isnan(ic):
            ics.append(ic)
            dates.append(date)
    return pd.Series(ics, index=dates, dtype=float)


def quintile_long_short_spread(
    factor_values: pd.DataFrame,
    forward_returns_df: pd.DataFrame,
) -> float:
    """五分位多空年化 spread（Q5 - Q1 平均前瞻收益 × 年化）。"""
    spreads: list[float] = []
    for date in factor_values.index:
        f_row = pd.to_numeric(factor_values.loc[date], errors="coerce")
        r_row = pd.to_numeric(forward_returns_df.loc[date], errors="coerce")
        aligned = pd.DataFrame({"factor": f_row, "ret": r_row}).dropna()
        if len(aligned) < 10:
            continue
        try:
            aligned["quintile"] = pd.qcut(
                aligned["factor"],
                5,
                labels=False,
                duplicates="drop",
            )
        except ValueError:
            continue
        q5 = aligned.loc[aligned["quintile"] == aligned["quintile"].max(), "ret"].mean()
        q1 = aligned.loc[aligned["quintile"] == aligned["quintile"].min(), "ret"].mean()
        if pd.notna(q5) and pd.notna(q1):
            spreads.append(float(q5 - q1))

    if not spreads:
        return 0.0
    mean_spread = float(np.mean(spreads))
    rebalance_per_year = TRADING_DAYS_PER_YEAR / max(FORWARD_RETURN_DAYS, 1)
    return mean_spread * rebalance_per_year


def evaluate_factor_cross_section(
    factor_values: pd.DataFrame,
    forward_returns_df: pd.DataFrame,
    *,
    lookback: int = IC_LOOKBACK_DAYS,
    limit_up_mask: pd.DataFrame | None = None,
) -> tuple[float, float, int, float]:
    """评估单因子截面 IC 与五分位 spread。"""
    trimmed_f, trimmed_r = _align_panel(
        {"f": factor_values},
        forward_returns_df,
        lookback,
    )
    f_frame = trimmed_f["f"]
    r_frame = trimmed_r
    mask = limit_up_mask.loc[f_frame.index] if limit_up_mask is not None else None
    ic_series = daily_cross_section_ic(f_frame, r_frame, limit_up_mask=mask)
    if len(ic_series) < MIN_IC_SAMPLES // 5:
        return 0.0, 0.0, len(ic_series), 0.0
    mean_ic, ir, count = ic_summary(ic_series, lookback=None)
    spread = quintile_long_short_spread(f_frame, r_frame)
    return mean_ic, ir, count, spread


def _build_limit_up_mask(
    symbol: str,
    ohlcv: pd.DataFrame,
    dates: pd.Index,
) -> pd.Series:
    """逐日涨停标志（IC 评估剔除不可买样本）。"""
    close = pd.to_numeric(ohlcv["close"], errors="coerce")
    prev = close.shift(1)
    high = pd.to_numeric(ohlcv["high"], errors="coerce")
    flags = [
        is_at_limit_up(symbol, "", float(c), float(p), float(h))
        if pd.notna(c) and pd.notna(p) and pd.notna(h)
        else False
        for c, p, h in zip(close, prev, high)
    ]
    return pd.Series(flags, index=dates, dtype=bool)


def build_symbol_panels(
    symbol_ohlcv: dict[str, pd.DataFrame],
    registry: FactorRegistry,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame | None]:
    """从多标的 OHLCV 构建因子面板、前瞻收益面板与涨停掩码。"""
    factor_names = [spec.name for spec in registry.all_specs()]
    factor_panels: dict[str, dict[str, pd.Series]] = {n: {} for n in factor_names}
    return_panels: dict[str, pd.Series] = {}
    limit_masks: dict[str, pd.Series] = {}

    for symbol, ohlcv in symbol_ohlcv.items():
        if ohlcv.empty or "close" not in ohlcv.columns:
            continue
        close = pd.to_numeric(ohlcv["close"], errors="coerce")
        if "trade_date" in ohlcv.columns:
            dates = pd.to_datetime(ohlcv["trade_date"])
        elif ohlcv.index.name == "trade_date" or isinstance(ohlcv.index, pd.DatetimeIndex):
            dates = pd.to_datetime(ohlcv.index)
        else:
            dates = pd.RangeIndex(len(ohlcv))

        fwd = forward_returns(close)
        return_panels[symbol] = pd.Series(fwd.values, index=dates)
        limit_masks[symbol] = _build_limit_up_mask(symbol, ohlcv, dates)

        for spec in registry.all_specs():
            try:
                raw = pd.to_numeric(spec.compute(ohlcv), errors="coerce")
                if len(raw) == len(dates):
                    factor_panels[spec.name][symbol] = pd.Series(raw.values, index=dates)
            except (TypeError, ValueError, KeyError) as exc:
                logger.warning("panel skip symbol=%s factor=%s err=%s", symbol, spec.name, exc)

    return_frame = pd.DataFrame(return_panels)
    factor_frames = {
        name: pd.DataFrame(cols) for name, cols in factor_panels.items() if cols
    }
    limit_up_mask = pd.DataFrame(limit_masks) if limit_masks else None
    return factor_frames, return_frame, limit_up_mask


def evaluate_panels_cross_section(
    factor_frames: dict[str, pd.DataFrame],
    return_frame: pd.DataFrame,
    registry: FactorRegistry,
    *,
    lookback: int = IC_LOOKBACK_DAYS,
    limit_up_mask: pd.DataFrame | None = None,
) -> list[CrossSectionICResult]:
    """在已构建面板上按 lookback 评估截面 IC（避免双窗重复算因子）。"""
    if return_frame.empty:
        return []

    results: list[CrossSectionICResult] = []
    for spec in registry.all_specs():
        frame = factor_frames.get(spec.name)
        if frame is None or frame.empty:
            results.append(CrossSectionICResult(spec.name, 0.0, 0.0, 0))
            continue
        mean_ic, ir, count, spread = evaluate_factor_cross_section(
            frame,
            return_frame,
            lookback=lookback,
            limit_up_mask=limit_up_mask,
        )
        results.append(
            CrossSectionICResult(
                name=spec.name,
                mean_ic=mean_ic,
                ir=ir,
                sample_count=count,
                q5_q1_spread_annual=spread,
            )
        )
    return results


def evaluate_registry_cross_section(
    symbol_ohlcv: dict[str, pd.DataFrame],
    registry: FactorRegistry,
    *,
    lookback: int = IC_LOOKBACK_DAYS,
) -> list[CrossSectionICResult]:
    """评估注册表全部因子的截面 IC。"""
    factor_frames, return_frame, limit_up_mask = build_symbol_panels(symbol_ohlcv, registry)
    return evaluate_panels_cross_section(
        factor_frames,
        return_frame,
        registry,
        lookback=lookback,
        limit_up_mask=limit_up_mask,
    )
