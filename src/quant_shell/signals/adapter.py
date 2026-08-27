"""A 股因子适配 — winsorize / 时序 rank / 截面 rank。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_shell.signals.constants import (
    ADAPT_LOOKBACK,
    SIGNAL_CLAMP_MAX,
    SIGNAL_CLAMP_MIN,
    WINSOR_LOWER,
    WINSOR_UPPER,
)

_UNKNOWN_INDUSTRY = "未知"


def winsorize(series: pd.Series) -> pd.Series:
    """按分位数截断极端值。"""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return clean
    lower = clean.quantile(WINSOR_LOWER)
    upper = clean.quantile(WINSOR_UPPER)
    return clean.clip(lower=lower, upper=upper)


def ts_rank(series: pd.Series, lookback: int = ADAPT_LOOKBACK) -> float:
    """时序 rank：当前值在最近 lookback 窗口中的分位。"""
    clean = winsorize(series)
    if len(clean) < 2:
        return 0.5
    window = clean.iloc[-lookback:] if len(clean) >= lookback else clean
    current = float(window.iloc[-1])
    return float((window <= current).sum() / len(window))


def ts_zscore(series: pd.Series, lookback: int = ADAPT_LOOKBACK) -> float:
    """时序 z-score。"""
    clean = winsorize(series)
    if len(clean) < 2:
        return 0.0
    window = clean.iloc[-lookback:] if len(clean) >= lookback else clean
    std = float(window.std())
    if std == 0 or np.isnan(std):
        return 0.0
    return float((window.iloc[-1] - window.mean()) / std)


def cross_section_rank(values: dict[str, float]) -> dict[str, float]:
    """全市场截面 rank。"""
    if not values:
        return {}
    frame = pd.Series(values, dtype=float)
    ranked = frame.rank(pct=True, method="average")
    return {str(k): float(ranked[k]) for k in ranked.index}


def cross_section_rank_by_industry(
    values: dict[str, float],
    industries: dict[str, str],
) -> dict[str, float]:
    """行业内 rank；单票行业或未知行业回退全市场 rank。"""
    if not values:
        return {}
    series = pd.Series(values, dtype=float)
    industry = pd.Series(
        {sym: industries.get(sym, _UNKNOWN_INDUSTRY) for sym in series.index},
        dtype=str,
    )
    ranked: dict[str, float] = {}
    for ind in industry.unique():
        if not ind or ind == _UNKNOWN_INDUSTRY:
            continue
        syms = industry.index[industry == ind]
        sub = series.reindex(syms).dropna()
        if len(sub) < 2:
            continue
        pct = sub.rank(pct=True, method="average")
        ranked.update({str(k): float(v) for k, v in pct.items()})

    fallback_syms = [
        sym
        for sym in series.index
        if sym not in ranked
        or industry.get(sym, _UNKNOWN_INDUSTRY) in ("", _UNKNOWN_INDUSTRY)
    ]
    if fallback_syms:
        fallback = cross_section_rank(series.reindex(fallback_syms).dropna().to_dict())
        ranked.update(fallback)
    if not ranked:
        return cross_section_rank(values)
    return ranked


def cross_section_scores(
    values: dict[str, float],
    *,
    invert: bool = False,
    industries: dict[str, str] | None = None,
    industry_neutral: bool = True,
) -> dict[str, float]:
    """截面 rank 并映射到 [-1, 1]。"""
    if industry_neutral and industries:
        ranked = cross_section_rank_by_industry(values, industries)
    else:
        ranked = cross_section_rank(values)
    scores = {sym: rank_to_score(pct) for sym, pct in ranked.items()}
    if invert:
        return {sym: -score for sym, score in scores.items()}
    return scores


def cross_section_adapt_dataframe(
    frame: pd.DataFrame,
    invert_cols: set[str] | None = None,
    *,
    industries: dict[str, str] | None = None,
    industry_neutral: bool = True,
) -> pd.DataFrame:
    """对 DataFrame 每列做截面适配（默认行业中性 rank）。"""
    invert = invert_cols or set()
    adapted = pd.DataFrame(index=frame.index)
    industry_map = industries or {}
    for col in frame.columns:
        values = frame[col].dropna().astype(float).to_dict()
        scores = cross_section_scores(
            values,
            invert=col in invert,
            industries=industry_map,
            industry_neutral=industry_neutral and bool(industry_map),
        )
        adapted[col] = pd.Series(scores, dtype=float)
    return adapted.fillna(0.0)


def rank_to_score(percentile: float) -> float:
    """分位 [0,1] 映射到 [-1,1]。"""
    return max(SIGNAL_CLAMP_MIN, min(SIGNAL_CLAMP_MAX, percentile * 2 - 1))


def zscore_to_score(zscore: float, scale: float = 2.0) -> float:
    """z-score 映射到 [-1,1]。"""
    normalized = zscore / scale
    return max(SIGNAL_CLAMP_MIN, min(SIGNAL_CLAMP_MAX, normalized))
