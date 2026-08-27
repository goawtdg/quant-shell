"""因子运维公共流程 — OHLCV 面板拉取与截面评估。"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable

import pandas as pd

from quant_shell.common import audit
from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.config.settings import settings
from quant_shell.data.akshare_client import fetch_etf_daily_ohlcv, fetch_etf_spot_batch
from quant_shell.data.stock_client import fetch_stock_daily_ohlcv
from quant_shell.data.symbol import ETF_PREFIXES
from quant_shell.data.universe import fetch_index_constituents
from quant_shell.risk.ic_monitor import evaluate_factor_ic
from quant_shell.factors.registry import FactorRegistry
from quant_shell.factors.state_store import load_registry
from quant_shell.risk.cross_section_ic import (
    CrossSectionICResult,
    evaluate_registry_cross_section,
)

logger = get_logger(__name__)

_DEFAULT_OHLCV_WORKERS = 12


def _ohlcv_workers() -> int:
    """并行拉日 K 的线程数（环境变量 FACTOR_OHLCV_WORKERS，默认 12，上限 16）。"""
    raw = os.environ.get("FACTOR_OHLCV_WORKERS", str(_DEFAULT_OHLCV_WORKERS))
    try:
        n = int(raw)
    except ValueError:
        n = _DEFAULT_OHLCV_WORKERS
    return max(1, min(16, n))


def _fetch_ohlcv_map_parallel(
    symbols: list[str],
    fetch_one: Callable[[str], pd.DataFrame],
    *,
    label: str,
) -> dict[str, pd.DataFrame]:
    """并行拉取日 K；已命中磁盘缓存的请求也会很快返回。"""
    total = len(symbols)
    workers = min(_ohlcv_workers(), max(1, total))
    logger.info("%s start total=%d workers=%d", label, total, workers)
    panels: dict[str, pd.DataFrame] = {}
    if total == 0:
        return panels

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, symbol): symbol for symbol in symbols}
        for fut in as_completed(futures):
            symbol = futures[fut]
            done += 1
            try:
                panels[symbol] = fut.result()
            except (DataFetchError, ValidationError, OSError) as exc:
                audit.emit(
                    layer="L5",
                    event="ohlcv_skip",
                    severity="ERROR",
                    symbol=symbol,
                    error_code="DATA_FETCH",
                    message=str(exc),
                    data={"label": label},
                )
                logger.warning("%s skip symbol=%s err=%s", label, symbol, exc)
            if done == 1 or done % 10 == 0 or done == total:
                logger.info(
                    "%s progress=%d/%d ok=%d",
                    label,
                    done,
                    total,
                    len(panels),
                )
    logger.info("%s done ok=%d/%d", label, len(panels), total)
    return panels


def fetch_symbol_ohlcv_map(
    symbols: list[str],
    *,
    max_symbols: int | None = None,
) -> dict[str, pd.DataFrame]:
    """批量拉取股票日 K，跳过失败标的。"""
    subset = symbols[:max_symbols] if max_symbols else symbols
    return _fetch_ohlcv_map_parallel(
        subset,
        fetch_stock_daily_ohlcv,
        label="fetch_symbol_ohlcv_map",
    )


def evaluate_alpha_cross_section(
    symbols: list[str],
    registry: FactorRegistry | None = None,
    *,
    max_symbols: int | None = None,
) -> tuple[list[CrossSectionICResult], dict[str, pd.DataFrame]]:
    """对标的列表做 alpha 截面 IC 评估。"""
    reg = registry or load_registry(scope="stock")
    panels = fetch_symbol_ohlcv_map(symbols, max_symbols=max_symbols)
    logger.info(
        "evaluate_alpha_cross_section computing IC panels=%d factors=%d",
        len(panels),
        len(reg.all_specs()),
    )
    results = evaluate_registry_cross_section(panels, reg)
    logger.info("evaluate_alpha_cross_section done")
    return results, panels


def load_universe_symbols(universe: str, max_symbols: int | None = None) -> list[str]:
    """拉取指数成分并截断。"""
    symbols = fetch_index_constituents(universe)
    return symbols[:max_symbols] if max_symbols else symbols


# 现货接口失败时的流动性兜底池（宽基 / 常见主题）
_ETF_UNIVERSE_FALLBACK: tuple[str, ...] = (
    "510300",
    "510500",
    "159915",
    "588000",
    "512100",
    "513100",
    "512880",
    "515880",
    "159919",
    "510050",
    "512690",
    "159922",
)


def load_etf_universe(max_etfs: int = 20) -> list[str]:
    """按成交额选取流动性最好的 ETF（含 MONITOR_SYMBOLS）。"""
    symbols: list[str] = []
    seen: set[str] = set()

    def _add(code: str) -> None:
        if code in seen or len(symbols) >= max_etfs:
            return
        if len(code) != 6:
            return
        if not code.startswith(ETF_PREFIXES):
            return
        seen.add(code)
        symbols.append(code)

    for sym in settings.monitor_symbol_list:
        _add(sym.zfill(6))

    try:
        batch = fetch_etf_spot_batch()
        vol_col = "成交量"
        code_col = "代码"
        ranked = batch.sort_values(vol_col, ascending=False)
        for code in ranked[code_col].astype(str).str.zfill(6):
            _add(code)
    except (DataFetchError, ValidationError, OSError) as exc:
        audit.emit(
            layer="L5",
            event="layer_error",
            severity="ERROR",
            error_code="ETF_UNIVERSE_SPOT_FAIL",
            message=str(exc),
        )
        logger.warning("load_etf_universe spot failed; using fallback err=%s", exc)
        for code in _ETF_UNIVERSE_FALLBACK:
            _add(code)

    logger.info("load_etf_universe count=%d", len(symbols))
    return symbols


def fetch_etf_ohlcv_map(
    symbols: list[str],
    *,
    max_symbols: int | None = None,
) -> dict[str, pd.DataFrame]:
    """批量拉取 ETF 日 K，跳过失败标的。"""
    subset = symbols[:max_symbols] if max_symbols else symbols
    return _fetch_ohlcv_map_parallel(
        subset,
        fetch_etf_daily_ohlcv,
        label="fetch_etf_ohlcv_map",
    )


def evaluate_pooled_timeseries_ic(
    symbol_ohlcv: dict[str, pd.DataFrame],
    registry: FactorRegistry,
) -> list[CrossSectionICResult]:
    """多 ETF 时序 IC 取中位数（避免单标的噪声误杀）。"""
    import numpy as np

    ic_buckets: dict[str, list[float]] = {spec.name: [] for spec in registry.all_specs()}
    ir_buckets: dict[str, list[float]] = {spec.name: [] for spec in registry.all_specs()}

    for symbol, ohlcv in symbol_ohlcv.items():
        if ohlcv.empty:
            continue
        for spec in registry.all_specs():
            mean_ic, ir, samples = evaluate_factor_ic(ohlcv, spec)
            if samples <= 0:
                continue
            ic_buckets[spec.name].append(mean_ic)
            ir_buckets[spec.name].append(ir)

    results: list[CrossSectionICResult] = []
    for spec in registry.all_specs():
        ics = ic_buckets.get(spec.name, [])
        if not ics:
            results.append(CrossSectionICResult(spec.name, 0.0, 0.0, 0))
            continue
        irs = ir_buckets.get(spec.name, [0.0])
        results.append(
            CrossSectionICResult(
                name=spec.name,
                mean_ic=float(np.median(ics)),
                ir=float(np.median(irs)),
                sample_count=len(ics),
            )
        )
    return results


def evaluate_etf_alpha_pooled(
    symbols: list[str] | None = None,
    registry: FactorRegistry | None = None,
    *,
    max_etfs: int = 20,
) -> tuple[list[CrossSectionICResult], dict[str, pd.DataFrame]]:
    """对 ETF 池做 pooled 时序 IC 评估。"""
    reg = registry or load_registry(scope="etf")
    sym_list = symbols or load_etf_universe(max_etfs=max_etfs)
    panels = fetch_etf_ohlcv_map(sym_list, max_symbols=max_etfs)
    results = evaluate_pooled_timeseries_ic(panels, reg)
    return results, panels
